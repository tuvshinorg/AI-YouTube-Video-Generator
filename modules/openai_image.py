"""OpenAI Images API as an alternative to local Flux/diffusers.

Used when IMAGE_PROVIDER=openai (see modules/config.py). Calls OpenAI's REST
images endpoint directly via `requests` — no `openai` SDK dependency needed.
This module only implements one function, openai_generate_image(), matching
the contract modules/image.py needs: given a prompt, write a PNG to disk.
"""

from .config import *

import base64
import requests

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"


def openai_generate_image(prompt: str, out_path: str) -> None:
    """Generate one image via the OpenAI Images API and save it to *out_path*."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set — required when IMAGE_PROVIDER=openai")

    payload = {
        "model": OPENAI_IMAGE_MODEL,
        "prompt": prompt,
        "size": OPENAI_IMAGE_SIZE,
        "n": 1,
    }
    # gpt-image-1 always returns b64_json and rejects response_format; dall-e-2/3
    # default to a URL response, so ask explicitly for base64 to skip a download.
    if OPENAI_IMAGE_MODEL.startswith("dall-e"):
        payload["response_format"] = "b64_json"

    resp = requests.post(
        OPENAI_IMAGES_URL,
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json=payload,
        timeout=OPENAI_IMAGE_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI image generation failed ({resp.status_code}): {resp.text[:500]}")

    b64 = resp.json()["data"][0]["b64_json"]
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(b64))
