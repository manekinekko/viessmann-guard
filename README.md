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

### Manual installation, including the current prerelease

**The implementation is currently on
[`manekinekko-integration-viessmann-guard`](https://github.com/manekinekko/viessmann-guard/tree/manekinekko-integration-viessmann-guard)
in draft [PR #1](https://github.com/manekinekko/viessmann-guard/pull/1).**
Until that PR is merged, `main` contains only the initial repository skeleton.
There is no published release or official HACS listing. Use the implementation
branch, not a guessed release download or the current `main` archive.

1. Back up your Home Assistant configuration. Download the
   [implementation branch ZIP](https://github.com/manekinekko/viessmann-guard/archive/refs/heads/manekinekko-integration-viessmann-guard.zip)
   and extract it on your computer. After publication, use a reviewed version
   that actually contains `custom_components/viessmann_guard`.
2. Copy **only the complete `custom_components/viessmann_guard` folder** into
   the Home Assistant configuration directory. This is the directory containing
   `configuration.yaml`, commonly `/config` on HA OS. Include all Python files,
   JSON files, `services.yaml`, and the whole `translations` subdirectory.
   Do not copy the repository root, `tests`, `.venv`, examples, or development files.
3. **Restart Home Assistant Core once** after installing or replacing the files.
   Reloading the integration or refreshing the browser does not load updated
   Python modules reliably. No host reboot is required. Wait for Core to finish
   starting, then refresh the browser.

The result must look like this, without an extra nested repository folder:

```text
<HA configuration directory>/
  configuration.yaml
  custom_components/
    viessmann_guard/
      __init__.py
      manifest.json
      config_flow.py
      ...other component files...
      strings.json
      services.yaml
      translations/
        en.json
        fr.json
        es.json
        de.json
```

Open **Settings > Devices & services > Add integration > Viessmann Guard**, or
use this link **after installing the files and restarting Core**:

[![Add Viessmann Guard](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=viessmann_guard)

### HACS after publication

HACS metadata is included, but the current `main` skeleton is not an installable
integration. **Use the manual branch installation above for this prerelease.**
Once a reviewed implementation is published on the repository's default branch
and HACS offers that version, it can be added through **HACS > Custom repositories**
as `https://github.com/manekinekko/viessmann-guard`, category **Integration**.
Download that published version and restart Core. This does not imply an
official HACS listing, and no nonexistent release is required by this guide.

## Quick setup

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

### Configuration defaults

These are monitoring settings, **not hydraulic advice or manufacturer limits**.
Change them in **Configure > Detection rules**, unless another section is listed.
Durations accumulate only eligible observed operation, not time offline.

| Setting | Default | Unit / effect |
| --- | --- | --- |
| Optional installation minimum flow | Not set | L/min; absolute alerts disabled until a real limit is supplied |
| Low-flow persistence | 180 | Seconds below the configured minimum before urgent detection |
| Relative decline threshold | 25 | Percent below a confirmed healthy reference |
| Relative-decline persistence | 1800 | Seconds of comparable decline before a watch incident |
| Recovery hysteresis | 10 | Percent margin; must be less than the relative decline threshold |
| Healthy recovery duration | 300 | Seconds of fresh, eligible healthy evidence |
| Startup grace | 180 | Seconds after startup or an operating-context change |
| Report freshness limit | 180 | Seconds since the source's HA report, not physical acquisition |
| Calibration sample count | 10 | Distinct eligible reports after explicit healthy confirmation |
| Calibration duration | 600 | Seconds spanned by healthy calibration observations |
| Pump-speed tolerance | 5 | Percentage points, when a speed source is configured |
| Enable emails | OFF | Emails and recipients; blocks every send, including tests |
| SMTP recipient entities | Empty | Emails and recipients; select up to 20 existing native SMTP entities |
| Reminder interval | 24 | Hours, configurable from 1 to 720 |
| Send watch-stage emails | OFF | Optional email for persistent relative decline |
| Email and report language | English | English, Français, Español, Deutsch; independent of HA UI |

Automatic ViCare setup maps verified compressor phases and heating-circuit pump
states when unambiguous. Manual mode/fault mappings have no universal model-specific
defaults. Changing source identities or detection rules invalidates calibration,
but keeps unresolved incidents and maintenance history. A language-only change
does neither and does not reload the monitor.

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

### Incident evidence and the five-day view

Version 0.4.0 adds the same evidence-rich layout to emails and local reports:
current flow and its HA report timestamp, next to an **immutable capture at the
alert decision**. An opening watch alert and a later urgent escalation have
separate captures. Reminders retain the flow that triggered the displayed alert
level, not the latest reading. The recorded rule, threshold/reference, observed
duration and window, decision time, opening time and any escalation time remain
distinct. A recovery message identifies confirmed stable recovery and retains
the closed incident's evidence. A native flow fault can have no usable flow
measurement; that value is unavailable, not zero.

Existing incidents from older versions keep their ID, acknowledgement, snooze
and delivery state. Their exact trigger measurement is **unknown**, even if a
nearby historical value exists. An upgrade never substitutes current flow,
reopens the incident or sends an upgrade notification.

The chart covers **five calendar days in HA's configured timezone**, including
today marked partial. Calendar boundaries honor daylight-saving changes.
The unit is consistently **L/min**, including converted source values. Red HTML
bars share one scale starting at zero; numbers remain readable with images
disabled. There are no remote images, tracking pixels, JavaScript or attachments.

History is collected **locally from this version onward**, independently of
Recorder. No extra setup is required. Guard takes the first evaluation in each
UTC minute, from the existing 15-second timer or source events. Only fresh
flow, an explicitly configured running mode and confirmed running circulation
are eligible, after startup grace. When pump speed is configured, it must be
fresh and valid. Repeated values may be sampled while their last HA report is
still within the configured freshness limit; they are not new persistence
evidence. Missing, stale, idle, defrost and otherwise excluded observations
remain gaps. There is no interpolation or catch-up after downtime.

Daily medians and minima describe these **regularly sampled observations**, not
every raw source reading. Bursts of state changes cannot contribute extra
samples within a minute. The displayed numerator counts comparable sampled
minute slots; the denominator counts elapsed calendar-minute slots, including
idle/excluded periods. This is **not measured continuous operating time**.
At least two samples in each compared day are needed for the percentage.
Sparse coverage is not proof of a representative day. The percentage compares
the first and last usable displayed daily medians, with both dates named, and
is unavailable when the first median is zero. Missing days preclude a five-day
decline conclusion. Consecutive decreases mean decreases in the **sampled daily
medians**, never that every individual reading fell.
The consecutive five-day label additionally requires observations in every
elapsed minute slot with no unknown/stale context gaps. Otherwise the report
explicitly says evidence is insufficient for that conclusion, even when a
first/last sampled-median percentage can be displayed.
Freshly identified idle/defrost intervals, confirmed stopped circulation and
known other operating modes account for observed **exclusions**, even when flow
stops reporting there. They are not unknown gaps and do not require the pump
to run 24 hours a day. Missing/old mode evidence cannot justify an exclusion.
Partial-history subjects say so immediately; their available-point percentage
is confined to the technical appendix, not presented as a proven continuous drop.

Comparison uses the captured alert's mode, circulation state and, when known,
pump speed within the configured tolerance. Without a capture, a fresh eligible
current context is used. Without measured speed, the report explicitly limits
comparability to mode and running state, not identical hydraulic conditions.
Source/rule changes discard incompatible history and prevent comparison with
an old incident context; registry-backed entity renames retain identity.
Heating, DHW, defrost and different known speed ranges are not blended.

There is **no Recorder backfill**. HA 2026.8.3 and 2026.9.3 Recorder history
records state changes and a last-reported endpoint, not the complete sequence
of unchanged reports needed to reconstruct freshness and gaps honestly.
Recorder can be absent, excluded or unavailable without delaying an alert.
The separate native dashboard history graph still needs Recorder.
Allow five calendar days to accumulate this new view; empty early days are
normal, not installation failures.

Local records are capped at six days and 8,641 compact samples per instance.
HA's atomic Store persists them about every five minutes and on unload;
incident/delivery changes still save immediately. A crash can lose recent
unsaved samples, never create replacement observations. The last 120 reported
flow points remain separately listed in the appendix for compatibility and
are **not** used to reconstruct the five-day chart.

**Upgrade/rollback:** 0.4.0 writes storage payload/engine schema 2 while accepting
schema 1 on upgrade. Before first loading it, keep a normal private Home Assistant
backup as well as the previous component folder. Replacing files before the
first restart has not migrated runtime state. After 0.4.0 has saved schema 2,
0.3.0 cannot read that state: rolling back needs the compatible pre-upgrade HA
backup, not just the old Python files. Do not edit `.storage` manually.

This is diagnostic context, not a new alert rule or automatic calibration.
Persistent low flow or declining comparable medians may justify professional
inspection of filters and the hydraulic circuit. Clean only when fouling is
confirmed and according to the manufacturer. Circulator problems, valves,
air, sensors and operating conditions remain alternative causes.

### Interface language versus email language

English is the canonical/fallback interface language. Native HA labels, forms,
states, actions and errors have complete English, French, Spanish and German
catalogs and use Home Assistant's normal localization behavior. Guard does not
change your profile language, the HA system language, entity IDs, unique IDs,
or customized names.

In **Configure > Emails and recipients > Email and report language**, choose
**English**, **Français**, **Español**, or **Deutsch**. This preference is per
Guard instance and independent of your interface language. It applies to all
email subjects, plain text and HTML, including watch, urgent, reminder, recovery
and test messages. The local `viessmann_guard.get_report` response uses this same
preference and keeps its `title`, `message`, `html` fields.

New monitors default to English, even when HA uses another language. Existing
saved English/French choices are preserved, including French automatically
selected by older quick setup. Missing or unsupported legacy language values
fall back to English; supported regional variants normalize to their base
language. No upgrade enables emails or sends a language-change notification.
Changing only the language preserves recipients, permissions, incidents and
retry outcomes. A later legitimate retry or remaining recipient uses the current
language; already accepted messages are not resent.

Some dynamic text is generated by the backend: the discovery summary,
persistent HA notifications, `reason_text`, `limitations_text` and neutral
recipient fallback labels follow **HA's system language**, not each user's
frontend profile and not the email preference. Machine reason codes and nested
diagnostic dictionaries remain stable. Source names, original operating values,
manufacturer codes and units remain as supplied. Report timestamps include an
explicit UTC offset. The example dashboard's authored captions are English;
edit them if you want another language.

### Configure native SMTP, then select recipients in Guard

Configure the SMTP connection and recipient addresses in Home Assistant's SMTP
UI. Select its recipient entities in Guard. **Do not copy SMTP passwords,
tokens, or server credentials into Guard, YAML examples, or issues.**

SMTP is optional. You can finish setup, observe data and read local reports
without configuring it. When you want email:

1. Open **Settings > Devices & services > Add integration > SMTP** and configure
   the connection using your provider's documented settings. Guard reuses
   Home Assistant's [native SMTP integration](https://www.home-assistant.io/integrations/smtp/);
   a legacy `notify.some_service` action is not a native recipient entity.
2. On the SMTP integration, choose **Add recipient**, enter a neutral name
   such as `Maintenance` and an address such as `maintenance@example.com`,
   then **Submit**. Repeat for each recipient. Each becomes its own `notify`
   entity. If setup already created the intended recipient, reuse it rather
   than adding it again. Recipients can use any email provider; they need not use Gmail.
3. Open **Viessmann Guard > Configure > Emails and recipients**. In
   **SMTP recipient entities**, **select the existing recipient entity or
   entities and save the form**. Then deliberately enable **Enable emails**,
   using the same options page or the dashboard switch.

**Creating an SMTP recipient does not select it in Guard.** If enabling gives
“Select at least one valid native SMTP recipient before enabling or testing emails”,
return to the Guard selector, select the existing entities and save. Do not add
fake addresses or disable validation. Selection and permission are separate.

Enabling emails can send a current, freshly confirmed active alert. Once enabled,
the optional **Send test email** action sends real email to every selected
recipient; do not press it unless that is intended. Saving a language alone is
not a test. A saved SMTP entry proves configuration, not current authentication
or successful inbox delivery.

### Gmail example

Enable [Google 2-Step Verification and create an app password](https://support.google.com/accounts/answer/185833)
for Home Assistant. Native SMTP uses password authentication, **not Google OAuth**.
Use the app password, not your normal Google account password. Some Workspace,
Advanced Protection or security-key-only policies prevent app-password creation;
follow Google's account guidance or choose another SMTP provider rather than
weakening account security.

Enter these values **only in Home Assistant's SMTP form**:

| SMTP field | Value |
| --- | --- |
| Host | `smtp.gmail.com` |
| Port | `587` |
| Connection security | `STARTTLS` |
| Verify SSL certificate | ON |
| Sender email | Your full Gmail address |
| Username | The same full Gmail address |
| Password | Your Google app password, not the account password |
| Sender name | A neutral label, for example `Viessmann Guard` |

Never post the app password, SMTP configuration or recipient addresses in an
issue or chat. After saving Gmail SMTP, **add its recipient entities and select
them in Guard using the steps above**. Gmail setup alone does not complete Guard's
recipient selection.

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

## Troubleshooting and updates

| Symptom | What to check |
| --- | --- |
| “Select at least one valid native SMTP recipient before enabling or testing emails” (`required_recipient`) | Select existing entities in **Guard > Configure > Emails and recipients > SMTP recipient entities**, save, then enable. Having recipients in SMTP alone is not enough. |
| “Emails are disabled, including tests” (`emails_disabled`) | This is intentional. Enable the persisted permission only if outgoing email is wanted. OFF never needs a fake recipient. |
| Selected SMTP entity is rejected | Check that it is an enabled native SMTP `notify` entity with an existing recipient subentry, not a deleted, orphaned or legacy service. Reselect the intended entity in Guard. |
| SMTP failure or authentication error | Inspect individual recipient outcomes and native SMTP errors. For Gmail, check the app password, full username/sender and STARTTLS settings. Registry validation cannot prove authentication. Do not repeatedly resend to successful recipients. |
| Guard missing from Add integration, or “does not support UI configuration” | Check the directory tree and `manifest.json`, install the full current component, restart **Core**, then refresh HA. Version 0.1.0 had catalog/serialization defects fixed in 0.1.1. A browser cache refresh alone cannot load Python changes. |
| Unsupported flow unit or invalid value | Use a finite nonnegative value with explicit `L/min`, `L/h`, `m³/h` (`m3/h`), `m³/s` (`m3/s`), or `US gal/min`. Missing units and ambiguous `gal/min` are rejected. Do not relabel an unrelated sensor to bypass validation. |
| Stale or post-restart waiting | Check whether ViCare is publishing reports, including unchanged values. HA report age is not controller acquisition age. Restore source telemetry; do not treat stale data as recovery. |
| Observation only / diagnosis unavailable | Read the reason and limitations. Missing minimum disables absolute detection. Relative analysis needs a confirmed healthy reference and comparable active mode/circulation. API tiers and models expose different data; Guard cannot manufacture missing measurements. |
| No candidate or ambiguous circuit | Use advanced manual mapping only with verified source roles. Guard never enables disabled upstream entities or picks an arbitrary heating circuit. |

For an update, back up the **existing Guard component and your HA configuration**
first. Replace the complete `custom_components/viessmann_guard` folder, keeping
backups outside `custom_components` so HA cannot discover duplicate integrations.
Do not delete/recreate your configured Guard entry or edit `.storage`. Restart
Core once at a convenient time after copying, then inspect the version, sources,
language, permission and diagnostics. Email permission and mappings remain saved;
fresh telemetry is still required after startup.

For rollback, restore the previous complete Guard folder from your backup and
restart Core. If a future version changes stored schemas, use its migration notes
and a compatible configuration backup, not manual `.storage` edits. Do not restore
an entire HA backup blindly over unrelated changes.

For installation feedback, [open a GitHub issue](https://github.com/manekinekko/viessmann-guard/issues)
with Guard/HA versions, the failed step and redacted source roles/units or error
codes. Never upload secrets, raw registries, private addresses or full backups.

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
