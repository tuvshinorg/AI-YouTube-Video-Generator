#!/usr/bin/env python3
"""
AI YouTube Video Generator — HTTP API
======================================
Exposes the same operations as cli.py (add text, queue status,
run/stop pipeline, list finished videos) as a REST API for the Flutter
app in app/.

Two ways to run it:

  python api.py --port 0 --token <uuid>
      Production shape: the Flutter app spawns exactly this. Binds
      127.0.0.1 on an OS-assigned port, prints one handshake JSON line
      to stdout once the socket is bound, then serves. Every request
      requires "Authorization: Bearer <token>". Idle for 60s with no
      request/heartbeat -> exits on its own.

  python api.py                    (or: make api)
      Dev shape: no token -> auth and the idle watchdog are both off.
      Binds 127.0.0.1:8000 (or $API_PORT) so `flutter run -- --dev` with
      YTGEN_BACKEND_URL set (see app/lib/backend_launcher.dart) can hit a
      manually-started backend, including under `uvicorn --reload`.
"""

import argparse
import asyncio
import json
import logging
import logging.handlers
import os
import queue
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

__version__ = "1.0.0"

IS_FROZEN = bool(getattr(sys, "frozen", False))

if IS_FROZEN:
    # Onefile exe: __file__ points into a throwaway temp extraction dir, and
    # backend.exe may not sit inside the actual project folder at all — so
    # BASE_DIR must come from a .env placed next to backend.exe by
    # `make backend-exe` (see Makefile), not be auto-detected.
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), ".env"))
    except ImportError:
        pass
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_DIR  = os.getenv("BASE_DIR") or _SCRIPT_DIR
DB_PATH   = os.path.join(BASE_DIR, "main.db")
LOCK_FILE = os.path.join(BASE_DIR, "pipeline.lock")
FINAL_DIR = os.path.join(BASE_DIR, "final")

# Inside a PyInstaller-frozen backend.exe, sys.executable IS the exe itself,
# not a real Python interpreter — running pipeline.py through it would fail.
# PYTHON_EXECUTABLE (.env) must point at a real interpreter with this
# project's dependencies installed when frozen.
PYTHON = os.getenv("PYTHON_EXECUTABLE") if IS_FROZEN else sys.executable

# "llama" (default) or "codex" — see modules/config.py and
# modules/codex_provider.py for where this actually changes pipeline
# behavior. Mirrored here (read straight from env, not imported from
# modules.config) so api.py stays free of any modules/* import — importing
# modules.config would re-run its own logging.basicConfig() and clash with
# this file's independent logging setup.
AI_PROVIDER = os.getenv("AI_PROVIDER", "llama").lower()
CODEX_BIN = shutil.which("codex") or "codex"

_STAGE_ORDER = [
    "feed", "image", "voice", "clip", "subtitle",
    "transition", "mix", "final", "upload", "clean",
]

# Mutable process-wide state. Set once in __main__ / at import for dev runs.
_state = {"token": None, "last_seen": time.time()}


# ── Logging: rotating daily file + console, request id on every line ─────────

REQUEST_ID: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = REQUEST_ID.get()
        return True


LOG_DIR = os.path.join(os.getenv("LOCALAPPDATA", BASE_DIR), "ytgen_manager", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Windows' console default encoding is cp1252, not UTF-8 — an en-dash,
# curly quote, or box-drawing character in a log message raises
# UnicodeEncodeError there and drops the line (see pipeline.py for the same
# fix; this file's _file_handler below already passes encoding="utf-8").
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

_file_handler = logging.handlers.TimedRotatingFileHandler(
    os.path.join(LOG_DIR, "backend.log"), when="midnight", backupCount=7, encoding="utf-8"
)
_file_handler.suffix = "%Y%m%d"
_stream_handler = logging.StreamHandler()

_req_filter = _RequestIdFilter()
_file_handler.addFilter(_req_filter)
_stream_handler.addFilter(_req_filter)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s [%(request_id)s] - %(message)s",
    handlers=[_stream_handler, _file_handler],
)
log = logging.getLogger("api")


# ── Watchdog: exit if the frontend goes silent for 60s ────────────────────────

