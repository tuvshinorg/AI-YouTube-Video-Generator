from .config import *


def feed_get_unprocessed_entry():
    """Return the first queued entry not yet turned into a seed, or None.

    Entries are queued manually (Add Text / Import JSON in the app or cli.py)
    — there is no automatic fetching from any external source.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT queue.queueId, queue.queueGroup, queue.queueText, queue.queueStamp
        FROM queue LEFT JOIN seed ON queue.queueId = seed.queueId
        WHERE seed.queueId IS NULL LIMIT 1
    """)
    row = c.fetchone()
    conn.close()
    if not row:
        log.info("[feed] No unprocessed queue entries")
        return None
    queue_id, queue_group, queue_text, queue_stamp = row
    try:
        parsed = json.loads(queue_text)
        queue_text = parsed[:5]
    except json.JSONDecodeError:
        pass
    return {"queueId": queue_id, "queueGroup": queue_group, "queueText": queue_text, "queueStamp": queue_stamp}


def feed_process_entry_to_seed(entry: dict, max_retries: int = 3):
    """Use Ollama/LLaMA to build 6 scenes from the queued text, insert seed+scene+task rows.

    Returns the new seedId on success, None otherwise. On failure to produce a
    valid 6-scene response, still inserts a seed row (marked with
    seedErrorStep='feed') so the entry isn't picked up and retried forever by
    feed_get_unprocessed_entry(), and so the failure is visible in the app.
    """
    if not entry:
        return None
    attribute = entry["queueText"]
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
    retry, validated, last_error = 0, None, None

    while retry < max_retries:
        try:
            raw = llm_chat(prompt, schema=SceneList.model_json_schema())
            data = SceneList.model_validate_json(raw)
            if len(data.scenes) == 6 and sorted(s.scene for s in data.scenes) == list(range(1, 7)):
                validated = data
                break
            last_error = f"Got {len(data.scenes)} scenes, expected 6"
            log.warning(f"[feed] {last_error}. Retry {retry+1}")
        except Exception as e:
            last_error = str(e)
            log.error(f"[feed] LLM validation error: {e}")
        retry += 1
        time.sleep(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not validated:
        log.error("[feed] Failed to get valid 6-scene response after retries")
        cursor.execute(
            """INSERT INTO seed
               (queueId, seedPrompt, seedTitle, seedDescription, seedSong,
                seedCreatedDate, seedTransitionStamp, seedMixStamp, seedRenderStamp, seedUploadStamp,
                seedErrorStep, seedErrorMsg)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (entry["queueId"], prompt, "not loaded", "not loaded", "not loaded",
             now, "0000-00-00 00:00:00", "0000-00-00 00:00:00",
             "0000-00-00 00:00:00", "0000-00-00 00:00:00",
             "feed", last_error or "Failed to get a valid 6-scene response after retries"),
        )
        conn.commit()
        conn.close()
        return None

    try:
        cursor.execute(
            """INSERT INTO seed
               (queueId, seedPrompt, seedTitle, seedDescription, seedSong,
                seedCreatedDate, seedTransitionStamp, seedMixStamp, seedRenderStamp, seedUploadStamp)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (entry["queueId"], prompt, "not loaded", "not loaded", "not loaded",
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
        return seed_id
    except sqlite3.Error as e:
        log.error(f"[feed] DB error: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def feed_generate_title_description(entry: dict):
    """Generate YouTube title + description and write to seed table."""
    if not entry:
        return
    prompt = (
        f"I want YouTube video title and description in JSON format only "
        f"from this text '{entry['queueText']}'. "
        f"Do not include any text or explanations."
    )
    try:
        raw    = llm_chat(prompt, schema=TitleDescriptionResponse.model_json_schema())
        parsed = TitleDescriptionResponse.model_validate_json(raw)
        conn   = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE seed SET seedTitle=?, seedDescription=? WHERE queueId=?",
            (parsed.title, parsed.description, entry["queueId"]),
        )
        conn.commit()
        conn.close()
        log.info(f"[feed] Title: {parsed.title}")
    except Exception as e:
        log.error(f"[feed] Title/desc error: {e}")


def feed_choose_song(entry: dict):
    """Pick a background music genre and random MP3, write path to seed table."""
    if not entry:
        return
    genres = ["bright", "calm", "dark", "dramatic", "funky", "happy", "inspirational", "sad"]
    genre = "calm"
    try:
        prompt = (
            f"I want YouTube video background music from this text '{entry['queueText']}'. "
            f"Choose one of: {' | '.join(genres)}."
        )
        raw    = llm_chat(prompt, schema=SongResponse.model_json_schema())
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
    conn.execute("UPDATE seed SET seedSong=? WHERE queueId=?", (song_path, entry["queueId"]))
    conn.commit()
    conn.close()
    log.info(f"[feed] Song: {song_path}")


def run_feed():
    """Run the full Feed module end-to-end.

    Only processes entries that were queued manually (Add Text / Import JSON)
    — there is no automatic fetching from any external RSS/news source.
    """
    log.info("═══ MODULE: FEED ═══")
    entry = feed_get_unprocessed_entry()
    seed_id = feed_process_entry_to_seed(entry)
    if seed_id is None:
        return
    feed_generate_title_description(entry)
    feed_choose_song(entry)
