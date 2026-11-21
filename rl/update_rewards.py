"""
Reward step for the editing bandit (run before each pipeline run).

For every Short in rl_log.json that has been public for at least
--min-age-hours (default 72), this reads how it performed and teaches the bandit:

  * Best:     YouTube Analytics API (needs the yt-analytics.readonly scope in the
              channel's token; re-run gen_token.py once to add it)
              -> averageViewPercentage (retention), subscribersGained, views
  * Fallback: YouTube Data API with YOUTUBE_API_KEY -> views, likes

Reward (0..1):
  with retention:  0.60 * retention (25% watched = 0, 100% = 1) + 0.25 * views vs channel median + 0.15 * subs per 1k views
  views only:      0.70 * views vs channel median + 0.30 * like rate

Usage:
    python -m rl.update_rewards --channels channels.json --channel MinecraftShorts2
"""
import argparse
import json
import logging
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402  (also writes channel tokens from env vars)
from rl import bandit  # noqa: E402

ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
MAX_TRACKED_VIEWS = 60


# ----------------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------------
def _token_path(channel):
    creds_config = channel.get("youtube_oauth_credentials")
    if isinstance(creds_config, str) and os.path.exists(creds_config):
        return creds_config
    sanitized = "".join(c if c.isalnum() else "_" for c in channel["channel_name"])
    return os.path.join(config.DATA_DIR, "channels", sanitized, "token.json")


def fetch_analytics(channel, video_ids, start_date):
    """Retention etc. from the YouTube Analytics API, or None if not authorised."""
    path = _token_path(channel)
    if not os.path.exists(path):
        logging.info("[RL] No token file; skipping YouTube Analytics.")
        return None
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        with open(path, "r", encoding="utf-8") as f:
            info = json.load(f)
        granted = info.get("scopes") or []
        if isinstance(granted, str):
            granted = granted.split()
        if ANALYTICS_SCOPE not in granted:
            logging.info("[RL] Token has no analytics permission yet (re-run gen_token.py). "
                         "Using public views instead.")
            return None
        creds = Credentials.from_authorized_user_info(info)
        yta = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        rows = {}
        for i in range(0, len(video_ids), 200):
            batch = video_ids[i:i + 200]
            resp = yta.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=datetime.now(timezone.utc).date().isoformat(),
                metrics="views,engagedViews,averageViewPercentage,averageViewDuration,subscribersGained,likes",
                dimensions="video",
                filters="video==" + ",".join(batch),
                maxResults=200,
            ).execute()
            names = [h["name"] for h in resp.get("columnHeaders", [])]
            for r in resp.get("rows", []) or []:
                rec = dict(zip(names, r))
                rows[rec["video"]] = {
                    "views": int(rec.get("views") or 0),
                    "engaged_views": int(rec.get("engagedViews") or 0),
                    "avg_view_pct": float(rec.get("averageViewPercentage") or 0.0),
                    "avg_view_sec": float(rec.get("averageViewDuration") or 0.0),
                    "subs": int(rec.get("subscribersGained") or 0),
                    "likes": int(rec.get("likes") or 0),
                    "source": "analytics",
                }
        return rows
    except Exception as e:
        logging.warning(f"[RL] YouTube Analytics failed ({e}); using public views instead.")
        return None


def fetch_public_stats(video_ids):
    key = config.YOUTUBE_API_KEY
    if not key:
        logging.warning("[RL] No YOUTUBE_API_KEY; cannot read public stats.")
        return {}
    try:
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", developerKey=key, cache_discovery=False)
        rows = {}
        for i in range(0, len(video_ids), 50):
            resp = yt.videos().list(part="statistics", id=",".join(video_ids[i:i + 50])).execute()
            for item in resp.get("items", []):
                st = item.get("statistics", {})
                rows[item["id"]] = {
                    "views": int(st.get("viewCount") or 0),
                    "likes": int(st.get("likeCount") or 0),
                    "source": "public",
                }
        return rows
    except Exception as e:
        logging.warning(f"[RL] Public stats failed: {e}")
        return {}


