from __future__ import annotations

import os
from pathlib import Path


def _int_env(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(minimum, int(raw))
    except ValueError as exc:
        raise RuntimeError(f"{name} 환경변수는 정수여야 합니다: {raw!r}") from exc


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

CHECK_INTERVAL = _int_env("CHECK_INTERVAL", 30, 15)
HEARTBEAT_HOURS = _int_env("HEARTBEAT_HOURS", 6, 1)
REQUEST_TIMEOUT = _int_env("REQUEST_TIMEOUT", 20, 5)
ERROR_ALERT_MINUTES = _int_env("ERROR_ALERT_MINUTES", 5, 1)
TELEGRAM_POLL_TIMEOUT = _int_env("TELEGRAM_POLL_TIMEOUT", 25, 5)

DATA_DIR = Path(os.getenv("DATA_DIR", ".")).resolve()
STATE_FILE = DATA_DIR / os.getenv("STATE_FILE", "bot_state.json")
SETTINGS_FILE = DATA_DIR / os.getenv("SETTINGS_FILE", "bot_settings.json")

DEFAULT_COURTS = ["A", "B", "C"]
DEFAULT_WEEKDAY_HOURS = [20]
DEFAULT_WEEKEND_HOURS: list[int] | None = None  # None = 모든 시간

SONGDO_URL = os.getenv("SONGDO_URL", "https://songdotennis.co.kr/songdo-tennis?tab=reservations").strip()
SONGDO_ENABLED_DEFAULT = os.getenv("SONGDO_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
SONGDO_COURTS = [x.strip() for x in os.getenv("SONGDO_COURTS", "").split(",") if x.strip()]
SONGDO_AUTH_STATE = os.getenv("SONGDO_AUTH_STATE", "").strip()
SONGDO_DEBUG_DIR = os.getenv("SONGDO_DEBUG_DIR", str(DATA_DIR / "songdo_debug"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN 환경변수가 없습니다. Railway Variables에 등록하세요.")
if not CHAT_ID:
    raise RuntimeError("CHAT_ID 환경변수가 없습니다. Railway Variables에 등록하세요.")
