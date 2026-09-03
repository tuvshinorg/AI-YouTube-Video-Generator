"""Codex CLI as an alternative provider for text generation and images.

codex_chat() is used when AI_PROVIDER=codex (see modules/config.py). Every
call shells out to `codex exec` with --output-schema, so the caller gets
back a raw JSON string it can Pydantic-validate exactly like the llama.cpp
path in modules/feed.py.

codex_generate_image() is used when IMAGE_PROVIDER=codex. The `codex`
CLI binary has no image flag/subcommand of its own, but the agent it runs
has a built-in `image_gen` tool (see ~/.codex/skills/.system/imagegen) that
it can invoke from a plain-language prompt — no OPENAI_API_KEY needed, it
rides on the same Codex/ChatGPT login used for text. We run `codex exec`
with --sandbox workspace-write pointed at the target directory and ask the
agent to save its output there.
"""

from .config import *

import copy
import queue
import shutil
import subprocess
import sys
import threading
import uuid

CODEX_BIN = shutil.which("codex") or "codex"
CODEX_WORKDIR = os.path.join(BASE_DIR, "temp", "codex")


def _strict_schema(schema: dict) -> dict:
    """OpenAI's structured-output strict mode requires additionalProperties:
    false on every object in the schema — Pydantic's model_json_schema()
    doesn't emit that, so inject it recursively (including into $defs)."""
    schema = copy.deepcopy(schema)

    def _walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                node.setdefault("additionalProperties", False)
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(schema)
    return schema


def codex_login_status() -> dict:
    """Return {'logged_in': bool, 'detail': str} from `codex login status`."""
    try:
        result = subprocess.run(
            [CODEX_BIN, "login", "status"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15,
        )
        detail = (result.stdout or result.stderr).strip()
        logged_in = result.returncode == 0 and "logged in" in detail.lower()
        return {"logged_in": logged_in, "detail": detail}
    except FileNotFoundError:
        return {"logged_in": False, "detail": "codex CLI not found on PATH"}
    except Exception as e:
        return {"logged_in": False, "detail": str(e)}


def _pipe_lines(pipe, q: "queue.Queue"):
    try:
        for line in iter(pipe.readline, ""):
            q.put(line)
    finally:
        q.put(None)   # EOF sentinel


def _drain_text(pipe, sink: list):
    """Reads *pipe* to EOF and appends the full text to *sink[0]* — run in a
    background thread so stderr is drained concurrently with the stdout
    JSONL loop below (an unread, full pipe buffer would otherwise deadlock
    the child)."""
    try:
        sink.append(pipe.read())
    except Exception:
        sink.append("")


def _kill_tree(pid: int):
    # On Windows, subprocess.kill() only kills the direct child — codex's
    # npm shim spawns node.exe as a separate process that isn't reliably
    # tracked as a child, so it survives and keeps stdout/stderr open,
    # making a plain kill() + wait() hang indefinitely instead of exiting.
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass


def _run_codex_exec(cmd: list[str], timeout: int, stdin_input: str | None = None,
                     on_event=None) -> str:
    """Run a `codex exec --json` command and return its stderr text.

    *cmd* should end with "-" as the prompt argument, with the actual prompt
    text passed as *stdin_input* instead of a CLI arg — CODEX_BIN resolves
    to codex.CMD (an npm-installed Windows batch shim), and cmd.exe mangles
    embedded newlines in command-line arguments, silently truncating any
    multi-line prompt to just its first line. Piping via stdin sidesteps
    that entirely (and any other shell-quoting hazards besides).

    *cmd* must include --json. Codex then streams one JSON object per stdout
    line — thread.started, item.started/item.completed for every tool call,
    turn.completed with usage — instead of staying silent until the whole
    process exits. This function reads that stream and applies two
    different limits instead of one blind timeout:

      - CODEX_STARTUP_IDLE_TIMEOUT: killed fast if *no event at all* has
        arrived for this long — Codex hasn't even started a tool call yet,
        which means it's genuinely stuck (dead network, waiting on an
        approval that'll never come), not just working slowly.
      - *timeout*: the overall ceiling, still enforced once a tool call is
        in flight. A real image/text generation can go fully silent for
        minutes inside a single tool call (confirmed empirically — no
        interim progress event exists to watch), so once one has started
        there is no signal left to react to early; this is what actually
        protects against a truly runaway call.

    *on_event*, if given, is called with each parsed event dict — callers
    use it to log real progress (e.g. which command Codex is running)
    instead of a generic "please wait".

    Raises RuntimeError on either timeout (after killing the process tree)
    or a non-zero exit code. Shared by codex_chat() and codex_generate_image().
    """
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )

    stdout_q: "queue.Queue" = queue.Queue()
    stderr_sink: list = []
    threading.Thread(target=_pipe_lines, args=(proc.stdout, stdout_q), daemon=True).start()
    threading.Thread(target=_drain_text, args=(proc.stderr, stderr_sink), daemon=True).start()

    if stdin_input is not None:
        try:
            proc.stdin.write(stdin_input)
        finally:
            proc.stdin.close()

    deadline = time.time() + timeout
    last_activity = time.time()
    open_tool_calls = 0
    timeout_reason = None

    while True:
        now = time.time()
        if now > deadline:
            timeout_reason = f"overall {timeout}s limit"
            break
        if open_tool_calls == 0 and (now - last_activity) > CODEX_STARTUP_IDLE_TIMEOUT:
            timeout_reason = f"no activity for {CODEX_STARTUP_IDLE_TIMEOUT}s"
            break

        wait = max(0.1, min(1.0, deadline - now))
        try:
            line = stdout_q.get(timeout=wait)
        except queue.Empty:
            continue
        if line is None:   # stdout closed — process is finishing up
            break
        last_activity = time.time()
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        etype = event.get("type")
        if etype == "item.started":
            open_tool_calls += 1
        elif etype == "item.completed":
            open_tool_calls = max(0, open_tool_calls - 1)
        if on_event:
            try:
                on_event(event)
            except Exception:
                pass

    if timeout_reason:
        _kill_tree(proc.pid)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        time.sleep(0.2)   # let the stderr-draining thread catch up
        partial_err = (stderr_sink[0] if stderr_sink else "").strip()[-500:]
        detail = f" — last output: {partial_err}" if partial_err else ""
        raise RuntimeError(f"codex exec timed out ({timeout_reason}) and was killed{detail}")

    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        proc.wait(timeout=5)
    stderr_text = stderr_sink[0] if stderr_sink else ""

    if proc.returncode != 0:
        raise RuntimeError(f"codex exec failed (exit {proc.returncode}): {stderr_text.strip()[-500:]}")
    return stderr_text


