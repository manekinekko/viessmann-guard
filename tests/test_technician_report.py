"""Useful heating-technician context without inferred roles or invented measurements."""

from copy import deepcopy
from datetime import timedelta
from html import unescape
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import entity_registry as er
from test_evidence import synthetic_report
from test_integration import setup_guard

from custom_components.viessmann_guard.const import MAX_REPORT_ENTITIES
from custom_components.viessmann_guard.discovery import discover
from custom_components.viessmann_guard.email_layout import _WORDS
from custom_components.viessmann_guard.report import (
    _LABELS,
    _technician_rows,
    render_report,
    report_copy,
)
from custom_components.viessmann_guard.telemetry import inventory


@pytest.mark.parametrize("language", ("en", "fr", "es", "de"))
@pytest.mark.parametrize("kind", ("urgent", "watch", "reminder", "recovery", "test", "report"))
def test_technician_context_is_upfront_localized_and_keeps_flow_large(language, kind):
    data = synthetic_report()
    if kind == "recovery":
        data.update(state="normal", reason_code="stable_recovery")
        data["incident"]["closed_at"] = data["generated_at"]
    copy = report_copy(language)
    title, plain, html = render_report(data, kind, language)
    front = unescape(html).split(copy["inspection_checks"])[0]
    assert copy["technician"] in front and copy["technician"] in plain
    for role in (
        "mode",
        "pump",
        "pump_speed",
        "compressor",
        "supply_temperature",
        "return_temperature",
        "delta_t",
        "pressure",
        "outside_temperature",
        "fault",
    ):
        if kind == "report" or role not in {"compressor", "outside_temperature"}:
            assert copy[role] in front and copy[role] in plain
    assert ("38.5 °C" if language == "en" else "38,5 °C") in front
    assert ("5.5 °C" if language == "en" else "5,5 °C") in front
    assert ("1.6 bar" if language == "en" else "1,6 bar") in front
    assert "55 %" in front
    assert front.count("font-size:48px;line-height:1.2;color:#FF3E17") == 2
    if kind == "report":
        assert copy["check_conditions"] in unescape(html) and copy["check_conditions"] in plain
        assert copy["check_hydraulics"] in unescape(html) and copy["check_record"] in plain
        assert copy["measurements_note"] in front
    else:
        assert copy["check_conditions"] not in html
        assert _WORDS["email_note"][("en", "fr", "es", "de").index(language)] in front
        assert len(plain.split()) <= 250
        assert len(plain.splitlines()) <= 40
        assert html.count('class="guard-big"') == 2
        assert "sensor.synthetic" not in html + plain
        assert copy["thresholds"] not in html + plain
        assert copy["telemetry"] not in html + plain
        assert "Recorder" not in html + plain
        assert _WORDS["appendix"][("en", "fr", "es", "de").index(language)] not in html + plain
        detailed = render_report(data, "report", language)[1]
        assert len(plain.split()) < len(detailed.split()) / 3
    if kind == "recovery":
        assert not title.startswith("[")
        assert copy["normal"] in front
    assert all(len(values) == 4 for values in _LABELS.values())


@pytest.mark.parametrize("status", ("stale", "unavailable", "awaiting_fresh_report", "invalid"))
def test_current_context_does_not_display_old_numeric_values_as_current(status):
    data = {
        "telemetry": [
            {
                "roles": ["pressure"],
                "value": 99.9,
                "unit": "bar",
                "status": status,
                "freshness_seconds": 241,
            }
        ]
    }
    copy = report_copy("fr")
    rows = dict(_technician_rows(data, copy, "fr"))
    assert "99" not in rows[copy["pressure"]]
    assert "bar" not in rows[copy["pressure"]]
    assert "241 secondes" in rows[copy["pressure"]]
    if status == "stale":
        assert copy["stale"] in rows[copy["pressure"]]


def test_source_names_and_unmapped_generic_faults_cannot_substitute_roles():
    data = {
        "telemetry": [
            {"name": "Supply temperature", "value": 80, "status": "ok", "unit": "°C"},
            {"name": "Flow fault", "value": "on", "status": "ok"},
            {"roles": ["pressure"], "value": {"private": "DO_NOT_RENDER"}, "status": "ok"},
        ]
    }
    copy = report_copy("en")
    rows = dict(_technician_rows(data, copy, "en"))
    assert rows[copy["supply_temperature"]] == copy["missing"]
    assert rows[copy["fault"]] == copy["missing"]
    assert rows[copy["pressure"]] == copy["missing"]
    assert "DO_NOT_RENDER" not in str(rows)


def test_zero_values_and_negative_delta_remain_real_escaped_measurements():
    data = {
        "telemetry": [
            {"roles": ["pressure"], "value": 0, "unit": "bar", "status": "ok"},
            {"roles": ["delta_t"], "value": -3.123456, "unit": "°C", "status": "ok"},
            {"roles": ["mode"], "value": '<script src="bad">', "status": "ok"},
        ]
    }
    _, plain, html = render_report(data, "report", "fr")
    assert "0 bar" in plain and "-3,12 °C" in plain
    assert '<script src="bad">' not in html
    assert "&lt;script src=&quot;bad&quot;&gt;" in html


