"""Native HA localization and presentation-only email preference changes."""

import asyncio
import json
import re
from copy import deepcopy
from html import escape, unescape
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations
from homeassistant.setup import async_setup_component
from test_integration import reports, settle, setup_guard, smtp_recipient
from test_no_smtp import assert_off

from custom_components.viessmann_guard.const import DOMAIN, LANGUAGES
from custom_components.viessmann_guard.email_layout import _WORDS
from custom_components.viessmann_guard.reasons import REASON_CODES, REASONS, describe_reason
from custom_components.viessmann_guard.report import _COPY, render_report, report_copy
from custom_components.viessmann_guard.runtime import configuration, fingerprint
from custom_components.viessmann_guard.validation import validate_emails

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN
HTTP = [
    pytest.mark.enable_socket,
    pytest.mark.allow_hosts(["127.0.0.1", "::1"]),
]


def flatten(value, path=""):
    return {
        leaf: text
        for key, item in value.items()
        for leaf, text in (
            flatten(item, f"{path}.{key}").items()
            if isinstance(item, dict)
            else [(f"{path}.{key}", item)]
        )
    }


@pytest.mark.parametrize("language", LANGUAGES)
async def test_complete_native_catalogs_loaded_by_home_assistant(hass, language):
    canonical = json.loads((ROOT / "strings.json").read_text())
    catalog = json.loads((ROOT / "translations" / f"{language}.json").read_text())
    expected, translated = flatten(canonical), flatten(catalog)
    assert translated.keys() == expected.keys()
    for key, value in translated.items():
        assert isinstance(value, str) and value
        assert set(re.findall(r"{(\w+)}", value)) == set(re.findall(r"{(\w+)}", expected[key]))
        assert "[%key:" not in value
    if language == "en":
        assert catalog == canonical
    for category in ("config", "options", "entity", "services", "exceptions", "selector"):
        loaded = await async_get_translations(hass, language, category, {DOMAIN})
        for key, value in flatten(catalog[category]).items():
            assert loaded[f"component.{DOMAIN}.{category}{key}"] == value
    assert set(_COPY[language]) == set(_COPY["en"])
    for code in set(REASON_CODES) | REASONS.keys():
        text = describe_reason(code, language)
        assert not text.endswith(f": {code}"), f"Untranslated {language} reason: {code}"
        if language != "en":
            assert text != describe_reason(code, "en")


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("kind", ["urgent", "watch", "reminder", "recovery", "test", "report"])
def test_every_report_kind_has_complete_localized_presentation(language, kind):
    malicious = '<img src=x onerror="steal()">&'
    snapshot = {
        "name": "Demo " + malicious,
        "generated_at": "2026-09-22T08:00:00+00:00",
        "state": "diagnostic_unavailable",
        "reason_code": "flow_stale",
        "flow": None,
        "thresholds": {
            "min_flow_l_min": None,
            "absolute_persistence_s": 180,
            "pump_tolerance_pct": 5,
            "running_modes": ["heating", "cooling"],
        },
        "incident": {"severity": "urgent", "acknowledged": False},
        "rule_codes": ["ha_report_time", "history_not_evidence", "inventory_scoped"],
        "limitation_codes": ["minimum_not_configured"],
        "telemetry": [
            {
                "name": malicious,
                "entity_id": "sensor.synthetic",
                "value": None,
                "unit": "L/min",
                "status": status,
            }
            for status in (
                "awaiting_fresh_report",
                "invalid",
                "invalid_or_unsupported_unit",
                "stale",
            )
        ],
    }
    title, text, html = render_report(snapshot, kind, language)
    copy = report_copy(language)
    assert copy[kind] in title
    assert "<img" not in html and escape(malicious) in html and malicious in text
    assert f'<html lang="{language}">' in html
    assert (
        ("[" + copy["urgent_prefix"] + "]") in title
        if kind in ("urgent", "reminder")
        else not title.startswith("[")
    )
    for content in (text, unescape(html)):
        if kind != "report":
            assert copy["diagnostic_unavailable"] in content
            assert describe_reason("flow_stale", language) in content
            assert _WORDS["email_advice"][LANGUAGES.index(language)] in content
            assert copy["thresholds"] not in content
            assert copy["limitations_text"] not in content
            continue
        for field in (
            "diagnostic_unavailable",
            "missing",
            "min_flow_l_min",
            "absolute_persistence_s",
            "running_modes",
            "awaiting_fresh_report",
            "invalid",
            "invalid_or_unsupported_unit",
            "possible_text",
            "alternatives_text",
            "advice_text",
            "limitations_text",
            "ha_report_time",
            "history_not_evidence",
        ):
            assert copy[field] in content
        assert f"180 {copy['seconds']}" in content
        assert f"5 {copy['percentage_points']}" in content
        assert "heating, cooling" in content
        assert "2026-09-22T08:00:00+00:00" in content
        assert describe_reason("flow_stale", language) in content
        assert describe_reason("minimum_not_configured", language) in content
    for key in ("absolute_persistence_s", "awaiting_fresh_report", "flow_stale"):
        assert key not in text
    if language != "en":
        for field in ("limitations_text", "ha_report_time", "history_not_evidence"):
            assert _COPY["en"][field] not in text
    assert "0 L/min" not in text


