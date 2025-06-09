#!/usr/bin/env python3
import sqlite3
import os
import shutil
import sys

def cleanup_temp_files():
    try:
        # Connect to the database
        conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
        cursor = conn.cursor()
        
        # Find all seeds that have been uploaded
        cursor.execute("""
            SELECT s.seedId, t.taskId 
            FROM SEED s
            LEFT JOIN TASK t ON s.seedId = t.seedId
            WHERE s.seedUploadStamp != '0000-00-00 00:00:00'
        """)
        
        completed_items = cursor.fetchall()
        
        if not completed_items:
            print("No completed uploads found to clean up.")
            return
        
        # Counter for tracking deleted items
        deleted_count = 0
        
        # Process each completed seed and its associated tasks
        for seed_id, task_id in completed_items:
            paths_to_remove = [
                f"/root/AI-YouTube-Video-Generator/temp/audio/{seed_id}.wav",
                f"/root/AI-YouTube-Video-Generator/temp/video/{seed_id}.mp4",
                f"/root/AI-YouTube-Video-Generator/temp/mix/{seed_id}.wav",
                f"/root/AI-YouTube-Video-Generator/temp/mix/{seed_id}",
                f"/root/AI-YouTube-Video-Generator/temp/image/{seed_id}"
            ]
            
            # Add task-specific paths if task_id is not None
            if task_id is not None:
                task_paths = [
                    f"/root/AI-YouTube-Video-Generator/temp/clip/{task_id}",
                    f"/root/AI-YouTube-Video-Generator/temp/image/{task_id}",
                    f"/root/AI-YouTube-Video-Generator/temp/subtitle/{task_id}",
                    f"/root/AI-YouTube-Video-Generator/temp/audio/{task_id}",
                    f"/root/AI-YouTube-Video-Generator/temp/voice/{task_id}"
                ]
                paths_to_remove.extend(task_paths)
            
            # Remove each path
            for path in paths_to_remove:
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                        print(f"Removed file: {path}")
                        deleted_count += 1
                    elif os.path.isdir(path):
                        shutil.rmtree(path)
                        print(f"Removed directory: {path}")
                        deleted_count += 1
                except Exception as e:
                    print(f"Error removing {path}: {e}")
        
        # Clean up the entire temp/temp directory
        temp_temp_dir = "/root/AI-YouTube-Video-Generator/temp/temp/"
        try:
            if os.path.exists(temp_temp_dir):
                # Remove all files in the directory
                for item in os.listdir(temp_temp_dir):
                    item_path = os.path.join(temp_temp_dir, item)
                    try:
                        if os.path.isfile(item_path):
                            os.remove(item_path)
                            print(f"Removed file: {item_path}")
                            deleted_count += 1
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                            print(f"Removed directory: {item_path}")
                            deleted_count += 1
                    except Exception as e:
                        print(f"Error removing {item_path}: {e}")
        except Exception as e:
            print(f"Error cleaning temp/temp directory: {e}")
        
        print(f"Cleanup complete. Removed {deleted_count} items.")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("Starting cleanup process...")
    cleanup_temp_files()