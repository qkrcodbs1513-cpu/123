from __future__ import annotations

import gc
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from config import REQUEST_TIMEOUT

KST = timezone(timedelta(hours=9))
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
TARGET_COURTS = (1, 2, 3, 4)
TIME_RE = re.compile(r"(?P<sh>\d{1,2}):(?P<sm>\d{2})\s*[~\-–—]\s*(?P<eh>\d{1,2}):(?P<em>\d{2})")
DATE_RE = re.compile(r"(?P<y>20\d{2})[.\-/년\s]+(?P<m>\d{1,2})[.\-/월\s]+(?P<d>\d{1,2})")

# 실제 송도공원사업단 대관 화면은 res.insiseol.or.kr에 있다.
# reserve.insiseol.or.kr 동일 경로는 404를 반환하므로 사용하지 않는다.
BASE_URL = "https://res.insiseol.or.kr/"
RES_URL = "https://res.insiseol.or.kr/rent/rentalSchedule?up_id=07"



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
    try:
        date_obj = datetime.strptime(date_raw, "%Y-%m-%d").date()
    except ValueError:
        return None
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
        "url": RES_URL,
    }


def _body_text(page: Any) -> str:
    try:
        return page.locator("body").inner_text(timeout=2500)
    except Exception:
        return ""


def _wait_select_options(page: Any, selector: str, timeout_ms: int = 15000) -> None:
    page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
    page.wait_for_function(
        "sel => { const e=document.querySelector(sel); return e && e.options && e.options.length > 0; }",
        arg=selector,
        timeout=timeout_ms,
    )


def _goto_schedule(page: Any) -> None:
    """새아침 대관 달력으로 직접 진입한다.

    사용자가 확인한 실제 공개 조회 주소는 res.insiseol.or.kr이다.
    개발자도구 감지 스크립트는 context 단계에서 차단/무력화한다.
    """
    response = page.goto(
        RES_URL,
        wait_until="domcontentloaded",
        timeout=min(25000, max(15000, REQUEST_TIMEOUT * 1000)),
    )
    status = response.status if response else "no-response"
    _log(f"대관 화면 접속 — HTTP {status} / {page.url}")

    if "res.insiseol.or.kr/rent/rentalSchedule" not in page.url or "up_id=07" not in page.url:
        raise RuntimeError(f"대관 화면이 아닌 곳으로 이동했습니다: {page.url}")

    page.wait_for_selector("#main_rent_idx", state="attached", timeout=10000)
    _wait_select_options(page, "#main_rent_idx", 10000)


def _select_by_text(page: Any, selectors: list[str], needles: list[str]) -> bool:
    """id가 바뀌어도 모든 select를 검색해 텍스트가 맞는 option을 선택한다."""
    seen: set[str] = set()
    for selector in selectors + ["select"]:
        try:
            loc = page.locator(selector)
            count = min(loc.count(), 30)
        except Exception:
            continue
        for i in range(count):
            select = loc.nth(i)
            try:
                key = select.evaluate("e => e.id + '|' + e.name")
                if key in seen:
                    continue
                seen.add(key)
                options = select.locator("option")
                for j in range(options.count()):
                    option = options.nth(j)
                    label = re.sub(r"\s+", " ", option.inner_text(timeout=500) or "").strip()
                    if any(n in label for n in needles):
                        value = option.get_attribute("value")
                        select.select_option(value=value) if value is not None else select.select_option(label=label)
                        page.wait_for_timeout(700)
                        return True
            except Exception:
                continue
    return False


def _click_text(page: Any, needles: list[str]) -> bool:
    """select가 아닌 버튼/링크 UI일 때 텍스트로 선택한다."""
    for needle in needles:
        for selector in ("button", "a", "label", "li", "div[role=button]"):
            try:
                candidates = page.locator(selector).filter(has_text=needle)
                for i in range(min(candidates.count(), 15)):
                    node = candidates.nth(i)
                    if node.is_visible(timeout=300):
                        node.click(timeout=2000)
                        page.wait_for_timeout(700)
                        return True
            except Exception:
                continue
    return False


