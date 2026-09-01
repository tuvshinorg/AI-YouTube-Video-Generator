import sqlite3
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed yet during first bootstrap run

_script_dir = os.path.dirname(os.path.abspath(__file__))
_base_dir   = os.getenv("BASE_DIR") or _script_dir
_db_path    = os.path.join(_base_dir, "main.db")

try:

    # Connecting to sqlite (this will create a new database)
    connection_obj = sqlite3.connect(_db_path)
    print(f"Database: {_db_path}")
    cursor_obj = connection_obj.cursor()

    # Drop existing tables if they exist
    tables = ["QUEUE", "TASK", "SCENE", "SEED"]
    for table in tables:
        cursor_obj.execute(f"DROP TABLE IF EXISTS {table}")

    # Create QUEUE table — entries added manually (Add Text / Import JSON),
    # no automatic fetching from any external source.
    cursor_obj.execute(
        """
        CREATE TABLE QUEUE (
            queueId INTEGER PRIMARY KEY AUTOINCREMENT,
            queueGroup TEXT NOT NULL,
            queueText TEXT NOT NULL,
            queueStamp TIMESTAMP
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
            queueId INT NOT NULL,
            seedPrompt TEXT NOT NULL,
            seedTitle TEXT NOT NULL,
            seedDescription TEXT NOT NULL,
            seedSong TEXT NOT NULL,
            seedCreatedDate TIMESTAMP,
            seedTransitionStamp TIMESTAMP,
            seedMixStamp TIMESTAMP,
            seedRenderStamp TIMESTAMP,
            seedUploadStamp TIMESTAMP,
            seedErrorStep TEXT DEFAULT NULL,
            seedErrorMsg  TEXT DEFAULT NULL
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
