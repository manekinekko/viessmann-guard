"""Read native ViCare registry semantics, without importing or calling its API."""

import math
import re
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    EMAIL_DEFAULTS,
    LIST_SETTINGS,
    NUMERIC_RULES,
    PRESSURE_UNITS,
    SOURCE_ROLES,
    TEMPERATURE_UNITS,
)
from .engine import convert_flow
from .telemetry import private_entity

# Keys/suffixes from HA 2026.8/9 vicare sensor, binary_sensor and entity descriptors.
# Component suffixes are circuit/compressor IDs, not part of a translated label.
ROLES = {
    "flow": ("sensor", "volumetric_flow", "volumetric_flow"),
    "mode": ("sensor", "compressor_phase", r"compressor_phase-\d+"),
    "pump": ("binary_sensor", "circulation_pump", r"circulationpump_active-\d+"),
    "compressor": ("binary_sensor", "compressor", r"compressor_active-\d+"),
    "outside_temperature": ("sensor", "outside_temperature", "outside_temperature"),
    "return_temperature": ("sensor", "return_temperature", "return_temperature"),
    "supply_temperature": ("sensor", "supply_temperature", r"supply_temperature-\d+"),
    "pressure": ("sensor", "supply_pressure", "supply_pressure"),
}
EXTRA_REPORT_KEYS = frozenset(
    (
        "compressor_phase",
        "compressor_starts",
        "compressor_hours",
        "heating_rod_starts",
        "heating_rod_hours",
        "spf_total",
        "spf_dhw",
        "spf_heating",
    )
)
AUTOMATIC_PHASE_PROFILE = 1
LEGACY_PHASE_MODES = {
    "running_modes": ["heating", "cooling"],
    "idle_modes": ["off"],
    "excluded_modes": ["defrost"],
}


def functional_suffix(entity: er.RegistryEntry, device: dr.DeviceEntry) -> str | None:
    if entity.platform != "vicare" or entity.device_id != device.id:
        return None
    for domain, identifier in device.identifiers:
        if domain == "vicare" and entity.unique_id.startswith(f"{identifier}-"):
            return entity.unique_id[len(identifier) + 1 :]
    return None


def matches(entity: er.RegistryEntry, device: dr.DeviceEntry, role: str) -> bool:
    domain, translation, pattern = ROLES[role]
    suffix = functional_suffix(entity, device)
    return bool(
        entity.domain == domain
        and entity.translation_key in (None, translation)
        and suffix is not None
        and re.fullmatch(pattern, suffix)
    )


@dataclass
class Candidate:
    device_id: str
    name: str
    config: dict[str, Any]
    statuses: dict[str, str]


def discover(hass: HomeAssistant) -> list[Candidate]:
    registry = er.async_get(hass)
    result = []
    devices = {
        device.id: device
        for entry in hass.config_entries.async_entries("vicare")
        if not entry.disabled_by
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    }
    for device in devices.values():
        entries = [
            entity
            for entity in er.async_entries_for_device(
                registry, device.id, include_disabled_entities=True
            )
            if entity.platform == "vicare"
            and entity.config_entry_id
            and (entry := hass.config_entries.async_get_entry(entity.config_entry_id))
            and entry.domain == "vicare"
        ]
        if device.disabled_by or not any(
            matches(entity, device, role)
            for entity in entries
            for role in ("flow", "compressor", "mode")
        ):
            continue
        name = (device.name_by_user or device.name or device.model or "ViCare")[:60]
        name = re.sub(r"[\r\n]", " ", name).strip() or "ViCare"
        config: dict[str, Any] = {
            **EMAIL_DEFAULTS,
            **{key: default for key, (default, _, _) in NUMERIC_RULES.items()},
            **{key: [] for key in LIST_SETTINGS},
            **{f"{role}_entity": None for role in SOURCE_ROLES},
            "name": f"{name[:54]} Guard",
            "device_ids": [device.id],
            "min_flow_l_min": None,
            "report_entities": [],
            "report_exclude": [],
            "setup_mode": "automatic",
            "source_registry_ids": {},
            "running_modes": ["heating", "cooling"],
            "idle_modes": ["off", "ready"],
            "excluded_modes": ["defrost"],
            "automatic_phase_profile": AUTOMATIC_PHASE_PROFILE,
            "pump_on_values": ["on"],
            "pump_off_values": ["off"],
            "language": "en",
        }
        statuses = {}
        for role in SOURCE_ROLES:
            found = [e for e in entries if role in ROLES and matches(e, device, role)]
            if not found:
                statuses[role] = "not_exposed"
                continue
            if len(found) != 1:
                statuses[role] = "ambiguous"
                continue
            entity = found[0]
            if entity.disabled or private_entity(
                entity.entity_id, entity.name or entity.original_name or ""
            ):
                statuses[role] = "disabled_or_excluded"
                continue
            # Persist registry identity, not just a renameable entity_id.
            config[f"{role}_entity"] = entity.entity_id
            config["source_registry_ids"][f"{role}_entity"] = entity.id
            state = hass.states.get(entity.entity_id)
            statuses[role] = "detected"
            if state is None or state.state in ("unknown", "unavailable"):
                statuses[role] = "unavailable"
            elif role == "flow":
                try:
                    convert_flow(state.state, state.attributes.get("unit_of_measurement"))
                except ValueError:
                    statuses[role] = "invalid_unit_or_value"
            elif role == "mode" and state.state not in (
                *config["running_modes"],
                *config["idle_modes"],
                *config["excluded_modes"],
            ):
                statuses[role] = "unmapped_state"
            elif role in (
                "supply_temperature",
                "return_temperature",
                "outside_temperature",
                "pressure",
            ):
                units = PRESSURE_UNITS if role == "pressure" else TEMPERATURE_UNITS
                try:
                    value = float(state.state)
                    valid = math.isfinite(value) and (role != "pressure" or value >= 0)
                except ValueError:
                    valid = False
                if not valid or state.attributes.get("unit_of_measurement") not in units:
                    statuses[role] = "invalid_unit_or_value"
        # A single heating circuit can be paired with its own supply sensor.
        # Multiple circuits stay ambiguous; a DHW pump/select never substitutes.
        if config.get("pump_entity") and config.get("supply_temperature_entity"):
            pump = registry.async_get(config["pump_entity"])
            supply = registry.async_get(config["supply_temperature_entity"])
            assert pump is not None and supply is not None
            if pump.unique_id.rsplit("-", 1)[-1] != supply.unique_id.rsplit("-", 1)[-1]:
                config["supply_temperature_entity"] = None
                config["source_registry_ids"].pop("supply_temperature_entity", None)
                statuses["supply_temperature"] = "ambiguous"
        config["discovery_statuses"] = statuses
        result.append(Candidate(device.id, name, config, statuses))
    return sorted(result, key=lambda item: (item.name.casefold(), item.device_id))


