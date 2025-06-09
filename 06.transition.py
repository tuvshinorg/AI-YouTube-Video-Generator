import os
import subprocess
import sqlite3
import logging
import shutil
from datetime import datetime
import random

# ------------------------------
# Global Constants (durations)
# ------------------------------
START_DURATION = 2.0  # seconds for start segment
END_DURATION = 2.0  # seconds for end segment
TRANSITION_DURATION = 2.0  # seconds for transition segments

# ------------------------------
# Logging configuration
# ------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/root/AI-YouTube-Video-Generator/logs/transition.log"),
        logging.StreamHandler(),
    ],
)

def cleanup_temp_directory(directory="/root/AI-YouTube-Video-Generator/temp/subtitle/"):
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


# ------------------------------
# Video Processing Helper Functions
# ------------------------------
def get_video_duration(video_path):
    """Return the duration (in seconds) of a video file."""
    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        duration = float(subprocess.check_output(probe_cmd).decode("utf-8").strip())
        return duration
    except subprocess.CalledProcessError as e:
        logging.error(f"Error getting duration for {video_path}: {e}")
        return None


def extract_segment(input_path, output_path, start_time, duration, force_reencode=True):
    # Always use re-encoding to ensure exact duration
    cmd = [
        "ffmpeg",
        "-ss",
        str(start_time),
        "-i",
        input_path,
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",  # Ensure compatibility
        "-c:a",
        "aac",
        "-y",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
        actual_duration = get_video_duration(output_path)
        logging.info(
            f"Extracted segment {os.path.basename(output_path)} from {input_path} at {start_time}s "
            f"for target {duration}s (actual: {actual_duration:.2f}s)"
        )

        # Verify if the extracted segment has the expected duration
        if abs(actual_duration - duration) > 0.1:
            logging.warning(
                f"Segment duration mismatch: expected {duration}s, got {actual_duration:.2f}s"
            )

        return actual_duration
    except subprocess.CalledProcessError as e:
        logging.error(
            f"Error extracting segment from {input_path}: {e.stderr.decode('utf-8')}"
        )
        raise


def create_transition_segment(
    segment1,
    segment2,
    output_path,
    transition_duration=TRANSITION_DURATION,
    transition_type="fade",
):
    # Get the duration of the first segment to calculate offset.
    dur1 = get_video_duration(segment1)
    if dur1 is None:
        raise ValueError(f"Could not get duration for {segment1}")
    offset = max(dur1 - transition_duration, 0)

    # Use a more detailed filter_complex to ensure video compatibility
    filter_complex = f"[0:v][1:v]xfade=transition={transition_type}:duration={transition_duration}:offset={offset}[vout]"

    # For audio, use a simple crossfade
    audio_filter = f"[0:a][1:a]acrossfade=d={transition_duration}[aout]"

    # Check if both input files have audio
    audio_cmd1 = [
        "ffprobe",
        "-i",
        segment1,
        "-show_streams",
        "-select_streams",
        "a",
        "-loglevel",
        "error",
    ]
    audio_cmd2 = [
        "ffprobe",
        "-i",
        segment2,
        "-show_streams",
        "-select_streams",
        "a",
        "-loglevel",
        "error",
    ]

    has_audio1 = subprocess.run(audio_cmd1, stdout=subprocess.PIPE).stdout != b""
    has_audio2 = subprocess.run(audio_cmd2, stdout=subprocess.PIPE).stdout != b""

    cmd = ["ffmpeg", "-i", segment1, "-i", segment2, "-filter_complex"]

    # Prepare the full filter command based on audio presence
    if has_audio1 and has_audio2:
        cmd.append(f"{filter_complex};{audio_filter}")
        maps = ["-map", "[vout]", "-map", "[aout]"]
    else:
        cmd.append(filter_complex)
        maps = ["-map", "[vout]"]
        if has_audio1:
            maps.extend(["-map", "0:a"])
        elif has_audio2:
            maps.extend(["-map", "1:a"])

    cmd.extend(maps)

    # Add encoding parameters for consistency
    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            "-y",
            output_path,
        ]
    )

    try:
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
        trans_duration = get_video_duration(output_path)
        logging.info(
            f"Created transition segment {os.path.basename(output_path)} "
            f"(type: {transition_type}, duration: {trans_duration:.2f}s)"
        )
    except subprocess.CalledProcessError as e:
        logging.error(
            f"Error creating transition between {segment1} and {segment2}: {e.stderr.decode('utf-8')}"
        )
        raise


