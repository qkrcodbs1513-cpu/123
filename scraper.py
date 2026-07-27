import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, parse_qs

WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
KST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 연수구시설안전관리공단 테니스장 (tennis_seq 확인 완료)
COURTS = {
    "연수문화공원 A코트": 1,
    "연수문화공원 B코트": 2,
    "연수문화공원 C코트": 3,
    "연수체육공원 A코트": 4,
    "연수체육공원 B코트": 5,
}

MONTH_URL = "https://www.ysfsmc.or.kr/tennis/tennisScheduleMonth.do"


def get_target_months():
    """오늘이 속한 달 + 다음 달 (YYYY-MM) 리스트"""
    now = datetime.now(KST)
    months = [f"{now.year:04d}-{now.month:02d}"]
    nxt = (now.replace(day=28) + timedelta(days=4))
    months.append(f"{nxt.year:04d}-{nxt.month:02d}")
    return months


def get_available_slots():
    """
    각 코트 페이지에서 '예약하기' 링크(tennisApplyRegForm.do)를 직접 찾아
    href 안의 sch_ymd, time 파라미터를 그대로 읽어온다.
    -> 텍스트 매칭이 아니라 실제 링크 파라미터를 쓰므로 100% 정확하다.
    """
    available_slots = []
    now = datetime.now(KST)
    today_str = now.strftime("%Y-%m-%d")
    months = get_target_months()
    session = requests.Session()

    for court_name, seq in COURTS.items():
        for ym in months:
            try:
                url = f"{MONTH_URL}?tennis_seq={seq}&sch_ym={ym}"
                res = session.get(url, headers=HEADERS, timeout=10)
                res.raise_for_status()
                res.encoding = res.apparent_encoding or "utf-8"
                soup = BeautifulSoup(res.text, "html.parser")

                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "tennisApplyRegForm.do" not in href:
                        continue

                    full_url = urljoin("https://www.ysfsmc.or.kr/tennis/", href)
                    qs = parse_qs(urlparse(full_url).query)
                    date_str = qs.get("sch_ymd", [None])[0]
                    time_str = qs.get("time", [None])[0]
                    if not date_str or not time_str:
                        continue

                    # 오늘보다 이전 날짜는 제외
                    if date_str < today_str:
                        continue

                    d = datetime.strptime(date_str, "%Y-%m-%d")
                    w_idx = d.weekday()  # 0=월 ... 6=일

                    start_h = int(time_str.split(":")[0])
                    end_h = (start_h + 2) % 24
                    time_label = f"{start_h}~{end_h}시"

                    available_slots.append({
                        "court": court_name,
                        "date": f"{date_str} ({WEEKDAYS_KO[w_idx]})",
                        "time": time_label,
                        "weekday_num": w_idx,
                        "url": full_url,
                    })
            except Exception as e:
                print(f"❌ [{court_name} / {ym}] 조회 에러: {e}")

    # 중복 제거
    unique = []
    seen_keys = set()
    for s in available_slots:
        k = f"{s['court']}_{s['date']}_{s['time']}"
        if k not in seen_keys:
            seen_keys.add(k)
            unique.append(s)

    print(f"📊 [크롤링 완료] 총 예약 가능 슬롯: {len(unique)}개")
    return unique


if __name__ == "__main__":
    slots = get_available_slots()
    for s in slots:
        print(s)

print(unique)

res = session.get(url, headers=HEADERS, timeout=10)

print("=" * 50)
print(court_name, ym)
print("예약하기" in res.text)
print("tennisApplyRegForm.do" in res.text)
