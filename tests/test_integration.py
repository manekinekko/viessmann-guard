"""Exercise real HA config flows, registry, storage, platforms and SMTP action."""

import asyncio
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.viessmann_guard.const import DOMAIN, NUMERIC_RULES
from custom_components.viessmann_guard.telemetry import report_telemetry
from custom_components.viessmann_guard.validation import validate_recipients


async def setup_guard(hass, config):
    entry = MockConfigEntry(domain=DOMAIN, title=config["name"], data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def reports(hass, config, freezer, seconds=1, flow="12", mode="heating", pump="on"):
    freezer.tick(timedelta(seconds=seconds))
    for role, value in (("flow", flow), ("mode", mode), ("pump", pump)):
        entity_id = config[f"{role}_entity"]
        old = hass.states.get(entity_id)
        hass.states.async_set(entity_id, value, dict(old.attributes))
    await hass.async_block_till_done()


async def settle(runtime):
    await runtime.hass.async_block_till_done()
    if runtime._evaluate_task is not None:
        await runtime._evaluate_task
    if runtime._delivery_task is not None:
        await runtime._delivery_task


def smtp_recipient(hass, address="Person@example.invalid", name="Technician"):
    entry = MockConfigEntry(
        domain="smtp",
        title="Synthetic SMTP",
        subentries_data=[
            {"subentry_type": "recipient", "title": name, "unique_id": address, "data": {}},
        ],
    )
    entry.add_to_hass(hass)
    entity = er.async_get(hass).async_get_or_create(
        "notify",
        "smtp",
        f"{entry.entry_id}_{address}",
        config_entry=entry,
        suggested_object_id=f"synthetic_{name.lower()}",
        original_name=name,
    )
    hass.states.async_set(entity.entity_id, "2026-09-01T00:00:00+00:00")
    return entry, entity.entity_id


async def test_setup_entities_sources_same_value_freshness_and_unload(hass, source_config, freezer):
    entry = await setup_guard(hass, source_config)
    runtime = entry.runtime_data
    assert runtime.engine.result.state == "diagnostic_unavailable"
    before = hass.states.get(source_config["flow_entity"])
    changed = before.last_changed
    await reports(hass, source_config, freezer)
    await settle(runtime)
    state = hass.states.get(source_config["flow_entity"])
    assert state.last_changed == changed
    assert state.last_reported > changed
    assert runtime.engine.result.flow == 12
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) == 15
    assert len({e.unique_id for e in entities}) == 15
    assert hass.services.has_service(DOMAIN, "test_email")
    freezer.tick(timedelta(seconds=181))
    await runtime.evaluate()
    assert runtime.engine.result.state == "diagnostic_unavailable"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert runtime.stopped and not runtime.unsubscribers


async def test_flow_validates_source_units_and_explicit_rules(hass, source_config):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    sources = {
        k: v
        for k, v in source_config.items()
        if k.endswith("_entity") or k in ("name", "device_ids")
    }
    flow_id = source_config["flow_entity"]
    hass.states.async_set(flow_id, "12", {"unit_of_measurement": "gallons"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], sources)
    assert result["errors"]["flow_entity"] == "invalid_flow_unit"
    hass.states.async_set(flow_id, "720", {"unit_of_measurement": "L/h"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], sources)
    assert result["step_id"] == "rules"
    rules = {
        k: v
        for k, v in source_config.items()
        if k in NUMERIC_RULES
        or k.endswith("_values")
        or k.endswith("_modes")
        or k == "min_flow_l_min"
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**rules, "running_modes": []}
    )
    assert result["errors"]["running_modes"] == "required_modes"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], rules)
    assert result["step_id"] == "emails"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "emails_enabled": False,
            "recipients": [],
            "reminder_hours": 24,
            "watch_email": False,
            "language": "fr",
        },
    )
    assert result["step_id"] == "report"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"report_entities": [], "report_exclude": []}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["emails_enabled"] is False


