import json
import os
import time
from datetime import datetime, timedelta, timezone
from scraper import get_available_slots
from telegram_bot import send_telegram_message

SEEN_FILE = "seen.json"

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
    weekday = slot.get("weekday_num", 0) # 5:토, 6:일
    time_str = slot.get("time", "")

    # 주말 -> 전체 허용
    if weekday in [5, 6]:
        return True

    # 평일 -> 20~22시 허용
    if "20~22" in time_str or "20시" in time_str or "21시" in time_str:
        return True

    return False

def send_chunked_messages(header, slot_blocks, footer):
    current_msg = header + "\n\n"
    for block in slot_blocks:
        if len(current_msg) + len(block) + 200 > 3800:
            send_telegram_message(current_msg)
            time.sleep(0.5)
            current_msg = "📊 <b>[이어서 계속...]</b>\n\n" + block + "\n\n"
        else:
            current_msg += block + "\n\n"
    
    current_msg += footer
    send_telegram_message(current_msg)

def test_send_current_all():
    print("🧪 [연수문화공원 전용] 현재 현황 조회 및 테스트 발송...")
    slots = get_available_slots()
    target_slots = [s for s in slots if is_target_slot(s)]

    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    now_str = now.strftime(f"%Y-%m-%d ({weekdays[now.weekday()]}) %H:%M:%S")

    if target_slots:
        header = f"🏟️ <b>[연수문화공원 예약 가능 현황]</b> (총 {len(target_slots)}개)"
        blocks = []
        for slot in target_slots:
            b = f"🎾 <b>{slot['court']}</b>\n📅 {slot['date']} {slot['time']}\n🔗 <a href='{slot['url']}'>예약하기</a>"
            blocks.append(b)
        footer = f"⏰ 조회 시간: {now_str}"
        send_chunked_messages(header, blocks, footer)
    else:
        send_telegram_message(
            f"🏟️ <b>[연수문화공원 예약 가능 현황]</b>\n\n"
            f"💤 현재 조건(평일 20~22시/주말 전체)에 맞는 연수문화공원 자리가 없습니다.\n\n"
            f"⏰ 조회 시간: {now_str}"
        )

def run_check():
    seen = load_seen()
    slots = get_available_slots()

    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    now_str = now.strftime(f"%Y-%m-%d ({weekdays[now.weekday()]}) %H:%M:%S")

    new_slots = [s for s in slots if is_target_slot(s) and f"{s['court']}_{s['date']}_{s['time']}" not in seen]

    if new_slots:
        blocks = []
        for slot in new_slots:
            slot_key = f"{slot['court']}_{slot['date']}_{slot['time']}"
            seen.add(slot_key)
            b = f"🚨 <b>[NEW] {slot['court']} 취소표!</b>\n📅 {slot['date']} {slot['time']}\n🔗 <a href='{slot['url']}'>예약하기</a>"
            blocks.append(b)

        header = f"🚨 <b>[연수문화공원 신규 취소표 발생!]</b> (총 {len(new_slots)}개)"
        footer = f"⏰ 알림 시간: {now_str}"
        send_chunked_messages(header, blocks, footer)
        save_seen(seen)

if __name__ == "__main__":
    print("🚀 [연수문화공원 전용] 테니스장 감시 로봇 가동!")
    try:
        test_send_current_all()
    except Exception as e:
        print(f"⚠️ 초기 전송 에러: {e}")

    while True:
        try:
            run_check()
        except Exception as e:
            print(f"⚠️ 실행 에러: {e}")
        time.sleep(30)
