from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import CHECK_INTERVAL, HEARTBEAT_HOURS
from scraper import get_available_slots, is_target_slot, slot_key
from telegram_bot import escape, send_telegram_message

KST = timezone(timedelta(hours=9))
STATE_FILE = Path(os.getenv("STATE_FILE", "current_slots.json"))
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]


def now_kst() -> datetime:
    return datetime.now(KST)


def now_str() -> str:
    now = now_kst()
    return now.strftime(f"%Y-%m-%d ({WEEKDAYS_KO[now.weekday()]}) %H:%M:%S")


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


def slot_block(slot: dict[str, Any], icon: str = "🎾") -> str:
    return (
        f"{icon} <b>{escape(slot['court'])}</b>\n"
        f"📅 {escape(slot['date'])}\n"
        f"🕐 {escape(slot['time'])}\n"
        f"🔗 <a href=\"{escape(slot['url'])}\">바로 예약하기</a>"
    )


def send_blocks(header: str, slots: list[dict[str, Any]], footer: str) -> bool:
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


def fetch_targets() -> list[dict[str, Any]]:
    slots = get_available_slots()
    targets = target_slots(slots)
    print(
        f"✅ 검사 완료: 전체 빈자리 {len(slots)}개 / "
        f"알림 조건 일치 {len(targets)}개 / {now_str()}",
        flush=True,
    )
    return targets


def send_startup_report(targets: list[dict[str, Any]]) -> None:
    if targets:
        send_blocks(
            f"🟢 <b>ChaenissBot Railway 감시 시작</b>\n"
            f"현재 조건 일치 빈자리: {len(targets)}개",
            targets,
            f"⏰ 확인 시간: {now_str()}\n"
            f"🔁 검사 주기: {CHECK_INTERVAL}초",
        )
    else:
        send_telegram_message(
            "🟢 <b>ChaenissBot Railway 감시 시작</b>\n\n"
            "현재 조건에 맞는 빈자리는 0개입니다.\n"
            "평일 20~22시 / 주말 모든 시간을 계속 확인합니다.\n\n"
            f"⏰ 확인 시간: {now_str()}\n"
            f"🔁 검사 주기: {CHECK_INTERVAL}초"
        )


def run_once(previous_keys: set[str] | None) -> tuple[set[str], int]:
    targets = fetch_targets()
    current_map = {slot_key(slot): slot for slot in targets}
    current_keys = set(current_map)

    if previous_keys is None:
        # 최초 배포/재배포 때 현재 상태를 전송해서 봇이 제대로 읽는지 확인 가능.
        send_startup_report(targets)
        save_current_keys(current_keys)
        return current_keys, 0

    newly_opened_keys = current_keys - previous_keys
    newly_opened = [current_map[key] for key in sorted(newly_opened_keys)]

    if newly_opened:
        send_blocks(
            f"🚨 <b>연수문화공원 신규 빈자리 {len(newly_opened)}개!</b>",
            newly_opened,
            f"⏰ 발견 시간: {now_str()}",
        )
        print(f"🚨 신규 빈자리 {len(newly_opened)}개 알림 완료", flush=True)
    else:
        print("💤 새로 생긴 조건 일치 빈자리 없음", flush=True)

    # 현재 예약 가능 목록으로 매번 교체한다.
    # 따라서 사라졌다가 다시 열린 자리는 다시 신규로 감지된다.
    save_current_keys(current_keys)
    return current_keys, len(newly_opened)


def monitor() -> None:
    print("🚀 연수문화공원 A/B/C 감시 시작", flush=True)
    previous_keys = load_previous_keys()
    last_heartbeat = now_kst()
    consecutive_errors = 0

    while True:
        cycle_started = time.monotonic()
        try:
            previous_keys, _ = run_once(previous_keys)
            consecutive_errors = 0

            if now_kst() - last_heartbeat >= timedelta(hours=HEARTBEAT_HOURS):
                send_telegram_message(
                    "💚 <b>ChaenissBot 정상 작동 중</b>\n\n"
                    f"마지막 검사: {now_str()}\n"
                    f"현재 조건 일치 빈자리: {len(previous_keys)}개\n"
                    f"검사 주기: {CHECK_INTERVAL}초"
                )
                last_heartbeat = now_kst()
        except Exception as exc:
            consecutive_errors += 1
            print(f"⚠️ 검사 오류 ({consecutive_errors}회 연속): {exc}", flush=True)
            # 일시적인 사이트 오류는 계속 재시도하고, 반복 오류는 Telegram으로 알린다.
            if consecutive_errors in (3, 10) or consecutive_errors % 30 == 0:
                send_telegram_message(
                    "⚠️ <b>ChaenissBot 조회 오류</b>\n\n"
                    f"연속 오류: {consecutive_errors}회\n"
                    f"내용: {escape(exc)}\n"
                    f"시간: {now_str()}\n\n"
                    "프로세스는 종료하지 않고 자동 재시도합니다."
                )

        elapsed = time.monotonic() - cycle_started
        time.sleep(max(1, CHECK_INTERVAL - elapsed))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="한 번만 조회하고 종료")
    parser.add_argument("--test-telegram", action="store_true", help="텔레그램 연결만 테스트")
    args = parser.parse_args()

    if args.test_telegram:
        ok = send_telegram_message(
            f"✅ <b>ChaenissBot 텔레그램 테스트 성공</b>\n{now_str()}"
        )
        raise SystemExit(0 if ok else 1)

    if args.once:
        run_once(None)
        return

    monitor()


if __name__ == "__main__":
    main()
