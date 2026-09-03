# ──────────────────────────────────────────────────────────────────────────────
# IMPORTS
# ──────────────────────────────────────────────────────────────────────────────
import argparse
import asyncio
import base64
import json
import logging
import math
import os
import random
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from html import unescape

# Third-party (installed via requirements)
from dotenv import load_dotenv
load_dotenv()          # loads .env from CWD or any parent directory

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from pydantic import BaseModel, Field, ValidationError


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG  — values come from .env; sensible defaults are provided so the
#           pipeline works right after `git clone` + `bash setup.sh`.
# ──────────────────────────────────────────────────────────────────────────────
# Auto-detect repo root as the directory that contains this script so the
# project works regardless of where it was cloned.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.getenv("BASE_DIR") or os.path.dirname(_SCRIPT_DIR)
DB_PATH     = f"{BASE_DIR}/main.db"
LOG_DIR     = f"{BASE_DIR}/logs"

# ── AI text provider ──────────────────────────────────────────────────────────
# "llama" (default, local llama.cpp) or "codex" (shells out to the Codex CLI,
# see modules/codex_provider.py — text generation only, no image capability).
AI_PROVIDER   = os.getenv("AI_PROVIDER", "llama").lower()
CODEX_TIMEOUT = int(os.getenv("CODEX_TIMEOUT", "120"))
# Used only when IMAGE_PROVIDER=codex below — image generation (agent tool
# calls + upload) runs slower than a plain text completion. Real generations
# routinely land in the 130-180s range, so a 180s cap kills some of them
# right as they finish — 240s gives that margin. This remains a hard ceiling
# even under --json (see modules/codex_provider.py): once Codex starts an
# actual tool call it can legitimately go silent for minutes with no
# intermediate event, so idle-detection can't safely shrink this further.
CODEX_IMAGE_TIMEOUT = int(os.getenv("CODEX_IMAGE_TIMEOUT", "240"))
# Pause between successive Codex image calls (references + scenes) to stay
# under its usage limit — see modules/image.py::_CodexImagePacer.
CODEX_IMAGE_DELAY = int(os.getenv("CODEX_IMAGE_DELAY", "180"))
# Every `codex exec --json` call is killed early — well before CODEX_TIMEOUT
# / CODEX_IMAGE_TIMEOUT — if it produces zero events (no tool call has even
# started yet) for this long. This is a *different* failure mode from a slow
# generation: it catches Codex hanging before doing any real work at all
# (dead network, stuck waiting on an approval it'll never get) fast, instead
# of waiting out the full per-call ceiling. It's suspended once a tool call
# is actually in flight, since those can go quiet for a long time legitimately.
#
# 90s (the original default) turned out to be too tight in production: with
# 3 reference images attached, Codex can sit on "Reading prompt from stdin"
# for well over a minute before its first tool call even starts — observed
# killing 3 of 6 scenes in a single run, once even mid-retry of an internal
# tool error (view_image "detail" param) that ate into the budget before we
# ever saw an event. 180s keeps the fail-fast benefit for a truly-dead
# process while giving real (if slow) starts enough room.
CODEX_STARTUP_IDLE_TIMEOUT = int(os.getenv("CODEX_STARTUP_IDLE_TIMEOUT", "180"))

# ── llama.cpp LLM ─────────────────────────────────────────────────────────────
# Set LLAMA_MODEL_PATH in .env to your GGUF file.  Download example:
#   huggingface-cli download bartowski/Llama-3.2-3B-Instruct-GGUF \
#       Llama-3.2-3B-Instruct-Q6_K.gguf --local-dir <BASE_DIR>/models
LLAMA_MODEL_PATH = os.getenv("LLAMA_MODEL_PATH",
                             os.path.join(os.path.dirname(_SCRIPT_DIR), "models",
                                          "Llama-3.2-3B-Instruct-Q6_K.gguf"))
LLAMA_N_CTX      = int(os.getenv("LLAMA_N_CTX",  "4096"))
LLAMA_N_GPU      = int(os.getenv("LLAMA_N_GPU",  "-1"))
LLAMA_VERBOSE    = os.getenv("LLAMA_VERBOSE", "false").lower() == "true"

