"""Installation and native dashboard contracts, not frontend stubs."""

import json
import re
from pathlib import Path

import pytest
import yaml
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from test_integration import setup_guard

from custom_components.viessmann_guard.button import ACTIONS
from custom_components.viessmann_guard.config_flow import (
    emails_schema,
    report_schema,
    rules_schema,
    sources_schema,
)
from custom_components.viessmann_guard.const import DOMAIN, LIST_SETTINGS, NUMERIC_RULES
from custom_components.viessmann_guard.reasons import REASON_CODES
from custom_components.viessmann_guard.sensor import KEYS
from custom_components.viessmann_guard.validation import (
    validate_emails,
    validate_rules,
    validate_sources,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.enable_socket
@pytest.mark.allow_hosts(["127.0.0.1", "::1"])
async def test_add_integration_catalog_exposes_guard(hass, hass_ws_client):
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "integration/descriptions"})
    message = await client.receive_json()
    assert message["success"]
    catalog = message["result"]["custom"]
    assert DOMAIN in catalog["integration"]
    assert DOMAIN not in catalog["helper"]
    assert catalog["integration"][DOMAIN]["config_flow"] is True
    assert catalog["integration"][DOMAIN]["name"] == "Viessmann Guard"


@pytest.mark.enable_socket
@pytest.mark.allow_hosts(["127.0.0.1", "::1"])
async def test_ui_config_flow_and_options_serialize_all_forms(hass, hass_client, source_config):
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()
    response = await client.get("/api/config/config_entries/flow_handlers")
    assert response.status == 200
    assert DOMAIN in await response.json()
    response = await client.post("/api/config/config_entries/flow", json={"handler": DOMAIN})
    assert response.status == 200
    result = await response.json()
    assert result["type"] == "menu"
    assert result["step_id"] == "user"
    flow_id = result["flow_id"]
    response = await client.post(
        f"/api/config/config_entries/flow/{flow_id}", json={"next_step_id": "manual"}
    )
    assert response.status == 200
    assert (await response.json())["step_id"] == "manual"
    sources = {
        key: value
        for key, value in source_config.items()
        if key in {"name", "device_ids"} or key.endswith("_entity")
    }
    response = await client.post(
        f"/api/config/config_entries/flow/{flow_id}",
        json={**sources, "name": "Name\rHeader"},
    )
    assert response.status == 200
    assert (await response.json())["errors"] == {"name": "invalid_name"}
    response = await client.post(f"/api/config/config_entries/flow/{flow_id}", json=sources)
    assert response.status == 200
    result = await response.json()
    assert result["type"] == "form"
    assert result["step_id"] == "rules"
    assert any(field["name"] == "min_flow_l_min" for field in result["data_schema"])
    rules = {key: source_config[key] for key in ("min_flow_l_min", *NUMERIC_RULES, *LIST_SETTINGS)}
    response = await client.post(
        f"/api/config/config_entries/flow/{flow_id}",
        json={**rules, "min_flow_l_min": 0},
    )
    assert response.status == 400
    response = await client.post(f"/api/config/config_entries/flow/{flow_id}", json=rules)
    assert response.status == 200
    result = await response.json()
    assert result["step_id"] == "emails"
    emails = {
        "emails_enabled": False,
        "recipients": [],
        "reminder_hours": 24,
        "watch_email": False,
        "language": "en",
    }
    response = await client.post(f"/api/config/config_entries/flow/{flow_id}", json=emails)
    assert response.status == 200
    result = await response.json()
    assert result["step_id"] == "report"
    response = await client.post(
        f"/api/config/config_entries/flow/{flow_id}",
        json={"report_entities": [], "report_exclude": []},
    )
    assert response.status == 200
    assert (await response.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data["emails_enabled"] is False
    assert isinstance(entry.data["calibration_samples"], int)
    for step in ("minimum", "sources", "rules", "emails", "report"):
        response = await client.post(
            "/api/config/config_entries/options/flow", json={"handler": entry.entry_id}
        )
        assert response.status == 200
        menu = await response.json()
        assert menu["type"] == "menu"
        option_id = menu["flow_id"]
        response = await client.post(
            f"/api/config/config_entries/options/flow/{option_id}",
            json={"next_step_id": step},
        )
        assert response.status == 200
        result = await response.json()
        assert result["type"] == "form"
        assert result["step_id"] == step
        assert result["data_schema"]
        await client.delete(f"/api/config/config_entries/options/flow/{option_id}")


@pytest.mark.parametrize("name", ["", " ", "x" * 61, "Name\rHeader", "Name\nHeader"])
def test_source_name_validation_remains_server_side(hass, source_config, name):
    assert validate_sources(hass, {**source_config, "name": name})["name"] == "invalid_name"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "invalid"])
def test_finite_rule_and_reminder_validation_remains_server_side(hass, source_config, value):
    assert validate_rules({**source_config, "min_flow_l_min": value}) == {
        "min_flow_l_min": "invalid_number"
    }
    assert validate_emails(hass, {**source_config, "reminder_hours": value}) == {
        "reminder_hours": "invalid_number"
    }


def test_calibration_sample_count_must_be_whole(source_config):
    assert validate_rules({**source_config, "calibration_samples": 3.5}) == {
        "calibration_samples": "invalid_number"
    }


def test_manifest_translations_and_services():
    component = ROOT / "custom_components" / DOMAIN
    manifest = json.loads((component / "manifest.json").read_text())
    assert manifest["config_flow"] is True
    assert manifest["integration_type"] == "service"
    assert manifest["requirements"] == []
    assert json.loads((ROOT / "hacs.json").read_text())["homeassistant"] == "2026.8.3"
    strings = json.loads((component / "strings.json").read_text())
    services = yaml.safe_load((component / "services.yaml").read_text())
    assert set(services) == set(ACTIONS) | {"get_report"}
    for language in ("en", "fr"):
        translated = json.loads((component / "translations" / f"{language}.json").read_text())
        for section in ("config", "options", "entity", "exceptions", "services"):
            assert section in translated
        for step, schema in (
            ("manual", sources_schema()),
            ("rules", rules_schema()),
            ("emails", emails_schema()),
            ("report", report_schema()),
        ):
            fields = {str(marker.schema) for marker in schema.schema}
            assert fields <= set(translated["config"]["step"][step]["data"])
        assert set(KEYS) <= set(translated["entity"]["sensor"])
        assert set(REASON_CODES) <= set(translated["entity"]["sensor"]["reason"]["state"])
        assert set(ACTIONS) <= set(translated["entity"]["button"])
        assert strings["config"]["error"].keys() == translated["config"]["error"].keys()
    french = json.loads((component / "translations" / "fr.json").read_text())
    assert french["entity"]["switch"]["emails_enabled"]["name"] == "Activer les emails"
    assert french["config"]["step"]["emails"]["data"]["emails_enabled"] == "Activer les emails"


async def test_dashboard_references_real_entities_and_actions(hass, source_config):
    entry = await setup_guard(hass, source_config)
    actual = {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    dashboard_text = (ROOT / "examples" / "dashboard.yaml").read_text()
    dashboard = yaml.safe_load(dashboard_text)
    assert dashboard
    referenced = set(re.findall(r"(?:sensor|button|switch)\.demo_guard_[a-z_]+", dashboard_text))
    assert referenced
    assert referenced <= actual, f"Dashboard references nonexistent entities: {referenced - actual}"
    for action in ACTIONS:
        assert hass.services.has_service(DOMAIN, action)
    assert hass.services.has_service(DOMAIN, "get_report")
