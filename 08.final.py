import subprocess
import os
import logging
import sqlite3
import json

# ============= CONFIGURATION (EDIT THESE PATHS) =============
LOG_PATH = "/root/AI-YouTube-Video-Generator/logs/final.log"  # Path for the log file

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH),
    ],
)

logger = logging.getLogger(__name__)


def get_media_duration(file_path):
    """Get the duration of a media file in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe", 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "json",
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        
        return duration
    except Exception as e:
        logger.error(f"Failed to get duration for {file_path}: {str(e)}")
        return None


def merge_video_audio(seed_id):
    logger.info(f"Starting video merging process for seed ID: {seed_id}")
    
    main_video = f"/root/AI-YouTube-Video-Generator/temp/video/{seed_id}.mp4"
    audio_path = f"/root/AI-YouTube-Video-Generator/temp/mix/{seed_id}/{seed_id}.wav"  # Changed from .mp3 to .wav
    output_path = f"/root/AI-YouTube-Video-Generator/final/{seed_id}.mp4"

    # Validate file existence
    for file_path, name in [
        (main_video, "Main video"),
        (audio_path, "Audio"),
    ]:
        if not os.path.exists(file_path):
            logger.error(f"{name} file not found: {file_path}")
            return False

    # Get durations
    video_duration = get_media_duration(main_video)
    audio_duration = get_media_duration(audio_path)
    
    if video_duration is None or audio_duration is None:
        logger.error("Failed to determine media durations")
        return False
        
    logger.info(f"Video duration: {video_duration:.2f}s, Audio duration: {audio_duration:.2f}s")
    
    # Base command
    command = ["ffmpeg", "-y"]

    # Input main video 
    command.extend(["-i", main_video])

    # Input audio file
    command.extend(["-i", audio_path])

    # Map outputs
    command.extend([
        "-map", "0:v",  # Use video from the main video
        "-map", "1:a",  # Use audio from the audio file
    ])
    
    # Adjust audio speed to match video duration
    if abs(video_duration - audio_duration) > 1:  # If difference is more than 1 second
        speed_factor = video_duration / audio_duration
        logger.info(f"Duration mismatch detected, adjusting audio speed by factor: {speed_factor:.4f}")
        
        # Use the atempo filter to adjust audio speed
        # Note: atempo filter is limited to 0.5x-2.0x range, so we may need to chain multiple filters
        tempo_filters = []
        remaining_factor = speed_factor
        
        # Break down the speed factor into multiple atempo filters if needed
        while remaining_factor > 2.0:
            tempo_filters.append("atempo=2.0")
            remaining_factor /= 2.0
        while remaining_factor < 0.5:
            tempo_filters.append("atempo=0.5")
            remaining_factor *= 2.0
            
        # Add the final adjustment
        tempo_filters.append(f"atempo={remaining_factor:.4f}")
        
        # Replace the audio mapping with a filter_complex to adjust speed
        command = ["ffmpeg", "-y"]
        command.extend(["-i", main_video])  # Input video
        command.extend(["-i", audio_path])  # Input audio
        
        # Apply the audio tempo filter
        filter_complex = f"[1:a]{','.join(tempo_filters)}[a]"
        command.extend(["-filter_complex", filter_complex])
        
        # Map the filtered audio and original video
        command.extend([
            "-map", "0:v",  # Use video from the main video
            "-map", "[a]",  # Use the speed-adjusted audio
        ])

    # Software encoding with libx264 (CPU-based)
    command.extend([
        "-c:v", "libx264",
        "-preset", "medium",  # Standard preset that works on all systems
        "-crf", "22",  # Quality setting (lower = better quality)
        "-pix_fmt", "yuv420p",
    ])

    # Audio settings
    command.extend(["-c:a", "libmp3lame", "-b:a", "192k"])

    # Output file
    command.append(output_path)

    # Execute the command
    logger.info("Starting FFmpeg processing...")
    logger.debug("Command: %s", " ".join(command))

    try:
        process = subprocess.run(command, check=True, capture_output=True, text=True)
        logger.info(f"SUCCESS: Final video saved to {output_path}")
        # Log output from FFmpeg if needed
        if process.stdout:
            logger.debug("FFmpeg output: %s", process.stdout)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg processing failed with error code {e.returncode}")
        if e.stderr:
            logger.error(f"FFmpeg error details: {e.stderr}")
        return False


def process_audio(seed_id):
    """
    Process audio for a specific seed ID
    """
    logger.info(f"Processing audio for seed ID: {seed_id}")

    try:
        # Here you would implement your audio processing logic
        # For example, generating the audio file at AUDIO_PATH

        # After audio processing, merge with video
        success = merge_video_audio(seed_id)

        if success:
            # Update the database to mark this seed as processed
            conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
            cursor = conn.cursor()

            # Update seedRenderStamp in the database
            cursor.execute(
                """
                UPDATE seed
                SET seedRenderStamp = CURRENT_TIMESTAMP
                WHERE seedId = ?
                """,
                (seed_id,),
            )

            conn.commit()
            logger.info(f"Updated seedRenderStamp for seed ID: {seed_id}")
            conn.close()
        else:
            logger.error(f"Failed to process seed ID: {seed_id}")

    except Exception as e:
        logger.exception(f"Error processing audio for seed ID {seed_id}: {str(e)}")


def get_pending_seed():
    """
    Retrieve a pending seed from the database
    """
    logger.info("Checking for pending seeds")
    try:
        conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT seedId 
            FROM seed 
            WHERE seedTransitionStamp != '0000-00-00 00:00:00' 
            AND seedMixStamp != '0000-00-00 00:00:00'
            AND seedRenderStamp = '0000-00-00 00:00:00'
            AND seedUploadStamp = '0000-00-00 00:00:00'
            LIMIT 1
            """
        )

        result = cursor.fetchone()
        conn.close()

        if result:
            seed_id = result[0]
            logger.info(f"Found pending seed ID: {seed_id}")
            return seed_id
        else:
            logger.info("No pending seeds found")
            return None

    except Exception as e:
        logger.exception(f"Database error when fetching pending seeds: {str(e)}")
        return None


if __name__ == "__main__":
    logger.info("=== Video Merger Started ===")
    logger.info("=" * 50)

    # Get pending seed and process it
    seed_id = get_pending_seed()
    if seed_id:
        process_audio(seed_id)
    else:
        logger.warning("No seeds to process")

    logger.info("=== Video Merger Completed ===")