async def test_email_switch_options_sync_and_off_blocks_test(hass, source_config):
    _, target = smtp_recipient(hass)
    source_config["recipients"] = [target]
    entry = await setup_guard(hass, source_config)
    runtime = entry.runtime_data
    with pytest.raises(ServiceValidationError, match="disabled"):
        await runtime.action("test_email")
    switch = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"{entry.entry_id}_emails_enabled"
    )
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    await hass.async_block_till_done()
    assert entry.options["emails_enabled"] is True
    assert runtime.config["emails_enabled"] is True
    assert hass.states.get(switch).state == "on"
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "emails"}
    )
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "emails_enabled": False,
            "recipients": [target],
            "reminder_hours": 24,
            "watch_email": False,
            "language": "en",
        },
    )
    assert flow["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["emails_enabled"] is False
    assert hass.states.get(switch).state == "off"


async def test_multiple_instances_and_services(hass, source_config):
    first = await setup_guard(hass, source_config)
    second = await setup_guard(hass, {**source_config, "name": "Second Guard"})
    registry = er.async_get(hass)
    ids1 = {e.unique_id for e in er.async_entries_for_config_entry(registry, first.entry_id)}
    ids2 = {e.unique_id for e in er.async_entries_for_config_entry(registry, second.entry_id)}
    assert not ids1 & ids2
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "test_email", {"entry_id": "missing"}, blocking=True)
    await hass.services.async_call(
        DOMAIN, "record_cleaning", {"entry_id": first.entry_id}, blocking=True
    )
    assert first.runtime_data.engine.result.last_cleaned is not None
    assert second.runtime_data.engine.result.last_cleaned is None


async def test_smtp_ownership_and_identity_dedup(hass):
    _, first = smtp_recipient(hass)
    _, duplicate = smtp_recipient(hass, "Person@EXAMPLE.invalid", "Duplicate")
    with pytest.raises(ValueError, match="duplicate_recipient"):
        validate_recipients(hass, [first, duplicate])
    with pytest.raises(ValueError, match="duplicate_recipient"):
        validate_recipients(hass, [first, first])
    _, different_local = smtp_recipient(hass, "person@example.invalid", "Case")
    assert validate_recipients(hass, [first, different_local]) == [first, different_local]
    malicious = er.async_get(hass).async_get_or_create("notify", "mobile_app", "fake")
    with pytest.raises(ValueError, match="invalid_smtp_recipient"):
        validate_recipients(hass, [malicious.entity_id])


async def test_native_smtp_schema_and_transport_are_mocked(hass, source_config, freezer):
    """Load the actual SMTP entity/action and intercept only its network client."""
    smtp = MockConfigEntry(
        domain="smtp",
        title="Synthetic SMTP",
        data={
            "sender": "sender@example.invalid",
            "server": "smtp.example.invalid",
            "port": 587,
            "encryption": "starttls",
            "verify_ssl": True,
        },
        options={"timeout": 5},
        subentries_data=[
            {
                "subentry_type": "recipient",
                "title": "Technician",
                "unique_id": "recipient@example.invalid",
                "data": {},
            }
        ],
    )
    smtp.add_to_hass(hass)
    connection = MagicMock()
    with patch("homeassistant.components.smtp.helpers.SmtpClient.connect", return_value=connection):
        assert await hass.config_entries.async_setup(smtp.entry_id)
        await hass.async_block_till_done()
        target = er.async_get(hass).async_get_entity_id(
            "notify", "smtp", f"{smtp.entry_id}_recipient@example.invalid"
        )
        assert target
        source_config["recipients"] = [target]
        guard = await setup_guard(hass, source_config)
        await reports(hass, source_config, freezer)
        await settle(guard.runtime_data)
        await guard.runtime_data.set_emails(True)
        await guard.runtime_data.action("test_email")
        assert connection.sendmail.call_count == 1
        sender, recipient, body = connection.sendmail.call_args.args
        assert sender == "sender@example.invalid" and recipient == "recipient@example.invalid"
        assert "text/plain" in body and "text/html" in body
        assert "X-Priority:" not in body
        assert guard.runtime_data.recipient_statuses[target]["test"]["status"] == "accepted"


