from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import CHECK_INTERVAL, ERROR_ALERT_MINUTES, HEARTBEAT_HOURS
from scraper import get_available_slots_with_status, is_target_slot, slot_key
from telegram_bot import escape, send_telegram_message

KST = timezone(timedelta(hours=9))
STATE_FILE = Path(os.getenv("STATE_FILE", "current_slots.json"))
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]


def now_kst() -> datetime:
    return datetime.now(KST)


def now_str() -> str:
    now = now_kst()
    return now.strftime(f"%Y-%m-%d ({WEEKDAYS_KO[now.weekday()]}) %H:%M:%S")


def log(message: str) -> None:
    print(f"[{now_kst().strftime('%H:%M:%S')}] {message}", flush=True)


def load_previous_keys() -> set[str] | None:
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_current_keys(keys: set[str]) -> None:
    temp_file = STATE_FILE.with_suffix(".tmp")
    temp_file.write_text(
        json.dumps(sorted(keys), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_file.replace(STATE_FILE)


def target_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [slot for slot in slots if is_target_slot(slot)]


def slot_block(slot: dict[str, Any]) -> str:
    return (
        f"🎾 <b>{escape(slot['court'])}</b>\n"
        f"📅 {escape(slot['date'])}\n"
        f"🕐 {escape(slot['time'])}\n"
        f"🔗 <a href=\"{escape(slot['url'])}\">예약 페이지 바로 열기</a>"
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


def fetch_targets() -> tuple[list[dict[str, Any]], list[str], int]:
    log("🔄 예약 페이지 확인 시작")
    all_slots, court_errors = get_available_slots_with_status()
    targets = target_slots(all_slots)
    log(
        f"📊 검사 완료 | 전체 빈자리 {len(all_slots)}개 | "
        f"조건 일치 {len(targets)}개 | 조회 오류 코트 {len(court_errors)}개"
    )
    return targets, court_errors, len(all_slots)


def send_startup_report(targets: list[dict[str, Any]]) -> None:
    if targets:
        send_slot_messages(
            "🟢 <b>ChaenissBot 시작 또는 재시작</b>\n"
            f"현재 조건 일치 빈자리: {len(targets)}개",
            targets,
            f"⏰ 확인 시간: {now_str()}\n"
            f"🔁 검사 주기: {CHECK_INTERVAL}초\n"
            f"💚 생존 알림: {HEARTBEAT_HOURS}시간마다",
        )
    else:
        send_telegram_message(
            "🟢 <b>ChaenissBot 시작 또는 재시작</b>\n\n"
            "현재 조건에 맞는 빈자리는 0개입니다.\n"
            "평일 20~22시 / 주말 전 시간을 계속 확인합니다.\n\n"
            f"⏰ 확인 시간: {now_str()}\n"
            f"🔁 검사 주기: {CHECK_INTERVAL}초\n"
            f"💚 생존 알림: {HEARTBEAT_HOURS}시간마다"
        )


def update_slots(
    previous_keys: set[str] | None,
    targets: list[dict[str, Any]],
) -> tuple[set[str], int]:
    current_map = {slot_key(slot): slot for slot in targets}
    current_keys = set(current_map)

    if previous_keys is None:
        send_startup_report(targets)
        save_current_keys(current_keys)
        return current_keys, 0

    newly_opened_keys = current_keys - previous_keys
    closed_keys = previous_keys - current_keys
    newly_opened = [current_map[key] for key in sorted(newly_opened_keys)]

    if newly_opened:
        send_slot_messages(
            f"🚨 <b>연수문화공원 신규 빈자리 {len(newly_opened)}개!</b>",
            newly_opened,
            f"⏰ 발견 시간: {now_str()}",
        )
        log(f"🚨 신규 빈자리 {len(newly_opened)}개 텔레그램 알림 완료")
    else:
        log("💤 새로 생긴 조건 일치 빈자리 없음")

    if closed_keys:
        log(f"🔒 사라진 빈자리 {len(closed_keys)}개를 기억 목록에서 제거")

    # 사라진 자리는 현재 목록에서 제거됩니다. 나중에 다시 열리면 신규 알림이 다시 갑니다.
    save_current_keys(current_keys)
    return current_keys, len(newly_opened)


def send_heartbeat(current_keys: set[str], total_slots: int) -> None:
    send_telegram_message(
        "💚 <b>ChaenissBot 정상 작동 중</b>\n\n"
        f"마지막 검사: {now_str()}\n"
        f"현재 조건 일치 빈자리: {len(current_keys)}개\n"
        f"전체 감지 빈자리: {total_slots}개\n"
        f"검사 주기: {CHECK_INTERVAL}초\n"
        f"다음 생존 알림: 약 {HEARTBEAT_HOURS}시간 후"
    )
    log("💚 생존 확인 텔레그램 전송")


def error_summary(errors: list[str]) -> str:
    return "\n".join(f"• {escape(error)}" for error in errors[:5])


def monitor() -> None:
    log("🚀 연수문화공원 A/B/C 감시 시작")
    log("📅 필터: 평일 20:00~22:00 / 토·일 모든 시간")
    log(f"⏱️ 검사 주기 {CHECK_INTERVAL}초 / 생존 알림 {HEARTBEAT_HOURS}시간")

    previous_keys = load_previous_keys()
    next_heartbeat_at = now_kst() + timedelta(hours=HEARTBEAT_HOURS)
    error_started_at: datetime | None = None
    error_alert_sent = False
    last_total_slots = 0

    while True:
        cycle_started = time.monotonic()
        try:
            targets, court_errors, last_total_slots = fetch_targets()
            previous_keys, _ = update_slots(previous_keys, targets)

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
                    log("⚠️ 5분 이상 지속된 조회 오류를 텔레그램으로 알림")
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
                send_heartbeat(previous_keys, last_total_slots)
                next_heartbeat_at = now_kst() + timedelta(hours=HEARTBEAT_HOURS)

        except Exception as exc:
            # 예기치 않은 코드 오류도 같은 5분 기준으로 알립니다.
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
        targets, _, _ = fetch_targets()
        update_slots(None, targets)
        return

    monitor()


if __name__ == "__main__":
    main()
