"""Exact incident captures and honest local sampling, using synthetic facts only."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from html import unescape
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from test_engine import absolute_incident, relative_incident, settings, snapshot
from test_integration import reports, settle, setup_guard
from test_report import Tags

from custom_components.viessmann_guard.email_layout import _WORDS
from custom_components.viessmann_guard.engine import Engine, validate_capture
from custom_components.viessmann_guard.history import (
    MAX_SAMPLES,
    RETENTION_SECONDS,
    FlowHistory,
    observation,
)
from custom_components.viessmann_guard.report import render_report
from custom_components.viessmann_guard.runtime import fingerprint
from custom_components.viessmann_guard.storage import validate_storage

ANCHOR = {"mode": "heat", "pump": "on", "pump_speed": 55, "speed_configured": True}


def test_open_escalation_reminder_and_recovery_keep_exact_independent_evidence():
    engine = Engine(settings())
    relative_incident(engine, speed=55)
    opening = engine.incident["opening"]
    assert opening["flow"] == 29
    assert opening["flow_reported_at"] == opening["decided_at"] == 52
    assert opening["duration_s"] == 30
    assert opening["reference"] == 40
    engine.evaluate(snapshot(53, 9, speed=55))
    result = engine.evaluate(snapshot(73, 8, speed=55, flow_at=72))
    assert result.transition == "escalated"
    incident = engine.incident
    escalation = incident["escalation"]
    assert escalation["flow"] == 8
    assert escalation["flow_reported_at"] == 72
    assert escalation["decided_at"] == 73
    assert escalation["minimum"] == 10
    assert escalation["observed_since"] == 53
    engine.evaluate(snapshot(90, 6, speed=55))
    assert engine.incident == incident
    engine.incident["opening"]["flow"] = 999
    assert engine.incident["opening"] == opening
    engine.evaluate(snapshot(91, 40, speed=55))
    assert engine.evaluate(snapshot(111, 40, speed=55)).transition == "recovered"
    assert engine.incident is None
    assert engine.last_incident == {**incident, "closed_at": 111}
    restored = Engine(settings(), json.loads(json.dumps(engine.serialize())))
    assert restored.last_incident == engine.last_incident
    assert restored.last_incident["opening"] == opening


@pytest.mark.parametrize("flow", [0, None])
def test_native_fault_without_fresh_flow_never_substitutes_a_value(flow):
    engine = Engine(settings(fault_values=("F-FLOW",)))
    sample = snapshot(100, flow, fault="F-FLOW", flow_at=1 if flow is None else 100)
    assert engine.evaluate(sample).transition == "opened"
    capture = engine.incident["opening"]
    assert capture["flow"] == flow
    assert capture["flow_reported_at"] == (None if flow is None else 100)
    assert capture["fault"] == "F-FLOW"
    assert capture["fault_reported_at"] == 100
    assert capture["reason"] == "native_fault"
    validate_capture(capture)


def test_fault_capture_rejects_changed_value_with_reused_report_timestamp():
    engine = Engine(settings(fault_values=("F",)))
    engine.evaluate(snapshot(10, 30, fault="off"))
    engine.evaluate(snapshot(11, 25, fault="F", flow_at=10))
    assert engine.incident["opening"]["flow"] is None


def test_legacy_incident_migrates_without_inventing_trigger_or_replaying():
    engine = Engine(settings())
    absolute_incident(engine)
    legacy = engine.serialize()
    legacy["version"] = 1
    del legacy["incident"]["opening"], legacy["incident"]["escalation"]
    legacy.pop("last_incident")
    legacy["acked"] = True
    legacy["snoozed_until"] = 20000
    restored = Engine(settings(), legacy)
    assert restored.incident["id"] == legacy["incident"]["id"]
    assert restored.incident["opened_at"] == 20
    assert restored.incident["opening"] is None
    assert restored.serialize()["acked"] is True
    assert restored.serialize()["version"] == 2
    first = restored.evaluate(snapshot(10000, 3))
    assert first.transition is None and not first.incident_confirmed
    assert restored.evaluate(snapshot(10001, 3)).transition is None
    assert restored.incident["opening"] is None
    assert restored.evaluate(snapshot(10021, 3)).incident_confirmed
    assert restored.incident["opening"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("flow", float("nan")),
        ("unit", "L/h"),
        ("decided_at", "2026"),
        ("flow_reported_at", None),
        ("reason", "all_filters_blocked"),
        ("pump_speed", 101),
        ("mode", {}),
        ("source_fingerprint", "x" * 200),
        ("version", 99),
    ],
)
def test_capture_corruption_is_not_silently_accepted(field, value):
    engine = Engine(settings())
    absolute_incident(engine)
    data = engine.serialize()
    data["incident"]["opening"][field] = value
    with pytest.raises(ValueError, match="incident|evidence|Incomplete"):
        Engine(settings(), data)


def add(history, when, flow=30, *, mode="heat", speed=55, pump="on", status="ok"):
    sample = snapshot(when, flow, mode=mode, speed=speed, pump=pump)
    sample = replace(sample, flow=replace(sample.flow, status=status))
    rules = settings()
    return history.add(sample, rules, Engine(rules).evaluate(sample))


def five_days(*, skip=None, zone="Europe/Paris", day="2026-10-25"):
    today = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo(zone))
    history = FlowHistory()
    for index, value in enumerate((24, 21, 18, 16, 13)):
        if index == skip:
            continue
        timestamp = (today - timedelta(days=4 - index) + timedelta(hours=12)).timestamp()
        add(history, timestamp, value - 1)
        # Irregular event bursts must not overweight this minute.
        for second in (1, 2, 4, 9, 15, 29, 50):
            assert not add(history, timestamp + second, value + 100)
        add(history, timestamp + 60, value + 1)
    now = (today + timedelta(hours=14)).timestamp()
    return history, now


def test_daily_statistics_cadence_common_context_and_exact_comparison():
    history, now = five_days()
    result = history.summary(now, "Europe/Paris", ANCHOR, 5)
    assert [row["median"] for row in result["days"]] == [24, 21, 18, 16, 13]
    assert [row["minimum"] for row in result["days"]] == [23, 20, 17, 15, 12]
    assert [row["samples"] for row in result["days"]] == [2] * 5
    assert result["change_pct"] == pytest.approx((13 / 24 - 1) * 100)
    assert result["consecutive_declines"] is None  # Sparse samples are not full-day evidence.
    assert result["first_date"] == "2026-10-21"
    assert result["last_date"] == "2026-10-25"
    assert result["days"][-1]["partial"]
    assert result["days"][-1]["expected_slots"] == 901  # DST fall-back + current minute.
    restored = FlowHistory(json.loads(json.dumps(history.export())))
    assert restored.summary(now, "Europe/Paris", ANCHOR, 5) == result
    history.export()["rows"][0][2] = 999
    assert history.rows[0]["flow"] == 23


def test_full_observed_days_support_sampled_median_declines_but_one_gap_revokes_it():
    history = FlowHistory()
    start = datetime(2026, 10, 21, tzinfo=UTC).timestamp()
    for index in range(4 * 1440 + 3):
        day = index // 1440
        add(history, start + index * 60, 30 - day)
    now = history.rows[-1]["at"]
    summary = history.summary(now, "UTC", ANCHOR, 5)
    assert summary["consecutive_declines"] == 4
    assert all(day["reliable"] for day in summary["days"])
    history.rows.pop(500)
    summary = history.summary(now, "UTC", ANCHOR, 5)
    assert summary["consecutive_declines"] is None
    assert summary["days"][0]["median"] == 30
    assert summary["change_pct"] == pytest.approx((26 / 30 - 1) * 100)


def test_one_sample_per_day_is_visible_without_percentage_or_conclusion():
    history = FlowHistory()
    add(history, 100000, 20)
    add(history, 186400, 10)
    result = history.summary(186500, "UTC", ANCHOR, 5)
    assert result["days"][-1]["median"] == 10
    assert result["change_pct"] is None
    assert result["consecutive_declines"] is None


def test_unit_conversion_and_anchor_tolerance_are_fixed_not_chained():
    rules = settings()
    history = FlowHistory()
    sample = snapshot(1000, 1200, speed=55)
    sample = replace(sample, flow=replace(sample.flow, unit="L/h"))
    history.add(sample, rules, Engine(rules).evaluate(sample))
    add(history, 1060, 19, speed=60)
    add(history, 1120, 1, speed=65)
    summary = history.summary(1200, "UTC", ANCHOR, 5)
    assert summary["days"][-1]["median"] == 19.5
    assert summary["days"][-1]["minimum"] == 19
    assert summary["days"][-1]["samples"] == 2


def test_legacy_storage_does_not_turn_old_trends_into_history():
    engine = Engine(settings())
    absolute_incident(engine)
    data = {
        "schema": 1,
        "engine": engine.serialize(),
        "delivery": {"version": 1},
        "trends": [{"flow": 99, "observed_at": "2026-01-01T00:00:00+00:00"}],
    }
    data["engine"]["version"] = 1
    data["engine"]["incident"].pop("opening")
    data["engine"]["incident"].pop("escalation")
    migrated = validate_storage(data)
    assert FlowHistory(migrated.get("flow_history")).rows == []
    assert Engine(settings(), migrated["engine"]).incident["opening"] is None


@pytest.mark.parametrize("day,seconds", [("2026-03-29", 23 * 3600), ("2026-10-25", 25 * 3600)])
def test_calendar_days_respect_dst_and_midnight_has_no_double_count(day, seconds):
    history, now = five_days(day=day)
    result = history.summary(now, "Europe/Paris", ANCHOR, 5)
    assert result["days"][-1]["day_seconds"] == seconds
    midnight = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo("Europe/Paris")).timestamp()
    only = FlowHistory()
    add(only, midnight, 10)
    days = only.summary(midnight, "Europe/Paris", ANCHOR, 5)["days"]
    assert days[-1]["samples"] == days[-1]["expected_slots"] == 1
    assert days[-2]["samples"] == 0


@pytest.mark.parametrize("skip", range(5))
def test_missing_day_is_not_zero_interpolated_or_a_five_day_decline(skip):
    history, now = five_days(skip=skip)
    result = history.summary(now, "Europe/Paris", ANCHOR, 5)
    assert result["days"][skip]["median"] is None
    assert result["days"][skip]["minimum"] is None
    assert result["consecutive_declines"] is None
    assert result["first_date"] != result["days"][skip]["date"]
    assert result["last_date"] != result["days"][skip]["date"]


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": "dhw"},
        {"mode": "defrost"},
        {"mode": "idle"},
        {"mode": "auto"},
        {"pump": "off"},
        {"pump": None},
        {"speed": 70},
        {"speed": None},
        {"status": "unavailable"},
        {"status": "stale"},
        {"status": "awaiting_fresh_report"},
        {"flow": -1},
        {"flow": float("nan")},
    ],
)
def test_context_and_invalid_sources_are_never_mixed_into_daily_medians(changes):
    history = FlowHistory()
    add(history, 100000, **changes)
    result = history.summary(100100, "UTC", ANCHOR, 5)
    assert sum(day["samples"] for day in result["days"]) == 0
    assert result["change_pct"] is None


def test_unmeasured_speed_is_explicit_and_never_matches_a_measured_speed():
    history = FlowHistory()
    add(history, 100000, speed=None)
    anchor = {**ANCHOR, "pump_speed": None, "speed_configured": False}
    assert history.summary(100100, "UTC", anchor, 5)["days"][-1]["samples"] == 1
    assert history.summary(100100, "UTC", ANCHOR, 5)["days"][-1]["samples"] == 0


def test_fresh_repeated_reports_do_not_extend_beyond_validity_or_credit_gaps():
    history = FlowHistory()
    rules = settings()
    engine = Engine(rules)
    sample = snapshot(1000, 20, speed=55)
    for now in (1000, 1060, 1120, 90000):
        current = replace(sample, now=now)
        history.add(current, rules, engine.evaluate(current))
    assert [row["quality"] for row in history.rows] == [
        "eligible",
        "eligible",
        "flow_stale",
        "flow_stale",
    ]
    assert sum(day["samples"] for day in history.summary(90001, "UTC", ANCHOR, 5)["days"]) == 2
    assert len(history.rows) == 4  # Nothing inserted for the unobserved gap.
    assert not history.add(replace(sample, now=2000), rules, engine.result)


def test_startup_and_bad_timestamps_are_not_eligible_history():
    rules = settings(startup_grace_s=180)
    sample = snapshot(1000, 20, speed=55)
    assert observation(sample, rules, Engine(rules).evaluate(sample))["quality"] == "startup_grace"
    sample = replace(sample, flow=replace(sample.flow, observed_at=1001))
    assert observation(sample, rules, Engine(rules).evaluate(sample))["quality"] != "eligible"


def test_zero_flow_is_real_not_missing_and_cannot_be_percentage_denominator():
    history = FlowHistory()
    for now in (100000, 100060, 186400, 186460):
        add(history, now, 0)
    result = history.summary(186500, "UTC", ANCHOR, 5)
    assert result["days"][-1]["median"] == 0
    assert result["change_pct"] is None


def test_history_age_volume_compact_storage_and_invalid_versions():
    history = FlowHistory()
    for index in range(MAX_SAMPLES + 20):
        add(history, index * 60 + 1000)
    assert len(history.rows) == MAX_SAMPLES
    assert history.rows[0]["at"] >= history.rows[-1]["at"] - RETENTION_SECONDS
    encoded = json.dumps(history.export())
    assert len(encoded) < 1_000_000
    restored = json.loads(encoded)
    restored["version"] = 99
    with pytest.raises(ValueError, match="schema"):
        FlowHistory(restored)
    for corrupted in ("extra", float("inf"), "private"):
        bad = history.export()
        bad["rows"][0][0] = corrupted
        with pytest.raises(ValueError):
            FlowHistory(bad)


def synthetic_report():
    """Public, explicitly synthetic example consumed by tests and local preview."""
    history, now = five_days()
    engine = Engine(settings())
    engine.evaluate(snapshot(now - 50, 9, speed=55))
    engine.evaluate(snapshot(now - 30, 8.75, speed=55))
    incident = engine.incident
    return {
        "name": "SYNTHETIC DEMONSTRATION / DÉMONSTRATION FICTIVE",
        "generated_at": datetime.fromtimestamp(now, UTC).isoformat(),
        "timezone": "Europe/Paris",
        "flow": 7.25,
        "flow_reported_at": datetime.fromtimestamp(now - 2, UTC).isoformat(),
        "minimum": 10,
        "state": "urgent",
        "reason_code": "absolute_low_flow",
        "incident": {
            **incident,
            "opened_at": datetime.fromtimestamp(incident["opened_at"], UTC).isoformat(),
        },
        "incident_capture": incident["opening"],
        "history": history.summary(now, "Europe/Paris", ANCHOR, 5),
        "telemetry": [
            {
                "name": "Synthetic flow / Débit fictif",
                "entity_id": "sensor.synthetic_flow",
                "value": 7.25,
                "unit": "L/min",
                "status": "ok",
                "observed_at": datetime.fromtimestamp(now - 2, UTC).isoformat(),
                "freshness_seconds": 2,
            },
            {
                "name": "Synthetic pump / Circulateur fictif",
                "entity_id": "sensor.synthetic_pump",
                "value": 55,
                "unit": "%",
                "status": "ok",
                "observed_at": datetime.fromtimestamp(now - 2, UTC).isoformat(),
                "freshness_seconds": 2,
            },
        ],
    }


@pytest.mark.parametrize("language", ("en", "fr", "es", "de"))
@pytest.mark.parametrize("kind", ("urgent", "watch", "reminder", "recovery", "test", "report"))
def test_actual_renderer_all_types_locales_evidence_escaping_and_email_safe_html(language, kind):
    data = synthetic_report()
    if kind == "watch":
        data["incident"]["severity"] = "watch"
    malicious = '<img src="https://example.com/tracker" onerror="bad()">'
    data["telemetry"].append({"name": malicious, "value": "<script>bad()</script>"})
    title, plain, html = render_report(data, kind, language)
    for content in (plain, unescape(html)):
        assert ("7.25" if language == "en" else "7,25") in content
        assert ("8.75" if language == "en" else "8,75") in content
        assert "2026-10-25" in content
        assert "Europe/Paris" in content
        assert "2026-10-21" in content
    assert (
        "[URG" not in title
        if kind in ("recovery", "test", "report", "watch")
        else "[URG" in title or "[DRINGEND]" in title
    )
    assert malicious not in html and malicious in unescape(html)
    assert "#FF3E17" in html and "#CC2C08" in html
    parser = Tags()
    parser.feed(html)
    assert not set(parser.tags) & {"img", "script", "canvas", "svg", "iframe", "button"}
    assert "var(" not in html
    assert not any(key in {"href", "src", "onerror"} for key, _ in parser.attributes)
    assert '<html lang="' + language + '">' in html
    assert all(len(values) == 4 and all(values) for values in _WORDS.values())


async def test_runtime_history_migration_reload_source_rename_and_source_change(
    hass, source_config, freezer
):
    entry = await setup_guard(hass, source_config)
    runtime = entry.runtime_data
    await reports(hass, source_config, freezer, seconds=61, flow="3")
    await reports(hass, source_config, freezer, seconds=61, flow="4")
    await settle(runtime)
    opening = runtime.engine.incident["opening"]
    assert opening["flow"] == 4
    assert opening["source_fingerprint"] == fingerprint(runtime.config)
    prior = runtime.flow_history.export()
    assert await hass.config_entries.async_reload(entry.entry_id)
    runtime = entry.runtime_data
    assert runtime.engine.incident["opening"] == opening
    assert runtime.flow_history.export() == prior
    assert not runtime.engine.result.incident_confirmed
    registry = er.async_get(hass)
    previous_fingerprint = fingerprint(runtime.config)
    registry.async_update_entity(
        source_config["flow_entity"], new_entity_id="sensor.renamed_synthetic_flow"
    )
    await hass.async_block_till_done()
    assert fingerprint(runtime.config) == previous_fingerprint
    assert runtime.flow_history.export() == prior
    source_config["flow_entity"] = "sensor.renamed_synthetic_flow"
    hass.states.async_set(source_config["flow_entity"], "4", {"unit_of_measurement": "L/min"})
    await reports(hass, source_config, freezer, seconds=61, flow="5")
    assert runtime.engine.incident["opening"] == opening
    hass.config_entries.async_update_entry(entry, options={**entry.options, "min_flow_l_min": 9})
    await hass.async_block_till_done()
    runtime = entry.runtime_data
    assert len(runtime.flow_history.rows) == 1
    assert runtime.flow_history.rows[0]["quality"] != "eligible"
    assert runtime.engine.incident["opening"] == opening
    assert "Sources or detection settings changed" in runtime.observation_report()["message"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert runtime.stopped and not runtime.unsubscribers


async def test_runtime_sampling_saves_in_batches_not_per_event_and_flushes_on_unload(
    hass, source_config, freezer
):
    entry = await setup_guard(hass, source_config)
    runtime = entry.runtime_data
    with patch.object(runtime.store, "async_save", wraps=runtime.store.async_save) as save:
        for _ in range(120):
            await reports(hass, source_config, freezer, seconds=1)
        assert len(runtime.flow_history.rows) <= 3
        assert save.call_count == 0
        await reports(hass, source_config, freezer, seconds=240)
        assert save.call_count == 1
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert save.call_count == 2
    assert len(runtime.flow_history.rows) <= 4


@pytest.mark.enable_socket
@pytest.mark.allow_hosts(["127.0.0.1", "::1"])
@pytest.mark.parametrize("language", ("en", "fr", "es", "de"))
async def test_http_report_real_capture_local_history_no_recorder_or_smtp(
    hass, hass_client, source_config, freezer, language
):
    source_config["language"] = language
    await hass.config.async_set_time_zone("Europe/Paris")
    assert await async_setup_component(hass, "api", {})
    assert "recorder" not in hass.config.components
    entry = await setup_guard(hass, source_config)
    await reports(hass, source_config, freezer, seconds=61, flow="3")
    await reports(hass, source_config, freezer, seconds=61, flow="4")
    await reports(hass, source_config, freezer, seconds=61, flow="5")
    runtime = entry.runtime_data
    before = deepcopy(runtime.export())
    validate_storage(before)
    client = await hass_client()
    with (
        patch.object(runtime, "_send", new_callable=AsyncMock) as send,
        patch(
            "homeassistant.components.recorder.history.get_significant_states",
            side_effect=RuntimeError("Recorder unavailable"),
        ) as query,
    ):
        response = await client.post(
            "/api/services/viessmann_guard/get_report?return_response",
            json={"entry_id": entry.entry_id},
        )
        assert response.status == 200
        body = (await response.json())["service_response"]
        assert set(body) == {"title", "message", "html"}
        assert "5 L/min" in body["message"] and "4 L/min" in body["message"]
        assert "Europe/Paris" in body["message"]
        assert '<html lang="' + language + '">' in body["html"]
        send.assert_not_awaited()
        query.assert_not_called()
    assert runtime.export() == before
    assert not runtime.config["emails_enabled"]
    assert runtime.engine.incident["opening"]["flow"] == 4
    assert runtime.engine.incident["opening"]["decided_at"] < dt_util.utcnow().timestamp()
