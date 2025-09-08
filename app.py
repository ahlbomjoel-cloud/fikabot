import os
import json
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, request, Response, jsonify
import requests

# === Your Lark credentials ===
APP_ID = os.getenv("LARK_APP_ID", "cli_a834297edb38de1a").strip()
APP_SECRET = os.getenv("LARK_APP_SECRET", "WLzBxwkIcrTiemSVhDb7NhLcmUdrIL4J").strip()

# Verbose logging toggle (set DEBUG_VERBOSE=1 in Render to dump raw payloads)
DEBUG_VERBOSE = os.getenv("DEBUG_VERBOSE", "0") == "1"

TZ = ZoneInfo("Europe/Stockholm")  # CET/CEST with DST handled

# ---------- Flask & logging ----------
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------- Helpers ----------
def get_tenant_access_token():
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": APP_ID, "app_secret": APP_SECRET}
    logging.info("Fetching tenant_access_token")
    resp = requests.post(url, json=payload, timeout=10)
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}
    logging.info(f"token resp status={resp.status_code} body={data}")
    resp.raise_for_status()
    if isinstance(data, dict) and data.get("code", 0) != 0:
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
    logging.info(f"POST {url} payload={payload}")
    r = requests.post(url, headers=headers, json=payload, timeout=10)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    logging.info(f"Lark send status={r.status_code} resp={data}")
    if isinstance(data, dict) and data.get("code", 0) != 0:
        logging.error(f"Lark send error code={data.get('code')} msg={data.get('msg')}")
    return r.ok

# ---------- Fika logic ----------
FIKA_SLOTS = (time(10, 0), time(15, 0))  # 10:00, 15:00 local

def next_fika(now: datetime):
    today_slots = [datetime.combine(now.date(), t, tzinfo=TZ) for t in FIKA_SLOTS]
    for dt in today_slots:
        if dt > now:
            return dt, dt.strftime("%H:%M")
    tomorrow = now.date() + timedelta(days=1)
    dt = datetime.combine(tomorrow, FIKA_SLOTS[0], tzinfo=TZ)
    return dt, dt.strftime("%H:%M")

def minutes_until(target: datetime, now: datetime) -> int:
    delta = target - now
    return max(0, int(delta.total_seconds() // 60))

# ---------- Routes ----------
@app.route("/", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "fikabot", "status": "running"})

@app.route("/lark", methods=["POST"])
def lark_events():
    try:
        data = request.get_json(force=True, silent=True) or {}
        if DEBUG_VERBOSE:
            logging.info(f"RAW EVENT: {data}")

        # 1) URL verification handshake
        if "challenge" in data:
            challenge = data["challenge"]
            logging.info(f"Verification challenge received: {challenge}")
            return Response(json.dumps({"challenge": challenge}), status=200, mimetype="application/json")

        # 2) Normal events
event = data.get("event", {})
etype = data.get("header", {}).get("event_type")
logging.info(f"Event type={etype}")

        if etype == "message":
            msg = event.get("message", {}) or {}
            chat_id = msg.get("chat_id")
            msg_id = msg.get("message_id")
            content_raw = msg.get("content", "{}")

            try:
                parsed = json.loads(content_raw)
            except Exception:
                parsed = {}
            text = (parsed.get("text") or "").lower()
            mentions = parsed.get("mentions", [])

            logging.info(f"message_id={msg_id} chat_id={chat_id} text={text!r} mentions={mentions}")

            # TEMP test: reply if text includes 'fika' (no need to @mention)
            if "fika" in text and chat_id:
                now = datetime.now(TZ)
                target_dt, target_label = next_fika(now)
                mins = minutes_until(target_dt, now)
                reply = (
                    f"☕️ It’s FIKA time right now ({target_label})!"
                    if mins == 0
                    else f"☕️ Next fika is at {target_label} (local).\n⏳ {mins} minute{'s' if mins != 1 else ''} left."
                )
                ok = send_text_to_chat(chat_id, reply)
                logging.info(f"Sent reply ok={ok} to chat_id={chat_id}")

        # Always ACK with JSON
        return Response('{"code":0,"msg":"ok"}', status=200, mimetype="application/json")

    except Exception:
        logging.exception("Error in /lark")
        return Response('{"code":0,"msg":"handled-error"}', status=200, mimetype="application/json")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
