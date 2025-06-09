import sqlite3
import os

try:

    # Connecting to sqlite (this will create a new database)
    connection_obj = sqlite3.connect("main.db")
    cursor_obj = connection_obj.cursor()

    # Drop existing tables if they exist
    tables = ["RSS", "TASK", "SCENE", "SEED"]
    for table in tables:
        cursor_obj.execute(f"DROP TABLE IF EXISTS {table}")

    # Create RSS table
    cursor_obj.execute(
        """
        CREATE TABLE RSS (
            rssId INTEGER PRIMARY KEY AUTOINCREMENT,
            rssGroup TEXT NOT NULL,
            rssText TEXT NOT NULL,
            rssStamp TIMESTAMP
        )
    """
    )

    # Create TASK table
    cursor_obj.execute(
        """
        CREATE TABLE TASK (
            taskId INTEGER PRIMARY KEY AUTOINCREMENT,
            seedId INT NOT NULL,
            sceneNumber INT NOT NULL,
            sceneImageDate TIMESTAMP,
            sceneAudioDate TIMESTAMP,
            sceneClipDate TIMESTAMP,
            sceneSubtitleDate TIMESTAMP
        )
    """
    )

    # Create SCENE table
    cursor_obj.execute(
        """
        CREATE TABLE SCENE (
            sceneId INTEGER PRIMARY KEY AUTOINCREMENT,
            seedId INT NOT NULL,
            sceneNumber INT NOT NULL,
            sceneImage TEXT NOT NULL,
            sceneText TEXT NOT NULL,
            sceneCreatedDate TIMESTAMP
        )
    """
    )

    # Create SEED table
    cursor_obj.execute(
        """
        CREATE TABLE SEED (
            seedId INTEGER PRIMARY KEY AUTOINCREMENT,
            rssId INT NOT NULL,
            seedPrompt TEXT NOT NULL,
            seedTitle TEXT NOT NULL,
            seedDescription TEXT NOT NULL,
            seedSong TEXT NOT NULL,
            seedCreatedDate TIMESTAMP,
            seedTransitionStamp TIMESTAMP,
            seedMixStamp TIMESTAMP,
            seedRenderStamp TIMESTAMP,
            seedUploadStamp TIMESTAMP
        )
    """
    )

    # Commit the changes
    connection_obj.commit()
    print("All tables created successfully")

except sqlite3.DatabaseError as e:
    print(f"Database error: {e}")
finally:
    if "connection_obj" in locals():
        connection_obj.close()
