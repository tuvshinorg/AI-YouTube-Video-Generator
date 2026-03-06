#!/usr/bin/env python3
"""
AI YouTube Video Generator — Pipeline Orchestrator
===================================================
Runs the 10 production modules in the correct order, skipping any that
have no pending work so heavy AI models (Llama, Flux, Whisper) are only
loaded when they are actually needed.

Usage
-----
  python pipeline.py                    # run all modules (state-aware)
  python pipeline.py --module feed      # run one module manually
  python pipeline.py --output file      # skip YouTube upload, save .mp4 locally

  make run          # alias for python pipeline.py --output api
  make run-file     # alias for python pipeline.py --output file
  make cli          # interactive manager (add RSS, queue status, retry…)
"""

import argparse
import logging
import os
import sqlite3
import sys

# ── Bootstrap: load .env so BASE_DIR / DB_PATH are available at import time ──
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.getenv("BASE_DIR", _SCRIPT_DIR)
DB_PATH     = os.path.join(BASE_DIR, "main.db")
LOCK_FILE   = os.path.join(BASE_DIR, "pipeline.lock")

# ── Logging (before module imports so every module shares this config) ────────
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(BASE_DIR, "logs", "pipeline.log")),
    ],
)
log = logging.getLogger("pipeline")

# ── Module imports (heavy AI deps loaded lazily inside each module) ───────────
from modules.feed       import run_feed
from modules.image      import run_image
from modules.voice      import run_voice
from modules.clip       import run_clip
from modules.subtitle   import run_subtitle
from modules.transition import run_transition
from modules.mix        import run_mix
from modules.final      import run_final
from modules.upload     import run_upload
from modules.clean      import run_clean

# ── Manual single-module dispatch table ──────────────────────────────────────
MODULES = {
    "feed":       run_feed,
    "image":      run_image,
    "voice":      run_voice,
    "clip":       run_clip,
    "subtitle":   run_subtitle,
    "transition": run_transition,
    "mix":        run_mix,
    "final":      run_final,
    "upload":     run_upload,
    "clean":      run_clean,
}


# ── DB migration ──────────────────────────────────────────────────────────────
def _migrate_db():
    """Add columns introduced after the initial schema, without dropping data."""
    conn = sqlite3.connect(DB_PATH)
    for col, definition in [
        ("seedErrorStep", "TEXT DEFAULT NULL"),
        ("seedErrorMsg",  "TEXT DEFAULT NULL"),
    ]:
        try:
            conn.execute(f"ALTER TABLE SEED ADD COLUMN {col} {definition}")
            log.info(f"[db] Added column SEED.{col}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


# ── State-check helpers (fast DB queries, no model loading) ───────────────────
def _count(sql: str) -> int:
    try:
        conn = sqlite3.connect(DB_PATH)
        n = conn.execute(sql).fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


def _pending_feed():
    return _count(
        "SELECT COUNT(*) FROM RSS "
        "WHERE rssId NOT IN (SELECT DISTINCT rssId FROM SEED WHERE rssId IS NOT NULL)"
    )

def _pending_image():
    return _count("SELECT COUNT(*) FROM TASK WHERE sceneImageDate='0000-00-00 00:00:00'")

def _pending_voice():
    return _count(
        "SELECT COUNT(*) FROM TASK "
        "WHERE sceneImageDate!='0000-00-00 00:00:00' AND sceneAudioDate='0000-00-00 00:00:00'"
    )

def _pending_clip():
    return _count(
        "SELECT COUNT(*) FROM TASK "
        "WHERE sceneAudioDate!='0000-00-00 00:00:00' AND sceneClipDate='0000-00-00 00:00:00'"
    )

def _pending_subtitle():
    return _count(
        "SELECT COUNT(*) FROM TASK "
        "WHERE sceneClipDate!='0000-00-00 00:00:00' AND sceneSubtitleDate='0000-00-00 00:00:00'"
    )

def _pending_transition():
    return _count(
        """SELECT COUNT(*) FROM SEED
           WHERE seedTransitionStamp='0000-00-00 00:00:00'
           AND seedId IN (SELECT DISTINCT seedId FROM TASK WHERE sceneSubtitleDate!='0000-00-00 00:00:00')
           AND seedId NOT IN (SELECT DISTINCT seedId FROM TASK WHERE sceneSubtitleDate='0000-00-00 00:00:00')"""
    )

def _pending_mix():
    return _count(
        "SELECT COUNT(*) FROM SEED "
        "WHERE seedTransitionStamp!='0000-00-00 00:00:00' AND seedMixStamp='0000-00-00 00:00:00'"
    )

def _pending_final():
    return _count(
        "SELECT COUNT(*) FROM SEED "
        "WHERE seedMixStamp!='0000-00-00 00:00:00' AND seedRenderStamp='0000-00-00 00:00:00'"
    )

def _pending_upload():
    return _count(
        "SELECT COUNT(*) FROM SEED "
        "WHERE seedRenderStamp!='0000-00-00 00:00:00' AND seedUploadStamp='0000-00-00 00:00:00'"
    )

def _pending_clean():
    return _count("SELECT COUNT(*) FROM SEED WHERE seedUploadStamp!='0000-00-00 00:00:00'")


# ── Lockfile ──────────────────────────────────────────────────────────────────
def _acquire_lock() -> bool:
    if os.path.exists(LOCK_FILE):
        try:
            pid = int(open(LOCK_FILE).read().strip())
            os.kill(pid, 0)
            log.warning(f"Pipeline already running (PID {pid})")
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True


def _release_lock():
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass


# ── Output helpers ────────────────────────────────────────────────────────────
def _print_output_files():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT seedId, seedTitle FROM SEED "
        "WHERE seedUploadStamp='0000-00-00 00:00:00' AND seedRenderStamp!='0000-00-00 00:00:00'"
    ).fetchall()
    conn.close()
    if not rows:
        return
    log.info("[output] Videos ready for manual upload:")
    for seed_id, title in rows:
        path = os.path.join(BASE_DIR, "final", f"{seed_id}.mp4")
        if os.path.exists(path):
            log.info(f"  [{seed_id}] {title}")
            log.info(f"       → {path}")


