"""
Editing-style bandit: learns which editing and clipping choices make Shorts that
people actually watch.

How it works (a multi-armed bandit, the simplest form of reinforcement learning):

  * ACTIONS  - for every Short, one option is picked in each DIMENSION below
               (layout, punch-ins, fonts, clip length, how the moment finder
               weighs loudness / motion / speech).
  * POLICY   - Thompson sampling: every option keeps a Beta(a, b) belief about
               how good it is; we draw a sample from each and take the best.
               Options with little data have wide beliefs, so they still get
               tried (exploration); proven options win most draws (exploitation).
               A small `explore` share of picks is fully random on top of that.
  * REWARD   - 48-72 h after a Short goes public, rl/update_rewards.py reads its
               retention (average % watched), subscribers gained and views, turns
               them into a score from 0 to 1, and adds it to the beliefs of the
               options that Short used.
  * MEMORY   - data/channels/<channel>/rl_state.json (beliefs) and rl_log.json
               (which options each uploaded Short used). The GitHub Actions
               workflow commits both back to the repo, so learning survives runs.

Per-channel settings in channels.json (all optional):

    "rl": {
      "enabled": true,              # default true for YouTube channels
      "fixed": ["headline_font"],   # dimensions to NOT learn; the channel's own
                                    # value (or the pipeline default) is used
      "explore": 0.1                # share of fully random picks per dimension
    }

Everything fails open: if the state can't be read or written, the pipeline uses
the channel's normal settings.
"""
import json
import logging
import os
import random
from datetime import datetime, timezone

import config

# ----------------------------------------------------------------------------
# What the bandit can choose
# ----------------------------------------------------------------------------
DIMENSIONS = {
    "framing": ["auto", "blur", "crop"],
    "punch_ins": ["on", "off"],
    "headline_font": ["luckiest", "anton", "bangers", "bebas"],
    "caption_font": ["luckiest", "anton", "bangers", "bebas"],
    "clip_length": ["short", "medium", "long"],
    "moment_style": ["balanced", "audio", "speech", "action"],
}

# clip_length -> candidate window lengths (seconds) for the moment finder
CLIP_LENGTHS = {
    "short": (15.0, 20.0, 25.0),
    "medium": (25.0, 30.0, 35.0),
    "long": (35.0, 40.0, 45.0),
}

# moment_style -> (audio, motion, speech) weights of the excitement curve
MOMENT_WEIGHTS = {
    "balanced": (0.45, 0.25, 0.30),   # the hand-tuned original
    "audio": (0.60, 0.15, 0.25),      # loud reactions, screams, blasts
    "speech": (0.30, 0.15, 0.55),     # funny lines, hype words, laughing
    "action": (0.35, 0.45, 0.20),     # on-screen action and fights
}

DEFAULT_EXPLORE = 0.1
DECAY = 0.995   # older evidence fades slowly, so the bandit can follow trends


# ----------------------------------------------------------------------------
# Files
# ----------------------------------------------------------------------------
def _channel_dir(channel_name):
    sanitized = "".join(c if c.isalnum() else "_" for c in channel_name)
    path = os.path.join(config.DATA_DIR, "channels", sanitized)
    os.makedirs(path, exist_ok=True)
    return path


def state_path(channel_name):
    return os.path.join(_channel_dir(channel_name), "rl_state.json")


def log_path(channel_name):
    return os.path.join(_channel_dir(channel_name), "rl_log.json")


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        logging.warning(f"[RL] Could not read {path}: {e}")
        return default


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def new_state():
    return {
        "version": 1,
        "arms": {dim: {opt: {"a": 1.0, "b": 1.0, "n": 0} for opt in opts}
                 for dim, opts in DIMENSIONS.items()},
        "recent_views": [],
        "rewards_total": 0,
        "updated_at": None,
    }


def load_state(channel_name):
    state = _read_json(state_path(channel_name), None) or new_state()
    # Add any dimension/option introduced after the state file was created.
    for dim, opts in DIMENSIONS.items():
        arms = state.setdefault("arms", {}).setdefault(dim, {})
        for opt in opts:
            arms.setdefault(opt, {"a": 1.0, "b": 1.0, "n": 0})
    state.setdefault("recent_views", [])
    state.setdefault("rewards_total", 0)
    return state


