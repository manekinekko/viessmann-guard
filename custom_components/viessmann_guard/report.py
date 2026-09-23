"""Render localized email reports from an explicitly sanitized snapshot."""

from __future__ import annotations

import unicodedata
from math import isfinite
from typing import Any

from .const import LANGUAGES, LIST_SETTINGS, normalize_language
from .email_layout import layout
from .reasons import describe_reason

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
    "es": {
        "report": "Informe de caudal hidráulico",
        "test": "Email de prueba",
        "urgent": "Alerta urgente de caudal",
        "reminder": "Recordatorio de alerta de caudal",
        "recovery": "Recuperación del caudal",
        "alert": "Alerta de caudal",
        "name": "Viessmann Guard",
        "summary": "Observaciones actuales",
        "generated_at": "Generado el",
        "state": "Estado del seguimiento",
        "reason": "Motivo de la evaluación",
        "flow": "Caudal actual de la fuente",
        "reference": "Caudal de referencia",
        "minimum": "Umbral mínimo de caudal",
        "decline_pct": "Descenso respecto a la referencia",
        "duration_seconds": "Duración de la condición",
        "last_cleaned": "Última limpieza registrada",
        "thresholds": "Umbrales configurados",
        "telemetry": "Telemetría completa de las fuentes",
        "name_label": "Nombre",
        "entity_id": "Entidad fuente",
        "value": "Valor",
        "unit": "Unidad",
        "status": "Estado de los datos",
        "observed_at": "Observado el",
        "freshness_seconds": "Antigüedad de los datos",
        "missing": "Ausente / no proporcionado",
        "stale": "Obsoleto",
        "available": "Disponible",
        "unavailable": "No disponible",
        "incident": "Estado del incidente",
        "id": "ID del incidente",
        "severity": "Gravedad registrada",
        "acknowledged": "Reconocido",
        "snoozed_until": "Pospuesto hasta",
        "yes": "Sí",
        "no": "No",
        "trends": "Tendencia reciente del caudal",
        "rules": "Reglas utilizadas para esta evaluación",
        "interpretation": "Interpretación y próximos pasos",
        "possible": "Explicación posible",
        "alternatives": "Causas alternativas",
        "advice": "Orientación profesional",
        "limitations": "Limitaciones",
        "seconds": "segundos",
        "possible_text": "Un caudal reducido puede ser compatible con un filtro sucio u obstruido, pero estas observaciones no permiten confirmar una obstrucción.",
        "alternatives_text": "Otras explicaciones incluyen la velocidad o el modo de la bomba, una avería de la bomba, válvulas cerradas o restringidas, aire atrapado y datos incorrectos u obsoletos de los sensores.",
        "advice_text": "Ante una anomalía activa, solicite pronto la inspección de los filtros y del circuito hidráulico por un profesional cualificado. Si se confirma la suciedad, encargue la limpieza de los filtros según los procedimientos de mantenimiento y seguridad del fabricante. Revise también la bomba, las válvulas, el aire y los sensores. No abra equipos presurizados ni anule las protecciones de seguridad.",
        "limitations_text": "Esta evaluación de solo lectura se basa en la telemetría proporcionada; no es un diagnóstico ni una prueba de obstrucción del filtro. No es un dispositivo de seguridad. Las mediciones ausentes u obsoletas reducen la confianza. Los umbrales son ajustes de seguimiento, no límites de seguridad del fabricante. No se modifican ajustes ni controles del equipo. La aceptación de un email por SMTP no demuestra que haya llegado al destinatario.",
    },
    "de": {
        "report": "Hydraulischer Durchflussbericht",
        "test": "Test-E-Mail",
        "urgent": "Dringende Durchflusswarnung",
        "reminder": "Erinnerung an die Durchflusswarnung",
        "recovery": "Erholung des Durchflusses",
        "alert": "Durchflusswarnung",
        "name": "Viessmann Guard",
        "summary": "Aktuelle Beobachtungen",
        "generated_at": "Erstellt am",
        "state": "Überwachungsstatus",
        "reason": "Beurteilungsgrund",
        "flow": "Aktueller Durchfluss der Quelle",
        "reference": "Referenzdurchfluss",
        "minimum": "Mindestdurchflussschwelle",
        "decline_pct": "Rückgang gegenüber der Referenz",
        "duration_seconds": "Dauer des Zustands",
        "last_cleaned": "Zuletzt erfasste Reinigung",
        "thresholds": "Konfigurierte Schwellenwerte",
        "telemetry": "Vollständige Quellentelemetrie",
        "name_label": "Name",
        "entity_id": "Quellentität",
        "value": "Wert",
        "unit": "Einheit",
        "status": "Datenstatus",
        "observed_at": "Beobachtet am",
        "freshness_seconds": "Datenalter",
        "missing": "Fehlend / nicht angegeben",
        "stale": "Veraltet",
        "available": "Verfügbar",
        "unavailable": "Nicht verfügbar",
        "incident": "Vorfallstatus",
        "id": "Vorfall-ID",
        "severity": "Erfasster Schweregrad",
        "acknowledged": "Bestätigt",
        "snoozed_until": "Zurückgestellt bis",
        "yes": "Ja",
        "no": "Nein",
        "trends": "Aktueller Durchflussverlauf",
        "rules": "Verwendete Beurteilungsregeln",
        "interpretation": "Einordnung und nächste Schritte",
        "possible": "Mögliche Erklärung",
        "alternatives": "Andere mögliche Ursachen",
        "advice": "Fachliche Empfehlung",
        "limitations": "Einschränkungen",
        "seconds": "Sekunden",
        "possible_text": "Ein verringerter Durchfluss kann zu einem verschmutzten oder zugesetzten Filter passen. Diese Beobachtungen belegen jedoch keine Filterverstopfung.",
        "alternatives_text": "Andere Erklärungen sind Pumpendrehzahl oder Betriebsart, ein Pumpendefekt, geschlossene oder eingeschränkte Ventile, eingeschlossene Luft sowie fehlerhafte oder veraltete Sensordaten.",
        "advice_text": "Lassen Sie bei einer aktiven Auffälligkeit die Filter und den Hydraulikkreis zeitnah von einer qualifizierten Fachkraft prüfen. Wenn Verschmutzung bestätigt wird, lassen Sie die Filter nach den Wartungs- und Sicherheitsvorgaben des Herstellers reinigen. Prüfen Sie auch Pumpe, Ventile, Luft und Sensoren. Öffnen Sie keine unter Druck stehenden Geräte und umgehen Sie keine Sicherheitseinrichtungen.",
        "limitations_text": "Diese rein lesende Beurteilung basiert auf den bereitgestellten Messwerten. Sie ist keine Diagnose und kein Nachweis eines verstopften Filters. Dies ist keine Sicherheitseinrichtung. Fehlende oder veraltete Messwerte verringern die Aussagekraft. Konfigurierte Schwellen sind Überwachungseinstellungen, keine Sicherheitsgrenzen des Herstellers. Geräteeinstellungen und Steuerungen werden nicht geändert. Die Annahme einer E-Mail durch SMTP belegt nicht die Zustellung an den Empfänger.",
    },
}

