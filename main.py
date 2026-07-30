from __future__ import annotations

import argparse
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from config import (
    CHECK_INTERVAL,
    ERROR_ALERT_MINUTES,
    HEARTBEAT_HOURS,
    TELEGRAM_POLL_TIMEOUT,
)
from scraper import get_available_slots_with_status, matches_settings, slot_key
from songdo_scraper import get_songdo_slots_with_status
from saeachim_scraper import get_saeachim_slots_with_status
from storage import load_settings, load_state, save_settings, save_state
from telegram_bot import (
    answer_callback_query,
    edit_telegram_message,
    escape,
    get_updates,
    send_telegram_message,
)

KST = timezone(timedelta(hours=9))
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
STATE_LOCK = threading.RLock()
APP_STATE = load_state()
APP_SETTINGS = load_settings()
LAST_TOTAL_SLOTS = 0
LAST_TARGET_COUNT = 0
LAST_YEONSU_TARGETS = 0
LAST_SONGDO_TARGETS = 0
LAST_SAEACHIM_TARGETS = 0
LAST_NEW_COUNT = 0
LAST_ERROR = ""
START_MONOTONIC = time.monotonic()


def now_kst() -> datetime:
    return datetime.now(KST)


def now_str() -> str:
    now = now_kst()
    return now.strftime(f"%Y-%m-%d ({WEEKDAYS_KO[now.weekday()]}) %H:%M:%S")


def log(level: str, message: str) -> None:
    print(f"[{now_kst():%Y-%m-%d %H:%M:%S}] [{level:<5}] {message}", flush=True)


def hours_text(hours: list[int] | None) -> str:
    if hours is None:
        return "모든 시간"
    if not hours:
        return "알림 안 함"
    return ", ".join(f"{h:02d}~{h + 2:02d}" for h in hours)


def site_hours_text(site: str) -> tuple[str, str]:
    with STATE_LOCK:
        weekday = APP_SETTINGS.get(f"{site}_weekday_hours", APP_SETTINGS.get("weekday_hours"))
        weekend = APP_SETTINGS.get(f"{site}_weekend_hours", APP_SETTINGS.get("weekend_hours"))
    return hours_text(weekday), hours_text(weekend)


def settings_text() -> str:
    with STATE_LOCK:
        courts = "/".join(APP_SETTINGS["courts"])
        yeonsu_enabled = bool(APP_SETTINGS.get("yeonsu_enabled", True))
        songdo_enabled = bool(APP_SETTINGS.get("songdo_enabled", False))
        songdo_courts = APP_SETTINGS.get("songdo_courts", list(range(5, 15)))
        surfaces = set(APP_SETTINGS.get("songdo_surfaces", ["hard", "artificial"]))
        saeachim_enabled = bool(APP_SETTINGS.get("saeachim_enabled", True))
        saeachim_courts = APP_SETTINGS.get("saeachim_courts", [1, 2, 3, 4])
    y_weekday, y_weekend = site_hours_text("yeonsu")
    d_weekday, d_weekend = site_hours_text("songdo")
    n_weekday, n_weekend = site_hours_text("saeachim")
    surface_text = "/".join(x for x, key in (("하드", "hard"), ("인조잔디", "artificial")) if key in surfaces) or "없음"
    court_text = ",".join(map(str, songdo_courts))
    saeachim_court_text = ",".join(map(str, saeachim_courts))
    return (
        f"🏟️ 연수문화공원: <b>{'켜짐' if yeonsu_enabled else '꺼짐'}</b>\n"
        f"　평일 <b>{escape(y_weekday)}</b> / 주말 <b>{escape(y_weekend)}</b>\n"
        f"　코트 <b>{escape(courts)}</b>\n"
        f"🌙 달빛공원: <b>{'켜짐' if songdo_enabled else '꺼짐'}</b>\n"
        f"　평일 <b>{escape(d_weekday)}</b> / 주말 <b>{escape(d_weekend)}</b>\n"
        f"　코트 <b>{escape(court_text)}</b> / 재질 <b>{escape(surface_text)}</b>\n"
        f"🌅 새아침테니스장: <b>{'켜짐' if saeachim_enabled else '꺼짐'}</b>\n"
        f"　평일 <b>{escape(n_weekday)}</b> / 주말 <b>{escape(n_weekend)}</b>\n"
        f"　코트 <b>{escape(saeachim_court_text)}</b>\n"
        f"🔁 검사 주기: <b>{CHECK_INTERVAL}초</b>"
    )