def save_state(channel_name, state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(state_path(channel_name), state)


def load_log(channel_name):
    return _read_json(log_path(channel_name), [])


def save_log(channel_name, log):
    _write_json(log_path(channel_name), log)


# ----------------------------------------------------------------------------
# Policy
# ----------------------------------------------------------------------------
def is_enabled(channel):
    if (channel.get("platform") or "youtube").lower() != "youtube":
        return False
    return bool((channel.get("rl") or {}).get("enabled", True))


def choose(channel_name, channel, rng=None):
    """Pick one option per dimension. Returns e.g. {"framing": "blur", ...}."""
    rng = rng or random.Random()
    rl_cfg = channel.get("rl") or {}
    fixed = set(rl_cfg.get("fixed") or [])
    explore = float(rl_cfg.get("explore", DEFAULT_EXPLORE))
    try:
        state = load_state(channel_name)
    except Exception as e:
        logging.warning(f"[RL] State unavailable ({e}); using channel defaults.")
        return {}

    choices = {}
    for dim, opts in DIMENSIONS.items():
        if dim in fixed:
            continue
        if rng.random() < explore:
            choices[dim] = rng.choice(opts)
            continue
        arms = state["arms"][dim]
        draws = {opt: rng.betavariate(max(arms[opt]["a"], 1e-3), max(arms[opt]["b"], 1e-3))
                 for opt in opts}
        choices[dim] = max(draws, key=draws.get)
    logging.info(f"[RL] Editing choices: {choices}")
    return choices


def to_channel_overrides(choices):
    """Map choices onto the channels.json keys the pipeline already reads."""
    out = {}
    if "framing" in choices:
        out["framing"] = choices["framing"]
    if "punch_ins" in choices:
        out["punch_ins"] = choices["punch_ins"] == "on"
    if "headline_font" in choices:
        out["headline_font"] = choices["headline_font"]
    if "caption_font" in choices:
        out["caption_font"] = choices["caption_font"]
    return out


def window_lengths(choices):
    return CLIP_LENGTHS.get((choices or {}).get("clip_length"))


def moment_weights(choices):
    return MOMENT_WEIGHTS.get((choices or {}).get("moment_style"))


def log_upload(channel_name, video_id, publish_time, choices, extra=None):
    """Remember which options an uploaded Short used, so it can be rewarded later."""
    if not choices or not video_id:
        return
    try:
        log = load_log(channel_name)
        entry = {
            "video_id": video_id,
            "publish_time": publish_time.astimezone(timezone.utc).isoformat()
            if isinstance(publish_time, datetime) else str(publish_time),
            "choices": choices,
            "rewarded": False,
        }
        if extra:
            entry.update(extra)
        log.append(entry)
        save_log(channel_name, log)
    except Exception as e:
        logging.warning(f"[RL] Could not log upload {video_id}: {e}")


# ----------------------------------------------------------------------------
# Learning
# ----------------------------------------------------------------------------
def update(state, choices, reward):
    """Add one reward (0..1) to every option a Short used."""
    reward = min(1.0, max(0.0, float(reward)))
    for dim, opts in state["arms"].items():
        for arm in opts.values():   # slow forgetting keeps the bandit adaptable
            arm["a"] = 1.0 + (arm["a"] - 1.0) * DECAY
            arm["b"] = 1.0 + (arm["b"] - 1.0) * DECAY
        opt = (choices or {}).get(dim)
        if opt in opts:
            opts[opt]["a"] += reward
            opts[opt]["b"] += 1.0 - reward
            opts[opt]["n"] += 1
    state["rewards_total"] = state.get("rewards_total", 0) + 1


def summary(state):
    """Human-readable table of what the bandit currently believes."""
    lines = []
    for dim, opts in state["arms"].items():
        ranked = sorted(opts.items(), key=lambda kv: kv[1]["a"] / (kv[1]["a"] + kv[1]["b"]), reverse=True)
        cells = [f"{opt} {arm['a'] / (arm['a'] + arm['b']):.2f} (n={arm['n']})" for opt, arm in ranked]
        lines.append(f"  {dim:<14} " + " | ".join(cells))
    return "\n".join(lines)
