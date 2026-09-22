"""Render English and French email reports from an explicitly sanitized snapshot."""

from __future__ import annotations

import unicodedata
from html import escape
from math import isfinite
from typing import Any

_COPY = {
    "en": {
        "report": "Hydraulic flow report",
        "test": "Test email",
        "urgent": "Urgent flow alert",
        "reminder": "Flow alert reminder",
        "recovery": "Flow recovery",
        "alert": "Flow alert",
        "name": "Viessmann Guard",
        "summary": "Current observations",
        "generated_at": "Generated at",
        "state": "Monitoring state",
        "reason": "Assessment reason",
        "flow": "Current source flow",
        "reference": "Reference flow",
        "minimum": "Minimum flow threshold",
        "decline_pct": "Decline from reference",
        "duration_seconds": "Condition duration",
        "last_cleaned": "Last recorded cleaning",
        "thresholds": "Configured thresholds",
        "telemetry": "Complete source telemetry",
        "name_label": "Name",
        "entity_id": "Source entity",
        "value": "Value",
        "unit": "Unit",
        "status": "Data status",
        "observed_at": "Observed at",
        "freshness_seconds": "Data age",
        "missing": "Missing / not supplied",
        "stale": "Stale",
        "available": "Available",
        "unavailable": "Unavailable",
        "incident": "Incident state",
        "id": "Incident ID",
        "severity": "Recorded severity",
        "acknowledged": "Acknowledged",
        "snoozed_until": "Snoozed until",
        "yes": "Yes",
        "no": "No",
        "trends": "Recent flow trend",
        "rules": "Rules used for this assessment",
        "interpretation": "Interpretation and next steps",
        "possible": "Possible explanation",
        "alternatives": "Alternative causes",
        "advice": "Professional guidance",
        "limitations": "Limitations",
        "seconds": "seconds",
        "possible_text": (
            "Reduced flow may be consistent with a dirty or restricted filter, but these "
            "observations do not establish filter clogging."
        ),
        "alternatives_text": (
            "Other explanations include pump speed or operating mode, a pump fault, "
            "closed or restricted valves, trapped air, or incorrect or stale sensor data."
        ),
        "advice_text": (
            "For an active anomaly, have the filters and hydraulic circuit inspected promptly "
            "by a qualified professional. If fouling is confirmed, have the filters cleaned "
            "according to the manufacturer's maintenance and safety procedures. Also assess "
            "the pump, valves, trapped air and sensors. Do not open pressurized equipment "
            "or bypass safety protections."
        ),
        "limitations_text": (
            "This is a read-only assessment of the supplied telemetry, not a diagnosis or "
            "proof of a blocked filter. This is not a safety device. Missing or stale measurements reduce confidence. "
            "Configured thresholds are monitoring settings, not manufacturer safety limits. "
            "No equipment settings or controls are changed. An email accepted by SMTP is "
            "not proof that it reached the recipient."
        ),
    },
    "fr": {
        "report": "Rapport de débit hydraulique",
        "test": "Courriel de test",
        "urgent": "Alerte urgente de débit",
        "reminder": "Rappel d'alerte de débit",
        "recovery": "Rétablissement du débit",
        "alert": "Alerte de débit",
        "name": "Viessmann Guard",
        "summary": "Observations actuelles",
        "generated_at": "Généré le",
        "state": "État de la surveillance",
        "reason": "Motif de l'évaluation",
        "flow": "Débit actuel de la source",
        "reference": "Débit de référence",
        "minimum": "Seuil minimal de débit",
        "decline_pct": "Baisse par rapport à la référence",
        "duration_seconds": "Durée de la condition",
        "last_cleaned": "Dernier nettoyage enregistré",
        "thresholds": "Seuils configurés",
        "telemetry": "Télémétrie complète des sources",
        "name_label": "Nom",
        "entity_id": "Entité source",
        "value": "Valeur",
        "unit": "Unité",
        "status": "État des données",
        "observed_at": "Observé le",
        "freshness_seconds": "Âge des données",
        "missing": "Manquant / non renseigné",
        "stale": "Périmé",
        "available": "Disponible",
        "unavailable": "Indisponible",
        "incident": "État de l'incident",
        "id": "Identifiant de l'incident",
        "severity": "Gravité enregistrée",
        "acknowledged": "Acquitté",
        "snoozed_until": "Reporté jusqu'au",
        "yes": "Oui",
        "no": "Non",
        "trends": "Tendance récente du débit",
        "rules": "Règles utilisées pour cette évaluation",
        "interpretation": "Interprétation et prochaines étapes",
        "possible": "Explication possible",
        "alternatives": "Autres causes possibles",
        "advice": "Conseil professionnel",
        "limitations": "Limites",
        "seconds": "secondes",
        "possible_text": (
            "Une baisse de débit peut être compatible avec un filtre encrassé ou obstrué, "
            "mais ces observations ne permettent pas de confirmer un colmatage."
        ),
        "alternatives_text": (
            "Les autres causes possibles comprennent la vitesse ou le mode de la pompe, "
            "une panne de pompe, des vannes fermées ou partiellement obstruées, de l'air "
            "dans le circuit, ou des données de capteur incorrectes ou périmées."
        ),
        "advice_text": (
            "En cas d'anomalie active, faites contrôler rapidement les filtres et le circuit "
            "hydraulique par un professionnel qualifié. Si l'encrassement est confirmé, faites "
            "nettoyer les filtres selon les procédures d'entretien et de sécurité du fabricant. "
            "Faites aussi vérifier le circulateur, les vannes, l'air et les capteurs. N'ouvrez "
            "pas un équipement sous pression et ne contournez pas les protections de sécurité."
        ),
        "limitations_text": (
            "Cette évaluation en lecture seule repose sur la télémétrie fournie. Ce n'est "
            "ni un diagnostic ni une preuve de colmatage du filtre, ni un dispositif de sécurité. Les mesures manquantes "
            "ou périmées réduisent la confiance. Les seuils configurés sont des paramètres "
            "de surveillance, pas des limites de sécurité du fabricant. Aucun réglage ni "
            "aucune commande de l'équipement n'est modifié. Un courriel accepté par SMTP "
            "ne garantit pas sa réception."
        ),
    },
}


