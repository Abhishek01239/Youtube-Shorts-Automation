
import os
# Subtitles: create SRT or burn into video

def create_srt(subtitle_text, duration=7, start_time="00:00:00,000"):
    return f"1\n{start_time} --> {start_time.replace(':','',1)}\n{subtitle_text}\n"
