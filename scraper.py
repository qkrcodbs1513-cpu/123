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
    "연수문화공원 A코트": {
        "seq": "1",
        "page": f"{BASE_URL}/business/culture/park_tennis2.jsp",
    },
    "연수문화공원 B코트": {
        "seq": "2",
        "page": f"{BASE_URL}/business/culture/park_tennis2_2.jsp",
    },
    "연수문화공원 C코트": {
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
    court_name: str,
    expected_seq: str,
    source_url: str,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html_text, "html.parser")
    slots: list[dict[str, Any]] = []
    today = datetime.now(KST).date()

    # '예약하기'라고 표시된 실제 신청 링크만 빈자리로 판단한다.
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
            print(f"⚠️ 해석할 수 없는 예약 링크: {full_url}", flush=True)
            continue

        if slot_date < today:
            continue

        weekday_num = slot_date.weekday()
        slots.append(
            {
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
    return f"{slot['court']}|{slot['date_raw']}|{slot['time_raw']}"


def is_target_slot(slot: dict[str, Any]) -> bool:
    """월~금은 20~22시만, 토·일은 모든 시간."""
    return slot["weekday_num"] in (5, 6) or slot["start_hour"] == 20


def get_available_slots() -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update(HEADERS)
    all_slots: list[dict[str, Any]] = []
    errors: list[str] = []

    for court_name, court in COURTS.items():
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
                court_name,
                court["seq"],
                response.url,
            )
            all_slots.extend(slots)
            target_count = sum(1 for slot in slots if is_target_slot(slot))
            print(
                f"🔎 {court_name}: 실제 빈자리 {len(slots)}개 / "
                f"알림 조건 일치 {target_count}개 / HTTP {response.status_code}",
                flush=True,
            )
        except requests.RequestException as exc:
            error = f"{court_name}: {exc}"
            errors.append(error)
            print(f"❌ 조회 실패 - {error}", flush=True)

    if len(errors) == len(COURTS):
        raise RuntimeError("A/B/C 코트 조회가 모두 실패했습니다: " + " | ".join(errors))

    unique = {slot_key(slot): slot for slot in all_slots}
    result = sorted(
        unique.values(),
        key=lambda slot: (slot["date_raw"], slot["start_hour"], slot["court"]),
    )
    return result


if __name__ == "__main__":
    found = get_available_slots()
    targets = [slot for slot in found if is_target_slot(slot)]
    print(f"📊 실제 빈자리 전체: {len(found)}개")
    print(f"🎯 알림 조건 일치: {len(targets)}개")
    for item in targets:
        print(item)
