"""
Telegram Listener — Polling based, koi webhook server nahi chahiye
====================================================================
Ye script GitHub Actions cron (har 2-5 minute) se chalti hai. Ye
Telegram ke getUpdates endpoint se check karti hai:

  1. Kya kisi ne "/start" bheja hai -> trending_finder.py chala do
  2. Kya kisi ne "✅ Use" / "❌ Skip" button dabaya hai -> use.json /
     skipped list mein record kar do (future scoring behtar karne ke liye)

Last processed update_id ek chhoti si state file (offset.txt) mein
GitHub repo ke andar hi save hota hai, taaki dubara wahi update process
na ho.
"""

import os
import json
import subprocess
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
OFFSET_FILE = "offset.txt"
CHOICES_FILE = "user_choices.json"


def get_offset():
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE) as f:
            return int(f.read().strip() or 0)
    return 0


def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))


def load_choices():
    if os.path.exists(CHOICES_FILE):
        with open(CHOICES_FILE) as f:
            return json.load(f)
    return []


def save_choices(choices):
    with open(CHOICES_FILE, "w", encoding="utf-8") as f:
        json.dump(choices, f, ensure_ascii=False, indent=2)


def answer_callback(callback_id, text):
    requests.post(f"{TELEGRAM_API}/answerCallbackQuery", data={
        "callback_query_id": callback_id,
        "text": text,
    }, timeout=10)


def main():
    offset = get_offset()
    resp = requests.get(f"{TELEGRAM_API}/getUpdates", params={
        "offset": offset + 1,
        "timeout": 0,
    }, timeout=20)
    updates = resp.json().get("result", [])

    choices = load_choices()
    run_finder = False

    for update in updates:
        offset = max(offset, update["update_id"])

        # /start command
        msg = update.get("message", {})
        if msg.get("text", "").strip().lower() == "/start":
            run_finder = True

        # Inline button press
        cb = update.get("callback_query")
        if cb:
            data = cb.get("data", "")  # format: action|channel_key|index
            parts = data.split("|")
            if len(parts) == 3:
                action, channel_key, idx = parts
                choices.append({"action": action, "channel": channel_key, "index": idx})
                answer_callback(cb["id"], "✅ Noted!" if action == "use" else "Skipped")

    save_offset(offset)
    save_choices(choices)

    if run_finder:
        subprocess.run(["python", "trending_finder.py"], check=False)


if __name__ == "__main__":
    main()
