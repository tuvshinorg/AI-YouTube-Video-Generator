"""Codex CLI as an alternative to llama.cpp for text generation.

Used when AI_PROVIDER=codex (see modules/config.py). Every call shells out
to `codex exec` with --output-schema, so the caller gets back a raw JSON
string it can Pydantic-validate exactly like the llama.cpp path in
modules/feed.py — this module only implements one function, codex_chat(),
matching that contract.

Codex has no image-generation capability at all, so this module is only
ever used for the text/scene-generation step; modules/image.py (Flux) is
unrelated and unaffected.
"""

from .config import *

import copy
import shutil
import subprocess
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
        "-C", CODEX_WORKDIR,
        "-o", output_path,
    ]
    if schema:
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(_strict_schema(schema), f)
        cmd += ["--output-schema", schema_path]
    cmd.append(prompt)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(f"codex exec failed (exit {result.returncode}): {result.stderr.strip()[-500:]}")
        if not os.path.exists(output_path):
            raise RuntimeError(f"codex exec produced no output: {result.stdout.strip()[-500:]}")
        with open(output_path, encoding="utf-8") as f:
            return f.read()
    finally:
        for p in (schema_path, output_path):
            try:
                os.remove(p)
            except OSError:
                pass
