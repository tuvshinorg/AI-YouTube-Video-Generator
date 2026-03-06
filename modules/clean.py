from .config import *


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
