import json
import os
import re
from groq import Groq
from config import GROQ_API_KEY

# Families we prefer for chat/JSON generation, in priority order.
# Used to rank models returned by the live /models list.
_CHAT_PREFER = (
    "llama-4", "llama-3.3", "llama-3.1", "deepseek", "qwen",
    "gemma", "gpt-oss", "kimi", "mistral",
)
# Model id substrings that are NOT text-chat models (skip them).
_SPEECH_HINTS = ("whisper", "tts", "playai", "distil-whisper")

# Best-guess current live fallbacks, used only if the live /models list
# cannot be fetched (e.g. key/network issue). Cycled through on failure.
_FALLBACK_MODELS = [
    "llama-4-scout-17b-16e-instruct",
    "llama-3.3-70b-versatile",
    "deepseek-r1-distill-llama-70b",
    "gpt-oss-120b",
]

_MODEL_CACHE = None  # module-level cache so we query /models at most once per run


def _available_chat_models(client):
    """Return chat-capable Groq model ids, preferred families first.

    Self-healing: queries the live /models endpoint so decommissioned models
    are never used. Falls back to a static list if the API is unreachable.
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    ids = []
    try:
        resp = client.models.list()
        ids = [m.id for m in resp.data]
    except Exception as e:
        print(f"[-] Could not list Groq models ({e}); using built-in list.")
    text = [i for i in ids if not any(h in i for h in _SPEECH_HINTS)]
    text.sort(key=lambda i: next(
        (idx for idx, p in enumerate(_CHAT_PREFER) if p in i), len(_CHAT_PREFER)))
    seen, ordered = set(), []
    for i in text:
        if i not in seen:
            seen.add(i)
            ordered.append(i)
    _MODEL_CACHE = ordered or list(_FALLBACK_MODELS)
    if _MODEL_CACHE and _MODEL_CACHE is not _FALLBACK_MODELS:
        print(f"[*] Groq live models available ({len(_MODEL_CACHE)}); will use in order.")
    return _MODEL_CACHE


def _extract_json(text):
    """Pull a JSON object out of a model response.

    Models sometimes wrap JSON in ```json fences or add prose around it. With
    response_format=json_object most return raw JSON, but a few models still
    emit fenced output that Groq's server-side validator rejects — so we parse
    defensively instead of trusting the forced mode.
    """
    if text is None:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # Strip ```json ... ``` fences
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:
            pass
    # Last resort: first balanced-looking {...}
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except Exception:
            pass
    return None


def _validate_metadata(obj):
    """Ensure the parsed object has the fields pipeline expects."""
    if not isinstance(obj, dict):
        return False
    if not obj.get("title") or not isinstance(obj.get("title"), str):
        return False
    if not obj.get("description") or not isinstance(obj.get("description"), str):
        return False
    return True


def _call_groq(client, prompt):
    """Try every available model until one returns valid JSON metadata.

    Robust against Groq's `json_validate_failed` (HTTP 400): when a model
    fails validation under forced json_object mode, we retry the SAME model
    WITHOUT the json_object mode (most models emit clean JSON that way) before
    moving on to the next model. This stops the noisy model-failed spam and
    gets a result from the preferred model instead of always falling back.
    """
    models = _available_chat_models(client)
    last_err = None
    for model in models:
        # Attempt 1: forced JSON mode (best for well-behaved models)
        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            obj = _extract_json(response.choices[0].message.content)
            if obj and _validate_metadata(obj):
                return obj, model
        except Exception as e:
            last_err = e
            err_text = str(e)
            # 'json_validate_failed' -> retry same model without json mode
            if "json_validate_failed" in err_text:
                try:
                    response = client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model=model,
                        temperature=0.7,
                    )
                    obj = _extract_json(response.choices[0].message.content)
                    if obj and _validate_metadata(obj):
                        return obj, model
                except Exception as e2:
                    last_err = e2
            # fall through to next model
        # Attempt 2 (used if forced-JSON returned bad/empty content but didn't raise)
        if True:
            try:
                response = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    temperature=0.7,
                )
                obj = _extract_json(response.choices[0].message.content)
                if obj and _validate_metadata(obj):
                    return obj, model
            except Exception as e:
                last_err = e
        print(f"[!] Groq model '{model}' failed: {last_err}; trying next model...")
    print(f"[!] All Groq models failed ({last_err}); using fallback metadata.")
    return None, None


def generate_metadata(video_title, niche="gaming"):
    """Generate Shorts metadata (title, description, tags) via Groq."""
    print(f"[*] Generating AI Metadata for niche '{niche}'...")
    niche_clean = "".join(c for c in niche if c.isalnum())
    fallback_data = {
        "title": f"Epic {niche.capitalize()} Moment 😱 #shorts",
        "description": f"Wait for the end of this crazy {niche} video!\n\n👍 Like and Subscribe for more amazing clips!\n\n#{niche_clean} #shorts",
        "hashtags": ["#shorts", f"#{niche_clean}", "#epic", "#moments", "#highlights", "#clip", "#viral"],
        "tags": f"{niche},shorts,epic,funny,moments,highlights,clip,viral,video",
    }

    if not GROQ_API_KEY:
        print("[-] GROQ_API_KEY missing. Using fallback metadata.")
        return fallback_data

    client = Groq(api_key=GROQ_API_KEY)
    prompt = f"""
    You are an expert YouTube Shorts creator. Generate metadata for a Shorts video in the "{niche}" niche, curated from a video titled: "{video_title}".

    Output strictly in this JSON format:
    {{
        "title": "<Click-worthy title under 80 characters with 1-2 emojis>",
        "description": "<SEO friendly description under 300 characters, ending with a Call to Action>",
        "hashtags": ["#shorts", ... 9 more relevant tags based on the niche],
        "tags": "comma, separated, list, of, 20, youtube, seo, tags, related to this niche/video"
    }}
    """

    data, used = _call_groq(client, prompt)
    if not data:
        return fallback_data

    print(f"[+] Groq metadata generated with model '{used}'.")
    if "#shorts" not in data.get("hashtags", []):
        data["hashtags"] = ["#shorts"] + data.get("hashtags", [])[:9]
    return data


def generate_video_metadata(video_title, niche="gaming"):
    """Generate LONG-FORM compilation metadata. Hashtags never include #shorts."""
    print(f"[*] Generating AI Video Metadata for niche '{niche}'...")
    niche_clean = "".join(c for c in niche if c.isalnum())
    fallback_data = {
        "title": f"INSANE {niche.upper()} MOMENTS - Best Plays Compilation 🔥",
        "description": f"The craziest {niche} moments you need to see!\n\n👍 Like and Subscribe for more amazing videos!\n\n#{niche_clean} #gaming #highlights",
        "hashtags": [f"#{niche_clean}", "#gaming", "#highlights", "#bestmoments", "#epic", "#viral", "#compilation", "#gameplay", "#twitch"],
        "tags": f"{niche},gaming,highlights,compilation,best moments,epic,gameplay,twitch,viral,funny,top plays,montage",
    }

    if not GROQ_API_KEY:
        print("[-] GROQ_API_KEY missing. Using fallback metadata.")
        return fallback_data

    client = Groq(api_key=GROQ_API_KEY)
    prompt = f"""
    You are an expert YouTube gaming channel creator. Generate metadata for a LONG-FORM compilation video in the "{niche}" niche, built from the best Twitch clips (one source clip is titled: "{video_title}").
    This is a regular YouTube video, NOT a Short, so hashtags must NOT include #shorts.

    Output strictly in this JSON format:
    {{
        "title": "<Click-worthy title under 100 characters with 1-2 emojis>",
        "description": "<SEO friendly description under 500 characters, ending with a Call to Action>",
        "hashtags": ["..." 9 relevant tags based on the niche, no #shorts],
        "tags": "comma, separated, list, of, 20, youtube, seo, tags, related to this niche/video"
    }}
    """

    data, used = _call_groq(client, prompt)
    if not data:
        return fallback_data

    print(f"[+] Groq video metadata generated with model '{used}'.")
    data["hashtags"] = [h for h in data.get("hashtags", []) if h.lower() != "#shorts"]
    if len(data["hashtags"]) < 9:
        data["hashtags"] += fallback_data["hashtags"][: 9 - len(data["hashtags"])]
    return data
