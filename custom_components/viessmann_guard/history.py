"""Bounded, local one-minute samples; never reconstruct report freshness from Recorder."""

from __future__ import annotations

import math
from copy import deepcopy
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .engine import Result, Settings, Snapshot, _label, convert_flow

INTERVAL = 60
RETENTION_SECONDS = 6 * 86400
MAX_SAMPLES = RETENTION_SECONDS // INTERVAL + 1
_FIELDS = ("at", "reported_at", "flow", "mode", "pump", "speed", "speed_configured", "quality")


def number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def observation(sample: Snapshot, rules: Settings, result: Result) -> dict[str, Any]:
    """Keep current facts plus an explicit exclusion, not a new detection rule."""
    roles = ("flow", "mode", "pump", "pump_speed", "fault")
    quality = "eligible"
    for role in roles:
        item = getattr(sample, role)
        if item is None and role in ("pump_speed", "fault"):
            continue
        if (
            item is None
            or item.status != "ok"
            or not number(item.observed_at)
            or not 0 <= sample.now - item.observed_at <= rules.stale_after_s
        ):
            quality = (
                f"{role}_{item.status}" if item and item.status != "ok" else f"{role}_unavailable"
            )
            if (
                item
                and item.status == "ok"
                and number(item.observed_at)
                and sample.now - item.observed_at > rules.stale_after_s
            ):
                quality = f"{role}_stale"
            break
    flow = None
    if sample.flow.status == "ok":
        try:
            flow = convert_flow(sample.flow.value, sample.flow.unit)
        except ValueError:
            quality = "flow_invalid"
    mode = _label(sample.mode.value)[:128] if sample.mode.value is not None else None
    pump = (
        _label(sample.pump.value)[:128] if sample.pump and sample.pump.value is not None else None
    )
    speed = None
    if sample.pump_speed is not None:
        try:
            speed = float(sample.pump_speed.value) if sample.pump_speed.value is not None else None
        except ValueError, TypeError:
            speed = None
        if (
            speed is None
            or not number(speed)
            or not 0 <= speed <= 100
            or sample.pump_speed.unit != "%"
        ):
            speed = None
            quality = "pump_speed_invalid"
    if quality == "eligible":
        if mode not in rules.running_modes:
            quality = (
                "mode_excluded"
                if mode in (*rules.idle_modes, *rules.excluded_modes)
                else "mode_unmapped"
            )
        elif pump not in rules.pump_on_values:
            quality = "pump_off"
        elif sample.fault and _label(sample.fault.value) not in rules.fault_clear_values:
            quality = "fault_unmapped"
        elif result.reason in {
            "startup_grace",
            "awaiting_post_restart_reports",
            "flow_out_of_order",
            "flow_changed_without_report",
            "clock_moved_backwards",
            "native_fault",
        }:
            quality = result.reason
    return {
        "at": sample.now,
        "reported_at": sample.flow.observed_at if number(sample.flow.observed_at) else None,
        "flow": flow if quality == "eligible" else None,
        "mode": mode,
        "pump": pump,
        "speed": speed,
        "speed_configured": sample.pump_speed is not None,
        "quality": quality,
    }


