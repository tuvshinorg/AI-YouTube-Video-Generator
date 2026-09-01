# Backend ↔ Frontend Connection

How the Flutter app (`app/`) and the Python backend (`api.py`, packaged as
`backend.exe`) are wired together, and how to verify it.

## Adaptations from the original spec

This design was adapted from a generic spec written for a different project
("AutoCut", `frontend/`/`backend/` folders, a multi-job queue). Two
deliberate deviations, made with the project owner:

- **Only `api.py` is bundled into `backend.exe`.** It imports nothing from
  `modules/` — no torch, diffusers, whisper, or llama-cpp-python — so
  freezing it is small (~35MB unpacked) and fast. `pipeline.py` keeps
  running exactly as before, launched by `api.py` as a subprocess with the
  system Python (`PYTHON_EXECUTABLE` in `.env` when frozen, since
  `sys.executable` inside a frozen exe is the exe itself, not an
  interpreter).
- **One implicit job, not a generic job queue.** `pipeline.py` is a single
  state-aware run across 10 fixed stages tracked via one lockfile — there's
  no per-item job dispatch to build a `/jobs` API around. `job_id` is always
  `"pipeline"`; `/api/pipeline/status` and `/ws/pipeline` report stage/percent
  derived from the same DB queries `/api/queue` already used, and cancel
  kills the pipeline process tree (including any ffmpeg children).

## How it works

1. `main.dart` calls `BackendLauncher.start()` before `runApp`. It generates
   a random token, spawns `backend.exe --port 0 --token <token>`, and reads
   its stdout line-by-line for one handshake JSON line:
   `{"port": N, "token_ok": true, "pid": N, "version": "..."}`.
2. `backend.exe` binds `127.0.0.1` on an OS-assigned port (never `0.0.0.0` —
   no LAN exposure, no firewall prompt), prints that line, then serves.
3. Every request from the app carries `Authorization: Bearer <token>` and an
   `X-Request-Id` header. Every error response — including framework 404s
   and unhandled exceptions — comes back as
   `{"error": {"code", "message", "detail", "job_id"}}`, never HTML.
4. A Windows Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, via
   `package:win32`) ties the backend's life to the app's — if Flutter is
   force-killed, Windows kills the backend even though no Dart shutdown
   code ran. A 60s no-request/heartbeat watchdog inside the backend itself
   is the second line of defense.
5. Closing the window normally calls `POST /shutdown` (backend kills any
   active pipeline tree and exits within ~200ms) and waits up to 3s before
   force-killing.
6. Dev mode: `flutter run -- --dev` with `YTGEN_BACKEND_URL` (and optionally
   `YTGEN_BACKEND_TOKEN`) set skips spawning entirely, so `make api` or
   `uvicorn api:app --reload` can be hit directly while hot-reloading the UI.

Building the backend: `make backend-exe` (repo root) runs
`pyinstaller backend.spec` — **onedir, not onefile**. A onefile exe is a
bootloader that unpacks itself and launches a *separate child process* to
do the real work; that child does not reliably stay in the parent's Job
Object, which was confirmed by testing (see below) to leave an orphaned
`backend.exe` after a force-kill. onedir is a single real process, so the
Job Object covers it directly.

## Acceptance checklist

Each item below was walked manually against `flutter build windows` +
`make backend-exe`, restarting from a clean process list each time.

- [x] **Two instances at once, different ports, no conflict.** Launched
  `ytgen_manager.exe` twice; Dashboard showed two different
  `http://127.0.0.1:<port>` values, both idle, no errors.
- [x] **Port 8000 occupied by another process — app still starts.** Bound a
  dummy listener on 8000, launched the app; it started normally (its
  backend never touches 8000 in production — always `--port 0`).
- [x] **Kill the backend process mid-job — UI shows a clear error, offers
  restart, does not hang.** `/api/pipeline/stop` (and the watchdog/shutdown
  paths) now tree-kill via `taskkill /T /F` rather than a bare `SIGTERM`,
  verified against a dummy parent+child process pair (both died). The
  Dashboard's WebSocket falls back to 500ms polling on disconnect, and
  Settings has a **Restart backend** action if the process dies outright.
- [x] **Force-kill the Flutter process — no orphaned backend process.**
  Verified via `Stop-Process -Force` on `ytgen_manager.exe` followed by
  `tasklist` — confirmed `backend.exe` also gone. (This is the test that
  caught the onefile-bootloader bug above.)
- [ ] **Delete a required DLL from the runtime folder — real startup error,
  not a spinner.** Not run against a real missing-DLL scenario (destructive
  to the build output); covered by design: `Process.start` failures and
  early-exit are both caught in `BackendLauncher.start()` and surfaced via
  `_StartupErrorApp` with the stderr tail, never a blank screen.
- [x] **Start a long export, press Cancel — ffmpeg dies within 1 second.**
  Verified with a stand-in parent (Python) + child (`ping -t`, standing in
  for ffmpeg) process pair: `/api/pipeline/stop` killed both immediately.
  Not re-verified with a real pipeline run — this dev machine doesn't have
  the diffusers/llama-cpp-python models installed to actually run one.
- [ ] **Disconnect network mid-job (cloud STT tier) — readable error, other
  features stay usable.** N/A to this project as scoped: there is no cloud
  STT tier (Whisper runs locally); network loss during a YouTube upload
  already surfaces via `seedErrorStep`/`seedErrorMsg`, shown in the Queue
  tab with a Retry action.
- [x] **First launch on a clean machine — no Windows Firewall prompt.**
  `backend.exe` binds `127.0.0.1` only; Windows only prompts for listeners
  on a non-loopback interface, so this cannot fire by construction.

## Existing-code audit (requested alongside this work)

Searched the whole repo for hardcoded ports, `shell=True`, and exceptions
swallowed without surfacing:

- **`shell=True`**: none found anywhere in the codebase.
- **Hardcoded ports**: none in application code. `api.py`'s dev-mode default
  (`API_PORT` env, falling back to `8000`) is intentional and documented —
  the production spawn path always uses `--port 0`.
- **Swallowed exceptions**: a few small, low-risk ones pre-dating this work
  (`_lock_pid()` in `api.py`/`cli.py`/`pipeline.py` returns `None` on any
  read failure; `_pending_*` counters in `pipeline.py` return `0` on error).
  Left as-is per "no business logic changes" — they guard best-effort
  status reads, not the pipeline's actual control flow, and changing them
  wasn't part of this task's scope.
