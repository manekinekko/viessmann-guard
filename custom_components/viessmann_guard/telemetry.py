"""Bounded, device-scoped telemetry without raw attribute or diagnostic dumps."""

import math
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    MAX_REPORT_ENTITIES,
    PRESSURE_UNITS,
    PRIVATE_NAME_PARTS,
    SAFE_DEVICE_CLASSES,
    SOURCE_ROLES,
    TEMPERATURE_UNITS,
)
from .engine import Measurement, convert_flow


def private_entity(entity_id: str, name: str) -> bool:
    text = f"{entity_id} {name}".lower()
    return any(part in text for part in PRIVATE_NAME_PARTS)


def scoped_entity(hass: HomeAssistant, entity_id: str, devices: list[str]) -> bool:
    entity = er.async_get(hass).async_get(entity_id)
    return bool(
        entity
        and not entity.disabled
        and entity.device_id in devices
        and entity.platform != DOMAIN
        and entity.domain in ("sensor", "binary_sensor", "select", "climate", "number")
        and not private_entity(entity_id, entity.name or entity.original_name or "")
    )


def validate_report_entities(hass: HomeAssistant, config: dict[str, Any]) -> dict[str, str]:
    errors = {}
    for key in ("report_entities", "report_exclude"):
        if any(
            not scoped_entity(hass, entity_id, config["device_ids"])
            for entity_id in config.get(key, [])
        ):
            errors[key] = "invalid_report_entity"
    return errors


def inventory(hass: HomeAssistant, config: dict[str, Any]) -> tuple[list[str], bool]:
    from homeassistant.helpers import device_registry as dr

    from .discovery import EXTRA_REPORT_KEYS, functional_suffix

    mapped = {config[f"{r}_entity"] for r in SOURCE_ROLES if config.get(f"{r}_entity")}
    selected = mapped | set(config.get("report_entities", []))
    excluded = set(config.get("report_exclude", []))
    for entity in er.async_get(hass).entities.values():
        if not scoped_entity(hass, entity.entity_id, config["device_ids"]):
            continue
        state = hass.states.get(entity.entity_id)
        if state is None:
            device_class = entity.device_class or entity.original_device_class
        else:
            device_class = state.attributes.get("device_class")
        if (
            (entity.domain == "sensor" and device_class in SAFE_DEVICE_CLASSES)
            or (
                entity.domain == "binary_sensor"
                and device_class in ("running", "problem", "heat", "power")
            )
            or entity.domain in ("climate", "number")
        ):
            selected.add(entity.entity_id)
        elif (
            entity.platform == "vicare"
            and entity.domain == "sensor"
            and entity.translation_key in EXTRA_REPORT_KEYS
            and entity.device_id
            and (device := dr.async_get(hass).async_get(entity.device_id))
            and isinstance(device, dr.DeviceEntry)
            and (suffix := functional_suffix(entity, device))
            and (
                suffix == entity.translation_key
                or suffix.rsplit("-", 1)[0] == entity.translation_key
            )
        ):
            selected.add(entity.entity_id)
    # Always keep explicit diagnostic mappings visible, even if excluded from auto-inventory.
    selected = (selected - excluded) | mapped
    safe = sorted(e for e in selected if scoped_entity(hass, e, config["device_ids"]))
    return safe[:MAX_REPORT_ENTITIES], len(safe) > MAX_REPORT_ENTITIES


def measurement(
    state: State | None, now: float, stale_after: float, started_at: float
) -> Measurement:
    if state is None:
        return Measurement(None, None, status="missing")
    timestamp = state.last_reported.timestamp()
    unit = state.attributes.get("unit_of_measurement")
    unit = str(unit)[:30] if unit is not None else None
    if state.state in ("unknown", "unavailable"):
        return Measurement(None, timestamp, unit, state.state)
    if timestamp <= started_at:
        return Measurement(None, timestamp, unit, "awaiting_fresh_report")
    if timestamp > now + 1 or now - timestamp > stale_after:
        return Measurement(None, timestamp, unit, "stale")
    try:
        numeric = float(state.state)
        if not math.isfinite(numeric):
            return Measurement(None, timestamp, unit, "invalid")
        value: float | str = numeric
    except ValueError:
        value = state.state[:128]
    return Measurement(value, timestamp, unit)


def temperature_celsius(value: Measurement) -> float | None:
    if value.status != "ok" or not isinstance(value.value, (int, float)):
        return None
    if value.unit == "°C":
        return float(value.value)
    if value.unit == "°F":
        return (value.value - 32) * 5 / 9
    if value.unit == "K":
        return value.value - 273.15
    return None


def iso(timestamp: float | None) -> str | None:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(timestamp, UTC).isoformat() if timestamp is not None else None


def report_telemetry(
    hass: HomeAssistant, config: dict[str, Any], now: float, started_at: float
) -> tuple[list[dict[str, Any]], bool]:
    ids, truncated = inventory(hass, config)
    result: list[dict[str, Any]] = []
    for entity_id in ids:
        state = hass.states.get(entity_id)
        item = measurement(state, now, config["stale_after_s"], started_at)
        name = state.name[:100] if state else entity_id
        if private_entity(entity_id, name):
            continue
        status = item.status
        value = item.value
        if (
            state
            and state.domain in ("sensor", "number")
            and state.attributes.get("device_class") in SAFE_DEVICE_CLASSES
            and isinstance(value, str)
        ):
            status, value = "invalid", None
        if entity_id == config.get("flow_entity") and item.status == "ok":
            try:
                convert_flow(item.value, item.unit)
            except TypeError, ValueError:
                status, value = "invalid_or_unsupported_unit", None
        if (
            state
            and state.attributes.get("device_class") == "pressure"
            and isinstance(value, (float, int))
            and value < 0
        ):
            status, value = "invalid", None
        if (
            state
            and item.status == "ok"
            and (
                state.attributes.get("device_class") == "pressure"
                and item.unit not in PRESSURE_UNITS
                or state.attributes.get("device_class") == "temperature"
                and item.unit not in TEMPERATURE_UNITS
            )
        ):
            status, value = "invalid_or_unsupported_unit", None
        if (
            entity_id == config.get("pump_speed_entity")
            and item.status == "ok"
            and (not isinstance(value, (float, int)) or not 0 <= value <= 100 or item.unit != "%")
        ):
            status, value = "invalid_or_unsupported_unit", None
        result.append(
            {
                "entity_id": entity_id,
                "name": name,
                "value": value,
                "unit": item.unit,
                "status": status,
                "observed_at": iso(item.observed_at),
                "freshness_seconds": max(0, now - item.observed_at) if item.observed_at else None,
            }
        )
        if state and state.domain == "climate":
            for key in (
                "current_temperature",
                "temperature",
                "target_temp_low",
                "target_temp_high",
            ):
                raw = state.attributes.get(key)
                valid = (
                    isinstance(raw, (int, float))
                    and not isinstance(raw, bool)
                    and math.isfinite(raw)
                )
                result.append(
                    {
                        **result[-1],
                        "name": f"{name}: {key}",
                        "value": raw if valid and item.status == "ok" else None,
                        "unit": str(hass.config.units.temperature_unit),
                        "status": item.status if valid else "missing",
                    }
                )
    return result, truncated
