#!/usr/bin/env python3
# Word-Level Subtitles Generator using FFmpeg
# This script converts a video to an audiogram with word-level highlighting using FFmpeg

import os
import json
import subprocess
import whisper
import tempfile
import logging
import shutil
import sqlite3
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/root/AI-YouTube-Video-Generator/logs/subtitle.log"),
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


def extract_audio(taskId):
    """Extract audio from video file using FFmpeg"""
    audio_filename = f"/root/AI-YouTube-Video-Generator/temp/voice/{taskId}/audio.mp3"
    video_filename = f"/root/AI-YouTube-Video-Generator/temp/clip/{taskId}/video.mp4"

    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(audio_filename), exist_ok=True)

    # Extract audio using FFmpeg
    cmd = [
        "ffmpeg",
        "-i",
        video_filename,
        "-vn",
        "-acodec",
        "libmp3lame",
        "-q:a",
        "2",
        audio_filename,
        "-y",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        logging.info(f"Extracted audio to {audio_filename}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error extracting audio: {e.stderr.decode()}")
        raise

    return audio_filename


def transcribe_audio(audio_filename):
    """Get word-level transcription using OpenAI's Whisper"""
    logging.info("Transcribing audio with word-level timestamps...")
    model = whisper.load_model("medium")
    result = model.transcribe(audio_filename, word_timestamps=True)

    # Extract word-level information
    wordlevel_info = []
    for segment in result["segments"]:
        words = segment["words"]
        for word in words:
            wordlevel_info.append(
                {
                    "word": word["word"].strip(),
                    "start": word["start"],
                    "end": word["end"],
                }
            )

    return wordlevel_info


def save_json(data, filename="data.json"):
    """Save data to JSON file"""
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)
    logging.info(f"Saved word-level timestamps to {filename}")


def load_json(filename="data.json"):
    """Load data from JSON file"""
    with open(filename, "r") as f:
        data = json.load(f)
    return data


def split_text_into_lines(data):
    """Convert word-level timestamps to line-level timestamps"""
    logging.info("Converting word-level to line-level timestamps...")

    MaxChars = 80
    # maxduration in seconds
    MaxDuration = 3.0
    # Split if nothing is spoken (gap) for these many seconds
    MaxGap = 1.5

    subtitles = []
    line = []
    line_duration = 0
    line_chars = 0

    for idx, word_data in enumerate(data):
        word = word_data["word"]
        start = word_data["start"]
        end = word_data["end"]

        line.append(word_data)
        line_duration += end - start

        temp = " ".join(item["word"] for item in line)

        # Check if adding a new word exceeds the maximum character count or duration
        new_line_chars = len(temp)

        duration_exceeded = line_duration > MaxDuration
        chars_exceeded = new_line_chars > MaxChars
        if idx > 0:
            gap = word_data["start"] - data[idx - 1]["end"]
            maxgap_exceeded = gap > MaxGap
        else:
            maxgap_exceeded = False

        if duration_exceeded or chars_exceeded or maxgap_exceeded:
            if line:
                subtitle_line = {
                    "word": " ".join(item["word"] for item in line),
                    "start": line[0]["start"],
                    "end": line[-1]["end"],
                    "textcontents": line,
                }
                subtitles.append(subtitle_line)
                line = []
                line_duration = 0
                line_chars = 0

    if line:
        subtitle_line = {
            "word": " ".join(item["word"] for item in line),
            "start": line[0]["start"],
            "end": line[-1]["end"],
            "textcontents": line,
        }
        subtitles.append(subtitle_line)

    return subtitles


def create_srt_file(subtitles, output_srt):
    """
    Convert line-level subtitles to SRT format
    """
    with open(output_srt, "w", encoding="utf-8") as f:
        for i, subtitle in enumerate(subtitles, 1):
            start_time = format_time(subtitle["start"])
            end_time = format_time(subtitle["end"])
            text = subtitle["word"]

            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{text}\n\n")

    logging.info(f"SRT file created: {output_srt}")
    return output_srt


