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


@pytest.fixture
def vicare_device(hass):
    """Synthetic registry records using native ViCare descriptor/unique-ID conventions."""
    registry = er.async_get(hass)
    counter = 0

    def create(*, origin=None, name="Demo heat pump", missing=(), via_device=None):
        nonlocal counter
        counter += 1
        if origin is None:
            origin = MockConfigEntry(domain="vicare", title=f"Demo installation {counter}")
            origin.add_to_hass(hass)
        identifier = f"demo_gateway_{counter}_demo_device_{counter}"
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=origin.entry_id,
            identifiers={("vicare", identifier)},
            name=name,
            model="Demo heat pump",
            via_device_id=via_device,
        )
        sources = {}
        definitions = (
            ("flow", "sensor", "volumetric_flow", "volumetric_flow", "0.72", "m³/h", None),
            ("mode", "sensor", "compressor_phase-0", "compressor_phase", "heating", None, None),
            (
                "pump",
                "binary_sensor",
                "circulationpump_active-0",
                "circulation_pump",
                "on",
                None,
                "running",
            ),
            (
                "compressor",
                "binary_sensor",
                "compressor_active-0",
                "compressor",
                "on",
                None,
                "running",
            ),
            (
                "supply_temperature",
                "sensor",
                "supply_temperature-0",
                "supply_temperature",
                "40",
                "°C",
                "temperature",
            ),
            (
                "return_temperature",
                "sensor",
                "return_temperature",
                "return_temperature",
                "35",
                "°C",
                "temperature",
            ),
            ("pressure", "sensor", "supply_pressure", "supply_pressure", "1.5", "bar", "pressure"),
            (
                "outside_temperature",
                "sensor",
                "outside_temperature",
                "outside_temperature",
                "10",
                "°C",
                "temperature",
            ),
            (
                "dhw_pump",
                "binary_sensor",
                "dhw_circulationpump_active",
                "domestic_hot_water_circulation_pump",
                "on",
                None,
                "running",
            ),
            (
                "dhw_mode",
                "select",
                "dhw_operating_mode",
                "domestic_hot_water_operating_mode",
                "on",
                None,
                None,
            ),
            ("climate", "climate", "heating-0", "heating", "auto", None, None),
            ("fault", "binary_sensor", "device_error", "device_error", "on", None, "problem"),
        )
        for role, domain, suffix, translation, state, unit, device_class in definitions:
            if role in missing:
                continue
            entity = registry.async_get_or_create(
                domain,
                "vicare",
                f"{identifier}-{suffix}",
                config_entry=origin,
                device_id=device.id,
                translation_key=translation,
                suggested_object_id=f"demo_{counter}_{role}",
                original_name=f"Demo {role}",
                original_device_class=device_class,
            )
            sources[role] = entity
            attrs = {}
            if unit:
                attrs["unit_of_measurement"] = unit
            if device_class:
                attrs["device_class"] = device_class
            hass.states.async_set(entity.entity_id, state, attrs)
        return origin, device, sources

    return create
