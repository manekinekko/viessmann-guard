"""Human-readable diagnostic explanations, also exposed in the native dashboard."""

from .const import normalize_language

REASON_CODES = (
    "awaiting_observations",
    "minimum_not_configured",
    "awaiting_post_restart_reports",
    "clock_moved_backwards",
    "flow_unavailable",
    "flow_stale",
    "flow_invalid",
    "flow_out_of_order",
    "flow_changed_without_report",
    "mode_unavailable",
    "mode_stale",
    "mode_unmapped",
    "mode_idle",
    "mode_excluded",
    "pump_not_configured",
    "pump_unavailable",
    "pump_stale",
    "pump_unmapped",
    "pump_off",
    "pump_speed_unavailable",
    "pump_speed_stale",
    "pump_speed_invalid",
    "fault_unavailable",
    "fault_stale",
    "fault_unmapped",
    "native_fault",
    "startup_grace",
    "baseline_unconfirmed",
    "baseline_context_mismatch",
    "absolute_low_pending",
    "absolute_low_flow",
    "relative_decline_pending",
    "relative_flow_decline",
    "incident_pending_revalidation",
    "recovery_pending",
    "recovery_hysteresis",
    "healthy",
    "calibration_sampling",
    "calibration_complete",
    "calibration_cancelled_by_cleaning",
)

