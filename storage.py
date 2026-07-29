from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import (
    DEFAULT_COURTS,
    DEFAULT_WEEKDAY_HOURS,
    DEFAULT_WEEKEND_HOURS,
    SETTINGS_FILE,
    STATE_FILE,
    SONGDO_ENABLED_DEFAULT,
)

KST = timezone(timedelta(hours=9))

DEFAULT_SETTINGS: dict[str, Any] = {
    "courts": DEFAULT_COURTS,
    "weekday_hours": DEFAULT_WEEKDAY_HOURS,
    "weekend_hours": DEFAULT_WEEKEND_HOURS,
    "yeonsu_weekday_hours": DEFAULT_WEEKDAY_HOURS,
    "yeonsu_weekend_hours": DEFAULT_WEEKEND_HOURS,
    "songdo_weekday_hours": DEFAULT_WEEKDAY_HOURS,
    "songdo_weekend_hours": DEFAULT_WEEKEND_HOURS,
    "yeonsu_enabled": True,
    "songdo_enabled": SONGDO_ENABLED_DEFAULT,
}

DEFAULT_STATE: dict[str, Any] = {
    "current_keys": [],
    "stats": {
        "started_at": None,
        "last_check_at": None,
        "checks": 0,
        "alerts": 0,
        "slots_notified": 0,
        "errors": 0,
        "recoveries": 0,
    },
    "telegram_offset": 0,
    "reset_baseline": False,
}


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    backup = path.with_suffix(path.suffix + ".bak")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if path.exists():
        try:
            shutil.copy2(path, backup)
        except OSError:
            pass
    temp.replace(path)


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    for candidate in (path, path.with_suffix(path.suffix + ".bak")):
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
        except (OSError, json.JSONDecodeError):
            continue
    return deepcopy(default)


def load_settings() -> dict[str, Any]:
    data = _load_json(SETTINGS_FILE, DEFAULT_SETTINGS)
    courts = [x for x in data.get("courts", []) if x in {"A", "B", "C"}]
    data["courts"] = courts or ["A", "B", "C"]
    data["yeonsu_enabled"] = bool(data.get("yeonsu_enabled", True))
    data["songdo_enabled"] = bool(data.get("songdo_enabled", SONGDO_ENABLED_DEFAULT))
    if not data["yeonsu_enabled"] and not data["songdo_enabled"]:
        data["yeonsu_enabled"] = True

    # v6.7 이하의 공통 시간 설정을 사이트별 설정으로 자동 이전합니다.
    legacy_weekday = data.get("weekday_hours", DEFAULT_WEEKDAY_HOURS)
    legacy_weekend = data.get("weekend_hours", DEFAULT_WEEKEND_HOURS)
    for key, fallback in (
        ("yeonsu_weekday_hours", legacy_weekday),
        ("yeonsu_weekend_hours", legacy_weekend),
        ("songdo_weekday_hours", legacy_weekday),
        ("songdo_weekend_hours", legacy_weekend),
    ):
        value = data.get(key, fallback)
        if value is not None:
            value = sorted({int(x) for x in value if 0 <= int(x) <= 23})
        data[key] = value

    # 호환용 공통 키도 유지합니다.
    data["weekday_hours"] = data["yeonsu_weekday_hours"]
    data["weekend_hours"] = data["yeonsu_weekend_hours"]

    return data


def save_settings(settings: dict[str, Any]) -> None:
    _atomic_write(SETTINGS_FILE, settings)


def load_state() -> dict[str, Any]:
    state = _load_json(STATE_FILE, DEFAULT_STATE)
    state.setdefault("current_keys", [])
    state.setdefault("telegram_offset", 0)
    state.setdefault("reset_baseline", False)
    stats = state.setdefault("stats", {})
    for key, value in DEFAULT_STATE["stats"].items():
        stats.setdefault(key, value)
    if not stats["started_at"]:
        stats["started_at"] = datetime.now(KST).isoformat()
    return state


def save_state(state: dict[str, Any]) -> None:
    _atomic_write(STATE_FILE, state)
