# Architecture

Viessmann Guard is a read-only Home Assistant service integration. It consumes existing
entity reports, evaluates conservative flow rules, keeps incident and delivery
state, and publishes native HA entities. It neither polls Viessmann nor issues
heat-pump commands. A browser is not part of the monitoring loop.

## Boundaries

| Layer | Responsibility |
| --- | --- |
| Configuration | Explicit device/source mapping, validated rules, native SMTP recipient selection, report scope |
| Telemetry | Device-scoped inventory, typed measurements, unit conversion, per-measurement freshness |
| Detection | Eligibility, sustained low flow/relative decline, fixed calibration, hysteresis, recovery |
| Persistence | Versioned local state for the reference, incidents, maintenance, and delivery bookkeeping |
| Delivery | Per-recipient dispatch, deduplication, backoff, cancellation and uncertain-result handling |
| HA entities/actions | Readable state and diagnostics, persistent email switch, explicit user actions |
| Dashboard | Optional presentation using built-in cards and existing entities |

Unsupported stored engine versions are rejected explicitly rather than
silently discarding an existing reference or incident history.

## Captured evidence and calendar history

Payload schema 2 / engine schema 2 accept schema-1 state explicitly. Missing
legacy `opening`/`escalation` evidence becomes `None`; current flow and old
120-point trends never supply a synthetic trigger. Initial and urgent-escalation
captures hold decision and source-report timestamps, canonical flow, rule,
observed duration/window, threshold/reference, native fault and normalized
mode/pump/speed context. One most recently closed incident is retained for the
recovery report. Serialization is detached and captures stay immutable.
No schema migration changes delivery permission, IDs, queues or entry options.
HA's Store envelope and config-entry versions are unchanged.

`history.py` observes at most once per UTC minute, on the first normal runtime
evaluation in that bucket. The existing timer runs every 15 seconds. Each row
stores observation/report times, eligible flow or a gap, raw normalized
mode/pump/speed, whether speed was configured, and quality. Fresh repeated
values can occupy successive slots within the freshness bound, but cannot
advance the engine's distinct-report evidence counters. No missed bucket is
filled and startup/restored/stale/excluded observations cannot become evidence.
Samples are pruned at six days and 8,641 rows; compact array serialization
avoids repeating field names. Atomic HA Store writes occur about every five
minutes for samples, immediately for durable engine/delivery changes, and on
unload. No extra background task or Recorder dependency is created.

The summary uses HA's IANA timezone to establish the last five local dates,
including today's partial window; UTC bucket cadence survives DST's 23/25-hour
days. The fixed anchor is the alert-level capture (or current eligible context
without a capture), never chained speed tolerances between neighboring samples.
Mode, pump state and optional speed must match. Coverage counts eligible
comparable sampled minute slots over elapsed wall-clock slots, not continuous
operation. Medians and minima are exact for that sampled set. At least two
samples per compared day support a first/last median percentage, with explicit
dates and a nonzero denominator. Five consecutive sampled daily medians are
necessary for the consecutive-decline label; missing days prohibit it.
Coverage and missing speed remain visible limitations, not claims of certainty.
The five-day consecutive label additionally requires every elapsed minute slot
to be observed without unknown/stale context gaps; sparse sampled medians alone
do not qualify. Known idle/excluded/startup intervals remain gaps in flow but
can account for an observed slot without asserting running time.

Source/rule fingerprint changes clear incompatible local samples; registry UUID
renames preserve them. Captures retain the original fingerprint so an old
incident cannot be compared against new-source samples. Summary caching is per
runtime, minute and context, invalidated on collection. There is no per-recipient
database query. New telemetry is rendered at actual dispatch, while capture and
chosen email language retain their existing contracts.

Recorder investigation on both supported HA versions found
`history.get_significant_states` returns state changes, and
`Recorder._process_state_changed_event_into_session` updates the previous state's
`last_reported_ts` endpoint. It does not preserve the full unchanged-report
cadence needed to infer all historical freshness gaps. Therefore Guard does not
backfill or query Recorder for this feature. Disabled Recorder, excluded
entities, limited retention and database errors cannot block urgent mail.

