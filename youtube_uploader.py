import os
import json
import logging
from datetime import datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.exceptions import TransportError
import config

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def get_authenticated_service(token_info=None, token_path=None):
    creds = None
    
    # Resolve the token path to save refreshed/new credentials
    target_token_path = token_path or config.get_token_file()
    
    # 1. Try to load from provided token_info dict
    if token_info and isinstance(token_info, dict):
        try:
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        except Exception as e:
            logging.error(f"[!] Error building credentials from token_info dict: {e}")
            
    # 2. Try to load from channel token file path if dict load failed or wasn't provided
    if not creds:
        if os.path.exists(target_token_path):
            try:
                creds = Credentials.from_authorized_user_file(target_token_path, SCOPES)
            except Exception as e:
                logging.error(f"[!] Error reading authorized user file {target_token_path}: {e}")
        elif os.path.exists('token.json'):
            # Backward compatibility fallback
            try:
                creds = Credentials.from_authorized_user_file('token.json', SCOPES)
                target_token_path = 'token.json'
            except Exception as e:
                logging.error(f"[!] Error reading fallback token.json: {e}")

    # 3. Refresh or authenticate via flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logging.info("[*] Refreshing expired YouTube credentials...")
                creds.refresh(Request())
                logging.info("[+] YouTube credentials refreshed successfully!")
            except TransportError as te:
                logging.error(f"[!] Network connection error during token refresh: {te}")
                raise te
            except Exception as e:
                logging.error(f"[!] Failed to refresh credentials: {e}. Falling back to InstalledAppFlow.")
                creds = None
                
        if not creds:
            logging.error("[!] No valid credentials or refresh token available. Attempting InstalledAppFlow login.")
            flow = InstalledAppFlow.from_client_secrets_file(config.CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Ensure parent directory exists for token path
        parent_dir = os.path.dirname(os.path.abspath(target_token_path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
            
        with open(target_token_path, 'w', encoding='utf-8') as token:
            token.write(creds.to_json())
            
    return build('youtube', 'v3', credentials=creds)

def get_upload_count_today():
    log_file = config.get_upload_log_file()
    if not os.path.exists(log_file):
        return 0
    with open(log_file, 'r', encoding='utf-8') as f:
        try:
            logs = json.load(f)
            today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            return sum(1 for log in logs if log.get('date') == today)
        except json.JSONDecodeError:
            return 0

def log_upload(video_id):
    log_file = config.get_upload_log_file()
    logs = []
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            try:
                logs = json.load(f)
            except:
                pass
                
    logs.append({
        'video_id': video_id,
        'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'time': datetime.now(timezone.utc).isoformat()
    })
    
    # Ensure parent dir exists
    parent_dir = os.path.dirname(os.path.abspath(log_file))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
        
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=4)

def _upload(video_path, metadata, schedule_time=None, token_info=None, token_path=None, is_short=True):
    """
    Uploads a video to YouTube via OAuth2.
    If schedule_time is provided, sets privacyStatus to 'private' and publishAt to future ISO 8601 UTC timestamp.
    is_short=True appends #shorts to the title/description (Shorts uploads);
    is_short=False uploads a regular long-form video without #shorts.
    """
    content_kind = "Short" if is_short else "video"
    logging.info(f"[*] Uploading {video_path} to YouTube {content_kind}...")
    youtube = get_authenticated_service(token_info=token_info, token_path=token_path)

    tags = [t.strip() for t in metadata['tags'].split(',')] if isinstance(metadata['tags'], str) else metadata['tags']
    description = metadata['description'] + "\n\n" + " ".join(metadata['hashtags'])
    if is_short and "#shorts" not in description.lower():
        description += " #shorts"

    title = metadata['title']
    if is_short:
        if "#shorts" not in title.lower():
            title = f"{title[:75]} #shorts"
    else:
        title = title[:100]

    status_payload = {
        'privacyStatus': 'public',
        'selfDeclaredMadeForKids': False
    }

    if schedule_time:
        # Explicit ISO 8601 formatting required by YouTube API: YYYY-MM-DDTHH:MM:SS.000Z
        formatted_publish_time = schedule_time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        status_payload['privacyStatus'] = 'private'
        status_payload['publishAt'] = formatted_publish_time
        logging.info(f"[*] Scheduling YouTube Video Status Payload: {json.dumps(status_payload)}")

    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags,
            'categoryId': '20' # Gaming
        },
        'status': status_payload
    }

    media = MediaFileUpload(video_path, mimetype='video/mp4', resumable=True)
    
    request = youtube.videos().insert(
        part='snippet,status',
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logging.info(f"[-] Uploaded {int(status.progress() * 100)}%")

    logging.info(f"[+] Upload Complete! Video ID: {response['id']} (Status: {status_payload['privacyStatus']})")
    log_upload(response['id'])
    return response['id']


def upload_short(video_path, metadata, schedule_time=None, token_info=None, token_path=None):
    """
    Uploads a short to YouTube via OAuth2 (adds #shorts to title/description).
    If schedule_time is provided, sets privacyStatus to 'private' and publishAt to future ISO 8601 UTC timestamp.
    """
    return _upload(
        video_path, metadata,
        schedule_time=schedule_time, token_info=token_info, token_path=token_path,
        is_short=True
    )


def upload_video(video_path, metadata, schedule_time=None, token_info=None, token_path=None):
    """
    Uploads a regular (long-form, non-short) video to YouTube via OAuth2.
    No '#shorts' is appended to the title/description.
    If schedule_time is provided, sets privacyStatus to 'private' and publishAt to future ISO 8601 UTC timestamp.
    """
    return _upload(
        video_path, metadata,
        schedule_time=schedule_time, token_info=token_info, token_path=token_path,
        is_short=False
    )
