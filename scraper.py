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

    # 오늘부터 다음 달 말일까지 전체 날짜 목록 생성
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

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.ysfsmc.or.kr/"
    }

    # 연수문화공원 A, B, C 코트
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
                    # 예약 가능 상태 검색
                    rows = soup.find_all("tr")
                    for r in rows:
                        text = r.get_text(" ", strip=True)
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

    # 중복 제거
    unique_slots = []
    seen_keys = set()
    for s in available_slots:
        k = f"{s['court']}_{s['date']}_{s['time']}"
        if k not in seen_keys:
            seen_keys.add(k)
            unique_slots.append(s)

    print(f"📊 [연수문화공원 스캔 완료] 총 슬롯 수: {len(unique_slots)}개")
    return unique_slots