`email_layout.py` applies the approved red inline-table layout to the shared
SMTP/local report snapshot. The subject, plain text and HTML cover all four
languages. It contains no client-side code, remote images or CID pipeline.
The entire allowlisted appendix remains available. Historical sampling adds no
new detection rule, automatic calibration, device control or SMTP permission.

## Configuration contract

The initial `user` dispatches to a zero-field `confirm` for one native ViCare
candidate, or `select_device` (native list) then `confirm` for multiple candidates.
With no recognized candidate, `user` offers secondary manual setup:
`manual`, `rules`, `emails`, `report`. Options independently offer `minimum`,
`sources`, `rules`, `emails`, and `report`. Options and the email switch share
the same persistent configuration.

`discovery.py` matches the native ViCare descriptor keys, translation keys,
domain and unique-ID suffix after the exact registered device identifier.
Fixtures check those contracts against each installed HA version's source.
Device membership and config-entry ownership, not model/friendly name, define
scope. A gateway alone is not a PAC candidate. Devices are deliberately not
merged merely because they share a `via_device_id` link or account.
Unverified split-device configurations require manual mapping.

Global `volumetric_flow`, compressor `compressor_phase-<id>` and heating-circuit
`circulationpump_active-<id>` are the main roles. Heating/cooling are eligible;
off is idle; defrost and unknown phases cannot form healthy evidence. DHW pumps,
DHW selectors and climate `auto` never substitute. No generic `device_error`
mapping is used for low-flow diagnosis. Multiple role candidates are ambiguous
even if one is disabled. No upstream registry is changed.

Config entries remain major version 1, minor version 3. Migration adds registry
UUID bindings without replacing data/options, thresholds or email permission.
Bindings follow entity renames and report exclusions; source identity, not the
renameable entity ID, enters the baseline fingerprint. Legacy unchanged
fingerprints remain compatible. Explicit source/rule changes still invalidate
the baseline, preserving unresolved incidents and maintenance history.

### Sources

`name` identifies the monitor. `device_ids` is a nonempty list of existing HA
devices. The source roles are:

| Field | Required at setup | Interpretation |
| --- | --- | --- |
| `flow_entity` | Manual path only | Numeric volumetric flow with an explicit supported unit |
| `mode_entity` | Manual path only | Raw operating state matched against configured mode sets |
| `pump_entity` | No | Pump-running status; necessary for active flow diagnosis |
| `pump_speed_entity` | No | Numeric value from 0 to 100, explicitly in `%` |
| `fault_entity` | No | Fault status, with both fault and clear mappings |
| `supply_temperature_entity` | No | Supply temperature |
| `return_temperature_entity` | No | Return temperature |
| `pressure_entity` | No | Hydraulic pressure |
| `outside_temperature_entity` | No | Outdoor temperature |
| `compressor_entity` | No | Compressor telemetry |
| `valve_entity` | No | Valve telemetry |

Source entities must be enabled, belong to selected devices, and use a
supported source domain (`sensor`, `binary_sensor`, `select`, `climate`, or
`number`). Explicit `number` sources are read-only; no value-setting action is
sent.
Guard's own entities are not valid inputs. Manual source selection rejects
unavailable evidence and invalid units. Quick setup can retain a recognized
unavailable source, explicitly exposing limited observation until reports
become usable; disabled/ambiguous sources stay unmapped.

Flow is normalized to litres per minute for comparison. Supported explicit
units are `L/min`, `L/h`, `m³/h` (or `m3/h`), `m³/s` (or `m3/s`), and
`US gal/min`, matched case-insensitively after trimming whitespace. Ambiguous
`gal/min` is not accepted. Unsupported or absent units are invalid; a
temperature or arbitrary numeric entity must not be accepted as flow.
Optional speed allows a tighter comparability check, but
must not substitute for a pump-running source. A missing pump mapping leaves
active diagnosis unavailable.

### Rules

`min_flow_l_min` has no installation-independent default. The following are
software defaults and validation bounds, **not manufacturer recommendations**.
Seconds mean elapsed observation time, not a prescribed controller sampling
rate.

