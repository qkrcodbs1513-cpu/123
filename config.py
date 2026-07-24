import json

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

BOT_TOKEN = config["bot_token"]
CHAT_ID = config["chat_id"]