async def test_safe_report_inventory(hass, source_config, freezer):
    entry = await setup_guard(hass, source_config)
    await reports(hass, source_config, freezer)
    device_id = source_config["device_ids"][0]
    registry = er.async_get(hass)
    origin = hass.config_entries.async_entries("vicare")[0]
    for name, device, value in (
        ("token", device_id, "secret"),
        ("serial", device_id, "123456"),
        ("unrelated_energy", None, "900"),
    ):
        item = registry.async_get_or_create(
            "sensor",
            "vicare",
            name,
            config_entry=origin,
            device_id=device,
            suggested_object_id=name,
            original_name=name,
        )
        hass.states.async_set(
            item.entity_id,
            value,
            {"device_class": "energy", "unit_of_measurement": "kWh", "password": "not-for-reports"},
        )
    rows, _ = report_telemetry(
        hass, source_config, dt_util.utcnow().timestamp(), entry.runtime_data.started_at
    )
    text = str(rows)
    assert "secret" not in text and "123456" not in text and "unrelated_energy" not in text
    assert "password" not in text
    assert any(row["unit"] == "L/min" and row["value"] == 12 for row in rows)


async def test_missing_smtp_is_visible_without_blocking_monitoring(hass, source_config):
    _, target = smtp_recipient(hass)
    source_config.update(recipients=[target], emails_enabled=True)
    entry = await setup_guard(hass, source_config)
    with pytest.raises(ServiceValidationError):
        await entry.runtime_data.action("test_email")
    assert entry.runtime_data.recipient_statuses[target]["test"]["status"] == "retry"
    assert entry.runtime_data.engine.result.state == "diagnostic_unavailable"


async def test_off_during_dispatch_blocks_next_recipient_and_retry(hass, source_config, freezer):
    _, first = smtp_recipient(hass)
    _, second = smtp_recipient(hass, "second@example.invalid", "Second")
    source_config.update(recipients=[first, second], emails_enabled=True)
    entry = await setup_guard(hass, source_config)
    runtime = entry.runtime_data
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def transport(call):
        calls.append(call.data["entity_id"])
        started.set()
        await release.wait()

    hass.services.async_register("smtp", "send_message", transport)
    sending = asyncio.create_task(runtime.action("test_email"))
    await started.wait()
    await runtime.set_emails(False)
    release.set()
    await sending
    assert calls == [first]
    freezer.tick(timedelta(seconds=1000))
    await runtime.delivery.dispatch(dt_util.utcnow().timestamp())
    assert calls == [first]
    await runtime.set_emails(True)
    await settle(runtime)
    assert calls == [first]


async def test_incident_restart_no_duplicate_and_no_downtime_recovery(hass, source_config, freezer):
    _, recipient = smtp_recipient(hass)
    source_config.update(recipients=[recipient], emails_enabled=True)
    calls = []

    async def transport(call):
        calls.append(call.data)

    hass.services.async_register("smtp", "send_message", transport)
    entry = await setup_guard(hass, source_config)
    runtime = entry.runtime_data
    await reports(hass, source_config, freezer, flow="4")
    await settle(runtime)
    await reports(hass, source_config, freezer, seconds=31, flow="4")
    await settle(runtime)
    assert runtime.engine.result.incident_id
    assert len(calls) == 1 and calls[0]["title"].startswith("[URGENT]")
    incident_id = runtime.engine.result.incident_id
    await runtime.action("acknowledge")
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.tick(timedelta(days=2))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry.runtime_data
    assert runtime.engine.result.incident_id == incident_id
    assert runtime.engine.result.acked
    assert not runtime.engine.result.incident_confirmed
    assert len(calls) == 1
    await reports(hass, source_config, freezer, flow="4")
    await settle(runtime)
    await reports(hass, source_config, freezer, seconds=31, flow="4")
    await settle(runtime)
    assert len(calls) == 1
    await reports(hass, source_config, freezer, flow="12")
    await settle(runtime)
    assert runtime.engine.result.incident_id == incident_id
    await reports(hass, source_config, freezer, seconds=31, flow="12")
    await settle(runtime)
    assert runtime.engine.result.incident_id is None
    assert len(calls) == 2