| Option | Default | Allowed range |
| --- | --- | --- |
| `min_flow_l_min` | Absent (`None`) | Optional; 0.001 to 100000 L/min when supplied |
| `absolute_persistence_s` | 180 | 1 to 86400 seconds |
| `relative_drop_pct` | 25 | 1 to 90 percent |
| `relative_persistence_s` | 1800 | 1 to 604800 seconds |
| `hysteresis_pct` | 10 | 0.1 to 50 percent, less than `relative_drop_pct` |
| `recovery_s` | 300 | 1 to 86400 seconds |
| `startup_grace_s` | 180 | 0 to 3600 seconds |
| `stale_after_s` | 180 | 10 to 86400 seconds |
| `calibration_samples` | 10 | 3 to 1000 observations |
| `calibration_duration_s` | 600 | 60 to 86400 seconds |
| `pump_tolerance_pct` | 5 | 0 to 50 percentage points |

The string-list settings use the source's **raw states**, not translated
display labels:

- `running_modes`, `idle_modes`, `excluded_modes` are disjoint. At least one
  running mode is required. Include defrost in the excluded set.
- `pump_on_values` and `pump_off_values` cannot overlap. Their initial values
  are `on` and `off`, but a source can require different mappings.
- `fault_values` and `fault_clear_values` cannot overlap. Both must be populated
  when a fault source is configured.

Do not treat unmapped states, unavailable sensors, an idle pump, or defrost as a
healthy running sample. Ineligible gaps interrupt evidence rather than helping
an incident or recovery timer mature.

### Emails and inventory

| Option | Default | Meaning |
| --- | --- | --- |
| `emails_enabled` | `false` | Master permission, including test messages |
| `recipients` | `[]` | At most 20 validated SMTP recipient entity IDs |
| `reminder_hours` | 24 | Reminder interval from 1 to 720 hours |
| `watch_email` | `false` | Opt in to watch-stage notifications |
| `language` | `en` | Email/local report language: `en`, `fr`, `es`, or `de`, independent of HA UI |
| `report_entities` | `[]` | Explicit additional entities, at most 150 |
| `report_exclude` | `[]` | Exclusions from automatic/additional inventory |

New entries always use English for email, regardless of HA's language. Existing
saved choices remain intact; supported regional variants normalize in memory,
and missing/unsupported legacy values fall back to English. New selections must
use one of the four stable codes. No storage-version migration is needed.

Native labels, states, attributes, selectors, actions and errors use the four
HA catalogs, with identical keys/placeholders and canonical English `strings.json`.
Dynamic discovery summaries, persistent notices and diagnostic explanation
attributes use HA's backend system language, not a user's frontend preference.
Nested diagnostic dictionaries retain machine codes. User source names and raw
values are not translated or renamed.

The shared report renderer translates presentation only. It includes locale-specific
subjects, cautious advice, reason/state/status descriptions, thresholds, context
lists and evidence rules. All dynamic HTML values remain escaped. `get_report`
uses the email locale with its unchanged `title`/`message`/`html` response.
Changing only `language` updates the runtime without reload, evaluation,
reconfiguration of delivery, incident-key changes or queue replay. Omitted email
form values default to the current configuration, not fresh-install defaults.
Dispatch re-renders for each recipient, so later retries/remaining recipients use
the current language without resending previously accepted deliveries.

The inventory is limited to selected devices and eligible entity domains:
`sensor`, `binary_sensor`, `select`, `climate`, and `number`. The configuration
picker for explicit report selections supports these report domains, including
device-scoped `number` entities as read-only telemetry. Reporting a number
entity never authorizes changing its value.

Automatic sensor inventory uses safe numeric device classes such as
temperature, pressure, volumetric flow, power, energy, current, voltage,
frequency, duration, volume, water, energy storage, and power factor.
Automatic binary sensors are restricted to running, problem, heat, and power
classes. Explicit mappings are always kept visible, even when also excluded.
The list is capped at 150 entities and reports indicate truncation.

Filtering rejects names/IDs suggesting serial numbers, credentials, network
addresses, location, or email addresses. This is defense in depth, not a promise
that arbitrary friendly names or manually selected states can never be private.
Never use a raw attribute dump as a substitute for a report.

## Freshness model

