from __future__ import annotations

import html
import time
from typing import Any, Optional

import requests

from config import BOT_TOKEN, CHAT_ID, REQUEST_TIMEOUT

BASE_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _post(method: str, payload: dict[str, Any], retries: int = 3) -> dict[str, Any] | None:
    last_error: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                f"{BASE_API}/{method}",
                json=payload,
                timeout=REQUEST_TIMEOUT + 5,
            )
            data = response.json()
            if response.status_code == 200 and data.get("ok"):
                return data
            # Telegram은 동일한 본문/버튼으로 editMessageText를 호출하면 400을 반환한다.
            # 실제 오류가 아니라 변경할 내용이 없다는 뜻이므로 성공(no-op)으로 처리한다.
            description = str(data.get("description", "")) if isinstance(data, dict) else ""
            if method == "editMessageText" and "message is not modified" in description.lower():
                return {"ok": True, "result": {"unchanged": True}}
            last_error = f"HTTP {response.status_code}: {response.text[:500]}"
        except (requests.RequestException, ValueError) as exc:
            last_error = str(exc)

        print(f"❌ Telegram {method} 실패 ({attempt}/{retries}): {last_error}", flush=True)
        if attempt < retries:
            time.sleep(attempt * 2)
    return None


def send_telegram_message(
    message: str,
    reply_markup: dict[str, Any] | None = None,
    retries: int = 3,
) -> bool:
    payload: dict[str, Any] = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _post("sendMessage", payload, retries) is not None


def edit_telegram_message(
    message_id: int,
    message: str,
    reply_markup: dict[str, Any] | None = None,
) -> bool:
    payload: dict[str, Any] = {
        "chat_id": CHAT_ID,
        "message_id": message_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _post("editMessageText", payload, 2) is not None


def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    _post(
        "answerCallbackQuery",
        {"callback_query_id": callback_query_id, "text": text, "show_alert": False},
        1,
    )


def get_updates(offset: int, timeout: int) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            f"{BASE_API}/getUpdates",
            params={"offset": offset, "timeout": timeout, "allowed_updates": '["message","callback_query"]'},
            timeout=timeout + 10,
        )
        data = response.json()
        if response.status_code == 200 and data.get("ok"):
            return data.get("result", [])
    except (requests.RequestException, ValueError) as exc:
        print(f"⚠️ Telegram getUpdates 오류: {exc}", flush=True)
    return []