# ── Main orchestrator ─────────────────────────────────────────────────────────
def run_pipeline(skip_upload: bool = False):
    """State-aware pipeline: only loads and runs modules with pending work.

    Cron can fire every minute — if nothing is pending the process exits
    in milliseconds without loading any AI model.
    """
    if not _acquire_lock():
        sys.exit(0)

    try:
        _migrate_db()

        steps = [
            (_pending_feed,       "feed",       run_feed,       True),
            (_pending_image,      "image",      run_image,      True),
            (_pending_voice,      "voice",      run_voice,      True),
            (_pending_clip,       "clip",       run_clip,       True),
            (_pending_subtitle,   "subtitle",   run_subtitle,   True),
            (_pending_transition, "transition", run_transition, True),
            (_pending_mix,        "mix",        run_mix,        True),
            (_pending_final,      "final",      run_final,      True),
            (_pending_upload,     "upload",     run_upload,     not skip_upload),
            (_pending_clean,      "clean",      run_clean,      True),
        ]

        work_done = False
        for pending_fn, name, run_fn, enabled in steps:
            if not enabled:
                continue
            n = pending_fn()
            if n == 0:
                log.debug(f"[pipeline] {name}: nothing pending")
                continue
            log.info(f"[pipeline] {name}: {n} pending — running")
            work_done = True
            try:
                run_fn()
            except Exception as e:
                log.error(f"[pipeline] {name} failed: {e}", exc_info=True)

        if work_done and skip_upload:
            _print_output_files()
        elif not work_done:
            log.debug("[pipeline] Nothing to do.")

    finally:
        _release_lock()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI YouTube Video Generator — state-aware pipeline",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--module", "-m",
        choices=list(MODULES.keys()),
        help="Run only one module:\n" + "\n".join(f"  {k}" for k in MODULES),
    )
    parser.add_argument(
        "--output", "-o",
        choices=["api", "file"],
        default="api",
        help=(
            "api  = full pipeline including YouTube upload (default)\n"
            "file = stop after final render, save .mp4 for manual upload"
        ),
    )
    args = parser.parse_args()

    if args.module:
        MODULES[args.module]()
    else:
        run_pipeline(skip_upload=(args.output == "file"))