def _scalar(value: Any) -> str | None:
    """Never stringify containers or objects that could hold private attributes."""
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not isfinite(value):
            return None
        return f"{value:g}" if isinstance(value, float) else str(value)
    if not isinstance(value, str):
        return None
    text = "".join(" " if unicodedata.category(char).startswith("C") else char for char in value)
    return " ".join(text.split()) or None


def _value(value: Any, copy: dict[str, str]) -> str:
    text = _scalar(value)
    return text if text is not None else copy["missing"]


def _measurement(value: Any, unit: str, copy: dict[str, str]) -> str:
    return f"{_value(value, copy)} {unit}"


def _threshold_unit(name: str, copy: dict[str, str]) -> str:
    lowered = name.casefold()
    if any(word in lowered for word in ("percent", "pct")):
        return "%"
    if any(word in lowered for word in ("second", "duration", "dwell", "age")):
        return copy["seconds"]
    if "flow" in lowered or lowered in {"minimum", "reference"}:
        return "L/min"
    return ""


def _telemetry_status(item: dict[str, Any], copy: dict[str, str]) -> str:
    status = _scalar(item.get("status"))
    value = _scalar(item.get("value"))
    markers = []
    if value is None or value.casefold() in {"unknown", "unavailable", "none"}:
        markers.append(copy["missing"])
    if status:
        normalized = status.casefold()
        translated = {
            "missing": copy["missing"],
            "stale": copy["stale"],
            "unavailable": copy["unavailable"],
            "unknown": copy["missing"],
            "fresh": copy["available"],
            "available": copy["available"],
            "ok": copy["available"],
        }.get(normalized, status)
        if translated not in markers and not (markers and translated == copy["available"]):
            markers.append(translated)
    return "; ".join(markers) if markers else copy["missing"]