def settings_keyboard() -> dict[str, Any]:
    with STATE_LOCK:
        yeonsu_enabled = bool(APP_SETTINGS.get("yeonsu_enabled", True))
        songdo_enabled = bool(APP_SETTINGS.get("songdo_enabled", False))
        saeachim_enabled = bool(APP_SETTINGS.get("saeachim_enabled", True))

    def mark(enabled: bool) -> str:
        return "✅" if enabled else "⬜"

    return {"inline_keyboard": [
        [
            {"text": f"{mark(yeonsu_enabled)} 연수문화공원", "callback_data": "site:yeonsu"},
            {"text": f"{mark(songdo_enabled)} 달빛공원", "callback_data": "site:songdo"},
        ],
        [{"text": f"{mark(saeachim_enabled)} 새아침테니스장", "callback_data": "site:saeachim"}],
        [
            {"text": "🏟️ 연수 설정", "callback_data": "site_menu:yeonsu"},
            {"text": "🌙 달빛 설정", "callback_data": "site_menu:songdo"},
        ],
        [{"text": "🌅 새아침 설정", "callback_data": "site_menu:saeachim"}],
        [
            {"text": "📊 상태", "callback_data": "show:status"},
            {"text": "🔄 새로고침", "callback_data": "show:settings"},
        ],
    ]}


def site_menu_keyboard(site: str) -> dict[str, Any]:
    if site == "yeonsu":
        rows = [
            [{"text": "🎾 A/B/C 코트 선택", "callback_data": "court_menu:yeonsu"}],
            [{"text": "⏰ 시간 설정", "callback_data": "time_menu:yeonsu"}],
        ]
    elif site == "songdo":
        rows = [
            [{"text": "🎾 5~14번 코트 선택", "callback_data": "court_menu:songdo"}],
            [{"text": "🌱 하드/인조잔디 선택", "callback_data": "surface_menu"}],
            [{"text": "⏰ 시간 설정", "callback_data": "time_menu:songdo"}],
        ]
    else:
        rows = [
            [{"text": "🎾 1~4코트 선택", "callback_data": "court_menu:saeachim"}],
            [{"text": "⏰ 시간 설정", "callback_data": "time_menu:saeachim"}],
        ]
    rows.append([{"text": "⬅️ 전체 설정", "callback_data": "show:settings"}])
    return {"inline_keyboard": rows}


def show_site_menu(site: str, message_id: int) -> None:
    name = {"yeonsu": "연수문화공원", "songdo": "달빛공원", "saeachim": "새아침테니스장"}[site]
    edit_telegram_message(message_id, f"⚙️ <b>{name} 설정</b>\n\n원하는 항목을 선택하세요.", site_menu_keyboard(site))


def court_settings_keyboard(site: str) -> dict[str, Any]:
    with STATE_LOCK:
        if site == "yeonsu":
            selected = set(APP_SETTINGS.get("courts", ["A", "B", "C"]))
            values = ["A", "B", "C"]
        elif site == "songdo":
            selected = set(APP_SETTINGS.get("songdo_courts", list(range(5, 15))))
            values = list(range(5, 15))
        else:
            selected = set(APP_SETTINGS.get("saeachim_courts", [1, 2, 3, 4]))
            values = [1, 2, 3, 4]
    rows = []
    for i in range(0, len(values), 3):
        row = []
        for value in values[i:i+3]:
            mark = "✅" if value in selected else "⬜"
            prefix = "court" if site == "yeonsu" else f"{site}_court"
            label = f"{mark} {value}코트" if site in {"yeonsu", "saeachim"} else f"{mark} {value}번"
            row.append({"text": label, "callback_data": f"{prefix}:{value}"})
        rows.append(row)
    if site == "songdo":
        rows.append([{
            "text": "✅ 전체 선택" if len(selected) < 10 else "✅ 전체 선택됨",
            "callback_data": "songdo_courts:all" if len(selected) < 10 else "noop",
        }])
    elif site == "saeachim":
        rows.append([{
            "text": "✅ 전체 선택" if len(selected) < 4 else "✅ 전체 선택됨",
            "callback_data": "saeachim_courts:all" if len(selected) < 4 else "noop",
        }])
    rows.append([{"text": "⬅️ 공원 설정", "callback_data": f"site_menu:{site}"}])
    return {"inline_keyboard": rows}


