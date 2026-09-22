"""Run custom integration tests inside the real Home Assistant harness."""

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.viessmann_guard.const import NUMERIC_RULES

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def source_config(hass):
    origin = MockConfigEntry(domain="vicare", title="Synthetic source")
    origin.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=origin.entry_id,
        identifiers={("vicare", "synthetic-only")},
        name="Synthetic PAC",
    )
    registry = er.async_get(hass)
    config = {
        "name": "Demo Guard",
        "device_ids": [device.id],
        "min_flow_l_min": 8.0,
        **{key: default for key, (default, _, _) in NUMERIC_RULES.items()},
        "absolute_persistence_s": 30,
        "recovery_s": 30,
        "startup_grace_s": 0,
        "running_modes": ["heating"],
        "idle_modes": ["idle"],
        "excluded_modes": ["defrost"],
        "pump_on_values": ["on"],
        "pump_off_values": ["off"],
        "fault_values": [],
        "fault_clear_values": ["off"],
        "emails_enabled": False,
        "recipients": [],
        "watch_email": False,
        "reminder_hours": 24,
        "language": "en",
        "report_entities": [],
        "report_exclude": [],
    }
    for role, domain, value, attributes in (
        (
            "flow",
            "sensor",
            "12",
            {"unit_of_measurement": "L/min", "device_class": "volume_flow_rate"},
        ),
        ("mode", "sensor", "heating", {}),
        ("pump", "binary_sensor", "on", {"device_class": "running"}),
        (
            "supply_temperature",
            "sensor",
            "40",
            {"unit_of_measurement": "°C", "device_class": "temperature"},
        ),
        (
            "return_temperature",
            "sensor",
            "95",
            {"unit_of_measurement": "°F", "device_class": "temperature"},
        ),
    ):
        entity = registry.async_get_or_create(
            domain,
            "vicare",
            f"synthetic_{role}",
            config_entry=origin,
            device_id=device.id,
            suggested_object_id=f"synthetic_{role}",
        )
        config[f"{role}_entity"] = entity.entity_id
        hass.states.async_set(entity.entity_id, value, attributes)
    return config
