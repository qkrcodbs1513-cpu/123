"""연수문화공원 테니스장 A/B/C 빈자리 수집기."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT

BASE_URL = "https://www.ysfsmc.or.kr"
KST = timezone(timedelta(hours=9))
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

COURTS = {
    "A": {
        "name": "연수문화공원 A코트",
        "seq": "1",
        "page": f"{BASE_URL}/business/culture/park_tennis2.jsp",
    },
    "B": {
        "name": "연수문화공원 B코트",
        "seq": "2",
        "page": f"{BASE_URL}/business/culture/park_tennis2_2.jsp",
    },
    "C": {
        "name": "연수문화공원 C코트",
        "seq": "3",
        "page": f"{BASE_URL}/business/culture/park_tennis2_3.jsp",
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def _normalise_time(time_value: str) -> tuple[str, int]:
    start_hour = int(time_value.split(":", 1)[0])
    return f"{start_hour:02d}~{start_hour + 2:02d}시", start_hour


def _extract_slots(
    html_text: str,
    court_code: str,
    court_name: str,
    expected_seq: str,
    source_url: str,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html_text, "html.parser")
    slots: list[dict[str, Any]] = []
    today = datetime.now(KST).date()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        label = " ".join(anchor.get_text(" ", strip=True).split())

        if "tennisApplyRegForm.do" not in href or "예약하기" not in label:
            continue

        full_url = urljoin(source_url, href)
        query = parse_qs(urlparse(full_url).query)
        date_value = query.get("sch_ymd", [""])[0]
        time_value = query.get("time", [""])[0]
        seq_value = query.get("tennis_seq", [expected_seq])[0]

        if seq_value != expected_seq or not date_value or not time_value:
            continue

        try:
            slot_date = datetime.strptime(date_value, "%Y-%m-%d").date()
            time_label, start_hour = _normalise_time(time_value)
        except (ValueError, TypeError):
            continue

        if slot_date < today:
            continue

        weekday_num = slot_date.weekday()
        slots.append(
            {
                "site": "yeonsu",
                "court_code": court_code,
                "court": court_name,
                "date_raw": date_value,
                "date": f"{date_value} ({WEEKDAYS_KO[weekday_num]})",
                "time_raw": time_value,
                "time": time_label,
                "start_hour": start_hour,
                "weekday_num": weekday_num,
                "url": full_url,
            }
        )
    return slots


def slot_key(slot: dict[str, Any]) -> str:
    return f"{slot.get('site', 'yeonsu')}|{slot['court_code']}|{slot['date_raw']}|{slot['time_raw']}"


def matches_settings(slot: dict[str, Any], settings: dict[str, Any]) -> bool:
    site = slot.get("site", "yeonsu")
    if site == "yeonsu" and slot["court_code"] not in settings["courts"]:
        return False
    if site == "songdo":
        try:
            court_num = int(str(slot.get("court_code", "S00")).lstrip("S"))
        except ValueError:
            return False
        if court_num not in settings.get("songdo_courts", list(range(5, 15))):
            return False
        surface = "hard" if 5 <= court_num <= 8 else "artificial"
        if surface not in settings.get("songdo_surfaces", ["hard", "artificial"]):
            return False

    if site == "saeachim":
        try:
            court_num = int(str(slot.get("court_code", "N0")).lstrip("N"))
        except ValueError:
            return False
        if court_num not in settings.get("saeachim_courts", [1, 2, 3, 4]):
            return False

    weekday_num = int(slot["weekday_num"])
    start_hour = int(slot["start_hour"])
    prefix = site if site in {"songdo", "saeachim"} else "yeonsu"
    day_type = "weekend" if weekday_num >= 5 else "weekday"
    hours = settings.get(f"{prefix}_{day_type}_hours")
    # 이전 설정 파일과의 호환
    if f"{prefix}_{day_type}_hours" not in settings:
        hours = settings.get(f"{day_type}_hours")
    return hours is None or start_hour in hours


def get_available_slots_with_status(
    enabled_courts: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    session = requests.Session()
    session.headers.update(HEADERS)
    all_slots: list[dict[str, Any]] = []
    errors: list[str] = []
    selected = enabled_courts or list(COURTS)

    for court_code in selected:
        court = COURTS.get(court_code)
        if not court:
            continue
        try:
            response = session.get(
                court["page"],
                params={"_": int(datetime.now(KST).timestamp())},
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"

            slots = _extract_slots(
                response.text,
                court_code,
                court["name"],
                court["seq"],
                response.url,
            )
            all_slots.extend(slots)
            print(
                f"    ✅ {court['name']}: 실제 빈자리 {len(slots)}개 / HTTP {response.status_code}",
                flush=True,
            )
        except requests.RequestException as exc:
            error = f"{court['name']}: {type(exc).__name__} - {exc}"
            errors.append(error)
            print(f"    ❌ {error}", flush=True)

    unique = {slot_key(slot): slot for slot in all_slots}
    result = sorted(
        unique.values(),
        key=lambda slot: (slot["date_raw"], slot["start_hour"], slot["court_code"]),
    )
    return result, errors
