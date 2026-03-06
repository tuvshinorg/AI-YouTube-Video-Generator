#!/usr/bin/env python3
"""
AI YouTube Video Generator — Unified Pipeline
==============================================
One file, ten independent modules.  Run the whole pipeline:

    python pipeline.py

Or run any single module on its own:

    python pipeline.py --module feed
    python pipeline.py --module image
    python pipeline.py --module voice
    python pipeline.py --module clip
    python pipeline.py --module subtitle
    python pipeline.py --module transition
    python pipeline.py --module mix
    python pipeline.py --module final
    python pipeline.py --module upload
    python pipeline.py --module clean

Image generation uses HuggingFace Diffusers with Flux directly.
Set FLUX_MODEL_ID in the CONFIG section to any Flux-compatible model,
e.g. "black-forest-labs/FLUX.1-dev" or "enhanceaiteam/Flux-Uncensored-V2".
"""

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
import feedparser
import httplib2
import requests
import whisper
from bs4 import BeautifulSoup
from googleapiclient import discovery
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import run_flow
from llama_cpp import Llama
from pydantic import BaseModel, ValidationError

# HuggingFace Diffusers for Flux image generation
import torch
from diffusers import FluxPipeline

# Optional: silence diffusers/transformers progress noise in production
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import edge_tts


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG  — values come from .env; sensible defaults are provided so the
#           pipeline works right after `git clone` + `bash setup.sh`.
# ──────────────────────────────────────────────────────────────────────────────
# Auto-detect repo root as the directory that contains this script so the
# project works regardless of where it was cloned.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.getenv("BASE_DIR", _SCRIPT_DIR)
DB_PATH     = f"{BASE_DIR}/main.db"
LOG_DIR     = f"{BASE_DIR}/logs"

