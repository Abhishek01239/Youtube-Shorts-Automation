#!/usr/bin/env python3
"""
Generate a YouTube OAuth token.json for one of your channels (local dev only).

Usage:
    python gen_token.py <CHANNEL_NAME>

What happens:
    1. Reads client_secret.json (root of this repo, gitignored).
    2. Opens your browser -> login with the Google/YouTube account that OWNS
       that channel -> approve the upload scope.
    3. Writes data/channels/<CHANNEL_NAME>/token.json
    4. Prints the JSON content so you can paste it into the GitHub secret
       YOUTUBE_TOKEN_JSON_<CHANNEL_NAME>  (or upload the file yourself).

The token file is self-contained (includes its own client_id/client_secret),
so it refreshes without the client_secret.json present in GitHub Actions.
"""
import argparse
import json
import os
import sys

# Allow running from anywhere inside the repo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("Usage:")[0])
    parser.add_argument("channel", help="exact channel_name from channels.json (e.g. GAMES)")
    args = parser.parse_args()

    sanitized = "".join([c if c.isalnum() else "_" for c in args.channel])
    token_path = os.path.join(BASE_DIR, "data", "channels", sanitized, "token.json")
    client_secret_path = os.path.join(BASE_DIR, "client_secret.json")

    if not os.path.exists(client_secret_path):
        sys.exit(f"[!] Missing {client_secret_path}. Put your client_secret.json in the repo root first.")

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        sys.exit("[!] Missing Google libs. Install: pip install google-api-python-client google-auth-oauthlib google-auth")

    print(f"[*] Opening browser to authorize channel '{args.channel}'...")
    print("    Sign in with the Google account that OWNS this YouTube channel,")
    print("    approve the scope, then come back here.\n")

    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
    creds = flow.run_local_server(port=0)

    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    token_json = creds.to_json()
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(token_json)

    print(f"\n[+] Token saved to: {token_path}")
    print("[+] Copy the ENTIRE JSON below into the GitHub secret "
          f"YOUTUBE_TOKEN_JSON_{args.channel.upper()}\n")
    print(json.dumps(json.loads(token_json), indent=2))

if __name__ == "__main__":
    main()