async def _watchdog_loop():
    while True:
        await asyncio.sleep(5)
        idle_for = time.time() - _state["last_seen"]
        if idle_for > 60:
            log.warning(f"[watchdog] No request/heartbeat for {idle_for:.0f}s — shutting down")
            _kill_active_pipeline()
            os._exit(0)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    task = asyncio.create_task(_watchdog_loop()) if _state["token"] else None
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(title="AI YouTube Video Generator API", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _request_context(request: Request, call_next):
    req_id = request.headers.get("x-request-id") or secrets.token_hex(8)
    ctx_token = REQUEST_ID.set(req_id)
    _state["last_seen"] = time.time()

    if _state["token"]:
        auth = request.headers.get("authorization", "")
        # /api/videos/*/file is opened by the OS's default video player via
        # url_launcher, which can't attach an Authorization header — accept
        # the token as a query param for that one route instead.
        query_ok = request.url.path.startswith("/api/videos/") and request.query_params.get("token") == _state["token"]
        if auth != f"Bearer {_state['token']}" and not query_ok:
            REQUEST_ID.reset(ctx_token)
            return JSONResponse(
                status_code=401,
                headers={"X-Request-Id": req_id},
                content={"error": {"code": "UNAUTHORIZED", "message": "Missing or invalid token", "detail": None, "job_id": None}},
            )

    try:
        response = await call_next(request)
    finally:
        REQUEST_ID.reset(ctx_token)
    response.headers["X-Request-Id"] = req_id
    return response


# ── Uniform error envelope — no route can ever return HTML or bare text ──────

_CODE_BY_STATUS = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 500: "SERVER_ERROR"}


