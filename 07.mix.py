import os
import subprocess
import shlex
import sqlite3
import logging
import shutil
import re

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/root/yikes/logs/mix.log"),
    ],
)


def process_audio(seedId):
    # Define file paths
    video_file = f"/root/yikes/temp/video/{seedId}.mp4"
    audio_file = f"/root/yikes/temp/audio/{seedId}.wav"
    
    # Define seedId-specific mix folder
    mix_folder = f"/root/yikes/temp/mix/{seedId}"
    
    # Check if the seedId mix folder exists, if so remove it
    if os.path.exists(mix_folder):
        try:
            shutil.rmtree(mix_folder)
            logging.info(f"Removed existing mix folder: {mix_folder}")
        except Exception as e:
            logging.error(f"Error removing mix folder {mix_folder}: {str(e)}")
    
    # Create the seedId mix folder
    try:
        os.makedirs(mix_folder, exist_ok=True)
        logging.info(f"Created mix folder: {mix_folder}")
    except Exception as e:
        logging.error(f"Error creating mix folder {mix_folder}: {str(e)}")
        raise
    
    # Files to remove before starting
    files_to_remove = [
        f"/root/yikes/temp/mix/{seedId}.wav",
        f"/root/yikes/temp/audio/{seedId}.wav",
    ]

    # Remove existing output files before starting
    for file_path in files_to_remove:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"Removed existing file: {file_path}")
        except Exception as e:
            logging.error(f"Error removing file {file_path}: {str(e)}")

    try:
        # Ensure audio directory exists
        os.makedirs(os.path.dirname(audio_file), exist_ok=True)

        # Get the exact duration of the video
        logging.info(f"Getting exact duration of video: {video_file}")
        video_duration_cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \"{video_file}\""
        video_duration = float(
            subprocess.check_output(shlex.split(video_duration_cmd), text=True).strip()
        )
        logging.info(f"Video duration: {video_duration} seconds")

        # Convert video to audio using a direct and reliable method that enforces exact duration
        logging.info(
            f"Converting video to audio with guaranteed exact duration: {video_file} -> {audio_file}"
        )

        # Using a more complex filter chain to ensure exact duration
        ffmpeg_extract_cmd = [
            "ffmpeg", 
            "-i", video_file, 
            "-af", f"aresample=async=1000, apad=pad_dur={video_duration}", 
            "-to", str(video_duration), 
            "-c:a", "pcm_s16le", 
            audio_file
        ]

        subprocess.run(ffmpeg_extract_cmd, check=True)

        # Verify the output duration
        audio_duration_cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \"{audio_file}\""
        audio_duration = float(
            subprocess.check_output(shlex.split(audio_duration_cmd), text=True).strip()
        )
        logging.info(
            f"Verified output audio duration: {audio_duration} seconds (should match video duration: {video_duration} seconds)"
        )

        # If there's still a discrepancy, log a warning
        if abs(audio_duration - video_duration) > 0.1:  # Allow 0.1 second tolerance
            logging.warning(
                f"Audio duration still doesn't match video duration! Difference: {abs(audio_duration - video_duration)} seconds"
            )
        logging.info(f"Video to audio conversion completed: {audio_file}")

        # Get the seed song from the database
        try:
            conn = sqlite3.connect("/root/yikes/main.db")
            cursor = conn.cursor()

            # Try to get the seedSong path
            cursor.execute(
                """
                SELECT DISTINCT seedSong 
                FROM seed 
                WHERE seedId = ?
                """,
                (seedId,),
            )
            pending_seeds = cursor.fetchone()
            conn.close()

            if not pending_seeds or not pending_seeds[0]:
                logging.error(f"No seedSong found for seedId {seedId}")
                raise ValueError(f"No seedSong found for seedId {seedId}")

            # Clean up the seedSong path
            seedSong = pending_seeds[0].strip()
            logging.info(f"Raw seedSong from DB: {seedSong}")
            
            # Check for path issues seen in the error log
            if not os.path.exists(seedSong):
                # Try to find a random mp3 file in the calm directory
                calm_dir = "/root/yikes/song/calm/"
                
                # Make sure the directory exists
                if not os.path.exists(calm_dir):
                    try:
                        os.makedirs(calm_dir, exist_ok=True)
                        logging.info(f"Created calm directory: {calm_dir}")
                    except Exception as e:
                        logging.error(f"Error creating calm directory: {str(e)}")
                
                # Get a list of mp3 files in the directory
                mp3_files = []
                if os.path.exists(calm_dir):
                    mp3_files = [os.path.join(calm_dir, f) for f in os.listdir(calm_dir) 
                                if f.lower().endswith('.mp3')]
                
                if mp3_files:
                    # Choose a random mp3 file
                    import random
                    random_mp3 = random.choice(mp3_files)
                    logging.warning(f"Original seedSong not found. Using random calm song: {random_mp3}")
                    seedSong = random_mp3
                else:
                    # Try to find a default seed song
                    default_seed_path = "/root/yikes/song/default.wav"
                    if os.path.exists(default_seed_path):
                        logging.warning(f"Using default seed song: {default_seed_path}")
                        seedSong = default_seed_path
                    else:
                        raise FileNotFoundError(f"seedSong file does not exist and no calm songs or defaults found")
                
        except Exception as e:
            logging.error(f"Error getting seedSong: {str(e)}")
            raise

        # Define temporary files in the seedId folder
        normalized_input = f"{mix_folder}/normalized_input.wav"
        normalized_loop = f"{mix_folder}/normalized_loop.wav"
        mixed_echo = f"{mix_folder}/mixed_echo.wav"
        final_output = f"{mix_folder}/{seedId}.wav"

        # Step 1: First normalization of the input audio
        logging.info(f"Normalizing input audio: {audio_file} to {normalized_input}")
        subprocess.run([
            "ffmpeg-normalize", 
            audio_file, 
            "-c:a", "pcm_s16le", 
            "--normalization-type", "rms", 
            "--target-level", "-18", 
            "-o", normalized_input
        ], check=True)

        # Step 1: First normalization of seedSong
        logging.info(f"Normalizing seedSong: {seedSong} to {normalized_loop}")
        try:
            subprocess.run([
                "ffmpeg-normalize", 
                seedSong, 
                "-c:a", "pcm_s16le", 
                "--normalization-type", "rms", 
                "--target-level", "-23", 
                "-o", normalized_loop
            ], check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error normalizing seedSong: {str(e)}")
            raise

        # Verify that normalized files exist
        if not os.path.exists(normalized_input):
            raise FileNotFoundError(f"Normalized input file does not exist: {normalized_input}")
            
        if not os.path.exists(normalized_loop):
            raise FileNotFoundError(f"Normalized loop file does not exist: {normalized_loop}")

        # Step 2: Mix with looped background and add echo
        logging.info(f"Mixing audio files: {normalized_input} and {normalized_loop}")
        
        # Build the complex ffmpeg command
        ffmpeg_cmd = [
            "ffmpeg", 
            "-i", normalized_input, 
            "-stream_loop", "-1", 
            "-i", normalized_loop,
            "-filter_complex",
            "[0:a]equalizer=f=100:width_type=o:width=2:g=6,equalizer=f=1000:width_type=o:width=2:g=-2,equalizer=f=5000:width_type=o:width=2:g=-1[aeq1]; [1:a]equalizer=f=100:width_type=o:width=2:g=6,equalizer=f=1000:width_type=o:width=2:g=4,equalizer=f=5000:width_type=o:width=2:g=4[aeq2]; [aeq1]aecho=0.5:0.6:30:0.05[aecho]; [aeq2]volume=0.03[bg]; [aecho][bg]amix=inputs=2:duration=shortest[aout]",
            "-map", "[aout]", 
            "-c:a", "pcm_s16le", 
            mixed_echo
        ]
        
        try:
            subprocess.run(ffmpeg_cmd, check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error running ffmpeg mixing command: {str(e)}")
            raise

        # Step 3: Final normalization
        logging.info(f"Performing final normalization: {mixed_echo} to {final_output}")
        subprocess.run([
            "ffmpeg-normalize", 
            mixed_echo, 
            "-c:a", "pcm_s16le", 
            "--normalization-type", "rms", 
            "--target-level", "-18", 
            "-o", final_output
        ], check=True)
        
        # Copy the final output to the standard location
        shutil.copy(final_output, f"/root/yikes/temp/mix/{seedId}.wav")
        logging.info(f"Copied final output to standard location: /root/yikes/temp/mix/{seedId}.wav")

        print(f"Processing completed successfully. Output: {seedId}.wav")

        try:
            conn = sqlite3.connect("/root/yikes/main.db")
            cursor = conn.cursor()

            cursor.execute(
                """
                    UPDATE seed 
                    SET seedMixStamp = datetime('now', 'localtime') 
                    WHERE seedId = ?
                """,
                (seedId,),
            )

            conn.commit()
            logging.info(f"Updated seedMixStamp for seedId {seedId}")

        except Exception as e:
            logging.error(f"Error updating database: {str(e)}")
        finally:
            conn.close()

    except subprocess.CalledProcessError as e:
        logging.error(f"Error processing audio: {str(e)}")
        print(f"Error processing audio: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        print(f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    try:
        conn = sqlite3.connect("/root/yikes/main.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT seedId 
            FROM seed 
            WHERE seedTransitionStamp != '0000-00-00 00:00:00' 
            AND seedMixStamp = '0000-00-00 00:00:00'
            AND seedRenderStamp = '0000-00-00 00:00:00'
            AND seedUploadStamp = '0000-00-00 00:00:00'
            """
        )
        pending_seeds = cursor.fetchone()
        
        if not pending_seeds:
            logging.warning("No pending seeds found for processing")
            print("No pending seeds found for processing")
            exit(0)
            
        seedId = pending_seeds[0]
        conn.close()
        
        logging.info(f"Processing seedId: {seedId}")
        process_audio(seedId)
        
    except Exception as e:
        logging.error(f"Unexpected error in main: {str(e)}")
        print(f"Unexpected error in main: {str(e)}")