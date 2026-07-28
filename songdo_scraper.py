"""달빛공원 예약 가능 시간 수집기.

실제 Prime Reserve DOM 구조를 기준으로 동작합니다.
- 현재 화면이 목록인지 상세인지 먼저 판별
- 상세 화면이면 aria-label="목록으로" 버튼으로 복귀
- 목록 화면에서 5~14번 코트를 텍스트 기준으로 찾음
- 각 코트 상세 화면의 button[data-date-key]와 title="n/m 예약 가능"을 사용
- 예약 가능한 날짜만 클릭하고 시간대 버튼을 읽음
- 특정 코트가 실패해도 다음 코트로 계속 진행
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from config import REQUEST_TIMEOUT, SONGDO_AUTH_STATE, SONGDO_DEBUG_DIR, SONGDO_URL

KST = timezone(timedelta(hours=9))
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
TIME_RE = re.compile(
    r"(?P<sh>\d{1,2}):(?P<sm>\d{2})\s*(?:-|~|–|—|부터)\s*"
    r"(?P<eh>\d{1,2}):(?P<em>\d{2})"
)
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
    lowered = text.replace(" ", "")
    if any(word in lowered for word in ("예약됨", "마감", "불가", "품절", "종료")):
        return None

    sh, sm = int(match["sh"]), int(match["sm"])
    eh, em = int(match["eh"]), int(match["em"])
    if not (0 <= sh <= 23 and 0 <= eh <= 24 and 0 <= sm <= 59 and 0 <= em <= 59):
        return None

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


def _poll(page: Any, predicate: Callable[[], bool], timeout_ms: int, step_ms: int = 250) -> bool:
    """wait_for_function 대신 Python 측에서 짧게 폴링합니다."""
    elapsed = 0
    while elapsed < timeout_ms:
        try:
            if predicate():
                return True
        except Exception:
            pass
        page.wait_for_timeout(step_ms)
        elapsed += step_ms
    return False


def _visible_count(locator: Any) -> int:
    count = 0
    try:
        for i in range(locator.count()):
            try:
                if locator.nth(i).is_visible(timeout=200):
                    count += 1
            except Exception:
                continue
    except Exception:
        return 0
    return count


def _is_detail(page: Any) -> bool:
    back = page.locator('button[aria-label="목록으로"]')
    return _visible_count(back) > 0


def _list_has_target_courts(page: Any) -> bool:
    if _is_detail(page):
        return False
    try:
        body_text = page.locator("body").inner_text(timeout=800)
    except Exception:
        return False
    return "5번 코트" in body_text and "14번 코트" in body_text


def _element_summary(element: Any) -> str:
    """예약 메뉴 후보의 태그·속성을 짧게 로그로 남깁니다."""
    try:
        return element.evaluate(
            """el => JSON.stringify({
                tag: el.tagName,
                text: (el.innerText || el.textContent || '').trim(),
                role: el.getAttribute('role'),
                href: el.getAttribute('href'),
                aria: el.getAttribute('aria-label'),
                dataState: el.getAttribute('data-state'),
                className: typeof el.className === 'string' ? el.className : ''
            })"""
        )
    except Exception:
        return "{}"


def _reservation_candidates(page: Any) -> list[tuple[str, Any]]:
    """Prime Reserve의 실제 태그를 가정하지 않고 예약 메뉴 후보를 모읍니다."""
    locators = [
        ("role=button", page.get_by_role("button", name="예약", exact=True)),
        ("role=link", page.get_by_role("link", name="예약", exact=True)),
        ("role=tab", page.get_by_role("tab", name="예약", exact=True)),
        ("text", page.get_by_text("예약", exact=True)),
        ("css-a", page.locator("a", has_text="예약")),
        ("css-role-tab", page.locator('[role="tab"]', has_text="예약")),
        ("css-role-button", page.locator('[role="button"]', has_text="예약")),
    ]
    found: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for source, locator in locators:
        try:
            count = locator.count()
        except Exception:
            continue
        for i in range(count):
            item = locator.nth(i)
            try:
                key = item.evaluate("el => el.tagName + '|' + (el.outerHTML || '')")[:700]
            except Exception:
                key = f"{source}:{i}"
            if key in seen:
                continue
            seen.add(key)
            found.append((source, item))
    return found


def _click_reservation_tab(page: Any) -> bool:
    """메인 화면의 예약 메뉴를 실제 클릭하고 성공 여부를 반환합니다."""
    candidates = _reservation_candidates(page)
    _log(f"예약 메뉴 후보 {len(candidates)}개 발견")

    for index, (source, item) in enumerate(candidates, start=1):
        try:
            visible = item.is_visible(timeout=300)
        except Exception:
            visible = False
        try:
            enabled = item.is_enabled(timeout=300)
        except Exception:
            enabled = True
        _log(
            f"[예약메뉴 {index}] source={source} visible={visible} enabled={enabled} "
            f"element={_compact(_element_summary(item), 500)}"
        )
        if not visible or not enabled:
            continue

        before_url = page.url
        try:
            item.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass
        try:
            item.click(timeout=4000)
        except Exception as exc:
            _log(f"[예약메뉴 {index}] 일반 클릭 실패: {type(exc).__name__}: {exc}")
            try:
                item.click(timeout=3000, force=True)
            except Exception as force_exc:
                _log(f"[예약메뉴 {index}] 강제 클릭 실패: {type(force_exc).__name__}: {force_exc}")
                continue

        page.wait_for_timeout(800)
        _log(
            f"[예약메뉴 {index}] 클릭 완료: url_changed={before_url != page.url} "
            f"url={page.url}"
        )
        if _poll(page, lambda: _list_has_target_courts(page), 8000):
            _log(f"[예약메뉴 {index}] 코트 목록 진입 확인")
            return True

        # 클릭은 됐지만 목록이 안 떴다면 다음 후보도 시도합니다.
        try:
            body = _compact(page.locator("body").inner_text(timeout=1000), 500)
        except Exception:
            body = ""
        _log(f"[예약메뉴 {index}] 클릭 후 목록 미확인, body={body!r}")

    return False


def _wait_for_app_shell(page: Any, timeout_ms: int = 15000) -> None:
    """Prime Reserve 앱의 기본 메뉴가 렌더링될 때까지 기다립니다."""
    def ready() -> bool:
        try:
            body = page.locator("body").inner_text(timeout=800)
            return "Prime Reserve" in body and "예약" in body
        except Exception:
            return False

    if _poll(page, ready, timeout_ms):
        _log("Prime Reserve 앱 셸 확인")
    else:
        _log("Prime Reserve 앱 셸 대기 시간 초과 — 현재 DOM으로 계속 진단")


def _goto_songdo(page: Any) -> None:
    _log(f"예약 URL 접속: {SONGDO_URL}")
    page.goto(SONGDO_URL, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        _log("networkidle 대기 시간 초과 — SPA 렌더링 폴링으로 계속")
    _wait_for_app_shell(page)


def _ensure_list(page: Any, timeout_ms: int = 30000) -> None:
    """Prime Reserve 메인/상세 어느 상태에서든 달빛공원 코트 목록으로 진입합니다."""
    if _is_detail(page):
        _log("상세 화면 감지 — 목록으로 복귀")
        back = page.locator('button[aria-label="목록으로"]')
        try:
            back.first.click(timeout=4000)
        except Exception as exc:
            _log(f"목록으로 버튼 클릭 실패({type(exc).__name__}) — 예약 URL 재접속")
            _goto_songdo(page)

    if _poll(page, lambda: _list_has_target_courts(page), 5000):
        _log("기존 화면에서 코트 목록 확인")
        return

    _wait_for_app_shell(page, timeout_ms=8000)
    _log("메인 화면에서 예약 메뉴 클릭 시도")
    if _click_reservation_tab(page):
        return

    # 첫 진입의 SPA 상태가 불완전했을 수 있으므로 새 문서에서 한 번 더 검증합니다.
    _log("첫 예약 메뉴 진입 실패 — 새로 접속 후 재시도")
    _goto_songdo(page)
    if _is_detail(page):
        try:
            page.locator('button[aria-label="목록으로"]').first.click(timeout=4000)
        except Exception:
            pass
    if _poll(page, lambda: _list_has_target_courts(page), 3000):
        return
    if _click_reservation_tab(page):
        return

    try:
        current = page.url
        snippet = _compact(page.locator("body").inner_text(timeout=1000), 700)
        candidate_count = len(_reservation_candidates(page))
    except Exception:
        current, snippet, candidate_count = page.url, "", -1
    raise RuntimeError(
        "코트 목록을 확인하지 못했습니다. "
        f"url={current} 예약메뉴후보={candidate_count} body={snippet!r}"
    )


def _exact_visible_text(page: Any, text: str) -> Any | None:
    locator = page.get_by_text(text, exact=True)
    for i in range(locator.count()):
        item = locator.nth(i)
        try:
            if item.is_visible(timeout=250):
                return item
        except Exception:
            continue
    return None


def _court_card(page: Any, court_num: int) -> Any | None:
    title = _exact_visible_text(page, f"{court_num}번 코트")
    if title is None:
        return None
    # 실제 태그(h2/h3/div)에 의존하지 않고, '예약' 버튼을 포함하는 가장 가까운 조상을 사용합니다.
    card = title.locator("xpath=ancestor::*[.//button[normalize-space()='예약']][1]")
    return card if card.count() > 0 else None


def _compact(value: str, limit: int = 500) -> str:
    return " ".join((value or "").split())[:limit]


def _describe_buttons(locator: Any, limit: int = 12) -> list[str]:
    rows: list[str] = []
    try:
        count = locator.count()
    except Exception:
        return rows
    for i in range(min(count, limit)):
        button = locator.nth(i)
        try:
            text = _compact(button.inner_text(timeout=300), 80)
        except Exception:
            text = ""
        try:
            aria = button.get_attribute("aria-label") or ""
        except Exception:
            aria = ""
        try:
            title = button.get_attribute("title") or ""
        except Exception:
            title = ""
        try:
            disabled = button.is_disabled(timeout=200)
        except Exception:
            disabled = None
        try:
            visible = button.is_visible(timeout=200)
        except Exception:
            visible = None
        rows.append(
            f"#{i} text={text!r} aria={aria!r} title={title!r} "
            f"visible={visible} disabled={disabled}"
        )
    return rows


def _open_court(page: Any, court_num: int, debug_dir: Path) -> None:
    court_text = f"{court_num}번 코트"
    _log(f"[{court_num}번][1] 카드 탐색 시작, url={page.url}")

    title = _exact_visible_text(page, court_text)
    if title is None:
        body = _compact(page.locator("body").inner_text(timeout=1000), 700)
        _log(f"[{court_num}번][FAIL] 코트명 텍스트 없음, body={body!r}")
        _save_debug(page, debug_dir, f"probe_{court_num}_title_missing")
        raise RuntimeError("코트명 텍스트를 찾지 못했습니다.")

    try:
        tag = title.evaluate("el => el.tagName")
    except Exception:
        tag = "?"
    _log(f"[{court_num}번][2] 코트명 발견: tag={tag}")

    # 코트명 주변 DOM을 로그에 남겨 실제 카드 구조를 확인합니다.
    try:
        parent_html = title.evaluate(
            "el => (el.closest('article,li,section,[role=\"listitem\"]') || el.parentElement || el).outerHTML"
        )
        _log(f"[{court_num}번][DOM] 주변 HTML={_compact(parent_html, 900)!r}")
    except Exception as exc:
        _log(f"[{court_num}번][DOM] 주변 HTML 수집 실패: {type(exc).__name__}")

    card = _court_card(page, court_num)
    if card is None:
        # 기존 선택자가 실패했을 때 페이지 전체 예약 버튼 현황을 출력합니다.
        for row in _describe_buttons(page.locator("button")):
            _log(f"[{court_num}번][BUTTON] {row}")
        _save_debug(page, debug_dir, f"probe_{court_num}_card_missing")
        raise RuntimeError("코트 카드를 찾지 못했습니다.")

    _log(f"[{court_num}번][3] 기존 카드 선택자 발견")
    reserve_buttons = card.locator("button")
    descriptions = _describe_buttons(reserve_buttons)
    _log(f"[{court_num}번][4] 카드 내부 버튼 {reserve_buttons.count()}개")
    for row in descriptions:
        _log(f"[{court_num}번][BUTTON] {row}")

    reserve = None
    for i in range(reserve_buttons.count()):
        candidate = reserve_buttons.nth(i)
        try:
            text = _compact(candidate.inner_text(timeout=300), 50)
            aria = (candidate.get_attribute("aria-label") or "").strip()
            # '예약'이 포함된 활성 버튼을 우선 사용합니다.
            if "예약" in text or "예약" in aria:
                if candidate.is_visible(timeout=250) and candidate.is_enabled(timeout=250):
                    reserve = candidate
                    break
        except Exception:
            continue

    if reserve is None:
        _save_debug(page, debug_dir, f"probe_{court_num}_no_enabled_button")
        raise RuntimeError("카드 안에서 활성화된 예약 버튼을 찾지 못했습니다.")

    _save_debug(page, debug_dir, f"probe_{court_num}_before_click")
    _log(f"[{court_num}번][5] 예약 버튼 클릭 직전")
    before_url = page.url
    reserve.scroll_into_view_if_needed(timeout=2000)

    # Prime Reserve의 SPA 버튼은 클릭 이벤트 직후 DOM이 교체되면서
    # Playwright가 클릭 완료를 기다리다가 TimeoutError를 낼 수 있습니다.
    # 따라서 클릭 예외 자체를 실패로 단정하지 않고 상세 화면 진입 여부를 먼저 검증합니다.
    click_error: Exception | None = None
    try:
        reserve.click(timeout=2500, no_wait_after=True)
        _log(f"[{court_num}번][6A] Playwright 클릭 명령 반환")
    except Exception as exc:
        click_error = exc
        _log(f"[{court_num}번][6A] Playwright 클릭 예외(진입 여부 계속 확인): {type(exc).__name__}: {exc}")

    entered = _poll(
        page,
        lambda: _is_detail(page) and page.locator("button[data-date-key]").count() > 0,
        5000,
    )

    if not entered:
        _log(f"[{court_num}번][6B] 일반 클릭 후 상세 미확인 — DOM click() 대체 시도")
        try:
            reserve.evaluate("el => el.click()")
            _log(f"[{court_num}번][6B] DOM click() 실행 완료")
        except Exception as exc:
            _log(f"[{court_num}번][6B] DOM click() 예외: {type(exc).__name__}: {exc}")

        entered = _poll(
            page,
            lambda: _is_detail(page) and page.locator("button[data-date-key]").count() > 0,
            7000,
        )

    page.wait_for_timeout(300)
    after_url = page.url
    detail = _is_detail(page)
    title_after = _exact_visible_text(page, court_text) is not None
    date_count = page.locator("button[data-date-key]").count()
    _log(
        f"[{court_num}번][7] 클릭 후 검증: url_changed={before_url != after_url}, "
        f"detail_back_button={detail}, court_title={title_after}, date_buttons={date_count}, "
        f"url={after_url}"
    )
    _save_debug(page, debug_dir, f"probe_{court_num}_after_click")

    if not (detail and title_after and date_count > 0):
        body = _compact(page.locator("body").inner_text(timeout=1000), 900)
        _log(f"[{court_num}번][FAIL] 상세 검증 실패, body={body!r}")
        raise RuntimeError("클릭 후 상세 화면 검증에 실패했습니다.")

    _log(f"[{court_num}번][OK] 상세 진입 확인 완료")


def _available_dates(page: Any) -> list[tuple[str, int, int]]:
    found: list[tuple[str, int, int]] = []
    buttons = page.locator("button[data-date-key]")
    for i in range(buttons.count()):
        button = buttons.nth(i)
        try:
            if not button.is_visible(timeout=200) or button.is_disabled(timeout=200):
                continue
            date_key = (button.get_attribute("data-date-key") or "").strip()
            title_nodes = button.locator('[title*="예약 가능"]')
            title = ""
            if title_nodes.count() > 0:
                title = title_nodes.first.get_attribute("title") or ""
            if not title:
                title = button.get_attribute("title") or ""
            match = AVAIL_RE.search(title)
            if not date_key or not match:
                continue
            available, total = int(match["available"]), int(match["total"])
            if available > 0:
                found.append((date_key, available, total))
        except Exception:
            continue
    return found


def _extract_times(page: Any, court_num: int, date_raw: str) -> list[dict[str, Any]]:
    def has_time_text() -> bool:
        try:
            text = page.locator("body").inner_text(timeout=800)
            return TIME_RE.search(text) is not None
        except Exception:
            return False

    _poll(page, has_time_text, 5000)
    slots: list[dict[str, Any]] = []
    elements = page.locator("button, [role='button']")
    for i in range(elements.count()):
        element = elements.nth(i)
        try:
            if not element.is_visible(timeout=150) or element.is_disabled(timeout=150):
                continue
            text = " ".join((element.inner_text(timeout=400) or "").split())
            slot = _make_slot(court_num, date_raw, text)
            if slot:
                slots.append(slot)
        except Exception:
            continue
    return slots


def _save_debug(page: Any, debug_dir: Path, name: str) -> None:
    try:
        (debug_dir / f"{name}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(path=str(debug_dir / f"{name}.png"), full_page=True)
    except Exception:
        pass


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
        _log("v6.1.10 CLICK-FALLBACK 진단 시작 — Prime Reserve 예약 메뉴 실제 클릭")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context_args: dict[str, Any] = {"locale": "ko-KR", "timezone_id": "Asia/Seoul"}
            storage_state = _load_storage_state()
            if storage_state:
                context_args["storage_state"] = storage_state
            context = browser.new_context(**context_args)
            page = context.new_page()
            page.set_default_timeout(REQUEST_TIMEOUT * 1000)

            _goto_songdo(page)
            _ensure_list(page)
            _log("코트 목록 확인 완료")

            for court_num in TARGET_COURTS:
                try:
                    _ensure_list(page)
                    _log(f"{court_num}번: 상세 화면 진입 시도")
                    _open_court(page, court_num, debug_dir)

                    dates = _available_dates(page)
                    _log(f"{court_num}번: 예약 가능 날짜 {len(dates)}개")
                    for date_raw, available, total in dates:
                        try:
                            date_button = page.locator(f'button[data-date-key="{date_raw}"]').first
                            date_button.click(timeout=3000)
                            found = _extract_times(page, court_num, date_raw)
                            slots.extend(found)
                            _log(f"{court_num}번 {date_raw}: {available}/{total}, 시간 슬롯 {len(found)}개")
                        except Exception as exc:
                            errors.append(f"달빛공원 {court_num}번 {date_raw}: {type(exc).__name__} - {exc}")

                    # 다음 코트를 위해 명시적으로 목록으로 복귀합니다.
                    back = page.locator('button[aria-label="목록으로"]')
                    if _visible_count(back) > 0:
                        back.first.click(timeout=4000)
                    _ensure_list(page)
                except Exception as exc:
                    errors.append(f"달빛공원 {court_num}번: {type(exc).__name__} - {exc}")
                    _save_debug(page, debug_dir, f"dalbit_error_court_{court_num}")
                    try:
                        _ensure_list(page, timeout_ms=10000)
                    except Exception:
                        try:
                            _goto_songdo(page)
                        except Exception:
                            pass

            try:
                context.storage_state(path=str(debug_dir / "songdo_storage_state.json"))
            except Exception:
                pass
            _save_debug(page, debug_dir, "songdo_last")
            browser.close()
    except Exception as exc:
        errors.append(f"달빛공원: {type(exc).__name__} - {exc}")

    unique = {f"{s['court_code']}|{s['date_raw']}|{s['time_raw']}": s for s in slots}
    result = sorted(unique.values(), key=lambda s: (s["date_raw"], s["start_hour"], s["court_code"]))
    _log(f"수집 종료: 가능 슬롯 {len(result)}개, 오류 {len(errors)}개")
    return result, errors