async def test_disabled_incident_no_backlog_replay(hass, source_config, freezer):
    _, recipient = smtp_recipient(hass)
    source_config["recipients"] = [recipient]
    calls = []

    async def transport(call):
        calls.append(call.data)

    hass.services.async_register("smtp", "send_message", transport)
    entry = await setup_guard(hass, source_config)
    runtime = entry.runtime_data
    await reports(hass, source_config, freezer, flow="4")
    await settle(runtime)
    await reports(hass, source_config, freezer, seconds=31, flow="4")
    await settle(runtime)
    assert runtime.engine.result.incident_id
    assert not calls
    await reports(hass, source_config, freezer, flow="12")
    await settle(runtime)
    await reports(hass, source_config, freezer, seconds=31, flow="12")
    await settle(runtime)
    assert runtime.engine.result.incident_id is None
    await runtime.set_emails(True)
    await settle(runtime)
    assert not calls
    await runtime.set_emails(False)
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.tick(timedelta(seconds=1))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not entry.runtime_data.config["emails_enabled"]
    switch = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"{entry.entry_id}_emails_enabled"
    )
    assert hass.states.get(switch).state == "off"


async def test_timer_marks_sources_stale_without_state_changes(hass, source_config, freezer):
    entry = await setup_guard(hass, source_config)
    await reports(hass, source_config, freezer)
    await settle(entry.runtime_data)
    assert entry.runtime_data.engine.result.flow == 12
    freezer.tick(timedelta(seconds=200))
    async_fire_time_changed(hass, dt_util.utcnow())
    await settle(entry.runtime_data)
    assert entry.runtime_data.engine.result.state == "diagnostic_unavailable"


async def test_options_can_remove_optional_source(hass, source_config):
    entry = await setup_guard(hass, source_config)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "sources"}
    )
    sources = {
        k: v
        for k, v in source_config.items()
        if (k.endswith("_entity") and k != "pump_entity") or k in ("name", "device_ids")
    }
    result = await hass.config_entries.options.async_configure(flow["flow_id"], sources)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.config["pump_entity"] is None


async def test_corrupt_storage_is_not_silently_reset(hass, source_config, hass_storage):
    entry = MockConfigEntry(domain=DOMAIN, title="Demo Guard", data=source_config)
    entry.add_to_hass(hass)
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {"schema": 999, "engine": {}, "delivery": {}},
    }
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_report_rejects_unrelated_selected_entity(hass, source_config):
    origin = MockConfigEntry(domain="test")
    origin.add_to_hass(hass)
    other = dr.async_get(hass).async_get_or_create(
        config_entry_id=origin.entry_id, identifiers={("test", "unrelated")}
    )
    entity = er.async_get(hass).async_get_or_create(
        "sensor", "test", "private", config_entry=origin, device_id=other.id
    )
    hass.states.async_set(entity.entity_id, "123", {"device_class": "temperature"})
    entry = await setup_guard(hass, source_config)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "report"}
    )
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "report_entities": [entity.entity_id],
            "report_exclude": [],
        },
    )
    assert flow["errors"] == {"report_entities": "invalid_report_entity"}