def _choose_facility_and_court(page: Any, court_num: int) -> None:
    facility_ok = _select_by_text(
        page,
        ["#main_rent_idx", "select[name*=main]", "select[name*=rent]", "select[name*=facility]"],
        ["새아침테니스장", "새아침"],
    ) or _click_text(page, ["새아침테니스장", "새아침"])

    # 페이지가 이미 새아침 전용 화면이면 시설 선택이 없어도 통과.
    if not facility_ok and "새아침" not in _body_text(page):
        options = page.locator("#main_rent_idx option").all_inner_texts() if page.locator("#main_rent_idx").count() else []
        raise RuntimeError(f"새아침 시설 선택 항목을 찾지 못했습니다. 업장옵션={options[:12]}")

    # 업장 선택 후 장소 목록은 비동기로 채워진다.
    try:
        _wait_select_options(page, "#sf_idx", 12000)
    except Exception:
        pass

    court_needles = [f"{court_num}코트", f"{court_num} 코트", f"제{court_num}코트"]
    court_ok = _select_by_text(
        page,
        ["#sf_idx", "select[name*=sf]", "select[name*=court]", "select[name*=facility]"],
        court_needles,
    ) or _click_text(page, court_needles)
    if not court_ok:
        options = page.locator("#sf_idx option").all_inner_texts() if page.locator("#sf_idx").count() else []
        raise RuntimeError(f"{court_num}코트 선택 항목을 찾지 못했습니다. 장소옵션={options[:20]}")

    # 조회/검색 버튼이 있으면 누르고, 자동 갱신형이면 그대로 진행.
    for needle in ("조회", "검색", "확인"):
        try:
            button = page.get_by_role("button", name=re.compile(needle)).first
            if button.count() and button.is_visible(timeout=300):
                button.click(timeout=2000)
                page.wait_for_timeout(1000)
                break
        except Exception:
            pass
    try:
        if page.locator("#btn_search").count() and page.locator("#btn_search").is_visible(timeout=300):
            page.locator("#btn_search").click(timeout=2000)
            page.wait_for_timeout(1000)
    except Exception:
        pass


