from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from config import REQUEST_TIMEOUT, SAEACHIM_URL

KST = timezone(timedelta(hours=9))
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
TIME_RE = re.compile(r"(?P<sh>\d{1,2}):(?P<sm>\d{2})\s*[~\-–—]\s*(?P<eh>\d{1,2}):(?P<em>\d{2})")
TARGET_COURTS = (1, 2, 3, 4)


def _log(message: str) -> None:
    print(f"[SAEACHIM] {message}", flush=True)


def _court_label(court_num: int) -> str:
    return f"새아침테니스장 {court_num}코트"


def _make_slot(court_num: int, date_raw: str, text: str) -> dict[str, Any] | None:
    match = TIME_RE.search(text)
    if not match:
        return None
    sh, sm = int(match["sh"]), int(match["sm"])
    eh, em = int(match["eh"]), int(match["em"])
    date_obj = datetime.strptime(date_raw, "%Y-%m-%d").date()
    return {
        "site": "saeachim",
        "court_code": f"N{court_num}",
        "court": _court_label(court_num),
        "date_raw": date_raw,
        "date": f"{date_raw} ({WEEKDAYS_KO[date_obj.weekday()]})",
        "time_raw": f"{sh:02d}:{sm:02d}",
        "time": f"{sh:02d}:{sm:02d}~{eh:02d}:{em:02d}",
        "start_hour": sh,
        "weekday_num": date_obj.weekday(),
        "url": SAEACHIM_URL,
    }


def _select_option_containing(select: Any, text: str) -> bool:
    options = select.locator("option")
    for i in range(options.count()):
        option = options.nth(i)
        label = (option.inner_text(timeout=300) or "").strip()
        if text in label:
            value = option.get_attribute("value")
            if value is not None:
                select.select_option(value=value)
            else:
                select.select_option(label=label)
            return True
    return False


def _wait_calendar(page: Any) -> None:
    page.wait_for_function(
        """() => {
          const body = document.querySelector('#cal_body');
          return !!(body && body.querySelectorAll('td').length > 0 && /\\d{1,2}:\\d{2}/.test(body.innerText || ''));
        }""",
        timeout=REQUEST_TIMEOUT * 1000,
    )


def _calendar_month(page: Any) -> tuple[int, int]:
    text = page.locator("div.schedule div.month p").inner_text(timeout=2000)
    nums = [int(x) for x in re.findall(r"\d+", text)]
    if len(nums) < 2:
        raise RuntimeError(f"달력 연월을 읽지 못했습니다: {text!r}")
    return nums[0], nums[1]


def _extract_current_calendar(page: Any, court_num: int) -> list[dict[str, Any]]:
    year, month = _calendar_month(page)
    rows = page.locator("#cal_body td")
    result: list[dict[str, Any]] = []

    for i in range(rows.count()):
        cell = rows.nth(i)
        payload = cell.evaluate(
            """td => {
              const dayNode = td.querySelector('.day, .date, .num, strong, em, span, p, div');
              const allText = (td.innerText || '').trim();
              let day = '';
              const candidates = [...td.querySelectorAll('span,strong,em,p,div')];
              for (const el of candidates) {
                const t = (el.textContent || '').trim();
                if (/^\\d{1,2}$/.test(t)) { day = t; break; }
              }
              if (!day) {
                const m = allText.match(/(^|\\n)\\s*(\\d{1,2})\\s*(\\n|$)/);
                if (m) day = m[2];
              }
              const times = [];
              const nodes = [...td.querySelectorAll('a,button,span,li,p,div')];
              for (const el of nodes) {
                const text = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                if (!/\\d{1,2}:\\d{2}\\s*[~\\-–—]\\s*\\d{1,2}:\\d{2}/.test(text)) continue;
                const style = getComputedStyle(el);
                const deco = `${style.textDecoration || ''} ${style.textDecorationLine || ''}`.toLowerCase();
                const cls = String(el.className || '').toLowerCase();
                const aria = String(el.getAttribute('aria-disabled') || '').toLowerCase();
                const disabled = el.disabled === true || aria === 'true';
                const struck = deco.includes('line-through') || deco.includes('line through');
                const unavailableClass = /(disabled|disable|closed|finish|sold|end|off|gray|grey)/.test(cls);
                const clickable = el.tagName === 'A' || el.tagName === 'BUTTON' || !!el.getAttribute('onclick') || !!el.getAttribute('href');
                if (!disabled && !struck && !unavailableClass && clickable) {
                  times.push(text);
                }
              }
              return {day, times: [...new Set(times)]};
            }"""
        )
        day_text = str(payload.get("day") or "").strip()
        if not day_text.isdigit():
            continue
        day = int(day_text)
        try:
            date_raw = datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            continue
        if date_raw < datetime.now(KST).date().isoformat():
            continue
        for text in payload.get("times") or []:
            slot = _make_slot(court_num, date_raw, str(text))
            if slot:
                result.append(slot)
    return result


