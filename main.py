import json
import os
import time
from datetime import datetime, timedelta, timezone

from scraper import get_available_slots
from telegram_bot import send_telegram_message

SEEN_FILE = "seen.json"
KST = timezone(timedelta(hours=9))
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen(seen_set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_set), f, ensure_ascii=False, indent=2)


def is_target_slot(slot):
    """평일(월~금): 20~22시만 / 주말(토,일): 전체 시간 허용"""
    weekday = slot.get("weekday_num", 0)  # 0=월 ... 6=일
    time_str = slot.get("time", "")
    if weekday in [5, 6]:
        return True
    if "20~22" in time_str:
        return True
    return False


def now_str():
    now = datetime.now(KST)
    return now.strftime(f"%Y-%m-%d ({WEEKDAYS_KO[now.weekday()]}) %H:%M:%S")


def send_chunked(header, blocks, footer):
    """텔레그램 4000자 제한 대응: 길면 나눠서 전송"""
    current = header + "\n\n"
    for block in blocks:
        if len(current) + len(block) + 200 > 3500:
            send_telegram_message(current)
            time.sleep(0.5)
            current = "📊 <b>[이어서 계속]</b>\n\n" + block + "\n\n"
        else:
            current += block + "\n\n"
    current += footer
    send_telegram_message(current)


def format_block(slot, tag="🎾"):
    return (
        f"{tag} <b>{slot['court']}</b>\n"
        f"📅 {slot['date']} {slot['time']}\n"
        f"🔗 <a href='{slot['url']}'>예약하기</a>"
    )


def test_send_current_all():
    """봇 시작 시 현재 예약 가능한 전체 현황을 1회 발송 (동작 확인용)"""
    print("🧪 [테스트] 현재 예약 가능 현황 스캔 중...")
    slots = get_available_slots()
    targets = [s for s in slots if is_target_slot(s)]

    if targets:
        header = f"📊 <b>[현재 예약 가능 현황]</b> (총 {len(targets)}개)"
        blocks = [format_block(s) for s in targets]
        footer = f"⏰ 조회 시간: {now_str()}"
        send_chunked(header, blocks, footer)
    else:
        send_telegram_message(
            f"📊 <b>[현재 예약 가능 현황]</b>\n\n"
            f"💤 조건(평일 20~22시 / 주말 전체)에 맞는 자리가 없습니다.\n\n"
            f"⏰ 조회 시간: {now_str()}"
        )
    print("✅ [테스트] 발송 완료!")


def run_check():
    seen = load_seen()
    slots = get_available_slots()

    new_slots = []
    for slot in slots:
        if not is_target_slot(slot):
            continue
        key = f"{slot['court']}_{slot['date']}_{slot['time']}"
        if key not in seen:
            new_slots.append(slot)
            seen.add(key)

    if new_slots:
        header = f"🚨 <b>[신규 취소표 발생!]</b> (총 {len(new_slots)}개)"
        blocks = [format_block(s, tag="🚨") for s in new_slots]
        footer = f"⏰ 알림 시간: {now_str()}"
        send_chunked(header, blocks, footer)
        save_seen(seen)
        print("📩 신규 알림 전송 완료!")
    else:
        print(f"💤 [{now_str()}] 새로운 자리 없음.")


if __name__ == "__main__":
    print("🚀 연수문화공원/연수체육공원 테니스장 감시 로봇 시작!")

    try:
        test_send_current_all()
    except Exception as e:
        print(f"⚠️ 테스트 발송 에러: {e}")

    while True:
        try:
            run_check()
        except Exception as e:
            print(f"⚠️ 실행 중 에러: {e}")
        time.sleep(30)
