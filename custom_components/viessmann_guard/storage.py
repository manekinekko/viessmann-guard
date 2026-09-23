"""Versioned storage; unknown formats fail closed rather than discard incidents."""

import math
from typing import Any

from homeassistant.helpers.storage import Store

from .engine import validate_capture
from .history import FlowHistory


class GuardStore(Store[dict[str, Any]]):
    async def _async_migrate_func(self, old_major_version, old_minor_version, old_data):
        if old_major_version == 1 and old_minor_version == 1 and isinstance(old_data, dict):
            # HA's envelope stays v1; payload v1/v2 migration is explicit in Engine/Runtime.
            return old_data
        raise ValueError("Unsupported Viessmann Guard storage version; restore a compatible backup")


def validate_storage(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    if not isinstance(data, dict) or data.get("schema") not in (1, 2):
        raise ValueError("Invalid Viessmann Guard storage schema")
    for key in ("engine", "delivery"):
        if not isinstance(data.get(key), dict):
            raise ValueError(f"Invalid Viessmann Guard storage section: {key}")
        if data[key].get("version") not in ((1, 2) if key == "engine" else (1,)):
            raise ValueError(f"Unsupported Viessmann Guard {key} schema")
    if "test_delivery" in data and not isinstance(data["test_delivery"], dict):
        raise ValueError("Invalid Viessmann Guard test notification storage")
    if "test_delivery" in data and data["test_delivery"].get("version") != 1:
        raise ValueError("Unsupported Viessmann Guard test notification schema")
    engine = data["engine"]
    for stored in (engine.get("incident"), engine.get("last_incident")):
        if isinstance(stored, dict):
            validate_capture(stored.get("opening"))
            validate_capture(stored.get("escalation"))
    incident = engine.get("incident")
    if incident is not None and (
        not isinstance(incident, dict)
        or not isinstance(incident.get("id"), str)
        or len(incident["id"]) != 32
        or any(char not in "0123456789abcdef" for char in incident["id"])
        or incident.get("severity") not in ("watch", "urgent")
        or incident.get("reason")
        not in ("absolute_low_flow", "relative_flow_decline", "native_fault")
        or not isinstance(incident.get("opened_at"), (int, float))
        or not math.isfinite(incident["opened_at"])
        or incident["opened_at"] < 0
    ):
        raise ValueError("Invalid Viessmann Guard persisted incident")
    baseline = engine.get("baseline")
    if baseline is not None and (
        not isinstance(baseline, dict)
        or not isinstance(baseline.get("value"), (int, float))
        or not math.isfinite(baseline["value"])
        or baseline["value"] <= 0
        or not isinstance(baseline.get("mode"), str)
        or not isinstance(baseline.get("confirmed_at"), (int, float))
        or not math.isfinite(baseline["confirmed_at"])
        or baseline["confirmed_at"] < 0
    ):
        raise ValueError("Invalid Viessmann Guard persisted reference")
    if not isinstance(data.get("mail_epoch", 0), int) or data.get("mail_epoch", 0) < 0:
        raise ValueError("Invalid Viessmann Guard notification epoch")
    for key in ("fingerprint", "mail_key", "mail_kind", "mail_incident", "mail_severity", "notice"):
        if data.get(key) is not None and (not isinstance(data[key], str) or len(data[key]) > 500):
            raise ValueError("Invalid Viessmann Guard notification metadata")
    trends = data.get("trends", [])
    if not isinstance(trends, list) or any(
        not isinstance(row, dict)
        or not isinstance(row.get("flow"), (float, int))
        or not math.isfinite(row["flow"])
        or row["flow"] < 0
        or not isinstance(row.get("observed_at"), str)
        or len(row["observed_at"]) > 50
        for row in trends
    ):
        raise ValueError("Invalid Viessmann Guard trend history")
    if data.get("flow_history") is not None:
        FlowHistory(data["flow_history"])
    return data
