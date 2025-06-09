import os
import sqlite3
import subprocess
import logging
import random
import math
import shutil

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/root/AI-YouTube-Video-Generator/logs/video.log"),
    ],
)

def cleanup_temp_directory(directory="/root/AI-YouTube-Video-Generator/temp/image/"):
    """
    Remove all files in the specified directory
    """
    try:
        if os.path.exists(directory):
            # Remove all files in the directory
            for file in os.listdir(directory):
                file_path = os.path.join(directory, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            logging.info(f"Cleaned up temporary directory: {directory}")
        else:
            # Create the directory if it doesn't exist
            os.makedirs(directory, exist_ok=True)
            logging.info(f"Created temporary directory: {directory}")
    except Exception as e:
        logging.error(f"Error cleaning up temporary directory: {str(e)}")


def make_video(seedId):
    # Enable multi-threading for SQLite to improve database operations
    conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db", check_same_thread=False)
    conn.execute(
        "PRAGMA journal_mode = WAL"
    )  # Write-Ahead Logging for better concurrency
    conn.execute(
        "PRAGMA synchronous = NORMAL"
    )  # Less strict sync for better performance
    conn.execute("PRAGMA cache_size = -50000")  # Increase cache size to 50MB
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT taskId, sceneNumber 
        FROM task 
        WHERE sceneClipDate = '0000-00-00 00:00:00' AND seedId = ?
    """,
        (seedId,),
    )
    results = cursor.fetchall()

    try:
        subprocess.check_output(["pgrep", "ollama"])
        subprocess.run(
            ["service", "ollama", "stop"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logging.info("Stopped ollama service")
    except Exception as e:
        print(f"Error stopping ollama service: {str(e)}")

    try:
        # Use pkill to find and kill the process by command pattern
        subprocess.run(
            ["pkill", "-f", "stable-diffusion-webui-forge/launch.py"], check=False
        )
        print("Stable Diffusion API process terminated")
    except Exception as e:
        print(f"Error killing Stable Diffusion API process: {e}")

    for result in results:
        taskId, sceneNumber = result

        cursor.execute(
            """
            SELECT sceneId 
            FROM scene 
            WHERE seedId = ? AND sceneNumber = ?
        """,
            (seedId, sceneNumber),
        )
        scene_result = cursor.fetchone()

        if scene_result:
            sceneId = scene_result[0]

            # Create directories for voice and video
            voice_directory = f"/root/AI-YouTube-Video-Generator/temp/voice/{sceneId}"
            video_directory = f"/root/AI-YouTube-Video-Generator/temp/clip/{sceneId}"
            os.makedirs(voice_directory, exist_ok=True)
            os.makedirs(video_directory, exist_ok=True)

            # Get image path
            image_path = f"/root/AI-YouTube-Video-Generator/temp/image/{sceneId}/image.png"
            audio_path = os.path.join(voice_directory, "audio.mp3")
            video_output_path = os.path.join(video_directory, "video.mp4")

            # Select a random optical flare video from 1.mp4 to 9.mp4
            flare_number = random.randint(1, 9)
            flare_path = f"/root/AI-YouTube-Video-Generator/optic/{flare_number}.mp4"

            # Apply optical flare effect to image and create video
            if os.path.exists(image_path):
                try:
                    # Get the duration of the audio file
                    audio_duration_cmd = [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        audio_path,
                    ]
                    audio_duration = float(
                        subprocess.check_output(audio_duration_cmd)
                        .decode("utf-8")
                        .strip()
                    )

                    # Round up to ensure we cover the full audio
                    audio_duration = math.ceil(audio_duration)

                    # Define start and end delays (in seconds)
                    start_delay = 2
                    end_delay = 2

                    # Calculate total video duration (audio + delays)
                    total_duration = audio_duration + start_delay + end_delay

                    # Get the duration of the flare video
                    flare_duration_cmd = [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        flare_path,
                    ]

                    try:
                        flare_duration = float(
                            subprocess.check_output(flare_duration_cmd)
                            .decode("utf-8")
                            .strip()
                        )
                        logging.info(f"Flare video duration: {flare_duration} seconds")
                    except Exception as e:
                        flare_duration = (
                            5.0  # Default to 5 seconds if we can't determine
                        )
                        logging.warning(
                            f"Could not determine flare video duration: {e}. Using default: {flare_duration}s"
                        )

                    # Using FFmpeg to create a video from the image with the optical flare overlay
                    # Include the delays and position the audio to start after the initial delay
                    ffmpeg_cmd = [
                        "ffmpeg",
                        "-y",  # Overwrite output file if it exists
                        "-loop",
                        "1",  # Loop the image
                        "-i",
                        image_path,  # Input image
                        "-i",
                        flare_path,  # Input flare video
                        "-i",
                        audio_path,  # Input audio
                        "-filter_complex",
                        # Modified filter to include start and end delays
                        f"[0:v]scale=1080:1920,setsar=1,format=yuva420p,trim=duration={total_duration}[bg]; "
                        f"[1:v]scale=1080:1920,format=rgba,colorchannelmixer=aa=0.5[flare_scaled]; "
                        f"[flare_scaled]loop=loop=-1:size={int(total_duration / flare_duration * 30 * flare_duration) + 30}:start=0[flare_loop]; "
                        f"[flare_loop]trim=duration={total_duration}[overlay]; "
                        "[bg][overlay]overlay=0:0:shortest=1[out]",
                        "-map",
                        "[out]",  # Map the output of the filter
                        "-map",
                        "2:a",  # Map the audio
                        # Position audio to start after the initial delay
                        "-af",
                        f"adelay={start_delay*1000}|{start_delay*1000}",  # Delay in milliseconds
                        "-c:v",
                        "libx264",  # Standard H.264 encoder
                        "-preset",
                        "medium",  # Preset for quality vs speed
                        "-crf",
                        "23",  # Constant Rate Factor for quality
                        "-c:a",
                        "aac",  # Audio codec
                        "-b:a",
                        "192k",  # Audio bitrate
                        "-t",
                        str(total_duration),  # Total duration including delays
                        "-pix_fmt",
                        "yuv420p",  # Pixel format for compatibility
                        "-r",
                        "30",  # Frame rate
                        video_output_path,
                    ]

                    # Log the full command for debugging
                    logging.debug(f"Executing FFmpeg command: {' '.join(ffmpeg_cmd)}")

                    subprocess.run(ffmpeg_cmd, check=True)
                    logging.info(
                        f"Created video for sceneId {sceneId} with {start_delay}s start delay and {end_delay}s end delay"
                    )
                except subprocess.CalledProcessError as e:
                    logging.error(
                        f"Error creating video for sceneId {sceneId}: {str(e)}"
                    )
            else:
                logging.error(f"Image file not found: {image_path}")

            # Update the database to mark the task as rendered
            cursor.execute(
                """
                UPDATE task 
                SET sceneClipDate = datetime('now', 'localtime') 
                WHERE taskId = ?
            """,
                (taskId,),
            )
            conn.commit()

    conn.close()


def check_gpu():
    """Check for NVIDIA GPU and return its information"""
    try:
        gpu_info = subprocess.check_output("nvidia-smi", shell=True).decode("utf-8")
        logging.info(f"GPU detected: \n{gpu_info.split('|')[1]}")
        return True
    except:
        logging.warning(
            "No NVIDIA GPU detected or nvidia-smi not found. Using CPU encoding."
        )
        return False


if __name__ == "__main__":
    try:
        # Check for GPU - kept for informational purposes only
        has_gpu = check_gpu()
        if has_gpu:
            logging.info("GPU detected but using CPU encoding as configured")
        else:
            logging.info("Using CPU encoding")

        # Use optimized connection settings
        conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db", check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -50000")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT seedId 
            FROM task 
            WHERE sceneImageDate != '0000-00-00 00:00:00' 
            AND sceneAudioDate != '0000-00-00 00:00:00' 
            AND sceneClipDate = '0000-00-00 00:00:00' 
            AND sceneSubtitleDate = '0000-00-00 00:00:00'
        """
        )
        pending_seeds = cursor.fetchall()
        print(f"Found {len(pending_seeds)} pending seeds")

        # Process seeds in batches for better resource management
        batch_size = 5  # Adjust based on your RAM capacity
        for i in range(0, len(pending_seeds), batch_size):
            batch = pending_seeds[i : i + batch_size]
            print(
                f"Processing batch {i//batch_size + 1} of {(len(pending_seeds) + batch_size - 1)//batch_size}"
            )

            for (seedId,) in batch:
                try:
                    print(f"Processing seedId: {seedId}")
                    make_video(seedId)
                except Exception as e:
                    print(f"Error processing seed {seedId}: {str(e)}")

    except Exception as e:
        print(f"Main error: {str(e)}")
    finally:
        conn.close()
