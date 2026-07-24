import re
import calendar
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

def clean_time_format(time_raw):
    match = re.search(r'(\d{1,2}):00~(\d{1,2}):00', time_raw)
    if match:
        return f"{int(match.group(1))}~{int(match.group(2))}시"
    match2 = re.search(r'(\d{1,2})시~(\d{1,2})시', time_raw)
    if match2:
        return f"{int(match2.group(1))}~{int(match2.group(2))}시"
    time_match = re.search(r'(\d{2}:\d{2}(?:~\d{2}:\d{2})?)', time_raw)
    return time_match.group(1) if time_match else time_raw

def get_available_slots():
    available_slots = []
    weekdays_ko = ["월", "화", "수", "목", "금", "토", "일"]
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)

    # 1. 오늘 날짜부터 다음 달 말일까지 전체 날짜 리스트 생성
    target_dates = []
    
    # 오늘이속한 달의 남은 날짜들
    curr_year = now.year
    curr_month = now.month
    _, last_day_curr = calendar.monthrange(curr_year, curr_month)
    
    for day in range(now.day, last_day_curr + 1):
        d = datetime(curr_year, curr_month, day, tzinfo=kst)
        w_idx = d.weekday()
        target_dates.append({
            "year": curr_year,
            "month": curr_month,
            "day": day,
            "date_str": f"{d.strftime('%Y-%m-%d')} ({weekdays_ko[w_idx]})",
            "weekday_num": w_idx,
            "is_next_month": False
        })

    # 다음 달 전체 날짜들
    next_month_date = (now.replace(day=28) + timedelta(days=4)) # 다음 달 안전한 이동
    next_year = next_month_date.year
    next_month = next_month_date.month
    _, last_day_next = calendar.monthrange(next_year, next_month)

    for day in range(1, last_day_next + 1):
        d = datetime(next_year, next_month, day, tzinfo=kst)
        w_idx = d.weekday()
        target_dates.append({
            "year": next_year,
            "month": next_month,
            "day": day,
            "date_str": f"{d.strftime('%Y-%m-%d')} ({weekdays_ko[w_idx]})",
            "weekday_num": w_idx,
            "is_next_month": True
        })

    print(f"🔍 [크롤링 시작] 오늘부터 다음달 말일까지 총 {len(target_dates)}일간 스캔...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # --- [1] 연수문화공원 테니스장 (A, B, C 코트) ---
        courts_ys = {
            "연수문화공원 A코트": "https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq=1",
            "연수문화공원 B코트": "https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq=2",
            "연수문화공원 C코트": "https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq=3",
        }

        for court_name, url in courts_ys.items():
            try:
                page.goto(url, timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(1000)

                # 이번 달 / 다음 달 구분 조회
                for is_next in [False, True]:
                    if is_next:
                        # 다음 달 달력 이동 버튼 클릭 시도
                        try:
                            next_btn = page.locator("text=/다음달|>|▶/").first
                            if next_btn.is_visible():
                                next_btn.click()
                                page.wait_for_timeout(1000)
                        except Exception:
                            pass

                    # 해당 달의 날짜 필터링
                    dates_in_month = [t for t in target_dates if t["is_next_month"] == is_next]

                    for t_info in dates_in_month:
                        try:
                            # 달력 날짜 클릭
                            day_btn = page.locator(f"xpath=//a[text()='{t_info['day']}'] | //td[text()='{t_info['day']}']").first
                            if day_btn.is_visible():
                                day_btn.click()
                                page.wait_for_timeout(400)
                        except Exception:
                            pass

                        # 예약가능 / 신청 버튼 추출
                        buttons = page.locator("text=/예약하기|신청|가능/").all()
                        for btn in buttons:
                            parent_text = btn.evaluate("el => el.closest('tr') ? el.closest('tr').innerText : (el.parentElement ? el.parentElement.innerText : '')")
                            if not parent_text:
                                continue

                            time_str = clean_time_format(parent_text)
                            available_slots.append({
                                "court": court_name,
                                "date": t_info["date_str"],
                                "time": time_str,
                                "weekday_num": t_info["weekday_num"],
                                "url": url
                            })
            except Exception as e:
                print(f"❌ [{court_name}] 에러: {e}")

        # --- [2] 송도 달빛공원 테니스장 ---
        try:
            url_moonlight = "https://songdotennis.co.kr/songdo-tennis?tab=reservations"
            page.goto(url_moonlight, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            for t_info in target_dates:
                buttons = page.locator("text=/예약가능|신청/").all()
                for btn in buttons:
                    parent_text = btn.evaluate("el => el.closest('tr') ? el.closest('tr').innerText : (el.parentElement ? el.parentElement.innerText : '')")
                    court_match = re.search(r'(\d+코트|[A-Za-z]+코트|제\d+코트)', parent_text)
                    court_label = f"달빛공원 {court_match.group(1)}" if court_match else "달빛공원 테니스장"
                    time_str = clean_time_format(parent_text)

                    available_slots.append({
                        "court": court_label,
                        "date": t_info["date_str"],
                        "time": time_str,
                        "weekday_num": t_info["weekday_num"],
                        "url": url_moonlight
                    })
        except Exception as e:
            print(f"❌ [달빛공원] 에러: {e}")

        # --- [3] 새아침공원 테니스장 ---
        try:
            url_newmorning = "https://res.insiseol.or.kr/rent/rentalSchedule?up_id=07"
            page.goto(url_newmorning, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            for t_info in target_dates:
                buttons = page.locator("text=/신청가능|예약/").all()
                for btn in buttons:
                    parent_text = btn.evaluate("el => el.closest('tr') ? el.closest('tr').innerText : (el.parentElement ? el.parentElement.innerText : '')")
                    court_match = re.search(r'(\d+코트|\d+번코트|제\d+코트)', parent_text)
                    court_label = f"새아침공원 {court_match.group(1)}" if court_match else "새아침공원 테니스장"
                    time_str = clean_time_format(parent_text)

                    available_slots.append({
                        "court": court_label,
                        "date": t_info["date_str"],
                        "time": time_str,
                        "weekday_num": t_info["weekday_num"],
                        "url": url_newmorning
                    })
        except Exception as e:
            print(f"❌ [새아침공원] 에러: {e}")

        browser.close()

    # 중복 제거
    unique_slots = []
    seen_keys = set()
    for s in available_slots:
        k = f"{s['court']}_{s['date']}_{s['time']}"
        if k not in seen_keys:
            seen_keys.add(k)
            unique_slots.append(s)

    print(f"📊 [크롤링 완료] 다음 달 말일까지 발견된 총 슬롯: {len(unique_slots)}개")
    return unique_slots