def _log_progress(prefix: str):
    """Builds an on_event callback that turns Codex's --json stream into
    real progress lines in pipeline.log, instead of the previous silence
    between "starting" and "finished/timed out"."""
    def _handler(event: dict):
        etype = event.get("type")
        if etype == "item.started" and event.get("item", {}).get("type") == "command_execution":
            command = (event["item"].get("command") or "")[:100]
            log.info(f"{prefix} running: {command}")
        elif etype == "item.completed" and event.get("item", {}).get("type") == "command_execution":
            log.info(f"{prefix} step finished (exit {event['item'].get('exit_code')})")
        elif etype == "turn.completed":
            tokens = (event.get("usage") or {}).get("output_tokens", "?")
            log.info(f"{prefix} done ({tokens} output tokens)")
    return _handler


def codex_chat(prompt: str, schema: dict | None = None, timeout: int | None = None) -> str:
    """Run one `codex exec` call and return its final message as raw text.

    Mirrors _llm_chat()'s contract in modules/feed.py: returns raw text
    (JSON, when *schema* is given) for the caller to validate. Runs with
    --sandbox read-only since this is pure text generation — Codex needs no
    shell/file-write access to answer a prompt, and shouldn't get any.
    """
    timeout = timeout or CODEX_TIMEOUT
    os.makedirs(CODEX_WORKDIR, exist_ok=True)

    call_id = uuid.uuid4().hex
    schema_path = os.path.join(CODEX_WORKDIR, f"schema_{call_id}.json")
    output_path = os.path.join(CODEX_WORKDIR, f"output_{call_id}.txt")

    cmd = [
        CODEX_BIN, "exec",
        "--skip-git-repo-check",
        "--sandbox", "read-only",
        "--ephemeral",
        "--json",
        "-C", CODEX_WORKDIR,
        "-o", output_path,
    ]
    if schema:
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(_strict_schema(schema), f)
        cmd += ["--output-schema", schema_path]
    cmd.append("-")  # read the (possibly multi-line) prompt from stdin — see _run_codex_exec

    try:
        stderr = _run_codex_exec(cmd, timeout, stdin_input=prompt, on_event=_log_progress("[codex]"))
        if not os.path.exists(output_path):
            raise RuntimeError(f"codex exec produced no output: {stderr.strip()[-500:]}")
        with open(output_path, encoding="utf-8") as f:
            return f.read()
    finally:
        for p in (schema_path, output_path):
            try:
                os.remove(p)
            except OSError:
                pass


