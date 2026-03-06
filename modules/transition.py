from .config import *
from .clip import _ffprobe_duration


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
