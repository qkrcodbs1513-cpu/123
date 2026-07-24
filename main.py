import json
import os
from datetime import datetime
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

def run_check():
    seen = load_seen()
    slots = get_available_slots()

    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    now = datetime.now()
    now_str = now.strftime(f"%Y-%m-%d ({weekdays[now.weekday()]}) %H:%M:%S")

    new_slots = []

    for slot in slots:
        slot_key = f"{slot['court']}_{slot['date']}_{slot['time']}"
        if slot_key not in seen:
            new_slots.append(slot)
            seen.add(slot_key)

    if new_slots:
        message_blocks = []

        for slot in new_slots:
            # 요청하신 이모티콘 및 라인 구성
            block = (
                f"🎾 연수문화공원 예약가능!\n"
                f"📅 {slot['date']} {slot['time']}\n"
                f"{slot['court']}"
            )
            message_blocks.append(block)

        # 하단 현재 시간 및 링크 붙이기
        footer = (
            f"⏰ 현재 시간: {now_str}\n"
            f"🔗 <a href='https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp'>예약 페이지 바로가기</a>"
        )

        final_message = "\n\n".join(message_blocks) + "\n\n" + footer
        send_telegram_message(final_message)

        save_seen(seen)
        print("📩 양식에 맞춘 알림 전송 완료!")
    else:
        print("💤 새로운 예약 가능 내역이 없습니다.")

if __name__ == "__main__":
    print("🚀 테니스장 예약 감시 로봇 실행...")
    run_check()