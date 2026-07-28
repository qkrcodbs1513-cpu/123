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


def settings_text() -> str:
    with STATE_LOCK:
        courts = "/".join(APP_SETTINGS["courts"])
        weekday = hours_text(APP_SETTINGS["weekday_hours"])
        weekend = hours_text(APP_SETTINGS["weekend_hours"])
        yeonsu_enabled = bool(APP_SETTINGS.get("yeonsu_enabled", True))
        songdo_enabled = bool(APP_SETTINGS.get("songdo_enabled", False))
    return (
        f"🏟️ 연수문화공원: <b>{'켜짐' if yeonsu_enabled else '꺼짐'}</b>\n"
        f"🌙 달빛공원(베타): <b>{'켜짐' if songdo_enabled else '꺼짐'}</b>\n"
        f"🎾 연수 코트: <b>{escape(courts)}</b>\n"
        f"📆 평일: <b>{escape(weekday)}</b>\n"
        f"🌈 주말: <b>{escape(weekend)}</b>\n"
        f"🔁 검사 주기: <b>{CHECK_INTERVAL}초</b>"
    )


def settings_keyboard() -> dict[str, Any]:
    with STATE_LOCK:
        courts = set(APP_SETTINGS["courts"])
        weekday_all = APP_SETTINGS["weekday_hours"] is None
        weekend_all = APP_SETTINGS["weekend_hours"] is None
        yeonsu_enabled = bool(APP_SETTINGS.get("yeonsu_enabled", True))
        songdo_enabled = bool(APP_SETTINGS.get("songdo_enabled", False))

    def mark(enabled: bool) -> str:
        return "✅" if enabled else "⬜"

    return {
        "inline_keyboard": [
            [
                {"text": f"{mark(yeonsu_enabled)} 연수문화공원", "callback_data": "site:yeonsu"},
                {"text": f"{mark(songdo_enabled)} 달빛공원 β", "callback_data": "site:songdo"},
            ],
            [
                {"text": f"{mark('A' in courts)} A코트", "callback_data": "court:A"},
                {"text": f"{mark('B' in courts)} B코트", "callback_data": "court:B"},
                {"text": f"{mark('C' in courts)} C코트", "callback_data": "court:C"},
            ],
            [
                {
                    "text": f"{mark(not weekday_all)} 평일 20~22",
                    "callback_data": "weekday:20",
                },
                {
                    "text": f"{mark(weekday_all)} 평일 전 시간",
                    "callback_data": "weekday:all",
                },
            ],
            [
                {
                    "text": f"{mark(weekend_all)} 주말 전 시간",
                    "callback_data": "weekend:all",
                },
                {
                    "text": f"{mark(not weekend_all)} 주말 20~22",
                    "callback_data": "weekend:20",
                },
            ],
            [
                {"text": "📊 상태·통계", "callback_data": "show:status"},
                {"text": "🔄 새로고침", "callback_data": "show:settings"},
            ],
        ]
    }


