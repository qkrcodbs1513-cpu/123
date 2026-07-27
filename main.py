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

    if weekday in [5, 6]:
        return True

    if "20~22" in time_str or "20시" in time_str or "21시" in time_str:
        return True

    return False

def categorize_by_venue(slots):
    venues = {
        "연수문화공원": [],
        "새아침공원": [],
        "송도달빛공원": []
    }
    for slot in slots:
        court_name = slot.get("court", "")
        if "연수문화" in court_name:
            venues["연수문화공원"].append(slot)
        elif "새아침" in court_name:
            venues["새아침공원"].append(slot)
        elif "달빛" in court_name:
            venues["송도달빛공원"].append(slot)
        else:
            venues["연수문화공원"].append(slot)
    return venues

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
    time.sleep(1)

def test_send_current_all():
    print("🧪 [테스트] 장소별 스캔 및 초기 메시지 발송...")
    slots = get_available_slots()
    target_slots = [s for s in slots if is_target_slot(s)]

    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    now_str = now.strftime(f"%Y-%m-%d ({weekdays[now.weekday()]}) %H:%M:%S")

    categorized = categorize_by_venue(target_slots)

    for venue_name, venue_slots in categorized.items():
        if venue_slots:
            header = f"🏟️ <b>[{venue_name} 예약 가능 현황]</b> (총 {len(venue_slots)}개)"
            blocks = []
            for slot in venue_slots:
                b = f"🎾 <b>{slot['court']}</b>\n📅 {slot['date']} {slot['time']}\n🔗 <a href='{slot['url']}'>예약하기</a>"
                blocks.append(b)
            footer = f"⏰ 조회 시간: {now_str}"
            send_chunked_messages(header, blocks, footer)
        else:
            send_telegram_message(
                f"🏟️ <b>[{venue_name} 예약 가능 현황]</b>\n\n"
                f"💤 조건(평일 20~22시/주말 전체)에 맞는 자리가 없습니다.\n\n"
                f"⏰ 조회 시간: {now_str}"
            )
            time.sleep(1)

def run_check():
    seen = load_seen()
    slots = get_available_slots()

    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    now_str = now.strftime(f"%Y-%m-%d ({weekdays[now.weekday()]}) %H:%M:%S")

    new_slots = [s for s in slots if is_target_slot(s) and f"{s['court']}_{s['date']}_{s['time']}" not in seen]

    if new_slots:
        categorized = categorize_by_venue(new_slots)

        for venue_name, venue_slots in categorized.items():
            if not venue_slots:
                continue

            blocks = []
            for slot in venue_slots:
                slot_key = f"{slot['court']}_{slot['date']}_{slot['time']}"
                seen.add(slot_key)
                b = f"🚨 <b>[NEW] {slot['court']} 취소표!</b>\n📅 {slot['date']} {slot['time']}\n🔗 <a href='{slot['url']}'>예약하기</a>"
                blocks.append(b)

            header = f"🚨 <b>[{venue_name} 신규 취소표 발생!]</b> (총 {len(venue_slots)}개)"
            footer = f"⏰ 알림 시간: {now_str}"
            send_chunked_messages(header, blocks, footer)

        save_seen(seen)

if __name__ == "__main__":
    print("🚀 테니스장 모니터링 로봇 시작!")
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
