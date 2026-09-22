# Viessmann Guard

An unofficial, read-only Home Assistant integration for monitoring hydraulic flow
from existing Viessmann heat-pump entities. It helps you notice sustained low flow
or a decline against a deliberately calibrated reference, review the evidence,
and optionally notify several recipients by email.

**This is not a safety device or a diagnosis of a blocked filter.** Low flow can
have other causes, including pump, valve, air, pressure, sensor, or operating-mode
problems. Follow the heat pump's own warnings and the manufacturer's instructions.
Ask a qualified professional to investigate. Do not open, drain, bypass, or adjust
equipment based only on this integration.

Viessmann Guard does not control the heat pump, change setpoints, or make
additional requests to Viessmann. Monitoring runs in Home Assistant even when
the dashboard is closed. This project is not affiliated with Viessmann.

## Requirements

- Home Assistant **2026.8.3 or newer**, using Python **3.14.2 or newer**.
  Home Assistant OS and Container manage their own Python runtime.
- An existing integration that provides entities for the equipment you want to
  monitor. Viessmann Guard does not collect Viessmann credentials.
- For automatic setup: native ViCare devices with recognized flow/compressor
  descriptors. Renamed or translated entities are supported.
- For active diagnosis: numeric flow with an explicit supported volumetric unit
  and an unambiguous actual operating phase, not just a climate `auto` setting.
- A mapped pump-running entity for active flow diagnostics. Setup can omit it,
  but active diagnostics then remain unavailable rather than assuming the pump
  is running.
- Optional: a pump-speed entity in `%`, a fault entity, and temperatures,
  pressure, compressor, or valve entities.
- Optional: Home Assistant's native **SMTP** integration configured through its
  UI, with one `notify` entity per recipient.

## Install

### HACS custom repository

This repository is a **custom repository**, not a claim of an official HACS
listing.

1. In HACS, open **Custom repositories**.
2. Add `https://github.com/manekinekko/viessmann-guard` as an **Integration**.
3. Download Viessmann Guard and restart Home Assistant.
4. Open **Settings > Devices & services > Add integration** and search for
   **Viessmann Guard**.

### Manual

Copy the `custom_components/viessmann_guard` directory from this repository into
your Home Assistant configuration directory at
`custom_components/viessmann_guard`. Preserve the directory structure, restart
Home Assistant, then add the integration through **Devices & services**.

Keep a backup of your configuration before installing or updating any custom
integration.

If version 0.1.0 is missing from **Add integration**, or opening its form fails,
update to 0.1.1 or newer. That version corrects the integration's catalog category
and form-schema serialization. After copying an update, restart Home Assistant
when appropriate and refresh the browser. The generic UI message about the
"latest version" does not by itself mean HA 2026.8.3 or newer needs upgrading.

## Quick setup (0.2.0)

After choosing **Viessmann Guard** in Add integration:

- **One ViCare heat pump:** review the detected sources and confirm. One
  confirmation, no fields to fill.
- **Several heat pumps:** select the named device in the list, submit, then
  confirm the summary. Three interactions, two forms. Rename identically named
  source devices first if you cannot distinguish them.
- **No supported candidate:** an explicitly secondary **Advanced manual setup**
  path is available. This path is not the three-click experience.

The integration identifies native ViCare function keys and registered device
ownership, not editable entity names. A gateway exposing only Wi-Fi telemetry
is not a second heat pump. Sharing an account, model name or gateway does not
merge separate devices. Disabled upstream entities are never enabled for you.
Ambiguous circuits/compressors are left unmapped, not arbitrarily selected.

The summary lists flow, actual compressor phase, heating-circuit circulation,
compressor, temperatures and pressure when exposed. A DHW circulation pump or
DHW operating-mode select is **not** substituted for heating hydraulics.
Climate `auto` is not evidence of an active hydraulic mode. Generic native
errors are not automatically mapped to low-flow faults.

**Observation starts without a manufacturer minimum.** Current flow/history
and device-scoped reports become available with fresh measurements. The minimum
is absent (`None`), not zero or a guessed threshold. Absolute low-flow alerts
remain disabled until you enter the installation's real minimum. Relative
monitoring still requires explicit healthy calibration and comparable operating
context. Missing context leaves diagnosis unavailable, not "Normal".
**Emails stay OFF**, with no SMTP setup or recipients added.
To read a report without SMTP, use **Developer tools > Actions >
Viessmann Guard: Read the observation report** (`viessmann_guard.get_report`),
choose the monitor, and read the returned response. This action only renders
the report locally; it does not send email or change incident state.