A measurement records its value, unit, status, and `observed_at` report
timestamp. Report rows also contain `freshness_seconds`. States include:

| Status | Interpretation |
| --- | --- |
| `ok` | Usable report within the freshness window |
| `missing` | The entity or required value is absent |
| `unknown` / `unavailable` | HA explicitly reports no usable value |
| `awaiting_fresh_report` | The value predates this runtime's startup |
| `stale` | The report is too old or has an implausible future timestamp |
| `invalid` | A numeric value is not finite or otherwise usable |

`last_reported` is an HA timestamp, not a physical controller measurement
timestamp. The runtime must follow same-value `state_reported` events as well
as changed states. An upstream integration that never republishes unchanged
values may appear stale conservatively. A recently updated unrelated entity
does not make flow, mode, or pump evidence fresh.

Startup/reload requires new reports before notifications or recovery. Restored
values and elapsed offline time cannot establish healthy operation.

Climate reports only expand allowlisted temperature fields
(`current_temperature`, `temperature`, `target_temp_low`, `target_temp_high`).
Those values inherit the parent measurement's freshness status. No location,
serial, authentication, or arbitrary diagnostic attributes are exported.

## Detection and calibration

Absolute detection compares flow with the configured installation minimum.
Without that minimum it is disabled, not replaced by a zero threshold.
Current flow/history remain available independently of diagnostic eligibility.
Healthy calibration without a minimum requires explicitly confirmed health,
positive fresh flow and comparable running context. Relative monitoring and
stable reference-based recovery then work without an absolute threshold, but
the missing absolute capability stays visible. Removing the minimum cannot
resolve a retained absolute/native incident; such recovery needs its minimum
restored and fresh eligible observations.
Relative detection compares comparable flow with an explicitly authorized
healthy reference. Persistence separates a brief fluctuation from sustained
evidence. Hysteresis and a separate recovery duration prevent an incident from
flapping around a threshold.

An explicitly matched native fault can raise an urgent incident independently
of idle/excluded operation or missing flow. It does not establish that the fault
is hydraulic. Without a native fault, missing pump-running evidence prevents
active flow inference.

The public state set is exactly `normal`, `learning`, `watch`, `urgent`, and
`diagnostic_unavailable`. The reason is authoritative context:

- `normal` includes eligible evaluation without a newly confirmed incident,
  pending thresholds, a missing reference, and explicitly idle
  operation. It is not a guarantee of equipment health.
- `learning` covers startup grace (`startup_grace`) and explicitly authorized
  calibration (`calibration_sampling`).
- `watch` and `urgent` identify incident severity.
- `diagnostic_unavailable` means the required evidence is insufficient or
  unusable, or operation is explicitly excluded (`mode_excluded`).

An active incident can remain recorded during idle operation, startup, excluded
operation, or unavailable evidence. The adapter publishes
`diagnostic_unavailable` for a retained incident in those phases, never a
misleading `normal` or `learning` state.
Only the explicit recovered transition supports a recovery notification; a
state change or missing-data condition alone does not.

The reference is tied to operating mode and, where available, pump-speed
comparability. Healthy calibration needs enough observations over enough
elapsed time. Unknown, stale, defrost, startup, and fault observations must not
contribute. A running system is not automatically a healthy system; the user
must explicitly confirm the premise.

The baseline does not continuously relearn a falling flow. A cleaning record
sets the maintenance date and cancels incomplete calibration, while retaining
the accepted baseline and active incident. Acknowledgement records that an
incident was seen. Snooze pauses reminders for a bounded period, not initial
alert retries or urgent escalation. None of these
actions proves hydraulic recovery or replaces the baseline.

A low-flow observation supports an investigation, not a specific diagnosis.
Alternative explanations include pump behavior, valve position, air, pressure,
source errors, and changing operating conditions. Preserve that distinction in
every email, translation, dashboard label, and issue report.

## Delivery contract

The integration uses native SMTP recipient entities, not legacy YAML notify
targets or raw address/password fields. Validation checks:

1. The entity registry says the enabled entity is a `notify` entity owned by
   `smtp`.
