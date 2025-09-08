import os
import json
import logging
from flask import Flask, request, jsonify
import requests

# === Your Lark credentials ===
APP_ID = "cli_a834297edb38de1a"
APP_SECRET = "WLzBxwkIcrTiemSVhDb7NhLcmUdrIL4J"

app = Flask(__name__)

# ===== Helpers =====
def get_tenant_access_token():
    """
    Get a tenant access token for this app.
    """
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Lark token error: {data}")
    return data["tenant_access_token"]

def send_text_to_chat(chat_id: str, text: str):
    """
    Send a plain text message into the chat.
    """
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

# ===== Routes =====
@app.route("/", methods=["GET"])
def health():
    """
    Health check for Render.
    """
    return jsonify({"ok": True, "service": "fikabot", "status": "running"})

@app.route("/lark", methods=["POST"])
def lark_events():
    """
    Handle Lark events (verification + messages).
    """
    data = request.get_json(force=True, silent=True) or {}

    # 1) URL verification handshake
    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})

    # 2) Event handling
    event = data.get("event", {})
    if event.get("type") == "message":
        msg = event.get("message", {}) or {}
        chat_id = msg.get("chat_id")

        # Extract text + mentions
        try:
            parsed = json.loads(msg.get("content", "{}"))
            text = (parsed.get("text") or "").lower()
            mentions = parsed.get("mentions", [])
        except Exception:
            text, mentions = "", []

        # Check if bot was tagged
        bot_was_tagged = any(m.get("name") for m in mentions)

        # Only reply if @mentioned AND "fika" in text
        if bot_was_tagged and "fika" in text:
            send_text_to_chat(chat_id, "☕️ FIKA is at 09:59 & 14:59 CET!")

    # Always return quickly so Lark stops retrying
    return jsonify({"code": 0, "msg": "ok"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)