class FlowHistory:
    """One observation per UTC minute, with no catch-up after gaps or restart."""

    def __init__(self, restored: dict | None = None) -> None:
        self.rows: list[dict[str, Any]] = []
        self.started_at: float | None = None
        self.truncated = False
        if restored is not None:
            self._restore(restored)

    def _restore(self, value: dict) -> None:
        if not isinstance(value, dict) or value.get("version") != 1:
            raise ValueError("Unsupported flow history schema")
        packed = value.get("rows")
        if not isinstance(packed, list) or len(packed) > MAX_SAMPLES:
            raise ValueError("Invalid flow history size")
        rows = []
        for packed_row in packed:
            if not isinstance(packed_row, list) or len(packed_row) != len(_FIELDS):
                raise ValueError("Invalid flow history row")
            rows.append(dict(zip(_FIELDS, packed_row, strict=True)))
        last = -1
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "at",
                "reported_at",
                "flow",
                "mode",
                "pump",
                "speed",
                "speed_configured",
                "quality",
            }:
                raise ValueError("Invalid flow history row")
            if not number(row["at"]) or row["at"] < 0 or int(row["at"] // INTERVAL) <= last:
                raise ValueError("Invalid flow history chronology")
            last = int(row["at"] // INTERVAL)
            for key in ("reported_at", "flow", "speed"):
                if row[key] is not None and (not number(row[key]) or row[key] < 0):
                    raise ValueError("Invalid flow history measurement")
            if row["speed"] is not None and row["speed"] > 100:
                raise ValueError("Invalid flow history speed")
            if type(row["speed_configured"]) is not bool or any(
                row[key] is not None and (not isinstance(row[key], str) or len(row[key]) > 128)
                for key in ("mode", "pump", "quality")
            ):
                raise ValueError("Invalid flow history context")
            if row["quality"] == "eligible" and (
                row["flow"] is None
                or row["reported_at"] is None
                or row["reported_at"] > row["at"]
                or not row["mode"]
                or not row["pump"]
                or (row["speed_configured"] and row["speed"] is None)
            ):
                raise ValueError("Incomplete flow history evidence")
        start = value.get("started_at")
        if start is not None and (not number(start) or start < 0):
            raise ValueError("Invalid history start")
        self.rows = deepcopy(rows)
        self.started_at = start
        self.truncated = value.get("truncated") is True

    def add(self, sample: Snapshot, rules: Settings, result: Result) -> bool:
        now = sample.now
        if self.rows and now // INTERVAL <= self.rows[-1]["at"] // INTERVAL:
            return False
        if self.started_at is None:
            self.started_at = now
        self.rows = [row for row in self.rows if row["at"] >= now - RETENTION_SECONDS]
        self.rows.append(observation(sample, rules, result))
        if len(self.rows) > MAX_SAMPLES:
            self.truncated = True
            self.rows = self.rows[-MAX_SAMPLES:]
        return True

    def export(self) -> dict[str, Any]:
        return {
            "version": 1,
            "started_at": self.started_at,
            "rows": [[row[key] for key in _FIELDS] for row in self.rows],
            "truncated": self.truncated,
        }

    def summary(self, now: float, timezone: str, anchor: dict | None, tolerance: float) -> dict:
        zone = ZoneInfo(timezone)
        today = datetime.fromtimestamp(now, zone).date()
        days: list[dict[str, Any]] = []
        for offset in range(4, -1, -1):
            day = today - timedelta(days=offset)
            start = datetime.combine(day, time.min, zone).timestamp()
            next_day = datetime.combine(day + timedelta(days=1), time.min, zone).timestamp()
            end = min(now, next_day)
            day_rows = [
                row for row in self.rows if start <= row["at"] < next_day and row["at"] <= now
            ]
            matched = [
                row
                for row in day_rows
                if anchor is not None
                and row["quality"] == "eligible"
                and row["mode"] == anchor.get("mode")
                and row["pump"] == anchor.get("pump")
                and row["speed_configured"] == anchor.get("speed_configured")
                and (
                    (
                        row["speed"] is None
                        and anchor.get("pump_speed") is None
                        and not row["speed_configured"]
                    )
                    or (
                        row["speed"] is not None
                        and number(anchor.get("pump_speed"))
                        and abs(row["speed"] - anchor["pump_speed"]) <= tolerance
                    )
                )
            ]
            values = sorted(row["flow"] for row in matched)
            count = len(values)
            middle = (
                (
                    values[count // 2]
                    if count % 2
                    else values[count // 2 - 1] / 2 + values[count // 2] / 2
                )
                if count
                else None
            )
            slots = max(0, math.ceil(end / INTERVAL) - int(start // INTERVAL))
            if day == today and now % INTERVAL == 0:
                slots += 1
            # A day with one point is visible, but cannot establish a daily comparison.
            days.append(
                {
                    "date": day.isoformat(),
                    "partial": day == today,
                    "median": middle,
                    "minimum": min(values) if values else None,
                    "samples": len(values),
                    "observed_slots": len(day_rows),
                    "expected_slots": slots,
                    "coverage_pct": min(100.0, len(values) / slots * 100) if slots else 0,
                    "comparable": len(values) >= 2,
                    "reliable": len(values) >= 2
                    and len(day_rows) == slots
                    and all(
                        row["quality"] in {"eligible", "mode_excluded", "pump_off", "startup_grace"}
                        for row in day_rows
                    ),
                    "first_at": matched[0]["at"] if matched else None,
                    "last_at": matched[-1]["at"] if matched else None,
                    "day_seconds": datetime.combine(
                        day + timedelta(days=1), time.min, zone
                    ).timestamp()
                    - start,
                }
            )
        usable = [row for row in days if row["comparable"]]
        first, last = (usable[0], usable[-1]) if len(usable) >= 2 else (None, None)
        change = (
            (last["median"] / first["median"] - 1) * 100
            if first and last and first["median"] > 0
            else None
        )
        if change is not None and not math.isfinite(change):
            change = None
        consecutive = all(row["reliable"] for row in days) and all(
            days[index]["median"] > days[index + 1]["median"] for index in range(4)
        )
        return {
            "days": days,
            "timezone": timezone,
            "change_pct": change,
            "first_date": first["date"] if first else None,
            "last_date": last["date"] if last else None,
            "consecutive_declines": 4 if consecutive else None,
            "anchor": deepcopy(anchor),
            "speed_tolerance": tolerance,
            "started_at": self.started_at,
            "truncated": self.truncated,
            "source": "local_regular_samples",
            "interval_seconds": INTERVAL,
        }
