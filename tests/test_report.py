"""Completeness, localization and injection-safety checks for email reports."""

from html import escape, unescape
from html.parser import HTMLParser

import pytest

from custom_components.viessmann_guard.report import render_report


@pytest.fixture
def snapshot():
    return {
        "generated_at": "2026-09-22T08:15:00+00:00",
        "name": "Heat pump",
        "state": "urgent",
        "reason": "Persistent low flow",
        "flow": 8.5,
        "reference": 20,
        "minimum": 12,
        "decline_pct": 57.5,
        "duration_seconds": 900,
        "last_cleaned": "2026-08-15T10:30:00+00:00",
        "thresholds": {
            "minimum_flow": 12,
            "decline_pct": 40,
            "urgent_duration_seconds": 900,
            "freshness_seconds": 300,
        },
        "telemetry": [
            {
                "name": "Flow",
                "entity_id": "sensor.water_flow",
                "value": 8.5,
                "unit": "L/min",
                "status": "fresh",
                "observed_at": "2026-09-22T08:14:58+00:00",
                "freshness_seconds": 2,
            },
            {
                "name": "Supply temperature",
                "entity_id": "sensor.supply",
                "value": 35.1,
                "unit": "°C",
                "status": "stale",
                "observed_at": "2026-09-22T07:00:00+00:00",
                "freshness_seconds": 4500,
            },
            {
                "name": "Return temperature",
                "entity_id": "sensor.return",
                "value": None,
                "unit": "°C",
                "status": "missing",
                "observed_at": None,
                "freshness_seconds": None,
            },
            {
                "name": "Compressor",
                "entity_id": "binary_sensor.compressor",
                "value": "on",
                "status": "fresh",
            },
            {
                "name": "Operating mode",
                "entity_id": "sensor.operating_mode",
                "value": "heating",
                "status": "fresh",
            },
            {
                "name": "Pump speed",
                "entity_id": "sensor.pump_speed",
                "value": 75,
                "unit": "%",
                "status": "fresh",
            },
        ],
        "trends": [
            {"observed_at": "2026-09-22T07:45:00+00:00", "flow": 19.9},
            {"observed_at": "2026-09-22T08:00:00+00:00", "flow": 11.5},
            {"observed_at": "2026-09-22T08:14:58+00:00", "flow": 8.5},
        ],
        "rules": ["Heating active", "Flow below configured minimum", "Condition duration exceeded"],
        "incident": {
            "id": "incident-17",
            "severity": "urgent",
            "acknowledged": True,
            "snoozed_until": "2026-09-22T09:00:00+00:00",
        },
    }


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attributes = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)


def test_english_report_includes_all_observations_and_telemetry(snapshot):
    title, plain, html = render_report(snapshot, "urgent")
    assert title.startswith("[URGENT] Heat pump")
    for content in (plain, unescape(html)):
        for value in (
            snapshot["generated_at"],
            snapshot["last_cleaned"],
            "8.5 L/min",
            "20 L/min",
            "12 L/min",
            "57.5 %",
            "900 seconds",
            "minimum_flow: 12 L/min" if content == plain else "minimum_flow",
            "urgent_duration_seconds",
            "300 seconds",
            "Stale",
            "Missing / not supplied",
            "incident-17",
            "urgent",
            "2026-09-22T09:00:00+00:00",
        ):
            assert value in content
        for item in snapshot["telemetry"]:
            assert item["name"] in content
            assert item["entity_id"] in content
            if item.get("observed_at"):
                assert item["observed_at"] in content
            if item.get("value") is not None:
                assert str(item["value"]) in content
        for item in snapshot["trends"]:
            assert item["observed_at"] in content
            assert f"{item['flow']} L/min" in content
        for rule in snapshot["rules"]:
            assert rule in content
    assert "Acknowledged: Yes" in plain
    assert "Data age: 4500 seconds" in plain


@pytest.mark.parametrize("language", ["fr", "fr-FR", "fr_CA"])
def test_french_template_is_complete_and_explicit_about_uncertainty(snapshot, language):
    title, plain, html = render_report(snapshot, "reminder", language)
    assert title.startswith("[URGENT]")
    assert "Rappel d'alerte" in title
    for content in (plain, unescape(html)):
        for text in (
            "Généré le",
            "Débit de référence",
            "Durée de la condition",
            "Dernier nettoyage enregistré",
            "Télémétrie complète",
            "Périmé",
            "Manquant / non renseigné",
            "900 secondes",
            "pompe",
            "vannes",
            "capteurs",
            "fabricant",
            "professionnel qualifié",
            "ne permettent pas de confirmer",
            "ni un diagnostic",
        ):
            assert text in content
        for item in snapshot["telemetry"]:
            assert item["entity_id"] in content
    assert '<html lang="fr">' in html


@pytest.mark.parametrize("kind", ["report", "test", "recovery", "alert"])
def test_nonurgent_report_kinds_do_not_invent_urgent_subject(snapshot, kind):
    title, _, _ = render_report(snapshot, kind)
    assert "[URGENT]" not in title
    assert "Urgent" not in title


@pytest.mark.parametrize("severity", [None, "warning", "normal", ""])
@pytest.mark.parametrize("kind", ["urgent", "reminder", "report", "test"])
def test_urgent_prefix_requires_recorded_urgent_incident(snapshot, kind, severity):
    snapshot["incident"]["severity"] = severity
    title, _, _ = render_report(snapshot, kind)
    assert "[URGENT]" not in title
    assert "Urgent" not in title


def test_report_and_test_without_incident_do_not_invent_severity():
    for kind in ("report", "test"):
        title, plain, _ = render_report({}, kind)
        assert "[URGENT]" not in title
        assert "Recorded severity: Missing / not supplied" in plain
        assert "Current source flow: Missing / not supplied L/min" in plain
        assert "Generated at: Missing / not supplied" in plain


