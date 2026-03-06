#!/usr/bin/env python3
"""
AI YouTube Video Generator — interactive CLI manager

Usage
-----
  python cli.py              # interactive menu
  python cli.py add-rss      # add / validate an RSS feed
  python cli.py check-rss    # validate all saved feeds
  python cli.py add-json     # import entries from a JSON file
  python cli.py add-text     # manually type text → queue it
  python cli.py queue        # show pipeline queue status
  python cli.py run          # run the full pipeline now
  python cli.py run --output file   # run but skip YouTube upload
  python cli.py stop         # kill a running pipeline (remove lock)
"""

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import textwrap
from datetime import datetime

# ── Bootstrap: load .env so BASE_DIR / DB_PATH are resolved ──────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.getenv("BASE_DIR", _SCRIPT_DIR)
DB_PATH     = os.path.join(BASE_DIR, "main.db")
LOCK_FILE   = os.path.join(BASE_DIR, "pipeline.lock")
PYTHON      = sys.executable

GENRES = ["bright", "calm", "dark", "dramatic", "funky", "happy", "inspirational", "sad"]

# ── Colours (disabled automatically if stdout is not a tty) ──────────────────
_USE_COLOR = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text

def green(t):  return _c("32", t)
def yellow(t): return _c("33", t)
def red(t):    return _c("31", t)
def bold(t):   return _c("1",  t)
def cyan(t):   return _c("36", t)
def dim(t):    return _c("2",  t)


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def _db():
    """Return an open sqlite3 connection to the project database."""
    if not os.path.exists(DB_PATH):
        print(red(f"Database not found: {DB_PATH}"))
        print(yellow("Run  bash setup.sh  first to initialise the database."))
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _insert_rss(group: str, text: str, stamp: str = None) -> int:
    """Insert one entry into the RSS table and return its rssId."""
    stamp = stamp or datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    conn = _db()
    cur  = conn.execute(
        "INSERT INTO RSS (rssGroup, rssText, rssStamp) VALUES (?,?,?)",
        (group, text, stamp),
    )
    rss_id = cur.lastrowid
    conn.commit()
    conn.close()
    return rss_id


# ─────────────────────────────────────────────────────────────────────────────
# Lock helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pipeline_running() -> bool:
    if not os.path.exists(LOCK_FILE):
        return False
    try:
        with open(LOCK_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)   # signal 0 = probe only
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False


