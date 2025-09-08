import os
import json
import logging
from flask import Flask, request, jsonify
import requests

# === Hardcoded credentials (you provided) ===
APP_ID = "cli_a834297edb38de1a"
APP_SECRET = "WLzBxwkIcrTiemSVhDb7NhLcmUdrIL4J"

app = Flask(__name__)

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
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    logging.info(f"Lark send status={r.status_code}, resp={data}")
    r.raise_for_status()
    if isinstance(data, dict) and data.get("code", 0) != 0:
        raise RuntimeError(f"Lark send error: {data}")
    return True

def extract_plain_text(message_obj: dict) -> str:
    content_raw = message_obj.get("content", "")
    try:
        parsed = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
    except Exception:
        parsed = {}
    text = parsed.get("text") or ""
    return str(text).strip()

@app.route("/", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "fikabot", "status": "running"})

@app.route("/lark", methods=["POST"])
def lark_events():
    data = request.get_json(force=True, silent=True) or {}

    # URL verification handshake
    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})

    # Message events
    event = data.get("event", {})
    if event.get("type") == "message":
        msg = event.get("message", {}) or {}
        chat_id = msg.get("chat_id")
        user_text = extract_plain_text(msg).lower()
        logging.info(f"Incoming message: chat_id={chat_id}, text={user_text!r}")

        if "fika" in user_text:
            try:
                send_text_to_chat(chat_id, "☕️ FIKA is at 09:59 & 14:59 CET!")
            except Exception as e:
                logging.exception("Failed to send reply")
                return jsonify({"code": 0, "msg": f"handled-with-error: {e}"}), 200

    return jsonify({"code": 0, "msg": "ok"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