def show_court_settings(site: str, message_id: int) -> None:
    name = {"yeonsu": "연수문화공원", "songdo": "달빛공원", "saeachim": "새아침테니스장"}[site]
    edit_telegram_message(message_id, f"🎾 <b>{name} 코트 선택</b>\n\n알림 받을 코트를 선택하세요.", court_settings_keyboard(site))


def surface_settings_keyboard() -> dict[str, Any]:
    with STATE_LOCK:
        selected = set(APP_SETTINGS.get("songdo_surfaces", ["hard", "artificial"]))
    return {"inline_keyboard": [
        [
            {"text": f"{'✅' if 'hard' in selected else '⬜'} 하드 (5~8)", "callback_data": "surface:hard"},
            {"text": f"{'✅' if 'artificial' in selected else '⬜'} 인조잔디 (9~14)", "callback_data": "surface:artificial"},
        ],
        [{"text": "⬅️ 달빛 설정", "callback_data": "site_menu:songdo"}],
    ]}


def show_surface_settings(message_id: int) -> None:
    edit_telegram_message(message_id, "🌱 <b>달빛공원 코트 재질</b>\n\n알림 받을 재질을 선택하세요.", surface_settings_keyboard())


def time_settings_keyboard(site: str) -> dict[str, Any]:
    with STATE_LOCK:
        weekday = APP_SETTINGS.get(f"{site}_weekday_hours")
        weekend = APP_SETTINGS.get(f"{site}_weekend_hours")

    def mark_selected(hours: list[int] | None, hour: int) -> str:
        return "✅" if hours is not None and hour in hours else "⬜"

    def all_mark(hours: list[int] | None) -> str:
        return "✅" if hours is None else "⬜"

    rows: list[list[dict[str, str]]] = []
    rows.append([{"text": "평일 시간", "callback_data": "noop"}])
    for a, b in ((6, 8), (10, 12), (14, 16), (18, 20)):
        rows.append([
            {"text": f"{mark_selected(weekday, a)} {a:02d}~{a+2:02d}", "callback_data": f"time:{site}:weekday:{a}"},
            {"text": f"{mark_selected(weekday, b)} {b:02d}~{b+2:02d}", "callback_data": f"time:{site}:weekday:{b}"},
        ])
    rows.append([
        {"text": f"{all_mark(weekday)} 평일 모든 시간", "callback_data": f"time:{site}:weekday:all"}
    ])
    rows.append([{"text": "주말 시간", "callback_data": "noop"}])
    for a, b in ((6, 8), (10, 12), (14, 16), (18, 20)):
        rows.append([
            {"text": f"{mark_selected(weekend, a)} {a:02d}~{a+2:02d}", "callback_data": f"time:{site}:weekend:{a}"},
            {"text": f"{mark_selected(weekend, b)} {b:02d}~{b+2:02d}", "callback_data": f"time:{site}:weekend:{b}"},
        ])
    rows.append([
        {"text": f"{all_mark(weekend)} 주말 모든 시간", "callback_data": f"time:{site}:weekend:all"}
    ])
    rows.append([{"text": "⬅️ 설정으로", "callback_data": "show:settings"}])
    return {"inline_keyboard": rows}


def show_time_settings(site: str, message_id: int) -> None:
    name = {"yeonsu": "연수문화공원", "songdo": "달빛공원", "saeachim": "새아침테니스장"}[site]
    weekday, weekend = site_hours_text(site)
    text = (
        f"⏰ <b>{name} 시간 설정</b>\n\n"
        "원하는 시간을 여러 개 선택할 수 있어요.\n"
        "‘모든 시간’을 누르면 시간 제한이 해제됩니다.\n\n"
        f"평일: <b>{escape(weekday)}</b>\n"
        f"주말: <b>{escape(weekend)}</b>"
    )
    edit_telegram_message(message_id, text, time_settings_keyboard(site))


def slot_block(slot: dict[str, Any]) -> str:
    return (
        f"🎾 <b>{escape(slot['court'])}</b>\n"
        f"📅 {escape(slot['date'])}\n"
        f"🕐 {escape(slot['time'])}\n"
        f"👉 <a href=\"{escape(slot['url'])}\"><b>예약하러 가기</b></a>"
    )


