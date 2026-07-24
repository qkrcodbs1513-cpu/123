import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

# 1. 연수문화공원 코트 URL
COURTS_YS = {
    "연수문화공원 A코트": "https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq=1",
    "연수문화공원 B코트": "https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq=2",
    "연수문화공원 C코트": "https://www.ysfsmc.or.kr/business/culture/park_tennis2.jsp?tennis_seq=3",
}

# 2. 송도 달빛공원 테니스장 URL
URL_MOONLIGHT = "https://songdotennis.co.kr/songdo-tennis?tab=reservations"

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

    # 한국 표준시(KST, UTC+9) 고정
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst)
    weekday_idx = today.weekday()
    date_str = f"{today.strftime('%Y-%m-%d')} ({weekdays[weekday_idx]})"

    # --- [1] 연수문화공원 스크래핑 ---
    for court_name, url in COURTS_YS.items():
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

                available_slots.append({
                    "court": court_name,
                    "date": date_str,
                    "time": time_str,
                    "weekday_num": weekday_idx,
                    "url": url
                })
        except Exception as e:
            print(f"[{court_name}] 조회 실패: {e}")

    # --- [2] 송도 달빛공원 테니스장 스크래핑 ---
    try:
        res = requests.get(URL_MOONLIGHT, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            # 코트 단위 구역 또는 행 탐색
            elements = soup.find_all(text=lambda t: t and ("예약가능" in t or "신청" in t or "예약하기" in t))
            
            for elem in elements:
                parent = elem.parent
                # 부모 요소를 넓게 탐색하여 코트 번호 식별
                container_text = ""
                curr = parent
                for _ in range(4):
                    if curr:
                        container_text += " " + curr.get_text(strip=True)
                        curr = curr.parent

                time_str = clean_time_format(container_text)

                # "1코트", "A코트", "제1코트" 등 상세 코트 명칭 추출
                court_match = re.search(r'(\d+코트|[A-Za-z]+코트|제\d+코트)', container_text)
                if court_match:
                    court_label = f"달빛공원 {court_match.group(1)}"
                else:
                    court_label = "달빛공원 테니스장"

                available_slots.append({
                    "court": court_label,
                    "date": date_str,
                    "time": time_str,
                    "weekday_num": weekday_idx,
                    "url": URL_MOONLIGHT
                })
    except Exception as e:
        print(f"[달빛공원 테니스장] 조회 실패: {e}")

    return available_slots
