import os,json,base64,hashlib,subprocess,tempfile\nfrom datetime import datetime,timezone,timedelta
from pathlib import Path
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SUPA=os.environ["SUPABASE_URL"].rstrip("/")
KEY=os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SECRET_KEY")
if not KEY: raise RuntimeError("Supabase server secret key is required")
HEAD={"apikey":KEY,"Authorization":f"Bearer {KEY}","Content-Type":"application/json"}
ENC=os.environ["OAUTH_ENCRYPTION_KEY"]

def db(path,method="GET",body=None,params=None):
 r=requests.request(method,SUPA+"/rest/v1/"+path,headers=HEAD,json=body,params=params,timeout=30)
 r.raise_for_status(); return r.json() if r.text else None

def dec(value):
 iv,tag,data=value.split(".")
 key=hashlib.sha256(ENC.encode()).digest()
 raw=AESGCM(key).decrypt(base64.urlsafe_b64decode(iv+"=="),base64.urlsafe_b64decode(tag+"==")+base64.urlsafe_b64decode(data+"=="),None)
 return raw.decode()

def main():
 jobs=db("clipilot_jobs",params={"status":"eq.queued","available_at":"lte.now()","order":"created_at.asc","limit":"3"})
 for job in jobs:
  jid=job["id"]; uid=job["user_id"]
  db("clipilot_jobs","PATCH",{"status":"running","attempts":job.get("attempts",0)+1},params={"id":"eq."+jid})
  try:
   settings=db("clipilot_settings",params={"user_id":"eq."+uid,"enabled":"eq.true","limit":"1"})[0]
   conns=db("clipilot_connections",params={"user_id":"eq."+uid})
   youtube=next((x for x in conns if x["provider"]=="youtube"),None); twitch=next((x for x in conns if x["provider"]=="twitch"),None)
   if not youtube or not twitch: raise RuntimeError("Twitch and YouTube must both be connected")
   yt=json.loads(dec(youtube["access_token_enc"]))
   if youtube.get("refresh_token_enc"): yt["refresh_token"]=dec(youtube["refresh_token_enc"])
   with tempfile.TemporaryDirectory() as td:
    channel="ClipPilot_"+uid[:8]
    token_dir=Path("data/channels")/channel; token_dir.mkdir(parents=True,exist_ok=True)
    (token_dir/"token.json").write_text(json.dumps(yt))
    cfg=[{"channel_name":channel,"niche":"gaming highlights","shorts_per_run":int(settings["shorts_per_run"]),"videos_per_run":0,"upload_schedule":{"interval_hours":int(settings["interval_hours"])},"youtube_oauth_credentials":str(token_dir/"token.json"),"source_configuration":{"source_type":"twitch","target_games":settings["target_games"]}}]
    Path(td,"channels.json").write_text(json.dumps(cfg))
    subprocess.run(["python","pipeline.py","--channels",str(Path(td,"channels.json")),"--channel",channel],check=True)
   db("clipilot_jobs","PATCH",{"status":"succeeded"},params={"id":"eq."+jid})
  except Exception as e:
   db("clipilot_jobs","PATCH",{"status":"failed","error":str(e)},params={"id":"eq."+jid})
if __name__=="__main__": main()
