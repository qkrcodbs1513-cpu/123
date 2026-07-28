"""달빛공원(송도테니스) 예약 가능 시간 수집기.

Prime Reserve의 실제 DOM 구조를 기준으로 동작합니다.
- 목록 화면에서 5~14번 코트를 찾음
- 활성화된 '예약' 버튼만 클릭
- 상세 화면의 button[data-date-key]에서 예약 가능 날짜를 찾음
- 해당 날짜를 클릭한 뒤 시간대 버튼을 읽음
- aria-label='목록으로' 버튼으로 목록에 복귀
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import REQUEST_TIMEOUT, SONGDO_AUTH_STATE, SONGDO_DEBUG_DIR, SONGDO_URL

KST = timezone(timedelta(hours=9))
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
TIME_RE = re.compile(r"(?P<sh>\d{1,2}):(?P<sm>\d{2})\s*[-~–]\s*(?P<eh>\d{1,2}):(?P<em>\d{2})")
AVAIL_RE = re.compile(r"(?P<available>\d+)\s*/\s*(?P<total>\d+)\s*예약\s*가능")
TARGET_COURTS = tuple(range(5, 15))


def _log(message: str) -> None:
    print(f"[DALBIT] {message}", flush=True)


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


def _make_slot(court_num: int, date_raw: str, text: str) -> dict[str, Any] | None:
    match = TIME_RE.search(text)
    if not match:
        return None
    if any(word in text for word in ("예약됨", "마감", "불가", "품절", "종료")):
        return None
    sh, sm = int(match["sh"]), int(match["sm"])
    eh, em = int(match["eh"]), int(match["em"])
    date_obj = datetime.strptime(date_raw, "%Y-%m-%d").date()
    return {
        "site": "songdo",
        "court_code": f"S{court_num:02d}",
        "court": f"달빛공원 {court_num}번 코트",
        "date_raw": date_raw,
        "date": f"{date_raw} ({WEEKDAYS_KO[date_obj.weekday()]})",
        "time_raw": f"{sh:02d}:{sm:02d}",
        "time": f"{sh:02d}:{sm:02d}~{eh:02d}:{em:02d}",
        "start_hour": sh,
        "weekday_num": date_obj.weekday(),
        "url": SONGDO_URL,
    }


def _wait_for_list(page: Any, timeout_ms: int = 20000) -> None:
    """상세 화면이면 목록으로 복귀하고 코트 목록 렌더링을 기다립니다."""
    back = page.locator('button[aria-label="목록으로"]')
    if back.count() > 0:
        try:
            back.first.click(timeout=3000)
        except Exception:
            page.goto(SONGDO_URL, wait_until="domcontentloaded")

    # 예약 탭이 다른 탭으로 열렸을 경우 다시 선택합니다.
    try:
        page.get_by_role("button", name="예약", exact=True).first.click(timeout=2500)
    except Exception:
        pass

    page.wait_for_function(
        """() => {
            const hs = [...document.querySelectorAll('h2')].map(x => (x.textContent || '').trim());
            return hs.some(x => /^5번\s*코트$/.test(x)) && hs.some(x => /^14번\s*코트$/.test(x));
        }""",
        timeout=timeout_ms,
    )


def _court_card(page: Any, court_num: int) -> Any:
    """코트 제목을 포함하면서 예약 버튼도 포함하는 가장 가까운 부모 요소."""
    title = page.get_by_role("heading", name=re.compile(rf"^{court_num}번\s*코트$"), exact=True)
    if title.count() == 0:
        return None
    # 카드 클래스에 의존하지 않고 '예약' 버튼을 가진 가장 가까운 조상을 찾습니다.
    card = title.first.locator(
        "xpath=ancestor::*[.//button[normalize-space()='예약']][1]"
    )
    return card if card.count() else None


def _available_dates(page: Any) -> list[tuple[str, int, int]]:
    found: list[tuple[str, int, int]] = []
    buttons = page.locator("button[data-date-key]")
    for i in range(buttons.count()):
        button = buttons.nth(i)
        try:
            date_key = button.get_attribute("data-date-key") or ""
            title = button.locator("[title*='예약 가능']").first.get_attribute("title") or ""
            match = AVAIL_RE.search(title)
            if not date_key or not match:
                continue
            available, total = int(match["available"]), int(match["total"])
            if available > 0 and not button.is_disabled():
                found.append((date_key, available, total))
        except Exception:
            continue
    return found


def _extract_times(page: Any, court_num: int, date_raw: str) -> list[dict[str, Any]]:
    """날짜 선택 후 표시된 시간대 요소에서 예약 가능한 시간만 읽습니다."""
    page.wait_for_timeout(700)
    slots: list[dict[str, Any]] = []
    # 버튼/role=button 모두 확인하되 날짜·달력 버튼은 TIME_RE가 없어 자동 제외됩니다.
    elements = page.locator("button, [role='button']")
    for i in range(elements.count()):
        element = elements.nth(i)
        try:
            text = " ".join((element.inner_text(timeout=600) or "").split())
            if not TIME_RE.search(text) or element.is_disabled(timeout=300):
                continue
            slot = _make_slot(court_num, date_raw, text)
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
        _log("v6.1.6 ACTUAL-DOM 수집 시작 — 5~14번 전체 코트")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context_args: dict[str, Any] = {"locale": "ko-KR", "timezone_id": "Asia/Seoul"}
            storage_state = _load_storage_state()
            if storage_state:
                context_args["storage_state"] = storage_state
            context = browser.new_context(**context_args)
            page = context.new_page()
            page.set_default_timeout(REQUEST_TIMEOUT * 1000)

            _log(f"페이지 접속: {SONGDO_URL}")
            page.goto(SONGDO_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            _wait_for_list(page)
            _log("코트 목록 렌더링 완료")

            for court_num in TARGET_COURTS:
                try:
                    # 매 코트마다 목록 상태를 보장합니다.
                    _wait_for_list(page)
                    card = _court_card(page, court_num)
                    if card is None:
                        errors.append(f"달빛공원 {court_num}번: 코트 카드를 찾지 못했습니다.")
                        continue

                    reserve = card.get_by_role("button", name="예약", exact=True).first
                    if reserve.count() == 0:
                        errors.append(f"달빛공원 {court_num}번: 예약 버튼을 찾지 못했습니다.")
                        continue
                    if reserve.is_disabled():
                        _log(f"{court_num}번: 예약 버튼 비활성 — 건너뜀")
                        continue

                    _log(f"{court_num}번: 상세 화면 진입")
                    reserve.click(timeout=4000)
                    page.get_by_role("heading", name=re.compile(rf"^{court_num}번\s*코트$"), exact=True).wait_for(timeout=10000)
                    page.locator('button[aria-label="목록으로"]').wait_for(timeout=10000)

                    dates = _available_dates(page)
                    _log(f"{court_num}번: 예약 가능 날짜 {len(dates)}개")
                    for date_raw, available, total in dates:
                        try:
                            date_button = page.locator(f'button[data-date-key="{date_raw}"]')
                            date_button.click(timeout=3000)
                            found = _extract_times(page, court_num, date_raw)
                            slots.extend(found)
                            _log(f"{court_num}번 {date_raw}: {available}/{total}, 시간 슬롯 {len(found)}개")
                        except Exception as exc:
                            errors.append(
                                f"달빛공원 {court_num}번 {date_raw}: {type(exc).__name__} - {exc}"
                            )

                    page.locator('button[aria-label="목록으로"]').click(timeout=4000)
                    _wait_for_list(page)
                except Exception as exc:
                    errors.append(f"달빛공원 {court_num}번: {type(exc).__name__} - {exc}")
                    try:
                        page.goto(SONGDO_URL, wait_until="domcontentloaded")
                        page.wait_for_timeout(1500)
                    except Exception:
                        pass

            context.storage_state(path=str(debug_dir / "songdo_storage_state.json"))
            (debug_dir / "songdo_last.html").write_text(page.content(), encoding="utf-8")
            browser.close()
    except Exception as exc:
        errors.append(f"달빛공원: {type(exc).__name__} - {exc}")

    unique = {f"{s['court_code']}|{s['date_raw']}|{s['time_raw']}": s for s in slots}
    result = sorted(unique.values(), key=lambda s: (s["date_raw"], s["start_hour"], s["court_code"]))
    _log(f"수집 종료: 가능 슬롯 {len(result)}개, 오류 {len(errors)}개")
    return result, errors
