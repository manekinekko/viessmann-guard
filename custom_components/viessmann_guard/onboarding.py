"""Plain-language native onboarding summaries, never raw registry attributes."""

import re

from .const import LANGUAGES, normalize_language

LABELS = {
    "flow": ("Flow", "Débit", "Caudal", "Durchfluss"),
    "mode": ("Compressor phase", "Phase du compresseur", "Fase del compresor", "Verdichterphase"),
    "pump": (
        "Heating-circuit circulation",
        "Circulation du circuit de chauffage",
        "Circulación del circuito de calefacción",
        "Heizkreisumwälzung",
    ),
    "compressor": ("Compressor", "Compresseur", "Compresor", "Verdichter"),
    "supply_temperature": (
        "Supply temperature",
        "Température de départ",
        "Temperatura de impulsión",
        "Vorlauftemperatur",
    ),
    "return_temperature": (
        "Return temperature",
        "Température de retour",
        "Temperatura de retorno",
        "Rücklauftemperatur",
    ),
    "pressure": ("Pressure", "Pression", "Presión", "Druck"),
    "outside_temperature": (
        "Outside temperature",
        "Température extérieure",
        "Temperatura exterior",
        "Außentemperatur",
    ),
}
STATUSES = {
    "detected": ("detected", "détecté", "detectado", "erkannt"),
    "not_exposed": (
        "not exposed: observation only if required",
        "non exposé : observation seule si nécessaire",
        "no expuesto: solo observación si es necesario",
        "nicht bereitgestellt: bei Bedarf nur Beobachtung",
    ),
    "ambiguous": (
        "ambiguous: no automatic selection",
        "ambigu : aucune sélection automatique",
        "ambiguo: sin selección automática",
        "mehrdeutig: keine automatische Auswahl",
    ),
    "disabled_or_excluded": (
        "disabled/excluded: left unchanged",
        "désactivé/exclu : laissé inchangé",
        "desactivado/excluido: sin cambios",
        "deaktiviert/ausgeschlossen: unverändert",
    ),
    "unavailable": (
        "detected, currently unavailable",
        "détecté, actuellement indisponible",
        "detectado, actualmente no disponible",
        "erkannt, derzeit nicht verfügbar",
    ),
    "unmapped_state": (
        "detected, unrecognized phase: observation only",
        "détecté, phase non reconnue : observation seule",
        "detectado, fase desconocida: solo observación",
        "erkannt, unbekannte Phase: nur Beobachtung",
    ),
    "invalid_unit_or_value": (
        "unsupported unit or invalid value",
        "unité non prise en charge ou valeur invalide",
        "unidad no compatible o valor inválido",
        "nicht unterstützte Einheit oder ungültiger Wert",
    ),
}


def summary(name: str, statuses: dict[str, str], language: str) -> str:
    language = normalize_language(language)
    index = LANGUAGES.index(language)
    safe_name = re.sub(r"[^A-Za-z0-9À-ÿ ._-]", "", name)
    lines = [f"**{safe_name}**", ""]
    for role, labels in LABELS.items():
        lines.append(f"- {labels[index]} : {STATUSES[statuses[role]][index]}")
    lines += [
        "",
        {
            "fr": "Observation et historique dès réception de mesures fraîches. Aucun minimum constructeur "
            "n'est supposé : alertes absolues désactivées jusqu'au réglage avancé du minimum réel. "
            "Suivi relatif seulement avec contexte comparable et référence saine confirmée. "
            "Emails désactivés. Vous pourrez ajuster les sources et destinataires dans les options.",
            "en": "Observation and history start with fresh reports. No manufacturer minimum is assumed: "
            "absolute alerts stay disabled until the actual minimum is set in options. Relative "
            "monitoring requires comparable operating context and a confirmed healthy reference. "
            "Emails stay OFF. Sources and recipients can be adjusted later in options.",
            "es": "La observación y el historial comienzan con informes recientes. No se supone ningún mínimo del fabricante: "
            "las alertas absolutas están desactivadas hasta configurar el mínimo real. El seguimiento relativo requiere "
            "un contexto comparable y una referencia saludable confirmada. Los emails están desactivados. "
            "Las fuentes y los destinatarios se pueden ajustar después en las opciones.",
            "de": "Beobachtung und Verlauf beginnen mit neuen Meldungen. Ein Herstellermindestwert wird nicht angenommen: "
            "Absolute Warnungen bleiben deaktiviert, bis der tatsächliche Mindestwert eingestellt ist. Relative Überwachung "
            "erfordert vergleichbare Bedingungen und eine bestätigte gesunde Referenz. E-Mails bleiben AUS. "
            "Quellen und Empfänger können später in den Optionen angepasst werden.",
        }[language],
    ]
    return "\n".join(lines)
