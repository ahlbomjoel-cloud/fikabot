import os
import json
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify
import requests

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# === Lark credentials from environment variables ===
APP_ID = os.getenv("LARK_APP_ID", "").strip()
APP_SECRET = os.getenv("LARK_APP_SECRET", "").strip()

# Validate that credentials are provided
if not APP_ID or not APP_SECRET:
    logging.warning("Lark credentials not found in environment variables")

# Debug mode setting
DEBUG_VERBOSE = os.getenv("DEBUG_VERBOSE", "0") == "1"

# Timezone configuration
TZ = ZoneInfo("Europe/Stockholm")

# Fika time slots
FIKA_SLOTS = (time(10, 0), time(15, 0))

# ---------- Helper Functions ----------
def get_tenant_access_token():
    """Get tenant access token from Lark API"""
    if not APP_ID or not APP_SECRET:
        raise ValueError("Lark credentials not configured")
    
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": APP_ID, "app_secret": APP_SECRET}
    logging.info("Fetching tenant_access_token")
    
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    
    if data.get("code", 0) != 0:
        raise RuntimeError(f"Lark token error: {data}")
    
    return data["tenant_access_token"]

def send_text_to_chat(chat_id: str, text: str):
    """Send a text message to a Lark chat"""
    try:
        token = get_tenant_access_token()
        url = "https://open.larksuite.com/open-apis/im/v1/messages"
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "receive_id_type": "chat_id",
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        }
        
        if DEBUG_VERBOSE:
            logging.info(f"POST {url} payload={payload}")
            
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        r.raise_for_status()
        
        if DEBUG_VERBOSE:
            data = r.json()
            logging.info(f"Lark send status={r.status_code} resp={data}")
            
        return True
    except Exception as e:
        logging.error(f"Failed to send message to chat {chat_id}: {e}")
        return False

def next_fika(now: datetime):
    """Calculate the next fika time"""
    today_slots = [datetime.combine(now.date(), t, tzinfo=TZ) for t in FIKA_SLOTS]
    for dt in today_slots:
        if dt > now:
            return dt, dt.strftime("%H:%M")
    
    tomorrow = now.date() + timedelta(days=1)
    dt = datetime.combine(tomorrow, FIKA_SLOTS[0], tzinfo=TZ)
    return dt, dt.strftime("%H:%M")

def minutes_until(target: datetime, now: datetime) -> int:
    """Calculate minutes until target time"""
    delta = target - now
    return max(0, int(delta.total_seconds() // 60))

# ---------- Routes ----------
@app.route("/", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({
        "ok": True, 
        "service": "fikabot", 
        "status": "running",
        "lark_configured": bool(APP_ID and APP_SECRET)
    })

@app.route("/lark", methods=["POST"])
def lark_events():
    """Handle incoming Lark events"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        if DEBUG_VERBOSE:
            logging.info(f"RAW EVENT: {data}")

        # URL verification handshake
        if "challenge" in data:
            challenge = data["challenge"]
            logging.info(f"Verification challenge received: {challenge}")
            return jsonify({"challenge": challenge})

        # Normal events
        event = data.get("event", {})
        etype = data.get("header", {}).get("event_type")
        logging.info(f"Event type={etype}")

        if etype == "im.message.receive_v1":
            msg = event.get("message", {})
            chat_id = msg.get("chat_id")
            content_raw = msg.get("content", "{}")

            try:
                parsed = json.loads(content_raw)
                text = (parsed.get("text") or "").lower()
            except Exception:
                text = ""
                
            if chat_id and "fika" in text:
                now = datetime.now(TZ)
                target_dt, target_label = next_fika(now)
                mins = minutes_until(target_dt, now)
                
                if mins == 0:
                    reply = f"☕️ It's FIKA time right now ({target_label})!"
                else:
                    plural = "s" if mins != 1 else ""
                    reply = f"☕️ Next fika is at {target_label} (local).\n⏳ {mins} minute{plural} left."
                
                ok = send_text_to_chat(chat_id, reply)
                logging.info(f"Sent reply ok={ok}")

        return jsonify({"code": 0, "msg": "ok"})

    except Exception as e:
        logging.exception(f"Error in /lark: {str(e)}")
        return jsonify({"code": 0, "msg": "handled-error"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