def codex_generate_image(
    prompt: str,
    out_path: str,
    timeout: int | None = None,
    references: list[tuple[str, str]] | None = None,
    require_portrait: bool = True,
) -> None:
    """Generate one image via Codex's built-in `image_gen` tool and save it
    to *out_path*.

    Runs `codex exec` with --sandbox workspace-write scoped to out_path's
    directory (-C), and asks the agent — in plain language — to generate
    the image and save it there. The built-in tool always writes under
    $CODEX_HOME/generated_images/... first; the agent is asked to then copy
    that file into our target directory itself, but in practice it doesn't
    reliably follow through on the copy step. So as a fallback, if out_path
    still doesn't exist after the run, we copy the newest file created
    under generated_images/ during this call ourselves. No OPENAI_API_KEY
    required either way.

    *references* is an optional list of (role, file_path) pairs — e.g.
    [("character", char_png), ("background", bg_png)] — attached via -i so
    the agent composes the image using those exact assets for visual
    continuity, instead of inventing them fresh from text alone.

    *require_portrait* forces 9:16 vertical framing (the default, for final
    scene images matching the video canvas); pass False for one-off
    reference images (e.g. a character sheet) where orientation doesn't
    matter.
    """
    timeout = timeout or CODEX_IMAGE_TIMEOUT
    out_dir = os.path.dirname(out_path)
    filename = os.path.basename(out_path)
    os.makedirs(out_dir, exist_ok=True)

    codex_home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    generated_dir = os.path.join(codex_home, "generated_images")
    start_time = time.time()

    lines = [
        "Use case: photorealistic-natural",
        "Asset type: vertical mobile video background (YouTube Shorts/TikTok, 9:16)",
        f"Primary request: {prompt}",
    ]
    if references:
        input_desc = "; ".join(
            f"Image {i}: {role} reference — use this exact {role}'s appearance, "
            f"do not redesign or restyle it"
            for i, (role, _path) in enumerate(references, start=1)
        )
        lines.append(f"Input images: {input_desc}")
    if require_portrait:
        lines.append(
            "Composition/framing: portrait orientation, vertical 9:16 aspect "
            "ratio, frame is taller than it is wide"
        )
        lines.append(
            "Constraints: image must be portrait/vertical, never landscape or "
            "square, regardless of how cinematic or widescreen the scene "
            "description reads"
        )
    lines.append(f"Save the final PNG into the current directory as {filename}.")
    task = "\n".join(lines)

    cmd = [
        CODEX_BIN, "exec",
        "--skip-git-repo-check",
        "--sandbox", "workspace-write",
        "--ephemeral",
        "--json",
        "-C", out_dir,
    ]
    for _role, ref_path in (references or []):
        cmd += ["-i", ref_path]
    cmd.append("-")  # read the (multi-line) task from stdin — see _run_codex_exec

    # A timeout kill races the agent's own last write: it can finish writing
    # out_path (or the underlying image_gen tool call can land) moments
    # before/after we give up and taskkill it. Don't discard a completed
    # image just because the wrapper process was slow to exit afterwards —
    # check for the file before treating a timeout as a real failure.
    timeout_error = None
    try:
        stderr = _run_codex_exec(cmd, timeout, stdin_input=task, on_event=_log_progress("[image]"))
    except RuntimeError as e:
        if "timed out" not in str(e):
            raise
        timeout_error, stderr = e, ""

    if os.path.exists(out_path):
        return

    newest_path, newest_mtime = None, start_time
    if os.path.isdir(generated_dir):
        for root, _dirs, files in os.walk(generated_dir):
            for name in files:
                candidate = os.path.join(root, name)
                mtime = os.path.getmtime(candidate)
                if mtime >= newest_mtime:
                    newest_path, newest_mtime = candidate, mtime
    if not newest_path:
        raise timeout_error or RuntimeError(f"codex exec (image) produced no file: {stderr.strip()[-500:]}")
    shutil.copyfile(newest_path, out_path)