def send_slot_messages(header: str, slots: list[dict[str, Any]], footer: str) -> bool:
    messages: list[str] = []
    current = header + "\n\n"
    for slot in slots:
        block = slot_block(slot) + "\n\n"
        if len(current) + len(block) + len(footer) > 3600:
            messages.append(current.rstrip())
            current = "📋 <b>[이어서]</b>\n\n" + block
        else:
            current += block
    current += footer
    messages.append(current)
    return all(send_telegram_message(message) for message in messages)


def status_text() -> str:
    with STATE_LOCK:
        stats = APP_STATE["stats"].copy()
        current_count = len(APP_STATE["current_keys"])
    uptime_seconds = int(time.monotonic() - START_MONOTONIC)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes = remainder // 60

    return (
        "📊 <b>ChaenissBot 상태</b>\n\n"
        f"상태: 🟢 실행 중\n"
        f"가동 시간: {hours}시간 {minutes}분\n"
        f"마지막 검사: {escape(stats.get('last_check_at') or '아직 없음')}\n"
        f"현재 조건 일치: {current_count}개 (연수 {LAST_YEONSU_TARGETS} / 달빛 {LAST_SONGDO_TARGETS} / 새아침 {LAST_SAEACHIM_TARGETS})\n"
        f"전체 감지 빈자리: {LAST_TOTAL_SLOTS}개\n"
        f"달빛 조회: API 우선 / facilityId 10개 내장\n"
        f"최근 신규 알림: {LAST_NEW_COUNT}개\n\n"
        f"총 검사: {stats.get('checks', 0):,}회\n"
        f"알림 전송: {stats.get('alerts', 0):,}회\n"
        f"알림 빈자리: {stats.get('slots_notified', 0):,}개\n"
        f"오류: {stats.get('errors', 0):,}회\n"
        f"복구: {stats.get('recoveries', 0):,}회\n\n"
        f"{settings_text()}"
    )


def persist() -> None:
    with STATE_LOCK:
        save_state(APP_STATE)
        save_settings(APP_SETTINGS)


def update_slots(
    targets: list[dict[str, Any]],
    initialize: bool = False,
    preserve_sites: set[str] | None = None,
) -> None:
    global LAST_NEW_COUNT
    current_map = {slot_key(slot): slot for slot in targets}
    current_keys = set(current_map)
    preserve_sites = preserve_sites or set()

    with STATE_LOCK:
        previous_raw = APP_STATE.get("current_keys", [])
        previous_keys = set(previous_raw)

    # 실패한 사이트는 이전 키를 그대로 보존합니다.
    # 한 사이트 오류 때문에 다른 사이트 알림이 막히거나, 복구 후 대량 재알림되는 것을 방지합니다.
    for key in previous_keys:
        site = key.split("|", 1)[0]
        if site in preserve_sites:
            current_keys.add(key)

    with STATE_LOCK:
        reset_baseline = bool(APP_STATE.pop("reset_baseline", False))
        first_run = initialize or APP_STATE["stats"]["checks"] == 0 or reset_baseline
        APP_STATE["current_keys"] = sorted(current_keys)

    if first_run:
        send_telegram_message(
            "🟢 <b>ChaenissBot 시작 또는 재시작</b>\n\n"
            f"현재 조건 일치 빈자리: {len(current_keys)}개\n"
            f"{settings_text()}\n\n"
            f"⏰ {now_str()}"
        )
        LAST_NEW_COUNT = 0
        persist()
        return

    newly_opened_keys = current_keys - previous_keys
    closed_keys = previous_keys - current_keys
    newly_opened = [current_map[key] for key in sorted(newly_opened_keys)]
    LAST_NEW_COUNT = len(newly_opened)

    if newly_opened:
        ok = send_slot_messages(
            f"🚨 <b>신규 빈자리 {len(newly_opened)}개!</b>",
            newly_opened,
            f"⏰ 발견: {now_str()}",
        )
        if ok:
            with STATE_LOCK:
                APP_STATE["stats"]["alerts"] += 1
                APP_STATE["stats"]["slots_notified"] += len(newly_opened)
            log("ALERT", f"신규 빈자리 {len(newly_opened)}개 알림 완료")
    if closed_keys:
        log("INFO", f"사라진 빈자리 {len(closed_keys)}개 제거 — 다시 열리면 재알림")
    persist()