# ── Image provider ────────────────────────────────────────────────────────────
# "flux" (default, local HuggingFace Flux via diffusers), "openai" (OpenAI
# Images API, billed per image via OPENAI_API_KEY — see modules/openai_image.py),
# or "codex" (Codex CLI's built-in image_gen tool, rides on the existing
# Codex/ChatGPT login, no separate API key — see modules/codex_provider.py).
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "flux").lower()

# ── Flux / HuggingFace image model ──────────────────────────────────────────
# Any FLUX-compatible HuggingFace repo.  Examples:
#   black-forest-labs/FLUX.1-dev
#   black-forest-labs/FLUX.1-schnell
#   enhanceaiteam/Flux-Uncensored-V2
FLUX_MODEL_ID    = os.getenv("FLUX_MODEL_ID", "enhanceaiteam/Flux-Uncensored-V2")
# torch.bfloat16 resolved lazily inside get_flux_pipe() to avoid importing torch at startup
FLUX_DTYPE_STR   = os.getenv("FLUX_DTYPE", "bfloat16")
FLUX_WIDTH       = int(os.getenv("FLUX_WIDTH",    "540"))
FLUX_HEIGHT      = int(os.getenv("FLUX_HEIGHT",   "960"))
FLUX_STEPS       = int(os.getenv("FLUX_STEPS",    "20"))
FLUX_GUIDANCE    = float(os.getenv("FLUX_GUIDANCE", "3.5"))
FLUX_CPU_OFFLOAD = os.getenv("FLUX_CPU_OFFLOAD", "true").lower() == "true"

# ── OpenAI Images API ─────────────────────────────────────────────────────────
# Used only when IMAGE_PROVIDER=openai. Needs an API key (platform.openai.com),
# not a ChatGPT/Codex login — separate from AI_PROVIDER=codex above.
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
OPENAI_IMAGE_MODEL   = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
# Portrait, matching the FLUX_WIDTH/HEIGHT default aspect for YouTube Shorts.
OPENAI_IMAGE_SIZE    = os.getenv("OPENAI_IMAGE_SIZE", "1024x1536")
OPENAI_IMAGE_TIMEOUT = int(os.getenv("OPENAI_IMAGE_TIMEOUT", "120"))

# ── Language detection ────────────────────────────────────────────────────────
# Shared by modules/voice.py (pick the TTS voice) and modules/subtitle.py
# (pick the Whisper model). A Cyrillic-script check is NOT enough here — a
# scene could be in Russian, Ukrainian, Kazakh, etc., all Cyrillic but none
# of them Mongolian, and mislabeling them as Mongolian meant the wrong TTS
# voice and a Whisper model fine-tuned on the wrong language entirely. Real
# language ID (fastText's lid.176 — a classifier over 176 languages,
# includes 'mn' and 'ru' as distinct classes) replaces that guess.
FASTTEXT_LID_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"
FASTTEXT_LID_MODEL_PATH = os.getenv(
    "FASTTEXT_LID_MODEL_PATH", os.path.join(BASE_DIR, "models", "lid.176.ftz")
)


def detect_language(text: str) -> str:
    """Return an ISO 639-1 code ('mn', 'ru', 'en', ...) for *text* via
    fastText's lid.176 model, downloaded to FASTTEXT_LID_MODEL_PATH on first
    use (~1MB). Falls back to 'en' for blank input."""
    text = " ".join(text.split())   # predict() rejects embedded newlines
    if not text:
        return "en"
    labels, _ = _get_lid_model().predict(text)
    return labels[0].removeprefix("__label__")


# ── TTS ──────────────────────────────────────────────────────────────────────
TTS_VOICE = "en-US-AvaNeural"
# Auto-selected instead of TTS_VOICE for scenes detected as Mongolian
# (modules/voice.py) — run `edge-tts --list-voices` for other mn-MN options.
TTS_VOICE_MN = os.getenv("TTS_VOICE_MN", "mn-MN-YesuiNeural")

# ── Subtitles (Whisper) ────────────────────────────────────────────────────────
# Generic OpenAI Whisper ("medium" below) is multilingual but mediocre on
# Mongolian specifically. WHISPER_MODEL_MN is a HuggingFace transformers
# checkpoint fine-tuned on Mongolian speech, used instead — picked the same
# way as TTS_VOICE_MN: per scene, based on detect_language(sceneText). It's
# a fine-tune of whisper-large-v3-turbo, so it isn't a good multilingual
# fallback — only ever used for scenes actually detected as Mongolian.
WHISPER_MODEL_MN = os.getenv("WHISPER_MODEL_MN", "Tsedee/whisper-large-v3-turbo-mn-2")

