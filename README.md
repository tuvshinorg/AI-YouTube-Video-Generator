# AI YouTube Video Generator

![GitHub stars](https://img.shields.io/github/stars/tuvshinorg/AI-YouTube-Video-Generator?style=social)
![GitHub forks](https://img.shields.io/github/forks/tuvshinorg/AI-YouTube-Video-Generator?style=social)
![GitHub last commit](https://img.shields.io/github/last-commit/tuvshinorg/AI-YouTube-Video-Generator)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

![llama.cpp](https://img.shields.io/badge/llama.cpp-LLaMA%203.2-orange.svg)
![HuggingFace Flux](https://img.shields.io/badge/HuggingFace-Flux-yellow.svg)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Video%20Processing-red.svg)
![YouTube API](https://img.shields.io/badge/YouTube-API%20v3-red.svg)
![OpenAI Whisper](https://img.shields.io/badge/OpenAI-Whisper-black.svg)

## Looking to Hire a Skilled AI/ML Developer?

**Contact: tuvshin.org@gmail.com**

[![Portfolio](https://img.shields.io/badge/💼-Available%20for%20Hire-brightgreen.svg?style=for-the-badge)](mailto:tuvshin.org@gmail.com)

---

## What It Does

Fully autonomous YouTube Shorts factory. Feed it RSS sources (or type text manually) and it generates, renders, and publishes videos without human intervention:

```
RSS / manual text
      ↓
  LLM (llama.cpp) → 6 scenes with narration + image prompts
      ↓
  Flux (HuggingFace) → AI-generated images per scene
      ↓
  Edge TTS → narration audio
      ↓
  FFmpeg → clips + subtitles (Whisper) + transitions + music mix
      ↓
  YouTube API → published  (or saved .mp4 for manual upload)
```

---

## Quick Start (clone → running in one command)

```bash
git clone https://github.com/tuvshinorg/AI-YouTube-Video-Generator.git
cd AI-YouTube-Video-Generator
bash setup.sh
```

`setup.sh` does everything automatically:
- Detects your repo path and writes it to `.env`
- Creates all runtime directories (`logs/`, `temp/*/`, `final/`, `song/*/`, `optic/`, `models/`)
- Detects CUDA and installs `llama-cpp-python` with GPU support if available
- Installs all pip dependencies
- Initialises the SQLite database
- Installs a cron job (full pipeline every hour by default)

Then fill in two values in `.env`:

```bash
# .env
LLAMA_MODEL_PATH=./models/Llama-3.2-3B-Instruct-Q6_K.gguf   # path to your GGUF
FLUX_MODEL_ID=enhanceaiteam/Flux-Uncensored-V2               # any Flux HF repo
```

Download a GGUF model (one-time):
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

## Output Modes

| Mode | Command | Result |
|------|---------|--------|
| **api** (default) | `make run` | Full pipeline → auto-upload to YouTube |
| **file** | `make run-file` | Full pipeline → `.mp4` saved in `final/` for manual upload |

The `--output file` mode skips the upload module and prints the path to your finished video.

---

## Make Targets

```
make setup        first-time install + cron
make cli          interactive manager
make run          full pipeline → YouTube upload
make run-file     full pipeline → save .mp4 locally

make feed         module 01 only: RSS → scenes
make image        module 02 only: images (Flux)
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

Copy `.env.example` to `.env` and edit:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_DIR` | auto-detected | Absolute path to the repo (set automatically by setup.sh) |
| `LLAMA_MODEL_PATH` | `./models/Llama-3.2-3B-Instruct-Q6_K.gguf` | Path to your GGUF model |
| `LLAMA_N_CTX` | `4096` | LLM context window (tokens) |
| `LLAMA_N_GPU` | `-1` | GPU layers: `-1` = all on GPU, `0` = CPU only |
| `LLAMA_VERBOSE` | `false` | Show llama.cpp token output |
| `FLUX_MODEL_ID` | `enhanceaiteam/Flux-Uncensored-V2` | Any Flux-compatible HuggingFace repo |
| `FLUX_CPU_OFFLOAD` | `true` | Offload model to CPU between calls (saves VRAM) |
| `FLUX_WIDTH` | `540` | Output image width (px) |
| `FLUX_HEIGHT` | `960` | Output image height (px) |
| `FLUX_STEPS` | `20` | Diffusion steps |
| `FLUX_GUIDANCE` | `3.5` | Guidance scale |
| `TTS_VOICE` | `en-US-AvaNeural` | Edge TTS voice (run `edge-tts --list-voices`) |
| `YT_CLIENT_SECRET` | `client_secret.json` | YouTube OAuth client secret filename |
| `YT_CREDENTIALS` | `credentials.storage` | OAuth token storage filename |

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Linux | Ubuntu 22.04+ |
| Python | 3.10 | 3.11+ |
| RAM | 16 GB | 32 GB |
| VRAM | 8 GB | 16 GB+ |
| Storage | 20 GB free | 50 GB+ |
| ffmpeg | any | latest |

---

## Directory Structure

```
AI-YouTube-Video-Generator/
├── pipeline.py          unified pipeline (all 10 modules)
├── cli.py               interactive CLI manager
├── create.py            database initialiser
├── setup.sh             one-shot bootstrap script
├── Makefile             convenience targets
├── requirements.txt     pip dependencies
├── .env.example         config template
├── .env                 your config (git-ignored)
├── main.db              SQLite database (git-ignored)
├── pipeline.lock        runtime lock file (git-ignored)
├── client_secret.json   YouTube OAuth secret (git-ignored)
├── credentials.storage  OAuth tokens (git-ignored)
├── logs/                pipeline logs + cron.log
├── models/              GGUF model files
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

`setup.sh` installs a cron entry automatically. Default: every hour.

To change the schedule, edit line `CRON_SCHEDULE` in `setup.sh` before running it:

```bash
CRON_SCHEDULE="0 * * * *"    # every hour (default)
CRON_SCHEDULE="0 */6 * * *"  # every 6 hours
CRON_SCHEDULE="0 2 * * *"    # daily at 02:00
```

The pipeline uses a lock file (`pipeline.lock`) so concurrent cron runs are safely refused.

```bash
make cron-show      # see installed cron entry
make cron-remove    # remove it
```

Cron output goes to `logs/cron.log`.

---

## Pipeline Modules

| # | Module | What it does |
|---|--------|-------------|
| 01 | **feed** | Fetches RSS / queued text → LLM generates 6 scenes (narration + image prompt + title + description + music genre) |
| 02 | **image** | Generates one AI image per scene via HuggingFace Flux |
| 03 | **voice** | Converts narration to speech via Edge TTS |
| 04 | **clip** | Combines image + audio + optical flare into a video clip per scene |
| 05 | **subtitle** | Transcribes audio with Whisper → burns word-level highlighted subtitles |
| 06 | **transition** | Concatenates scene clips with smooth transitions |
| 07 | **mix** | Overlays background music (genre chosen by LLM), applies echo/EQ, normalises |
| 08 | **final** | Merges video + mixed audio → `final/{seedId}.mp4` |
| 09 | **upload** | Uploads to YouTube with title + description (skipped in `--output file` mode) |
| 10 | **clean** | Deletes temp files for uploaded videos |

---

## Troubleshooting

**`LLAMA_MODEL_PATH` not found**
Download a GGUF from HuggingFace and set the path in `.env`.

**Flux out of VRAM**
Set `FLUX_CPU_OFFLOAD=true` in `.env` (enabled by default), or use a smaller model like `black-forest-labs/FLUX.1-schnell`.

**YouTube upload fails with 403**
OAuth token expired — delete `credentials.storage` and run `make upload` once to re-authenticate.

**Pipeline already running (lock file)**
A previous run crashed and left the lock. Use `python cli.py stop` or `rm pipeline.lock`.

**Logs**
All modules log to `logs/` and to stdout. Cron output goes to `logs/cron.log`.

---

## About the Developer

**Available for hire** — AI/ML Engineer specialising in end-to-end automation pipelines.

**Skills demonstrated in this project:**
- Local LLM inference with llama.cpp (structured JSON output via Pydantic)
- HuggingFace diffusers + Flux image generation
- FFmpeg media processing pipeline (clips, subtitles, transitions, audio mixing)
- Whisper speech-to-text for word-level subtitle alignment
- YouTube Data API v3 + OAuth2
- SQLite pipeline state machine
- Interactive CLI with menu + subcommands
- Cron automation with lockfile concurrency control
- Zero-config clone-to-run setup

**Contact: tuvshin.org@gmail.com**

---

## License

MIT License — see LICENSE for details.