async def test_recipients_changed_during_incident_do_not_resend_successes(
    hass, source_config, freezer
):
    _, first = smtp_recipient(hass)
    _, removed = smtp_recipient(hass, "removed@example.invalid", "Removed")
    _, added = smtp_recipient(hass, "added@example.invalid", "Added")
    config = {**source_config, "recipients": [first, removed], "emails_enabled": True}
    calls = []

    async def transport(call):
        target = call.data["entity_id"]
        calls.append(target)
        if target == removed:
            raise ServiceValidationError("Synthetic SMTP failure")

    hass.services.async_register("smtp", "send_message", transport)
    entry = await setup_guard(hass, config)
    for seconds in (1, 31):
        await reports(hass, config, freezer, seconds=seconds, flow="4")
        await settle(entry.runtime_data)
    assert calls == [first, removed]
    changed = {**config, "recipients": [first, added]}
    entry.runtime_data.prepare_options(changed)
    hass.config_entries.async_update_entry(entry, options=changed)
    await hass.async_block_till_done()
    for seconds in (1, 31):
        await reports(hass, config, freezer, seconds=seconds, flow="4")
        await settle(entry.runtime_data)
    assert calls == [first, removed, added]
    assert removed not in entry.runtime_data.recipient_statuses


async def test_manual_report_does_not_replace_incident_retry(hass, source_config, freezer):
    _, target = smtp_recipient(hass)
    config = {**source_config, "recipients": [target], "emails_enabled": True}
    titles = []

    async def transport(call):
        title = call.data["title"]
        titles.append(title)
        if len(titles) == 1:
            raise ServiceValidationError("Synthetic transient rejection")

    hass.services.async_register("smtp", "send_message", transport)
    entry = await setup_guard(hass, config)
    for seconds in (1, 31):
        await reports(hass, config, freezer, seconds=seconds, flow="4")
        await settle(entry.runtime_data)
    assert len(titles) == 1
    await entry.runtime_data.action("test_email")
    assert len(titles) == 2
    assert entry.runtime_data.recipient_statuses[target]["status"] == "retry"
    assert entry.runtime_data.recipient_statuses[target]["test"]["status"] == "accepted"
    await reports(hass, config, freezer, seconds=61, flow="4")
    await settle(entry.runtime_data)
    assert len(titles) == 3
    assert titles[0] == titles[2]


async def test_dispatch_revalidates_telemetry_between_recipients(hass, source_config, freezer):
    _, first = smtp_recipient(hass)
    _, second = smtp_recipient(hass, "second@example.invalid", "Second")
    config = {**source_config, "recipients": [first, second], "emails_enabled": True}
    calls = []

    async def transport(call):
        calls.append(call.data["entity_id"])
        if len(calls) == 1:
            # Simulate a long first SMTP call without fresh PAC reports.
            freezer.tick(timedelta(seconds=181))

    hass.services.async_register("smtp", "send_message", transport)
    entry = await setup_guard(hass, config)
    for seconds in (1, 31):
        await reports(hass, config, freezer, seconds=seconds, flow="4")
        await settle(entry.runtime_data)
    assert calls == [first]
    assert entry.runtime_data.engine.result.state == "diagnostic_unavailable"


async def test_native_buttons_and_reminder_snooze_expiry(hass, source_config, freezer):
    _, recipient = smtp_recipient(hass)
    config = {
        **source_config,
        "recipients": [recipient],
        "emails_enabled": True,
        "reminder_hours": 1,
    }
    titles = []

    async def transport(call):
        titles.append(call.data["title"])

    hass.services.async_register("smtp", "send_message", transport)
    entry = await setup_guard(hass, config)
    runtime = entry.runtime_data
    for seconds in (1, 31):
        await reports(hass, config, freezer, seconds=seconds, flow="4")
        await settle(runtime)
    assert len(titles) == 1
    for action in ("acknowledge", "record_cleaning"):
        entity_id = er.async_get(hass).async_get_entity_id(
            "button", DOMAIN, f"{entry.entry_id}_{action}"
        )
        await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
    assert runtime.engine.result.incident_id
    assert runtime.engine.result.acked
    assert runtime.engine.result.last_cleaned
    await hass.services.async_call(
        DOMAIN, "snooze", {"entry_id": entry.entry_id, "hours": 2}, blocking=True
    )
    for seconds in (3601, 31):
        await reports(hass, config, freezer, seconds=seconds, flow="4")
        await settle(runtime)
    assert len(titles) == 1
    for seconds in (3601, 31):
        await reports(hass, config, freezer, seconds=seconds, flow="4")
        await settle(runtime)
    assert len(titles) == 2 and titles[1].startswith("[URGENT]")