# ── llama.cpp LLM ─────────────────────────────────────────────────────────────
# Set LLAMA_MODEL_PATH in .env to your GGUF file.  Download example:
#   huggingface-cli download bartowski/Llama-3.2-3B-Instruct-GGUF \
#       Llama-3.2-3B-Instruct-Q6_K.gguf --local-dir <BASE_DIR>/models
LLAMA_MODEL_PATH = os.getenv("LLAMA_MODEL_PATH",
                             os.path.join(_SCRIPT_DIR, "models",
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
FLUX_DTYPE       = torch.bfloat16
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


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 01 · FEED  (RSS → seed + scene rows in the DB)
# ══════════════════════════════════════════════════════════════════════════════
def _clean_text(html_text: str) -> str:
    text = re.sub(r"<[^>]+>", "", html_text)
    text = re.sub(r"http\S+|www\.\S+", "", text)
    text = re.sub(r"\s+", " ", text)
    text = unescape(text)
    text = re.sub(r"^unbfacts:\s*", "", text)
    return text.strip()


# Module-level LLM cache — loaded once, reused for all feed calls.
_llm: Llama | None = None


def _get_llm() -> Llama:
    """Return the llama.cpp model, loading it on first call."""
    global _llm
    if _llm is not None:
        return _llm
    log.info(f"[llm] Loading model: {LLAMA_MODEL_PATH}")
    _llm = Llama(
        model_path=LLAMA_MODEL_PATH,
        n_ctx=LLAMA_N_CTX,
        n_gpu_layers=LLAMA_N_GPU,
        verbose=LLAMA_VERBOSE,
    )
    log.info("[llm] Model loaded")
    return _llm


def _llm_chat(prompt: str, schema: dict | None = None,
              max_tokens: int = 2048, temperature: float = 0.7) -> str:
    """Send a chat message and return the raw string reply.

    If *schema* is provided the model is constrained to emit valid JSON
    matching that JSON-Schema (llama.cpp grammar mode).
    """
    fmt = {"type": "json_object"}
    if schema:
        fmt["schema"] = schema          # llama-cpp-python ≥ 0.2.76

    resp = _get_llm().create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        response_format=fmt if schema else None,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp["choices"][0]["message"]["content"]


def feed_fetch_snopes():
    """Fetch Snopes RSS, parse full article text, insert new rows into RSS table."""
    log.info("[feed] Fetching Snopes RSS")
    feed = feedparser.parse("https://www.snopes.com/feed/")
    if feed.bozo:
        log.warning(f"[feed] Feed error: {feed.bozo_exception}")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    new = 0
    for entry in feed.entries:
        try:
            link = entry.get("link")
            if not link:
                continue
            r = requests.get(link, timeout=10)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            el = soup.select_one("#article-content")
            if not el:
                continue
            text = _clean_text(el.get_text(strip=True))
            c.execute("SELECT rssId FROM RSS WHERE rssText = ?", (text,))
            if c.fetchone():
                continue
            published = entry.get("published", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            c.execute(
                "INSERT INTO RSS (rssGroup, rssText, rssStamp) VALUES (?,?,?)",
                ("snopes", text, published),
            )
            conn.commit()
            new += 1
        except Exception as e:
            log.error(f"[feed] Entry error: {e}")
    conn.close()
    log.info(f"[feed] Inserted {new} new Snopes entries")


def feed_fetch_news():
    """Fetch Daily Mail RSS (first 5 items) and insert into RSS table."""
    log.info("[feed] Fetching news RSS")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        r = requests.get("https://www.dailymail.co.uk/articles.rss", headers=headers, timeout=10)
        if r.status_code != 200:
            log.warning("[feed] Daily Mail feed unavailable")
            return False
        feed = feedparser.parse(r.content)
        if not feed.entries:
            return False
    except Exception as e:
        log.error(f"[feed] News feed error: {e}")
        return False

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    new = 0
    for entry in feed.entries[:5]:
        try:
            link = entry.get("link")
            if not link:
                continue
            ar = requests.get(link, headers=headers, timeout=10)
            if ar.status_code != 200:
                continue
            soup = BeautifulSoup(ar.content, "html.parser")
            title = entry.get("title", "").strip()
            content = ""
            el = soup.select_one("#content > div.articleWide.cleared > div.alpha")
            if el:
                content = el.get_text(separator=" ", strip=True)
            else:
                for cls in ["content-inner", "entry-content", "article-content", "post-content"]:
                    el = soup.find(class_=cls)
                    if el:
                        content = el.get_text(separator=" ", strip=True)
                        break
            if not content:
                desc = entry.get("description", "") or entry.get("summary", "")
                content = BeautifulSoup(desc, "html.parser").get_text(separator=" ", strip=True)
            text = _clean_text(f"{title} {content}")
            if len(text.strip()) < 20:
                continue
            c.execute("SELECT rssId FROM RSS WHERE rssText = ?", (text,))
            if c.fetchone():
                continue
            published = entry.get("published", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            c.execute(
                "INSERT INTO RSS (rssGroup, rssText, rssStamp) VALUES (?,?,?)",
                ("dailymail", text, published),
            )
            conn.commit()
            new += 1
        except Exception as e:
            log.error(f"[feed] News entry error: {e}")
    conn.close()
    log.info(f"[feed] Inserted {new} new news entries")
    return new > 0


def feed_get_unprocessed_rss():
    """Return the first RSS entry not yet in the seed table, or None."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT rss.rssId, rss.rssGroup, rss.rssText, rss.rssStamp
        FROM rss LEFT JOIN seed ON rss.rssId = seed.rssId
        WHERE seed.rssId IS NULL LIMIT 1
    """)
    row = c.fetchone()
    conn.close()
    if not row:
        log.info("[feed] No unprocessed RSS entries")
        return None
    rss_id, rss_group, rss_text, rss_stamp = row
    try:
        parsed = json.loads(rss_text)
        rss_text = parsed[:5]
    except json.JSONDecodeError:
        pass
    return {"rssId": rss_id, "rssGroup": rss_group, "rssText": rss_text, "rssStamp": rss_stamp}


def feed_process_rss_to_seed(rss_entry: dict, max_retries: int = 3):
    """Use Ollama/LLaMA to build 6 scenes from the RSS text, insert seed+scene+task rows."""
    if not rss_entry:
        return
    attribute = rss_entry["rssText"]
    prompt = f"""Generate a surprising YouTube video script from this text: '{attribute}'.
IMPORTANT REQUIREMENTS:
1. The output MUST have EXACTLY 6 scenes — no more, no less.
2. Each scene MUST be a separate object in a JSON array.
3. Each 'scene' object MUST have:
   - Key 'scene' with value as scene number (1 through 6)
   - Key 'image' with value as a detailed description for AI image generation
   - Key 'text'  with value as narration text for the scene
4. The 6th scene MUST be a creative way to say 'subscribe and like our video'
"""
    retry, validated = 0, None

    while retry < max_retries:
        try:
            raw = _llm_chat(prompt, schema=SceneList.model_json_schema())
            data = SceneList.model_validate_json(raw)
            if len(data.scenes) == 6 and sorted(s.scene for s in data.scenes) == list(range(1, 7)):
                validated = data
                break
            log.warning(f"[feed] Got {len(data.scenes)} scenes, expected 6. Retry {retry+1}")
        except Exception as e:
            log.error(f"[feed] LLM validation error: {e}")
        retry += 1
        time.sleep(1)

    if not validated:
        log.error("[feed] Failed to get valid 6-scene response after retries")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute(
            """INSERT INTO seed
               (rssId, seedPrompt, seedTitle, seedDescription, seedSong,
                seedCreatedDate, seedTransitionStamp, seedMixStamp, seedRenderStamp, seedUploadStamp)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (rss_entry["rssId"], prompt, "not loaded", "not loaded", "not loaded",
             now, "0000-00-00 00:00:00", "0000-00-00 00:00:00",
             "0000-00-00 00:00:00", "0000-00-00 00:00:00"),
        )
        seed_id = cursor.lastrowid
        for scene in validated.scenes:
            cursor.execute(
                "INSERT INTO scene (seedId, sceneNumber, sceneImage, sceneText, sceneCreatedDate) VALUES (?,?,?,?,?)",
                (seed_id, scene.scene, scene.image, scene.text, now),
            )
            cursor.execute(
                """INSERT INTO task
                   (seedId, sceneNumber, sceneImageDate, sceneAudioDate, sceneClipDate, sceneSubtitleDate)
                   VALUES (?,?,?,?,?,?)""",
                (seed_id, scene.scene,
                 "0000-00-00 00:00:00", "0000-00-00 00:00:00",
                 "0000-00-00 00:00:00", "0000-00-00 00:00:00"),
            )
        conn.commit()
        log.info(f"[feed] Seed {seed_id} created with 6 scenes")
    except sqlite3.Error as e:
        log.error(f"[feed] DB error: {e}")
        conn.rollback()
    finally:
        conn.close()


def feed_generate_title_description(rss_entry: dict):
    """Generate YouTube title + description and write to seed table."""
    if not rss_entry:
        return
    prompt = (
        f"I want YouTube video title and description in JSON format only "
        f"from this text '{rss_entry['rssText']}'. "
        f"Do not include any text or explanations."
    )
    try:
        raw    = _llm_chat(prompt, schema=TitleDescriptionResponse.model_json_schema())
        parsed = TitleDescriptionResponse.model_validate_json(raw)
        conn   = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE seed SET seedTitle=?, seedDescription=? WHERE rssId=?",
            (parsed.title, parsed.description, rss_entry["rssId"]),
        )
        conn.commit()
        conn.close()
        log.info(f"[feed] Title: {parsed.title}")
    except Exception as e:
        log.error(f"[feed] Title/desc error: {e}")


def feed_choose_song(rss_entry: dict):
    """Pick a background music genre and random MP3, write path to seed table."""
    if not rss_entry:
        return
    genres = ["bright", "calm", "dark", "dramatic", "funky", "happy", "inspirational", "sad"]
    genre = "calm"
    try:
        prompt = (
            f"I want YouTube video background music from this text '{rss_entry['rssText']}'. "
            f"Choose one of: {' | '.join(genres)}."
        )
        raw    = _llm_chat(prompt, schema=SongResponse.model_json_schema())
        parsed = SongResponse.model_validate_json(raw)
        if parsed.genre in genres:
            genre = parsed.genre
    except Exception as e:
        log.warning(f"[feed] Song genre error: {e}, using 'calm'")

    mp3_dir = f"{BASE_DIR}/song/{genre}/"
    mp3_files = [os.path.join(mp3_dir, f) for f in os.listdir(mp3_dir) if f.lower().endswith(".mp3")] \
        if os.path.isdir(mp3_dir) else []
    if not mp3_files:
        mp3_dir = f"{BASE_DIR}/song/calm/"
        mp3_files = [os.path.join(mp3_dir, f) for f in os.listdir(mp3_dir) if f.lower().endswith(".mp3")] \
            if os.path.isdir(mp3_dir) else []
    if not mp3_files:
        log.error("[feed] No MP3 files found in song directories")
        return

    song_path = random.choice(mp3_files)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE seed SET seedSong=? WHERE rssId=?", (song_path, rss_entry["rssId"]))
    conn.commit()
    conn.close()
    log.info(f"[feed] Song: {song_path}")


def run_feed():
    """Run the full Feed module end-to-end."""
    log.info("═══ MODULE: FEED ═══")
    feed_fetch_snopes()
    rss = feed_get_unprocessed_rss()
    feed_process_rss_to_seed(rss)
    feed_generate_title_description(rss)
    feed_choose_song(rss)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 02 · IMAGE  (HuggingFace Flux — no Automatic1111/WebUI Forge needed)
# ══════════════════════════════════════════════════════════════════════════════

# Module-level pipeline cache so we only load weights once per process.
_flux_pipe = None


def _get_flux_pipe() -> FluxPipeline:
    """Load the Flux pipeline once and return it on subsequent calls."""
    global _flux_pipe
    if _flux_pipe is not None:
        return _flux_pipe

    log.info(f"[image] Loading Flux model: {FLUX_MODEL_ID}")
    pipe = FluxPipeline.from_pretrained(
        FLUX_MODEL_ID,
        torch_dtype=FLUX_DTYPE,
    )
    if FLUX_CPU_OFFLOAD:
        # Moves model layers to CPU when not in use – reduces peak VRAM usage
        pipe.enable_model_cpu_offload()
    else:
        pipe = pipe.to("cuda")

    _flux_pipe = pipe
    log.info("[image] Flux model loaded")
    return pipe


def image_generate_for_seed(seed_id: int):
    """Generate one PNG per scene that hasn't been imaged yet, using Flux."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT taskId, sceneNumber FROM task "
        "WHERE sceneImageDate='0000-00-00 00:00:00' AND seedId=?",
        (seed_id,),
    )
    tasks = cursor.fetchall()

    if not tasks:
        conn.close()
        return

    pipe = _get_flux_pipe()

    for task_id, scene_number in tasks:
        cursor.execute(
            "SELECT sceneId, sceneImage FROM scene WHERE seedId=? AND sceneNumber=?",
            (seed_id, scene_number),
        )
        row = cursor.fetchone()
        if not row:
            continue
        scene_id, scene_image_prompt = row

        out_dir = f"{BASE_DIR}/temp/image/{scene_id}"
        os.makedirs(out_dir, exist_ok=True)
        image_path = os.path.join(out_dir, "image.png")

        full_prompt = scene_image_prompt
        # Append negative guidance as a separate "negative" token block if supported;
        # Flux is a guidance-distilled model – negative prompt has no official channel,
        # so we append style cues to the positive prompt instead.
        full_prompt += f", high quality, sharp, professional photography, cinematic"

        log.info(f"[image] Generating scene {scene_number} (task {task_id}): {scene_image_prompt[:80]}…")
        try:
            result = pipe(
                prompt=full_prompt,
                height=FLUX_HEIGHT,
                width=FLUX_WIDTH,
                num_inference_steps=FLUX_STEPS,
                guidance_scale=FLUX_GUIDANCE,
                generator=torch.Generator().manual_seed(random.randint(0, 2**32 - 1)),
            )
            image = result.images[0]
            image.save(image_path)
            log.info(f"[image] Saved: {image_path}")

            cursor.execute(
                "UPDATE task SET sceneImageDate=datetime('now','localtime') WHERE taskId=?",
                (task_id,),
            )
            conn.commit()
        except Exception as e:
            log.error(f"[image] Generation failed for taskId {task_id}: {e}")

    conn.close()


def run_image():
    """Run the Image module for all pending seeds."""
    log.info("═══ MODULE: IMAGE ═══")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT DISTINCT seedId FROM task
           WHERE sceneImageDate='0000-00-00 00:00:00'
           AND sceneAudioDate='0000-00-00 00:00:00'
           AND sceneClipDate='0000-00-00 00:00:00'
           AND sceneSubtitleDate='0000-00-00 00:00:00'"""
    )
    seeds = cursor.fetchall()
    conn.close()
    log.info(f"[image] {len(seeds)} pending seeds")
    for (seed_id,) in seeds:
        try:
            image_generate_for_seed(seed_id)
        except Exception as e:
            log.error(f"[image] Seed {seed_id} failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 03 · VOICE  (edge-tts text-to-speech)
# ══════════════════════════════════════════════════════════════════════════════
async def _tts_scene(seed_id: int, task_id: int, scene_number: int, cursor, conn):
    cursor.execute(
        "SELECT sceneId, sceneText FROM scene WHERE seedId=? AND sceneNumber=?",
        (seed_id, scene_number),
    )
    row = cursor.fetchone()
    if not row:
        return
    scene_id, scene_text = row
    out_dir = f"{BASE_DIR}/temp/voice/{scene_id}"
    os.makedirs(out_dir, exist_ok=True)
    audio_path = os.path.join(out_dir, "audio.mp3")
    communicate = edge_tts.Communicate(scene_text, TTS_VOICE)
    await communicate.save(audio_path)
    cursor.execute(
        "UPDATE task SET sceneAudioDate=datetime('now','localtime') WHERE taskId=?",
        (task_id,),
    )
    conn.commit()
    log.info(f"[voice] Saved audio: {audio_path}")


async def voice_generate_for_seed(seed_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT taskId, sceneNumber FROM task
           WHERE sceneImageDate!='0000-00-00 00:00:00'
           AND sceneAudioDate='0000-00-00 00:00:00'
           AND seedId=?""",
        (seed_id,),
    )
    tasks = cursor.fetchall()
    for task_id, scene_number in tasks:
        await _tts_scene(seed_id, task_id, scene_number, cursor, conn)
    conn.close()


def run_voice():
    """Run the Voice module for all pending seeds."""
    log.info("═══ MODULE: VOICE ═══")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT DISTINCT seedId FROM task
           WHERE sceneImageDate!='0000-00-00 00:00:00'
           AND sceneAudioDate='0000-00-00 00:00:00'
           AND sceneClipDate='0000-00-00 00:00:00'
           AND sceneSubtitleDate='0000-00-00 00:00:00'"""
    )
    seeds = cursor.fetchall()
    conn.close()
    log.info(f"[voice] {len(seeds)} pending seeds")
    for (seed_id,) in seeds:
        try:
            asyncio.run(voice_generate_for_seed(seed_id))
        except Exception as e:
            log.error(f"[voice] Seed {seed_id} failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 04 · CLIP  (image + audio → video clip with optical flare)
# ══════════════════════════════════════════════════════════════════════════════
def _ffprobe_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    return float(subprocess.check_output(cmd).decode().strip())


def clip_make_for_seed(seed_id: int):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT taskId, sceneNumber FROM task WHERE sceneClipDate='0000-00-00 00:00:00' AND seedId=?",
        (seed_id,),
    )
    tasks = cursor.fetchall()

    for task_id, scene_number in tasks:
        cursor.execute(
            "SELECT sceneId FROM scene WHERE seedId=? AND sceneNumber=?",
            (seed_id, scene_number),
        )
        row = cursor.fetchone()
        if not row:
            continue
        scene_id = row[0]

        voice_dir = f"{BASE_DIR}/temp/voice/{scene_id}"
        clip_dir  = f"{BASE_DIR}/temp/clip/{scene_id}"
        os.makedirs(voice_dir, exist_ok=True)
        os.makedirs(clip_dir, exist_ok=True)

        image_path = f"{BASE_DIR}/temp/image/{scene_id}/image.png"
        audio_path = os.path.join(voice_dir, "audio.mp3")
        video_path = os.path.join(clip_dir, "video.mp4")
        flare_path = f"{BASE_DIR}/optic/{random.randint(1, OPTIC_COUNT)}.mp4"

        if not os.path.exists(image_path):
            log.error(f"[clip] Image not found: {image_path}")
            continue

        try:
            audio_dur   = math.ceil(_ffprobe_duration(audio_path))
            total_dur   = audio_dur + CLIP_START_DELAY + CLIP_END_DELAY
            flare_dur   = _ffprobe_duration(flare_path)
            loop_frames = int(total_dur / flare_dur * 30 * flare_dur) + 30

            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", image_path,
                "-i", flare_path,
                "-i", audio_path,
                "-filter_complex",
                (
                    f"[0:v]scale=1080:1920,setsar=1,format=yuva420p,trim=duration={total_dur}[bg]; "
                    f"[1:v]scale=1080:1920,format=rgba,colorchannelmixer=aa=0.5[flare_scaled]; "
                    f"[flare_scaled]loop=loop=-1:size={loop_frames}:start=0[flare_loop]; "
                    f"[flare_loop]trim=duration={total_dur}[overlay]; "
                    "[bg][overlay]overlay=0:0:shortest=1[out]"
                ),
                "-map", "[out]",
                "-map", "2:a",
                "-af", f"adelay={CLIP_START_DELAY*1000}|{CLIP_START_DELAY*1000}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(total_dur),
                "-pix_fmt", "yuv420p",
                "-r", "30",
                video_path,
            ]
            subprocess.run(cmd, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log.info(f"[clip] Created: {video_path}")

            cursor.execute(
                "UPDATE task SET sceneClipDate=datetime('now','localtime') WHERE taskId=?",
                (task_id,),
            )
            conn.commit()
        except Exception as e:
            log.error(f"[clip] Failed for scene {scene_id}: {e}")
    conn.close()


def run_clip():
    """Run the Clip module for all pending seeds."""
    log.info("═══ MODULE: CLIP ═══")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    cursor = conn.cursor()
    cursor.execute(
        """SELECT DISTINCT seedId FROM task
           WHERE sceneImageDate!='0000-00-00 00:00:00'
           AND sceneAudioDate!='0000-00-00 00:00:00'
           AND sceneClipDate='0000-00-00 00:00:00'
           AND sceneSubtitleDate='0000-00-00 00:00:00'"""
    )
    seeds = cursor.fetchall()
    conn.close()
    log.info(f"[clip] {len(seeds)} pending seeds")
    for (seed_id,) in seeds:
        try:
            clip_make_for_seed(seed_id)
        except Exception as e:
            log.error(f"[clip] Seed {seed_id} failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 05 · SUBTITLE  (Whisper transcription + ASS burn-in)
# ══════════════════════════════════════════════════════════════════════════════
def _format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _split_into_lines(words: list) -> list:
    MAX_CHARS, MAX_DUR, MAX_GAP = 80, 3.0, 1.5
    subtitles, line, line_dur = [], [], 0.0
    for i, w in enumerate(words):
        line.append(w)
        line_dur += w["end"] - w["start"]
        exceeded = (
            line_dur > MAX_DUR
            or len(" ".join(x["word"] for x in line)) > MAX_CHARS
            or (i > 0 and w["start"] - words[i-1]["end"] > MAX_GAP)
        )
        if exceeded and line:
            subtitles.append({
                "word": " ".join(x["word"] for x in line),
                "start": line[0]["start"],
                "end": line[-1]["end"],
                "textcontents": line,
            })
            line, line_dur = [], 0.0
    if line:
        subtitles.append({
            "word": " ".join(x["word"] for x in line),
            "start": line[0]["start"],
            "end": line[-1]["end"],
            "textcontents": line,
        })
    return subtitles


def _write_ass(subtitles: list, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nTitle: Subtitles\nScriptType: v4.00+\n"
                "PlayResX: 1080\nPlayResY: 1920\nTimer: 100.0000\n\n")
        f.write("[V4+ Styles]\n"
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write("Style: Default,Arial,70,&H00FFFFFF,&H000000FF,&H00000000,"
                "&H00000000,-1,0,0,0,100,100,0,0,1,2,0,5,10,10,30,1\n")
        f.write("Style: Highlight,Arial,70,&H00FFFFFF,&H000000FF,&H00000000,"
                "&H000000FF,-1,0,0,0,100,100,0,0,1,2,0,5,10,10,30,1\n\n")
        f.write("[Events]\nFormat: Layer, Start, End, Style, Name, "
                "MarginL, MarginR, MarginV, Effect, Text\n")
        for line in subtitles:
            s = _format_ass_time(line["start"])
            e = _format_ass_time(line["end"])
            f.write(f"Dialogue: 0,{s},{e},Default,,0,0,0,,{line['word']}\n")
            for w in line["textcontents"]:
                ws = _format_ass_time(w["start"])
                we = _format_ass_time(w["end"])
                pos = line["word"].find(w["word"])
                if pos != -1:
                    pre  = line["word"][:pos]
                    post = line["word"][pos + len(w["word"]):]
                    hl   = f"{{\\c&H00FFFF&}}{w['word']}{{\\c&HFFFFFF&}}"
                    f.write(f"Dialogue: 1,{ws},{we},Highlight,,0,0,0,,{pre}{hl}{post}\n")


def subtitle_process_task(task_id: int):
    video_in   = f"{BASE_DIR}/temp/clip/{task_id}/video.mp4"
    sub_dir    = f"{BASE_DIR}/temp/subtitle/{task_id}"
    os.makedirs(sub_dir, exist_ok=True)
    audio_tmp  = os.path.join(sub_dir, "audio.mp3")
    ass_path   = os.path.join(sub_dir, "subtitles.ass")
    video_out  = os.path.join(sub_dir, "video.mp4")

    # Extract audio
    subprocess.run(
        ["ffmpeg", "-i", video_in, "-vn", "-acodec", "libmp3lame", "-q:a", "2", audio_tmp, "-y"],
        check=True, capture_output=True,
    )

    # Transcribe
    model = whisper.load_model("medium")
    result = model.transcribe(audio_tmp, word_timestamps=True)
    words = [
        {"word": w["word"].strip(), "start": w["start"], "end": w["end"]}
        for seg in result["segments"] for w in seg["words"]
    ]

    # Build & burn subtitles
    lines = _split_into_lines(words)
    _write_ass(lines, ass_path)
    subprocess.run(
        ["ffmpeg", "-i", video_in, "-vf", f"ass={ass_path}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "22",
         "-c:a", "aac", "-b:a", "192k", video_out, "-y"],
        check=True, capture_output=True,
    )
    log.info(f"[subtitle] Created: {video_out}")


def run_subtitle():
    """Run the Subtitle module for all pending tasks."""
    log.info("═══ MODULE: SUBTITLE ═══")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT DISTINCT taskId FROM task
           WHERE sceneImageDate!='0000-00-00 00:00:00'
           AND sceneAudioDate!='0000-00-00 00:00:00'
           AND sceneClipDate!='0000-00-00 00:00:00'
           AND sceneSubtitleDate='0000-00-00 00:00:00'"""
    )
    tasks = cursor.fetchall()
    conn.close()
    log.info(f"[subtitle] {len(tasks)} pending tasks")
    for (task_id,) in tasks:
        try:
            subtitle_process_task(task_id)
            conn2 = sqlite3.connect(DB_PATH)
            conn2.execute(
                "UPDATE task SET sceneSubtitleDate=datetime('now','localtime') WHERE taskId=?",
                (task_id,),
            )
            conn2.commit()
            conn2.close()
        except Exception as e:
            log.error(f"[subtitle] Task {task_id} failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 06 · TRANSITION  (xfade between scene clips)
# ══════════════════════════════════════════════════════════════════════════════
def _extract_segment(src: str, dst: str, start: float, dur: float):
    subprocess.run(
        ["ffmpeg", "-ss", str(start), "-i", src, "-t", str(dur),
         "-c:v", "libx264", "-preset", "fast", "-crf", "22",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-y", dst],
        check=True, stderr=subprocess.PIPE,
    )


def _has_audio(path: str) -> bool:
    result = subprocess.run(
        ["ffprobe", "-i", path, "-show_streams", "-select_streams", "a", "-loglevel", "error"],
        stdout=subprocess.PIPE,
    )
    return bool(result.stdout)


def _create_transition(seg1: str, seg2: str, out: str, ttype: str):
    dur1   = _ffprobe_duration(seg1)
    offset = max(dur1 - TRANS_DURATION, 0)
    vf = f"[0:v][1:v]xfade=transition={ttype}:duration={TRANS_DURATION}:offset={offset}[vout]"
    af = f"[0:a][1:a]acrossfade=d={TRANS_DURATION}[aout]"
    a1, a2 = _has_audio(seg1), _has_audio(seg2)
    cmd = ["ffmpeg", "-i", seg1, "-i", seg2, "-filter_complex"]
    if a1 and a2:
        cmd += [f"{vf};{af}", "-map", "[vout]", "-map", "[aout]"]
    else:
        cmd += [vf, "-map", "[vout]"]
        if a1:  cmd += ["-map", "0:a"]
        elif a2: cmd += ["-map", "1:a"]
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", out]
    subprocess.run(cmd, check=True, stderr=subprocess.PIPE)


def transition_make_video(video_paths: list, output_path: str) -> str:
    if len(video_paths) < 2:
        raise ValueError("Need at least 2 videos for transitions")
    tmp = f"{BASE_DIR}/temp/temp/run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    os.makedirs(tmp, exist_ok=True)

    segs = {}
    for i, v in enumerate(video_paths):
        dur    = _ffprobe_duration(v)
        mid_d  = max(dur - TRANS_START_DUR - TRANS_END_DUR, 0.1)
        s_path = os.path.join(tmp, f"start_{i}.mp4")
        e_path = os.path.join(tmp, f"end_{i}.mp4")
        m_path = os.path.join(tmp, f"mid_{i}.mp4")
        _extract_segment(v, s_path, 0, TRANS_START_DUR)
        _extract_segment(v, e_path, max(dur - TRANS_END_DUR, 0), TRANS_END_DUR)
        _extract_segment(v, m_path, TRANS_START_DUR, mid_d)
        segs[i] = {"start": s_path, "end": e_path, "mid": m_path}

    trans = {}
    for i in range(len(video_paths) - 1):
        t_path = os.path.join(tmp, f"trans_{i}.mp4")
        _create_transition(segs[i]["end"], segs[i+1]["start"], t_path, random.choice(TRANSITION_TYPES))
        trans[i] = t_path

    order = []
    for i in range(len(video_paths)):
        if i > 0:
            order.append(trans[i-1])
        if i == 0:
            order.append(segs[i]["start"])
        order.append(segs[i]["mid"])
        if i == len(video_paths) - 1:
            order.append(segs[i]["end"])

    concat_file = os.path.join(tmp, "concat.txt")
    with open(concat_file, "w") as f:
        for p in order:
            f.write(f"file '{os.path.abspath(p)}'\n")

    cmd = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", "-y", output_path]
    try:
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        # Fallback with re-encode
        cmd[-3:-1] = ["-c:v", "libx264", "-preset", "medium", "-crf", "22",
                      "-pix_fmt", "yuv420p", "-c:a", "aac"]
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE)

    log.info(f"[transition] Output: {output_path}")
    return tmp


def run_transition():
    """Run the Transition module for one pending seed."""
    log.info("═══ MODULE: TRANSITION ═══")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT DISTINCT seedId FROM seed
           WHERE seedTransitionStamp='0000-00-00 00:00:00'
           AND seedMixStamp='0000-00-00 00:00:00'
           AND seedRenderStamp='0000-00-00 00:00:00'
           AND seedUploadStamp='0000-00-00 00:00:00'
           ORDER BY seedId ASC LIMIT 1"""
    )
    row = cursor.fetchone()
    if not row:
        log.info("[transition] No pending seeds")
        conn.close()
        return
    seed_id = row[0]
    cursor.execute(
        """SELECT DISTINCT taskId FROM task
           WHERE sceneImageDate!='0000-00-00 00:00:00'
           AND sceneAudioDate!='0000-00-00 00:00:00'
           AND sceneClipDate!='0000-00-00 00:00:00'
           AND sceneSubtitleDate!='0000-00-00 00:00:00'
           AND seedId=?""",
        (seed_id,),
    )
    task_ids = cursor.fetchall()

    videos = [f"{BASE_DIR}/temp/subtitle/{tid}/video.mp4"
              for (tid,) in task_ids
              if os.path.exists(f"{BASE_DIR}/temp/subtitle/{tid}/video.mp4")]

    os.makedirs(f"{BASE_DIR}/temp/video", exist_ok=True)
    out = f"{BASE_DIR}/temp/video/{seed_id}.mp4"

    try:
        transition_make_video(videos, out)
        cursor.execute(
            "UPDATE seed SET seedTransitionStamp=datetime('now','localtime') WHERE seedId=?",
            (seed_id,),
        )
        conn.commit()
    except Exception as e:
        log.error(f"[transition] Seed {seed_id} failed: {e}")
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 07 · MIX  (narration + background music → mixed WAV)
# ══════════════════════════════════════════════════════════════════════════════
def mix_process_seed(seed_id: int):
    video_file = f"{BASE_DIR}/temp/video/{seed_id}.mp4"
    audio_file = f"{BASE_DIR}/temp/audio/{seed_id}.wav"
    mix_folder = f"{BASE_DIR}/temp/mix/{seed_id}"

    if os.path.exists(mix_folder):
        shutil.rmtree(mix_folder)
    os.makedirs(mix_folder, exist_ok=True)
    os.makedirs(os.path.dirname(audio_file), exist_ok=True)

    # Get video duration
    video_dur = float(
        subprocess.check_output(
            shlex.split(f'ffprobe -v error -show_entries format=duration '
                        f'-of default=noprint_wrappers=1:nokey=1 "{video_file}"'),
            text=True,
        ).strip()
    )

    # Extract audio track from the video
    subprocess.run(
        ["ffmpeg", "-i", video_file,
         "-af", f"aresample=async=1000,apad=pad_dur={video_dur}",
         "-to", str(video_dur), "-c:a", "pcm_s16le", audio_file],
        check=True,
    )

    # Get background song
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT seedSong FROM seed WHERE seedId=?", (seed_id,)).fetchone()
    conn.close()
    if not row or not row[0]:
        raise ValueError(f"No seedSong for seed {seed_id}")
    seed_song = row[0].strip()
    if not os.path.exists(seed_song):
        calm = f"{BASE_DIR}/song/calm/"
        mp3s = [os.path.join(calm, f) for f in os.listdir(calm) if f.endswith(".mp3")]
        if not mp3s:
            raise FileNotFoundError("No background music found")
        seed_song = random.choice(mp3s)
        log.warning(f"[mix] Original song not found, using: {seed_song}")

    norm_in   = f"{mix_folder}/norm_input.wav"
    norm_bg   = f"{mix_folder}/norm_bg.wav"
    mixed     = f"{mix_folder}/mixed.wav"
    final_out = f"{mix_folder}/{seed_id}.wav"

    subprocess.run(["ffmpeg-normalize", audio_file, "-c:a", "pcm_s16le",
                    "--normalization-type", "rms", "--target-level", "-18",
                    "-o", norm_in], check=True)
    subprocess.run(["ffmpeg-normalize", seed_song, "-c:a", "pcm_s16le",
                    "--normalization-type", "rms", "--target-level", "-23",
                    "-o", norm_bg], check=True)

    # Mix with EQ + echo + low background volume
    subprocess.run(
        ["ffmpeg", "-i", norm_in, "-stream_loop", "-1", "-i", norm_bg,
         "-filter_complex",
         "[0:a]equalizer=f=100:width_type=o:width=2:g=6,"
         "equalizer=f=1000:width_type=o:width=2:g=-2,"
         "equalizer=f=5000:width_type=o:width=2:g=-1[aeq1]; "
         "[1:a]equalizer=f=100:width_type=o:width=2:g=6,"
         "equalizer=f=1000:width_type=o:width=2:g=4,"
         "equalizer=f=5000:width_type=o:width=2:g=4[aeq2]; "
         "[aeq1]aecho=0.5:0.6:30:0.05[aecho]; "
         "[aeq2]volume=0.03[bg]; "
         "[aecho][bg]amix=inputs=2:duration=shortest[aout]",
         "-map", "[aout]", "-c:a", "pcm_s16le", mixed],
        check=True,
    )
    subprocess.run(["ffmpeg-normalize", mixed, "-c:a", "pcm_s16le",
                    "--normalization-type", "rms", "--target-level", "-18",
                    "-o", final_out], check=True)

    shutil.copy(final_out, f"{BASE_DIR}/temp/mix/{seed_id}.wav")

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE seed SET seedMixStamp=datetime('now','localtime') WHERE seedId=?",
        (seed_id,),
    )
    conn.commit()
    conn.close()
    log.info(f"[mix] Done for seed {seed_id}")


def run_mix():
    """Run the Mix module for one pending seed."""
    log.info("═══ MODULE: MIX ═══")
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        """SELECT DISTINCT seedId FROM seed
           WHERE seedTransitionStamp!='0000-00-00 00:00:00'
           AND seedMixStamp='0000-00-00 00:00:00'
           AND seedRenderStamp='0000-00-00 00:00:00'
           AND seedUploadStamp='0000-00-00 00:00:00'"""
    ).fetchone()
    conn.close()
    if not row:
        log.info("[mix] No pending seeds")
        return
    try:
        mix_process_seed(row[0])
    except Exception as e:
        log.error(f"[mix] Seed {row[0]} failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 08 · FINAL  (merge video track + mixed audio into final MP4)
# ══════════════════════════════════════════════════════════════════════════════
def final_merge(seed_id: int) -> bool:
    video_in  = f"{BASE_DIR}/temp/video/{seed_id}.mp4"
    audio_in  = f"{BASE_DIR}/temp/mix/{seed_id}/{seed_id}.wav"
    output    = f"{BASE_DIR}/final/{seed_id}.mp4"
    os.makedirs(os.path.dirname(output), exist_ok=True)

    for p, label in [(video_in, "video"), (audio_in, "audio")]:
        if not os.path.exists(p):
            log.error(f"[final] {label} not found: {p}")
            return False

    v_dur = _ffprobe_duration(video_in)
    a_dur = _ffprobe_duration(audio_in)
    log.info(f"[final] video={v_dur:.2f}s  audio={a_dur:.2f}s")

    cmd = ["ffmpeg", "-y", "-i", video_in, "-i", audio_in]

    if abs(v_dur - a_dur) > 1:
        factor = v_dur / a_dur
        filters = []
        r = factor
        while r > 2.0:
            filters.append("atempo=2.0"); r /= 2.0
        while r < 0.5:
            filters.append("atempo=0.5"); r *= 2.0
        filters.append(f"atempo={r:.4f}")
        cmd += ["-filter_complex", f"[1:a]{','.join(filters)}[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]

    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-pix_fmt", "yuv420p", "-c:a", "libmp3lame", "-b:a", "192k",
            output]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        log.info(f"[final] Saved: {output}")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"[final] FFmpeg error: {e.stderr.decode()}")
        return False


def run_final():
    """Run the Final module for one pending seed."""
    log.info("═══ MODULE: FINAL ═══")
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        """SELECT DISTINCT seedId FROM seed
           WHERE seedTransitionStamp!='0000-00-00 00:00:00'
           AND seedMixStamp!='0000-00-00 00:00:00'
           AND seedRenderStamp='0000-00-00 00:00:00'
           AND seedUploadStamp='0000-00-00 00:00:00'
           LIMIT 1"""
    ).fetchone()
    conn.close()
    if not row:
        log.info("[final] No pending seeds")
        return
    seed_id = row[0]
    if final_merge(seed_id):
        conn2 = sqlite3.connect(DB_PATH)
        conn2.execute(
            "UPDATE seed SET seedRenderStamp=CURRENT_TIMESTAMP WHERE seedId=?",
            (seed_id,),
        )
        conn2.commit()
        conn2.close()


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 09 · UPLOAD  (YouTube Data API v3)
# ══════════════════════════════════════════════════════════════════════════════
def _yt_credentials():
    storage = Storage(CREDENTIALS_STORAGE)
    creds = storage.get()
    if not creds or creds.invalid:
        flow = flow_from_clientsecrets(
            CLIENT_SECRET_FILE, scope=YOUTUBE_SCOPES,
            message="MISSING_CLIENT_SECRET_FILE",
        )
        flags = argparse.Namespace(
            noauth_local_webserver=True, logging_level="ERROR",
            auth_host_name="localhost", auth_host_port=[8080, 8090],
        )
        creds = run_flow(flow, storage, flags=flags, http=httplib2.Http())
    if creds.access_token_expired:
        creds.refresh(httplib2.Http())
        storage.put(creds)
    return creds


def _yt_service():
    creds = _yt_credentials()
    http  = creds.authorize(httplib2.Http(timeout=30))
    return discovery.build("youtube", "v3", http=http, cache_discovery=False)


def upload_video_to_youtube(file_path: str, title: str, description: str = "") -> str | None:
    title = (title or "short").strip()[:100]
    yt = _yt_service()
    body = {
        "snippet": {"title": title, "description": description,
                    "tags": [], "categoryId": "22"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response, retry = None, 0
    while response is None and retry < 3:
        try:
            status, response = request.next_chunk()
            if status:
                log.info(f"[upload] {int(status.progress()*100)}%")
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                retry += 1; time.sleep(5 * retry)
            else:
                raise
    if response:
        vid_id = response["id"]
        log.info(f"[upload] Done: https://www.youtube.com/watch?v={vid_id}")
        return vid_id
    return None


def run_upload():
    """Upload one ready video to YouTube."""
    log.info("═══ MODULE: UPLOAD ═══")
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        """SELECT seedId, seedTitle, seedDescription FROM seed
           WHERE seedTransitionStamp!='0000-00-00 00:00:00'
           AND seedMixStamp!='0000-00-00 00:00:00'
           AND seedRenderStamp!='0000-00-00 00:00:00'
           AND seedUploadStamp='0000-00-00 00:00:00'
           LIMIT 1"""
    ).fetchone()
    conn.close()
    if not row:
        log.info("[upload] No videos ready to upload")
        return
    seed_id, title, description = row
    video_path = f"{BASE_DIR}/final/{seed_id}.mp4"
    if not os.path.exists(video_path):
        log.error(f"[upload] File not found: {video_path}")
        return
    vid_id = upload_video_to_youtube(video_path, title, description)
    if vid_id:
        conn2 = sqlite3.connect(DB_PATH)
        conn2.execute(
            "UPDATE seed SET seedUploadStamp=CURRENT_TIMESTAMP WHERE seedId=?",
            (seed_id,),
        )
        conn2.commit()
        conn2.close()


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 10 · CLEAN  (remove temp files for uploaded seeds)
# ══════════════════════════════════════════════════════════════════════════════
def run_clean():
    """Delete temporary files for all uploaded seeds."""
    log.info("═══ MODULE: CLEAN ═══")
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT s.seedId, t.taskId FROM SEED s
           LEFT JOIN TASK t ON s.seedId = t.seedId
           WHERE s.seedUploadStamp != '0000-00-00 00:00:00'"""
    ).fetchall()
    conn.close()

    if not rows:
        log.info("[clean] Nothing to clean")
        return

    deleted = 0
    for seed_id, task_id in rows:
        paths = [
            f"{BASE_DIR}/temp/audio/{seed_id}.wav",
            f"{BASE_DIR}/temp/video/{seed_id}.mp4",
            f"{BASE_DIR}/temp/mix/{seed_id}.wav",
            f"{BASE_DIR}/temp/mix/{seed_id}",
            f"{BASE_DIR}/temp/image/{seed_id}",
        ]
        if task_id is not None:
            paths += [
                f"{BASE_DIR}/temp/clip/{task_id}",
                f"{BASE_DIR}/temp/image/{task_id}",
                f"{BASE_DIR}/temp/subtitle/{task_id}",
                f"{BASE_DIR}/temp/audio/{task_id}",
                f"{BASE_DIR}/temp/voice/{task_id}",
            ]
        for p in paths:
            try:
                if os.path.isfile(p):
                    os.remove(p); deleted += 1
                elif os.path.isdir(p):
                    shutil.rmtree(p); deleted += 1
            except Exception as e:
                log.warning(f"[clean] Could not remove {p}: {e}")

    # Purge transition scratch space
    temp_temp = f"{BASE_DIR}/temp/temp/"
    if os.path.exists(temp_temp):
        for item in os.listdir(temp_temp):
            p = os.path.join(temp_temp, item)
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
                deleted += 1
            except Exception as e:
                log.warning(f"[clean] {e}")

    log.info(f"[clean] Removed {deleted} items")


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE ORCHESTRATOR  (runs all modules in sequence)
# ══════════════════════════════════════════════════════════════════════════════
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


LOCK_FILE = os.path.join(BASE_DIR, "pipeline.lock")


def _acquire_lock():
    """Write a lock file containing our PID.  Returns True if acquired."""
    if os.path.exists(LOCK_FILE):
        try:
            pid = int(open(LOCK_FILE).read().strip())
            os.kill(pid, 0)          # signal 0 = probe only
            log.warning(f"Pipeline already running (PID {pid}) — lock file: {LOCK_FILE}")
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass                     # stale lock — safe to overwrite
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True


def _release_lock():
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass


def run_pipeline(skip_upload: bool = False):
    """Execute every module in order.

    Parameters
    ----------
    skip_upload : bool
        When True the 'upload' module is skipped; the final .mp4 is kept in
        final/ for the user to upload manually.
    """
    if not _acquire_lock():
        log.error("Aborting: another instance is already running.")
        return

    log.info("╔══════════════════════════════════╗")
    log.info("║  AI YouTube Video Generator      ║")
    log.info("║  Full Pipeline Run               ║")
    if skip_upload:
        log.info("║  Output mode: file (no upload)   ║")
    log.info("╚══════════════════════════════════╝")

    try:
        for name, fn in MODULES.items():
            if skip_upload and name == "upload":
                log.info("── Skipping: upload (output=file) ──")
                continue
            log.info(f"── Running: {name} ──")
            try:
                fn()
            except Exception as e:
                log.error(f"Module '{name}' raised an exception: {e}", exc_info=True)
        log.info("Pipeline complete.")
        if skip_upload:
            _print_output_files()
    finally:
        _release_lock()


def _print_output_files():
    """Log paths of .mp4 files in the final/ directory that are not yet uploaded."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT seedId, seedTitle FROM seed WHERE seedUploadStamp='0000-00-00 00:00:00' "
        "AND seedRenderStamp!='0000-00-00 00:00:00'"
    ).fetchall()
    conn.close()
    if not rows:
        log.info("[output] No completed videos found.")
        return
    log.info("[output] Videos ready for manual upload:")
    for seed_id, title in rows:
        path = os.path.join(BASE_DIR, "final", f"{seed_id}.mp4")
        if os.path.exists(path):
            log.info(f"  [{seed_id}] {title}")
            log.info(f"       → {path}")


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI YouTube Video Generator — unified pipeline",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--module", "-m",
        choices=list(MODULES.keys()),
        help=(
            "Run only one module:\n"
            + "\n".join(f"  {k}" for k in MODULES)
        ),
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
