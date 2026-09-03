# AI YouTube Video Generator

![GitHub stars](https://img.shields.io/github/stars/tuvshinorg/AI-YouTube-Video-Generator?style=social)
![GitHub forks](https://img.shields.io/github/forks/tuvshinorg/AI-YouTube-Video-Generator?style=social)
![GitHub last commit](https://img.shields.io/github/last-commit/tuvshinorg/AI-YouTube-Video-Generator)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6.svg)
![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Flutter](https://img.shields.io/badge/Flutter-Windows%20desktop-02569B.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

![Codex](https://img.shields.io/badge/OpenAI-Codex%20CLI-black.svg)
![llama.cpp](https://img.shields.io/badge/llama.cpp-local%20LLM-orange.svg)
![HuggingFace Flux](https://img.shields.io/badge/HuggingFace-Flux-yellow.svg)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Video%20Processing-red.svg)
![YouTube API](https://img.shields.io/badge/YouTube-API%20v3-red.svg)
![Whisper](https://img.shields.io/badge/OpenAI-Whisper-black.svg)

## Looking to Hire a Skilled AI/ML Developer?

**Contact: tuvshin.org@gmail.com**

[![Portfolio](https://img.shields.io/badge/💼-Available%20for%20Hire-brightgreen.svg?style=for-the-badge)](mailto:tuvshin.org@gmail.com)

---

## Download

**[⬇ Download the latest Windows release](https://github.com/tuvshinorg/AI-YouTube-Video-Generator/releases/latest)** — two options on the release page:

- **`AI-YouTube-Video-Generator-Setup-vX.Y.Z.exe`** (recommended) — a normal
  Windows installer. Run it, click through, get a Start Menu/Desktop
  shortcut. Installs per-user (no admin/UAC prompt) since the app writes
  its database and rendered videos directly next to itself.
- **`AI-YouTube-Video-Generator-Windows-vX.Y.Z.zip`** — the same app as a
  portable folder; extract anywhere and run `ytgen_manager.exe` directly,
  no installer.

Either way, this build is **fully self-contained** — `pipeline.exe` bundles
the entire pipeline (CPU-only torch, transformers, Whisper, fastText), so
no separate Python install is needed at all for the Codex-only path (see
[AI Providers](#ai-providers)). The only thing you still need is a Codex
login, which [First Run](#first-run) below walks you through from inside
the app.

Building either yourself: `flutter build windows` + `pyinstaller backend.spec`
+ `pyinstaller pipeline.spec` produce the pieces (see [Flutter Manager
App](#flutter-manager-app)); `iscc installer.iss` (needs [Inno
Setup](https://jrsoftware.org/isinfo.php)) turns the assembled release
folder into the installer.

---

## What It Does

Turn an article, an idea, or a topic into a ready-to-post vertical video —
narration, AI-generated images, subtitles, music, transitions — with one
button in a native Windows app, or fully unattended via cron/Task Scheduler.

```
Your text / idea
      ↓
  LLM  (llama.cpp locally, or Codex CLI)      → 6 scenes: narration + image prompt
      ↓
  Images  (HuggingFace Flux, OpenAI Images, or Codex's image_gen)
      ↓
  Edge TTS  (auto-picks a Mongolian voice if the scene is written in Mongolian)
      ↓
  FFmpeg  → clips + subtitles (Whisper, or a Mongolian-finetuned Whisper) + transitions + music mix
      ↓
  YouTube API → published  (or saved as .mp4 for manual upload)
```

Every stage above has a swappable provider — run it fully local (llama.cpp +
Flux, needs a GPU), fully through a ChatGPT/Codex login (no GPU, no local
models), or mix and match. See [AI Providers](#ai-providers) below.

---

## Use Cases

- **Faceless YouTube Shorts / TikTok channel** — paste a news article or
  write an idea, get a narrated, subtitled, vertical video with background
  music in a few minutes, auto-uploaded or saved for you to review first.
- **Content repurposing** — turn a blog post, press release, or long-form
  script into a short-form video without touching an editor.
- **Bilingual (English/Mongolian) content** — write in either language (or
  mix scenes across both in the same project) and narration, subtitles, and
  transcription are all picked automatically per scene — see
  [Mongolian Language Support](#mongolian-language-support).
- **No-GPU / low-power machine** — set `AI_PROVIDER=codex` and
  `IMAGE_PROVIDER=codex` and the entire pipeline (text, images) runs through
  your Codex/ChatGPT login instead of local models; only subtitles (Whisper)
  and video compositing (FFmpeg) run locally, and both are CPU-friendly.
- **Unattended batch production** — queue several ideas, let cron (Linux/WSL)
  or Windows Task Scheduler run the pipeline on a schedule, and check the
  "Finished" list in the app whenever you like.
- **Portfolio / automation reference** — a complete, working example of
  chaining an LLM, image generation, TTS, ASR, and video composition into
  one state-machine pipeline with a real desktop UI on top.

---

## First Run

The backend now configures as much of itself as it safely can, and tells
you clearly about the part it can't:

- **Directories, `.env`, and the database are created automatically** the
  first time the backend starts — no manual `setup.sh` or `create.py` step
  before the app is even usable.
- **Language-ID and Mongolian-Whisper models auto-download** (~1 MB and
  ~3.2 GB respectively) the first time a scene actually needs them — you'll
  see it happening in the app's Activity log, not a silent multi-minute stall.
- **Python dependencies are the one thing that genuinely can't be automated
  invisibly** — the app can't know which Python you want them installed
  into, or safely run a multi-minute install with no visible progress. If
  they're missing, the dashboard shows a banner with the exact command to
  copy, where to run it from, and a "Recheck" button:

  ```
  ⚠ Python dependencies aren't installed yet
  pip install -r requirements.txt          [copy]
  Run it from: C:\...\AI-YouTube-Video-Generator
  ```

- **Codex login** (only shown if `AI_PROVIDER=codex` or `IMAGE_PROVIDER=codex`):
  a banner offers to install Node.js + the Codex CLI for you (same commands
  you'd type yourself, just run for you, with the output shown live), then
  walks you through the device-login flow — open a link, paste a code
  that's already on your clipboard. No terminal required.

Once both banners are gone, "Make the video" works.

---

## Quick Start (from source)

```bash
git clone https://github.com/tuvshinorg/AI-YouTube-Video-Generator.git
cd AI-YouTube-Video-Generator
bash setup.sh
```

`setup.sh` does the parts that need to happen before Python even runs:
- Detects your repo path and writes it to `.env`
- Creates all runtime directories (`logs/`, `temp/*/`, `final/`, `song/*/`, `optic/`, `models/`)
- Detects CUDA and installs `llama-cpp-python` with GPU support if available
- Installs all pip dependencies
- Initializes the SQLite database
- Installs a cron job (Linux/WSL only — every hour by default)

Everything after that (further directory/DB repair, Codex install/login) is
handled by the app itself on first launch — see [First Run](#first-run).

**Fastest path (no GPU, no local models):** set these two lines in `.env`
and skip straight to running the app or `make run-file`:

```bash
AI_PROVIDER=codex
IMAGE_PROVIDER=codex
```

**Local/offline path:** fill in a GGUF model and a Flux repo instead:

```bash
LLAMA_MODEL_PATH=./models/Llama-3.2-3B-Instruct-Q6_K.gguf
FLUX_MODEL_ID=enhanceaiteam/Flux-Uncensored-V2
```

```bash
huggingface-cli download bartowski/Llama-3.2-3B-Instruct-GGUF \
    Llama-3.2-3B-Instruct-Q6_K.gguf --local-dir ./models
```

---

## Interactive CLI

```bash
make cli          # or: python cli.py
```

```
╔══════════════════════════════════════════╗
║  AI YouTube Video Generator — Manager   ║
╚══════════════════════════════════════════╝

  Pipeline: ○ idle   DB: /path/to/main.db

  1)  Add RSS feed
  2)  Check RSS feeds
  3)  Import from JSON
  4)  Enter text manually
  5)  Show queue
  6)  Run pipeline (api)       ← upload to YouTube
  7)  Run pipeline (file)      ← save .mp4 locally
  8)  Stop running pipeline
  q)  Quit
```

CLI subcommands also work for scripting:

```bash
python cli.py add-rss                  # validate & import an RSS feed
python cli.py check-rss                # show all RSS groups + entry counts
python cli.py add-json entries.json    # bulk import from JSON file
python cli.py add-text                 # paste text, no RSS needed
python cli.py queue                    # live queue status table
python cli.py run --output api         # run now, upload to YouTube
python cli.py run --output file        # run now, save .mp4 for manual upload
python cli.py stop                     # SIGTERM the running pipeline
```

### Manual text input

No RSS feed? Just type:

```
Enter text manually → type or paste → finish with a line containing ---
```

The pipeline treats it exactly like an RSS article and generates a full video.

### JSON import format

```json
{
  "group": "my-source",
  "entries": [
    { "title": "Optional title", "text": "Full article body here..." },
    { "title": "Another one",    "text": "More content..." }
  ]
}
```

---

## Flutter Manager App

A native Windows desktop app (`app/`) is the primary way to run this —
paste an idea, watch it render live, browse and delete finished/queued/
errored projects, and manage Codex login, all from one window. It talks to
a small FastAPI backend (`api.py`, packaged as `backend.exe`) that wraps
the same operations as `cli.py`.

**The app owns the backend's whole lifecycle** — it spawns `backend.exe`
itself on a random port with a random auth token, and shuts it down when
the window closes (or Windows does, if the app is force-killed). There's
nothing to start manually and nothing to type in — see
[`docs/CONNECTION.md`](docs/CONNECTION.md) for exactly how, plus a walked
acceptance checklist.

**1. Build the backend once (or after changing `api.py`):**

```bash
make backend-exe    # pyinstaller -> dist/backend/, copied into app/windows/backend/
```

`backend.exe` deliberately stays small (~35 MB unpacked) — it never imports
torch/transformers/whisper/llama-cpp itself, only `pipeline.py` does, run
as a normal Python subprocess. That's also why installing Python
dependencies (see [First Run](#first-run)) can't be skipped by using the
prebuilt exe alone.

**2. Run or build the app:**

```bash
cd app
flutter run -d windows          # dev
flutter build windows           # → app/build/windows/x64/runner/Release/
```

That's it — launching either one spawns the backend automatically.

**Dev mode** (hot-reload the UI against a manually-started backend, e.g.
`uvicorn api:app --reload`): set `YTGEN_BACKEND_URL` (and optionally
`YTGEN_BACKEND_TOKEN`) and pass `--dev`:

```bash
YTGEN_BACKEND_URL=http://127.0.0.1:8000 flutter run -d windows -- --dev
```

> Android support was scaffolded and works the same way, but the platform
> folder was removed for now. Re-add it anytime with
> `flutter create --platforms=android .` from inside `app/`.

---

## AI Providers

Every AI-driven stage picks its provider independently via `.env` — mix and
match based on what hardware/accounts you have.

| Stage | Env var | Options | Notes |
|---|---|---|---|
| Text (scenes, title, description) | `AI_PROVIDER` | `llama` (default) · `codex` | `llama` runs a local GGUF via llama.cpp — needs a GPU for reasonable speed. `codex` shells out to the Codex CLI — no GPU, but needs a Codex/ChatGPT login. |
| Images | `IMAGE_PROVIDER` | `flux` (default) · `openai` · `codex` | `flux` runs locally via HuggingFace diffusers — needs a GPU. `openai` calls the Images API (billed, needs `OPENAI_API_KEY`). `codex` uses Codex's built-in `image_gen` tool — same login as `AI_PROVIDER=codex`, no separate key or billing. |
| Subtitles | *(automatic)* | generic Whisper · Mongolian fine-tune | Always runs locally. Per-scene language detection (see below) picks the right model — no config needed. |
| Narration voice | *(automatic)* | `TTS_VOICE` · `TTS_VOICE_MN` | Same per-scene language detection picks the voice. |

**The zero-GPU path:** `AI_PROVIDER=codex` + `IMAGE_PROVIDER=codex` needs no
local models and no dedicated GPU at all — only Whisper (CPU-friendly) and
FFmpeg run locally. This is what [First Run](#first-run)'s Codex banner is for.

### About using Codex this way

- **Auth is whatever `codex login` is signed into.** If that's a ChatGPT
  Plus/Pro login rather than an API key, know that it's designed for
  interactive terminal sessions on one device, not unattended backend
  automation — using it this way may run against OpenAI's usage terms.
  That's your call to make for your own account, not something this
  project enforces either way.
- **Starting a new login ends the old one immediately**, even if the new
  one is never completed — there's no "cancel and keep the old session."
- **Codex has its own usage limits.** The pipeline paces successive image
  calls (`CODEX_IMAGE_DELAY`, default 180s) to stay under them — a project
  with several scenes can take a while to fully render; that pacing is
  intentional, not the app being stuck (the Activity log says so explicitly).

---

## Mongolian Language Support

Any scene text — regardless of what language the rest of the project is
in — is run through a real language-identification model
([fastText's `lid.176`](https://fasttext.cc/docs/en/language-identification.html),
176 languages, auto-downloads ~1MB on first use) before narration and
subtitles are generated for it:

- **Detected as Mongolian (`mn`)** → narration uses `TTS_VOICE_MN`
  (`mn-MN-YesuiNeural` by default), and subtitles are transcribed with
  [`Tsedee/whisper-large-v3-turbo-mn-2`](https://huggingface.co/Tsedee/whisper-large-v3-turbo-mn-2),
  a Whisper fine-tune substantially more accurate on Mongolian speech than
  the generic model. Auto-downloads (~3.2 GB) the first time a Mongolian
  scene is actually transcribed.
- **Anything else** → the normal `TTS_VOICE` and the generic multilingual
  Whisper model — including Russian, Ukrainian, Kazakh, and other
  Cyrillic-script languages, which are *not* Mongolian and are not routed
  to the Mongolian-specific models.

This is real classification, not a "contains Cyrillic characters" guess —
the two extra Mongolian Cyrillic letters (Өө, Үү) plus every other
Cyrillic-script language would have made a script-based check
indistinguishable from actual Mongolian.

---

## Output Modes

| Mode | Command | Result |
|------|---------|--------|
| **api** (default) | `make run` | Full pipeline → auto-upload to YouTube |
| **file** | `make run-file` | Full pipeline → `.mp4` saved in `final/` for manual upload |

The Flutter app's "Make the video" button always uses `file` mode — YouTube
upload needs OAuth credentials the app doesn't set up for you (see
[YouTube API Setup](#youtube-api-setup)); use `make run` or the CLI for the
auto-upload path.

---

## Make Targets

```
make setup        first-time install + cron
make cli          interactive manager
make api          REST API for the Flutter manager app
make backend-exe  build backend.exe for the Flutter app to spawn
make run          full pipeline → YouTube upload
make run-file     full pipeline → save .mp4 locally

make feed         module 01 only: text/RSS → scenes
make image        module 02 only: images
make voice        module 03 only: TTS
make clip         module 04 only: clips
make subtitle     module 05 only: subtitles (Whisper)
make transition   module 06 only: transitions
make mix          module 07 only: music mix
make final        module 08 only: final render
make upload       module 09 only: YouTube upload
make clean        module 10 only: delete temp files

make cron-show    print current crontab
make cron-remove  remove the pipeline cron entry
```

---

## Configuration (`.env`)

Copy `.env.example` to `.env` and edit (the app also does this
automatically on first launch if `.env` is missing — see [First
Run](#first-run)):

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_DIR` | auto-detected | Absolute path to the repo |
| `AI_PROVIDER` | `llama` | `llama` (local llama.cpp) or `codex` (Codex CLI, text only) |
| `CODEX_TIMEOUT` | `120` | Overall ceiling (seconds) for one text `codex exec` call |
| `LLAMA_MODEL_PATH` | `./models/Llama-3.2-3B-Instruct-Q6_K.gguf` | Path to your GGUF model |
| `LLAMA_N_CTX` | `4096` | LLM context window (tokens) |
| `LLAMA_N_GPU` | `-1` | GPU layers: `-1` = all on GPU, `0` = CPU only |
| `LLAMA_VERBOSE` | `false` | Show llama.cpp token output |
| `IMAGE_PROVIDER` | `flux` | `flux` (local), `openai` (Images API), or `codex` (Codex's image_gen tool) |
| `CODEX_IMAGE_TIMEOUT` | `240` | Overall ceiling (seconds) for one image `codex exec` call |
| `CODEX_IMAGE_DELAY` | `180` | Pause between successive Codex image calls, to stay under its usage limit |
| `CODEX_STARTUP_IDLE_TIMEOUT` | `180` | Kill a `codex exec` call early if it produces zero activity for this long (catches a genuine hang fast without cutting off a slow-but-working start) |
| `FLUX_MODEL_ID` | `enhanceaiteam/Flux-Uncensored-V2` | Any Flux-compatible HuggingFace repo |
| `FLUX_CPU_OFFLOAD` | `true` | Offload model to CPU between calls (saves VRAM) |
| `FLUX_WIDTH` / `FLUX_HEIGHT` | `540` / `960` | Output image size (portrait, for Shorts) |
| `FLUX_STEPS` | `20` | Diffusion steps |
| `FLUX_GUIDANCE` | `3.5` | Guidance scale |
| `OPENAI_API_KEY` | — | Used only when `IMAGE_PROVIDER=openai` |
| `OPENAI_IMAGE_MODEL` | `gpt-image-1` | OpenAI Images API model |
| `OPENAI_IMAGE_SIZE` | `1024x1536` | Portrait, matching the Flux default aspect |
| `TTS_VOICE` | `en-US-AvaNeural` | Edge TTS voice (run `edge-tts --list-voices`) |
| `TTS_VOICE_MN` | `mn-MN-YesuiNeural` | Auto-selected for scenes detected as Mongolian — see [Mongolian Language Support](#mongolian-language-support) |
| `WHISPER_MODEL_MN` | `Tsedee/whisper-large-v3-turbo-mn-2` | Whisper fine-tune used for scenes detected as Mongolian |
| `YT_CLIENT_SECRET` | `client_secret.json` | YouTube OAuth client secret filename |
| `YT_CREDENTIALS` | `credentials.storage` | OAuth token storage filename |
| `API_PORT` | `8000` | Port for `python api.py` / `make api` dev mode only |
| `PYTHON_EXECUTABLE` | — | Required only inside a frozen `backend.exe` — point at the Python this project's dependencies are installed into |

---

## System Requirements

The desktop app itself is Windows-only (Flutter Windows + Win32 APIs for
backend process lifecycle). `pipeline.py`/`cli.py` are plain Python and run
on Linux/macOS too if you're not using the Flutter app.

Requirements depend heavily on which providers you pick (see [AI
Providers](#ai-providers)):

| Component | Codex path (`AI_PROVIDER=codex` + `IMAGE_PROVIDER=codex`) | Local path (`llama` + `flux`) |
|-----------|---|---|
| GPU / VRAM | Not required | 8 GB minimum, 16 GB+ recommended |
| RAM | 8 GB | 16–32 GB |
| Storage | ~5 GB (models auto-download as needed) | 20–50 GB (GGUF + Flux weights) |
| Account | ChatGPT/Codex login | None |
| ffmpeg | Required either way | Required either way |

---

## Directory Structure

```
AI-YouTube-Video-Generator/
├── pipeline.py          unified pipeline (all 10 modules)
├── cli.py               interactive CLI manager
├── api.py               REST API for the Flutter manager app (self-configures on startup)
├── backend.spec         PyInstaller spec -> backend.exe (make backend-exe)
├── app/                 Flutter manager app (Windows desktop)
│   └── lib/stage_ring.dart   the tinted progress-ring widget used across the UI
├── docs/CONNECTION.md   backend<->frontend connection design + checklist
├── create.py            database initialiser (auto-run by api.py if main.db is missing)
├── setup.sh             one-shot bootstrap script
├── Makefile             convenience targets
├── requirements.txt     pip dependencies
├── .env.example         config template
├── .env                 your config (git-ignored; auto-created from .env.example if missing)
├── main.db              SQLite database (git-ignored; auto-created if missing)
├── pipeline.lock        runtime lock file (git-ignored)
├── client_secret.json   YouTube OAuth secret (git-ignored)
├── credentials.storage  OAuth tokens (git-ignored)
├── logs/                pipeline logs + cron.log
├── models/              GGUF / auto-downloaded models (git-ignored)
│   └── lid.176.ftz      fastText language-ID model (auto-downloaded)
├── song/                background music library
│   ├── bright/          .mp3 files per mood
│   ├── calm/
│   ├── dark/
│   ├── dramatic/
│   ├── funky/
│   ├── happy/
│   ├── inspirational/
│   └── sad/
├── optic/               optical flare clips (1.mp4 – 9.mp4)
├── temp/                intermediate render files (auto-cleaned)
│   ├── audio/
│   ├── clip/
│   ├── codex/           scratch dir for AI_PROVIDER=codex (per-call schema/output files)
│   ├── image/
│   ├── mix/
│   ├── subtitle/
│   ├── temp/
│   ├── video/
│   └── voice/
└── final/               finished .mp4 files
```

---

## YouTube API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → enable **YouTube Data API v3**
3. Create OAuth 2.0 credentials (Desktop app)
4. Download `client_secret.json` → place in repo root
5. First upload run opens a browser for OAuth consent — token is saved automatically

---

## Cron (Automated Scheduling)

`setup.sh` installs a cron entry automatically (Linux/WSL). Default: every hour.

To change the schedule, edit line `CRON_SCHEDULE` in `setup.sh` before running it:

```bash
CRON_SCHEDULE="0 * * * *"    # every hour (default)
CRON_SCHEDULE="0 */6 * * *"  # every 6 hours
CRON_SCHEDULE="0 2 * * *"    # daily at 02:00
```

The pipeline uses a lock file (`pipeline.lock`) so concurrent runs are safely refused.

```bash
make cron-show      # see installed cron entry
make cron-remove    # remove it
```

Cron output goes to `logs/cron.log`. On native Windows without WSL, use
Windows Task Scheduler to run `python pipeline.py` on a schedule instead,
or just use the Flutter app's "Run now" button interactively.

---

## Pipeline Modules

| # | Module | What it does |
|---|--------|-------------|
| 01 | **feed** | Text/RSS queue → LLM (llama.cpp or Codex) generates 6 scenes: narration + image prompt + title + description + music genre |
| 02 | **image** | One AI image per scene, via Flux, OpenAI Images, or Codex's `image_gen` tool |
| 03 | **voice** | Narration → speech via Edge TTS, auto-selecting a Mongolian voice per scene when detected |
| 04 | **clip** | Combines image + audio + optical flare into a video clip per scene |
| 05 | **subtitle** | Transcribes audio with Whisper (generic or Mongolian-finetuned, auto-selected) → burns word-level highlighted subtitles |
| 06 | **transition** | Concatenates scene clips with smooth transitions |
| 07 | **mix** | Overlays background music (genre chosen by the LLM), applies echo/EQ, normalises |
| 08 | **final** | Merges video + mixed audio → `final/{seedId}.mp4` |
| 09 | **upload** | Uploads to YouTube with title + description (skipped in `--output file` mode) |
| 10 | **clean** | Deletes temp files for uploaded videos |

Every stage that can fail records the failure against its project
(`seedErrorStep`/`seedErrorMsg`) so it surfaces as "Needs attention" in the
app — projects don't silently sit in "in progress" forever with no visible
reason why.

---

## Troubleshooting

**Dashboard shows "Python dependencies aren't installed yet"**
Run the exact command the banner shows (`pip install -r requirements.txt`
from the repo root), then click "Recheck". See [First Run](#first-run).

**A project sits in "In progress" with no error**
Should not happen anymore — every pipeline stage now records a failure
against the project so it surfaces under "Needs attention" instead. If you
still see this, please open an issue with the relevant lines from
`logs/pipeline.log`.

**Codex image/text calls time out**
`CODEX_STARTUP_IDLE_TIMEOUT` (default 180s) kills a call that produces zero
activity for that long — a genuine hang, not a slow-but-working one. If you
see `"no activity for Ns"` failures on a slow connection or with several
reference images attached, raise it in `.env`. `CODEX_IMAGE_TIMEOUT` /
`CODEX_TIMEOUT` are the overall per-call ceilings, separate from that.

**`LLAMA_MODEL_PATH` not found**
Only relevant if `AI_PROVIDER=llama`. Download a GGUF from HuggingFace and
set the path in `.env` — or switch to `AI_PROVIDER=codex` to skip local
models entirely.

**Flux out of VRAM**
Only relevant if `IMAGE_PROVIDER=flux`. Set `FLUX_CPU_OFFLOAD=true` in
`.env` (enabled by default), use a smaller model like
`black-forest-labs/FLUX.1-schnell`, or switch to `IMAGE_PROVIDER=codex`.

**YouTube upload fails with 403**
OAuth token expired — delete `credentials.storage` and run `make upload` once to re-authenticate.

**Pipeline already running (lock file)**
A previous run crashed and left the lock. Use `python cli.py stop` or `rm pipeline.lock`.

**Logs**
All modules log to `logs/pipeline.log` (UTF-8 — safe for non-English
scenes) and to stdout. Cron output goes to `logs/cron.log`. The Flutter
app's own log folder is reachable from Settings → "Open log folder".

---

## About the Developer

**Available for hire** — AI/ML Engineer specialising in end-to-end automation pipelines.

**Skills demonstrated in this project:**
- Multi-provider AI orchestration (local llama.cpp/Flux, OpenAI APIs, Codex CLI) behind one interface
- Real language identification (fastText) driving per-scene voice/model selection, not string heuristics
- HuggingFace diffusers + Flux image generation, and `transformers`-based ASR fine-tune integration
- FFmpeg media processing pipeline (clips, subtitles, transitions, audio mixing)
- Whisper speech-to-text for word-level subtitle alignment
- YouTube Data API v3 + OAuth2
- SQLite pipeline state machine with per-stage failure surfacing
- Native Windows desktop app (Flutter) with a self-configuring, first-run-aware backend
- Cron automation with lockfile concurrency control
- Zero-config clone-to-run setup

**Contact: tuvshin.org@gmail.com**

---

## License

MIT License — see LICENSE for details.
