#!/usr/bin/env python3
"""
clip_radar.py
Watches a list of streamers on Twitch and reports their most-viewed recent clips
of the target games (GTA 6 by default), plus who is live right now.

It only reads public metadata (titles, view counts, links) through the official
Twitch Helix API. It never downloads or uploads any video: the report is for
spotting trending moments and streamers worth asking for clipping permission.

Output:
  - data/clip_radar/latest.md and latest.json
  - the GitHub Actions job summary (when run in Actions)
  - a Telegram message with clips not reported before (if Telegram is configured)

CLI:
    python clip_radar.py [--config clip_radar.json] [--no-notify]
"""
import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import requests

import config
from twitch_finder import get_twitch_access_token, get_game_id, resolve_streamers

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OUT_DIR = os.path.join(config.BASE_DIR, "data", "clip_radar")
NOTIFIED_FILE = os.path.join(OUT_DIR, "notified.txt")
MAX_NOTIFIED = 2000


def helix(path, headers, params):
    res = requests.get(f"https://api.twitch.tv/helix/{path}", headers=headers, params=params, timeout=15)
    res.raise_for_status()
    return res.json()


def live_streams(user_ids, headers):
    """Returns {user_id: stream} for streamers who are live right now."""
    live = {}
    ids = list(user_ids)
    for i in range(0, len(ids), 100):
        data = helix("streams", headers, [("user_id", u) for u in ids[i:i + 100]])
        for s in data.get("data", []):
            live[s["user_id"]] = s
    return live


def recent_clips(broadcaster_id, game_ids, since, headers, pages=3):
    """Most-viewed clips of the target games created since `since` (Twitch returns them by views)."""
    clips, cursor = [], None
    for _ in range(pages):
        params = {"broadcaster_id": broadcaster_id, "first": 100,
                  "started_at": since.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if cursor:
            params["after"] = cursor
        data = helix("clips", headers, params)
        clips += [c for c in data.get("data", []) if c.get("game_id") in game_ids]
        cursor = data.get("pagination", {}).get("cursor")
        if not cursor:
            break
    return clips


def build_report(cfg, now=None):
    now = now or datetime.now(timezone.utc)
    token = get_twitch_access_token()
    if not token:
        raise RuntimeError("Twitch authentication failed: check TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET")
    headers = {"Client-ID": config.TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}"}

    game_ids = {}
    for name in cfg.get("games", ["Grand Theft Auto VI"]):
        gid = get_game_id(name, headers)
        if gid:
            game_ids[gid] = name
    if not game_ids:
        raise RuntimeError(f"None of the games were found on Twitch: {cfg.get('games')}")

    wanted = [s.strip().lstrip("@").lower() for s in cfg.get("streamers", []) if s.strip()]
    streamers = resolve_streamers(wanted, headers)  # {id: login}
    since = now - timedelta(hours=int(cfg.get("lookback_hours", 24)))
    live = live_streams(streamers.keys(), headers) if streamers else {}

    rows, all_clips = [], []
    for uid, login in streamers.items():
        try:
            clips = recent_clips(uid, game_ids, since, headers)
        except Exception as e:
            logging.error(f"[!] Clip lookup failed for @{login}: {e}")
            clips = []
        stream = live.get(uid)
        rows.append({
            "login": login,
            "live": bool(stream),
            "live_game": stream.get("game_name") if stream else None,
            "live_title": stream.get("title") if stream else None,
            "live_viewers": stream.get("viewer_count") if stream else None,
            "clips_found": len(clips),
        })
        for c in clips:
            all_clips.append({
                "id": c["id"],
                "streamer": c.get("broadcaster_name") or login,
                "login": login,
                "title": (c.get("title") or "").strip(),
                "views": c.get("view_count", 0),
                "duration": round(c.get("duration", 0)),
                "created_at": c.get("created_at"),
                "game": game_ids.get(c.get("game_id")),
                "url": c.get("url"),
            })

    min_views = int(cfg.get("min_views", 0))
    top = sorted((c for c in all_clips if c["views"] >= min_views), key=lambda c: c["views"], reverse=True)
    top = top[:int(cfg.get("top_clips", 15))]
    not_found = sorted(set(wanted) - set(streamers.values()))
    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "games": list(game_ids.values()),
        "lookback_hours": int(cfg.get("lookback_hours", 24)),
        "streamers": sorted(rows, key=lambda r: (not r["live"], -r["clips_found"], r["login"])),
        "not_found": not_found,
        "top_clips": top,
    }


def to_markdown(report):
    games = ", ".join(report["games"])
    lines = [f"# 📡 Clip Radar: {games}",
             f"_Updated {report['generated_at']} · clips from the last {report['lookback_hours']}h_", "",
             "## Streamers", "", "| Streamer | Status | Clips found |", "|---|---|---|"]
    for r in report["streamers"]:
        if r["live"]:
            status = f"🔴 LIVE: {r['live_game']} ({r['live_viewers']:,} viewers)"
        else:
            status = "offline"
        lines.append(f"| [{r['login']}](https://twitch.tv/{r['login']}) | {status} | {r['clips_found']} |")
    for login in report["not_found"]:
        lines.append(f"| {login} | ⚠️ not found on Twitch | - |")
    lines += ["", "## Top clips", ""]
    if not report["top_clips"]:
        lines.append("_No clips of these games in this window yet._")
    else:
        lines += ["| # | Views | Streamer | Clip | Length |", "|---|---|---|---|---|"]
        for i, c in enumerate(report["top_clips"], 1):
            title = c["title"].replace("|", "/") or "(untitled)"
            lines.append(f"| {i} | {c['views']:,} | {c['streamer']} | [{title}]({c['url']}) | {c['duration']}s |")
    lines += ["", "> Links only, for discovery. Get the streamer's permission before reposting any clip."]
    return "\n".join(lines) + "\n"


def load_notified():
    if not os.path.exists(NOTIFIED_FILE):
        return []
    with open(NOTIFIED_FILE, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


def notify_new(report):
    """Sends a Telegram message with top clips that haven't been reported before."""
    notified = load_notified()
    new = [c for c in report["top_clips"] if c["id"] not in set(notified)]
    live = [r for r in report["streamers"] if r["live"] and r["live_game"] in report["games"]]
    if not new and not live:
        logging.info("[*] Nothing new to notify.")
        return
    msg = [f"📡 Clip Radar: {', '.join(report['games'])}"]
    if live:
        msg.append("🔴 Live now: " + ", ".join(f"{r['login']} ({r['live_viewers']:,})" for r in live))
    for c in new[:10]:
        msg.append(f"\n🔥 {c['views']:,} views · {c['streamer']}\n{c['title'][:90]}\n{c['url']}")
    text = "\n".join(msg)[:4000]
    if config.NOTIFICATION_PROVIDER == "TELEGRAM" and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        from notifier import send_telegram_msg
        send_telegram_msg(text)
    else:
        logging.info("[*] Telegram not configured; skipping notification.")
    keep = (notified + [c["id"] for c in new])[-MAX_NOTIFIED:]
    with open(NOTIFIED_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(keep) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Report trending clips from watched streamers")
    ap.add_argument("--config", default=os.path.join(config.BASE_DIR, "clip_radar.json"))
    ap.add_argument("--no-notify", action="store_true")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    report = build_report(cfg)
    md = to_markdown(report)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "latest.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(OUT_DIR, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(md)
    print(md)
    if not args.no_notify:
        notify_new(report)


if __name__ == "__main__":
    main()