def _lock_pid() -> int | None:
    try:
        with open(LOCK_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# RSS validation
# ─────────────────────────────────────────────────────────────────────────────

def _validate_rss_url(url: str) -> tuple[bool, str]:
    """Return (ok, message). Requires feedparser."""
    try:
        import feedparser
    except ImportError:
        return False, "feedparser not installed — run: pip install feedparser"

    try:
        feed = feedparser.parse(url)
    except Exception as e:
        return False, f"Parse error: {e}"

    if feed.bozo and not feed.entries:
        return False, f"Feed error: {feed.bozo_exception}"
    if not feed.entries:
        return False, "Feed parsed but contains 0 entries"

    title = feed.feed.get("title", "(no title)")
    return True, f'Valid — "{title}" ({len(feed.entries)} entries)'


# ─────────────────────────────────────────────────────────────────────────────
# Prompt helpers
# ─────────────────────────────────────────────────────────────────────────────

def _prompt(msg: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{msg}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val or default


def _pick(msg: str, options: list[str], default: str = "") -> str:
    print(f"{msg}")
    for i, o in enumerate(options, 1):
        marker = " ◀" if o == default else ""
        print(f"  {i}. {o}{marker}")
    while True:
        raw = _prompt("Choose number", str(options.index(default) + 1) if default in options else "")
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(yellow("  Invalid choice, try again."))


# ─────────────────────────────────────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────────────────────────────────────

# ── add-rss ──────────────────────────────────────────────────────────────────

def cmd_add_rss(_args=None):
    """Add and validate an RSS feed URL, then save it for the next pipeline run."""
    print(bold("\n── Add RSS Feed ──────────────────────────────────────"))
    url   = _prompt("RSS feed URL")
    if not url:
        print(red("No URL entered."))
        return

    print(dim("  Validating …"))
    ok, msg = _validate_rss_url(url)
    if ok:
        print(green(f"  ✔ {msg}"))
    else:
        print(red(f"  ✘ {msg}"))
        if _prompt("Add anyway? (yes/no)", "no").lower() not in ("y", "yes"):
            return

    group = _prompt("Group / source name", url.split("/")[2].replace("www.", ""))
    # Fetch and store the raw feed text so the pipeline can process it
    try:
        import feedparser
        feed = feedparser.parse(url)
        saved = 0
        for entry in feed.entries:
            summary = entry.get("summary") or entry.get("description") or ""
            title   = entry.get("title", "")
            text    = f"{title}\n\n{summary}".strip()
            if text:
                _insert_rss(group, text, entry.get("published", ""))
                saved += 1
        print(green(f"  ✔ Saved {saved} entries from feed (group='{group}')"))
    except ImportError:
        # feedparser not available — save the URL itself as a reference
        _insert_rss(group, url)
        print(yellow("  ⚠ feedparser not installed; saved URL as-is."))
    except Exception as e:
        print(red(f"  Error fetching feed: {e}"))


# ── check-rss ────────────────────────────────────────────────────────────────

def cmd_check_rss(_args=None):
    """Validate all RSS groups stored in the database."""
    print(bold("\n── Check RSS Feeds ───────────────────────────────────"))
    conn = _db()
    rows = conn.execute(
        "SELECT rssGroup, COUNT(*) as n, MAX(rssStamp) as latest FROM RSS GROUP BY rssGroup ORDER BY rssGroup"
    ).fetchall()
    conn.close()

    if not rows:
        print(yellow("  No RSS entries in database yet."))
        return

    print(f"  {'Group':<20} {'Entries':>7}  {'Latest entry'}")
    print("  " + "─" * 55)
    for row in rows:
        print(f"  {row['rssGroup']:<20} {row['n']:>7}  {row['latest'] or '—'}")
    print()


# ── add-json ─────────────────────────────────────────────────────────────────

_JSON_SCHEMA = """\
Expected JSON format:
{
  "group": "my-source",
  "entries": [
    { "title": "...", "text": "..." },
    { "title": "...", "text": "..." }
  ]
}
Field "text" is required. "title" is prepended to text if provided.
"""

def cmd_add_json(_args=None):
    """Import entries from a JSON file into the RSS queue."""
    print(bold("\n── Import from JSON ──────────────────────────────────"))
    print(dim(_JSON_SCHEMA))
    path = _prompt("Path to JSON file")
    if not path:
        return
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        print(red(f"  File not found: {path}"))
        return

    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(red(f"  JSON parse error: {e}"))
        return

    group   = data.get("group") or os.path.splitext(os.path.basename(path))[0]
    entries = data.get("entries", [])
    if not entries:
        print(red("  No entries found in JSON."))
        return

    saved = 0
    for entry in entries:
        text = entry.get("text", "").strip()
        if not text:
            continue
        title = entry.get("title", "").strip()
        full  = f"{title}\n\n{text}".strip() if title else text
        _insert_rss(group, full)
        saved += 1

    print(green(f"  ✔ Imported {saved} entries (group='{group}')"))
    print(dim(f"  Run  make run  or  python cli.py run  to process them."))


# ── add-text ─────────────────────────────────────────────────────────────────

def cmd_add_text(_args=None):
    """Manually input text to queue a video without an RSS feed."""
    print(bold("\n── Manual Text Input ─────────────────────────────────"))
    print(dim("  The text you enter will be queued like an RSS article."))
    print(dim("  The pipeline will use it to generate scenes and a video.\n"))

    title = _prompt("Title (optional)")
    print("  Enter / paste your text below.")
    print(dim("  Finish with a line containing only  ---"))
    lines = []
    try:
        while True:
            line = input()
            if line.strip() == "---":
                break
            lines.append(line)
    except (EOFError, KeyboardInterrupt):
        pass
    text = "\n".join(lines).strip()
    if not text:
        print(red("  No text entered."))
        return

    full  = f"{title}\n\n{text}".strip() if title else text
    group = _prompt("Group label", "manual")
    rss_id = _insert_rss(group, full)
    print(green(f"  ✔ Queued as RSS entry #{rss_id} (group='{group}')"))
    print(dim(f"  Run  make run  or  python cli.py run  to process it."))


# ── queue ─────────────────────────────────────────────────────────────────────

def cmd_queue(_args=None):
    """Show the current pipeline queue and status of each video."""
    print(bold("\n── Pipeline Queue ────────────────────────────────────"))
    conn = _db()

    # Un-processed RSS entries (not yet turned into seeds)
    rss_pending = conn.execute(
        """SELECT rssId, rssGroup, SUBSTR(rssText,1,60) as snippet, rssStamp
           FROM RSS
           WHERE rssId NOT IN (SELECT rssId FROM SEED)
           ORDER BY rssId
           LIMIT 20"""
    ).fetchall()

    # Seeds and their pipeline stage
    seeds = conn.execute(
        """SELECT seedId, seedTitle,
             CASE
               WHEN seedUploadStamp   != '0000-00-00 00:00:00' THEN 'uploaded'
               WHEN seedRenderStamp   != '0000-00-00 00:00:00' THEN 'ready-to-upload'
               WHEN seedMixStamp      != '0000-00-00 00:00:00' THEN 'mixed'
               WHEN seedTransitionStamp != '0000-00-00 00:00:00' THEN 'transitioned'
               ELSE 'processing'
             END as stage,
             seedCreatedDate
           FROM SEED
           ORDER BY seedId DESC
           LIMIT 20"""
    ).fetchall()

    conn.close()

    # Lock status
    if _pipeline_running():
        pid = _lock_pid()
        print(yellow(f"  ● Pipeline is running (PID {pid})"))
    else:
        print(dim("  ○ Pipeline is idle"))

    print()
    if rss_pending:
        print(f"  {bold('Pending RSS entries')} (not yet processed into scenes):")
        print(f"  {'ID':>5}  {'Group':<16}  {'Fetched':<20}  Snippet")
        print("  " + "─" * 72)
        for r in rss_pending:
            snippet = (r["snippet"] or "").replace("\n", " ")
            print(f"  {r['rssId']:>5}  {(r['rssGroup'] or ''):<16}  {(r['rssStamp'] or '')[:19]:<20}  {snippet}…")
    else:
        print(dim("  No unprocessed RSS entries."))

    print()
    # Fetch error info too
    error_map = {}
    try:
        err_rows = conn.execute(
            "SELECT seedId, seedErrorStep, seedErrorMsg FROM SEED WHERE seedErrorStep IS NOT NULL"
        ).fetchall()
        for r in err_rows:
            error_map[r["seedId"]] = (r["seedErrorStep"], r["seedErrorMsg"])
    except Exception:
        pass   # column may not exist on old DBs yet
    conn.close()

    if seeds:
        print(f"  {bold('Videos in pipeline')}:")
        print(f"  {'ID':>5}  {'Stage':<18}  {'Created':<20}  Title")
        print("  " + "─" * 72)
        stage_color = {
            "uploaded":        green,
            "ready-to-upload": cyan,
            "mixed":           yellow,
            "transitioned":    yellow,
            "processing":      dim,
            "error":           red,
        }
        for s in seeds:
            sid   = s["seedId"]
            stage = "error" if sid in error_map else s["stage"]
            col   = stage_color.get(stage, str)
            title = (s["seedTitle"] or "")[:35]
            print(f"  {sid:>5}  {col(f'{stage:<18}')}  {(s['seedCreatedDate'] or '')[:19]:<20}  {title}")
            if sid in error_map:
                step, msg = error_map[sid]
                print(f"         {red('↳ failed at:')} {step}  —  {(msg or '')[:60]}")
                print(f"         {dim('  run: python cli.py retry ' + str(sid) + '  to clear error and re-queue')}")
    else:
        print(dim("  No videos in pipeline yet."))
    print()


# ── run ───────────────────────────────────────────────────────────────────────

def cmd_run(args=None):
    """Run the full pipeline now. Warns if already running."""
    output = getattr(args, "output", "api") if args else "api"
    print(bold(f"\n── Run Pipeline (output={output}) ────────────────────"))

    if _pipeline_running():
        pid = _lock_pid()
        print(yellow(f"  ⚠ Pipeline already running (PID {pid})."))
        choice = _prompt("Continue anyway? (yes/no)", "no")
        if choice.lower() not in ("y", "yes"):
            print("  Aborted.")
            return

    cmd = [PYTHON, os.path.join(BASE_DIR, "pipeline.py"), "--output", output]
    print(dim(f"  → {' '.join(cmd)}\n"))
    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        print(yellow("\n  Interrupted."))


# ── retry ────────────────────────────────────────────────────────────────────

def cmd_retry(args=None):
    """Clear the error state on a seed so the pipeline will retry it."""
    print(bold("\n── Retry Failed Video ────────────────────────────────"))
    seed_id_str = getattr(args, "seed_id", None) if args else None
    if not seed_id_str:
        seed_id_str = _prompt("Seed ID to retry")
    if not str(seed_id_str).isdigit():
        print(red("  Invalid seed ID."))
        return
    seed_id = int(seed_id_str)
    conn = _db()
    row = conn.execute("SELECT seedTitle, seedErrorStep FROM SEED WHERE seedId=?", (seed_id,)).fetchone()
    if not row:
        print(red(f"  Seed {seed_id} not found."))
        conn.close()
        return
    title, step = row["seedTitle"], row["seedErrorStep"]
    if not step:
        print(yellow(f"  Seed {seed_id} has no recorded error."))
        conn.close()
        return
    print(f"  Title: {title}")
    print(f"  Failed step: {red(step)}")
    conn.execute("UPDATE SEED SET seedErrorStep=NULL, seedErrorMsg=NULL WHERE seedId=?", (seed_id,))
    conn.commit()
    conn.close()
    print(green(f"  ✔ Error cleared — seed {seed_id} will be retried on next pipeline run."))


# ── stop ─────────────────────────────────────────────────────────────────────

def cmd_stop(_args=None):
    """Stop a running pipeline process."""
    print(bold("\n── Stop Pipeline ─────────────────────────────────────"))
    if not _pipeline_running():
        print(dim("  Pipeline is not running."))
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            print(yellow("  Stale lock file removed."))
        return

    pid = _lock_pid()
    print(yellow(f"  Pipeline is running with PID {pid}."))
    choice = _prompt("Send SIGTERM to stop it? (yes/no)", "no")
    if choice.lower() not in ("y", "yes"):
        print("  Aborted.")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        print(green(f"  ✔ SIGTERM sent to PID {pid}"))
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except ProcessLookupError:
        print(yellow("  Process already gone."))
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except PermissionError:
        print(red(f"  Permission denied — cannot signal PID {pid}"))


# ─────────────────────────────────────────────────────────────────────────────
# Interactive menu
# ─────────────────────────────────────────────────────────────────────────────

MENU = [
    ("1", "Add RSS feed",          cmd_add_rss),
    ("2", "Check RSS feeds",       cmd_check_rss),
    ("3", "Import from JSON",      cmd_add_json),
    ("4", "Enter text manually",   cmd_add_text),
    ("5", "Show queue",            cmd_queue),
    ("6", "Retry failed video",    cmd_retry),
    ("7", "Run pipeline (api)",    lambda _: cmd_run(type("A", (), {"output": "api"})())),
    ("8", "Run pipeline (file)",   lambda _: cmd_run(type("A", (), {"output": "file"})())),
    ("9", "Stop running pipeline", cmd_stop),
    ("q", "Quit",                  None),
]

def interactive_menu():
    print(bold("\n╔══════════════════════════════════════════╗"))
    print(bold("║  AI YouTube Video Generator — Manager   ║"))
    print(bold("╚══════════════════════════════════════════╝"))

    while True:
        # Quick status line
        status = yellow("● running") if _pipeline_running() else dim("○ idle")
        print(f"\n  Pipeline: {status}   DB: {dim(DB_PATH)}\n")

        for key, label, _ in MENU:
            print(f"  {cyan(key)})  {label}")
        print()

        try:
            choice = input("  Choose: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        for key, _, fn in MENU:
            if choice == key:
                if fn is None:
                    print("  Bye!")
                    return
                fn(None)
                break
        else:
            print(yellow("  Unknown option."))


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="AI YouTube Video Generator — management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python cli.py                  # interactive menu
              python cli.py add-rss          # add an RSS feed
              python cli.py add-text         # queue manual text
              python cli.py queue            # show status
              python cli.py run              # run full pipeline (uploads to YouTube)
              python cli.py run --output file  # run pipeline, save .mp4 locally only
              python cli.py stop             # stop a running pipeline
        """),
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("add-rss",    help="Add and validate an RSS feed URL")
    sub.add_parser("check-rss",  help="Validate all saved RSS groups")
    sub.add_parser("add-json",   help="Import entries from a JSON file")
    sub.add_parser("add-text",   help="Manually enter text to queue a video")
    sub.add_parser("queue",      help="Show pipeline queue and status")
    sub.add_parser("stop",       help="Stop a running pipeline process")

    retry_p = sub.add_parser("retry", help="Clear error state on a failed video so it is retried")
    retry_p.add_argument("seed_id", nargs="?", help="Seed ID to retry (prompted if omitted)")

    run_p = sub.add_parser("run", help="Run the full pipeline now")
    run_p.add_argument(
        "--output", "-o",
        choices=["api", "file"],
        default="api",
        help=(
            "api  = run all modules including YouTube upload (default)\n"
            "file = stop after final render; save .mp4 for manual upload"
        ),
    )

    args = parser.parse_args()

    dispatch = {
        "add-rss":   cmd_add_rss,
        "check-rss": cmd_check_rss,
        "add-json":  cmd_add_json,
        "add-text":  cmd_add_text,
        "queue":     cmd_queue,
        "run":       cmd_run,
        "retry":     cmd_retry,
        "stop":      cmd_stop,
    }

    if args.command:
        dispatch[args.command](args)
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
