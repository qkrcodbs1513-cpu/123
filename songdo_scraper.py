"""달빛공원 예약 페이지 수집기(ENABLED-CLICK v6.1.3 MODAL-RESET ALLCOURTS).

- Playwright 단계별 로그 출력
- 전체 수집 시간 제한
- WebSocket 수신 프레임 JSONL 저장
- DOM/웹소켓 양쪽에서 예약 가능 슬롯 후보 추출
- 실패해도 호출 측에 오류를 반환하고 메인 감시 루프는 계속 진행
"""
from __future__ import annotations

import json
import multiprocessing as mp
import re
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

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


def _normalise_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    try:
        return datetime(int(match[1]), int(match[2]), int(match[3]), tzinfo=KST).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _slot(court_num: str, date_raw: str, sh: int, sm: int, eh: int, em: int) -> dict[str, Any]:
    date_obj = datetime.strptime(date_raw, "%Y-%m-%d").date()
    return {
        "site": "songdo",
        "court_code": f"S{court_num}",
        "court": f"달빛공원 {court_num}번 코트",
        "date_raw": date_raw,
        "date": f"{date_raw} ({WEEKDAYS_KO[date_obj.weekday()]})",
        "time_raw": f"{sh:02d}:{sm:02d}",
        "time": f"{sh:02d}:{sm:02d}~{eh:02d}:{em:02d}",
        "start_hour": sh,
        "weekday_num": date_obj.weekday(),
        "url": SONGDO_URL,
    }


def _slot_from_text(court_num: str, date_raw: str, text: str, disabled: bool) -> dict[str, Any] | None:
    match = TIME_RE.search(text)
    if not match:
        return None
    unavailable_words = ("예약됨", "마감", "불가", "품절", "종료", "완료")
    if disabled or any(word in text for word in unavailable_words):
        return None
    return _slot(
        court_num,
        date_raw,
        int(match["sh"]),
        int(match["sm"]),
        int(match["eh"]),
        int(match["em"]),
    )


