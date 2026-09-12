
import os
# Programmatic graphics: generate simple shapes/colors using Python + FFmpeg

def generate_background(duration=15, width=1080, height=1920, color="black"):
    """Generate a simple colored background video clip."""
    return f"ffmpeg -f lavfi -i color=c={color}:s={width}x{height}:d={duration} -t {duration} -c:v libx264 -pix_fmt yuv420p"

def generate_text_overlay(text, font_color="white", fontsize=48):
    return f"drawtext=text=\'{text}\':fontcolor={font_color}:fontsize={fontsize}:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5"