def _error_content(code: str, message: str, detail=None, job_id=None):
    return {"error": {"code": code, "message": message, "detail": detail, "job_id": job_id}}


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = _CODE_BY_STATUS.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(status_code=exc.status_code, content=_error_content(code, str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=_error_content("VALIDATION_ERROR", "Invalid request", detail=exc.errors()))


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled exception", exc_info=True)
    return JSONResponse(status_code=500, content=_error_content("INTERNAL_ERROR", "Internal server error", detail=str(exc)))


# ── DB helpers (same semantics as cli.py) ─────────────────────────────────────

def _db() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        raise HTTPException(500, f"Database not found: {DB_PATH}. Run setup.sh first.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _insert_queue_entry(group: str, text: str, stamp: Optional[str] = None) -> int:
    stamp = stamp or datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    conn = _db()
    cur = conn.execute(
        "INSERT INTO QUEUE (queueGroup, queueText, queueStamp) VALUES (?,?,?)",
        (group, text, stamp),
    )
    queue_id = cur.lastrowid
    conn.commit()
    conn.close()
    return queue_id


def _pid_alive(pid: int) -> bool:
    """Cross-platform "is this PID still running" check.

    os.kill(pid, 0) is a POSIX idiom — on Windows, os.kill() only accepts
    CTRL_C_EVENT/CTRL_BREAK_EVENT/SIGTERM, so passing 0 always raises
    OSError([WinError 87]) regardless of whether the process exists.
    """
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _pipeline_running() -> bool:
    if not os.path.exists(LOCK_FILE):
        return False
    try:
        with open(LOCK_FILE) as f:
            pid = int(f.read().strip())
        return _pid_alive(pid)
    except ValueError:
        return False


def _lock_pid() -> Optional[int]:
    try:
        with open(LOCK_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _kill_tree(pid: int):
    """Kill pid and every child it spawned (e.g. ffmpeg) — not just pid itself."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _kill_active_pipeline():
    pid = _lock_pid()
    if pid:
        _kill_tree(pid)
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass


def _stage_counts() -> dict:
    """Pending-work counts per stage — mirrors pipeline.py's _pending_* checks."""
    conn = _db()
    counts = {
        "feed": conn.execute(
            "SELECT COUNT(*) FROM QUEUE WHERE queueId NOT IN (SELECT DISTINCT queueId FROM SEED WHERE queueId IS NOT NULL)"
        ).fetchone()[0],
        "image": conn.execute(
            "SELECT COUNT(*) FROM TASK WHERE sceneImageDate='0000-00-00 00:00:00'"
        ).fetchone()[0],
        "voice": conn.execute(
            "SELECT COUNT(*) FROM TASK WHERE sceneImageDate!='0000-00-00 00:00:00' AND sceneAudioDate='0000-00-00 00:00:00'"
        ).fetchone()[0],
        "clip": conn.execute(
            "SELECT COUNT(*) FROM TASK WHERE sceneAudioDate!='0000-00-00 00:00:00' AND sceneClipDate='0000-00-00 00:00:00'"
        ).fetchone()[0],
        "subtitle": conn.execute(
            "SELECT COUNT(*) FROM TASK WHERE sceneClipDate!='0000-00-00 00:00:00' AND sceneSubtitleDate='0000-00-00 00:00:00'"
        ).fetchone()[0],
        "transition": conn.execute(
            """SELECT COUNT(*) FROM SEED
               WHERE seedTransitionStamp='0000-00-00 00:00:00'
               AND seedId IN (SELECT DISTINCT seedId FROM TASK WHERE sceneSubtitleDate!='0000-00-00 00:00:00')
               AND seedId NOT IN (SELECT DISTINCT seedId FROM TASK WHERE sceneSubtitleDate='0000-00-00 00:00:00')"""
        ).fetchone()[0],
        "mix": conn.execute(
            "SELECT COUNT(*) FROM SEED WHERE seedTransitionStamp!='0000-00-00 00:00:00' AND seedMixStamp='0000-00-00 00:00:00'"
        ).fetchone()[0],
        "final": conn.execute(
            "SELECT COUNT(*) FROM SEED WHERE seedMixStamp!='0000-00-00 00:00:00' AND seedRenderStamp='0000-00-00 00:00:00'"
        ).fetchone()[0],
        "upload": conn.execute(
            "SELECT COUNT(*) FROM SEED WHERE seedRenderStamp!='0000-00-00 00:00:00' AND seedUploadStamp='0000-00-00 00:00:00'"
        ).fetchone()[0],
        "clean": conn.execute(
            "SELECT COUNT(*) FROM SEED WHERE seedUploadStamp!='0000-00-00 00:00:00'"
        ).fetchone()[0],
    }
    conn.close()
    return counts


def _tail_lines(path: str, n: int = 12, max_bytes: int = 8192) -> list:
    """Last n lines of a log file, without loading the whole thing into memory."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            data = f.read()
        return data.decode("utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def _pipeline_status_payload() -> dict:
    running = _pipeline_running()
    counts = _stage_counts()
    started_at = None
    if running and os.path.exists(LOCK_FILE):
        try:
            started_at = datetime.fromtimestamp(os.path.getmtime(LOCK_FILE)).isoformat(sep=" ", timespec="seconds")
        except OSError:
            pass
    if not running:
        stage = "idle"
        percent = 100 if all(v == 0 for v in counts.values()) else 0
        message = "Pipeline idle"
    else:
        current = next((s for s in _STAGE_ORDER if counts[s] > 0), None)
        if current is None:
            stage, percent, message = "finishing", 95, "Wrapping up"
        else:
            idx = _STAGE_ORDER.index(current)
            stage = current
            percent = round(idx / len(_STAGE_ORDER) * 100)
            message = f"{current}: {counts[current]} pending"
    return {
        "job_id": "pipeline", "running": running, "pid": _lock_pid(),
        "stage": stage, "percent": percent, "message": message,
        "started_at": started_at,
        "log_tail": _tail_lines(os.path.join(BASE_DIR, "logs", "pipeline.log")) if running else [],
    }


# ── Schemas ────────────────────────────────────────────────────────────────────

class AddTextRequest(BaseModel):
    text: str
    title: Optional[str] = None
    group: str = "manual"


class ImportEntry(BaseModel):
    title: Optional[str] = None
    text: str


class ImportRequest(BaseModel):
    group: Optional[str] = None
    entries: list[ImportEntry]


class RunRequest(BaseModel):
    output: str = "api"   # "api" | "file"


# ── Lifecycle: heartbeat / shutdown ──────────────────────────────────────────

@app.post("/heartbeat")
def heartbeat():
    _state["last_seen"] = time.time()
    return {"ok": True}


def _do_shutdown():
    time.sleep(0.1)
    _kill_active_pipeline()
    os._exit(0)


@app.post("/shutdown")
def shutdown(background_tasks: BackgroundTasks):
    background_tasks.add_task(_do_shutdown)
    return {"ok": True}


# ── Status / queue ─────────────────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    return {
        "running": _pipeline_running(),
        "pid": _lock_pid(),
        "base_dir": BASE_DIR,
        "db_path": DB_PATH,
        "version": __version__,
        "ai_provider": AI_PROVIDER,
    }


@app.get("/api/pipeline/status")
def pipeline_status():
    return _pipeline_status_payload()


@app.websocket("/ws/pipeline")
async def ws_pipeline(websocket: WebSocket):
    if _state["token"]:
        auth = websocket.headers.get("authorization", "")
        if auth != f"Bearer {_state['token']}":
            await websocket.close(code=4401)
            return
    await websocket.accept()
    try:
        while True:
            _state["last_seen"] = time.time()
            await websocket.send_json(_pipeline_status_payload())
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass


@app.get("/api/queue")
def get_queue():
    conn = _db()
    queue_pending = conn.execute(
        """SELECT queueId, queueGroup, SUBSTR(queueText,1,120) as snippet, queueStamp
           FROM QUEUE
           WHERE queueId NOT IN (SELECT queueId FROM SEED)
           ORDER BY queueId DESC
           LIMIT 50"""
    ).fetchall()

    seeds = conn.execute(
        """SELECT seedId, seedTitle, seedErrorStep, seedErrorMsg,
             CASE
               WHEN seedUploadStamp     != '0000-00-00 00:00:00' THEN 'uploaded'
               WHEN seedRenderStamp     != '0000-00-00 00:00:00' THEN 'rendered'
               WHEN seedMixStamp        != '0000-00-00 00:00:00' THEN 'mixed'
               WHEN seedTransitionStamp != '0000-00-00 00:00:00' THEN 'transitioned'
               ELSE 'processing'
             END as stage,
             seedCreatedDate
           FROM SEED
           ORDER BY seedId DESC
           LIMIT 50"""
    ).fetchall()
    conn.close()

    return {
        "running": _pipeline_running(),
        "pid": _lock_pid(),
        "queue_pending": [dict(r) for r in queue_pending],
        "seeds": [
            {**dict(s), "stage": "error" if s["seedErrorStep"] else s["stage"]}
            for s in seeds
        ],
    }


@app.get("/api/queue/{queue_id}")
def get_queue_entry(queue_id: int):
    conn = _db()
    row = conn.execute(
        "SELECT queueId, queueGroup, queueText, queueStamp FROM QUEUE WHERE queueId=?", (queue_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"Queue entry {queue_id} not found")
    return dict(row)


@app.delete("/api/queue/{queue_id}")
def delete_queue_entry(queue_id: int):
    conn = _db()
    row = conn.execute("SELECT queueId FROM QUEUE WHERE queueId=?", (queue_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, f"Queue entry {queue_id} not found")
    if conn.execute("SELECT seedId FROM SEED WHERE queueId=?", (queue_id,)).fetchone():
        conn.close()
        raise HTTPException(400, "This entry already started a project — delete the project instead")
    conn.execute("DELETE FROM QUEUE WHERE queueId=?", (queue_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/text")
def add_text(req: AddTextRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "text is required")
    full = f"{req.title}\n\n{text}".strip() if req.title else text
    queue_id = _insert_queue_entry(req.group, full)
    return {"ok": True, "queue_id": queue_id, "group": req.group}


@app.post("/api/import")
def import_entries(req: ImportRequest):
    group = req.group or "import"
    if not req.entries:
        raise HTTPException(400, "No entries provided")

    saved = 0
    for entry in req.entries:
        text = entry.text.strip()
        if not text:
            continue
        full = f"{entry.title}\n\n{text}".strip() if entry.title else text
        _insert_queue_entry(group, full)
        saved += 1

    return {"ok": True, "saved": saved, "group": group}


@app.post("/api/seeds/{seed_id}/retry")
def retry_seed(seed_id: int):
    conn = _db()
    row = conn.execute("SELECT seedTitle, seedErrorStep FROM SEED WHERE seedId=?", (seed_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, f"Seed {seed_id} not found")
    if not row["seedErrorStep"]:
        conn.close()
        return {"ok": False, "note": "Seed has no recorded error"}
    if row["seedErrorStep"] == "feed":
        # A feed-generation failure never got scenes/tasks — the seed row only
        # exists to record the error and keep feed_get_unprocessed_entry() from
        # retrying it forever. Delete it outright so that queueId is picked up
        # as pending again on the next pipeline run.
        conn.execute("DELETE FROM SEED WHERE seedId=?", (seed_id,))
    else:
        conn.execute("UPDATE SEED SET seedErrorStep=NULL, seedErrorMsg=NULL WHERE seedId=?", (seed_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "seed_id": seed_id}


@app.get("/api/seeds/{seed_id}")
def get_seed_detail(seed_id: int):
    conn = _db()
    seed = conn.execute(
        """SELECT seedId, queueId, seedPrompt, seedTitle, seedDescription, seedSong,
             seedCreatedDate, seedErrorStep, seedErrorMsg,
             CASE
               WHEN seedUploadStamp     != '0000-00-00 00:00:00' THEN 'uploaded'
               WHEN seedRenderStamp     != '0000-00-00 00:00:00' THEN 'rendered'
               WHEN seedMixStamp        != '0000-00-00 00:00:00' THEN 'mixed'
               WHEN seedTransitionStamp != '0000-00-00 00:00:00' THEN 'transitioned'
               ELSE 'processing'
             END as stage
           FROM SEED WHERE seedId=?""",
        (seed_id,),
    ).fetchone()
    if not seed:
        conn.close()
        raise HTTPException(404, f"Seed {seed_id} not found")
    scenes = conn.execute(
        "SELECT sceneNumber, sceneImage, sceneText FROM SCENE WHERE seedId=? ORDER BY sceneNumber",
        (seed_id,),
    ).fetchall()
    conn.close()
    result = dict(seed)
    result["stage"] = "error" if result["seedErrorStep"] else result["stage"]
    result["scenes"] = [dict(s) for s in scenes]
    return result


@app.delete("/api/seeds/{seed_id}")
def delete_seed(seed_id: int):
    """Deletes the project entirely: scenes, tasks, the seed row, the queue
    entry it came from (so it isn't silently re-queued), and its rendered
    .mp4 if one exists."""
    conn = _db()
    row = conn.execute("SELECT queueId FROM SEED WHERE seedId=?", (seed_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, f"Seed {seed_id} not found")
    queue_id = row["queueId"]
    conn.execute("DELETE FROM SCENE WHERE seedId=?", (seed_id,))
    conn.execute("DELETE FROM TASK WHERE seedId=?", (seed_id,))
    conn.execute("DELETE FROM SEED WHERE seedId=?", (seed_id,))
    conn.execute("DELETE FROM QUEUE WHERE queueId=?", (queue_id,))
    conn.commit()
    conn.close()

    video_path = os.path.join(FINAL_DIR, f"{seed_id}.mp4")
    if os.path.exists(video_path):
        try:
            os.remove(video_path)
        except OSError:
            pass
    return {"ok": True}


# ── Pipeline control ────────────────────────────────────────────────────────────

@app.post("/api/pipeline/run")
def run_pipeline(req: RunRequest):
    if req.output not in ("api", "file"):
        raise HTTPException(400, "output must be 'api' or 'file'")
    if _pipeline_running():
        return {"ok": False, "note": f"Pipeline already running (PID {_lock_pid()})"}

    if IS_FROZEN and not (PYTHON and os.path.exists(PYTHON)):
        raise HTTPException(
            500,
            "PYTHON_EXECUTABLE is not configured or invalid. Set it in .env to the path "
            "of a real python.exe with this project's dependencies installed.",
        )

    cmd = [PYTHON, os.path.join(BASE_DIR, "pipeline.py"), "--output", req.output]
    proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"ok": True, "pid": proc.pid, "output": req.output}


@app.post("/api/pipeline/stop")
def stop_pipeline():
    pid = _lock_pid()
    if not pid or not _pipeline_running():
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
        return {"ok": True, "note": "Pipeline was not running; stale lock removed"}

    _kill_tree(pid)
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
    return {"ok": True, "pid": pid}


# ── Videos ───────────────────────────────────────────────────────────────────

@app.get("/api/videos")
def list_videos():
    if not os.path.isdir(FINAL_DIR):
        return []

    conn = _db()
    titles = {r["seedId"]: r["seedTitle"] for r in conn.execute("SELECT seedId, seedTitle FROM SEED")}
    uploaded = {
        r["seedId"]
        for r in conn.execute(
            "SELECT seedId FROM SEED WHERE seedUploadStamp != '0000-00-00 00:00:00'"
        )
    }
    conn.close()

    videos = []
    for fname in os.listdir(FINAL_DIR):
        if not fname.endswith(".mp4"):
            continue
        seed_id_str = fname[:-4]
        path = os.path.join(FINAL_DIR, fname)
        stat = os.stat(path)
        try:
            seed_id = int(seed_id_str)
        except ValueError:
            seed_id = None
        videos.append({
            "seed_id": seed_id,
            "filename": fname,
            "title": titles.get(seed_id, fname),
            "uploaded": seed_id in uploaded,
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(sep=" ", timespec="seconds"),
        })
    videos.sort(key=lambda v: v["modified"], reverse=True)
    return videos


@app.get("/api/videos/{seed_id}/file")
def get_video_file(seed_id: int):
    path = os.path.join(FINAL_DIR, f"{seed_id}.mp4")
    if not os.path.exists(path):
        raise HTTPException(404, "Video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"{seed_id}.mp4")


# ── Codex login (AI_PROVIDER=codex) ──────────────────────────────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _codex_login_status() -> dict:
    try:
        result = subprocess.run(
            [CODEX_BIN, "login", "status"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15,
        )
        detail = _ANSI_RE.sub("", result.stdout or result.stderr).strip()
        logged_in = result.returncode == 0 and "logged in" in detail.lower()
        return {"logged_in": logged_in, "detail": detail}
    except FileNotFoundError:
        return {"logged_in": False, "detail": "codex CLI not found on PATH"}
    except Exception as e:
        return {"logged_in": False, "detail": str(e)}


@app.get("/api/codex/status")
def codex_status():
    return {"ai_provider": AI_PROVIDER, **_codex_login_status()}


def _pipe_to_queue(pipe, q: "queue.Queue"):
    try:
        for line in iter(pipe.readline, ""):
            q.put(line)
    finally:
        q.put(None)   # EOF sentinel


@app.post("/api/codex/login")
def codex_login():
    """Starts `codex login --device-auth` and returns the verification URL +
    one-time code as soon as they're printed, for the app to display.

    IMPORTANT: starting a new login flow immediately invalidates whatever
    session was previously logged in, even if this new one is never
    completed. Only call this when the user has explicitly asked to log in.

    The subprocess is left running in the background on return — it's what
    actually receives and writes the credentials once the user approves in
    their own browser, so it must not be killed here. It exits on its own
    once the code is approved or its ~15 minute expiry passes.
    """
    try:
        proc = subprocess.Popen(
            [CODEX_BIN, "login", "--device-auth"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except FileNotFoundError:
        raise HTTPException(500, "codex CLI not found on PATH")

    q: "queue.Queue" = queue.Queue()
    threading.Thread(target=_pipe_to_queue, args=(proc.stdout, q), daemon=True).start()

    url = code = None
    deadline = time.time() + 10
    while time.time() < deadline and (url is None or code is None):
        try:
            line = q.get(timeout=max(0.0, deadline - time.time()))
        except queue.Empty:
            break
        if line is None:
            break
        clean = _ANSI_RE.sub("", line)
        if url is None:
            m = re.search(r"https?://\S+", clean)
            if m:
                url = m.group(0)
        if code is None:
            m = re.search(r"\b[A-Z0-9]{4,8}-[A-Z0-9]{4,8}\b", clean)
            if m:
                code = m.group(0)

    if not url or not code:
        _kill_tree(proc.pid)
        raise HTTPException(500, "Could not read a login URL/code from codex login — see backend logs")

    return {"url": url, "code": code}


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI YouTube Video Generator API")
    parser.add_argument("--port", type=int, default=int(os.getenv("API_PORT", "8000")),
                         help="0 = let the OS pick a free port (used when spawned by the Flutter app)")
    parser.add_argument("--token", default=None, help="Bearer token required on every request; omit for local dev")
    args = parser.parse_args()

    _state["token"] = args.token

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))   # never 0.0.0.0 — no LAN exposure, no firewall prompt
    sock.listen(100)
    actual_port = sock.getsockname()[1]

    handshake = {"port": actual_port, "token_ok": bool(args.token), "pid": os.getpid(), "version": __version__}
    print(json.dumps(handshake), flush=True)
    log.info(f"[api] Listening on http://127.0.0.1:{actual_port} (auth={'on' if args.token else 'off'})")

    import uvicorn
    config = uvicorn.Config(app, log_level="warning")
    server = uvicorn.Server(config)
    asyncio.run(server.serve(sockets=[sock]))


if __name__ == "__main__":
    main()
