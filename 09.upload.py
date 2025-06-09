import sqlite3
import os
import logging
import httplib2
import argparse
import sys
import time
import shutil
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import run_flow
from googleapiclient import discovery
from datetime import datetime, timedelta

# Configuration constants
CLIENT_SECRET_FILE = "/root/AI-YouTube-Video-Generator/client_secret.json"
CREDENTIALS_STORAGE = "/root/AI-YouTube-Video-Generator/credentials.storage"
DATABASE_PATH = "/root/AI-YouTube-Video-Generator/main.db"
BASE_VIDEO_PATH = "/root/AI-YouTube-Video-Generator/final"
SCOPES = ["https://www.googleapis.com/auth/youtube"]
LOG_FILE = "/root/AI-YouTube-Video-Generator/logs/upload.log"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)],
)
logger = logging.getLogger(__name__)


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


def handle_exception(exc_type, exc_value, exc_traceback):
    """Handle uncaught exceptions"""
    logger.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = handle_exception


def authorize_credentials():
    """Authorize and refresh credentials with enhanced error handling"""
    try:
        storage = Storage(CREDENTIALS_STORAGE)
        credentials = storage.get()

        if not credentials or credentials.invalid:
            logger.info("No valid credentials found, initiating OAuth flow")
            flow = flow_from_clientsecrets(
                CLIENT_SECRET_FILE, scope=SCOPES, message="MISSING_CLIENT_SECRET_FILE"
            )
            flags = argparse.Namespace(
                noauth_local_webserver=True,
                logging_level="ERROR",
                auth_host_name="localhost",
                auth_host_port=[8080, 8090],
            )
            credentials = run_flow(flow, storage, flags=flags, http=httplib2.Http())

        # Proactive token refresh if expiring within 1 hour
        if credentials.access_token_expired:
            logger.info("Access token expired, refreshing...")
            credentials.refresh(httplib2.Http())
            storage.put(credentials)
            logger.info("Token refreshed successfully")

        return credentials
    except Exception as e:
        logger.error(f"Authorization failed: {str(e)}")
        raise


def get_youtube_service():
    """Build YouTube service with connection pooling"""
    credentials = authorize_credentials()
    http = credentials.authorize(
        httplib2.Http(cache=None, timeout=30, disable_ssl_certificate_validation=False)
    )
    return discovery.build("youtube", "v3", http=http, cache_discovery=False)


def upload_video(file_path, title, description=""):
    """Robust video upload with retry logic"""
    # Validate title
    if not title or not title.strip():
        title = 'short'

    # Trim title to YouTube's limit (100 characters)
    if len(title) > 100:
        logger.warning(f"Title too long, trimming to 100 characters")
        title = title[:100]

    try:
        youtube = get_youtube_service()

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": [],
                "categoryId": "22",
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        }

        media = MediaFileUpload(
            file_path, chunksize=-1, resumable=True, mimetype="video/mp4"
        )

        request = youtube.videos().insert(
            part="snippet,status", body=body, media_body=media
        )

        response = None
        retry = 0
        while response is None and retry < 3:
            try:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Upload progress: {int(status.progress() * 100)}%")
            except HttpError as e:
                if e.resp.status in [500, 502, 503, 504]:
                    logger.warning(f"Upload error ({e}), retrying...")
                    retry += 1
                    time.sleep(5 * retry)
                else:
                    raise

        if response:
            logger.info(
                f"Upload complete: https://www.youtube.com/watch?v={response['id']}"
            )
            return response["id"]
        return None

    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        return None


def process_single_video():
    """Process one eligible video at a time from the database."""
    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT seedId, seedTitle, seedDescription 
                FROM seed
                WHERE seedTransitionStamp != '0000-00-00 00:00:00' 
                AND seedMixStamp != '0000-00-00 00:00:00'
                AND seedRenderStamp != '0000-00-00 00:00:00'
                AND seedUploadStamp = '0000-00-00 00:00:00'
                LIMIT 1
            """
            )

            seed = cursor.fetchone()
            if not seed:
                logger.info("No videos found for upload")
                return False

            seed_id, title, description = seed
            video_path = f"{BASE_VIDEO_PATH}/{seed_id}.mp4"

            if not os.path.exists(video_path):
                logger.warning(f"Video file not found for seedId: {seed_id}")
                return False

            logger.info(f"Processing upload for seedId: {seed_id}")
            logger.info(f"Video title: {title}")
            logger.info(f"Video description: {description}")

            if upload_video(video_path, title, description):
                cursor.execute(
                    """
                    UPDATE seed 
                    SET seedUploadStamp = CURRENT_TIMESTAMP 
                    WHERE seedId = ?
                """,
                    (seed_id,),
                )
                conn.commit()
                logger.info(f"Database updated for seedId: {seed_id}")
                return True

            return False

    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")

    return False


def force_token_refresh():
    """Explicit token refresh for cron jobs"""
    try:
        logger.info("Initiating proactive token refresh")
        get_youtube_service()
        logger.info("Token refresh successful")
        return True
    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube Upload Manager")
    parser.add_argument(
        "--refresh-only", action="store_true", help="Only refresh authentication tokens"
    )
    args = parser.parse_args()

    if args.refresh_only:
        force_token_refresh()
    else:
        process_single_video()

    # cleanup_temp_directory("/root/AI-YouTube-Video-Generator/temp/mix/")
    # cleanup_temp_directory("/root/AI-YouTube-Video-Generator/temp/temp/")
    # cleanup_temp_directory("/root/AI-YouTube-Video-Generator/temp/final/")
    # cleanup_temp_directory("/root/AI-YouTube-Video-Generator/temp/video/")
    # cleanup_temp_directory("/root/AI-YouTube-Video-Generator/temp/audio/")
    # cleanup_temp_directory("/root/AI-YouTube-Video-Generator/temp/voice/")
    # cleanup_temp_directory("/root/AI-YouTube-Video-Generator/temp/image/")
    # cleanup_temp_directory("/root/AI-YouTube-Video-Generator/temp/clip/")
    # cleanup_temp_directory("/root/AI-YouTube-Video-Generator/temp/subtitle/")