REASONS: dict[str, tuple[str, str]] = {
    "minimum_not_configured": (
        "Observation / relative monitoring only: the installation's minimum flow has not been set. Absolute low-flow alerts are disabled.",
        "Observation / suivi relatif uniquement : débit minimum de l'installation non renseigné. Alertes de débit absolu désactivées.",
    ),
    "awaiting_observations": ("Waiting for source reports.", "Attente des mesures des sources."),
    "mode_idle": (
        "Heat pump is idle; no low-flow diagnosis.",
        "PAC au repos : aucun diagnostic de débit faible.",
    ),
    "mode_excluded": (
        "Excluded mode or defrost; heuristic monitoring paused.",
        "Mode exclu ou dégivrage : surveillance heuristique suspendue.",
    ),
    "mode_unmapped": (
        "Map this operating mode before enabling diagnosis.",
        "Associez ce mode de fonctionnement pour permettre le diagnostic.",
    ),
    "pump_unmapped": (
        "Circulator state is not mapped; diagnosis unavailable.",
        "État du circulateur non reconnu : diagnostic indisponible.",
    ),
    "pump_not_configured": (
        "Select a circulator-running source to establish eligible operation.",
        "Sélectionnez une source d'état du circulateur pour confirmer son fonctionnement.",
    ),
    "pump_speed_invalid": (
        "Circulator speed must be a finite percentage from 0 to 100.",
        "La vitesse du circulateur doit être un pourcentage fini entre 0 et 100.",
    ),
    "fault_unmapped": (
        "Unmapped fault state; no assumption that this is a flow fault.",
        "État de défaut non reconnu : aucune association automatique à un défaut de débit.",
    ),
    "native_fault": (
        "An explicitly mapped native flow fault is active.",
        "Un défaut natif explicitement associé au débit est actif.",
    ),
    "relative_flow_decline": (
        "Persistent flow decline against a comparable healthy reference.",
        "Baisse durable du débit par rapport à une référence saine comparable.",
    ),
    "absolute_low_pending": (
        "Low flow observed; configured persistence period not yet confirmed.",
        "Débit faible observé : la durée de persistance configurée n'est pas encore confirmée.",
    ),
    "relative_decline_pending": (
        "Flow decline observed; configured persistence period not yet confirmed.",
        "Baisse du débit observée : la durée de persistance configurée n'est pas encore confirmée.",
    ),
    "baseline_unconfirmed": (
        "No confirmed healthy reference; relative monitoring is unavailable.",
        "Aucune référence saine confirmée : surveillance relative indisponible.",
    ),
    "baseline_context_mismatch": (
        "Reference not comparable in this mode or circulator condition.",
        "Référence non comparable dans ce mode ou à cette vitesse de circulation.",
    ),
    "calibration_sampling": (
        "Collecting representative healthy samples after your confirmation.",
        "Collecte de mesures saines représentatives après votre confirmation.",
    ),
    "calibration_complete": (
        "Healthy reference established and frozen.",
        "Référence saine établie et figée.",
    ),
    "calibration_cancelled_by_cleaning": (
        "Cleaning recorded; pending calibration cancelled, existing reference preserved.",
        "Nettoyage enregistré : étalonnage en cours annulé, référence existante conservée.",
    ),
    "recovery_pending": (
        "Healthy measurements observed; waiting for stable recovery.",
        "Mesures saines observées : attente d'un rétablissement stable.",
    ),
    "recovery_hysteresis": (
        "Incident retained until measurements exceed the recovery margin.",
        "Incident maintenu jusqu'au dépassement de la marge de rétablissement.",
    ),
    "incident_pending_revalidation": (
        "Stored incident awaiting fresh confirmation; no downtime counted.",
        "Incident enregistré en attente de confirmation par de nouvelles mesures, sans compter l'arrêt.",
    ),
    "awaiting_post_restart_reports": (
        "Waiting for fresh reports after restart.",
        "Attente de nouvelles mesures après le redémarrage.",
    ),
    "clock_moved_backwards": (
        "Clock moved backwards; observation timers restarted.",
        "L'horloge a reculé : temporisations d'observation réinitialisées.",
    ),
    "flow_invalid": (
        "Flow is invalid or its unit is unsupported.",
        "Débit invalide ou unité non prise en charge.",
    ),
    "flow_out_of_order": (
        "Flow timestamp moved backwards; diagnosis paused.",
        "L'horodatage du débit a reculé : diagnostic suspendu.",
    ),
    "flow_changed_without_report": (
        "Flow changed without a new report timestamp.",
        "Le débit a changé sans nouvel horodatage de mesure.",
    ),
    "startup_grace": (
        "Waiting for stable circulation after startup or an operating-context change.",
        "Attente d'une circulation stable après un démarrage ou un changement de fonctionnement.",
    ),
    "idle": (
        "Heat pump is idle; no low-flow diagnosis.",
        "PAC au repos : aucun diagnostic de débit faible.",
    ),
    "pump_off": (
        "Circulator is stopped; no low-flow diagnosis.",
        "Circulateur arrêté : aucun diagnostic de débit faible.",
    ),
    "unknown_mode": (
        "Operating mode is not mapped; diagnosis unavailable.",
        "Mode de fonctionnement non reconnu : diagnostic indisponible.",
    ),
    "excluded_mode": (
        "Excluded mode or defrost; heuristic diagnosis paused.",
        "Mode exclu ou dégivrage : analyse heuristique suspendue.",
    ),
    "native_flow_fault": (
        "An explicitly mapped native flow fault is active.",
        "Un défaut natif explicitement associé au débit est actif.",
    ),
    "absolute_low_flow": (
        "Persistent flow below the installer-supplied minimum.",
        "Débit durablement inférieur au minimum fourni par l'installateur.",
    ),
    "relative_degradation": (
        "Persistent flow decline against the confirmed healthy reference.",
        "Baisse durable du débit par rapport à la référence saine confirmée.",
    ),
    "healthy": (
        "Stable measurements meet the configured recovery criteria.",
        "Mesures stables conformes aux critères de rétablissement configurés.",
    ),
    "calibrating": (
        "Collecting representative healthy samples after your confirmation.",
        "Collecte de mesures saines représentatives après votre confirmation.",
    ),
    "baseline_required": (
        "No confirmed healthy reference. Absolute monitoring remains available.",
        "Aucune référence saine confirmée. La surveillance du minimum reste disponible.",
    ),
    "awaiting_fresh_report": (
        "Waiting for fresh source reports after startup.",
        "Attente de nouvelles mesures des sources après le démarrage.",
    ),
}