def render_report(snapshot: dict, kind: str, language: str = "en") -> tuple[str, str, str]:
    """Return a single-line title, complete plain text, and escaped HTML.

    Only documented snapshot fields and primitive threshold values are rendered.
    No arbitrary attributes, recipients, credentials or attachments are included.
    """
    language = "fr" if language.lower().split("-")[0].split("_")[0] == "fr" else "en"
    copy = _COPY[language]
    kind = (
        kind if kind in {"report", "test", "urgent", "reminder", "recovery", "alert"} else "report"
    )
    incident = snapshot.get("incident")
    incident = incident if isinstance(incident, dict) else {}
    urgent = kind in {"urgent", "reminder"} and incident.get("severity") == "urgent"
    name = _scalar(snapshot.get("name")) or copy["name"]
    label = copy[kind] if kind != "urgent" or urgent else copy["alert"]
    title = f"{'[URGENT] ' if urgent else ''}{name}: {label}"[:240]
    sections: list[tuple[str, list[tuple[str, str]]]] = []
    summary = [
        (copy["generated_at"], _value(snapshot.get("generated_at"), copy)),
        (copy["state"], _value(snapshot.get("state"), copy)),
        (copy["reason"], _value(snapshot.get("reason"), copy)),
    ]
    for field in ("flow", "reference", "minimum"):
        summary.append((copy[field], _measurement(snapshot.get(field), "L/min", copy)))
    summary.extend(
        (
            (copy["decline_pct"], _measurement(snapshot.get("decline_pct"), "%", copy)),
            (
                copy["duration_seconds"],
                _measurement(snapshot.get("duration_seconds"), copy["seconds"], copy),
            ),
            (copy["last_cleaned"], _value(snapshot.get("last_cleaned"), copy)),
        )
    )
    sections.append((copy["summary"], summary))
    incident_rows = []
    for field in ("id", "severity", "acknowledged", "snoozed_until"):
        value = incident.get(field)
        text = copy["yes" if value else "no"] if isinstance(value, bool) else _value(value, copy)
        incident_rows.append((copy[field], text))
    sections.append((copy["incident"], incident_rows))

    thresholds = snapshot.get("thresholds")
    threshold_rows = []
    if isinstance(thresholds, dict):
        for name, value in thresholds.items():
            if not isinstance(name, str) or not isinstance(
                value, (str, int, float, bool, type(None))
            ):
                continue
            label = _value(name, copy)
            unit = _threshold_unit(name, copy)
            threshold_rows.append((label, _measurement(value, unit, copy).strip()))
    sections.append((copy["thresholds"], threshold_rows))

    telemetry = snapshot.get("telemetry")
    telemetry_rows = []
    if isinstance(telemetry, list):
        for index, item in enumerate(telemetry, 1):
            item = item if isinstance(item, dict) else {}
            label = (
                f"{index}. {_value(item.get('name'), copy)} ({_value(item.get('entity_id'), copy)})"
            )
            details = (
                f"{copy['value']}: {_value(item.get('value'), copy)}; "
                f"{copy['unit']}: {_value(item.get('unit'), copy)}; "
                f"{copy['status']}: {_telemetry_status(item, copy)}; "
                f"{copy['observed_at']}: {_value(item.get('observed_at'), copy)}; "
                f"{copy['freshness_seconds']}: "
                f"{_measurement(item.get('freshness_seconds'), copy['seconds'], copy)}"
            )
            telemetry_rows.append((label, details))
    sections.append((copy["telemetry"], telemetry_rows))

    trend_rows = []
    trends = snapshot.get("trends")
    if isinstance(trends, list):
        for item in trends:
            item = item if isinstance(item, dict) else {}
            trend_rows.append(
                (
                    _value(item.get("observed_at"), copy),
                    _measurement(item.get("flow"), "L/min", copy),
                )
            )
    sections.append((copy["trends"], trend_rows))
    rules = snapshot.get("rules")
    rule_rows = (
        [
            (str(index), _value(rule, copy))
            for index, rule in enumerate(rules, 1)
            if isinstance(rule, str)
        ]
        if isinstance(rules, list)
        else []
    )
    sections.append((copy["rules"], rule_rows))
    sections.append(
        (
            copy["interpretation"],
            [
                (copy[field], copy[f"{field}_text"])
                for field in ("possible", "alternatives", "advice")
            ],
        )
    )
    sections.append((copy["limitations"], [("", copy["limitations_text"])]))

    plain_parts = [title]
    html_parts = [
        f'<!DOCTYPE html><html lang="{language}"><head><meta charset="utf-8">'
        f"<title>{escape(title)}</title></head><body><h1>{escape(title)}</h1>"
    ]
    for heading, rows in sections:
        plain_parts.extend(("", heading))
        html_parts.append(f"<section><h2>{escape(heading)}</h2>")
        if rows:
            html_parts.append("<dl>")
            for label, value in rows:
                plain_parts.append(f"{label}: {value}" if label else value)
                html_parts.append(f"<dt>{escape(label)}</dt><dd>{escape(value)}</dd>")
            html_parts.append("</dl>")
        else:
            plain_parts.append(copy["missing"])
            html_parts.append(f"<p>{escape(copy['missing'])}</p>")
        html_parts.append("</section>")
    html_parts.append("</body></html>")
    return title, "\n".join(plain_parts), "".join(html_parts)
