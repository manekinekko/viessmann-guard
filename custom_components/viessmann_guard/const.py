"""Shared configuration and entity definitions."""

DOMAIN = "viessmann_guard"
PLATFORMS = ["sensor", "switch", "button"]
MIN_HA_VERSION = "2026.8.3"
MAX_RECIPIENTS = 20
MAX_REPORT_ENTITIES = 150
TEMPERATURE_UNITS = frozenset(("°C", "°F", "K"))
PRESSURE_UNITS = frozenset(
    ("Pa", "hPa", "kPa", "MPa", "bar", "mbar", "cbar", "psi", "inHg", "mmHg")
)

SOURCE_ROLES = (
    "flow",
    "mode",
    "pump",
    "pump_speed",
    "fault",
    "supply_temperature",
    "return_temperature",
    "pressure",
    "outside_temperature",
    "compressor",
    "valve",
)
REQUIRED_ROLES = ("flow", "mode")
LIST_SETTINGS = (
    "running_modes",
    "idle_modes",
    "excluded_modes",
    "pump_on_values",
    "pump_off_values",
    "fault_values",
    "fault_clear_values",
)
NUMERIC_RULES = {
    "absolute_persistence_s": (180, 1, 86400),
    "relative_drop_pct": (25, 1, 90),
    "relative_persistence_s": (1800, 1, 604800),
    "hysteresis_pct": (10, 0.1, 50),
    "recovery_s": (300, 1, 86400),
    "startup_grace_s": (180, 0, 3600),
    "stale_after_s": (180, 10, 86400),
    "calibration_samples": (10, 3, 1000),
    "calibration_duration_s": (600, 60, 86400),
    "pump_tolerance_pct": (5, 0, 50),
}
EMAIL_DEFAULTS = {
    "emails_enabled": False,
    "recipients": [],
    "reminder_hours": 24,
    "watch_email": False,
    "language": "en",
}

LANGUAGES = ("en", "fr", "es", "de")


def normalize_language(value: object) -> str:
    if not isinstance(value, str):
        return "en"
    language = value.lower().replace("_", "-").split("-")[0]
    return language if language in LANGUAGES else "en"


SAFE_DEVICE_CLASSES = frozenset(
    (
        "temperature",
        "pressure",
        "volume_flow_rate",
        "power",
        "energy",
        "current",
        "voltage",
        "frequency",
        "duration",
        "volume",
        "water",
        "energy_storage",
        "power_factor",
    )
)
PRIVATE_NAME_PARTS = (
    "serial",
    "token",
    "password",
    "secret",
    "address",
    "latitude",
    "longitude",
    "location",
    "credential",
    "ssid",
    "mac_address",
    "ip_address",
    "email",
)


def public_state(state: str, incident_active: bool = False) -> str:
    """Reduce engine phases to the five user-facing diagnostic states."""
    if incident_active and state not in ("urgent", "watch"):
        return "diagnostic_unavailable"
    return {
        "idle": "normal",
        "excluded": "diagnostic_unavailable",
        "startup": "learning",
        "calibrating": "learning",
    }.get(state, state)
