import calendar
import re
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup

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

    # 오늘부터 다음 달 말일까지 전체 날짜 생성
    target_dates = []
    curr_year, curr_month = now.year, now.month
    _, last_day_curr = calendar.monthrange(curr_year, curr_month)

    for day in range(now.day, last_day_curr + 1):
        d = datetime(curr_year, curr_month, day, tzinfo=kst)
        w_idx = d.weekday()
        target_dates.append({
            "year": f"{curr_year:04d}",
            "month": f"{curr_month:02d}",
            "day": f"{day:02d}",
            "date_str": f"{d.strftime('%Y-%m-%d')} ({weekdays_ko[w_idx]})",
            "weekday_num": w_idx
        })

    next_month_date = (now.replace(day=28) + timedelta(days=4))
    next_year, next_month = next_month_date.year, next_month_date.month
    _, last_day_next = calendar.monthrange(next_year, next_month)

    for day in range(1, last_day_next + 1):
        d = datetime(next_year, next_month, day, tzinfo=kst)
        w_idx = d.weekday()
        target_dates.append({
            "year": f"{next_year:04d}",
            "month": f"{next_month:02d}",
            "day": f"{day:02d}",
            "date_str": f"{d.strftime('%Y-%m-%d')} ({weekdays_ko[w_idx]})",
            "weekday_num": w_idx
        })

    # 세션 헤더 강화 (일반 PC 브라우저 위장)
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.ysfsmc.or.kr/"
    }

    # --- [1] 연수문화공원 테니스장 ---
    courts_ys = {
        "연수문화공원 A코트": "1",
        "연수문화공원 B코트": "2",
        "연수문화공원 C코트": "3"
    }

    for court_name, seq in courts_ys.items():
        for t in target_dates:
            try:
                url = f"https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq={seq}&sYear={t['year']}&sMonth={t['month']}&sDay={t['day']}"
                res = session.get(url, headers=headers, timeout=8)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")
                    
                    # 모든 <tr> 및 <td> 요소에서 키워드 탐색
                    elements = soup.find_all(['tr', 'td', 'div', 'a'])
                    for elem in elements:
                        text = elem.get_text(" ", strip=True)
                        # '신청', '예약', '가능' 문구가 포함된 시간줄 파싱
                        if any(k in text for k in ["신청", "예약", "가능"]) and not any(k in text for k in ["불가", "마감", "완료"]):
                            if any(c in text for c in [":", "시", "~"]):
                                time_str = clean_time_format(text)
                                available_slots.append({
                                    "court": court_name,
                                    "date": t["date_str"],
                                    "time": time_str,
                                    "weekday_num": t["weekday_num"],
                                    "url": url
                                })
            except Exception as e:
                print(f"❌ [{court_name}] {t['date_str']} 에러: {e}")

    # --- [2] 송도 달빛공원 테니스장 ---
    try:
        url_m = "https://songdotennis.co.kr/songdo-tennis?tab=reservations"
        res_m = session.get(url_m, headers=headers, timeout=8)
        if res_m.status_code == 200:
            soup_m = BeautifulSoup(res_m.text, "html.parser")
            elements = soup_m.find_all(text=re.compile(r"예약가능|신청|가능"))
            for elem in elements:
                parent = elem.parent.parent if elem.parent else elem
                text = parent.get_text(" ", strip=True)
                if "불가" not in text and "마감" not in text:
                    court_match = re.search(r'(\d+코트|[A-Za-z]+코트|제\d+코트)', text)
                    court_label = f"달빛공원 {court_match.group(1)}" if court_match else "달빛공원 테니스장"
                    time_str = clean_time_format(text)

                    for t in target_dates:
                        available_slots.append({
                            "court": court_label,
                            "date": t["date_str"],
                            "time": time_str,
                            "weekday_num": t["weekday_num"],
                            "url": url_m
                        })
    except Exception as e:
        print(f"❌ [달빛공원] 에러: {e}")

    # --- [3] 새아침공원 테니스장 ---
    try:
        url_n = "https://res.insiseol.or.kr/rent/rentalSchedule?up_id=07"
        res_n = session.get(url_n, headers=headers, timeout=8)
        if res_n.status_code == 200:
            soup_n = BeautifulSoup(res_n.text, "html.parser")
            elements = soup_n.find_all(text=re.compile(r"신청가능|예약가능|가능"))
            for elem in elements:
                parent = elem.parent.parent if elem.parent else elem
                text = parent.get_text(" ", strip=True)
                if "불가" not in text and "마감" not in text:
                    court_match = re.search(r'(\d+코트|\d+번코트|제\d+코트)', text)
                    court_label = f"새아침공원 {court_match.group(1)}" if court_match else "새아침공원 테니스장"
                    time_str = clean_time_format(text)

                    for t in target_dates:
                        available_slots.append({
                            "court": court_label,
                            "date": t["date_str"],
                            "time": time_str,
                            "weekday_num": t["weekday_num"],
                            "url": url_n
                        })
    except Exception as e:
        print(f"❌ [새아침공원] 에러: {e}")

    # 중복 제거
    unique_slots = []
    seen_keys = set()
    for s in available_slots:
        k = f"{s['court']}_{s['date']}_{s['time']}"
        if k not in seen_keys:
            seen_keys.add(k)
            unique_slots.append(s)

    print(f"📊 [크롤링 완료] 조건 검사 전 총 슬롯 수: {len(unique_slots)}개")
    return unique_slots
