import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

# Railway Variables에서 숫자만 바꾸면 바로 반영됩니다.
CHECK_INTERVAL = max(30, int(os.getenv("CHECK_INTERVAL", "30")))
HEARTBEAT_HOURS = max(1, int(os.getenv("HEARTBEAT_HOURS", "6")))
REQUEST_TIMEOUT = max(5, int(os.getenv("REQUEST_TIMEOUT", "20")))
ERROR_ALERT_MINUTES = max(1, int(os.getenv("ERROR_ALERT_MINUTES", "5")))
REOPEN_URGENT_SECONDS = max(30, int(os.getenv("REOPEN_URGENT_SECONDS", "90")))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN 환경변수가 없습니다. Railway Variables에 등록하세요.")
if not CHAT_ID:
    raise RuntimeError("CHAT_ID 환경변수가 없습니다. Railway Variables에 등록하세요.")