async def test_off_before_retry_stops_both_outboxes(hass, source_config, freezer):
    _, recipient = smtp_recipient(hass)
    config = {**source_config, "recipients": [recipient], "emails_enabled": True}
    calls = []

    async def transport(call):
        calls.append(call.data)
        raise ServiceValidationError("Synthetic failure")

    hass.services.async_register("smtp", "send_message", transport)
    entry = await setup_guard(hass, config)
    for seconds in (1, 31):
        await reports(hass, config, freezer, seconds=seconds, flow="4")
        await settle(entry.runtime_data)
    with pytest.raises(ServiceValidationError):
        await entry.runtime_data.action("test_email")
    assert len(calls) == 2
    switch = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"{entry.entry_id}_emails_enabled"
    )
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    await reports(hass, config, freezer, seconds=61, flow="4")
    await settle(entry.runtime_data)
    assert len(calls) == 2
    assert entry.options["emails_enabled"] is False


async def test_urgent_escalation_is_not_hidden_by_reminder_snooze(hass, source_config, freezer):
    _, recipient = smtp_recipient(hass)
    config = {
        **source_config,
        "recipients": [recipient],
        "emails_enabled": True,
        "watch_email": True,
        "calibration_samples": 3,
        "calibration_duration_s": 60,
        "relative_persistence_s": 30,
    }
    titles = []

    async def transport(call):
        titles.append(call.data["title"])

    hass.services.async_register("smtp", "send_message", transport)
    entry = await setup_guard(hass, config)
    runtime = entry.runtime_data
    await reports(hass, config, freezer)
    await settle(runtime)
    await runtime.action("confirm_calibration", confirmed=True)
    for _ in range(3):
        await reports(hass, config, freezer, seconds=30)
        await settle(runtime)
    for seconds in (1, 31):
        await reports(hass, config, freezer, seconds=seconds, flow="9")
        await settle(runtime)
    assert runtime.engine.result.state == "watch"
    assert len(titles) == 1
    await runtime.action("snooze")
    for seconds in (1, 31):
        await reports(hass, config, freezer, seconds=seconds, flow="4")
        await settle(runtime)
    assert len(titles) == 2 and titles[-1].startswith("[URGENT]")


async def test_missing_speed_unit_is_rejected_after_setup(hass, source_config, freezer):
    origin = hass.config_entries.async_entries("vicare")[0]
    entity = er.async_get(hass).async_get_or_create(
        "sensor",
        "vicare",
        "pump_speed",
        config_entry=origin,
        device_id=source_config["device_ids"][0],
        suggested_object_id="synthetic_speed",
    )
    hass.states.async_set(entity.entity_id, "80", {"unit_of_measurement": "%"})
    config = {**source_config, "pump_speed_entity": entity.entity_id}
    entry = await setup_guard(hass, config)
    await reports(hass, config, freezer)
    hass.states.async_set(entity.entity_id, "80", {})
    await settle(entry.runtime_data)
    assert entry.runtime_data.engine.result.state == "diagnostic_unavailable"
    assert entry.runtime_data.engine.result.reason == "pump_speed_unavailable"


async def test_options_off_applies_even_if_saved_recipient_was_removed(hass, source_config):
    _, recipient = smtp_recipient(hass)
    entry = await setup_guard(
        hass, {**source_config, "emails_enabled": True, "recipients": [recipient]}
    )
    er.async_get(hass).async_remove(recipient)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "emails"}
    )
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "emails_enabled": False,
            "recipients": [recipient],
            "reminder_hours": 24,
            "watch_email": False,
            "language": "en",
        },
    )
    assert flow["errors"] == {"recipients": "invalid_smtp_recipient"}
    assert entry.options["emails_enabled"] is False
    assert entry.runtime_data.config["emails_enabled"] is False
