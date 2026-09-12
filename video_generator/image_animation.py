
import os
# Image animations: slow zoom, pan using ffmpeg filters

def zoom_in_filter(duration=7):
    return f"zoompan=z='zoom+in':d={duration}:s=1280x720"

def pan_right_filter(duration=7):
    return f"zoompan=z=1:d={duration}:x=w/2:y=h/2"