def create_video_with_transitions(video_paths, output_path):
    if len(video_paths) < 2:
        raise ValueError("At least two videos are required for transitions.")

    temp_base_dir = "/root/AI-YouTube-Video-Generator/temp/temp"
    if not os.path.exists(temp_base_dir):
        os.makedirs(temp_base_dir, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    temp_dir = os.path.join(temp_base_dir, f"run_{run_id}")
    os.makedirs(temp_dir, exist_ok=True)
    logging.info(f"Using temporary directory: {temp_dir}")

    # Dictionary to store segments for each video
    segments = {}
    for i, video in enumerate(video_paths):
        duration = get_video_duration(video)
        if duration is None:
            raise ValueError(f"Cannot get duration for video: {video}")
        logging.info(f"Processing video {i}: {video} (duration: {duration:.2f}s)")
        segments[i] = {}

        # Calculate dynamic middle duration
        middle_duration = max(duration - START_DURATION - END_DURATION, 0.1)
        logging.info(f"Dynamic middle duration for video {i}: {middle_duration:.2f}s")

        # Extract start segment (first START_DURATION seconds)
        start_path = os.path.join(temp_dir, f"start_{i}.mp4")
        extract_segment(video, start_path, 0, START_DURATION, force_reencode=True)
        segments[i]["start"] = start_path

        # Extract end segment (last END_DURATION seconds)
        end_start = max(duration - END_DURATION, 0)
        end_path = os.path.join(temp_dir, f"end_{i}.mp4")
        extract_segment(video, end_path, end_start, END_DURATION, force_reencode=True)
        segments[i]["end"] = end_path

        # Extract middle segment (dynamic duration starting after START_DURATION)
        middle_start = START_DURATION
        middle_path = os.path.join(temp_dir, f"middle_{i}.mp4")
        actual_middle_duration = extract_segment(
            video, middle_path, middle_start, middle_duration, force_reencode=True
        )
        segments[i]["middle"] = middle_path
        segments[i]["middle_duration"] = actual_middle_duration

        # Validate middle segment duration
        if abs(actual_middle_duration - middle_duration) > 0.3:
            logging.warning(
                f"Middle segment duration mismatch for video {i}: "
                f"expected {middle_duration:.2f}s, got {actual_middle_duration:.2f}s"
            )

    # Create transition segments between adjacent videos
    transitions = {}
    for i in range(len(video_paths) - 1):
        trans_path = os.path.join(temp_dir, f"transition_{i}.mp4")
        # Randomly select a transition type
        trans_types = [
            "fade",
            "fadeblack",
            "fadewhite",
            "distance",
            "smoothleft",
            "smoothright",
            "smoothup",
            "smoothdown",
            "horzclose",
            "horzopen",
            "vertclose",
            "vertopen",
        ]
        selected_trans = random.choice(trans_types)
        create_transition_segment(
            segments[i]["end"],
            segments[i + 1]["start"],
            trans_path,
            TRANSITION_DURATION,
            selected_trans,
        )
        transitions[i] = trans_path

    # Build concatenation order
    concat_order = []
    for i in range(len(video_paths)):
        # For all videos except the first, we use transitions
        if i > 0:
            concat_order.append(transitions[i - 1])  # Transition from previous video

        # For all videos, add the start segment
        if i == 0:  # Only for the first video
            concat_order.append(segments[i]["start"])

        # For all videos, add the middle segment
        concat_order.append(segments[i]["middle"])

        # Only for the last video, add the end segment
        if i == len(video_paths) - 1:
            concat_order.append(segments[i]["end"])

    # Write the list to a file for ffmpeg concat demuxer
    concat_list_path = os.path.join(temp_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for seg in concat_order:
            f.write(f"file '{os.path.abspath(seg)}'\n")

    logging.info("Created ffmpeg concat list file with the following segments:")
    for i, seg in enumerate(concat_order):
        logging.info(f"  {i}: {os.path.basename(seg)}")

    # Concatenate all segments using the concat demuxer
    concat_cmd = [
        "ffmpeg",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_list_path,
        "-c",
        "copy",  # Stream copy since all segments have the same encoding
        "-y",
        output_path,
    ]

    try:
        logging.info("Executing concat command...")
        subprocess.run(concat_cmd, check=True, stderr=subprocess.PIPE)

        # Verify the final output
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            final_duration = get_video_duration(output_path)
            logging.info(
                f"Final output video created: {output_path} (duration: {final_duration:.2f}s)"
            )

            # Log the theoretical duration
            theoretical_duration = sum(get_video_duration(seg) for seg in concat_order)
            logging.info(f"Theoretical total duration: {theoretical_duration:.2f}s")
        else:
            raise ValueError(
                f"Final output video is missing or too small: {output_path}"
            )
    except subprocess.CalledProcessError as e:
        logging.error(
            f"Error concatenating segments: {e.stderr.decode('utf-8') if e.stderr else str(e)}"
        )
        # Try fallback method with re-encoding
        try:
            logging.info(
                "First concat approach failed. Trying fallback method with re-encoding..."
            )
            fallback_cmd = [
                "ffmpeg",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_list_path,
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-y",
                output_path,
            ]
            subprocess.run(fallback_cmd, check=True, stderr=subprocess.PIPE)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                final_duration = get_video_duration(output_path)
                logging.info(
                    f"Fallback method succeeded. Final output: {output_path} (duration: {final_duration:.2f}s)"
                )
            else:
                raise ValueError("Fallback method also failed")
        except Exception as fallback_error:
            logging.error(f"Fallback method also failed: {fallback_error}")
            raise

    logging.info(f"Temporary files retained in: {temp_dir}")
    return temp_dir  # Return temp directory path for inspection


# ------------------------------
# Database (liteSQL) Functions
# ------------------------------
def get_pending_seeds():
    conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT seedId 
            FROM seed 
            WHERE seedTransitionStamp = '0000-00-00 00:00:00' 
            AND seedMixStamp = '0000-00-00 00:00:00'
            AND seedRenderStamp = '0000-00-00 00:00:00'
            AND seedUploadStamp = '0000-00-00 00:00:00'
            ORDER BY seedId ASC
            LIMIT 1
            """
        )
        pending_seed = cursor.fetchone()
        return conn, cursor, pending_seed
    except Exception as e:
        conn.close()
        logging.error(f"Database error in get_pending_seeds: {e}")
        raise


def update_seed_status(conn, cursor, seedId):
    try:
        cursor.execute(
            """
            UPDATE seed 
            SET seedTransitionStamp = datetime('now', 'localtime') 
            WHERE seedId = ?
            """,
            (seedId,),
        )
        conn.commit()
        logging.info(f"Updated seedTransitionStamp for seedId {seedId}")
    except Exception as e:
        logging.error(f"Error updating seed status for seedId {seedId}: {e}")
        raise


# ------------------------------
# Main Processing Function
# ------------------------------
def main():
    try:
        # Get a pending seed from the database.
        conn, cursor, pending_seed = get_pending_seeds()
        if not pending_seed:
            logging.info("No pending seeds to process.")
            conn.close()
            return

        seedId = pending_seed[0]
        videos = []
        # Retrieve all scene/task IDs for this seed.
        cursor.execute("""SELECT DISTINCT taskId FROM task WHERE sceneImageDate != '0000-00-00 00:00:00' 
            AND sceneAudioDate != '0000-00-00 00:00:00' 
            AND sceneClipDate != '0000-00-00 00:00:00' 
            AND sceneSubtitleDate != '0000-00-00 00:00:00' 
            AND seedId = ?
            """, (seedId,))
        pending_scenes = cursor.fetchall()

        for (taskId,) in pending_scenes:
            video_path = f"/root/AI-YouTube-Video-Generator/temp/subtitle/{taskId}/video.mp4"
            if os.path.exists(video_path):
                videos.append(video_path)
            else:
                logging.warning(f"Video file not found: {video_path}")

        if len(videos) < 2:
            logging.error(
                f"Not enough videos found for seedId {seedId}. Found {len(videos)} videos."
            )
            update_seed_status(conn, cursor, seedId)  # Update status even on error.
            conn.close()
            raise ValueError(
                f"At least 2 videos are required, but only {len(videos)} were found"
            )

        output_video = f"/root/AI-YouTube-Video-Generator/temp/video/{seedId}.mp4"

        create_video_with_transitions(video_paths=videos, output_path=output_video)
        # Update seed status after successful processing.
        update_seed_status(conn, cursor, seedId)
    except Exception as e:
        logging.error(f"Main error: {e}")
    finally:
        if "conn" in locals() and conn:
            conn.close()
            logging.info("Database connection closed.")
        logging.info(
            "Script execution completed. Temporary files are retained for inspection."
        )


if __name__ == "__main__":
    main()
