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

from pydantic import BaseModel, ValidationError


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG  — values come from .env; sensible defaults are provided so the
#           pipeline works right after `git clone` + `bash setup.sh`.
# ──────────────────────────────────────────────────────────────────────────────
# Auto-detect repo root as the directory that contains this script so the
# project works regardless of where it was cloned.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.getenv("BASE_DIR", os.path.dirname(_SCRIPT_DIR))
DB_PATH     = f"{BASE_DIR}/main.db"
LOG_DIR     = f"{BASE_DIR}/logs"

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

# ── Flux / HuggingFace image model ──────────────────────────────────────────
# Any FLUX-compatible HuggingFace repo.  Examples:
#   black-forest-labs/FLUX.1-dev
#   black-forest-labs/FLUX.1-schnell
#   enhanceaiteam/Flux-Uncensored-V2
FLUX_MODEL_ID    = os.getenv("FLUX_MODEL_ID", "enhanceaiteam/Flux-Uncensored-V2")
# torch.bfloat16 resolved lazily inside _get_flux_pipe() to avoid importing torch at startup
FLUX_DTYPE_STR   = os.getenv("FLUX_DTYPE", "bfloat16")
FLUX_WIDTH       = int(os.getenv("FLUX_WIDTH",    "540"))
FLUX_HEIGHT      = int(os.getenv("FLUX_HEIGHT",   "960"))
FLUX_STEPS       = int(os.getenv("FLUX_STEPS",    "20"))
FLUX_GUIDANCE    = float(os.getenv("FLUX_GUIDANCE", "3.5"))
FLUX_CPU_OFFLOAD = os.getenv("FLUX_CPU_OFFLOAD", "true").lower() == "true"

# ── TTS ──────────────────────────────────────────────────────────────────────
TTS_VOICE = "en-US-AvaNeural"

# ── YouTube upload ───────────────────────────────────────────────────────────
CLIENT_SECRET_FILE  = os.path.join(BASE_DIR, os.getenv("YT_CLIENT_SECRET",  "client_secret.json"))
CREDENTIALS_STORAGE = os.path.join(BASE_DIR, os.getenv("YT_CREDENTIALS",     "credentials.storage"))
YOUTUBE_SCOPES      = ["https://www.googleapis.com/auth/youtube"]

# ── Video constants ───────────────────────────────────────────────────────────
OPTIC_COUNT        = 9     # optic/1.mp4 … optic/9.mp4
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"{LOG_DIR}/pipeline.log"),
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
    scenes: list[SceneInfo]

class TitleDescriptionResponse(BaseModel):
    title: str
    description: str

class SongResponse(BaseModel):
    genre: str


# ──────────────────────────────────────────────────────────────────────────────
# MODULE-LEVEL CACHES  (populated lazily on first use of each module)
# ──────────────────────────────────────────────────────────────────────────────
_llm         = None   # llama.cpp Llama instance
_flux_pipe   = None   # HuggingFace FluxPipeline instance
_whisper_mdl = None   # OpenAI Whisper model


def _get_llm():
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


def _get_whisper():
    """Return the Whisper model, loading it once per process."""
    global _whisper_mdl
    if _whisper_mdl is not None:
        return _whisper_mdl
    import whisper
    log.info("[subtitle] Loading Whisper model (medium)…")
    _whisper_mdl = whisper.load_model("medium")
    log.info("[subtitle] Whisper ready")
    return _whisper_mdl


def _get_flux_pipe():
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