def format_time(seconds):
    """
    Convert seconds to SRT time format (HH:MM:SS,mmm)
    """
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    msecs = int((seconds - int(seconds)) * 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{msecs:03d}"


def create_word_level_subtitle_file(subtitles, output_file):
    """
    Create an ASS subtitle file with word-level highlighting
    """
    with open(output_file, "w", encoding="utf-8") as f:
        # Write ASS header
        f.write("[Script Info]\n")
        f.write("Title: Word-level subtitles\n")
        f.write("ScriptType: v4.00+\n")
        f.write("PlayResX: 1080\n")
        f.write("PlayResY: 1920\n")
        f.write("Timer: 100.0000\n\n")

        # Write styles
        f.write("[V4+ Styles]\n")
        f.write(
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        )
        f.write(
            "Style: Default,Arial,70,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,5,10,10,30,1\n"
        )
        f.write(
            "Style: Highlight,Arial,70,&H00FFFFFF,&H000000FF,&H00000000,&H000000FF,-1,0,0,0,100,100,0,0,1,2,0,5,10,10,30,1\n\n"
        )

        # Write events
        f.write("[Events]\n")
        f.write(
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        # Write each line-level subtitle
        for line in subtitles:
            line_start = format_ass_time(line["start"])
            line_end = format_ass_time(line["end"])

            # Create the full line with default style
            f.write(
                f"Dialogue: 0,{line_start},{line_end},Default,,0,0,0,,{line['word']}\n"
            )

            # For each word, create a highlighted version
            for word_data in line["textcontents"]:
                word_start = format_ass_time(word_data["start"])
                word_end = format_ass_time(word_data["end"])
                word = word_data["word"]

                # Find the position of the word in the line
                line_text = line["word"]
                word_pos = line_text.find(word)

                if word_pos != -1:
                    # Create a modified line where only this word is highlighted
                    pre_text = line_text[:word_pos]
                    post_text = line_text[word_pos + len(word) :]

                    highlighted_text = f"{{\\c&H00FFFF&}}{word}{{\\c&HFFFFFF&}}"
                    full_text = f"{pre_text}{highlighted_text}{post_text}"

                    f.write(
                        f"Dialogue: 1,{word_start},{word_end},Highlight,,0,0,0,,{full_text}\n"
                    )

    logging.info(f"ASS subtitle file created: {output_file}")
    return output_file


def format_ass_time(seconds):
    """
    Convert seconds to ASS time format (H:MM:SS.cc)
    """
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centisecs = int((seconds - int(seconds)) * 100)
    return f"{hrs}:{mins:02d}:{secs:02d}.{centisecs:02d}"


def create_audiogram_ffmpeg(video_filename, subtitle_file, output_filename):
    """
    Create audiogram with burned-in subtitles using FFmpeg
    """
    logging.info("Creating audiogram with FFmpeg...")

    cmd = [
        "ffmpeg",
        "-i",
        video_filename,
        "-vf",
        f"ass={subtitle_file}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "22",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        output_filename,
        "-y",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        logging.info(f"Audiogram created successfully: {output_filename}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error creating audiogram: {e.stderr.decode()}")
        raise

    return output_filename


def main(taskId):
    logging.info(f"Processing taskId: {taskId}")

    # Use fixed local video path
    video_filename = f"/root/AI-YouTube-Video-Generator/temp/clip/{taskId}/video.mp4"
    logging.info(f"Using video file: {video_filename}")

    # Set output paths
    json_path = f"/root/AI-YouTube-Video-Generator/temp/subtitle/{taskId}/data.json"
    subtitle_path = f"/root/AI-YouTube-Video-Generator/temp/subtitle/{taskId}/subtitles.ass"
    output_filename = f"/root/AI-YouTube-Video-Generator/temp/subtitle/{taskId}/video.mp4"

    # Create directories if they don't exist
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    os.makedirs(os.path.dirname(output_filename), exist_ok=True)

    # Step 1: Extract audio from the video file
    audio_filename = extract_audio(taskId)

    # Step 2: Get word-level transcription
    wordlevel_info = transcribe_audio(audio_filename)

    # Step 3: Store word-level timestamps into JSON file
    save_json(wordlevel_info, json_path)

    # Step 4: Load the JSON
    wordlevel_info_modified = load_json(json_path)

    # Step 5: Convert word-level to line-level timestamps
    linelevel_subtitles = split_text_into_lines(wordlevel_info_modified)

    # Step 6: Create ASS subtitle file with word-level highlighting
    create_word_level_subtitle_file(linelevel_subtitles, subtitle_path)

    # Step 7: Create the audiogram with FFmpeg
    create_audiogram_ffmpeg(video_filename, subtitle_path, output_filename)

    try:
        conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE task 
            SET sceneSubtitleDate = datetime('now', 'localtime') 
            WHERE taskId = ?
            """,
            (taskId,),
        )

        conn.commit()
        logging.info(f"Updated task record for taskId: {taskId}")

    except Exception as e:
        logging.error(f"Database error: {e}")
    finally:
        conn.close()

    logging.info(f"Success! Your video has been created: {output_filename}")


if __name__ == "__main__":
    try:
        conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT taskId 
            FROM task 
            WHERE sceneImageDate != '0000-00-00 00:00:00' 
            AND sceneAudioDate != '0000-00-00 00:00:00' 
            AND sceneClipDate != '0000-00-00 00:00:00' 
            AND sceneSubtitleDate = '0000-00-00 00:00:00'
            """
        )

        pending_tasks = cursor.fetchall()

        logging.info(f"Found {len(pending_tasks)} pending tasks")

        for (taskId,) in pending_tasks:
            try:
                main(taskId)
            except Exception as e:
                logging.error(f"Error processing task {taskId}: {str(e)}")
                import traceback

                logging.error(traceback.format_exc())

        conn.close()

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        import traceback

        logging.error(traceback.format_exc())
