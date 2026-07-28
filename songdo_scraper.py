"""달빛공원 예약 페이지 브라우저 수집기(베타).

사이트가 WebSocket/클라이언트 캐시 기반이라 requests만으로는 슬롯을 읽기 어렵습니다.
Playwright로 실제 예약 화면을 렌더링한 뒤, 화면에 표시되는 코트/시간 버튼을 수집합니다.
기존 연수문화공원 감시는 이 모듈과 독립적으로 유지됩니다.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import (
    REQUEST_TIMEOUT,
    SONGDO_AUTH_STATE,
    SONGDO_COURTS,
    SONGDO_DEBUG_DIR,
    SONGDO_URL,
)

KST = timezone(timedelta(hours=9))
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
TIME_RE = re.compile(r"(?P<sh>\d{1,2}):(?P<sm>\d{2})\s*[-~–]\s*(?P<eh>\d{1,2}):(?P<em>\d{2})")
COURT_RE = re.compile(r"(?P<num>\d{1,2})\s*번\s*코트")
DATE_RE = re.compile(r"(20\d{2})[-./년\s]+(\d{1,2})[-./월\s]+(\d{1,2})")


def _load_storage_state() -> dict[str, Any] | None:
    raw = SONGDO_AUTH_STATE.strip()
    if not raw:
        return None
    path = Path(raw)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("SONGDO_AUTH_STATE는 파일 경로 또는 JSON 문자열이어야 합니다.") from exc


def _normalise_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    try:
        return datetime(int(match[1]), int(match[2]), int(match[3]), tzinfo=KST).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _slot_from_text(court_num: str, date_raw: str, text: str, disabled: bool) -> dict[str, Any] | None:
    match = TIME_RE.search(text)
    if not match:
        return None
    unavailable_words = ("예약됨", "마감", "불가", "품절", "종료")
    if disabled or any(word in text for word in unavailable_words):
        return None
    start_hour = int(match["sh"])
    start_minute = int(match["sm"])
    end_hour = int(match["eh"])
    end_minute = int(match["em"])
    date_obj = datetime.strptime(date_raw, "%Y-%m-%d").date()
    return {
        "site": "songdo",
        "court_code": f"S{court_num}",
        "court": f"달빛공원 {court_num}번 코트",
        "date_raw": date_raw,
        "date": f"{date_raw} ({WEEKDAYS_KO[date_obj.weekday()]})",
        "time_raw": f"{start_hour:02d}:{start_minute:02d}",
        "time": f"{start_hour:02d}:{start_minute:02d}~{end_hour:02d}:{end_minute:02d}",
        "start_hour": start_hour,
        "weekday_num": date_obj.weekday(),
        "url": SONGDO_URL,
    }


def _extract_visible_slots(page: Any, court_num: str, date_raw: str) -> list[dict[str, Any]]:
    # 예약 시간은 대개 button 또는 role=button 요소로 표시됩니다.
    elements = page.locator("button, [role='button']")
    slots: list[dict[str, Any]] = []
    for index in range(elements.count()):
        element = elements.nth(index)
        try:
            text = " ".join((element.inner_text(timeout=1000) or "").split())
            if not TIME_RE.search(text):
                continue
            disabled = element.is_disabled(timeout=500)
            slot = _slot_from_text(court_num, date_raw, text, disabled)
            if slot:
                slots.append(slot)
        except Exception:
            continue
    return slots


def get_songdo_slots_with_status() -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    slots: list[dict[str, Any]] = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], ["달빛공원: playwright가 설치되지 않았습니다."]

    debug_dir = Path(SONGDO_DEBUG_DIR)
    debug_dir.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context_args: dict[str, Any] = {"locale": "ko-KR", "timezone_id": "Asia/Seoul"}
            storage_state = _load_storage_state()
            if storage_state:
                context_args["storage_state"] = storage_state
            context = browser.new_context(**context_args)
            page = context.new_page()
            page.set_default_timeout(REQUEST_TIMEOUT * 1000)
            page.goto(SONGDO_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)

            # 공지 팝업이 있으면 닫습니다.
            for label in ("닫기", "확인"):
                try:
                    page.get_by_role("button", name=label).first.click(timeout=800)
                except Exception:
                    pass

            # 예약 탭 진입.
            try:
                page.get_by_text("예약", exact=True).first.click(timeout=3000)
                page.wait_for_timeout(1500)
            except Exception:
                pass

            body_text = page.locator("body").inner_text()

            # 화면에서 날짜를 찾습니다. 찾지 못하면 오늘 날짜를 사용합니다.
            date_raw = _normalise_date(body_text) or datetime.now(KST).strftime("%Y-%m-%d")

            configured = set(SONGDO_COURTS)
            court_candidates: list[tuple[str, Any]] = []
            buttons = page.locator("button, [role='button']")
            for index in range(buttons.count()):
                element = buttons.nth(index)
                try:
                    text = " ".join((element.inner_text(timeout=700) or "").split())
                except Exception:
                    continue
                match = COURT_RE.search(text)
                if match and (not configured or match["num"] in configured):
                    court_candidates.append((match["num"], element))

            if not court_candidates:
                # UI에서 코트 선택이 별도 제공되지 않고 이미 한 코트가 열린 경우를 위한 대체 경로.
                current_court = COURT_RE.search(body_text)
                if current_court:
                    slots.extend(_extract_visible_slots(page, current_court["num"], date_raw))
                else:
                    raise RuntimeError("코트 선택 요소를 찾지 못했습니다. 사이트 UI가 변경되었을 수 있습니다.")
            else:
                seen_courts: set[str] = set()
                for court_num, element in court_candidates:
                    if court_num in seen_courts:
                        continue
                    seen_courts.add(court_num)
                    try:
                        element.click(timeout=2500)
                        page.wait_for_timeout(700)
                        current_text = page.locator("body").inner_text()
                        current_date = _normalise_date(current_text) or date_raw
                        slots.extend(_extract_visible_slots(page, court_num, current_date))
                    except Exception as exc:
                        errors.append(f"달빛공원 {court_num}번 코트: {type(exc).__name__} - {exc}")

            # 다음 분석 때 사용할 수 있도록 로그인 상태와 HTML을 저장합니다.
            context.storage_state(path=str(debug_dir / "songdo_storage_state.json"))
            (debug_dir / "songdo_last.html").write_text(page.content(), encoding="utf-8")
            browser.close()
    except Exception as exc:
        errors.append(f"달빛공원: {type(exc).__name__} - {exc}")

    unique = {f"{s['court_code']}|{s['date_raw']}|{s['time_raw']}": s for s in slots}
    result = sorted(unique.values(), key=lambda s: (s["date_raw"], s["start_hour"], s["court_code"]))
    return result, errors
