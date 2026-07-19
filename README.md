# Twitch to YouTube Shorts Automation Bot 🤖🎬

An automated production pipeline that fetches trending gaming clips from the **Twitch Helix API**, processes them into high-quality 9:16 vertical 1080p **YouTube Shorts**, generates AI titles & descriptions with **Groq**, and uploads them to YouTube automatically via **GitHub Actions**.

---

## 🌟 Key Features

- **Twitch Helix API Source**: Fetches trending clips across top game categories (GTA V, Fortnite, Minecraft, Apex Legends, VALORANT, Warzone, etc.).
- **Direct CDN Fast Downloader**: Downloads Twitch clip MP4 files directly from Twitch's CDN infrastructure without IP throttling or sign-in blocks.
- **AI Audio & Highlight Analysis**: Detects human voice vs. game audio vs. silence and applies background music (BGM) accordingly.
- **Shorts Video Processor**: Crops, scales, sharpens, and speeds up 16:9 gameplay into pristine 9:16 vertical 1080p video (< 45 seconds).
- **Groq Llama 3.3 Metadata**: Generates viral titles, SEO descriptions, and tags.
- **YouTube OAuth2 Uploader**: Automatically uploads Shorts to YouTube with `#shorts` tags.
- **GitHub Actions 24/7 Scheduler**: Automatically runs 6 times daily (`0 6,9,12,15,18,21 * * *` UTC).

---

## 🛠️ Prerequisites

- Python 3.11+
- FFmpeg installed
- Twitch Developer Account (for Client ID & Client Secret)
- YouTube Cloud Console Credentials (for OAuth2 token)

---

## 🔑 Environment Variables Setup

Create a `.env` file in the root directory:

```env
# Twitch Helix API Credentials (dev.twitch.tv)
TWITCH_CLIENT_ID="your_twitch_client_id"
TWITCH_CLIENT_SECRET="your_twitch_client_secret"

# Optional YouTube Data API & Groq API
YOUTUBE_API_KEY="your_youtube_api_key"
GROQ_API_KEY="your_groq_api_key"

# YouTube OAuth Secrets
YOUTUBE_TOKEN_JSON='{"token": "...", "refresh_token": "..."}'
YOUTUBE_CLIENT_SECRET_JSON='{"installed": {"client_id": "..."}}'
```

---

## 🚀 Local Usage

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run single trigger (1 Short upload)**:
   ```bash
   python pipeline.py
   ```

3. **Run in 24/7 loop mode**:
   ```bash
   python pipeline.py --loop
   ```

---

## 🤖 GitHub Actions Workflow Secrets

Add the following Repository Secrets under **Settings** $\rightarrow$ **Secrets and variables** $\rightarrow$ **Actions**:

- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`
- `YOUTUBE_API_KEY`
- `GROQ_API_KEY`
- `YOUTUBE_TOKEN_JSON`
- `YOUTUBE_CLIENT_SECRET_JSON`

---

## 📁 Repository Architecture

```
├── config.py                 # Central config & target game categories
├── twitch_finder.py          # Queries Twitch Helix API for trending game clips
├── twitch_downloader.py      # Direct Twitch CDN & yt-dlp clip downloader
├── audio_analyzer.py         # Voice detection & audio analysis
├── highlight_detector.py     # Detects exciting gameplay highlights
├── video_processor.py        # Crops 16:9 to 9:16 vertical Short (< 45s)
├── metadata_generator.py     # AI title, description & tag generation via Groq
├── youtube_uploader.py       # OAuth2 YouTube Shorts uploader
├── pipeline.py               # Main trigger controller & workflow executor
└── .github/workflows/        # Scheduled GitHub Actions cron pipeline
```
