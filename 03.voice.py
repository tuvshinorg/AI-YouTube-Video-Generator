import os
import sqlite3
import requests
import edge_tts
import subprocess
import logging
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/root/yikes/logs/voice.log"),
    ],
)


async def make_text_to_audio(seedId):
    conn = sqlite3.connect("/root/yikes/main.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT taskId, sceneNumber 
        FROM task 
        WHERE sceneImageDate != '0000-00-00 00:00:00' 
        AND sceneAudioDate = '0000-00-00 00:00:00' 
        AND seedId = ?
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
        print(f"Error processing seed {seedId}: {str(e)}")

    try:
        # Use pkill to find and kill the process by command pattern
        subprocess.run(
            ["pkill", "-f", "stable-diffusion-webui-forge/launch.py"], check=False
        )
        print("Stable Diffusion API process terminated")
    except Exception as e:
        print(f"Error killing Stable Diffusion API process: {e}")

    # Use a female English voice
    communicate = edge_tts.Communicate("Hello World", "en-US-AvaNeural")

    for result in results:
        taskId, sceneNumber = result

        cursor.execute(
            """
            SELECT sceneId, sceneText 
            FROM scene 
            WHERE seedId = ? AND sceneNumber = ?
        """,
            (seedId, sceneNumber),
        )
        scene_result = cursor.fetchone()

        if scene_result:
            sceneId, sceneText = scene_result

            directory = f"/root/yikes/temp/voice/{sceneId}"
            os.makedirs(directory, exist_ok=True)

            audio_path = os.path.join(directory, "audio.mp3")
            communicate = edge_tts.Communicate(sceneText, "en-US-AvaNeural")
            await communicate.save(audio_path)

            cursor.execute(
                """
                UPDATE task 
                SET sceneAudioDate = datetime('now', 'localtime') 
                WHERE taskId = ?
            """,
                (taskId,),
            )
            conn.commit()

    conn.close()

    # download_scene_images()


if __name__ == "__main__":
    try:
        conn = sqlite3.connect("/root/yikes/main.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT seedId 
            FROM task 
            WHERE sceneImageDate != '0000-00-00 00:00:00' 
            AND sceneAudioDate = '0000-00-00 00:00:00' 
            AND sceneClipDate = '0000-00-00 00:00:00' 
            AND sceneSubtitleDate = '0000-00-00 00:00:00'
        """
        )
        pending_seeds = cursor.fetchall()
        print(f"Found {len(pending_seeds)} pending seeds")

        for (seedId,) in pending_seeds:
            try:
                print(f"Processing seedId: {seedId}")
                asyncio.run(make_text_to_audio(seedId))
            except Exception as e:
                print(f"Error processing seed {seedId}: {str(e)}")

    except Exception as e:
        print(f"Main error: {str(e)}")
    finally:
        conn.close()
