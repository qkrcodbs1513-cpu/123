from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import (
    CHECK_INTERVAL,
    ERROR_ALERT_MINUTES,
    HEARTBEAT_HOURS,
    REOPEN_URGENT_SECONDS,
)
from scraper import get_available_slots_with_status, is_target_slot, slot_key
from telegram_bot import escape, send_telegram_message

KST = timezone(timedelta(hours=9))
STATE_FILE = Path(os.getenv("STATE_FILE", "bot_state.json"))
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]


def now_kst() -> datetime:
    return datetime.now(KST)


def now_str() -> str:
    now = now_kst()
    return now.strftime(f"%Y-%m-%d ({WEEKDAYS_KO[now.weekday()]}) %H:%M:%S")


def log(message: str) -> None:
    print(f"[{now_kst().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def default_state() -> dict[str, Any]:
    return {
        "current_keys": [],
        "closed_at": {},
        "daily_alert_date": now_kst().strftime("%Y-%m-%d"),
        "daily_alert_count": 0,
    }


def load_state() -> dict[str, Any]:
    state = default_state()
    if not STATE_FILE.exists():
        return state
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            state["current_keys"] = raw
            return state
        if isinstance(raw, dict):
            state.update(raw)
    except (OSError, json.JSONDecodeError):
        pass
    return state


def save_state(state: dict[str, Any]) -> None:
    temp_file = STATE_FILE.with_suffix(".tmp")
    temp_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_file.replace(STATE_FILE)


def reset_daily_counter_if_needed(state: dict[str, Any]) -> None:
    today = now_kst().strftime("%Y-%m-%d")
    if state.get("daily_alert_date") != today:
        state["daily_alert_date"] = today
        state["daily_alert_count"] = 0


def uptime_text(started_at: datetime) -> str:
    seconds = int((now_kst() - started_at).total_seconds())
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"{days}일 {hours}시간 {minutes}분"
    if hours:
        return f"{hours}시간 {minutes}분"
    return f"{minutes}분"


def target_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [slot for slot in slots if is_target_slot(slot)]


def send_slot_card(slot: dict[str, Any], reopened_seconds: int | None = None) -> bool:
    if reopened_seconds is None:
        title = "🎾🎾🎾 <b>새 빈자리 발견!</b>"
    elif reopened_seconds <= REOPEN_URGENT_SECONDS:
        title = "🚨🚨🚨 <b>긴급 재등장 빈자리!</b>"
    else:
        title = "🔁 <b>다시 열린 빈자리!</b>"

    message = (
        f"{title}\n\n"
        f"<b>{escape(slot['court'])}</b>\n"
        f"📅 {escape(slot['date'])}\n"
        f"🕐 {escape(slot['time'])}\n\n"
        f"⏰ 발견 시간: {now_str()}"
    )
    return send_telegram_message(message, button_url=slot["url"])


def send_startup_report(targets: list[dict[str, Any]]) -> None:
    send_telegram_message(
        "🟢 <b>ChaenissBot 시작 또는 재시작</b>\n\n"
        f"현재 조건 일치 빈자리: {len(targets)}개\n"
        "감시 조건: 평일 20:00~22:00 / 토·일 모든 시간\n"
        f"검사 주기: {CHECK_INTERVAL}초\n"
        f"생존 알림: {HEARTBEAT_HOURS}시간마다\n"
        f"시작 시간: {now_str()}"
    )


def update_slots(state: dict[str, Any], targets: list[dict[str, Any]]) -> tuple[int, int]:
    reset_daily_counter_if_needed(state)
    current_map = {slot_key(slot): slot for slot in targets}
    current_keys = set(current_map)
    previous_keys = set(state.get("current_keys", []))
    closed_at: dict[str, float] = dict(state.get("closed_at", {}))

    newly_opened_keys = sorted(current_keys - previous_keys)
    closed_keys = previous_keys - current_keys

    now_ts = now_kst().timestamp()
    for key in closed_keys:
        closed_at[key] = now_ts

    sent_count = 0
    for key in newly_opened_keys:
        reopened_seconds: int | None = None
        if key in closed_at:
            reopened_seconds = max(0, int(now_ts - float(closed_at[key])))
        if send_slot_card(current_map[key], reopened_seconds):
            sent_count += 1
            state["daily_alert_count"] = int(state.get("daily_alert_count", 0)) + 1
        closed_at.pop(key, None)

    # 7일이 지난 재등장 기록은 제거합니다.
    cutoff = now_ts - 7 * 86400
    closed_at = {key: ts for key, ts in closed_at.items() if float(ts) >= cutoff}

    state["current_keys"] = sorted(current_keys)
    state["closed_at"] = closed_at
    save_state(state)
    return sent_count, len(closed_keys)


def send_heartbeat(
    state: dict[str, Any],
    total_slots: int,
    started_at: datetime,
) -> None:
    reset_daily_counter_if_needed(state)
    send_telegram_message(
        "💚 <b>ChaenissBot 정상 작동 중</b>\n\n"
        f"마지막 검사: {now_str()}\n"
        f"현재 조건 일치 빈자리: {len(state.get('current_keys', []))}개\n"
        f"전체 감지 빈자리: {total_slots}개\n"
        f"오늘 신규 알림: {state.get('daily_alert_count', 0)}건\n"
        f"연속 가동시간: {uptime_text(started_at)}\n"
        f"검사 주기: {CHECK_INTERVAL}초"
    )
    save_state(state)
    log("💚 생존 확인 텔레그램 전송")


def error_summary(errors: list[str]) -> str:
    return "\n".join(f"• {escape(error)}" for error in errors[:5])


def compact_log(stats: dict[str, dict[str, int]], total: int, targets: int, new: int, closed: int, errors: int) -> None:
    parts = []
    for name in ("A", "B", "C"):
        item = stats.get(name, {"all": 0, "target": 0})
        parts.append(f"{name} {item['target']}개")
    log(
        "📊 " + " | ".join(parts) +
        f" | 전체 {total}개 | 조건 {targets}개 | 신규 {new}개 | 사라짐 {closed}개 | 오류 {errors}개"
    )


def monitor() -> None:
    started_at = now_kst()
    log("🚀 연수문화공원 A/B/C 감시 시작")
    log("📅 필터: 평일 20:00~22:00 / 토·일 모든 시간")
    log(f"⏱️ 검사 주기 {CHECK_INTERVAL}초 / 생존 알림 {HEARTBEAT_HOURS}시간")

    state = load_state()
    first_cycle = True
    next_heartbeat_at = now_kst() + timedelta(hours=HEARTBEAT_HOURS)
    error_started_at: datetime | None = None
    error_alert_sent = False
    last_total_slots = 0

    while True:
        cycle_started = time.monotonic()
        try:
            all_slots, court_errors, stats = get_available_slots_with_status()
            targets = target_slots(all_slots)
            last_total_slots = len(all_slots)

            if first_cycle:
                send_startup_report(targets)
                first_cycle = False

            new_count, closed_count = update_slots(state, targets)
            compact_log(stats, len(all_slots), len(targets), new_count, closed_count, len(court_errors))

            if court_errors:
                if error_started_at is None:
                    error_started_at = now_kst()
                    error_alert_sent = False
                    log(f"⚠️ 일부 코트 조회 오류 시작: {len(court_errors)}개")

                error_minutes = (now_kst() - error_started_at).total_seconds() / 60
                if error_minutes >= ERROR_ALERT_MINUTES and not error_alert_sent:
                    send_telegram_message(
                        "⚠️ <b>연수문화공원 사이트 조회 오류 지속</b>\n\n"
                        f"지속 시간: 약 {int(error_minutes)}분\n"
                        f"오류 코트: {len(court_errors)}개\n"
                        f"{error_summary(court_errors)}\n\n"
                        "봇은 종료하지 않고 계속 자동 재시도합니다."
                    )
                    error_alert_sent = True
                    log("⚠️ 지속 오류를 텔레그램으로 알림")
            else:
                if error_started_at is not None:
                    duration = int((now_kst() - error_started_at).total_seconds() // 60)
                    if error_alert_sent:
                        send_telegram_message(
                            "✅ <b>연수문화공원 사이트 조회 정상 복구</b>\n\n"
                            f"오류 지속 시간: 약 {duration}분\n"
                            f"복구 시간: {now_str()}"
                        )
                    log("✅ 모든 코트 조회 정상 복구")
                error_started_at = None
                error_alert_sent = False

            if now_kst() >= next_heartbeat_at:
                send_heartbeat(state, last_total_slots, started_at)
                next_heartbeat_at = now_kst() + timedelta(hours=HEARTBEAT_HOURS)

        except Exception as exc:
            if error_started_at is None:
                error_started_at = now_kst()
                error_alert_sent = False
            error_minutes = (now_kst() - error_started_at).total_seconds() / 60
            log(f"❌ 검사 예외: {type(exc).__name__} - {exc}")
            if error_minutes >= ERROR_ALERT_MINUTES and not error_alert_sent:
                send_telegram_message(
                    "⚠️ <b>ChaenissBot 오류가 5분 이상 지속 중</b>\n\n"
                    f"내용: {escape(type(exc).__name__)} - {escape(exc)}\n"
                    f"시간: {now_str()}\n\n"
                    "봇은 종료하지 않고 계속 자동 재시도합니다."
                )
                error_alert_sent = True

        elapsed = time.monotonic() - cycle_started
        time.sleep(max(1, CHECK_INTERVAL - elapsed))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--test-telegram", action="store_true")
    args = parser.parse_args()

    if args.test_telegram:
        ok = send_telegram_message(
            f"✅ <b>ChaenissBot 텔레그램 연결 정상</b>\n{now_str()}"
        )
        raise SystemExit(0 if ok else 1)

    if args.once:
        all_slots, errors, stats = get_available_slots_with_status()
        targets = target_slots(all_slots)
        compact_log(stats, len(all_slots), len(targets), 0, 0, len(errors))
        return

    monitor()


if __name__ == "__main__":
    main()