async def test_runtime_uses_bound_roles_units_and_preserves_engine_and_delivery(
    hass, vicare_device, freezer
):
    _, _, sources = vicare_device()
    (candidate,) = discover(hass)
    entry = await setup_guard(hass, candidate.config)
    runtime = entry.runtime_data
    freezer.tick(timedelta(seconds=1))
    for source in sources.values():
        state = hass.states.get(source.entity_id)
        hass.states.async_set(source.entity_id, state.state, dict(state.attributes))
    hass.states.async_set(
        sources["return_temperature"].entity_id, "95", {"unit_of_measurement": "°F"}
    )
    await hass.async_block_till_done()
    before = deepcopy(runtime.export())
    with (
        patch.object(runtime, "_send", new_callable=AsyncMock) as send,
        patch(
            "custom_components.viessmann_guard.runtime.render_report", wraps=render_report
        ) as render,
    ):
        result = runtime.observation_report()
    assert runtime.export() == before
    send.assert_not_awaited()
    rows = dict(_technician_rows(render.call_args.args[0], report_copy("en"), "en"))
    assert rows["Supply water temperature"].startswith("40 °C")
    assert rows["Return water temperature"].startswith("95 °F")
    assert rows[report_copy("en")["delta_t"]].startswith("5 °C")
    assert rows["Configured fault signal (raw)"] == report_copy("en")["missing"]
    assert "Current hydraulic operating context" in result["html"]
    # No stale value or delta survives when just the return report expires.
    freezer.tick(timedelta(seconds=181))
    hass.states.async_set(
        sources["supply_temperature"].entity_id, "40", {"unit_of_measurement": "°C"}
    )
    with patch(
        "custom_components.viessmann_guard.runtime.render_report", wraps=render_report
    ) as render:
        runtime.observation_report()
    rows = dict(_technician_rows(render.call_args.args[0], report_copy("en"), "en"))
    assert "95" not in rows["Return water temperature"]
    assert "Stale" in rows["Return water temperature"]
    assert "°C" not in rows[report_copy("en")["delta_t"]]


@pytest.mark.parametrize(
    "role,value,unit",
    [
        ("pressure", "1.5", "unknown"),
        ("pressure", "-1", "bar"),
        ("supply_temperature", "warm", "°C"),
        ("return_temperature", "35", "unknown"),
    ],
)
async def test_mapped_context_validates_units_without_device_class(
    hass, vicare_device, freezer, role, value, unit
):
    _, _, sources = vicare_device()
    (candidate,) = discover(hass)
    entry = await setup_guard(hass, candidate.config)
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(sources[role].entity_id, value, {"unit_of_measurement": unit})
    with patch(
        "custom_components.viessmann_guard.runtime.render_report", wraps=render_report
    ) as render:
        entry.runtime_data.observation_report()
    copy = report_copy("en")
    rows = dict(_technician_rows(render.call_args.args[0], copy, "en"))
    assert copy["missing"] in rows[copy[role]]
    assert "Invalid" in rows[copy[role]]


def test_explicit_hydraulic_sources_survive_the_bounded_inventory(hass, vicare_device):
    origin, device, _ = vicare_device()
    (candidate,) = discover(hass)
    for index in range(MAX_REPORT_ENTITIES):
        entity = er.async_get(hass).async_get_or_create(
            "sensor",
            "vicare",
            f"synthetic_extra_{index}",
            config_entry=origin,
            device_id=device.id,
            suggested_object_id=f"aaa_extra_{index}",
        )
        hass.states.async_set(
            entity.entity_id,
            "20",
            {
                "unit_of_measurement": "°C",
                "device_class": "temperature",
            },
        )
    ids, truncated = inventory(hass, candidate.config)
    assert truncated and len(ids) == MAX_REPORT_ENTITIES
    assert all(
        value in ids for key, value in candidate.config.items() if key.endswith("_entity") and value
    )


def test_conflicting_role_rows_stay_unknown_instead_of_picking_a_value():
    copy = report_copy("en")
    data = {
        "telemetry": [
            {"roles": ["pressure"], "value": value, "unit": "bar", "status": "ok"}
            for value in (1.2, 2.3)
        ]
    }
    assert dict(_technician_rows(data, copy, "en"))[copy["pressure"]] == copy["missing"]


@pytest.mark.parametrize("reason", ("mode_idle", "flow_stale", "stable_recovery"))
def test_compact_email_keeps_current_state_distinct_from_the_recorded_alert(reason):
    from custom_components.viessmann_guard.reasons import describe_reason

    data = synthetic_report()
    data.update(reason_code=reason, state="diagnostic_unavailable")
    original = deepcopy(data)
    _, plain, html = render_report(data, "reminder", "fr")
    for content in (plain, unescape(html)):
        assert describe_reason(reason, "fr") in content
        assert "8,75" in content
        assert "20 secondes" in content
    assert data == original


def test_compact_relative_and_native_fault_keep_actual_trigger_evidence():
    data = synthetic_report()
    capture = data["incident_capture"]
    capture.update(reason="relative_flow_decline", reference=24, relative_drop_pct=25)
    _, plain, _ = render_report(data, "watch", "fr")
    assert "24 L/min" in plain and "25 %" in plain
    capture.update(reason="native_fault", flow=None, fault="F_SYNTHETIC")
    _, plain, html = render_report(data, "urgent", "fr")
    assert "F_SYNTHETIC" in plain + html
    assert "8,75" not in plain + html
    assert "Débit au déclenchement de l'alerte: Manquant" in plain
