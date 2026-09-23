"""Inline-table email presentation shared by SMTP and the local report."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from html import escape
from typing import Any, TypeGuard
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .reasons import describe_reason

_WORDS = {
    "day": ("Day", "Jour", "Día", "Tag"),
    "daily_view": ("Daily median", "Médiane du jour", "Mediana diaria", "Tagesmedian"),
    "fault": (
        "Recorded native fault",
        "Défaut natif enregistré",
        "Fallo nativo registrado",
        "Gespeicherter Gerätefehler",
    ),
    "changed_sources": (
        "Sources or detection settings changed after this capture. No historical comparison is made with the old incident context.",
        "Les sources ou règles ont changé depuis cette capture. Aucune comparaison historique n'est faite avec l'ancien contexte de l'incident.",
        "Las fuentes o reglas cambiaron después de esta captura. No se compara el historial con el contexto anterior del incidente.",
        "Quellen oder Erkennungsregeln wurden seit dieser Aufnahme geändert. Kein historischer Vergleich mit dem alten Vorfallkontext.",
    ),
    "current_minimum": (
        "Compared with the currently configured minimum",
        "Par rapport au minimum actuellement configuré",
        "Respecto al mínimo configurado actualmente",
        "Im Vergleich zum aktuell konfigurierten Mindestwert",
    ),
    "current": ("Current flow", "Débit actuel", "Caudal actual", "Aktueller Durchfluss"),
    "trigger": (
        "Flow at alert trigger",
        "Débit au déclenchement de l'alerte",
        "Caudal al activarse la alerta",
        "Durchfluss bei Alarmauslösung",
    ),
    "reported": ("Reported to HA", "Rapporté à HA", "Notificado a HA", "An HA gemeldet"),
    "decision": ("Alert decision", "Décision d'alerte", "Decisión de alerta", "Alarmentscheidung"),
    "opening": (
        "Incident opened",
        "Ouverture de l'incident",
        "Apertura del incidente",
        "Vorfall eröffnet",
    ),
    "escalation": (
        "Escalated to urgent",
        "Passage en urgence",
        "Escalado a urgente",
        "Auf dringend eskaliert",
    ),
    "closed": (
        "Stable recovery confirmed",
        "Retour stable confirmé",
        "Recuperación estable confirmada",
        "Stabile Erholung bestätigt",
    ),
    "frozen": (
        "Immutable capture for this alert level, not the latest reading.",
        "Capture immuable pour ce niveau d'alerte, distincte de la dernière mesure.",
        "Captura inmutable de este nivel de alerta, no la última lectura.",
        "Unveränderliche Aufnahme dieser Alarmstufe, nicht der neueste Messwert.",
    ),
    "legacy": (
        "Trigger evidence unavailable. The incident may predate this update; current flow is never substituted.",
        "Preuve du déclenchement indisponible. L'incident peut être antérieur à cette mise à jour ; le débit actuel ne la remplace jamais.",
        "Evidencia de activación no disponible. El incidente puede ser anterior a esta actualización; nunca se sustituye por el caudal actual.",
        "Auslösungsdaten nicht verfügbar. Der Vorfall kann vor diesem Update liegen; der aktuelle Durchfluss wird niemals ersatzweise verwendet.",
    ),
    "no_incident": (
        "No captured incident",
        "Aucun incident capturé",
        "Ningún incidente capturado",
        "Kein erfasster Vorfall",
    ),
    "trigger_rule": (
        "Recorded trigger rule",
        "Règle enregistrée au déclenchement",
        "Regla registrada al activarse",
        "Gespeicherte Auslöseregel",
    ),
    "observed": ("Observed duration", "Durée observée", "Duración observada", "Beobachtete Dauer"),
    "since": (
        "Observation window began",
        "Début de la fenêtre observée",
        "Inicio de la ventana observada",
        "Beginn des Beobachtungsfensters",
    ),
    "five_days": (
        "Five calendar days of flow",
        "Cinq jours calendaires de débit",
        "Cinco días naturales de caudal",
        "Fünf Kalendertage Durchfluss",
    ),
    "median": (
        "Sample median",
        "Médiane échantillonnée",
        "Mediana muestreada",
        "Stichprobenmedian",
    ),
    "minimum": (
        "Sample minimum",
        "Minimum échantillonné",
        "Mínimo muestreado",
        "Stichprobenminimum",
    ),
    "partial": ("today, partial", "aujourd'hui, partiel", "hoy, parcial", "heute, unvollständig"),
    "change": (
        "Change between sampled daily medians",
        "Évolution entre médianes journalières échantillonnées",
        "Cambio entre medianas diarias muestreadas",
        "Änderung der täglichen Stichprobenmediane",
    ),
    "range": ("Compared dates", "Dates comparées", "Fechas comparadas", "Verglichene Tage"),
    "insufficient": (
        "Insufficient comparable data for a five-day decline conclusion.",
        "Données comparables insuffisantes pour conclure à une baisse sur cinq jours.",
        "Datos comparables insuficientes para concluir una bajada de cinco días.",
        "Nicht genügend vergleichbare Daten für eine Aussage über einen fünftägigen Rückgang.",
    ),
    "consecutive": (
        "Four consecutive declines in sampled daily medians across the five displayed days. This does not mean every reading decreased.",
        "Quatre baisses consécutives des médianes journalières échantillonnées sur les cinq jours affichés. Cela ne signifie pas que chaque mesure a baissé.",
        "Cuatro bajadas consecutivas de las medianas diarias muestreadas en los cinco días mostrados. No significa que cada lectura haya bajado.",
        "Vier aufeinanderfolgende Rückgänge der täglichen Stichprobenmediane an den fünf angezeigten Tagen. Nicht jeder Einzelwert muss gesunken sein.",
    ),
    "not_continuous": (
        "The displayed daily medians do not establish five consecutive days of decline.",
        "Les médianes affichées n'établissent pas cinq jours consécutifs de baisse.",
        "Las medianas mostradas no demuestran cinco días consecutivos de bajada.",
        "Die angezeigten Mediane belegen keinen Rückgang an fünf aufeinanderfolgenden Tagen.",
    ),
    "coverage": (
        "Comparable sampling slots",
        "Créneaux échantillonnés comparables",
        "Intervalos muestreados comparables",
        "Vergleichbare Abtastintervalle",
    ),
    "method": (
        "Local sampling: at most one fresh eligible observation per UTC minute, evaluated every 15 seconds. No catch-up or interpolation. Medians/minima describe these samples, not all source readings. A daily comparison needs at least two samples per day; low coverage is not proof of representative or uninterrupted operation.",
        "Échantillonnage local : au plus une observation fraîche admissible par minute UTC, évaluée toutes les 15 secondes. Aucun rattrapage ni interpolation. Médianes/minima décrivent ces échantillons, pas toutes les mesures source. Une comparaison journalière exige au moins deux échantillons par jour ; une faible couverture ne prouve pas un fonctionnement représentatif ou ininterrompu.",
        "Muestreo local: como máximo una observación válida y reciente por minuto UTC, evaluada cada 15 segundos. Sin relleno ni interpolación. Medianas/mínimos describen estas muestras, no todas las lecturas. La comparación diaria requiere al menos dos muestras por día; una cobertura baja no prueba un funcionamiento representativo o continuo.",
        "Lokale Abtastung: höchstens eine frische, geeignete Beobachtung pro UTC-Minute, alle 15 Sekunden geprüft. Kein Nachholen oder Interpolieren. Mediane/Minima beschreiben diese Stichproben, nicht alle Quellwerte. Ein Tagesvergleich benötigt mindestens zwei Stichproben je Tag; geringe Abdeckung belegt keinen repräsentativen oder ununterbrochenen Betrieb.",
    ),
    "no_backfill": (
        "No Recorder backfill: historical state changes cannot establish repeated-report freshness. Collection starts with this version; missing days stay unavailable. Coverage counts sampled minute slots, not measured continuous running time.",
        "Aucun rattrapage Recorder : les changements d'état historiques ne prouvent pas la fraîcheur des rapports répétés. La collecte commence avec cette version ; les jours absents restent indisponibles. La couverture compte des créneaux minute échantillonnés, pas une durée continue mesurée.",
        "Sin relleno de Recorder: los cambios históricos no prueban la frescura de informes repetidos. La recopilación empieza con esta versión; los días ausentes siguen sin datos. La cobertura cuenta intervalos de muestreo, no tiempo de funcionamiento continuo medido.",
        "Kein Recorder-Rückimport: historische Zustandsänderungen belegen keine wiederholten frischen Meldungen. Die Erfassung beginnt mit dieser Version; fehlende Tage bleiben ohne Daten. Die Abdeckung zählt Minuten-Stichproben, keine gemessene Dauerbetriebszeit.",
    ),
    "reliability": (
        "A five-day consecutive-decline conclusion additionally requires every elapsed minute slot to be observed, with no unknown or stale context gaps. Otherwise only the available sampled medians are compared.",
        "Une conclusion de baisses consécutives sur cinq jours exige aussi une observation à chaque créneau minute écoulé, sans lacune de contexte inconnu ou périmé. Sinon, seules les médianes échantillonnées disponibles sont comparées.",
        "Una conclusión de bajadas consecutivas en cinco días exige observar cada intervalo de minuto transcurrido, sin lagunas de contexto desconocido u obsoleto. En caso contrario, solo se comparan las medianas muestreadas disponibles.",
        "Eine Aussage über fünf Tage mit aufeinanderfolgenden Rückgängen setzt außerdem eine Beobachtung in jedem abgelaufenen Minutenintervall ohne unbekannte oder veraltete Kontextlücken voraus. Andernfalls werden nur die verfügbaren Stichprobenmediane verglichen.",
    ),
    "scale": (
        "Common scale from zero",
        "Échelle commune à partir de zéro",
        "Escala común desde cero",
        "Gemeinsame Skala ab null",
    ),
    "context": (
        "Comparison context",
        "Contexte de comparaison",
        "Contexto de comparación",
        "Vergleichskontext",
    ),
    "mode": ("Operating mode", "Mode de fonctionnement", "Modo de funcionamiento", "Betriebsart"),
    "pump": (
        "Circulation state",
        "État de circulation",
        "Estado de circulación",
        "Zirkulationszustand",
    ),
    "speed": ("Pump speed", "Vitesse circulateur", "Velocidad de bomba", "Pumpendrehzahl"),
    "speed_missing": (
        "Speed unmeasured: only the configured running mode and circulation state can be matched, not identical hydraulic conditions.",
        "Vitesse non mesurée : seuls le mode actif configuré et l'état de circulation peuvent être comparés, pas des conditions hydrauliques identiques.",
        "Velocidad no medida: solo se comparan el modo activo configurado y el estado de circulación, no condiciones hidráulicas idénticas.",
        "Drehzahl nicht gemessen: nur konfigurierte Betriebsart und Zirkulationszustand sind vergleichbar, keine identischen hydraulischen Bedingungen.",
    ),
    "speed_tolerance": (
        "Speed tolerance (percentage points)",
        "Tolérance de vitesse (points de pourcentage)",
        "Tolerancia de velocidad (puntos porcentuales)",
        "Drehzahltoleranz (Prozentpunkte)",
    ),
    "started": (
        "Local collection started",
        "Début de la collecte locale",
        "Inicio de la recopilación local",
        "Beginn der lokalen Erfassung",
    ),
    "timezone": (
        "Calendar timezone",
        "Fuseau des jours calendaires",
        "Zona horaria del calendario",
        "Kalenderzeitzone",
    ),
    "inspect": (
        "Inspect filters and the hydraulic circuit",
        "Faire inspecter les filtres et le circuit hydraulique",
        "Inspeccionar filtros y circuito hidráulico",
        "Filter und Hydraulikkreis prüfen lassen",
    ),
    "inspection": (
        "Persistent low flow or a decline in comparable sampled medians can justify inspection by a qualified professional. Clean only if fouling is confirmed, following the manufacturer's procedure. A restricted filter is a possibility, not a confirmed diagnosis.",
        "Un débit bas persistant ou une baisse des médianes échantillonnées comparables peut justifier une inspection par un professionnel qualifié. Nettoyer uniquement si l'encrassement est confirmé, selon la procédure du fabricant. Un filtre encrassé est une possibilité, pas un diagnostic confirmé.",
        "Un caudal bajo persistente o una bajada de medianas muestreadas comparables puede justificar la inspección por un profesional cualificado. Limpiar solo si se confirma suciedad, según el fabricante. Un filtro obstruido es una posibilidad, no un diagnóstico confirmado.",
        "Anhaltend niedriger Durchfluss oder sinkende vergleichbare Stichprobenmediane können eine Prüfung durch Fachpersonal rechtfertigen. Nur bei bestätigter Verschmutzung nach Herstellervorgaben reinigen. Ein zugesetzter Filter ist eine Möglichkeit, keine gesicherte Diagnose.",
    ),
    "appendix": (
        "Diagnostic appendix",
        "Annexe de diagnostic",
        "Anexo de diagnóstico",
        "Diagnoseanhang",
    ),
}

BRAND = "#FF3E17"
INK = "#CC2C08"


def finite(value: Any) -> TypeGuard[int | float]:
    return type(value) in (int, float) and math.isfinite(value)


def layout(
    snapshot: dict,
    kind: str,
    language: str,
    title: str,
    label: str,
    copy: dict[str, str],
    scalar: Callable[[Any], str | None],
    sections: list[tuple[str, list[tuple[str, str]]]],
) -> tuple[str, str, str]:
    words = {
        key: values[("en", "fr", "es", "de").index(language)] for key, values in _WORDS.items()
    }
    missing = copy["missing"]

    def text(value: Any) -> str:
        return scalar(value) or missing

    def num(value: Any) -> str:
        if type(value) not in (int, float) or not math.isfinite(value):
            return missing
        result = str(value).removesuffix(".0")
        return result if language == "en" else result.replace(".", ",")

    def measure(value: Any) -> str:
        return (
            f"{num(value)} L/min"
            if type(value) in (int, float) and math.isfinite(value)
            else missing
        )

    try:
        zone = ZoneInfo(snapshot.get("timezone") or "UTC")
    except ZoneInfoNotFoundError, TypeError, ValueError:
        zone = ZoneInfo("UTC")

    def stamp(value: Any) -> str:
        try:
            date = (
                datetime.fromtimestamp(value, UTC)
                if type(value) in (float, int)
                else datetime.fromisoformat(value)
            )
            if date.tzinfo is None:
                return missing
            return f"{date.astimezone(zone).isoformat(timespec='seconds')} ({zone.key})"
        except ValueError, TypeError, OverflowError, OSError:
            return missing

    incident = snapshot.get("incident")
    incident = incident if isinstance(incident, dict) else {}
    capture = snapshot.get("incident_capture")
    capture = capture if isinstance(capture, dict) else {}
    history = snapshot.get("history")
    history = history if isinstance(history, dict) else {}
    days = history.get("days")
    days = days[:5] if isinstance(days, list) and all(isinstance(row, dict) for row in days) else []
    change = history.get("change_pct")
    flow = snapshot.get("flow")
    if finite(flow):
        title += f" | {words['current']}: {measure(flow)}"
    if finite(change):
        title += f" | {words['change']}: {num(round(change, 2))} %"
    title = title[:400]
    front = [
        (words["current"], measure(flow)),
        (words["reported"], stamp(snapshot.get("flow_reported_at"))),
        (words["trigger"], measure(capture.get("flow"))),
        (words["reported"], stamp(capture.get("flow_reported_at"))),
        (words["decision"], stamp(capture.get("decided_at"))),
    ]
    for key, field in (
        ("opening", "opened_at"),
        ("escalation", "escalated_at"),
        ("closed", "closed_at"),
    ):
        if incident.get(field) is not None:
            front.append((words[key], stamp(incident[field])))
    if capture:
        front.extend(
            [
                (words["trigger_rule"], describe_reason(text(capture.get("reason")), language)),
                (words["observed"], f"{num(capture.get('duration_s'))} {copy['seconds']}"),
                (words["since"], stamp(capture.get("observed_since"))),
            ]
        )
        if capture.get("reason") == "absolute_low_flow":
            front.append((copy["minimum"], measure(capture.get("minimum"))))
        if capture.get("reason") == "relative_flow_decline":
            front.extend(
                [
                    (copy["reference"], measure(capture.get("reference"))),
                    (copy["relative_drop_pct"], f"{num(capture.get('relative_drop_pct'))} %"),
                ]
            )
        if capture.get("reason") == "native_fault":
            front.extend(
                [
                    (words["fault"], text(capture.get("fault"))),
                    (words["reported"], stamp(capture.get("fault_reported_at"))),
                ]
            )
    evidence_note = (
        words["frozen"]
        if capture
        else words["legacy"]
        if incident.get("id")
        else words["no_incident"]
    )
    if snapshot.get("incident_source_changed") is True:
        evidence_note += " " + words["changed_sources"]
    minimum = snapshot.get("minimum")
    relation = None
    if finite(minimum) and minimum > 0 and finite(flow):
        difference = (flow / minimum - 1) * 100
        if math.isfinite(difference):
            relation = (
                f"{words['current_minimum']}: {num(round(difference, 2))} % ({measure(minimum)})"
            )
    sufficient = len(days) == 5 and all(row.get("reliable") is True for row in days)
    conclusion = (
        words["consecutive"]
        if sufficient and history.get("consecutive_declines") == 4
        else words["not_continuous"]
        if sufficient
        else words["insufficient"]
    )
    history_rows = [
        (words["timezone"], text(history.get("timezone") or zone.key)),
        (words["started"], stamp(history.get("started_at"))),
        (
            words["change"],
            f"{num(round(change, 2))} %" if finite(change) else missing,
        ),
        (words["range"], f"{text(history.get('first_date'))} / {text(history.get('last_date'))}"),
    ]
    anchor = history.get("anchor")
    anchor = anchor if isinstance(anchor, dict) else {}
    context = [
        (words["mode"], text(anchor.get("mode"))),
        (words["pump"], text(anchor.get("pump"))),
        (
            words["speed"],
            f"{num(anchor['pump_speed'])} %" if anchor.get("pump_speed") is not None else missing,
        ),
        (words["speed_tolerance"], num(history.get("speed_tolerance"))),
    ]
    extra = [(words["current"], front), (words["five_days"], history_rows)]
    plain = [title, evidence_note]
    if relation:
        plain.append(relation)
    for heading, rows in extra:
        plain.extend(["", heading, *(f"{key}: {value}" for key, value in rows)])
    maximum = max(
        (
            row["median"]
            for row in days
            if type(row.get("median")) in (int, float)
            and math.isfinite(row["median"])
            and row["median"] >= 0
        ),
        default=0,
    )
    plain.extend(f"{key}: {value}" for key, value in context)
    chart = []
    for row in days:
        day = text(row.get("date")) + (
            f" ({words['partial']})" if row.get("partial") is True else ""
        )
        value = row.get("median")
        width = (
            min(100.0, max(0.0, value / maximum * 100))
            if type(value) in (int, float) and math.isfinite(value) and maximum > 0
            else 0
        )
        coverage = f"{num(row.get('samples'))}/{num(row.get('expected_slots'))}"
        day_detail = f"{words['median']}: {measure(value)}; {words['minimum']}: {measure(row.get('minimum'))}"
        plain.append(f"{day}: {day_detail}; {words['coverage']}: {coverage}")
        bar = (
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td style="height:14px;background:{BRAND};width:{width:.6f}%"></td>'
            f'<td style="height:14px;background:#e9e7e4;width:{100 - width:.6f}%"></td></tr></table>'
            if width > 0
            else '<div style="height:14px;background:#e9e7e4"></div>'
        )
        chart.append(
            f'<tr><th scope="row" style="text-align:left;padding:14px 8px 14px 0;font-size:12px;border-bottom:1px solid #e9e7e4">{escape(day)}</th>'
            f'<td style="padding:14px 6px;border-bottom:1px solid #e9e7e4">{bar}</td>'
            f'<td style="padding:14px 4px;text-align:right;font-size:13px;border-bottom:1px solid #e9e7e4">{escape(num(value))}</td>'
            f'<td style="padding:14px 0 14px 4px;text-align:right;font-size:13px;border-bottom:1px solid #e9e7e4">{escape(num(row.get("minimum")))}</td></tr>'
            f'<tr><td colspan="4" style="font-size:11px">{escape(words["coverage"])}: {escape(coverage)}</td></tr>'
        )
    scale = f"{words['scale']}: 0 / {measure(maximum)}" if maximum else words["insufficient"]
    notes = [scale, conclusion, words["method"], words["reliability"], words["no_backfill"]]
    if not anchor.get("speed_configured"):
        notes.append(words["speed_missing"])
    plain.extend(notes)
    plain.extend(["", words["inspect"], words["inspection"], copy["alternatives_text"]])
    plain.extend(["", words["appendix"]])
    for heading, rows in sections:
        plain.extend(
            ["", heading, *(f"{key}: {value}" if key else value for key, value in rows)]
            if rows
            else ["", heading, missing]
        )

    def pairs(rows: list[tuple[str, str]]) -> str:
        return "".join(
            f'<p style="margin:8px 0;font-size:14px;overflow-wrap:anywhere"><strong>{escape(key)}:</strong> {escape(value)}</p>'
            for key, value in rows
        )

    appendix = "".join(
        f'<h3 style="font-size:17px;margin:26px 0 8px">{escape(heading)}</h3>{pairs(rows) if rows else escape(missing)}'
        for heading, rows in sections
    )
    markup = (
        f'<!DOCTYPE html><html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>@media(max-width:600px){{.guard-pad{{padding:22px!important}}.guard-kpi{{display:block!important;width:auto!important}}.guard-title{{font-size:30px!important}}}}"
        "@media(prefers-color-scheme:dark){.guard-body{background:#171717!important;color:#f3f0ec!important}.guard-card{background:#242424!important;color:#f3f0ec!important}.guard-panel{background:#302723!important;color:#f3f0ec!important}.guard-accent{color:#ff8065!important}}</style></head>"
        '<body class="guard-body" style="margin:0;background:#f3f1ee;color:#262626;font-family:Arial,Helvetica,sans-serif;line-height:1.5">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:24px 10px">'
        f'<table role="presentation" class="guard-card" width="100%" cellspacing="0" cellpadding="0" style="max-width:780px;table-layout:fixed;background:white;border-top:6px solid {BRAND};border-radius:18px"><tr><td class="guard-pad" style="padding:40px;overflow-wrap:anywhere">'
        f'<table role="presentation" width="100%"><tr><td class="guard-accent" style="font-size:16px;font-weight:bold;color:{INK}">VIESSMANN GUARD</td><td style="text-align:right;font-size:12px">{escape(label)}</td></tr></table>'
        f'<h1 class="guard-title" style="font-size:40px;line-height:1.1;letter-spacing:-1px;margin:24px 0">{escape(label)}</h1>'
        f'<p style="font-size:14px">{escape(text(snapshot.get("name")))}</p>'
        f'<p style="font-size:13px">{escape(copy["generated_at"])}: {escape(stamp(snapshot.get("generated_at")))}</p>'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="table-layout:fixed;margin:24px 0"><tr>'
        f'<td class="guard-kpi guard-panel" width="50%" style="vertical-align:top;background:#fff1ed;padding:22px;border-radius:12px">'
        f'<strong>{escape(words["current"])}</strong><p class="guard-accent" style="font-size:34px;line-height:1.2;color:{INK};font-weight:bold;margin:12px 0">{escape(measure(flow))}</p>'
        f'<p style="font-size:12px">{escape(words["reported"])}<br>{escape(stamp(snapshot.get("flow_reported_at")))}</p></td>'
        f'<td class="guard-kpi guard-panel" width="50%" style="vertical-align:top;background:#f6f5f3;padding:22px;border-radius:12px">'
        f'<strong>{escape(words["trigger"])}</strong><p style="font-size:34px;line-height:1.2;font-weight:bold;margin:12px 0">{escape(measure(capture.get("flow")))}</p>'
        f'<p style="font-size:12px">{escape(words["reported"])}<br>{escape(stamp(capture.get("flow_reported_at")))}</p></td></tr></table>'
        f'<p style="font-size:13px">{escape(relation) if relation else ""}</p>'
        f'<p style="font-size:13px">{escape(evidence_note)}</p>{pairs(front[4:])}'
        f'<h2 style="font-size:27px;margin:32px 0 10px">{escape(words["five_days"])}</h2>{pairs(history_rows)}'
        f'<p class="guard-accent" style="font-size:40px;font-weight:bold;color:{INK};margin:12px 0">{escape(num(round(change, 2)) + " %" if finite(change) else missing)}</p>'
        f'<table width="100%" cellspacing="0" cellpadding="0" style="table-layout:fixed;overflow-wrap:anywhere"><caption style="text-align:left;font-size:12px">{escape(scale)}</caption>'
        f'<thead><tr><th scope="col" width="24%" style="text-align:left;font-size:11px">{escape(words["day"])}</th><th scope="col" width="38%" style="font-size:11px">{escape(words["daily_view"])}</th>'
        f'<th scope="col" width="19%" style="text-align:right;font-size:11px">{escape(words["median"])}<br>L/min</th><th scope="col" width="19%" style="text-align:right;font-size:11px">{escape(words["minimum"])}<br>L/min</th></tr></thead><tbody>{"".join(chart)}</tbody></table>'
        f'<p><strong>{escape(conclusion)}</strong></p><h3 style="font-size:16px">{escape(words["context"])}</h3>{pairs(context)}'
        + "".join(f'<p style="font-size:12px">{escape(note)}</p>' for note in notes[2:])
        + f'<table role="presentation" class="guard-panel" width="100%" cellspacing="0" cellpadding="0" style="background:#fff1ed;border-left:4px solid {BRAND};margin:28px 0"><tr><td style="padding:20px">'
        f'<h2 style="font-size:20px;margin:0 0 10px">{escape(words["inspect"])}</h2><p>{escape(words["inspection"])}</p><p style="font-size:13px">{escape(copy["alternatives_text"])}</p></td></tr></table>'
        f'<h2 style="font-size:25px">{escape(words["appendix"])}</h2>{appendix}'
        "</td></tr></table></td></tr></table></body></html>"
    )
    return title, "\n".join(plain), markup
