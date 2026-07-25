import json
from groq import Groq
from config import GROQ_API_KEY

def generate_metadata(video_title, niche="gaming"):
    """
    Uses Groq API (Llama 3.3 70B) to generate a clickable title, description, and tags.
    """
    print(f"[*] Generating AI Metadata for niche '{niche}'...")
    niche_clean = "".join(c for c in niche if c.isalnum())
    fallback_data = {
        "title": f"Epic {niche.capitalize()} Moment 😱 #shorts",
        "description": f"Wait for the end of this crazy {niche} video!\n\n👍 Like and Subscribe for more amazing clips!\n\n#{niche_clean} #shorts",
        "hashtags": ["#shorts", f"#{niche_clean}", "#epic", "#moments", "#highlights", "#clip", "#viral"],
        "tags": f"{niche},shorts,epic,funny,moments,highlights,clip,viral,video"
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
    
    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
            temperature=0.7
        )
        data = json.loads(response.choices[0].message.content)
        
        # Ensure hashtag compliance
        if "#shorts" not in data.get("hashtags", []):
            data["hashtags"] = ["#shorts"] + data.get("hashtags", [])[:9]
            
        return data
    except Exception as e:
        print(f"[!] Groq API Error: {e}")
        return fallback_data