_LABELS = {
    "percentage_points": (
        "percentage points",
        "points de pourcentage",
        "puntos porcentuales",
        "Prozentpunkte",
    ),
    "watch": (
        "Flow decline watch",
        "Surveillance d'une baisse de débit",
        "Vigilancia del descenso de caudal",
        "Beobachtung eines Durchflussrückgangs",
    ),
    "urgent_prefix": ("URGENT", "URGENT", "URGENTE", "DRINGEND"),
    "normal": (
        "Normal or idle; check the reason",
        "Normal ou repos ; lire le motif",
        "Normal o en reposo; consulte el motivo",
        "Normal oder Leerlauf; Grund prüfen",
    ),
    "learning": (
        "Startup or calibration",
        "Démarrage ou étalonnage",
        "Arranque o calibración",
        "Start oder Kalibrierung",
    ),
    "diagnostic_unavailable": (
        "Diagnosis unavailable",
        "Diagnostic indisponible",
        "Diagnóstico no disponible",
        "Diagnose nicht verfügbar",
    ),
    "recipient": ("SMTP recipient", "Destinataire SMTP", "Destinatario SMTP", "SMTP-Empfänger"),
    "smtp_failure": (
        "SMTP report could not be accepted. Check the recipient status and the native SMTP integration.",
        "Le rapport SMTP n'a pas été accepté. Vérifiez l'état du destinataire et l'intégration SMTP native.",
        "No se ha aceptado el informe SMTP. Revise el estado del destinatario y la integración SMTP nativa.",
        "Der SMTP-Bericht wurde nicht angenommen. Prüfen Sie den Empfängerstatus und die native SMTP-Integration.",
    ),
    "delta_t": (
        "Delta T (supply - return)",
        "Delta T (départ - retour)",
        "Delta T (impulsión - retorno)",
        "Delta T (Vorlauf - Rücklauf)",
    ),
    "awaiting_fresh_report": (
        "Waiting for a new report after startup",
        "Attente d'un nouveau rapport après démarrage",
        "Esperando un informe nuevo tras el arranque",
        "Warten auf eine neue Meldung nach dem Start",
    ),
    "invalid": ("Invalid value", "Valeur invalide", "Valor inválido", "Ungültiger Wert"),
    "invalid_or_unsupported_unit": (
        "Invalid value or unsupported unit",
        "Valeur invalide ou unité non prise en charge",
        "Valor inválido o unidad no compatible",
        "Ungültiger Wert oder nicht unterstützte Einheit",
    ),
    "ha_report_time": (
        "HA last_reported is a Home Assistant report time, not a verified controller acquisition time. Timestamps include their UTC offset.",
        "HA last_reported est une date de rapport Home Assistant, pas une date d'acquisition vérifiée du contrôleur. Les horodatages indiquent leur décalage UTC.",
        "HA last_reported es la hora de un informe de Home Assistant, no una hora de adquisición verificada del controlador. Las marcas de tiempo incluyen su desfase UTC.",
        "HA last_reported ist die Meldungszeit in Home Assistant, keine geprüfte Erfassungszeit des Reglers. Zeitstempel enthalten ihren UTC-Versatz.",
    ),
    "history_not_evidence": (
        "Historical trend rows are not new observations. Unavailable values do not establish recovery.",
        "L'historique ne constitue pas de nouvelles observations. Les valeurs indisponibles ne prouvent pas une récupération.",
        "El historial no constituye observaciones nuevas. Los valores no disponibles no demuestran recuperación.",
        "Verlaufswerte sind keine neuen Beobachtungen. Nicht verfügbare Werte belegen keine Erholung.",
    ),
    "inventory_truncated": (
        "Inventory truncated at 150 entities.",
        "Inventaire limité à 150 entités.",
        "Inventario limitado a 150 entidades.",
        "Bestandsliste auf 150 Entitäten begrenzt.",
    ),
    "inventory_scoped": (
        "Device-scoped inventory; only selected state fields.",
        "Inventaire limité aux appareils choisis et aux champs autorisés.",
        "Inventario limitado a los dispositivos elegidos y a los campos permitidos.",
        "Bestandsliste nur für ausgewählte Geräte und zulässige Zustandsfelder.",
    ),
    "min_flow_l_min": (
        "Installation minimum flow",
        "Débit minimum de l'installation",
        "Caudal mínimo de la instalación",
        "Mindestdurchfluss der Anlage",
    ),
    "absolute_persistence_s": (
        "Low-flow persistence",
        "Persistance du débit faible",
        "Persistencia del caudal bajo",
        "Dauer des niedrigen Durchflusses",
    ),
    "relative_drop_pct": (
        "Relative decline threshold",
        "Seuil de baisse relative",
        "Umbral de descenso relativo",
        "Schwelle des relativen Rückgangs",
    ),
    "relative_persistence_s": (
        "Relative-decline persistence",
        "Persistance de la baisse relative",
        "Persistencia del descenso relativo",
        "Dauer des relativen Rückgangs",
    ),
    "hysteresis_pct": (
        "Recovery hysteresis",
        "Hystérésis de récupération",
        "Histéresis de recuperación",
        "Erholungshysterese",
    ),
    "recovery_s": (
        "Healthy recovery duration",
        "Durée de récupération saine",
        "Duración de recuperación saludable",
        "Dauer der gesunden Erholung",
    ),
    "startup_grace_s": (
        "Startup grace",
        "Délai de démarrage",
        "Espera de arranque",
        "Anlaufwartezeit",
    ),
    "stale_after_s": (
        "Report freshness limit",
        "Délai de fraîcheur",
        "Límite de antigüedad del informe",
        "Gültigkeitsdauer der Meldung",
    ),
    "calibration_samples": (
        "Calibration sample count",
        "Nombre de mesures d'étalonnage",
        "Número de muestras de calibración",
        "Anzahl der Kalibrierungswerte",
    ),
    "calibration_duration_s": (
        "Calibration duration",
        "Durée d'étalonnage",
        "Duración de calibración",
        "Kalibrierungsdauer",
    ),
    "pump_tolerance_pct": (
        "Pump-speed tolerance",
        "Tolérance de vitesse de pompe",
        "Tolerancia de velocidad de la bomba",
        "Pumpendrehzahltoleranz",
    ),
    "running_modes": (
        "Active mode values",
        "Valeurs des modes actifs",
        "Valores de modos activos",
        "Werte aktiver Betriebsarten",
    ),
    "idle_modes": (
        "Idle mode values",
        "Valeurs des modes au repos",
        "Valores de modos en reposo",
        "Werte der Leerlaufbetriebsarten",
    ),
    "excluded_modes": (
        "Excluded mode values",
        "Valeurs des modes exclus",
        "Valores de modos excluidos",
        "Werte ausgeschlossener Betriebsarten",
    ),
    "pump_on_values": (
        "Pump-running values",
        "Valeurs de pompe en marche",
        "Valores de bomba en marcha",
        "Werte für laufende Pumpe",
    ),
    "pump_off_values": (
        "Pump-stopped values",
        "Valeurs de pompe à l'arrêt",
        "Valores de bomba parada",
        "Werte für stehende Pumpe",
    ),
    "fault_values": (
        "Active fault values",
        "Valeurs de défaut actif",
        "Valores de fallo activo",
        "Werte aktiver Fehler",
    ),
    "fault_clear_values": (
        "Clear fault values",
        "Valeurs d'absence de défaut",
        "Valores sin fallo",
        "Werte ohne Fehler",
    ),
}
for _index, _language in enumerate(LANGUAGES):
    _COPY[_language].update({key: values[_index] for key, values in _LABELS.items()})


