"""Native registry discovery and the real, zero-typing HTTP onboarding."""

import ast
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import homeassistant
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_integration import reports, setup_guard

from custom_components.viessmann_guard.const import (
    DOMAIN,
    EMAIL_DEFAULTS,
    LIST_SETTINGS,
    NUMERIC_RULES,
    SOURCE_ROLES,
)
from custom_components.viessmann_guard.discovery import ROLES, bind_sources, discover
from custom_components.viessmann_guard.runtime import fingerprint
from custom_components.viessmann_guard.telemetry import inventory


def test_native_descriptor_contract():
    """Check the actual installed version, rather than a second copy of our guesses."""
    root = Path(homeassistant.__file__).parent / "components" / "vicare"
    descriptors = {}
    for module in ("sensor", "binary_sensor"):
        tree = ast.parse((root / f"{module}.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fields = {
                    keyword.arg: keyword.value.value
                    for keyword in node.keywords
                    if isinstance(keyword.value, ast.Constant)
                }
                if "key" in fields and "translation_key" in fields:
                    descriptors[module, fields["key"]] = fields["translation_key"]
    for domain, translation, pattern in ROLES.values():
        key = pattern.split("-")[0]
        assert descriptors[domain, key] == translation
    entity_code = (root / "entity.py").read_text()
    assert 'self._attr_unique_id = f"{identifier}-{unique_id_suffix}"' in entity_code
    assert 'f"-{component.id}"' in entity_code


@pytest.mark.parametrize("language", ["en", "fr"])
def test_renamed_localized_names_do_not_define_roles(hass, vicare_device, language):
    hass.config.language = language
    _, device, sources = vicare_device(name="PAC renommée" if language == "fr" else "Renamed pump")
    registry = er.async_get(hass)
    flow = registry.async_update_entity(
        sources["flow"].entity_id, new_entity_id="sensor.arbitrary_user_name", name="Mon débit"
    )
    (candidate,) = discover(hass)
    assert candidate.device_id == device.id
    assert candidate.config["flow_entity"] == flow.entity_id
    assert candidate.config["mode_entity"] == sources["mode"].entity_id
    assert candidate.config["pump_entity"] == sources["pump"].entity_id
    assert candidate.config["min_flow_l_min"] is None
    assert candidate.config["fault_entity"] is None  # A generic error is not a low-flow fault.
    assert candidate.config["emails_enabled"] is False
    assert candidate.config["recipients"] == []
    assert candidate.config["language"] == "en"


@pytest.mark.parametrize("link", [False, True])
def test_gateway_is_not_a_second_heat_pump_and_distinct_pumps_stay_separate(
    hass, vicare_device, link
):
    origin, device, sources = vicare_device()
    gateway = dr.async_get(hass).async_get_or_create(
        config_entry_id=origin.entry_id,
        identifiers={("vicare", "demo_gateway_only")},
        name="Demo gateway",
        via_device_id=device.id if link else None,
    )
    entity = er.async_get(hass).async_get_or_create(
        "sensor",
        "vicare",
        "demo_gateway_only-wifi_signal_strength",
        config_entry=origin,
        device_id=gateway.id,
        translation_key="wifi_signal_strength",
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )
    (candidate,) = discover(hass)
    assert candidate.config["device_ids"] == [device.id]
    assert entity.entity_id not in inventory(hass, candidate.config)[0]
    _, second, other_sources = vicare_device(origin=origin, name=device.name, via_device=gateway.id)
    assert {item.device_id for item in discover(hass)} == {device.id, second.id}
    ids = inventory(hass, candidate.config)[0]
    assert sources["flow"].entity_id in ids
    assert not set(ids) & {e.entity_id for e in other_sources.values()}


@pytest.mark.parametrize("role", ["flow", "mode", "pump"])
def test_missing_required_context_never_substitutes_dhw_or_climate(hass, vicare_device, role):
    vicare_device(missing=[role])
    (candidate,) = discover(hass)
    assert candidate.config[f"{role}_entity"] is None
    assert candidate.statuses[role] == "not_exposed"


def test_no_candidates_and_disabled_device(hass, vicare_device):
    assert discover(hass) == []
    _, device, _ = vicare_device()
    dr.async_get(hass).async_update_device(device.id, disabled_by=dr.DeviceEntryDisabler.USER)
    assert discover(hass) == []


def test_unknown_phase_and_invalid_optional_units_are_visible_in_summary(hass, vicare_device):
    _, _, sources = vicare_device()
    hass.states.async_set(sources["mode"].entity_id, "auto")
    hass.states.async_set(sources["pressure"].entity_id, "1.5", {"unit_of_measurement": "unknown"})
    (candidate,) = discover(hass)
    assert candidate.statuses["mode"] == "unmapped_state"
    assert candidate.statuses["pressure"] == "invalid_unit_or_value"


@pytest.mark.parametrize(
    "case,status",
    [
        ("disabled", "disabled_or_excluded"),
        ("unknown", "unavailable"),
        ("unavailable", "unavailable"),
        ("missing_state", "unavailable"),
        ("gallons", "invalid_unit_or_value"),
        ("negative", "invalid_unit_or_value"),
        ("ambiguous", "ambiguous"),
    ],
)
def test_unusable_flow_is_explicit_not_an_arbitrary_choice(hass, vicare_device, case, status):
    origin, device, sources = vicare_device()
    entity = sources["flow"]
    registry = er.async_get(hass)
    if case == "disabled":
        registry.async_update_entity(entity.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    elif case == "missing_state":
        hass.states.async_remove(entity.entity_id)
    elif case == "ambiguous":
        registry.async_get_or_create(
            "sensor", "vicare", entity.unique_id, config_entry=origin, device_id=device.id
        )
        # A second registered ViCare identifier can expose the same semantic role.
        identifier = "demo_ambiguous"
        dr.async_get(hass).async_update_device(
            device.id, new_identifiers={*device.identifiers, ("vicare", identifier)}
        )
        registry.async_get_or_create(
            "sensor",
            "vicare",
            f"{identifier}-volumetric_flow",
            config_entry=origin,
            device_id=device.id,
            translation_key="volumetric_flow",
        )
    else:
        hass.states.async_set(
            entity.entity_id,
            "-1" if case == "negative" else "12" if case == "gallons" else case,
            {"unit_of_measurement": "gallons" if case == "gallons" else "L/min"},
        )
    (candidate,) = discover(hass)
    assert candidate.statuses["flow"] == status
    if case in ("disabled", "ambiguous"):
        assert candidate.config["flow_entity"] is None


@pytest.mark.parametrize(
    "role,key,translation",
    [
        ("pump", "circulationpump_active-1", "circulation_pump"),
        ("mode", "compressor_phase-1", "compressor_phase"),
    ],
)
def test_multiple_circuits_or_compressors_are_ambiguous(
    hass, vicare_device, role, key, translation
):
    origin, device, sources = vicare_device()
    identifier = next(iter(device.identifiers))[1]
    er.async_get(hass).async_get_or_create(
        sources[role].domain,
        "vicare",
        f"{identifier}-{key}",
        config_entry=origin,
        device_id=device.id,
        translation_key=translation,
    )
    (candidate,) = discover(hass)
    assert candidate.config[f"{role}_entity"] is None
    assert candidate.statuses[role] == "ambiguous"


@pytest.mark.enable_socket
@pytest.mark.allow_hosts(["127.0.0.1", "::1"])
@pytest.mark.parametrize("count", [1, 2])
async def test_quick_http_path_no_typing_then_real_setup_and_every_option(
    hass, hass_client, vicare_device, count, freezer
):
    for _ in range(count):
        vicare_device()
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()
    response = await client.post("/api/config/config_entries/flow", json={"handler": DOMAIN})
    assert response.status == 200
    result = await response.json()
    url = f"/api/config/config_entries/flow/{result['flow_id']}"
    confirmation_count = 0
    if count > 1:
        assert result["step_id"] == "select_device"
        fields = result["data_schema"]
        assert len(fields) == 1 and fields[0]["name"] == "device_id"
        choices = fields[0]["selector"]["select"]
        assert choices["mode"] == "list"
        assert len(choices["options"]) == count
        response = await client.post(url, json={"device_id": choices["options"][0]["value"]})
        assert response.status == 200
        result = await response.json()
        confirmation_count += 1
    assert result["step_id"] == "confirm"
    assert result["data_schema"] == []  # No entity IDs, numbers, lists or text to enter.
    assert "Emails stay OFF" in result["description_placeholders"]["summary"]
    response = await client.post(url, json={})
    assert response.status == 200
    assert (await response.json())["type"] == "create_entry"
    confirmation_count += 1
    assert confirmation_count == count
    await hass.async_block_till_done()
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    assert entry.state is ConfigEntryState.LOADED
    runtime = entry.runtime_data
    assert not runtime.config["emails_enabled"]
    assert runtime.config["min_flow_l_min"] is None
    registry = er.async_get(hass)
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 15
    # Genuine reports, not pre-setup cached states, expose the flow in observation mode.
    freezer.tick(timedelta(seconds=1))
    for role in ("flow", "mode", "pump"):
        old = hass.states.get(runtime.config[f"{role}_entity"])
        hass.states.async_set(old.entity_id, old.state, dict(old.attributes))
    await hass.async_block_till_done()
    await runtime.evaluate()
    assert runtime.observed_flow() == 12
    assert runtime.engine.result.state != "normal"
    assert runtime.engine.result.incident_id is None
    assert runtime.trends[-1]["flow"] == 12
    assert "minimum_not_configured" in runtime.limitations
    # All advanced menu forms go through HA's real HTTP schema serializer.
    for step in ("minimum", "sources", "rules", "emails", "report"):
        response = await client.post(
            "/api/config/config_entries/options/flow", json={"handler": entry.entry_id}
        )
        menu = await response.json()
        option_url = f"/api/config/config_entries/options/flow/{menu['flow_id']}"
        response = await client.post(option_url, json={"next_step_id": step})
        assert response.status == 200
        form = await response.json()
        assert form["step_id"] == step
        assert form["data_schema"]
        current = entry.runtime_data.config
        if step == "minimum":
            payload = {}
        elif step == "sources":
            payload = {
                key: current[key]
                for key in ("name", "device_ids", *(f"{role}_entity" for role in SOURCE_ROLES))
                if current.get(key) is not None
            }
        elif step == "rules":
            payload = {key: current[key] for key in (*NUMERIC_RULES, *LIST_SETTINGS)}
        elif step == "emails":
            payload = {key: current[key] for key in EMAIL_DEFAULTS}
        else:
            payload = {"report_entities": [], "report_exclude": []}
        response = await client.post(option_url, json=payload)
        assert response.status == 200
        assert (await response.json())["type"] == "create_entry"
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert not entry.runtime_data.config["emails_enabled"]
    # Adding and clearing the actual optional minimum both execute a real options reload.
    for payload, expected in (({"min_flow_l_min": 8}, 8), ({}, None)):
        response = await client.post(
            "/api/config/config_entries/options/flow", json={"handler": entry.entry_id}
        )
        option_url = f"/api/config/config_entries/options/flow/{(await response.json())['flow_id']}"
        await client.post(option_url, json={"next_step_id": "minimum"})
        response = await client.post(option_url, json=payload)
        assert response.status == 200
        assert (await response.json())["type"] == "create_entry"
        await hass.async_block_till_done()
        assert entry.runtime_data.config["min_flow_l_min"] == expected
        assert entry.state is ConfigEntryState.LOADED
        assert entry.options["emails_enabled"] is False
        assert entry.runtime_data.config["flow_entity"] == runtime.config["flow_entity"]


async def test_duplicate_quick_flow_and_legacy_manual_device(hass, vicare_device):
    _, device, _ = vicare_device()
    existing = MockConfigEntry(domain=DOMAIN, data={"device_ids": [device.id]})
    existing.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_parallel_flows_cannot_create_duplicate(hass, vicare_device):
    vicare_device()
    first = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    second = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    created = await hass.config_entries.flow.async_configure(first["flow_id"], {})
    assert created["type"] == "create_entry"
    blocked = await hass.config_entries.flow.async_configure(second["flow_id"], {})
    assert blocked["type"] == "abort" and blocked["reason"] == "already_configured"
    await hass.async_block_till_done()


async def test_migration_preserves_expert_overrides_and_rename_across_reload(
    hass, source_config, freezer
):
    original = dict(source_config)
    entry = await setup_guard(hass, source_config)
    assert entry.minor_version == 4
    assert entry.data == original
    runtime = entry.runtime_data
    before = fingerprint(runtime.config)
    flow = er.async_get(hass).async_get(source_config["flow_entity"])
    renamed = er.async_get(hass).async_update_entity(
        flow.entity_id, new_entity_id="sensor.renamed_after_setup"
    )
    await hass.async_block_till_done()
    assert runtime.config["flow_entity"] == renamed.entity_id
    assert fingerprint(runtime.config) == before
    source_config["flow_entity"] = renamed.entity_id
    hass.states.async_set(renamed.entity_id, "12", {"unit_of_measurement": "L/min"})
    await reports(hass, source_config, freezer)
    assert runtime.observed_flow() == 12
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.config["flow_entity"] == renamed.entity_id
    assert entry.runtime_data.config["min_flow_l_min"] == 8
    assert entry.runtime_data.config["running_modes"] == original["running_modes"]
    assert entry.runtime_data.config["emails_enabled"] is False


async def test_explicit_report_exclusion_survives_registry_rename(hass, source_config):
    # Remove an optional mapping so it is solely governed by automatic inventory/exclusions.
    excluded = source_config.pop("supply_temperature_entity")
    source_config["report_exclude"] = [excluded]
    entry = await setup_guard(hass, bind_sources(hass, source_config))
    renamed = er.async_get(hass).async_update_entity(
        excluded, new_entity_id="sensor.renamed_excluded"
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.config["report_exclude"] == [renamed.entity_id]
    assert renamed.entity_id not in inventory(hass, entry.runtime_data.config)[0]


async def test_observation_survives_missing_context_without_false_alert(
    hass, vicare_device, freezer
):
    vicare_device(missing=["mode", "pump"])
    (candidate,) = discover(hass)
    entry = await setup_guard(hass, candidate.config)
    freezer.tick(timedelta(seconds=1))
    flow_id = candidate.config["flow_entity"]
    hass.states.async_set(flow_id, "0.72", {"unit_of_measurement": "m³/h"})
    await hass.async_block_till_done()
    runtime = entry.runtime_data
    assert runtime.observed_flow() == 12
    assert runtime.engine.result.state == "diagnostic_unavailable"
    assert runtime.engine.result.incident_id is None
    assert runtime.engine.result.reference is None
    with pytest.raises(ValueError):
        runtime.engine.confirm_calibration(runtime.started_at + 1)


@pytest.mark.enable_socket
@pytest.mark.allow_hosts(["127.0.0.1", "::1"])
async def test_local_report_http_response_is_device_scoped_and_sends_nothing(
    hass, hass_client, vicare_device, freezer
):
    assert await async_setup_component(hass, "api", {})
    vicare_device()
    (candidate,) = discover(hass)
    _, _, others = vicare_device(name="Unrelated installation")
    entry = await setup_guard(hass, candidate.config)
    freezer.tick(timedelta(seconds=1))
    for key in ("flow_entity", "mode_entity", "pump_entity"):
        state = hass.states.get(candidate.config[key])
        hass.states.async_set(state.entity_id, state.state, dict(state.attributes))
    await hass.async_block_till_done()
    client = await hass_client()
    before = entry.runtime_data.export()
    with patch.object(entry.runtime_data, "_send", new_callable=AsyncMock) as send:
        response = await client.post(
            "/api/services/viessmann_guard/get_report?return_response",
            json={"entry_id": entry.entry_id},
        )
        assert response.status == 200
        report = (await response.json())["service_response"]
        assert set(report) == {"title", "message", "html"}
        assert "12 L/min" in report["message"]
        assert "minimum" in report["message"].lower()
        assert "Unrelated installation" not in report["message"]
        assert not any(entity.entity_id in report["message"] for entity in others.values())
        send.assert_not_awaited()
    assert entry.runtime_data.export() == before
    assert entry.runtime_data.config["emails_enabled"] is False


@pytest.mark.parametrize("change", ["disable", "remove", "move"])
async def test_registry_source_loss_never_falls_back_to_old_state(
    hass, vicare_device, freezer, change
):
    _, _, sources = vicare_device()
    (candidate,) = discover(hass)
    entry = await setup_guard(hass, candidate.config)
    registry = er.async_get(hass)
    flow = sources["flow"]
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(flow.entity_id, "0.72", {"unit_of_measurement": "m³/h"})
    await hass.async_block_till_done()
    assert entry.runtime_data.observed_flow() == 12
    if change == "disable":
        registry.async_update_entity(flow.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    elif change == "remove":
        registry.async_remove(flow.entity_id)
    else:
        _, other, _ = vicare_device()
        registry.async_update_entity(flow.entity_id, device_id=other.id)
    await hass.async_block_till_done()
    assert entry.runtime_data.observed_flow() is None
    assert flow.entity_id not in inventory(hass, entry.runtime_data.config)[0]
    assert entry.runtime_data.engine.result.incident_id is None


async def test_summary_rechecks_sources_before_creating_entry(hass, vicare_device):
    _, _, sources = vicare_device()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["step_id"] == "confirm"
    er.async_get(hass).async_update_entity(
        sources["pump"].entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "confirm" and result["errors"]["base"] == "source_changed"
    assert not hass.config_entries.async_entries(DOMAIN)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    assert result["data"]["pump_entity"] is None
    await hass.async_block_till_done()


async def test_same_identity_rename_preserves_explicit_healthy_reference(
    hass, source_config, freezer
):
    source_config.update(calibration_samples=3, calibration_duration_s=20)
    entry = await setup_guard(hass, source_config)
    await reports(hass, source_config, freezer)
    runtime = entry.runtime_data
    runtime.engine.confirm_calibration(runtime.started_at + 1)
    for _ in range(3):
        await reports(hass, source_config, freezer, seconds=11)
    assert runtime.engine.result.reference == 12
    before = fingerprint(runtime.config)
    registry = er.async_get(hass)
    renamed = registry.async_update_entity(
        source_config["flow_entity"], new_entity_id="sensor.healthy_renamed"
    )
    source_config["flow_entity"] = renamed.entity_id
    hass.states.async_set(renamed.entity_id, "12", {"unit_of_measurement": "L/min"})
    await hass.async_block_till_done()
    assert fingerprint(runtime.config) == before
    await runtime.save()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.engine.serialize()["baseline"]["value"] == 12
    assert not entry.runtime_data.engine.result.incident_confirmed


async def test_expert_override_survives_automatic_entry_reload(hass, vicare_device):
    origin, device, sources = vicare_device()
    (candidate,) = discover(hass)
    entry = await setup_guard(hass, candidate.config)
    custom = er.async_get(hass).async_get_or_create(
        "sensor",
        "vicare",
        "demo_expert_external_phase",
        config_entry=origin,
        device_id=device.id,
        suggested_object_id="demo_custom_phase",
    )
    hass.states.async_set(custom.entity_id, "heat")
    config = {
        **entry.runtime_data.config,
        "mode_entity": custom.entity_id,
        "running_modes": ["heat"],
        "min_flow_l_min": 9,
    }
    hass.config_entries.async_update_entry(entry, options=bind_sources(hass, config))
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.config["mode_entity"] == custom.entity_id
    assert entry.runtime_data.config["mode_entity"] != sources["mode"].entity_id
    assert entry.runtime_data.config["running_modes"] == ["heat"]
    assert entry.runtime_data.config["min_flow_l_min"] == 9
