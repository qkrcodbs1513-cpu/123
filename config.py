from __future__ import annotations
import os
from pathlib import Path

def int_env(name: str, default: int, minimum: int=1) -> int:
    try: return max(minimum, int(os.getenv(name, str(default))))
    except ValueError as exc: raise RuntimeError(f"{name} 환경변수는 정수여야 합니다.") from exc

BOT_TOKEN=os.getenv("BOT_TOKEN","").strip()
ADMIN_CHAT_ID=os.getenv("ADMIN_CHAT_ID", os.getenv("CHAT_ID","")).strip()
CHECK_INTERVAL=int_env("CHECK_INTERVAL",30,15)
REQUEST_TIMEOUT=int_env("REQUEST_TIMEOUT",20,5)
TELEGRAM_POLL_TIMEOUT=int_env("TELEGRAM_POLL_TIMEOUT",25,5)
ERROR_ALERT_MINUTES=int_env("ERROR_ALERT_MINUTES",5,1)
DATA_DIR=Path(os.getenv("DATA_DIR", ".")).resolve()
DB_FILE=DATA_DIR/os.getenv("DB_FILE","chaeniss_v8.json")
LOG_LIMIT=int_env("LOG_LIMIT",100,20)
SONGDO_URL=os.getenv("SONGDO_URL","https://songdotennis.co.kr/songdo-tennis?tab=reservations").strip()
SONGDO_AUTH_STATE=os.getenv("SONGDO_AUTH_STATE","").strip()
SONGDO_DEBUG_DIR=os.getenv("SONGDO_DEBUG_DIR",str(DATA_DIR/'songdo_debug'))
SAEACHIM_URL=os.getenv("SAEACHIM_URL","https://reserve.insiseol.or.kr/rent/rentalSchedule?up_id=07").strip()
if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN 환경변수가 없습니다.")
