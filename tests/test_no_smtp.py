"""Exercise no-SMTP onboarding and email defaults through Home Assistant HTTP."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from test_integration import setup_guard

from custom_components.viessmann_guard.const import (
    DOMAIN,
    EMAIL_DEFAULTS,
    LIST_SETTINGS,
    NUMERIC_RULES,
)
from custom_components.viessmann_guard.discovery import discover

pytestmark = [
    pytest.mark.enable_socket,
    pytest.mark.allow_hosts(["127.0.0.1", "::1"]),
]


def assert_no_smtp(hass):
    assert not hass.config_entries.async_entries("smtp")
    assert not any(entity.platform == "smtp" for entity in er.async_get(hass).entities.values())
    assert not hass.services.has_service("smtp", "send_message")


def assert_off(hass, entry):
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.config["emails_enabled"] is False
    assert entry.runtime_data.config["recipients"] == []
    switch_id = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"{entry.entry_id}_emails_enabled"
    )
    assert hass.states.get(switch_id).state == "off"
    assert_no_smtp(hass)
    return switch_id


async def email_options(client, entry):
    response = await client.post(
        "/api/config/config_entries/options/flow", json={"handler": entry.entry_id}
    )
    assert response.status == 200
    url = f"/api/config/config_entries/options/flow/{(await response.json())['flow_id']}"
    response = await client.post(url, json={"next_step_id": "emails"})
    assert response.status == 200
    form = await response.json()
    assert form["step_id"] == "emails"
    field = next(field for field in form["data_schema"] if field["name"] == "emails_enabled")
    assert field["default"] is False
    return url


@pytest.mark.parametrize(
    "payload", [{}, {"emails_enabled": False}, {"emails_enabled": False, "recipients": []}]
)
async def test_quick_create_and_email_options_without_smtp(
    hass, hass_client, vicare_device, payload
):
    vicare_device()
    defaults_before = deepcopy(EMAIL_DEFAULTS)
    assert_no_smtp(hass)
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()
    response = await client.post("/api/config/config_entries/flow", json={"handler": DOMAIN})
    assert response.status == 200
    form = await response.json()
    assert form["step_id"] == "confirm"
    assert form["data_schema"] == []
    assert "Emails stay OFF" in form["description_placeholders"]["summary"]
    response = await client.post(f"/api/config/config_entries/flow/{form['flow_id']}", json={})
    assert response.status == 200
    assert (await response.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    assert_off(hass, entry)
    url = await email_options(client, entry)
    response = await client.post(url, json=payload)
    assert response.status == 200
    assert (await response.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["emails_enabled"] is False
    assert_off(hass, entry)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert_off(hass, entry)
    assert EMAIL_DEFAULTS == defaults_before


@pytest.mark.parametrize("automatic", [False, True])
@pytest.mark.parametrize("explicit_false", [False, True])
async def test_legacy_entry_absent_or_false_email_setting_and_omitted_options(
    hass, hass_client, source_config, vicare_device, automatic, explicit_false
):
    if automatic:
        vicare_device()
        (candidate,) = discover(hass)
        config = candidate.config
    else:
        config = dict(source_config)
    if not explicit_false:
        config.pop("emails_enabled")
        config.pop("recipients")
    assert await async_setup_component(hass, "config", {})
    entry = await setup_guard(hass, config)
    assert_off(hass, entry)
    client = await hass_client()
    url = await email_options(client, entry)
    response = await client.post(url, json={})
    assert response.status == 200
    assert (await response.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert_off(hass, entry)
    assert entry.options["emails_enabled"] is False


@pytest.mark.parametrize("payload", [{}, {"emails_enabled": False, "recipients": []}])
async def test_manual_http_creation_without_smtp_and_omitted_defaults(
    hass, hass_client, source_config, payload
):
    assert_no_smtp(hass)
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()
    response = await client.post("/api/config/config_entries/flow", json={"handler": DOMAIN})
    assert response.status == 200
    form = await response.json()
    assert form["type"] == "menu"
    url = f"/api/config/config_entries/flow/{form['flow_id']}"
    response = await client.post(url, json={"next_step_id": "manual"})
    assert response.status == 200
    assert (await response.json())["step_id"] == "manual"
    sources = {
        key: value
        for key, value in source_config.items()
        if key in ("name", "device_ids") or key.endswith("_entity")
    }
    response = await client.post(url, json=sources)
    assert response.status == 200
    assert (await response.json())["step_id"] == "rules"
    rules = {key: source_config[key] for key in ("min_flow_l_min", *NUMERIC_RULES, *LIST_SETTINGS)}
    response = await client.post(url, json=rules)
    assert response.status == 200
    assert (await response.json())["step_id"] == "emails"
    response = await client.post(url, json=payload)
    assert response.status == 200
    assert (await response.json())["step_id"] == "report"
    response = await client.post(url, json={})
    assert response.status == 200
    assert (await response.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    assert entry.data["emails_enabled"] is False
    assert_off(hass, entry)


async def test_open_email_forms_do_not_reuse_another_forms_invalid_on_submission(
    hass, hass_client, vicare_device
):
    vicare_device()
    (candidate,) = discover(hass)
    assert await async_setup_component(hass, "config", {})
    entry = await setup_guard(hass, candidate.config)
    client = await hass_client()
    original = await email_options(client, entry)
    newer = await email_options(client, entry)
    response = await client.post(newer, json={"emails_enabled": True})
    assert response.status == 200
    assert (await response.json())["errors"] == {"recipients": "required_recipient"}
    response = await client.post(original, json={})
    assert response.status == 200
    assert (await response.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert_off(hass, entry)
    await client.delete(newer)


async def test_on_without_recipient_is_rejected_but_off_and_disabled_test_are_distinct(
    hass, hass_client, vicare_device
):
    vicare_device()
    (candidate,) = discover(hass)
    assert await async_setup_component(hass, "config", {})
    entry = await setup_guard(hass, candidate.config)
    switch_id = assert_off(hass, entry)
    client = await hass_client()
    url = await email_options(client, entry)
    response = await client.post(url, json={"emails_enabled": True})
    assert response.status == 200
    assert (await response.json())["errors"] == {"recipients": "required_recipient"}
    assert_off(hass, entry)
    response = await client.post(url, json={})
    assert response.status == 200
    assert (await response.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert_off(hass, entry)
    runtime = entry.runtime_data
    with patch.object(runtime, "_send", new_callable=AsyncMock) as send:
        with pytest.raises(ServiceValidationError) as disabled:
            await hass.services.async_call(
                DOMAIN, "test_email", {"entry_id": entry.entry_id}, blocking=True
            )
        assert disabled.value.translation_key == "emails_disabled"
        with pytest.raises(ServiceValidationError) as missing:
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": switch_id}, blocking=True
            )
        assert missing.value.translation_key == "required_recipient"
        assert str(missing.value) == (
            "Select at least one valid native SMTP recipient before enabling or testing emails"
        )
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": switch_id}, blocking=True
        )
        await hass.async_block_till_done()
        send.assert_not_awaited()
    assert_off(hass, entry)