2. Its configuration entry is an SMTP entry.
3. Its unique ID matches a `recipient` subentry.
4. Its recipient identity is distinct from the other selected recipients.

Identity comparison lowercases only the domain. The local part remains
case-sensitive. This does not detect equivalent aliases or forwarding routes.
The SMTP integration owns address validation and credentials.

An unused native notify entity can have state `unknown` until its first
successful send. That state is eligible for dispatch; a missing or
`unavailable` entity is not. This initial notify state is separate from an
uncertain delivery outcome recorded by Guard.

Dispatch calls `smtp.send_message` with entity targets and the fields `title`,
`message`, and `html`. There is no `importance` field. Delivery bookkeeping is
per recipient and incident/notification kind. Retryable failures use a maximum
of three attempts with 60-second and 300-second backoffs; successful recipients
are not retried merely because another failed.

Manual tests have a separate persisted delivery queue so they cannot replace a
pending incident notification or its retries. Recipient diagnostics expose
their latest test detail under the nested `test` field.

Persistence must not turn a process interruption into an automatic duplicate:
a dispatch whose outcome is unknown is exposed as unknown and not blindly
resent. SMTP completion means only that the action completed, not that an inbox
received the message. Exactly-once email delivery cannot be guaranteed.

Restored pending/retry records stay inert until the runtime explicitly queues a
freshly revalidated event. Revalidating the same event preserves its attempt
count and retry deadline. Accepted and unknown outcomes remain terminal and
are not replayed.

Disabling emails invalidates queued work and retries, including tests. It
cannot recall a message already in flight. Configuration changes invalidate
dispatch decisions made against the old configuration. Re-enabling does not
flush a backlog; fresh evidence must confirm the current incident again.

## Native entity contract

The stable sensor translation keys are `state`, `reason`, `current_flow`,
`reference_flow`, `minimum_flow`, `decline`, `telemetry_updated`, `last_cleaned`,
and `email_status`. Per-recipient diagnostic entities supplement the aggregate
email status. The email status entity exposes a `recipients` attribute for
individual outcomes, including a sanitized neutral `name` from each native
SMTP entity's friendly label. The labels contain no address or Markdown.
Users should choose meaningful neutral names in SMTP; the dashboard displays
these labels rather than raw addresses or registry keys.

The switch key is `emails_enabled`. Its French name is **Activer les emails**.
Button keys are `acknowledge`, `snooze` (pause reminders for 24 hours), `record_cleaning`,
`confirm_calibration`, and `test_email`. Services use `entry_id` to identify the
monitor; `snooze` accepts 1 to 168 hours and `confirm_calibration` requires
`confirmed: true`.
`get_report` is a response-only native action taking `entry_id`. It returns
`title`, `message`, and `html` using the same bounded report renderer, without
mail permission, queue changes, incident mutation or equipment actions.

The calibration entity button deliberately passes confirmation itself. Its
first-person label states that the user is confirming healthy operation.
The dashboard adds a confirmation dialog, but callers of `button.press`
outside that dashboard do not get the dialog automatically.

Reason states are stable machine codes. Entity translations provide human
explanations without turning the state into a sentence. Do not derive behavior
from a translated label. Default entity IDs use the device prefix and a stable
entity key, independent of translated labels. User renaming and collisions
with existing IDs can still change the actual registry ID.

The state entity also exposes a readable `reason_text` attribute. The reason
sensor remains an enum with raw machine codes and localized display strings.
It also exposes `absolute_alerts_configured`, `limitations`, `limitations_text`
and the initial `source_statuses` from discovery. Missing minimum uses the
`minimum_not_configured` reason and never a normal running/idle public state.

## Local verification

Development uses isolated HA runtimes and synthetic measurements, never a live
installation or real SMTP credentials. CI checks the locked current dependency set
on Home Assistant 2026.9.3 and the supported minimum 2026.8.3 separately.
Both use isolated HA runtimes with network access blocked and mocked SMTP
transport, not a live installation. See [CONTRIBUTING.md](../CONTRIBUTING.md)
for commands and the required boundary cases.

The example dashboard is a configuration template, not evidence that a live
installation was inspected. Its IDs and any demonstration values must be
replaced and independently verified before use.
