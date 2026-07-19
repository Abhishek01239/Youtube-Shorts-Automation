# YouTube Shorts Automation Bot 🤖

A fully automated, 24/7 Python pipeline that curates Minecraft gameplay videos from small creators, intelligently extracts the best highlights, converts them into styled vertical Shorts, generates AI metadata using Groq (Llama 3.3), and uploads them via the YouTube API.

## Features ✨
- **Smart Sourcing**: Finds Minecraft videos and filters creators with < 20K subscribers via YouTube Data API v3.
- **Voice Filtering**: Uses Spectral Analysis & Speech Recognition to reject videos containing human voices.
- **AI Highlight Detection**: Evaluates scenes using `scenedetect` and audio energy (`librosa`) to find the most exciting moments.
- **FFmpeg Magic**: Auto-crops to 9:16 (1080x1920), adds a Ken Burns zoom effect, burns auto-generated text overlays, and mixes background music.
- **AI Metadata**: Utilizes Groq's Llama 3.3 model to generate highly clickable titles, descriptions, and SEO tags.
- **Automated Publishing**: OAuth2 authenticated uploads, scheduling Shorts for peak times (3 PM, 7 PM, 10 PM UTC).
- **24/7 Loop**: Automatically runs every day, cleans up raw files to save disk space, and prevents duplicate uploads.

## Setup Instructions 🛠️

### 1. Prerequisites
- Python 3.10+
- **FFmpeg** must be installed on your system. 
  - Ubuntu: `sudo apt install ffmpeg`
  - Mac: `brew install ffmpeg`
  - Windows: Download from gyan.dev and add to PATH.

### 2. Installation
```bash
# Clone or setup directory
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. API Credentials
1. **YouTube API & OAuth**:
   - Go to Google Cloud Console. Enable the "YouTube Data API v3".
   - Create an API Key and add it to `.env` as `YOUTUBE_API_KEY`.
   - Create an OAuth 2.0 Client ID (Desktop App). Download the JSON and save it in the root folder as `client_secret.json`.
2. **Groq API**:
   - Go to Groq console, get a free API key.
   - Add it to `.env` as `GROQ_API_KEY`.

### 4. Assets
- **Background Music**: Place royalty-free `.mp3` files in `assets/background_music/`. The bot will randomly pick one if available.
- **Fonts**: (Optional) Add `.ttf` files in `assets/fonts/` for custom subtitle fonts.

### 5. Running the Bot
```bash
python pipeline.py
```
*Note: The first time it uploads, a browser window (or console link) will prompt you to authorize your YouTube account.*

## Project Structure
All raw and processed videos are stored in `data/` and cleaned up periodically to conserve space. State is maintained in `data/seen_videos.txt`.