### Advanced options, only when needed

Open the integration's **Configure** options menu. Each section is independent;
you do not have to repeat the setup wizard:

1. **Optional installation minimum flow:** enter the actual minimum from the
   manufacturer/installer in L/min, or clear it to disable absolute alerts.
   Changing it invalidates the learned reference but cannot clear an incident.
2. **Sources:** name the monitor, select the equipment devices, and map existing
   entities explicitly. Only entities belonging to the selected devices are
   eligible. Supported source domains include `sensor`, `binary_sensor`,
   `select`, `climate`, and read-only `number` entities. Entity names alone
   are not proof of what a sensor measures.
3. **Detection rules:** adjust durations and exact
   raw values for active, idle, and excluded modes. Exclude defrost and other
   incomparable modes. Map pump on/off values and, if a fault source is selected,
   both fault and clear values. Unknown mappings do not count as healthy.
4. **Emails:** select native SMTP recipient entities, the report language, and
   optional reminders/watch notifications. **Emails start OFF, including test
   messages.** Enabling requires at least one valid recipient.
5. **Report contents:** review device-scoped telemetry, explicitly include
   relevant entities, and exclude unwanted inventory items. Explicit diagnostic
   source mappings stay visible even if also listed as exclusions.

There is **no universal or manufacturer minimum supplied by this project**.
Obtain the appropriate limit for your installation from reliable equipment
documentation or a qualified professional. Numerical values in tests,
demonstrations, and screenshots are synthetic, not installation advice.

Existing manual configurations keep their mappings, thresholds and email
permission during migration. Sources are bound to registry identities so entity
renames survive reload/restart. Discovery never overwrites expert overrides.

### A fixed, healthy reference

Relative decline detection needs a confirmed healthy calibration. Use
**I confirm healthy operation: calibrate** only after a professional or other reliable
evidence establishes that the system is healthy, stable, and operating in a
comparable mode and pump-speed range. Calibration excludes startup, defrost,
unknown, stale, and otherwise ineligible observations.

The accepted reference is fixed. It must not drift down with a deteriorating
system. Recording cleaning is a maintenance note, not proof of recovery and
not permission to replace the reference. It cancels any unfinished calibration
but retains the accepted reference and active incident. Confirm a new
calibration deliberately when appropriate.

### Freshness is evidence, not a guarantee

Each measurement has a status, a Home Assistant report timestamp, and an age.
Home Assistant's `last_reported` timestamp describes when HA received/reported a
state, **not when the controller physically measured it**. Identical values can
be fresh when the upstream integration reports them again. If it leaves an
unchanged value cached without reporting, Guard may conservatively mark it
stale. Check the source integration's reporting behavior before changing
`stale_after_s`.

After startup, fresh source reports are required before sending incident emails
or recognizing recovery. A restored state is not fresh proof.

## Dashboard and actions

[`examples/dashboard.yaml`](examples/dashboard.yaml) uses only built-in
Home Assistant cards: entities, history graph, markdown, and labeled buttons.
It inherits your HA theme and needs no custom frontend or external resources.
Copy it into a new dashboard's raw configuration editor, then replace **every**
example entity ID with the IDs shown on your integration's device page.

`sensor.demo_guard_state` and the other `demo_guard` IDs are **placeholders** for
an entry named `Demo Guard`, not discovered entity IDs. HA can choose different
IDs because of the entry/device name, user renaming, or existing entities.
Default suffixes use stable keys, independent of translated display labels.

The dashboard shows the state and reason, current/minimum/reference flow,
decline, maintenance and telemetry timestamps, email toggle, and individual
recipient outcomes. It uses text as well as icons, so color is not the only
status indicator. The history graph needs Recorder history.
The status also lists diagnostic limitations. An unset minimum appears as
unknown, never a fabricated zero. Observation/relative-only operation is not
presented as full protection or an unconditional normal state.

Always read the reason alongside the state. `normal` can mean a pending
threshold, missing reference, or idle mode, not guaranteed healthy equipment.
Excluded operation reports `diagnostic_unavailable`, with `mode_excluded` as
the reason. `learning` covers startup grace and explicit calibration.
An active incident can remain recorded while evaluation is paused or
unavailable. If an active incident is retained during idle, startup, or excluded
operation, the public state is `diagnostic_unavailable`, never `normal` or
`learning`. Only confirmed recovery resolves the incident.