def _infer_month(page: Any) -> tuple[int, int]:
    now = datetime.now(KST)
    text = _body_text(page)
    patterns = [
        r"(20\d{2})\s*[.년/-]\s*(\d{1,2})\s*월?",
        r"(20\d{2})(\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year, month = int(match.group(1)), int(match.group(2))
            if 1 <= month <= 12 and now.year - 1 <= year <= now.year + 2:
                return year, month
    return now.year, now.month


def _extract_slots(page: Any, court_num: int) -> list[dict[str, Any]]:
    year, month = _infer_month(page)
    today = datetime.now(KST).date()
    raw = page.evaluate(
        """() => {
          const out = [];
          const candidates = [...document.querySelectorAll('td, li, tr, .day, .date, .calendar-day, [data-date]')];
          for (const node of candidates) {
            const text = (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
            if (!/\\d{1,2}:\\d{2}\\s*[~\\-–—]\\s*\\d{1,2}:\\d{2}/.test(text)) continue;
            const dateAttr = node.getAttribute('data-date') || node.getAttribute('data-day') || '';
            const cls = String(node.className || '').toLowerCase();
            const nodes = [...node.querySelectorAll('a,button,input,label,span,li,p,div')];
            const times = [];
            for (const el of nodes.length ? nodes : [node]) {
              const t = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
              if (!/\\d{1,2}:\\d{2}\\s*[~\\-–—]\\s*\\d{1,2}:\\d{2}/.test(t)) continue;
              const style = getComputedStyle(el);
              const ecls = String(el.className || '').toLowerCase();
              const disabled = el.disabled === true || el.getAttribute('aria-disabled') === 'true';
              const unavailable = /(마감|예약완료|불가|종료|closed|disabled|disable|finish|sold|end|off)/i.test(t + ' ' + ecls + ' ' + cls);
              const struck = String(style.textDecorationLine || style.textDecoration || '').includes('line-through');
              const clickable = ['A','BUTTON','INPUT','LABEL'].includes(el.tagName) || !!el.onclick || !!el.getAttribute('href');
              const availableWord = /(예약가능|신청가능|접수가능|가능)/.test(t);
              if (!disabled && !unavailable && !struck && (clickable || availableWord)) times.push(t);
            }
            out.push({text, dateAttr, times:[...new Set(times)]});
          }
          return out;
        }"""
    )

    result: list[dict[str, Any]] = []
    for row in raw or []:
        text = str(row.get("text") or "")
        date_attr = str(row.get("dateAttr") or "")
        date_raw = ""
        match = DATE_RE.search(date_attr + " " + text)
        if match:
            try:
                date_raw = datetime(int(match["y"]), int(match["m"]), int(match["d"])).strftime("%Y-%m-%d")
            except ValueError:
                continue
        else:
            day_match = re.search(r"(?:^|\s)(\d{1,2})(?:일|\s|$)", text)
            if not day_match:
                continue
            day = int(day_match.group(1))
            try:
                date_raw = datetime(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                continue
        if date_raw < today.isoformat():
            continue
        for time_text in row.get("times") or []:
            slot = _make_slot(court_num, date_raw, str(time_text))
            if slot:
                result.append(slot)
    return result


def _next_month(page: Any) -> bool:
    before = _infer_month(page)
    for selector in (
        "a[title*='다음']", "button[title*='다음']", ".btn_next a", ".next a", ".calendar-next",
    ):
        try:
            node = page.locator(selector).first
            if node.count() and node.is_visible(timeout=300):
                node.click(timeout=2000)
                page.wait_for_timeout(1200)
                return _infer_month(page) != before
        except Exception:
            continue
    return _click_text(page, ["다음 달", "다음달"])


def _new_browser_context(playwright: Any) -> tuple[Any, Any]:
    """새아침 조회용 브라우저와 context를 만든다."""
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    context = browser.new_context(
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        ),
    )
    context.route("**/devtools-detector.js*", lambda route: route.abort())
    context.add_init_script(
        """
        try { Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); } catch (_) {}
        try { Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko', 'en-US', 'en']}); } catch (_) {}
        try { Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]}); } catch (_) {}
        window.chrome = window.chrome || { runtime: {} };
        window.devtoolsDetector = {addListener:function(){},launch:function(){},stop:function(){},isLaunch:function(){return false;}};
        """
    )
    return browser, context


def _scrape_court_in_context(context: Any, court_num: int) -> tuple[list[dict[str, Any]], str | None]:
    """이미 열린 브라우저 context에서 코트 하나를 조회한다.

    일시적인 페이지 접속 지연은 한 번 재시도한다. 첫 실패 결과로 빈자리가
    사라졌다고 잘못 판단하지 않도록 최종 실패만 오류로 반환한다.
    """
    started = time.monotonic()
    last_exc: Exception | None = None
    for attempt in (1, 2):
        page = None
        try:
            page = context.new_page()
            page.on("dialog", lambda dialog: dialog.dismiss())
            page.set_default_timeout(min(9000, max(6500, REQUEST_TIMEOUT * 1000)))
            _goto_schedule(page)
            _choose_facility_and_court(page, court_num)
            page.wait_for_timeout(250)
            court_slots = _extract_slots(page, court_num)
            if _next_month(page):
                page.wait_for_timeout(250)
                court_slots.extend(_extract_slots(page, court_num))
            elapsed = time.monotonic() - started
            suffix = f" / 재시도 {attempt-1}회" if attempt > 1 else ""
            _log(f"{court_num}코트: 실제 빈자리 {len(court_slots)}개 / {elapsed:.1f}초{suffix}")
            return court_slots, None
        except Exception as exc:
            last_exc = exc
            if attempt == 1:
                _log(f"{court_num}코트 1차 조회 지연 — 1회 재시도")
                time.sleep(1.0)
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass

    assert last_exc is not None
    error = f"새아침테니스장 {court_num}코트: {type(last_exc).__name__} - {last_exc}"
    _log(f"오류: {error}")
    return [], error


def _scrape_court_batch(courts: list[int]) -> tuple[list[dict[str, Any]], list[str]]:
    """한 worker가 브라우저 하나를 재사용해 여러 코트를 순차 조회한다."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], ["새아침테니스장: playwright가 설치되지 않았습니다."]

    slots: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        with sync_playwright() as p:
            browser, context = _new_browser_context(p)
            try:
                for court_num in courts:
                    court_slots, error = _scrape_court_in_context(context, court_num)
                    slots.extend(court_slots)
                    if error:
                        errors.append(error)
            finally:
                try:
                    context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as exc:
        # worker 자체가 죽은 경우 해당 묶음 전체를 오류로 표시한다.
        for court_num in courts:
            errors.append(f"새아침테니스장 {court_num}코트: {type(exc).__name__} - {exc}")
    return slots, errors


def get_saeachim_slots_with_status(enabled_courts: list[int] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    courts = sorted({int(x) for x in (enabled_courts or TARGET_COURTS) if int(x) in TARGET_COURTS})
    if not courts:
        return [], []

    # 장시간 Railway 운용 안정성 우선: Chromium은 항상 1개만 생성하고
    # 코트 1~4를 순차 조회한다. 매 호출이 끝나면 context/browser/playwright가
    # 모두 닫히므로 다음 주기에 브라우저 프로세스가 누적되지 않는다.
    _log(f"안정 단일브라우저 조회 시작 — 코트 {len(courts)}개 / 브라우저 1개")
    slots, errors = _scrape_court_batch(courts)

    unique = {f"{s['court_code']}|{s['date_raw']}|{s['time_raw']}": s for s in slots}
    result = sorted(unique.values(), key=lambda s: (s["date_raw"], s["start_hour"], s["court_code"]))
    _log(f"수집 종료: 가능 슬롯 {len(result)}개, 오류 {len(errors)}개")
    return result, errors
