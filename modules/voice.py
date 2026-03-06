from .config import *

import edge_tts


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