TRANSLATED_REASONS = {
    "es": {
        "awaiting_observations": "Esperando informes de las fuentes.",
        "minimum_not_configured": "Solo observación / seguimiento relativo: no se ha configurado el caudal mínimo. Las alertas absolutas están desactivadas.",
        "awaiting_post_restart_reports": "Esperando informes nuevos tras el reinicio.",
        "clock_moved_backwards": "El reloj ha retrocedido; se reinician los tiempos de observación.",
        "flow_invalid": "El caudal no es válido o su unidad no es compatible.",
        "flow_out_of_order": "La marca de tiempo del caudal ha retrocedido; diagnóstico en pausa.",
        "flow_changed_without_report": "El caudal cambió sin una nueva marca de tiempo.",
        "mode_unmapped": "Modo de funcionamiento sin correspondencia; diagnóstico no disponible.",
        "mode_idle": "La bomba de calor está en reposo; no se diagnostica caudal bajo.",
        "mode_excluded": "Modo excluido o desescarche; seguimiento heurístico en pausa.",
        "pump_not_configured": "Seleccione una fuente de estado del circulador para confirmar que funciona.",
        "pump_unmapped": "Estado del circulador sin correspondencia; diagnóstico no disponible.",
        "pump_off": "El circulador está parado; no se diagnostica caudal bajo.",
        "pump_speed_invalid": "La velocidad del circulador debe ser un porcentaje finito entre 0 y 100.",
        "fault_unmapped": "Estado de fallo sin correspondencia; no se supone que sea un fallo de caudal.",
        "native_fault": "Hay un fallo nativo asociado explícitamente al caudal; su causa requiere investigación.",
        "startup_grace": "Esperando circulación estable tras el arranque o un cambio de contexto.",
        "baseline_unconfirmed": "No hay una referencia saludable confirmada; el seguimiento relativo no está disponible.",
        "baseline_context_mismatch": "La referencia no es comparable con este modo o velocidad del circulador.",
        "absolute_low_pending": "Caudal bajo observado; aún no se cumple la duración configurada.",
        "absolute_low_flow": "Caudal persistentemente inferior al mínimo de la instalación.",
        "relative_decline_pending": "Descenso observado; aún no se cumple la duración configurada.",
        "relative_flow_decline": "Descenso persistente respecto a una referencia saludable comparable.",
        "incident_pending_revalidation": "Incidente guardado pendiente de confirmación reciente; no se cuenta el tiempo sin observación.",
        "recovery_pending": "Mediciones saludables observadas; esperando recuperación estable.",
        "recovery_hysteresis": "El incidente se conserva hasta superar el margen de recuperación.",
        "healthy": "Las mediciones comparables cumplen los criterios de recuperación configurados.",
        "calibration_sampling": "Recopilando muestras saludables representativas tras su confirmación.",
        "calibration_complete": "Referencia saludable establecida y fijada.",
        "calibration_cancelled_by_cleaning": "Limpieza registrada; calibración pendiente cancelada y referencia existente conservada.",
    },
    "de": {
        "awaiting_observations": "Warten auf Meldungen der Quellen.",
        "minimum_not_configured": "Nur Beobachtung / relative Überwachung: Mindestdurchfluss nicht festgelegt. Absolute Warnungen sind deaktiviert.",
        "awaiting_post_restart_reports": "Warten auf neue Meldungen nach dem Neustart.",
        "clock_moved_backwards": "Die Uhr wurde zurückgestellt; Beobachtungszeiten werden neu gestartet.",
        "flow_invalid": "Durchfluss ungültig oder Einheit nicht unterstützt.",
        "flow_out_of_order": "Der Durchflusszeitstempel liegt vor dem vorherigen; Diagnose pausiert.",
        "flow_changed_without_report": "Durchfluss ohne neuen Meldungszeitstempel geändert.",
        "mode_unmapped": "Betriebsart nicht zugeordnet; Diagnose nicht verfügbar.",
        "mode_idle": "Wärmepumpe im Leerlauf; keine Diagnose eines niedrigen Durchflusses.",
        "mode_excluded": "Ausgeschlossene Betriebsart oder Abtauung; heuristische Überwachung pausiert.",
        "pump_not_configured": "Wählen Sie eine Statusquelle der Umwälzpumpe, um deren Betrieb zu bestätigen.",
        "pump_unmapped": "Status der Umwälzpumpe nicht zugeordnet; Diagnose nicht verfügbar.",
        "pump_off": "Umwälzpumpe steht; keine Diagnose eines niedrigen Durchflusses.",
        "pump_speed_invalid": "Die Pumpendrehzahl muss ein endlicher Prozentwert zwischen 0 und 100 sein.",
        "fault_unmapped": "Fehlerstatus nicht zugeordnet; ein Durchflussfehler wird nicht unterstellt.",
        "native_fault": "Ein ausdrücklich zugeordneter nativer Durchflussfehler ist aktiv; die Ursache muss untersucht werden.",
        "startup_grace": "Warten auf stabile Zirkulation nach dem Start oder einem Kontextwechsel.",
        "baseline_unconfirmed": "Keine bestätigte gesunde Referenz; relative Überwachung nicht verfügbar.",
        "baseline_context_mismatch": "Referenz für diese Betriebsart oder Pumpendrehzahl nicht vergleichbar.",
        "absolute_low_pending": "Niedriger Durchfluss beobachtet; festgelegte Dauer noch nicht erreicht.",
        "absolute_low_flow": "Durchfluss dauerhaft unter dem Mindestwert der Anlage.",
        "relative_decline_pending": "Rückgang beobachtet; festgelegte Dauer noch nicht erreicht.",
        "relative_flow_decline": "Dauerhafter Rückgang gegenüber einer vergleichbaren gesunden Referenz.",
        "incident_pending_revalidation": "Gespeicherter Vorfall wartet auf neue Bestätigung; Ausfallzeiten werden nicht mitgezählt.",
        "recovery_pending": "Gesunde Messwerte beobachtet; Warten auf stabile Erholung.",
        "recovery_hysteresis": "Vorfall bleibt bestehen, bis die Erholungsmarge überschritten wird.",
        "healthy": "Vergleichbare Messwerte erfüllen die festgelegten Erholungskriterien.",
        "calibration_sampling": "Nach Ihrer Bestätigung werden repräsentative gesunde Messwerte gesammelt.",
        "calibration_complete": "Gesunde Referenz erstellt und festgeschrieben.",
        "calibration_cancelled_by_cleaning": "Reinigung erfasst; laufende Kalibrierung beendet, vorhandene Referenz beibehalten.",
    },
}


