import json
import os
import time
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

def is_target_slot(slot):
    """
    조건 필터링:
    - 평일(월~금): 20시~22시 포함 슬롯
    - 주말(토~일): 모든 시간 허용
    """
    weekday = slot.get("weekday_num", 0)  # 0:월 ~ 6:일
    time_str = slot.get("time", "")

    # 주말 (토:5, 일:6) -> 모든 시간 허용
    if weekday in [5, 6]:
        return True

    # 평일 (월~금) -> 20시~22시 관련 슬롯만 허용
    if "20~22" in time_str or "20시" in time_str:
        return True

    return False

def run_check():
    seen = load_seen()
    slots = get_available_slots()

    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    now = datetime.now()
    now_str = now.strftime(f"%Y-%m-%d ({weekdays[now.weekday()]}) %H:%M:%S")

    new_slots = []

    for slot in slots:
        # 조건에 맞는 슬롯만 필터링
        if not is_target_slot(slot):
            continue

        slot_key = f"{slot['court']}_{slot['date']}_{slot['time']}"
        if slot_key not in seen:
            new_slots.append(slot)
            seen.add(slot_key)

    if new_slots:
        message_blocks = []

        for slot in new_slots:
            block = (
                f"🎾 연수문화공원 예약가능!\n"
                f"📅 {slot['date']} {slot['time']}\n"
                f"{slot['court']}"
            )
            message_blocks.append(block)

        footer = (
            f"⏰ 현재 시간: {now_str}\n"
            f"🔗 <a href='https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp'>예약 페이지 바로가기</a>"
        )

        final_message = "\n\n".join(message_blocks) + "\n\n" + footer
        send_telegram_message(final_message)

        save_seen(seen)
        print("📩 조건에 맞는 신규 예약 알림 전송 완료!")
    else:
        print("💤 조건에 맞는 새로운 예약 가능 내역이 없습니다.")

if __name__ == "__main__":
    # Railway 등에서 무한 루프로 주기적 실행 (예: 5분마다 감시)
    print("🚀 테니스장 예약 감시 로봇 실행 중... (5분 간격 감시)")
    while True:
        try:
            run_check()
        except Exception as e:
            print(f"⚠️ 실행 중 오류 발생: {e}")
        time.sleep(30)  # 30초 = 30초 마다 반복
