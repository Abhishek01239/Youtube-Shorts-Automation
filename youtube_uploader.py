import os
import json
from datetime import datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from config import CLIENT_SECRETS_FILE, UPLOAD_LOG_FILE

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def get_authenticated_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('youtube', 'v3', credentials=creds)

def get_upload_count_today():
    if not os.path.exists(UPLOAD_LOG_FILE):
        return 0
    with open(UPLOAD_LOG_FILE, 'r') as f:
        try:
            logs = json.load(f)
            today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            return sum(1 for log in logs if log.get('date') == today)
        except json.JSONDecodeError:
            return 0

def log_upload(video_id):
    logs = []
    if os.path.exists(UPLOAD_LOG_FILE):
        with open(UPLOAD_LOG_FILE, 'r') as f:
            try:
                logs = json.load(f)
            except:
                pass
                
    logs.append({
        'video_id': video_id,
        'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'time': datetime.now(timezone.utc).isoformat()
    })
    
    with open(UPLOAD_LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=4)

def upload_short(video_path, metadata, schedule_time=None):
    """
    Uploads a short to YouTube via OAuth2.
    If schedule_time is provided, sets privacyStatus to 'private' and publishAt to future ISO 8601 UTC timestamp.
    """
    print(f"[*] Uploading {video_path} to YouTube Shorts...")
    youtube = get_authenticated_service()

    tags = [t.strip() for t in metadata['tags'].split(',')] if isinstance(metadata['tags'], str) else metadata['tags']
    description = metadata['description'] + "\n\n" + " ".join(metadata['hashtags'])
    if "#shorts" not in description.lower():
        description += " #shorts"

    title = metadata['title']
    if "#shorts" not in title.lower():
        title = f"{title[:75]} #shorts"

    status_payload = {
        'privacyStatus': 'public',
        'selfDeclaredMadeForKids': False
    }

    if schedule_time:
        # Explicit ISO 8601 formatting required by YouTube API: YYYY-MM-DDTHH:MM:SS.000Z
        formatted_publish_time = schedule_time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        status_payload['privacyStatus'] = 'private'
        status_payload['publishAt'] = formatted_publish_time
        print(f"[*] Scheduling YouTube Video Status Payload: {json.dumps(status_payload)}")

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
            print(f"[-] Uploaded {int(status.progress() * 100)}%")

    print(f"[+] Upload Complete! Video ID: {response['id']} (Status: {status_payload['privacyStatus']})")
    log_upload(response['id'])
    return response['id']