def has_legacy_automatic_phase_profile(
    hass: HomeAssistant, data: dict[str, Any], options: dict[str, Any]
) -> bool:
    """Recognize untouched native discovery mappings, never expert replacements."""
    current = {**data, **options}
    if (
        data.get("setup_mode") != "automatic"
        or current.get("setup_mode") != "automatic"
        or data.get("automatic_phase_profile") is not None
        or current.get("automatic_phase_profile") is not None
        or not data.get("discovery_statuses")
        or current.get("discovery_statuses") != data["discovery_statuses"]
        or current.get("device_ids") != data.get("device_ids")
        or any(
            data.get(key) != values or current.get(key) != values
            for key, values in LEGACY_PHASE_MODES.items()
        )
    ):
        return False
    original_bindings = data.get("source_registry_ids", {})
    current_bindings = current.get("source_registry_ids", {})
    if (
        not isinstance(original_bindings, dict)
        or not original_bindings.get("mode_entity")
        or current_bindings != original_bindings
        or any(
            current.get(f"{role}_entity") != data.get(f"{role}_entity")
            and not original_bindings.get(f"{role}_entity")
            for role in SOURCE_ROLES
        )
    ):
        return False
    entity = er.async_get(hass).async_get(original_bindings["mode_entity"])
    device = dr.async_get(hass).async_get(entity.device_id) if entity and entity.device_id else None
    source_entry = (
        hass.config_entries.async_get_entry(entity.config_entry_id)
        if entity and entity.config_entry_id
        else None
    )
    return bool(
        entity
        and not entity.disabled
        and isinstance(device, dr.DeviceEntry)
        and not device.disabled_by
        and device.id in current.get("device_ids", [])
        and source_entry
        and source_entry.domain == "vicare"
        and not source_entry.disabled_by
        and matches(entity, device, "mode")
    )


def configured_devices(hass: HomeAssistant, *, excluding: str | None = None) -> set[str]:
    return {
        device_id
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != excluding
        for device_id in {**entry.data, **entry.options}.get("device_ids", [])
    }


def bind_sources(hass: HomeAssistant, config: dict[str, Any]) -> dict[str, Any]:
    """Remember explicit selections too; never rediscover over an expert override."""
    registry = er.async_get(hass)
    bound = dict(config)
    bound["source_registry_ids"] = {
        key: entity.id
        for role in SOURCE_ROLES
        if (key := f"{role}_entity")
        and config.get(key)
        and (entity := registry.async_get(config[key])) is not None
    }
    bound["report_registry_ids"] = {
        key: {
            entity_id: entity.id
            for entity_id in config.get(key, [])
            if (entity := registry.async_get(entity_id)) is not None
        }
        for key in ("report_entities", "report_exclude")
    }
    return bound


def resolve_sources(hass: HomeAssistant, config: dict[str, Any]) -> dict[str, Any]:
    result = dict(config)
    registry = er.async_get(hass)
    for key, registry_id in config.get("source_registry_ids", {}).items():
        if key not in {f"{role}_entity" for role in SOURCE_ROLES}:
            continue
        entity = registry.async_get(registry_id)
        result[key] = entity.entity_id if entity and not entity.disabled else None
    for key, bindings in config.get("report_registry_ids", {}).items():
        if key in ("report_entities", "report_exclude"):
            result[key] = [
                entity.entity_id
                for registry_id in bindings.values()
                if (entity := registry.async_get(registry_id)) is not None
            ]
    return result
