import requests
import config
from app import app
from flask import render_template, request, jsonify
from flask_login import login_required


AI_MODEL = "Qwen 3.5 Flash"


@app.route("/ai_chat")
@login_required
def ai_chat_page():
    return render_template("ai_chat.html")


@app.route("/api/ai_chat/send", methods=["POST"])
@login_required
def ai_chat_send():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages")

    if not messages or not isinstance(messages, list):
        return jsonify({"error": "empty_message"}), 400

    try:
        response = requests.post(
            f"{config.OPENAI_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 800,
                "stream": False,
            },
            timeout=30,
        )
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except requests.RequestException:
        return jsonify({"error": "ai_unavailable"}), 502
