import logging
import requests
from requests.auth import HTTPBasicAuth
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def format_report_message(report):
    msg_lines = ["🤖 YouTube Shorts Automation Report", "="*30]
    for r in report:
        status_emoji = "✅" if r['status'] == "Success" else "⚠️" if r['status'] == "Partial Success" else "❌" if r['status'] == "Failed" else "⏭️"
        msg_lines.append(f"{status_emoji} {r['channel_name']}: {r['status']}")
        msg_lines.append(f"   Shorts Created: {r['shorts_created']}")
        msg_lines.append(f"   Videos Created: {r.get('videos_created', 0)}")
        if r['error']:
            msg_lines.append(f"   Error: {r['error'][:80]}")
        msg_lines.append("-"*30)
    return "\n".join(msg_lines)

def send_twilio_sms(body):
    if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and config.TWILIO_FROM_NUMBER and config.USER_PHONE_NUMBER):
        logging.warning("Twilio credentials missing. Skipping SMS.")
        return
    url = f"https://api.twilio.org/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Messages.json"
    data = {
        "To": config.USER_PHONE_NUMBER,
        "From": config.TWILIO_FROM_NUMBER,
        "Body": body
    }
    try:
        response = requests.post(url, data=data, auth=HTTPBasicAuth(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN), timeout=10)
        response.raise_for_status()
        logging.info("[+] SMS notification sent successfully via Twilio.")
    except Exception as e:
        logging.error(f"[!] Failed to send Twilio SMS: {e}")

def send_telegram_msg(body):
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        logging.warning("Telegram credentials missing. Skipping Telegram notification.")
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": body
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("[+] Telegram notification sent successfully.")
    except Exception as e:
        logging.error(f"[!] Failed to send Telegram notification: {e}")

def notify_report(report):
    if config.NOTIFICATION_PROVIDER == "NONE":
        return
    
    body = format_report_message(report)
    
    if config.NOTIFICATION_PROVIDER == "TWILIO":
        send_twilio_sms(body)
    elif config.NOTIFICATION_PROVIDER == "TELEGRAM":
        send_telegram_msg(body)
