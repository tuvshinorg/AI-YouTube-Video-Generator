from .config import *


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