# ── YouTube upload ───────────────────────────────────────────────────────────
CLIENT_SECRET_FILE  = os.path.join(BASE_DIR, os.getenv("YT_CLIENT_SECRET",  "client_secret.json"))
CREDENTIALS_STORAGE = os.path.join(BASE_DIR, os.getenv("YT_CREDENTIALS",     "credentials.storage"))
YOUTUBE_SCOPES      = ["https://www.googleapis.com/auth/youtube"]

# ── Video constants ───────────────────────────────────────────────────────────
OPTIC_COUNT        = 5     # optic/1.mp4 … optic/5.mp4
CLIP_START_DELAY   = 2     # seconds of silence before narration in each clip
CLIP_END_DELAY     = 2     # seconds of silence after narration in each clip
TRANS_START_DUR    = 2.0
TRANS_END_DUR      = 2.0
TRANS_DURATION     = 2.0

TRANSITION_TYPES = [
    "fade", "fadeblack", "fadewhite", "distance",
    "smoothleft", "smoothright", "smoothup", "smoothdown",
    "horzclose", "horzopen", "vertclose", "vertopen",
]

NEGATIVE_PROMPT = (
    "nsfw, blurry, low quality, low resolution, cropped, deformed, disfigured, "
    "poorly drawn, bad anatomy, wrong anatomy, extra limbs, missing limbs, "
    "floating limbs, disconnected limbs, mutation, mutated, ugly, disgusting, "
    "amputee, grain, grainy, noisy, jpeg artifacts, watermarks, text, typography, "
    "out of frame, cut off, duplicate, error, mutant, poorly rendered, "
    "rendering artifacts, poorly rendered hands, poorly rendered face, "
    "duplicate heads, poorly rendered fingers, poorly rendered limbs, "
    "multiple heads, multiple bodies, too many fingers, fused fingers, bad hands, "
    "signature, username, artist name"
)

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING SETUP
# ──────────────────────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)

# Only takes effect if nothing has called basicConfig yet (e.g. a module
# imported directly, outside pipeline.py) — see pipeline.py's own logging
# setup for why UTF-8 must be forced explicitly on Windows here too.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"{LOG_DIR}/pipeline.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("pipeline")


# ──────────────────────────────────────────────────────────────────────────────
# PYDANTIC SCHEMAS  (used by the Feed module for LLM structured output)
# ──────────────────────────────────────────────────────────────────────────────
class SceneInfo(BaseModel):
    scene: int
    image: str
    text: str

class SceneList(BaseModel):
    # min/max both 6: the prompt already demands exactly 6 scenes, and
    # feed.py's retry loop already rejects anything else post-hoc — this
    # just puts that same rule in the schema too, so providers with
    # schema-enforced structured output (Codex) actually honor it during
    # generation instead of only being checked after the fact.
    scenes: list[SceneInfo] = Field(min_length=6, max_length=6)

class TitleDescriptionResponse(BaseModel):
    title: str
    description: str

class SongResponse(BaseModel):
    genre: str

class SceneAssetRefs(BaseModel):
    # One consistent character/background/item description derived from a
    # seed's existing scene texts, used to generate reusable reference
    # images (modules/image.py) so every scene's final image is composed
    # from the same character/setting/prop instead of inventing them fresh
    # from text each time.
    character: str
    background: str
    item: str


