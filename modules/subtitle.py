from .config import *


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

    # Transcribe (model loaded once and cached for the whole process)
    result = _get_whisper().transcribe(audio_tmp, word_timestamps=True)
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