def monitor_loop() -> None:
    global LAST_TOTAL_SLOTS, LAST_TARGET_COUNT, LAST_YEONSU_TARGETS, LAST_SONGDO_TARGETS, LAST_SAEACHIM_TARGETS, LAST_ERROR
    next_heartbeat = now_kst() + timedelta(hours=HEARTBEAT_HOURS)
    error_started_at: datetime | None = None
    error_alert_sent = False
    initialized = False

    while True:
        started = time.monotonic()
        try:
            with STATE_LOCK:
                settings = {
                    "courts": list(APP_SETTINGS["courts"]),
                    "weekday_hours": APP_SETTINGS.get("weekday_hours"),
                    "weekend_hours": APP_SETTINGS.get("weekend_hours"),
                    "yeonsu_weekday_hours": APP_SETTINGS.get("yeonsu_weekday_hours"),
                    "yeonsu_weekend_hours": APP_SETTINGS.get("yeonsu_weekend_hours"),
                    "songdo_weekday_hours": APP_SETTINGS.get("songdo_weekday_hours"),
                    "songdo_weekend_hours": APP_SETTINGS.get("songdo_weekend_hours"),
                    "yeonsu_enabled": bool(APP_SETTINGS.get("yeonsu_enabled", True)),
                    "songdo_enabled": bool(APP_SETTINGS.get("songdo_enabled", False)),
                    "songdo_courts": list(APP_SETTINGS.get("songdo_courts", range(5, 15))),
                    "songdo_surfaces": list(APP_SETTINGS.get("songdo_surfaces", ["hard", "artificial"])),
                    "saeachim_weekday_hours": APP_SETTINGS.get("saeachim_weekday_hours"),
                    "saeachim_weekend_hours": APP_SETTINGS.get("saeachim_weekend_hours"),
                    "saeachim_enabled": bool(APP_SETTINGS.get("saeachim_enabled", True)),
                    "saeachim_courts": list(APP_SETTINGS.get("saeachim_courts", [1, 2, 3, 4])),
                }

            all_slots: list[dict[str, Any]] = []
            errors: list[str] = []
            failed_sites: set[str] = set()

            if settings["yeonsu_enabled"]:
                yeonsu_slots, yeonsu_errors = get_available_slots_with_status(settings["courts"])
                all_slots.extend(yeonsu_slots)
                if yeonsu_errors:
                    failed_sites.add("yeonsu")
                    errors.extend(yeonsu_errors)

            if settings["songdo_enabled"]:
                songdo_slots, songdo_errors = get_songdo_slots_with_status()
                all_slots.extend(songdo_slots)
                if songdo_errors:
                    failed_sites.add("songdo")
                    errors.extend(songdo_errors)

            if settings["saeachim_enabled"]:
                saeachim_slots, saeachim_errors = get_saeachim_slots_with_status(settings["saeachim_courts"])
                all_slots.extend(saeachim_slots)
                if saeachim_errors:
                    failed_sites.add("saeachim")
                    errors.extend(saeachim_errors)

            targets = [slot for slot in all_slots if matches_settings(slot, settings)]

            songdo_targets = [s for s in targets if s.get("site") == "songdo"]
            yeonsu_targets = [s for s in targets if s.get("site") == "yeonsu"]
            saeachim_targets = [s for s in targets if s.get("site") == "saeachim"]

            LAST_TOTAL_SLOTS = len(all_slots)
            LAST_TARGET_COUNT = len(targets)
            LAST_YEONSU_TARGETS = len(yeonsu_targets)
            LAST_SONGDO_TARGETS = len(songdo_targets)
            LAST_SAEACHIM_TARGETS = len(saeachim_targets)

            with STATE_LOCK:
                APP_STATE["stats"]["checks"] += 1
                APP_STATE["stats"]["last_check_at"] = now_str()

            update_slots(targets, initialize=not initialized, preserve_sites=failed_sites)
            initialized = True

            if errors:
                LAST_ERROR = " | ".join(errors)
                log("WARN", f"일부 사이트 조회 실패 — 나머지 사이트는 계속 처리: {LAST_ERROR}")
                with STATE_LOCK:
                    APP_STATE["stats"]["errors"] += 1
                persist()
                if error_started_at is None:
                    error_started_at = now_kst()
                elapsed_error = (now_kst() - error_started_at).total_seconds() / 60
                if elapsed_error >= ERROR_ALERT_MINUTES and not error_alert_sent:
                    send_telegram_message(
                        "⚠️ <b>일부 사이트 조회 오류 지속</b>\n\n"
                        f"지속 시간: 약 {int(elapsed_error)}분\n"
                        f"내용: {escape(LAST_ERROR)}\n\n"
                        "정상인 사이트 감시와 알림은 계속됩니다."
                    )
                    error_alert_sent = True
            else:
                if error_started_at is not None:
                    duration = max(1, int((now_kst() - error_started_at).total_seconds() // 60))
                    if error_alert_sent:
                        send_telegram_message(
                            "✅ <b>조회 정상 복구</b>\n\n"
                            f"오류 지속: 약 {duration}분\n"
                            f"복구 시간: {now_str()}"
                        )
                    with STATE_LOCK:
                        APP_STATE["stats"]["recoveries"] += 1
                    persist()
                    log("OK", "사이트 조회 정상 복구")
                error_started_at = None
                error_alert_sent = False
                LAST_ERROR = ""

            if now_kst() >= next_heartbeat:
                send_telegram_message("💚 <b>정상 작동 중</b>\n\n" + status_text())
                next_heartbeat = now_kst() + timedelta(hours=HEARTBEAT_HOURS)

            log(
                "OK",
                f"전체 {LAST_TOTAL_SLOTS} | 조건 연수 {LAST_YEONSU_TARGETS}·달빛 {LAST_SONGDO_TARGETS}·새아침 {LAST_SAEACHIM_TARGETS} | 신규 {LAST_NEW_COUNT} | {CHECK_INTERVAL}초 후",
            )

        except Exception as exc:
            LAST_ERROR = f"{type(exc).__name__}: {exc}"
            log("ERROR", LAST_ERROR)
            with STATE_LOCK:
                APP_STATE["stats"]["errors"] += 1
            persist()

            if error_started_at is None:
                error_started_at = now_kst()

            elapsed_error = (now_kst() - error_started_at).total_seconds() / 60
            if elapsed_error >= ERROR_ALERT_MINUTES and not error_alert_sent:
                send_telegram_message(
                    "⚠️ <b>ChaenissBot 오류 지속</b>\n\n"
                    f"지속 시간: 약 {int(elapsed_error)}분\n"
                    f"내용: {escape(LAST_ERROR)}\n\n"
                    "봇은 멈추지 않고 자동 재시도합니다."
                )
                error_alert_sent = True

        elapsed = time.monotonic() - started
        time.sleep(max(1, CHECK_INTERVAL - elapsed))


def show_settings(message_id: int | None = None) -> None:
    text = "⚙️ <b>알림 설정</b>\n\n버튼을 누르면 즉시 변경됩니다.\n\n" + settings_text()
    keyboard = settings_keyboard()
    if message_id is None:
        send_telegram_message(text, keyboard)
    else:
        edit_telegram_message(message_id, text, keyboard)


def apply_callback(data: str) -> str:
    with STATE_LOCK:
        if data == "site:yeonsu":
            enabled = not bool(APP_SETTINGS.get("yeonsu_enabled", True))
            if not enabled and not bool(APP_SETTINGS.get("songdo_enabled", False)) and not bool(APP_SETTINGS.get("saeachim_enabled", True)):
                return "감시 사이트는 최소 1개가 필요합니다."
            APP_SETTINGS["yeonsu_enabled"] = enabled
            result = f"연수문화공원 감시 {'켬' if enabled else '끔'}"
        elif data == "site:songdo":
            enabled = not bool(APP_SETTINGS.get("songdo_enabled", False))
            if not enabled and not bool(APP_SETTINGS.get("yeonsu_enabled", True)) and not bool(APP_SETTINGS.get("saeachim_enabled", True)):
                return "감시 사이트는 최소 1개가 필요합니다."
            APP_SETTINGS["songdo_enabled"] = enabled
            result = f"달빛공원 감시 {'켬' if enabled else '끔'}"
        elif data == "site:saeachim":
            enabled = not bool(APP_SETTINGS.get("saeachim_enabled", True))
            if not enabled and not bool(APP_SETTINGS.get("yeonsu_enabled", True)) and not bool(APP_SETTINGS.get("songdo_enabled", False)):
                return "감시 사이트는 최소 1개가 필요합니다."
            APP_SETTINGS["saeachim_enabled"] = enabled
            result = f"새아침테니스장 감시 {'켬' if enabled else '끔'}"
        elif data.startswith("court:"):
            court = data.split(":", 1)[1]
            courts = set(APP_SETTINGS["courts"])
            if court in courts and len(courts) > 1:
                courts.remove(court)
                result = f"{court}코트 알림 끔"
            elif court not in courts:
                courts.add(court)
                result = f"{court}코트 알림 켬"
            else:
                return "코트는 최소 1개가 필요합니다."
            APP_SETTINGS["courts"] = sorted(courts)

        elif data.startswith("songdo_court:"):
            court = int(data.split(":", 1)[1])
            courts = set(APP_SETTINGS.get("songdo_courts", range(5, 15)))
            if court in courts and len(courts) > 1:
                courts.remove(court)
                result = f"달빛 {court}번 알림 끔"
            elif court not in courts:
                courts.add(court)
                result = f"달빛 {court}번 알림 켬"
            else:
                return "달빛 코트는 최소 1개가 필요합니다."
            APP_SETTINGS["songdo_courts"] = sorted(courts)
        elif data == "songdo_courts:all":
            APP_SETTINGS["songdo_courts"] = list(range(5, 15))
            result = "달빛 코트 전체 선택"
        elif data == "songdo_courts:none":
            return "달빛 코트는 최소 1개가 필요합니다."
        elif data.startswith("saeachim_court:"):
            court = int(data.split(":", 1)[1])
            courts = set(APP_SETTINGS.get("saeachim_courts", [1, 2, 3, 4]))
            if court in courts and len(courts) > 1:
                courts.remove(court)
                result = f"새아침 {court}코트 알림 끔"
            elif court not in courts:
                courts.add(court)
                result = f"새아침 {court}코트 알림 켬"
            else:
                return "새아침 코트는 최소 1개가 필요합니다."
            APP_SETTINGS["saeachim_courts"] = sorted(courts)
        elif data == "saeachim_courts:all":
            APP_SETTINGS["saeachim_courts"] = [1, 2, 3, 4]
            result = "새아침 코트 전체 선택"
        elif data.startswith("surface:"):
            surface = data.split(":", 1)[1]
            selected = set(APP_SETTINGS.get("songdo_surfaces", ["hard", "artificial"]))
            if surface in selected and len(selected) > 1:
                selected.remove(surface)
                result = "해당 재질 알림 끔"
            elif surface not in selected:
                selected.add(surface)
                result = "해당 재질 알림 켬"
            else:
                return "코트 재질은 최소 1개가 필요합니다."
            APP_SETTINGS["songdo_surfaces"] = sorted(selected)
        elif data.startswith("time:"):
            _, site, day_type, value = data.split(":", 3)
            if site not in {"yeonsu", "songdo", "saeachim"} or day_type not in {"weekday", "weekend"}:
                return "잘못된 시간 설정입니다."
            key = f"{site}_{day_type}_hours"
            if value == "all":
                APP_SETTINGS[key] = None
                result = "모든 시간 알림으로 변경"
            else:
                hour = int(value)
                current = APP_SETTINGS.get(key)
                # 모든 시간 상태에서 개별 시간을 누르면 그 시간만 선택합니다.
                selected = set() if current is None else set(current)
                if hour in selected:
                    selected.remove(hour)
                    result = f"{hour:02d}~{hour+2:02d} 알림 끔"
                else:
                    selected.add(hour)
                    result = f"{hour:02d}~{hour+2:02d} 알림 켬"
                APP_SETTINGS[key] = sorted(selected)
        else:
            return "새로고침했습니다."

        # 설정 변경 후 기존 키를 초기화하여 새 조건에서 과거 상태가 섞이지 않게 합니다.
        APP_STATE["current_keys"] = []
        APP_STATE["reset_baseline"] = True
        save_settings(APP_SETTINGS)
        save_state(APP_STATE)
        return result


def handle_update(update: dict[str, Any]) -> None:
    callback = update.get("callback_query")
    if callback:
        sender_chat = str(callback.get("message", {}).get("chat", {}).get("id", ""))
        if sender_chat != str(__import__("config").CHAT_ID):
            answer_callback_query(callback["id"], "허용되지 않은 사용자입니다.")
            return

        data = callback.get("data", "")
        message_id = callback.get("message", {}).get("message_id")

        if data == "show:status":
            answer_callback_query(callback["id"])
            if message_id:
                edit_telegram_message(
                    message_id,
                    status_text(),
                    {"inline_keyboard": [[{"text": "⚙️ 설정으로", "callback_data": "show:settings"}]]},
                )
            return

        if data.startswith("site_menu:"):
            site = data.split(":", 1)[1]
            answer_callback_query(callback["id"])
            if message_id and site in {"yeonsu", "songdo", "saeachim"}:
                show_site_menu(site, message_id)
            return

        if data.startswith("court_menu:"):
            site = data.split(":", 1)[1]
            answer_callback_query(callback["id"])
            if message_id and site in {"yeonsu", "songdo", "saeachim"}:
                show_court_settings(site, message_id)
            return

        if data == "surface_menu":
            answer_callback_query(callback["id"])
            if message_id:
                show_surface_settings(message_id)
            return

        if data.startswith("time_menu:"):
            site = data.split(":", 1)[1]
            answer_callback_query(callback["id"])
            if message_id and site in {"yeonsu", "songdo", "saeachim"}:
                show_time_settings(site, message_id)
            return

        if data == "noop":
            answer_callback_query(callback["id"])
            return

        result = apply_callback(data)
        answer_callback_query(callback["id"], result)
        if message_id:
            if data.startswith("time:"):
                site = data.split(":", 2)[1]
                show_time_settings(site, message_id)
            elif data.startswith("songdo_court:") or data.startswith("songdo_courts:"):
                show_court_settings("songdo", message_id)
            elif data.startswith("saeachim_court:") or data.startswith("saeachim_courts:"):
                show_court_settings("saeachim", message_id)
            elif data.startswith("court:"):
                show_court_settings("yeonsu", message_id)
            elif data.startswith("surface:"):
                show_surface_settings(message_id)
            else:
                show_settings(message_id)
        return

    message = update.get("message")
    if not message:
        return

    sender_chat = str(message.get("chat", {}).get("id", ""))
    if sender_chat != str(__import__("config").CHAT_ID):
        return

    command = (message.get("text") or "").split()[0].lower()
    if command in {"/start", "/help"}:
        send_telegram_message(
            "🎾 <b>ChaenissBot 명령어</b>\n\n"
            "/settings — 코트·시간 설정\n"
            "/status — 상태와 통계\n"
            "/stats — 통계\n"
            "/check — 즉시 현재 상태 확인\n"
            "/help — 도움말"
        )
    elif command == "/settings":
        show_settings()
    elif command in {"/status", "/stats", "/check"}:
        send_telegram_message(status_text())
    else:
        send_telegram_message("명령어를 모르겠어요. /help 를 보내주세요.")


def telegram_command_loop() -> None:
    while True:
        try:
            with STATE_LOCK:
                offset = int(APP_STATE.get("telegram_offset", 0))

            updates = get_updates(offset, TELEGRAM_POLL_TIMEOUT)
            for update in updates:
                handle_update(update)
                with STATE_LOCK:
                    APP_STATE["telegram_offset"] = int(update["update_id"]) + 1
                    save_state(APP_STATE)
        except Exception as exc:
            log("ERROR", f"텔레그램 명령 처리 오류: {type(exc).__name__}: {exc}")
            time.sleep(5)


def run_supervised(name: str, target: Any) -> None:
    while True:
        try:
            log("START", f"{name} 시작")
            target()
        except Exception:
            log("CRASH", f"{name} 비정상 종료 — 10초 후 자동 재시작")
            traceback.print_exc()
            send_telegram_message(
                f"🔄 <b>{escape(name)} 자동 복구 중</b>\n\n10초 후 재시작합니다."
            )
            time.sleep(10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-telegram", action="store_true")
    args = parser.parse_args()

    if args.test_telegram:
        ok = send_telegram_message(f"✅ <b>텔레그램 연결 정상</b>\n{now_str()}")
        raise SystemExit(0 if ok else 1)

    log("START", "ChaenissBot v7.2 새아침 독립 추가 실행")
    log("INFO", settings_text().replace("<b>", "").replace("</b>", "").replace("\n", " | "))

    command_thread = threading.Thread(
        target=run_supervised,
        args=("텔레그램 명령 수신", telegram_command_loop),
        daemon=True,
    )
    command_thread.start()

    run_supervised("예약 감시", monitor_loop)


if __name__ == "__main__":
    main()