def describe_reason(code: str, language: str) -> str:
    language = normalize_language(language)
    code = {
        "idle": "mode_idle",
        "unknown_mode": "mode_unmapped",
        "excluded_mode": "mode_excluded",
        "native_flow_fault": "native_fault",
        "relative_degradation": "relative_flow_decline",
        "calibrating": "calibration_sampling",
        "baseline_required": "baseline_unconfirmed",
        "awaiting_fresh_report": "awaiting_post_restart_reports",
    }.get(code, code)
    index = ("en", "fr", "es", "de").index(language)
    roles = {
        "flow": ("Flow", "Débit", "Caudal", "Durchfluss"),
        "mode": (
            "Operating mode",
            "Mode de fonctionnement",
            "Modo de funcionamiento",
            "Betriebsart",
        ),
        "pump": (
            "Circulator state",
            "État du circulateur",
            "Estado del circulador",
            "Umwälzpumpenstatus",
        ),
        "pump_speed": (
            "Circulator speed",
            "Vitesse du circulateur",
            "Velocidad del circulador",
            "Pumpendrehzahl",
        ),
        "fault": ("Fault signal", "Signal de défaut", "Señal de fallo", "Fehlersignal"),
    }
    for suffix in ("_stale", "_unavailable"):
        role = code.removesuffix(suffix)
        if code.endswith(suffix) and role in roles:
            detail = (
                (
                    "report is stale.",
                    "mesure trop ancienne.",
                    "informe demasiado antiguo.",
                    "Meldung veraltet.",
                )
                if suffix == "_stale"
                else (
                    "report is missing, invalid or unavailable.",
                    "mesure manquante, invalide ou indisponible.",
                    "informe ausente, inválido o no disponible.",
                    "Meldung fehlt, ist ungültig oder nicht verfügbar.",
                )
            )
            return f"{roles[role][index]}: {detail[index]}"
    if language in TRANSLATED_REASONS and code in TRANSLATED_REASONS[language]:
        return TRANSLATED_REASONS[language][code]
    pair = REASONS.get(code)
    if pair:
        return pair[1 if language == "fr" else 0]
    # Preserve an unknown future engine reason visibly; never replace it with "healthy".
    return f"{('Diagnosis', 'Diagnostic', 'Diagnóstico', 'Diagnose')[index]}: {code}"
