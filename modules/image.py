from .config import *


def image_generate_for_seed(seed_id: int):
    """Generate one PNG per scene that hasn't been imaged yet, using Flux."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT taskId, sceneNumber FROM task "
        "WHERE sceneImageDate='0000-00-00 00:00:00' AND seedId=?",
        (seed_id,),
    )
    tasks = cursor.fetchall()

    if not tasks:
        conn.close()
        return

    pipe = _get_flux_pipe()

    for task_id, scene_number in tasks:
        cursor.execute(
            "SELECT sceneId, sceneImage FROM scene WHERE seedId=? AND sceneNumber=?",
            (seed_id, scene_number),
        )
        row = cursor.fetchone()
        if not row:
            continue
        scene_id, scene_image_prompt = row

        out_dir = f"{BASE_DIR}/temp/image/{scene_id}"
        os.makedirs(out_dir, exist_ok=True)
        image_path = os.path.join(out_dir, "image.png")

        full_prompt = scene_image_prompt
        # Append negative guidance as a separate "negative" token block if supported;
        # Flux is a guidance-distilled model – negative prompt has no official channel,
        # so we append style cues to the positive prompt instead.
        full_prompt += f", high quality, sharp, professional photography, cinematic"

        log.info(f"[image] Generating scene {scene_number} (task {task_id}): {scene_image_prompt[:80]}…")
        try:
            import torch
            result = pipe(
                prompt=full_prompt,
                height=FLUX_HEIGHT,
                width=FLUX_WIDTH,
                num_inference_steps=FLUX_STEPS,
                guidance_scale=FLUX_GUIDANCE,
                generator=torch.Generator().manual_seed(random.randint(0, 2**32 - 1)),
            )
            image = result.images[0]
            image.save(image_path)
            log.info(f"[image] Saved: {image_path}")

            cursor.execute(
                "UPDATE task SET sceneImageDate=datetime('now','localtime') WHERE taskId=?",
                (task_id,),
            )
            conn.commit()
        except Exception as e:
            log.error(f"[image] Generation failed for taskId {task_id}: {e}")

    conn.close()


def run_image():
    """Run the Image module for all pending seeds."""
    log.info("═══ MODULE: IMAGE ═══")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT DISTINCT seedId FROM task
           WHERE sceneImageDate='0000-00-00 00:00:00'
           AND sceneAudioDate='0000-00-00 00:00:00'
           AND sceneClipDate='0000-00-00 00:00:00'
           AND sceneSubtitleDate='0000-00-00 00:00:00'"""
    )
    seeds = cursor.fetchall()
    conn.close()
    log.info(f"[image] {len(seeds)} pending seeds")
    for (seed_id,) in seeds:
        try:
            image_generate_for_seed(seed_id)
        except Exception as e:
            log.error(f"[image] Seed {seed_id} failed: {e}")
