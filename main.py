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
    """
    조건 필터링:
    - 평일(월~금): 20시~22시 관련 슬롯
    - 주말(토~일): 모든 시간대 허용
    """
    weekday = slot.get("weekday_num", 0)  # 0:월 ~ 6:일
    time_str = slot.get("time", "")

    # 주말 (토:5, 일:6) -> 모든 시간 허용
    if weekday in [5, 6]:
        return True

    # 평일 (월~금) -> 20시~22시 관련 슬롯만 허용
    if "20~22" in time_str or "20시" in time_str or "21시" in time_str:
        return True

    return False

def test_send_current_all():
    """서버 시작 시 현재 예약 가능한 전체 현황을 텔레그램으로 1회 강제 발송"""
    print("🧪 [테스트] 현재 예약 가능 현황 스캔 중...")
    slots = get_available_slots()
    target_slots = [s for s in slots if is_target_slot(s)]

    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    now_str = now.strftime(f"%Y-%m-%d ({weekdays[now.weekday()]}) %H:%M:%S")

    if target_slots:
        message_blocks = [f"📊 <b>[현재 예약 가능 코트 현황]</b> (총 {len(target_slots)}개)"]
        for slot in target_slots:
            block = (
                f"🎾 <b>{slot['court']}</b>\n"
                f"📅 {slot['date']} {slot['time']}\n"
                f"🔗 <a href='{slot['url']}'>예약하기</a>"
            )
            message_blocks.append(block)

        message_blocks.append(f"⏰ 조회 시간: {now_str}")
        send_telegram_message("\n\n".join(message_blocks))
        print("✅ [테스트] 현재 예약 가능한 전체 현황 발송 완료!")
    else:
        send_telegram_message(
            f"📊 <b>[현재 예약 가능 코트 현황]</b>\n\n"
            f"💤 현재 조건(평일 20~22시 / 주말)에 맞는 빈자리가 없습니다.\n\n"
            f"⏰ 조회 시간: {now_str}\n"
            f"💡 지금부터 30초 간격으로 취소표를 실시간 감시합니다!"
        )
        print("✅ [테스트] 빈자리 없음 현황 메시지 발송 완료!")

def run_check():
    seen = load_seen()
    slots = get_available_slots()

    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    now_str = now.strftime(f"%Y-%m-%d ({weekdays[now.weekday()]}) %H:%M:%S")

    new_slots = []

    for slot in slots:
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
                f"🚨 <b>[NEW] {slot['court']} 취소표 발생!</b>\n"
                f"📅 {slot['date']} {slot['time']}\n"
                f"🔗 <a href='{slot['url']}'>예약 페이지 바로가기</a>"
            )
            message_blocks.append(block)

        footer = f"⏰ 알림 시간: {now_str}"
        final_message = "\n\n".join(message_blocks) + "\n\n" + footer
        send_telegram_message(final_message)

        save_seen(seen)
        print("📩 조건에 맞는 신규 예약 알림 전송 완료!")
    else:
        print("💤 조건에 맞는 새로운 예약 가능 내역이 없습니다.")

if __name__ == "__main__":
    print("🚀 테니스장(연수문화/달빛/새아침) 감시 로봇 시작")
    
    # 1. 시작하자마자 현재 전체 상태 텔레그램으로 1회 발송
    try:
        test_send_current_all()
    except Exception as e:
        print(f"⚠️ 테스트 전송 실패: {e}")

    # 2. 이후 30초마다 새로운 취소표 감시 루프
    while True:
        try:
            run_check()
        except Exception as e:
            print(f"⚠️ 실행 중 오류 발생: {e}")
        time.sleep(30)