def test_malicious_values_are_escaped_and_header_controls_normalized(snapshot):
    malicious = '<img src=x onerror="alert(1)">&\'</dd><script>bad()</script>'
    snapshot["name"] = "Unit\r\nBcc: stolen@example.test\x00\u202e" + malicious
    snapshot["state"] = malicious
    snapshot["reason"] = malicious
    snapshot["generated_at"] = malicious
    snapshot["last_cleaned"] = malicious
    snapshot["flow"] = malicious
    snapshot["thresholds"] = {malicious: malicious}
    snapshot["telemetry"] = [
        {
            key: malicious
            for key in (
                "name",
                "entity_id",
                "value",
                "unit",
                "status",
                "observed_at",
                "freshness_seconds",
            )
        }
    ]
    snapshot["trends"] = [{"observed_at": malicious, "flow": malicious}]
    snapshot["rules"] = [malicious]
    snapshot["incident"] = {
        "id": malicious,
        "severity": malicious,
        "acknowledged": malicious,
        "snoozed_until": malicious,
    }
    title, plain, html = render_report(snapshot, "report")
    assert not any(char in title for char in "\r\n\0\u202e")
    assert malicious in plain
    assert malicious not in html
    assert escape(malicious) in html
    parser = Tags()
    parser.feed(html)
    assert "script" not in parser.tags
    assert "img" not in parser.tags
    assert all(name not in {"onerror", "onclick", "src", "href"} for name, _ in parser.attributes)


@pytest.mark.parametrize("language", ["en", "fr"])
def test_arbitrary_attributes_recipients_and_credentials_are_not_rendered(snapshot, language):
    private = "DO_NOT_RENDER_PRIVATE_PAYLOAD"
    snapshot.update(
        attributes={"password": private},
        recipients=[private],
        credentials=private,
        raw_ha_data={"token": private},
    )
    snapshot["telemetry"][0]["attributes"] = {"token": private}
    snapshot["incident"]["recipient"] = private
    snapshot["thresholds"]["raw_attributes"] = {"token": private}
    snapshot["rules"].append({"secret": private})
    for content in render_report(snapshot, "report", language):
        assert private not in content


def test_nonprimitive_field_values_never_stringify_private_objects(snapshot):
    class Private:
        def __str__(self):
            raise AssertionError("Private object must not be stringified")

    snapshot["name"] = Private()
    snapshot["reason"] = Private()
    snapshot["telemetry"][0]["value"] = {"token": "private-secret"}
    title, plain, html = render_report(snapshot, "report")
    assert title.startswith("Viessmann Guard:")
    assert "private-secret" not in plain + html
    assert "Missing / not supplied" in plain


@pytest.mark.parametrize("language", ["en", "fr"])
def test_every_report_is_cautious_and_provides_professional_alternatives(snapshot, language):
    for kind in ("urgent", "reminder", "recovery", "report", "test"):
        _, plain, html = render_report(snapshot, kind, language)
        for content in (plain.lower(), unescape(html).lower()):
            if language == "en":
                assert "may be consistent" in content
                assert "not a diagnosis" in content
                assert "pump" in content
                assert "valves" in content
                assert "air" in content
                assert "sensor" in content
                assert "qualified professional" in content
                assert "manufacturer" in content
                assert "inspected promptly" in content
                assert "if fouling is confirmed" in content
                assert "filters cleaned" in content
                assert "not a safety device" in content
                assert "filter is clogged" not in content
                assert "filter is blocked" not in content
                assert "smtp" in content
            else:
                assert "peut être compatible" in content
                assert "ni un diagnostic" in content
                assert "pompe" in content
                assert "vannes" in content
                assert "air" in content
                assert "capteur" in content
                assert "professionnel qualifié" in content
                assert "fabricant" in content
                assert "contrôler rapidement" in content
                assert "si l'encrassement est confirmé" in content
                assert "nettoyer les filtres" in content
                assert "ni un dispositif de sécurité" in content
                assert "le filtre est colmaté" not in content


def test_missing_and_stale_are_both_explicit_even_for_partial_telemetry():
    snapshot = {
        "telemetry": [
            {"name": "Optional sensor", "entity_id": "sensor.optional"},
            {"name": "Old sensor", "value": None, "status": "stale"},
            {"name": "Offline sensor", "value": "unavailable", "status": "unavailable"},
            {"name": "Unknown sensor", "value": "unknown"},
        ],
    }
    _, plain, html = render_report(snapshot, "test")
    assert "Optional sensor (sensor.optional)" in plain
    assert "Data age: Missing / not supplied seconds" in plain
    assert "Missing / not supplied; Stale" in plain
    assert "Missing / not supplied; Unavailable" in plain
    assert plain.count("Data status: Missing / not supplied") == 4
    assert "Stale" in html


def test_unknown_language_and_kind_fall_back_to_english_report(snapshot):
    title, plain, html = render_report(snapshot, "<script>alert(1)</script>", "de")
    assert title == "Heat pump: Hydraulic flow report"
    assert "Current observations" in plain
    assert '<html lang="en">' in html
    assert "<script>" not in html


def test_nonfinite_numbers_are_missing_instead_of_misleading_measurements(snapshot):
    snapshot["flow"] = float("nan")
    snapshot["reference"] = float("inf")
    snapshot["telemetry"][0]["value"] = float("-inf")
    _, plain, _ = render_report(snapshot, "report")
    assert "Current source flow: Missing / not supplied L/min" in plain
    assert "Reference flow: Missing / not supplied L/min" in plain
    assert "nan L/min" not in plain
    assert "inf L/min" not in plain