# ----------------------------------------------------------------------------
# Reward
# ----------------------------------------------------------------------------
def compute_reward(m, median_views):
    views = max(0, m.get("views", 0))
    views_rel = views / (views + max(1.0, median_views))          # 0.5 = median
    if m.get("source") == "analytics" and views > 0:
        # 25% watched -> 0, 100% -> 1 (Shorts can loop past 100%; capped at 1)
        retention = min(1.0, max(0.0, (m.get("avg_view_pct", 0.0) - 25.0) / 75.0))
        subs_rel = min(1.0, (m.get("subs", 0) / views * 1000) / 5.0)
        return 0.60 * retention + 0.25 * views_rel + 0.15 * subs_rel
    like_rel = min(1.0, (m.get("likes", 0) / views) / 0.06) if views else 0.0
    return 0.70 * views_rel + 0.30 * like_rel


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def update_channel(channel, min_age_hours=72, max_age_days=28):
    name = channel["channel_name"]
    log = bandit.load_log(name)
    if not log:
        logging.info(f"[RL] {name}: nothing logged yet.")
        return 0
    now = datetime.now(timezone.utc)
    ready, expired = [], 0
    for entry in log:
        if entry.get("rewarded"):
            continue
        try:
            published = datetime.fromisoformat(entry["publish_time"].replace("Z", "+00:00"))
        except Exception:
            entry["rewarded"], entry["reward"] = True, None
            continue
        age = now - published
        if age > timedelta(days=max_age_days):
            entry["rewarded"], entry["reward"], entry["note"] = True, None, "expired"
            expired += 1
        elif age >= timedelta(hours=min_age_hours):
            ready.append((entry, published))
    if not ready:
        if expired:
            bandit.save_log(name, log)
        logging.info(f"[RL] {name}: no Shorts old enough to score yet.")
        return 0

    ids = [e["video_id"] for e, _ in ready]
    start = min(p for _, p in ready).date().isoformat()
    metrics = fetch_analytics(channel, ids, start) or {}
    missing = [i for i in ids if i not in metrics]
    if missing:
        metrics.update(fetch_public_stats(missing))

    state = bandit.load_state(name)
    batch_views = [metrics[i]["views"] for i in ids if i in metrics]
    history = state.get("recent_views", []) + batch_views
    median_views = statistics.median(history) if history else 1.0

    scored = 0
    for entry, _ in ready:
        m = metrics.get(entry["video_id"])
        if not m:
            continue   # stats not available yet (e.g. still processing); try next run
        reward = compute_reward(m, median_views)
        bandit.update(state, entry["choices"], reward)
        entry.update({"rewarded": True, "reward": round(reward, 4), "metrics": m,
                      "scored_at": now.isoformat()})
        scored += 1
        logging.info(f"[RL] {entry['video_id']}: reward {reward:.2f} "
                     f"({m['source']}, views {m['views']}"
                     + (f", watched {m['avg_view_pct']:.0f}%" if m.get("source") == "analytics" else "") + ")")

    state["recent_views"] = history[-MAX_TRACKED_VIEWS:]
    bandit.save_state(name, state)
    bandit.save_log(name, log)
    logging.info(f"[RL] {name}: scored {scored} Short(s), median views {median_views:.0f}. Current beliefs:\n"
                 + bandit.summary(state))
    return scored


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Score uploaded Shorts and update the editing bandit.")
    p.add_argument("--channels", default="channels.json")
    p.add_argument("--channel", default=None, help="only this channel_name")
    p.add_argument("--min-age-hours", type=float, default=72)
    p.add_argument("--max-age-days", type=float, default=28)
    args = p.parse_args()

    with open(args.channels, "r", encoding="utf-8") as f:
        channels = json.load(f)
    for ch in channels:
        if args.channel and ch.get("channel_name") != args.channel:
            continue
        if not bandit.is_enabled(ch):
            continue
        try:
            update_channel(ch, args.min_age_hours, args.max_age_days)
        except Exception as e:   # never block the upload run
            logging.warning(f"[RL] {ch.get('channel_name')}: reward update failed: {e}")


if __name__ == "__main__":
    main()
