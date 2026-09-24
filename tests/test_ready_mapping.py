"""Native ViCare ready/idle compatibility without rewriting expert intent or evidence."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import homeassistant
import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_engine import snapshot
from test_integration import reports, settle, smtp_recipient

from custom_components.viessmann_guard import async_migrate_entry
from custom_components.viessmann_guard.const import DOMAIN
from custom_components.viessmann_guard.discovery import discover
from custom_components.viessmann_guard.engine import Engine, Measurement
from custom_components.viessmann_guard.history import observation
from custom_components.viessmann_guard.report import render_report
from custom_components.viessmann_guard.runtime import (
    GuardRuntime,
    compatible_fingerprints,
    configuration,
    fingerprint,
    settings,
)


def legacy_config(hass):
    (candidate,) = discover(hass)
    data = deepcopy(candidate.config)
    data.pop("automatic_phase_profile")
    data["idle_modes"] = ["off"]
    return data


def test_ready_is_idle_in_installed_native_vicare_catalog():
    root = Path(next(iter(homeassistant.__path__)))
    native = json.loads((root / "components/vicare/strings.json").read_text())
    assert (
        native["entity"]["sensor"]["compressor_phase"]["state"]["ready"]
        == "[%key:common::state::idle%]"
    )


async def test_new_automatic_entry_ready_is_known_idle_not_active(hass, vicare_device, freezer):
    _, _, sources = vicare_device()
    hass.states.async_set(sources["mode"].entity_id, "ready")
    hass.states.async_set(sources["pump"].entity_id, "off")
    (candidate,) = discover(hass)
    assert candidate.statuses["mode"] == "detected"
    assert candidate.config["idle_modes"] == ["off", "ready"]
    assert "ready" not in candidate.config["running_modes"]
    assert candidate.config["automatic_phase_profile"] == 1
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["step_id"] == "confirm"
    created = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    entry = created["result"]
    assert entry.minor_version == 4
    await reports(
        hass, candidate.config, freezer, seconds=61, flow="0.72", mode="ready", pump="off"
    )
    await settle(entry.runtime_data)
    assert entry.runtime_data.engine.result.reason == "mode_idle"
    assert entry.runtime_data.flow_history.rows[-1]["quality"] == "mode_excluded"
    assert entry.runtime_data.flow_history.rows[-1]["mode_verified"]
    assert entry.runtime_data.flow_history.rows[-1]["flow"] is None
    assert entry.runtime_data.engine.incident is None


@pytest.mark.parametrize("copied_options", [False, True])
@pytest.mark.parametrize("escalated", [False, True])
async def test_existing_automatic_entry_keeps_reference_history_capture_and_email_options(
    hass, vicare_device, hass_storage, freezer, copied_options, escalated
):
    vicare_device()
    data = legacy_config(hass)
    data.update(
        min_flow_l_min=10,
        startup_grace_s=0,
        absolute_persistence_s=20,
        relative_persistence_s=20,
    )
    _, recipient = smtp_recipient(hass)
    options = deepcopy(data) if copied_options else {}
    options.update(emails_enabled=True, recipients=[recipient], language="de")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Synthetic legacy automatic Guard",
        data=data,
        options=options,
        version=1,
        minor_version=3,
    )
    entry.add_to_hass(hass)
    old_options = deepcopy(options)
    previous = GuardRuntime(hass, entry)
    now = dt_util.utcnow().timestamp()
    baseline = {"value": 40, "mode": "heating", "pump_speed": None, "confirmed_at": now - 3600}
    old_fingerprint = fingerprint(previous.config)
    previous.engine = Engine(
        settings(previous.config),
        {"version": 2, "baseline": baseline},
        source_fingerprint=old_fingerprint,
    )
    for stamp in (now - 300, now - 299, now - 279):
        previous.engine.evaluate(snapshot(stamp, 29 if escalated else 4, mode="heating"))
    if escalated:
        assert previous.engine.incident["severity"] == "watch"
        for stamp in (now - 278, now - 258):
            previous.engine.evaluate(snapshot(stamp, 4, mode="heating"))
        assert previous.engine.incident["escalation"]
    assert previous.engine.incident
    capture = previous.engine.incident
    previous.engine.acknowledge(now - 250)
    previous.engine.snooze(now - 250, 3600)
    previous.engine.record_cleaning(now - 249)
    idle = snapshot(now - 100, 12, mode="ready", pump="off")
    previous.flow_history.add(idle, previous.engine.settings, previous.engine.evaluate(idle))
    old_rows = deepcopy(previous.flow_history.rows)
    assert old_rows[0]["quality"] == "mode_unmapped"
    assert old_rows[0]["mode_verified"] is False
    stored = previous.export()
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {"version": 1, "minor_version": 1, "data": stored}
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry.runtime_data
    assert entry.minor_version == 4
    assert entry.data["automatic_phase_profile"] == 1
    assert runtime.config["idle_modes"] == ["off", "ready"]
    expected_options = {**old_options}
    if copied_options:
        expected_options["idle_modes"] = ["off", "ready"]
    assert entry.options == expected_options
    assert runtime.config["emails_enabled"] is True
    assert runtime.config["recipients"] == [recipient]
    assert runtime.config["language"] == "de"
    assert runtime.config["stale_after_s"] == 180
    assert runtime.engine.serialize()["baseline"] == baseline
    assert runtime.engine.serialize() == stored["engine"]
    assert runtime.engine.incident == capture
    assert runtime.flow_history.rows[: len(old_rows)] == old_rows
    assert old_fingerprint in compatible_fingerprints(runtime.config)
    assert runtime.engine.incident["opening"]["source_fingerprint"] == old_fingerprint
    with patch(
        "custom_components.viessmann_guard.runtime.render_report", wraps=render_report
    ) as render:
        runtime._render("report")
    assert render.call_args.args[0]["incident_source_changed"] is False
    assert render.call_args.args[0]["incident_capture"] == (
        capture["escalation"] or capture["opening"]
    )
    await reports(hass, runtime.config, freezer, seconds=61, flow="0.72", mode="ready", pump="off")
    await settle(runtime)
    assert runtime.engine.incident == capture
    assert runtime.engine.last_incident is None
    assert runtime.diagnostic_state == "diagnostic_unavailable"
    assert runtime.flow_history.rows[-1]["quality"] == "mode_excluded"
    assert runtime.flow_history.rows[-1]["mode_verified"]
    assert runtime.engine.serialize()["baseline"] == baseline
    migrated_data = deepcopy(dict(entry.data))
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.data == migrated_data
    assert entry.runtime_data.engine.incident == capture
    assert entry.runtime_data.engine.serialize()["baseline"] == baseline
    for change in (
        {"stale_after_s": 181},
        {
            "source_registry_ids": {
                **runtime.config["source_registry_ids"],
                "mode_entity": "different_source",
            }
        },
        {"idle_modes": ["off"]},
        {"setup_mode": "manual"},
    ):
        changed = {**entry.runtime_data.config, **change}
        assert compatible_fingerprints(changed) == {fingerprint(changed)}


@pytest.mark.parametrize(
    "change",
    [
        {"setup_mode": "manual"},
        {"idle_modes": ["off", "custom_idle"]},
        {"running_modes": ["heating", "dhw"]},
        {"excluded_modes": ["defrost", "transition"]},
        {"discovery_statuses": {}},
        {"automatic_phase_profile": 99},
    ],
)
async def test_expert_or_unproven_legacy_entry_is_not_remapped(hass, vicare_device, change):
    vicare_device()
    data = legacy_config(hass)
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=change, version=1, minor_version=3)
    entry.add_to_hass(hass)
    original_data, original_options = deepcopy(dict(entry.data)), deepcopy(dict(entry.options))
    assert await async_migrate_entry(hass, entry)
    assert entry.minor_version == 4
    assert entry.data == original_data
    assert entry.options == original_options
    assert "ready_idle_compatibility" not in configuration(entry)


@pytest.mark.parametrize(
    "change", ["wrong_provider", "wrong_descriptor", "disabled", "source_override"]
)
async def test_migration_requires_unchanged_enabled_native_source_provenance(
    hass, vicare_device, change
):
    vicare_device()
    data = legacy_config(hass)
    registry = er.async_get(hass)
    entity = registry.async_get(data["mode_entity"])
    if change == "wrong_provider":
        data["source_registry_ids"]["mode_entity"] = registry.async_get_or_create(
            "sensor", "other", "synthetic_foreign", device_id=entity.device_id
        ).id
    elif change == "disabled":
        registry.async_update_entity(entity.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    elif change == "wrong_descriptor":
        registry.async_update_entity(entity.entity_id, translation_key="dhw_operating_mode")
    options = (
        {
            "source_registry_ids": {
                **data["source_registry_ids"],
                "mode_entity": "missing_registry_id",
            }
        }
        if change == "source_override"
        else {}
    )
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=options, minor_version=3)
    entry.add_to_hass(hass)
    original = deepcopy(dict(entry.data))
    assert await async_migrate_entry(hass, entry)
    assert entry.data == original
    assert entry.options == options


async def test_bound_native_source_rename_does_not_lose_migration_provenance(hass, vicare_device):
    vicare_device()
    data = legacy_config(hass)
    registry = er.async_get(hass)
    entity = registry.async_update_entity(
        data["mode_entity"], new_entity_id="sensor.renamed_native_phase"
    )
    entry = MockConfigEntry(
        domain=DOMAIN, data=data, options={"mode_entity": entity.entity_id}, minor_version=3
    )
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry)
    assert entry.data["idle_modes"] == ["off", "ready"]
    assert entry.options["mode_entity"] == entity.entity_id


async def test_manual_entry_keeps_ready_unmapped(hass, source_config):
    source_config["idle_modes"] = ["off"]
    entry = MockConfigEntry(domain=DOMAIN, data=source_config, minor_version=3)
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry)
    assert "ready" not in configuration(entry)["idle_modes"]
    assert entry.data == source_config


async def test_later_expert_override_is_not_reapplied_on_reload(hass, vicare_device):
    vicare_device()
    entry = MockConfigEntry(domain=DOMAIN, data=legacy_config(hass), minor_version=3)
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry)
    migrated = deepcopy(dict(entry.data))
    hass.config_entries.async_update_entry(entry, options={"idle_modes": ["off"]})
    assert await async_migrate_entry(hass, entry)
    assert entry.data == migrated
    assert configuration(entry)["idle_modes"] == ["off"]


async def test_ready_classification_does_not_invent_freshness_or_hide_native_fault(
    hass, vicare_device
):
    vicare_device()
    (candidate,) = discover(hass)
    rules = settings(candidate.config)
    fresh = snapshot(1000, None, mode="ready", pump="off", flow_at=100)
    fresh = replace(fresh, flow=replace(fresh.flow, status="stale"))
    engine = Engine(rules)
    result = engine.evaluate(fresh)
    assert result.reason == "mode_idle"
    row = observation(fresh, rules, result)
    assert row["quality"] == "mode_excluded" and row["mode_verified"]
    assert row["flow"] is None
    stale_mode = replace(fresh, mode=Measurement("ready", 100))
    assert Engine(rules).evaluate(stale_mode).reason == "mode_stale"
    assert not observation(stale_mode, rules, result)["mode_verified"]
    assert observation(stale_mode, rules, result)["quality"] != "mode_excluded"
    fault_rules = replace(rules, fault_values=("FLOW_FAULT",), fault_clear_values=("off",))
    faulty = replace(fresh, fault=Measurement("FLOW_FAULT", 1000))
    engine = Engine(fault_rules)
    assert engine.evaluate(faulty).reason == "native_fault"
    assert engine.result.incident_severity == "urgent"
    assert engine.incident["opening"]["mode"] == "ready"
    assert engine.incident["opening"]["flow"] is None
