"""Validate explicit source mappings and native SMTP recipient entities."""

import math
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    MAX_RECIPIENTS,
    PRESSURE_UNITS,
    PRIVATE_NAME_PARTS,
    REQUIRED_ROLES,
    SOURCE_ROLES,
    TEMPERATURE_UNITS,
)
from .engine import convert_flow


def smtp_identity(hass: HomeAssistant, entity_id: str) -> str:
    """Use registry ownership and SMTP subentry identity, never read credentials."""
    entity = er.async_get(hass).async_get(entity_id)
    if (
        entity is None
        or entity.domain != "notify"
        or entity.platform != "smtp"
        or entity.disabled
        or not entity.config_entry_id
    ):
        raise ValueError("invalid_smtp_recipient")
    entry = hass.config_entries.async_get_entry(entity.config_entry_id)
    if entry is None or entry.domain != "smtp":
        raise ValueError("invalid_smtp_recipient")
    for subentry in entry.subentries.values():
        address = subentry.unique_id
        if (
            subentry.subentry_type == "recipient"
            and address
            and entity.unique_id == f"{entry.entry_id}_{address}"
        ):
            # Preserve the case-sensitive local part. SMTP owns address validation.
            local, sep, domain = address.rpartition("@")
            if not sep or not local or not domain or "\r" in address or "\n" in address:
                raise ValueError("invalid_smtp_recipient")
            return f"{local}@{domain.lower()}"
    raise ValueError("invalid_smtp_recipient")


def validate_recipients(hass: HomeAssistant, recipients: list[str]) -> list[str]:
    if len(recipients) > MAX_RECIPIENTS:
        raise ValueError("too_many_recipients")
    seen: set[str] = set()
    result = []
    for entity_id in recipients:
        identity = smtp_identity(hass, entity_id)
        if identity in seen:
            raise ValueError("duplicate_recipient")
        seen.add(identity)
        result.append(entity_id)
    return result


def validate_sources(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    devices = data.get("device_ids", [])
    if not devices or any(dr.async_get(hass).async_get(d) is None for d in devices):
        errors["device_ids"] = "invalid_device"
    registry = er.async_get(hass)
    for role in SOURCE_ROLES:
        key = f"{role}_entity"
        entity_id = data.get(key)
        if not entity_id:
            if role in REQUIRED_ROLES:
                errors[key] = "required_source"
            continue
        entity = registry.async_get(entity_id)
        if (
            entity is None
            or entity.device_id not in devices
            or entity.domain not in ("sensor", "binary_sensor", "select", "climate", "number")
            or entity.platform == "viessmann_guard"
            or entity.disabled
        ):
            errors[key] = "invalid_source"
            continue
        state = hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            errors[key] = "source_unavailable"
            continue
        if any(part in f"{entity_id} {state.name}".lower() for part in PRIVATE_NAME_PARTS):
            errors[key] = "invalid_source"
            continue
        if role == "flow":
            try:
                convert_flow(state.state, state.attributes.get("unit_of_measurement"))
            except TypeError, ValueError:
                errors[key] = "invalid_flow_unit"
        if role == "pump_speed":
            try:
                value = float(state.state)
                valid = math.isfinite(value) and 0 <= value <= 100
            except ValueError:
                valid = False
            if not valid or state.attributes.get("unit_of_measurement") != "%":
                errors[key] = "invalid_speed_unit"
        if role.endswith("_temperature") or role == "pressure":
            unit = state.attributes.get("unit_of_measurement")
            try:
                value = float(state.state)
                valid = math.isfinite(value) and not (
                    (role == "pressure" or unit == "K") and value < 0
                )
            except ValueError:
                valid = False
            supported = PRESSURE_UNITS if role == "pressure" else TEMPERATURE_UNITS
            if not valid or unit not in supported:
                errors[key] = "invalid_measurement_unit"
    return errors


def validate_rules(data: dict[str, Any]) -> dict[str, str]:
    errors = {}
    if not data.get("running_modes"):
        errors["running_modes"] = "required_modes"
    groups = [set(data.get(key, [])) for key in ("running_modes", "idle_modes", "excluded_modes")]
    if any(groups[i] & groups[j] for i in range(3) for j in range(i)):
        errors["running_modes"] = "overlapping_values"
    for left, right in (
        ("pump_on_values", "pump_off_values"),
        ("fault_values", "fault_clear_values"),
    ):
        if set(data.get(left, [])) & set(data.get(right, [])):
            errors[left] = "overlapping_values"
    if data.get("fault_entity") and (
        not data.get("fault_values") or not data.get("fault_clear_values")
    ):
        errors["fault_values"] = "required_fault_mapping"
    if float(data["hysteresis_pct"]) >= float(data["relative_drop_pct"]):
        errors["hysteresis_pct"] = "invalid_hysteresis"
    return errors
