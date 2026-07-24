import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime

COURTS = {
    "A코트": "https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq=1",
    "B코트": "https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq=2",
    "C코트": "https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq=3",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_time_format(time_raw):
    match = re.search(r'(\d{2}):00~(\d{2}):00', time_raw)
    if match:
        start_h = int(match.group(1))
        end_h = int(match.group(2))
        return f"{start_h}~{end_h}시"
    
    time_match = re.search(r'(\d{2}:\d{2}(?:~\d{2}:\d{2})?)', time_raw)
    return time_match.group(1) if time_match else time_raw

def get_available_slots():
    available_slots = []
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]

    for court_name, url in COURTS.items():
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'

            soup = BeautifulSoup(response.text, "html.parser")
            elements = soup.find_all(text=lambda t: t and "예약하기" in t)

            for elem in elements:
                parent = elem.parent
                row_text = parent.get_text(strip=True) if parent else ""

                time_str = clean_time_format(row_text)

                today = datetime.now()
                weekday_idx = today.weekday()
                date_str = f"{today.strftime('%Y-%m-%d')} ({weekdays[weekday_idx]})"

                available_slots.append({
                    "court": court_name,
                    "date": date_str,
                    "time": time_str,
                    "weekday_num": weekday_idx,
                    "url": url
                })

        except Exception as e:
            print(f"[{court_name}] 조회 실패: {e}")

    return available_slots