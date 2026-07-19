import json
from groq import Groq
from config import GROQ_API_KEY

def generate_metadata(video_title):
    """
    Uses Groq API (Llama 3.3 70B) to generate a clickable title, description, and tags.
    """
    print("[*] Generating AI Metadata...")
    fallback_data = {
        "title": "Epic Minecraft Moment 😱 #shorts",
        "description": "Wait for the end of this crazy Minecraft gameplay!\n\n👍 Like and Subscribe for more amazing clips!\n\n#minecraft #shorts #gaming",
        "hashtags": ["#shorts", "#minecraft", "#gaming", "#minecraftshorts", "#gamer", "#mcpe", "#minecrafter", "#minecraftclips", "#epic", "#gameplay"],
        "tags": "minecraft,shorts,gaming,gameplay,minecraft shorts,epic,funny,mcpe,survival,speedrun,pro,noob,moments,highlights,clip,gamer,video games,bedrock,java,creeper"
    }
    
    if not GROQ_API_KEY:
        print("[-] GROQ_API_KEY missing. Using fallback metadata.")
        return fallback_data
        
    client = Groq(api_key=GROQ_API_KEY)
    
    prompt = f"""
    You are an expert YouTube Shorts creator. Generate metadata for a gaming Shorts video curated from a video titled: "{video_title}".
    
    Output strictly in this JSON format:
    {{
        "title": "<Click-worthy title under 80 characters with 1-2 emojis>",
        "description": "<SEO friendly description under 300 characters, ending with a Call to Action>",
        "hashtags": ["#shorts", "#gaming", ... 8 more relevant tags based on the game],
        "tags": "comma, separated, list, of, 20, youtube, seo, tags, related, to, the, specific, game"
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