| Action | Meaning |
| --- | --- |
| Acknowledge | Mark the current incident as seen. It does not resolve it. |
| Pause reminders for 24 hours | Pause reminders only. Initial alert retries and urgent escalation remain eligible; expiry does not mean recovery. |
| Record cleaning | Record a maintenance date and cancel unfinished calibration. Keep the incident and accepted reference. |
| I confirm healthy operation: calibrate | Explicitly authorize calibration against healthy, comparable observations. |
| Send test email | Request a test for the configured recipients, only while emails are enabled. |
| Enable emails / **Activer les emails** | Change the same persistent setting as the Emails options page. |

Cleaning and calibration buttons in the example ask for confirmation.
Pressing the calibration entity button itself is an explicit assertion of
healthy operation; its label says so. Automations calling `button.press` do
not display the dashboard's confirmation dialog.
The integration also exposes `viessmann_guard.acknowledge`, `snooze`,
`record_cleaning`, `confirm_calibration`, and `test_email` actions. Each takes
`entry_id`; `snooze` also takes `hours` from 1 to 168, and
`confirm_calibration` requires `confirmed: true`. See the action descriptions in
Home Assistant's **Developer tools > Actions**. These actions never control
heat-pump hardware.

## Email behavior and limits

Configure the SMTP connection and recipient addresses in Home Assistant's SMTP
UI. Select its recipient entities in Guard. **Do not copy SMTP passwords,
tokens, or server credentials into Guard, YAML examples, or issues.**

Give SMTP recipient entities useful neutral names such as `Maintenance` or
`Household`, without addresses or personal information. The dashboard displays
the runtime's sanitized recipient labels, not raw email addresses.

A native SMTP recipient entity that has never sent a message can normally show
`unknown`; that initial notify state does not prevent a test. A missing or
`unavailable` recipient cannot be used for dispatch. This is different from
Guard's **unknown delivery outcome** after an interrupted send.

- Recipient validation checks the entity registry, SMTP integration ownership,
  and recipient subentries, not just the `notify.*` name.
- Deduplication preserves the address's case-sensitive local part and lowercases
  its domain. It cannot establish whether aliases, forwarding addresses, or
  different mailboxes deliver to the same inbox.
- Guard invokes `smtp.send_message` with `title`, `message`, and `html`. It does
  not use an `importance` parameter.
- Failures are tracked per recipient, with at most three attempts and retry
  delays of 60 and 300 seconds. One recipient's failure must not resend an
  already successful delivery to another.
- Manual tests use a separate persisted queue. They do not replace pending
  incident alerts or their retries; recipient diagnostics retain nested test
  details.
- A completed SMTP call is not proof of inbox delivery. Exactly-once delivery
  cannot be guaranteed. An interrupted dispatch can leave an **unknown** result;
  it is not blindly resent.
- Turning emails off invalidates pending work, including tests. It cannot
  recall an SMTP call already in flight or a message already accepted.
- Turning emails on again requires freshly confirmed evidence of the current
  incident. Old queued incidents are not replayed as a backlog.

Acknowledgement, snooze, and email delivery state are separate from the
equipment's diagnostic state. Snooze pauses reminders only, not an initial
alert's retries or escalation to an urgent incident. An email failure is not
a heat-pump fault.

## Privacy

Reports use a bounded, device-scoped inventory of selected domains and safe
numeric device classes, plus explicit inclusions and exclusions. Measurements
carry their own availability/freshness status; missing values are not invented.
Only allowlisted climate temperature attributes are included, not raw
attribute dumps. Guard does not include raw diagnostics, location, serial
numbers, or credentials.

Friendly names and manually selected values still deserve review. Use neutral
names, inspect your selected sources, and redact addresses, names, locations,
identifiers, and credentials before sharing a report or screenshot. Do not
attach an unredacted Home Assistant diagnostic export to a public issue.

## Documentation and development

To run the local, synthetic showcase after installing the development
dependencies:

```sh
uv sync --frozen
uv run python examples/showcase.py
```

The command runs an isolated HA test fixture and prints a scenario covering
healthy calibration, relative decline, sustained low flow, maintenance actions,
recovery, and stale telemetry. It does not connect to your Home Assistant or
heat pump, and emails stay disabled. All values are synthetic. It is a terminal
demonstration, not a browser preview or evidence about your installation.

- [Architecture and operating limits](docs/architecture.md)
- [Guide en français](docs/guide.fr.md)
- [Contributing and local checks](CONTRIBUTING.md)
- [Bug reports](https://github.com/manekinekko/viessmann-guard/issues)

The existing [MIT license](LICENSE) applies. Community contributions are welcome,
especially reproducible, redacted source mappings and tests for conservative
behavior when evidence is missing.
