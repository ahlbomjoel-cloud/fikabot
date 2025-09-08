import os
import json
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify, Response
import requests

# === Your Lark credentials ===
APP_ID = "cli_a834297edb38de1a"
APP_SECRET = "WLzBxwkIcrTiemSVhDb7NhLcmUdrIL4J"

TZ = ZoneInfo("Europe/Stockholm")  # CET/CEST with DST handled

app = Flask(__name__)

# --------- Lark helpers ---------
def get_tenant_access_token():
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Lark token error: {data}")
    return data["tenant_access_token"]

def send_text_to_chat(chat_id: str, text: str):
    token = get_tenant_access_token()
    url = "https://open.larksuite.com/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "receive_id_type": "chat_id",
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}),
    }
    r = requests.post(url, headers=headers, json=payload, timeout=10)
    logging.info(f"Lark send status={r.status_code}, resp={r.text}")
    return True

# --------- Fika time logic ---------
FIKA_SLOTS = (time(10, 0), time(15, 0))  # 10:00, 15:00 local

def next_fika(now: datetime):
    """Return (next_datetime, label_str) for the next fika slot from now."""
    today_slots = [datetime.combine(now.date(), t, tzinfo=TZ) for t in FIKA_SLOTS]
    # pick the first slot still ahead today
    for dt in today_slots:
        if dt > now:
            return dt, dt.strftime("%H:%M")
    # otherwise, tomorrow at first slot (10:00)
    tomorrow = now.date() + timedelta(days=1)
    dt = datetime.combine(tomorrow, FIKA_SLOTS[0], tzinfo=TZ)
    return dt, dt.strftime("%H:%M")

def minutes_until(target: datetime, now: datetime) -> int:
    """Whole minutes until target (floor)."""
    delta = target - now
    return max(0, int(delta.total_seconds() // 60))

# --------- Routes ---------
@app.route("/", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "fikabot", "status": "running"})

@app.route("/lark", methods=["POST"])
def lark_events():
    try:
        data = request.get_json(force=True, silent=True) or {}

        # URL verification handshake — must return pure JSON
        if "challenge" in data:
            return Response(
                json.dumps({"challenge": data["challenge"]}),
                status=200,
                mimetype="application/json",
            )

        event = data.get("event", {})
        if event.get("type") == "message":
            msg = event.get("message", {}) or {}
            chat_id = msg.get("chat_id")

            # Parse content to get text + mentions
            try:
                parsed = json.loads(msg.get("content", "{}"))
                text = (parsed.get("text") or "").lower()
                mentions = parsed.get("mentions", [])
            except Exception:
                text, mentions = "", []

            # Only respond when the bot is @mentioned
            bot_was_tagged = bool(mentions)

            if bot_was_tagged:
                now = datetime.now(TZ)
                target_dt, target_label = next_fika(now)
                mins = minutes_until(target_dt, now)

                if mins == 0:
                    reply = f"☕️ It’s FIKA time right now ({target_label})!"
                else:
                    reply = (
                        f"☕️ Next fika is at {target_label} (local).\n"
                        f"⏳ {mins} minute{'s' if mins != 1 else ''} left."
                    )
                # Optional: also require 'fika' in text -> if "fika" in text:
                send_text_to_chat(chat_id, reply)

        # Always ACK with JSON so Lark never sees an HTML error page
        return Response('{"code":0,"msg":"ok"}', status=200, mimetype="application/json")

    except Exception:
        logging.exception("Error in /lark")
        # Still return JSON, even if something went wrong
        return Response('{"code":0,"msg":"handled-error"}', status=200, mimetype="application/json")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
