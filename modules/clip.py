from .config import *


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
