from .config import *

import httplib2
from googleapiclient import discovery
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import run_flow


def _yt_credentials():
    storage = Storage(CREDENTIALS_STORAGE)
    creds = storage.get()
    if not creds or creds.invalid:
        flow = flow_from_clientsecrets(
            CLIENT_SECRET_FILE, scope=YOUTUBE_SCOPES,
            message="MISSING_CLIENT_SECRET_FILE",
        )
        flags = argparse.Namespace(
            noauth_local_webserver=True, logging_level="ERROR",
            auth_host_name="localhost", auth_host_port=[8080, 8090],
        )
        creds = run_flow(flow, storage, flags=flags, http=httplib2.Http())
    if creds.access_token_expired:
        creds.refresh(httplib2.Http())
        storage.put(creds)
    return creds


def _yt_service():
    creds = _yt_credentials()
    http  = creds.authorize(httplib2.Http(timeout=30))
    return discovery.build("youtube", "v3", http=http, cache_discovery=False)


def upload_video_to_youtube(file_path: str, title: str, description: str = "") -> str | None:
    title = (title or "short").strip()[:100]
    yt = _yt_service()
    body = {
        "snippet": {"title": title, "description": description,
                    "tags": [], "categoryId": "22"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response, retry = None, 0
    while response is None and retry < 3:
        try:
            status, response = request.next_chunk()
            if status:
                log.info(f"[upload] {int(status.progress()*100)}%")
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                retry += 1; time.sleep(5 * retry)
            else:
                raise
    if response:
        vid_id = response["id"]
        log.info(f"[upload] Done: https://www.youtube.com/watch?v={vid_id}")
        return vid_id
    return None


def run_upload():
    """Upload one ready video to YouTube."""
    log.info("═══ MODULE: UPLOAD ═══")
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        """SELECT seedId, seedTitle, seedDescription FROM seed
           WHERE seedTransitionStamp!='0000-00-00 00:00:00'
           AND seedMixStamp!='0000-00-00 00:00:00'
           AND seedRenderStamp!='0000-00-00 00:00:00'
           AND seedUploadStamp='0000-00-00 00:00:00'
           LIMIT 1"""
    ).fetchone()
    conn.close()
    if not row:
        log.info("[upload] No videos ready to upload")
        return
    seed_id, title, description = row
    video_path = f"{BASE_DIR}/final/{seed_id}.mp4"
    if not os.path.exists(video_path):
        log.error(f"[upload] File not found: {video_path}")
        return
    vid_id = upload_video_to_youtube(video_path, title, description)
    if vid_id:
        conn2 = sqlite3.connect(DB_PATH)
        conn2.execute(
            "UPDATE seed SET seedUploadStamp=CURRENT_TIMESTAMP WHERE seedId=?",
            (seed_id,),
        )
        conn2.commit()
        conn2.close()