def _extract_visible_slots(page: Any, court_num: str, date_raw: str) -> list[dict[str, Any]]:
    selectors = "button, [role='button'], a, td, div"
    elements = page.locator(selectors)
    count = min(elements.count(), 2500)
    slots: list[dict[str, Any]] = []
    for index in range(count):
        element = elements.nth(index)
        try:
            text = " ".join((element.inner_text(timeout=250) or "").split())
            if not text or len(text) > 120 or not TIME_RE.search(text):
                continue
            disabled = False
            try:
                disabled = element.is_disabled(timeout=150)
            except Exception:
                disabled = element.get_attribute("aria-disabled") == "true"
            slot = _slot_from_text(court_num, date_raw, text, disabled)
            if slot:
                slots.append(slot)
        except Exception:
            continue
    return slots


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _parse_ws_slots(payloads: list[Any], fallback_date: str) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for payload in payloads:
        for item in _walk(payload):
            keys = set(item)
            if not {"startMinute", "endMinute"}.issubset(keys):
                continue
            booked = item.get("isBooked")
            if booked is True:
                continue
            try:
                start = int(item["startMinute"])
                end = int(item["endMinute"])
            except (TypeError, ValueError):
                continue
            facility = item.get("courtNumber", item.get("court", item.get("facilityId", "")))
            court_match = re.search(r"\d{1,2}", str(facility))
            if not court_match:
                continue
            court_num = court_match.group(0)
            if court_num not in {str(n) for n in range(5, 15)}:
                continue
            date_raw = _normalise_date(str(item.get("date", ""))) or fallback_date
            slots.append(_slot(court_num, date_raw, start // 60, start % 60, end // 60, end % 60))
    return slots


def _collect_worker(queue: Any) -> None:
    errors: list[str] = []
    slots: list[dict[str, Any]] = []
    ws_payloads: list[Any] = []
    debug_dir = Path(SONGDO_DEBUG_DIR)
    debug_dir.mkdir(parents=True, exist_ok=True)
    ws_file = debug_dir / "dalbit_ws_frames.jsonl"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        queue.put(([], ["달빛공원: playwright가 설치되지 않았습니다."]))
        return

    try:
        _log(f"ENABLED-CLICK v6.1.3 MODAL-RESET ALLCOURTS 수집 시작: {SONGDO_URL}")
        with sync_playwright() as p:
            _log("Chromium 실행")
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context_args: dict[str, Any] = {"locale": "ko-KR", "timezone_id": "Asia/Seoul"}
            storage_state = _load_storage_state()
            if storage_state:
                context_args["storage_state"] = storage_state
                _log("저장된 로그인 상태 적용")
            context = browser.new_context(**context_args)
            page = context.new_page()
            page.set_default_timeout(REQUEST_TIMEOUT * 1000)
            page.set_default_navigation_timeout(REQUEST_TIMEOUT * 1000)

            def on_ws(ws: Any) -> None:
                _log(f"WebSocket 연결: {ws.url}")

                def on_frame(payload: Any) -> None:
                    text = payload if isinstance(payload, str) else str(payload)
                    try:
                        parsed = json.loads(text)
                        ws_payloads.append(parsed)
                        with ws_file.open("a", encoding="utf-8") as fp:
                            fp.write(json.dumps(parsed, ensure_ascii=False) + "\n")
                    except Exception:
                        with ws_file.open("a", encoding="utf-8") as fp:
                            fp.write(json.dumps({"raw": text[:10000]}, ensure_ascii=False) + "\n")

                ws.on("framereceived", on_frame)

            page.on("websocket", on_ws)
            _log("페이지 접속")
            page.goto(SONGDO_URL, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
            _log("초기 데이터 대기 5초")
            page.wait_for_timeout(5000)

            body_text = page.locator("body").inner_text(timeout=3000)
            date_raw = _normalise_date(body_text) or datetime.now(KST).strftime("%Y-%m-%d")
            _log(f"화면 기준 날짜: {date_raw}")

            # 달빛공원 코트는 5~14번을 전부 확인합니다.
            target_courts = [str(n) for n in range(5, 15)]
            _log("5~14번 코트의 활성화된 예약 버튼만 클릭해 시간표 확인")

            def read_current_slots(court_num: str) -> list[dict[str, Any]]:
                current_text = page.locator("body").inner_text(timeout=3000)
                current_date = _normalise_date(current_text) or date_raw
                found = _extract_visible_slots(page, court_num, current_date)
                _log(f"{court_num}번 시간표 DOM 후보 {len(found)}개")
                return found

            list_url = page.url
            for court_num in target_courts:
                try:
                    # 코트명 요소에서 가장 가까운 '예약' 버튼 포함 카드로 올라갑니다.
                    court_name = page.get_by_text(re.compile(fr"^\s*{court_num}\s*번\s*코트\s*$")).first
                    if court_name.count() == 0:
                        _log(f"{court_num}번: 코트 카드를 찾지 못함")
                        continue
                    card = court_name.locator(
                        "xpath=ancestor::*[.//button[contains(normalize-space(.), '예약')]][1]"
                    )
                    if card.count() == 0:
                        _log(f"{court_num}번: 예약 버튼이 포함된 카드를 찾지 못함")
                        continue
                    reserve = card.locator("button").filter(has_text=re.compile(r"^\s*예약\s*$")).first
                    if reserve.count() == 0:
                        _log(f"{court_num}번: 예약 버튼 없음")
                        continue
                    disabled = reserve.is_disabled(timeout=800)
                    aria_disabled = reserve.get_attribute("aria-disabled") == "true"
                    if disabled or aria_disabled:
                        _log(f"{court_num}번: 예약 버튼 비활성 — 클릭하지 않음")
                        continue

                    _log(f"{court_num}번: 활성 예약 버튼 클릭")
                    reserve.click(timeout=3000)
                    page.wait_for_timeout(1800)
                    slots.extend(read_current_slots(court_num))

                    # 상세 화면/모달에서 추가 WebSocket 데이터가 들어오도록 잠시 기다립니다.
                    page.wait_for_timeout(700)

                    # 모달 오버레이가 다음 코트 클릭을 가로막는 문제가 있어,
                    # 코트 하나를 확인할 때마다 목록 URL을 새로 열어 완전히 초기화합니다.
                    _log(f"{court_num}번: 시간표 확인 완료 — 목록 화면 초기화")
                    try:
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(200)
                    except Exception:
                        pass
                    page.goto(SONGDO_URL, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
                    page.wait_for_timeout(1400)
                    list_url = page.url
                except Exception as exc:
                    errors.append(f"달빛공원 {court_num}번 코트: {type(exc).__name__} - {exc}")
                    _log(f"{court_num}번 처리 오류: {type(exc).__name__} - {exc}")
                    try:
                        page.goto(SONGDO_URL, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
                        page.wait_for_timeout(1200)
                        list_url = page.url
                    except Exception:
                        pass

            _log("WebSocket 추가 데이터 대기 3초")
            page.wait_for_timeout(3000)
            ws_slots = _parse_ws_slots(ws_payloads, date_raw)
            _log(f"WebSocket 프레임 {len(ws_payloads)}개, 슬롯 후보 {len(ws_slots)}개")
            slots.extend(ws_slots)

            try:
                context.storage_state(path=str(debug_dir / "dalbit_storage_state.json"))
                (debug_dir / "dalbit_last.html").write_text(page.content(), encoding="utf-8")
                page.screenshot(path=str(debug_dir / "dalbit_last.png"), full_page=True)
            except Exception as exc:
                errors.append(f"달빛공원 디버그 저장: {type(exc).__name__} - {exc}")
            browser.close()
    except Exception as exc:
        errors.append(f"달빛공원: {type(exc).__name__} - {exc}")
        errors.append(traceback.format_exc(limit=3).strip())

    unique = {f"{s['court_code']}|{s['date_raw']}|{s['time_raw']}": s for s in slots}
    result = sorted(unique.values(), key=lambda s: (s["date_raw"], s["start_hour"], s["court_code"]))
    _log(f"수집 종료: 가능 슬롯 {len(result)}개, 오류 {len(errors)}개")
    queue.put((result, errors))


def get_songdo_slots_with_status() -> tuple[list[dict[str, Any]], list[str]]:
    """별도 프로세스에서 수집하여 무한 대기를 방지합니다."""
    timeout_seconds = max(120, REQUEST_TIMEOUT * 8)
    ctx = mp.get_context("fork")
    queue = ctx.Queue()
    process = ctx.Process(target=_collect_worker, args=(queue,), daemon=True)
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        return [], [f"달빛공원: 전체 수집 제한시간 {timeout_seconds}초를 초과해 강제 종료했습니다."]
    if queue.empty():
        return [], [f"달빛공원: 수집 프로세스가 결과 없이 종료했습니다(exit={process.exitcode})."]
    return queue.get()
