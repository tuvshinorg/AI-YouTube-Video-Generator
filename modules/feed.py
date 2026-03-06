from .config import *

import feedparser
import requests
from bs4 import BeautifulSoup


def _clean_text(html_text: str) -> str:
    text = re.sub(r"<[^>]+>", "", html_text)
    text = re.sub(r"http\S+|www\.\S+", "", text)
    text = re.sub(r"\s+", " ", text)
    text = unescape(text)
    text = re.sub(r"^unbfacts:\s*", "", text)
    return text.strip()


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
