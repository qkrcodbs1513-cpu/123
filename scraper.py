import re
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

def clean_time_format(time_raw):
    match = re.search(r'(\d{2}):00~(\d{2}):00', time_raw)
    if match:
        return f"{int(match.group(1))}~{int(match.group(2))}시"
    time_match = re.search(r'(\d{2}:\d{2}(?:~\d{2}:\d{2})?)', time_raw)
    return time_match.group(1) if time_match else time_raw

def get_available_slots():
    available_slots = []
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst)
    weekday_idx = today.weekday()
    date_str = f"{today.strftime('%Y-%m-%d')} ({weekdays[weekday_idx]})"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1. 달빛공원 테니스장
        try:
            url_moonlight = "https://songdotennis.co.kr/songdo-tennis?tab=reservations"
            page.goto(url_moonlight, timeout=15000, wait_until="networkidle")
            
            # 페이지 내 모든 예약가능 텍스트/버튼 탐색
            elements = page.locator("text=/예약가능|신청|예약하기/").all()
            for elem in elements:
                text = elem.text_content() or ""
                parent_text = elem.evaluate("el => el.parentElement ? el.parentElement.innerText : ''")
                
                court_match = re.search(r'(\d+코트|[A-Za-z]+코트|제\d+코트)', parent_text)
                court_label = f"달빛공원 {court_match.group(1)}" if court_match else "달빛공원 테니스장"
                time_str = clean_time_format(parent_text)

                available_slots.append({
                    "court": court_label,
                    "date": date_str,
                    "time": time_str,
                    "weekday_num": weekday_idx,
                    "url": url_moonlight
                })
        except Exception as e:
            print(f"[달빛공원] 크롤링 에러: {e}")

        # 2. 새아침공원 테니스장
        try:
            url_newmorning = "https://res.insiseol.or.kr/rent/rentalSchedule?up_id=07"
            page.goto(url_newmorning, timeout=15000, wait_until="networkidle")
            
            elements = page.locator("text=/신청가능|예약가능|신청/").all()
            for elem in elements:
                parent_text = elem.evaluate("el => el.parentElement ? el.parentElement.innerText : ''")
                
                court_match = re.search(r'(\d+코트|\d+번코트|제\d+코트)', parent_text)
                court_label = f"새아침공원 {court_match.group(1)}" if court_match else "새아침공원 테니스장"
                time_str = clean_time_format(parent_text)

                available_slots.append({
                    "court": court_label,
                    "date": date_str,
                    "time": time_str,
                    "weekday_num": weekday_idx,
                    "url": url_newmorning
                })
        except Exception as e:
            print(f"[새아침공원] 크롤링 에러: {e}")

        # 3. 연수문화공원 테니스장
        courts_ys = {
            "연수문화공원 A코트": "https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq=1",
            "연수문화공원 B코트": "https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq=2",
            "연수문화공원 C코트": "https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq=3",
        }
        for court_name, url in courts_ys.items():
            try:
                page.goto(url, timeout=15000, wait_until="networkidle")
                elements = page.locator("text=/예약하기|신청/").all()
                for elem in elements:
                    parent_text = elem.evaluate("el => el.parentElement ? el.parentElement.innerText : ''")
                    time_str = clean_time_format(parent_text)

                    available_slots.append({
                        "court": court_name,
                        "date": date_str,
                        "time": time_str,
                        "weekday_num": weekday_idx,
                        "url": url
                    })
            except Exception as e:
                print(f"[{court_name}] 크롤링 에러: {e}")

        browser.close()

    return available_slots
