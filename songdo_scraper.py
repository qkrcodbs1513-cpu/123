"""달빛공원 예약 페이지 수집기(진단 강화 베타).

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
    configured = set(SONGDO_COURTS)
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
            if configured and court_num not in configured:
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
        _log(f"수집 시작: {SONGDO_URL}")
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

            for label in ("닫기", "확인"):
                try:
                    page.get_by_role("button", name=label).first.click(timeout=500)
                except Exception:
                    pass

            body_text = page.locator("body").inner_text(timeout=3000)
            date_raw = _normalise_date(body_text) or datetime.now(KST).strftime("%Y-%m-%d")
            _log(f"화면 기준 날짜: {date_raw}")

            configured = set(SONGDO_COURTS)
            _log("코트 버튼 클릭 없이 DOM 상태 읽기")

            # 시간 표시가 들어간 실제 인터랙션 요소를 읽고, 가장 가까운 상위
            # 카드에서 코트 번호를 찾습니다. disabled 요소는 예약 불가로 처리합니다.
            dom_rows = page.evaluate(r"""
                () => {
                  const timeRe = /(?:^|\s)(\d{1,2}):(\d{2})\s*[-~–]\s*(\d{1,2}):(\d{2})(?:\s|$)/;
                  const courtRe = /(\d{1,2})\s*번\s*코트/;
                  const rows = [];
                  const nodes = Array.from(document.querySelectorAll('button, a, [role="button"]'));

                  for (const node of nodes) {
                    const text = (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
                    const tm = text.match(timeRe);
                    if (!tm) continue;

                    let court = null;
                    let parent = node;
                    for (let depth = 0; depth < 10 && parent; depth++, parent = parent.parentElement) {
                      const parentText = (parent.innerText || '').replace(/\s+/g, ' ').trim();
                      const matches = [...parentText.matchAll(new RegExp(courtRe.source, 'g'))];
                      const unique = [...new Set(matches.map(m => m[1]))];
                      if (unique.length === 1) {
                        court = unique[0];
                        break;
                      }
                    }

                    const disabled = Boolean(
                      node.disabled ||
                      node.getAttribute('disabled') !== null ||
                      node.getAttribute('aria-disabled') === 'true' ||
                      node.classList.contains('disabled')
                    );
                    rows.push({
                      court,
                      text,
                      disabled,
                      tag: node.tagName,
                      cls: node.className || ''
                    });
                  }
                  return rows;
                }
            """)

            _log(f"시간 인터랙션 요소 {len(dom_rows)}개 발견")
            for row in dom_rows[:80]:
                court_num = str(row.get("court") or "")
                text = str(row.get("text") or "")
                disabled = bool(row.get("disabled"))
                if not court_num:
                    _log(f"코트 미확인 | {'불가' if disabled else '활성'} | {text[:80]}")
                    continue
                if configured and court_num not in configured:
                    continue
                _log(f"{court_num}번 | {'예약불가' if disabled else '예약가능 후보'} | {text[:80]}")
                slot = _slot_from_text(court_num, date_raw, text, disabled)
                if slot:
                    slots.append(slot)

            # 인터랙션 요소에 시간이 없는 사이트를 위한 보조 진단입니다.
            # 코트명이 표시된 카드별 전체 문구를 저장하되, 여기서는 예약 가능으로
            # 단정하지 않습니다. Railway 로그를 통해 실제 DOM 구조를 확인할 수 있습니다.
            card_rows = page.evaluate(r"""
                () => {
                  const courtRe = /(\d{1,2})\s*번\s*코트/;
                  const seen = new Set();
                  const rows = [];
                  const all = Array.from(document.querySelectorAll('body *'));
                  for (const el of all) {
                    const own = (el.innerText || '').replace(/\s+/g, ' ').trim();
                    const m = own.match(courtRe);
                    if (!m || own.length > 500) continue;
                    const key = m[1] + '|' + own;
                    if (seen.has(key)) continue;
                    seen.add(key);
                    rows.push({court: m[1], text: own});
                  }
                  return rows.slice(0, 100);
                }
            """)
            for row in card_rows:
                court_num = str(row.get("court") or "")
                if configured and court_num not in configured:
                    continue
                _log(f"DOM 카드 {court_num}번: {str(row.get('text') or '')[:180]}")

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
    timeout_seconds = max(35, REQUEST_TIMEOUT * 3)
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
