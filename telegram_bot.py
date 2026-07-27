import html
import time
from typing import Optional

import requests

from config import BOT_TOKEN, CHAT_ID

_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def send_telegram_message(
    message: str,
    retries: int = 3,
    button_url: str | None = None,
    button_text: str = "📲 예약하기",
) -> bool:
    payload: dict[str, object] = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    if button_url:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": button_text, "url": button_url}]]
        }

    last_error: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(_API_URL, json=payload, timeout=15)
            if response.status_code == 200:
                print("📩 텔레그램 전송 성공", flush=True)
                return True
            last_error = f"HTTP {response.status_code}: {response.text[:500]}"
        except requests.RequestException as exc:
            last_error = str(exc)

        print(f"❌ 텔레그램 전송 실패 ({attempt}/{retries}): {last_error}", flush=True)
        if attempt < retries:
            time.sleep(attempt * 2)

    return False


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)