async def options(client, entry):
    response = await client.post(
        "/api/config/config_entries/options/flow", json={"handler": entry.entry_id}
    )
    assert response.status == 200
    url = f"/api/config/config_entries/options/flow/{(await response.json())['flow_id']}"
    response = await client.post(url, json={"next_step_id": "emails"})
    assert response.status == 200
    form = await response.json()
    field = next(item for item in form["data_schema"] if item["name"] == "language")
    assert field["selector"]["select"]["options"] == list(LANGUAGES)
    assert field["selector"]["select"]["translation_key"] == "email_language"
    assert field["default"] == entry.runtime_data.config["language"]
    return url


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.enable_socket
@pytest.mark.allow_hosts(["127.0.0.1", "::1"])
async def test_quick_http_default_and_locale_options_without_smtp(
    hass, hass_client, vicare_device, language
):
    hass.config.language = language
    vicare_device()
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()
    response = await client.post("/api/config/config_entries/flow", json={"handler": DOMAIN})
    assert response.status == 200
    form = await response.json()
    assert form["step_id"] == "confirm" and form["data_schema"] == []
    response = await client.post(f"/api/config/config_entries/flow/{form['flow_id']}", json={})
    assert response.status == 200 and (await response.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    assert entry.data["language"] == "en"
    assert_off(hass, entry)
    runtime = entry.runtime_data
    url = await options(client, entry)
    response = await client.post(url, json={"language": "not-a-language"})
    assert response.status == 400
    assert entry.runtime_data.config["language"] == "en"
    response = await client.post(url, json={"language": language})
    assert response.status == 200 and (await response.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.runtime_data is runtime
    assert entry.options["language"] == language
    assert f'<html lang="{language}">' in runtime.observation_report()["html"]
    assert_off(hass, entry)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.config["language"] == language
    assert_off(hass, entry)
    with pytest.raises(ServiceValidationError) as error:
        await entry.runtime_data.action("test_email")
    assert error.value.translation_key == "emails_disabled"


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.enable_socket
@pytest.mark.allow_hosts(["127.0.0.1", "::1"])
async def test_locale_only_http_options_preserve_permission_recipients_and_runtime(
    hass, hass_client, source_config, language, enabled
):
    _, recipient = smtp_recipient(hass)
    config = {**source_config, "recipients": [recipient], "emails_enabled": enabled}
    entry = await setup_guard(hass, config)
    second = await setup_guard(hass, {**source_config, "name": "Separate", "language": "fr"})
    runtime = entry.runtime_data
    before = deepcopy(runtime.export())
    fingerprint_before = fingerprint(runtime.config)
    registry = er.async_get(hass)
    switch = registry.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_emails_enabled")
    registry.async_update_entity(switch, name="User's own switch label")
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()
    url = await options(client, entry)
    with (
        patch.object(runtime, "evaluate", new_callable=AsyncMock) as evaluate,
        patch.object(runtime, "_send", new_callable=AsyncMock) as send,
    ):
        response = await client.post(url, json={"language": language})
        assert response.status == 200 and (await response.json())["type"] == "create_entry"
        await hass.async_block_till_done()
        evaluate.assert_not_awaited()
        send.assert_not_awaited()
    assert entry.runtime_data is runtime
    assert runtime.config["language"] == language
    assert runtime.config["recipients"] == [recipient]
    assert runtime.config["emails_enabled"] is enabled
    assert runtime.export() == before
    assert fingerprint(runtime.config) == fingerprint_before
    assert hass.states.get(switch).state == ("on" if enabled else "off")
    assert registry.async_get(switch).name == "User's own switch label"
    assert second.runtime_data.config["language"] == "fr"
    assert not hass.services.has_service("smtp", "send_message")
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.config["language"] == language
    assert entry.runtime_data.config["recipients"] == [recipient]
    assert entry.runtime_data.config["emails_enabled"] is enabled
    assert hass.states.get(switch).state == ("on" if enabled else "off")
    assert registry.async_get(switch).name == "User's own switch label"


@pytest.mark.enable_socket
@pytest.mark.allow_hosts(["127.0.0.1", "::1"])
async def test_retry_uses_new_locale_without_resending_successful_recipient(
    hass, hass_client, source_config, freezer
):
    _, first = smtp_recipient(hass)
    _, second = smtp_recipient(hass, "second@example.invalid", "Second")
    config = {**source_config, "recipients": [first, second], "emails_enabled": True}
    calls = []

    async def transport(call):
        calls.append(dict(call.data))
        if len(calls) == 2:
            raise ServiceValidationError("Synthetic rejection")

    hass.services.async_register("smtp", "send_message", transport)
    entry = await setup_guard(hass, config)
    runtime = entry.runtime_data
    for seconds in (1, 31):
        await reports(hass, config, freezer, seconds=seconds, flow="4")
        await settle(runtime)
    assert len(calls) == 2
    assert runtime.recipient_statuses[first]["status"] == "accepted"
    assert runtime.recipient_statuses[second]["status"] == "retry"
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()
    url = await options(client, entry)
    before = deepcopy(runtime.export())
    response = await client.post(url, json={"language": "de"})
    assert response.status == 200
    await hass.async_block_till_done()
    assert entry.runtime_data is runtime and runtime.export() == before
    assert len(calls) == 2
    await reports(hass, config, freezer, seconds=61, flow="4")
    await settle(runtime)
    assert [call["entity_id"] for call in calls] == [first, second, second]
    assert '<html lang="en">' in calls[0]["html"]
    assert '<html lang="de">' in calls[2]["html"]
    assert calls[2]["title"].startswith("[DRINGEND]")
    assert describe_reason("absolute_low_flow", "de") in calls[2]["message"]
    assert runtime.recipient_statuses[first]["attempts"] == 1
    assert runtime.recipient_statuses[second]["attempts"] == 2


async def test_locale_change_between_recipients_uses_current_locale(hass, source_config):
    _, first = smtp_recipient(hass)
    _, second = smtp_recipient(hass, "second@example.invalid", "Second")
    entry = await setup_guard(
        hass, {**source_config, "recipients": [first, second], "emails_enabled": True}
    )
    runtime = entry.runtime_data
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def transport(call):
        calls.append(dict(call.data))
        if len(calls) == 1:
            started.set()
            await release.wait()

    hass.services.async_register("smtp", "send_message", transport)
    sending = asyncio.create_task(runtime.action("test_email"))
    await started.wait()
    hass.config_entries.async_update_entry(entry, options={**entry.options, "language": "es"})
    await runtime.apply_options()
    release.set()
    await sending
    await settle(runtime)
    assert entry.runtime_data is runtime
    assert len(calls) == 2
    assert '<html lang="en">' in calls[0]["html"]
    assert '<html lang="es">' in calls[1]["html"]
    assert runtime.recipient_statuses[first]["test"]["attempts"] == 1
    assert runtime.recipient_statuses[second]["test"]["attempts"] == 1


@pytest.mark.parametrize(
    "stored,expected",
    [("fr", "fr"), ("fr-FR", "fr"), ("de_DE", "de"), ("unknown", "en"), (None, "en")],
)
async def test_legacy_locale_fallback_preserves_entry_data_and_permission(
    hass, source_config, stored, expected
):
    config = {**source_config}
    if stored is None:
        config.pop("language")
    else:
        config["language"] = stored
    entry = await setup_guard(hass, config)
    assert entry.state is ConfigEntryState.LOADED
    assert configuration(entry)["language"] == expected
    assert entry.data.get("language") == stored
    assert_off(hass, entry)
    assert f'<html lang="{expected}">' in entry.runtime_data.observation_report()["html"]
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert configuration(entry)["language"] == expected
    assert_off(hass, entry)


@pytest.mark.parametrize("invalid", ["it", "fr-FR", "", None])
def test_new_locale_choices_are_validated(hass, invalid):
    assert validate_emails(
        hass, {"emails_enabled": False, "recipients": [], "language": invalid, "reminder_hours": 24}
    ) == {"language": "invalid_language"}


async def test_backend_diagnostics_do_not_follow_email_language(hass, source_config, freezer):
    hass.config.language = "fr"
    entry = await setup_guard(hass, {**source_config, "language": "de"})
    await reports(hass, source_config, freezer, flow="4")
    await reports(hass, source_config, freezer, seconds=31, flow="4")
    await settle(entry.runtime_data)
    state_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_state")
    assert hass.states.get(state_id).attributes["reason_text"] == describe_reason(
        "absolute_low_flow", "fr"
    )
    assert (
        describe_reason("absolute_low_flow", "de")
        in entry.runtime_data.observation_report()["message"]
    )
    assert (
        report_copy("fr")["possible_text"]
        in hass.data["persistent_notification"][f"{DOMAIN}_{entry.entry_id}_incident"]["message"]
    )


@pytest.mark.parametrize("language", LANGUAGES)
async def test_runtime_action_errors_use_native_translation_keys(hass, source_config, language):
    hass.config.language = language
    entry = await setup_guard(hass, source_config)
    for action, key in (("acknowledge", "no_incident_ack"), ("snooze", "no_incident_snooze")):
        with pytest.raises(ServiceValidationError) as error:
            await entry.runtime_data.action(action)
        assert error.value.translation_domain == DOMAIN
        assert error.value.translation_key == key


@pytest.mark.parametrize("language", LANGUAGES)
def test_added_report_code_fields_do_not_stringify_private_containers(language):
    private = "PRIVATE_DO_NOT_RENDER"
    for codes in (None, {"secret": private}, [{"secret": private}]):
        result = render_report({"rule_codes": codes, "limitation_codes": codes}, "report", language)
        assert all(private not in value for value in result)
