"""Installation and native dashboard contracts, not frontend stubs."""

import json
import re
from pathlib import Path

import yaml
from homeassistant.helpers import entity_registry as er
from test_integration import setup_guard

from custom_components.viessmann_guard.button import ACTIONS
from custom_components.viessmann_guard.config_flow import (
    emails_schema,
    report_schema,
    rules_schema,
    sources_schema,
)
from custom_components.viessmann_guard.const import DOMAIN
from custom_components.viessmann_guard.reasons import REASON_CODES
from custom_components.viessmann_guard.sensor import KEYS

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_translations_and_services():
    component = ROOT / "custom_components" / DOMAIN
    manifest = json.loads((component / "manifest.json").read_text())
    assert manifest["config_flow"] is True
    assert manifest["requirements"] == []
    assert json.loads((ROOT / "hacs.json").read_text())["homeassistant"] == "2026.8.3"
    strings = json.loads((component / "strings.json").read_text())
    services = yaml.safe_load((component / "services.yaml").read_text())
    assert set(services) == set(ACTIONS)
    for language in ("en", "fr"):
        translated = json.loads((component / "translations" / f"{language}.json").read_text())
        for section in ("config", "options", "entity", "exceptions", "services"):
            assert section in translated
        for step, schema in (
            ("user", sources_schema()),
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