def mark_seed_error(seed_id: int, step: str, msg: str):
    """Record a stage failure against a seed so it surfaces as 'needs
    attention' in the app instead of silently sitting in 'in progress'
    forever with no visible reason why."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE seed SET seedErrorStep=?, seedErrorMsg=? WHERE seedId=?",
        (step, str(msg)[:2000], seed_id),
    )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# MODULE-LEVEL CACHES  (populated lazily on first use of each module)
# ──────────────────────────────────────────────────────────────────────────────
_llm          = None   # llama.cpp Llama instance
_flux_pipe    = None   # HuggingFace FluxPipeline instance
_whisper_mdl  = None   # OpenAI Whisper model (generic, multilingual)
_whisper_mn   = None   # transformers ASR pipeline, Mongolian fine-tune
_lid_model    = None   # fastText lid.176 language-identification model


def _get_lid_model():
    global _lid_model
    if _lid_model is not None:
        return _lid_model
    import fasttext
    if not os.path.exists(FASTTEXT_LID_MODEL_PATH):
        os.makedirs(os.path.dirname(FASTTEXT_LID_MODEL_PATH), exist_ok=True)
        log.info(f"[lang] Downloading language-ID model to {FASTTEXT_LID_MODEL_PATH}…")
        import requests
        resp = requests.get(FASTTEXT_LID_URL, timeout=60)
        resp.raise_for_status()
        with open(FASTTEXT_LID_MODEL_PATH, "wb") as f:
            f.write(resp.content)
    _lid_model = fasttext.load_model(FASTTEXT_LID_MODEL_PATH)
    return _lid_model


def get_llm():
    """Return the llama.cpp model, loading it on first call."""
    global _llm
    if _llm is not None:
        return _llm
    from llama_cpp import Llama
    log.info(f"[llm] Loading model: {LLAMA_MODEL_PATH}")
    _llm = Llama(
        model_path=LLAMA_MODEL_PATH,
        n_ctx=LLAMA_N_CTX,
        n_gpu_layers=LLAMA_N_GPU,
        verbose=LLAMA_VERBOSE,
    )
    log.info("[llm] Model loaded")
    return _llm


def llm_chat(prompt: str, schema: dict | None = None,
              max_tokens: int = 2048, temperature: float = 0.7) -> str:
    """Send a chat message and return the raw string reply.

    If *schema* is provided the model is constrained to emit valid JSON
    matching that JSON-Schema. Routes to Codex CLI or local llama.cpp
    depending on AI_PROVIDER. Shared by modules/feed.py and modules/image.py.
    """
    if AI_PROVIDER == "codex":
        from .codex_provider import codex_chat
        return codex_chat(prompt, schema=schema)

    fmt = {"type": "json_object"}
    if schema:
        fmt["schema"] = schema          # llama-cpp-python ≥ 0.2.76

    resp = get_llm().create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        response_format=fmt if schema else None,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp["choices"][0]["message"]["content"]


def get_whisper():
    """Return the generic (multilingual) Whisper model, loading it once per
    process. Used for every scene except ones is_cyrillic() flags as
    Mongolian — see get_whisper_mn()."""
    global _whisper_mdl
    if _whisper_mdl is not None:
        return _whisper_mdl
    import whisper
    log.info("[subtitle] Loading Whisper model (medium)…")
    _whisper_mdl = whisper.load_model("medium")
    log.info("[subtitle] Whisper ready")
    return _whisper_mdl


def get_whisper_mn():
    """Return a `transformers` ASR pipeline running WHISPER_MODEL_MN (the
    Mongolian Whisper fine-tune), loading it once per process.

    Community fine-tunes like this one are published as plain `transformers`
    checkpoints (config.json + model.safetensors), not the OpenAI-format
    checkpoints modules.config.get_whisper() understands — hence the
    separate loader and cache instead of just passing a different name to
    whisper.load_model().
    """
    global _whisper_mn
    if _whisper_mn is not None:
        return _whisper_mn
    import torch
    from transformers import pipeline
    cuda = torch.cuda.is_available()
    log.info(f"[subtitle] Loading Mongolian Whisper fine-tune: {WHISPER_MODEL_MN}…")
    _whisper_mn = pipeline(
        "automatic-speech-recognition",
        model=WHISPER_MODEL_MN,
        dtype=torch.float16 if cuda else torch.float32,
        device=0 if cuda else -1,
        chunk_length_s=30,   # Whisper's native window — without this, audio longer than 30s past the first window is silently dropped
    )
    log.info("[subtitle] Mongolian Whisper ready")
    return _whisper_mn


def get_flux_pipe():
    """Load the Flux pipeline once and return it on subsequent calls."""
    global _flux_pipe
    if _flux_pipe is not None:
        return _flux_pipe

    import torch
    from diffusers import FluxPipeline
    dtype = getattr(torch, FLUX_DTYPE_STR, torch.bfloat16)

    log.info(f"[image] Loading Flux model: {FLUX_MODEL_ID}")
    pipe = FluxPipeline.from_pretrained(FLUX_MODEL_ID, torch_dtype=dtype)
    if FLUX_CPU_OFFLOAD:
        pipe.enable_model_cpu_offload()
    else:
        pipe = pipe.to("cuda")

    _flux_pipe = pipe
    log.info("[image] Flux model loaded")
    return pipe
