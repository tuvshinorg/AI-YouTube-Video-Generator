import os
import sqlite3
import requests
import asyncio
import base64
import subprocess
import time
import logging
import warnings

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/root/video/logs/image.log"),
    ],
)


def download_scene_images(seedId):
    # Path to the virtual environment activation script.
    venv_activate = "/root/stable-diffusion-webui-forge/venv/bin/activate"

    # Check if the Stable Diffusion API process is running.
    def is_api_running():
        result = subprocess.run(
            ["pgrep", "-f", "launch.py --api"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.returncode == 0

    # Start the Stable Diffusion process if not running.
    def start_api_process():
        print("Starting Stable Diffusion API process...")
        subprocess.Popen(
            f"source {venv_activate} && python3 /root/stable-diffusion-webui-forge/launch.py --api",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            executable="/bin/bash",  # Ensure the command runs in a bash shell for `source`
        )

    # Ensure the Stable Diffusion API is running.
    if not is_api_running():
        start_api_process()
        print("Waiting for Stable Diffusion API to start...")
        time.sleep(60)

    conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT taskId, sceneNumber FROM task WHERE sceneImageDate = '0000-00-00 00:00:00' AND seedId = ?",
        (seedId,),
    )
    results = cursor.fetchall()

    for result in results:
        taskId, sceneNumber = result
        cursor.execute(
            "SELECT sceneId, sceneImage FROM scene WHERE seedId = ? AND sceneNumber = ?",
            (seedId, sceneNumber),
        )
        scene_data = cursor.fetchone()

        if scene_data:
            sceneId, sceneImage = scene_data

            try:
                subprocess.run(["service", "ollama", "stop"], check=True)
                print("All 'ollama' processes have been terminated.")
            except subprocess.CalledProcessError:
                print("No 'ollama' processes found or an error occurred.")

            directory = f"/root/AI-YouTube-Video-Generator/temp/image/{sceneId}"
            os.makedirs(directory, exist_ok=True)

            # Construct payload for the Stable Diffusion Web UI API
            payload = {
                "prompt": sceneImage,
                "negative_prompt": "nsfw, blurry, low quality, low resolution, cropped, deformed, disfigured, poorly drawn, bad anatomy, wrong anatomy, extra limbs, missing limbs, floating limbs, disconnected limbs, mutation, mutated, ugly, disgusting, amputee, grain, grainy, noisy, jpeg artifacts, watermarks, text, typography, out of frame, cut off, duplicate, error, mutant, poorly rendered, rendering artifacts, poorly rendered hands, poorly rendered face, duplicate heads, poorly rendered fingers, poorly rendered limbs, multiple heads, multiple bodies, too many fingers, fused fingers, bad hands, signature, username, artist name",
                "override_settings": {
                    "sd_model_checkpoint": "fluxmania_V.safetensors",
                    "forge_preset": "flux",
                },
                "override_settings_restore_afterwards": False,
                "steps": 20,
                "width": 540,
                "height": 960,
                "seed": -1,
                "subseed": -1,
                "subseed_strength": 0,
                "seed_resize_from_h": -1,
                "seed_resize_from_w": -1,
                "sampler_name": "Euler",
                "scheduler": "Simple",
                "batch_size": 1,
                "n_iter": 1,
                "cfg_scale": 1,
                "distilled_cfg_scale": 3.5,
                "sampler_index": "Euler",
            }

            try:
                response = requests.post(
                    "http://127.0.0.1:7860/sdapi/v1/txt2img", json=payload
                )

                if response.status_code == 200:
                    result_json = response.json()
                    if "images" in result_json and len(result_json["images"]) > 0:
                        # The images are returned as base64-encoded strings
                        img_data = result_json["images"][0]

                        # Some versions return a data URL. If that’s the case, strip it:
                        if img_data.startswith("data:image"):
                            img_data = img_data.split(",", 1)[1]

                        img_binary = base64.b64decode(img_data)

                        image_path = os.path.join(directory, "image.png")
                        with open(image_path, "wb") as f:
                            f.write(img_binary)

                        # Update the sceneImageDownloadDate for the task
                        cursor.execute(
                            "UPDATE task SET sceneImageDate = datetime('now', 'localtime') WHERE taskId = ?",
                            (taskId,),
                        )
                        logging.info(f"Fetched {len(response.json())} response")
                        conn.commit()
                    else:
                        print(
                            f"No images returned by the Stable Diffusion API for scene {sceneId}."
                        )
                else:
                    print(
                        f"Error generating image for scene {sceneId}: {response.text}"
                    )

            except Exception as e:
                print(f"Error in image generation process: {str(e)}")
                continue

    conn.close()


# download_scene_images()
if __name__ == "__main__":
    try:
        conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT seedId 
            FROM task 
            WHERE sceneImageDate = '0000-00-00 00:00:00' 
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
                download_scene_images(seedId)
            except Exception as e:
                print(f"Error processing seed {seedId}: {str(e)}")

    except Exception as e:
        print(f"Main error: {str(e)}")
    finally:
        conn.close()
