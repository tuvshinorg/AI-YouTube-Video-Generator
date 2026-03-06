from .config import *
from .clip import _ffprobe_duration


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