def _click_next_month(page: Any) -> bool:
    before = page.locator("div.schedule div.month p").inner_text(timeout=1500)
    page.locator("div.schedule .btn_next a").click(timeout=3000)
    try:
        page.wait_for_function(
            """before => {
              const p = document.querySelector('div.schedule div.month p');
              return p && (p.innerText || '').trim() !== before.trim();
            }""",
            before,
            timeout=5000,
        )
        _wait_calendar(page)
        return True
    except Exception:
        return False


def get_saeachim_slots_with_status(
    enabled_courts: list[int] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    courts = sorted({int(x) for x in (enabled_courts or TARGET_COURTS) if int(x) in TARGET_COURTS})
    slots: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], ["새아침테니스장: playwright가 설치되지 않았습니다."]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(locale="ko-KR", timezone_id="Asia/Seoul")
            page = context.new_page()
            page.set_default_timeout(REQUEST_TIMEOUT * 1000)
            for court_num in courts:
                try:
                    # 코트마다 새로 접속하여 항상 현재 월부터 확인합니다.
                    page.goto(SAEACHIM_URL, wait_until="domcontentloaded")
                    page.wait_for_selector("#main_rent_idx", timeout=REQUEST_TIMEOUT * 1000)
                    main_select = page.locator("#main_rent_idx")
                    if not _select_option_containing(main_select, "새아침"):
                        raise RuntimeError("새아침(테니스장) 시설 옵션을 찾지 못했습니다.")
                    page.wait_for_timeout(500)
                    court_select = page.locator("#sf_idx")
                    if not _select_option_containing(court_select, f"{court_num}코트"):
                        raise RuntimeError(f"{court_num}코트 옵션을 찾지 못했습니다.")
                    page.locator("#btn_search").click(timeout=3000)
                    _wait_calendar(page)

                    court_slots = _extract_current_calendar(page, court_num)
                    # 다음 달도 공개되어 있으면 함께 확인합니다.
                    if _click_next_month(page):
                        court_slots.extend(_extract_current_calendar(page, court_num))
                    slots.extend(court_slots)
                    _log(f"{court_num}코트: 실제 빈자리 {len(court_slots)}개")

                    # 다음 코트를 고를 때 현재 달이 바뀌어 있어도 검색 버튼이 현재 기준 달력을 다시 렌더링합니다.
                except Exception as exc:
                    error = f"새아침테니스장 {court_num}코트: {type(exc).__name__} - {exc}"
                    errors.append(error)
                    _log(f"오류: {error}")
            browser.close()
    except Exception as exc:
        errors.append(f"새아침테니스장: {type(exc).__name__} - {exc}")

    unique = {f"{s['court_code']}|{s['date_raw']}|{s['time_raw']}": s for s in slots}
    result = sorted(unique.values(), key=lambda s: (s["date_raw"], s["start_hour"], s["court_code"]))
    _log(f"수집 종료: 가능 슬롯 {len(result)}개, 오류 {len(errors)}개")
    return result, errors
