"""Plain-language native onboarding summaries, never raw registry attributes."""

import re

LABELS = {
    "flow": ("Flow", "Débit"),
    "mode": ("Compressor phase", "Phase du compresseur"),
    "pump": ("Heating-circuit circulation", "Circulation du circuit de chauffage"),
    "compressor": ("Compressor", "Compresseur"),
    "supply_temperature": ("Supply temperature", "Température de départ"),
    "return_temperature": ("Return temperature", "Température de retour"),
    "pressure": ("Pressure", "Pression"),
    "outside_temperature": ("Outside temperature", "Température extérieure"),
}
STATUSES = {
    "detected": ("detected", "détecté"),
    "not_exposed": (
        "not exposed: observation only if required",
        "non exposé : observation seule si nécessaire",
    ),
    "ambiguous": ("ambiguous: no automatic selection", "ambigu : aucune sélection automatique"),
    "disabled_or_excluded": (
        "disabled/excluded: left unchanged",
        "désactivé/exclu : laissé inchangé",
    ),
    "unavailable": ("detected, currently unavailable", "détecté, actuellement indisponible"),
    "unmapped_state": (
        "detected, unrecognized phase: observation only",
        "détecté, phase non reconnue : observation seule",
    ),
    "invalid_unit_or_value": (
        "unsupported unit or invalid value",
        "unité non prise en charge ou valeur invalide",
    ),
}


def summary(name: str, statuses: dict[str, str], french: bool) -> str:
    index = int(french)
    safe_name = re.sub(r"[^A-Za-z0-9À-ÿ ._-]", "", name)
    lines = [f"**{safe_name}**", ""]
    for role, labels in LABELS.items():
        lines.append(f"- {labels[index]} : {STATUSES[statuses[role]][index]}")
    lines += [
        "",
        (
            "Observation et historique dès réception de mesures fraîches. Aucun minimum constructeur "
            "n'est supposé : alertes absolues désactivées jusqu'au réglage avancé du minimum réel. "
            "Suivi relatif seulement avec contexte comparable et référence saine confirmée. "
            "Emails désactivés. Vous pourrez ajuster les sources et destinataires dans les options."
            if french
            else "Observation and history start with fresh reports. No manufacturer minimum is assumed: "
            "absolute alerts stay disabled until the actual minimum is set in options. Relative "
            "monitoring requires comparable operating context and a confirmed healthy reference. "
            "Emails stay OFF. Sources and recipients can be adjusted later in options."
        ),
    ]
    return "\n".join(lines)
