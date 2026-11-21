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
- **Long-form Compilation Videos**: Also builds regular 16:9 1080p videos (several clips stitched with BGM) and schedules them as standard YouTube uploads (no `#shorts`).
- **GitHub Actions 24/7 Scheduler**: Automatically runs 6 times daily (`0 6,9,12,15,18,21 * * *` UTC).

---

## 🎨 Shorts Editing Options (per channel, in `channels.json`)

Every Short goes through: AI clip picker → moment finder → layout → zoom punch-ins → captions → headline + streamer credit → quality mastering → upload. All options are optional; defaults shown.

| Key | Default | What it does |
|---|---|---|
| `min_clip_score` | `4` | AI clip picker: Groq rates each clip 1-10 from its speech, title and views; lower scores are skipped. The bar drops by 1 after every 3 rejections in a run, so a channel never runs dry. `0` disables. Needs `GROQ_API_KEY` (clips are kept if scoring fails). |
| `smart_moments` | `true` | Moment finder: picks the best 15-45 s of each clip from loudness spikes, on-screen motion and the streamer's speech (hype words, laughing, shouting), cross-checked with Groq's pick from the timestamped transcript, and cut on sentence boundaries. `false` = old middle cut. |
| `framing` | `"auto"` | `"auto"`: facecam split layout if a streamer facecam is found, else `"blur"`. `"split"`, `"blur"` (full frame over a blurred background) or `"crop"` (old centre crop). |
| `punch_ins` | `true` | Quick zoom + shake on the loudest hype moments. |
| `credit_streamer` | `true` | `twitch.tv/name` under the headline and a clip link in the description. |
| `headline` | `true` | Burns the video title in at the top of the Short. |
| `headline_font` | `"luckiest"` | `luckiest`, `anton`, `bangers` or `bebas`. |
| `caption_font` | same as `headline_font` | Same choices, plus `minecraft` (needs `fonts/Monocraft.ttf`). |
| `min_source_height` | `480` | Skip clips below this resolution. |
| `enhance_quality` | `true` | Final mastering pass (sharpening, -14 LUFS loudness, high-quality encode). |

## 🧠 Self-improving editing (RL bandit)

Every YouTube Short is edited with a style chosen by a **multi-armed bandit** (a simple form of reinforcement learning) that learns from how your past Shorts performed.

- **What it chooses** for each Short: layout (`auto` / `blur` / `crop`), punch-ins (on / off), headline font, caption font, clip length (15-25 / 25-35 / 35-45 s) and moment style (how the moment finder weighs loudness, on-screen motion and speech).
- **How it learns:** before each run, `python -m rl.update_rewards` scores every Short that has been public for 72 h. The score mostly comes from **retention (average % watched)**, plus subscribers gained and views compared with the channel's median. Thompson sampling then favours the options that score best while still testing the others (10% fully random picks).
- **Memory:** `data/channels/<channel>/rl_state.json` (what it believes) and `rl_log.json` (which options each Short used). The workflow commits both back to the repo.
- **Retention needs one-time setup:** enable the *YouTube Analytics API* in your Google Cloud project, then re-run `python gen_token.py <CHANNEL>` and paste the new JSON into the `YOUTUBE_TOKEN_JSON_<CHANNEL>` secret. Until then it learns from public views and likes (via `YOUTUBE_API_KEY`).
- **Per-channel options** in `channels.json`:

```json
"rl": {
  "enabled": true,
  "fixed": ["headline_font"],
  "explore": 0.1
}
```

`enabled` defaults to `true` for YouTube channels. Dimensions listed in `fixed` are never changed by the bandit (the channel's own setting is used). The run log prints the current beliefs after every reward update, e.g. `clip_length short 0.58 (n=12) | medium 0.51 (n=9) | long 0.44 (n=7)`.

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

```json
{
  "channel_name": "MyChannel",
  "niche": "Minecraft gaming highlights and funny moments",
  "upload_schedule": { "interval_hours": 3 },
  "shorts_per_run": 6,
  "videos_per_run": 3,
  "clips_per_video": 5,
  "youtube_oauth_credentials": "data/channels/MyChannel/token.json",
  "source_configuration": {
    "source_type": "twitch",
    "target_games": ["Minecraft"]
  }
}
```
- `shorts_per_run` → how many Shorts to create per batch (default 6).
- `videos_per_run` → how many long-form compilation videos to create per batch (default 0 = disabled; each video stitches `clips_per_video` clips, default 5).

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