def report_copy(language: str) -> dict[str, str]:
    return _COPY[normalize_language(language)]


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
    if name == "pump_tolerance_pct":
        return copy["percentage_points"]
    if name in {"relative_drop_pct", "hysteresis_pct", "decline_pct"}:
        return "%"
    if name in {
        "absolute_persistence_s",
        "relative_persistence_s",
        "recovery_s",
        "startup_grace_s",
        "stale_after_s",
        "calibration_duration_s",
        "urgent_duration_seconds",
        "freshness_seconds",
    }:
        return copy["seconds"]
    if name in {"min_flow_l_min", "minimum_flow", "minimum", "reference"}:
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
            "awaiting_fresh_report": copy["awaiting_fresh_report"],
            "invalid": copy["invalid"],
            "invalid_or_unsupported_unit": copy["invalid_or_unsupported_unit"],
        }.get(normalized, status)
        if translated not in markers and not (markers and translated == copy["available"]):
            markers.append(translated)
    return "; ".join(markers) if markers else copy["missing"]


def render_report(snapshot: dict, kind: str, language: str = "en") -> tuple[str, str, str]:
    """Return a single-line title, complete plain text, and escaped HTML.

    Only documented fields, primitive thresholds and configured context lists are rendered.
    No arbitrary attributes, recipients, credentials or attachments are included.
    """
    language = normalize_language(language)
    copy = _COPY[language]
    kind = (
        kind
        if kind in {"report", "test", "urgent", "watch", "reminder", "recovery", "alert"}
        else "report"
    )
    incident = snapshot.get("incident")
    incident = incident if isinstance(incident, dict) else {}
    urgent = kind in {"urgent", "reminder"} and incident.get("severity") == "urgent"
    name = _scalar(snapshot.get("name")) or copy["name"]
    label = copy[kind] if kind != "urgent" or urgent else copy["alert"]
    prefix = f"[{copy['urgent_prefix']}] " if urgent else ""
    title = f"{prefix}{name}: {label}"[:240]
    sections: list[tuple[str, list[tuple[str, str]]]] = []
    summary = [
        (copy["generated_at"], _value(snapshot.get("generated_at"), copy)),
        (
            copy["state"],
            copy.get(_value(snapshot.get("state"), copy), _value(snapshot.get("state"), copy)),
        ),
        (
            copy["reason"],
            describe_reason(snapshot["reason_code"], language)
            if isinstance(snapshot.get("reason_code"), str)
            else _value(snapshot.get("reason"), copy),
        ),
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
        if field == "severity":
            text = copy.get(text, text)
        incident_rows.append((copy[field], text))
    sections.append((copy["incident"], incident_rows))

    thresholds = snapshot.get("thresholds")
    threshold_rows = []
    if isinstance(thresholds, dict):
        for name, value in thresholds.items():
            if name in LIST_SETTINGS and isinstance(value, (list, tuple)):
                value = ", ".join(item for item in value if isinstance(item, str))
            if not isinstance(name, str) or not isinstance(
                value, (str, int, float, bool, type(None))
            ):
                continue
            label = copy.get(name, _value(name, copy))
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
    rule_codes = snapshot.get("rule_codes")
    if isinstance(rule_codes, list):
        rule_rows.extend(
            ("", copy[code])
            for code in rule_codes
            if isinstance(code, str)
            and code
            in {
                "ha_report_time",
                "history_not_evidence",
                "inventory_truncated",
                "inventory_scoped",
            }
        )
    limitation_codes = snapshot.get("limitation_codes")
    if isinstance(limitation_codes, list):
        rule_rows.extend(
            ("", describe_reason(code, language))
            for code in limitation_codes
            if isinstance(code, str)
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

    return layout(snapshot, kind, language, title, copy[kind], copy, _scalar, sections)
