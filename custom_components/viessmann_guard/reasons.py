"""Human-readable diagnostic explanations, also exposed in the native dashboard."""

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
        "No confirmed healthy reference; only absolute monitoring is available.",
        "Aucune référence saine confirmée : seule la surveillance du minimum est disponible.",
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


def describe_reason(code: str, language: str) -> str:
    roles = {
        "flow": ("Flow", "Débit"),
        "mode": ("Operating mode", "Mode de fonctionnement"),
        "pump": ("Circulator state", "État du circulateur"),
        "pump_speed": ("Circulator speed", "Vitesse du circulateur"),
        "fault": ("Fault signal", "Signal de défaut"),
    }
    for suffix in ("_stale", "_unavailable"):
        role = code.removesuffix(suffix)
        if code.endswith(suffix) and role in roles:
            en, fr = roles[role]
            if suffix == "_stale":
                return (
                    f"{fr} : mesure trop ancienne."
                    if language == "fr"
                    else f"{en}: report is stale."
                )
            return (
                f"{fr} : mesure manquante, invalide ou indisponible."
                if language == "fr"
                else f"{en}: report is missing, invalid or unavailable."
            )
    pair = REASONS.get(code)
    if pair:
        return pair[1 if language == "fr" else 0]
    # Preserve an unknown future engine reason visibly; never replace it with "healthy".
    return f"{'Diagnostic' if language == 'fr' else 'Diagnosis'}: {code.replace('_', ' ')}"