def slot_block(slot: dict[str, Any]) -> str:
    return (
        f"🎾 <b>{escape(slot['court'])}</b>\n"
        f"📅 {escape(slot['date'])}\n"
        f"🕐 {escape(slot['time'])}\n"
        f"🔗 <a href=\"{escape(slot['url'])}\">예약하기</a>"
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
        f"현재 조건 일치: {current_count}개\n"
        f"전체 감지 빈자리: {LAST_TOTAL_SLOTS}개\n\n"
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


def update_slots(targets: list[dict[str, Any]], initialize: bool = False) -> None:
    current_map = {slot_key(slot): slot for slot in targets}
    current_keys = set(current_map)

    with STATE_LOCK:
        previous_raw = APP_STATE.get("current_keys", [])
        previous_keys = set(previous_raw)
        first_run = initialize or APP_STATE["stats"]["checks"] == 0
        APP_STATE["current_keys"] = sorted(current_keys)

    if first_run:
        send_telegram_message(
            "🟢 <b>ChaenissBot 시작 또는 재시작</b>\n\n"
            f"현재 조건 일치 빈자리: {len(current_keys)}개\n"
            f"{settings_text()}\n\n"
            f"⏰ {now_str()}"
        )
        persist()
        return

    newly_opened_keys = current_keys - previous_keys
    closed_keys = previous_keys - current_keys
    newly_opened = [current_map[key] for key in sorted(newly_opened_keys)]

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
    global LAST_TOTAL_SLOTS, LAST_TARGET_COUNT, LAST_ERROR
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
                    "weekday_hours": APP_SETTINGS["weekday_hours"],
                    "weekend_hours": APP_SETTINGS["weekend_hours"],
                    "yeonsu_enabled": bool(APP_SETTINGS.get("yeonsu_enabled", True)),
                    "songdo_enabled": bool(APP_SETTINGS.get("songdo_enabled", False)),
                }

            all_slots: list[dict[str, Any]] = []
            errors: list[str] = []
            if settings["yeonsu_enabled"]:
                yeonsu_slots, yeonsu_errors = get_available_slots_with_status(settings["courts"])
                all_slots.extend(yeonsu_slots)
                errors.extend(yeonsu_errors)
            if settings["songdo_enabled"]:
                songdo_slots, songdo_errors = get_songdo_slots_with_status()
                all_slots.extend(songdo_slots)
                errors.extend(songdo_errors)
            if errors:
                raise RuntimeError(" | ".join(errors))

            targets = [slot for slot in all_slots if matches_settings(slot, settings)]

            songdo_targets = [s for s in targets if s.get("site") == "songdo"]
            yeonsu_targets = [s for s in targets if s.get("site") == "yeonsu"]

            log(
                "INFO",
                f"연수 대상 {len(yeonsu_targets)}개 | 달빛 대상 {len(songdo_targets)}개",
            )

            for slot in songdo_targets:
                log(
                    "INFO",
                    f"[DALBIT TARGET] {slot['court']} {slot['date']} {slot['time']}",
                )

            LAST_TOTAL_SLOTS = len(all_slots)
            LAST_TARGET_COUNT = len(targets)

            with STATE_LOCK:
                APP_STATE["stats"]["checks"] += 1
                APP_STATE["stats"]["last_check_at"] = now_str()

            update_slots(targets, initialize=not initialized)
            initialized = True

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
                f"전체 {LAST_TOTAL_SLOTS}개 | 조건 일치 {LAST_TARGET_COUNT}개 | "
                f"다음 검사 {CHECK_INTERVAL}초 후",
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
            if not enabled and not bool(APP_SETTINGS.get("songdo_enabled", False)):
                return "감시 사이트는 최소 1개가 필요합니다."
            APP_SETTINGS["yeonsu_enabled"] = enabled
            result = f"연수문화공원 감시 {'켬' if enabled else '끔'}"
        elif data == "site:songdo":
            enabled = not bool(APP_SETTINGS.get("songdo_enabled", False))
            if not enabled and not bool(APP_SETTINGS.get("yeonsu_enabled", True)):
                return "감시 사이트는 최소 1개가 필요합니다."
            APP_SETTINGS["songdo_enabled"] = enabled
            result = f"달빛공원 감시 {'켬' if enabled else '끔'}"
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

        elif data == "weekday:20":
            APP_SETTINGS["weekday_hours"] = [20]
            result = "평일 20~22시만 알림"
        elif data == "weekday:all":
            APP_SETTINGS["weekday_hours"] = None
            result = "평일 모든 시간 알림"
        elif data == "weekend:20":
            APP_SETTINGS["weekend_hours"] = [20]
            result = "주말 20~22시만 알림"
        elif data == "weekend:all":
            APP_SETTINGS["weekend_hours"] = None
            result = "주말 모든 시간 알림"
        else:
            return "새로고침했습니다."

        # 설정 변경 후 기존 키를 초기화하여 새 조건에서 과거 상태가 섞이지 않게 합니다.
        APP_STATE["current_keys"] = []
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

        result = apply_callback(data)
        answer_callback_query(callback["id"], result)
        if message_id:
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

    log("START", "ChaenissBot v6.1.14 EXACT-TIME 진단 실행")
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