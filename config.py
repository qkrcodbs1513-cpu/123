import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

# 기본값: 30초마다 검사, 매일 오전 9시(KST)에 생존 알림
CHECK_INTERVAL = max(30, int(os.getenv("CHECK_INTERVAL", "30")))
HEARTBEAT_HOUR = min(23, max(0, int(os.getenv("HEARTBEAT_HOUR", "9"))))
REQUEST_TIMEOUT = max(5, int(os.getenv("REQUEST_TIMEOUT", "20")))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN 환경변수가 없습니다. Railway Variables에 등록하세요.")
if not CHAT_ID:
    raise RuntimeError("CHAT_ID 환경변수가 없습니다. Railway Variables에 등록하세요.")
