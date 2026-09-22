# Contributing

Use synthetic or carefully redacted evidence. Development and tests must not
connect to a live Home Assistant installation, Viessmann account, or SMTP server.
No credentials are needed to contribute.

## Local checks

Use Python 3.14.2 or newer in the 3.14 series and install
[uv](https://docs.astral.sh/uv/). From the repository root:

```sh
uv sync --frozen
uv run pytest
uv run ruff check .
uv run mypy
```

Also test the oldest supported Home Assistant fixture set in an isolated
environment:

```sh
uv venv .venv-min --python 3.14
uv pip install --python .venv-min/bin/python \
  pytest-homeassistant-custom-component==0.13.357 \
  PyTurboJPEG==1.8.3 mutagen==1.48.1 ha-ffmpeg==3.2.2
.venv-min/bin/pytest
```

That fixture package pins Home Assistant 2026.8.3. The locked development
environment exercises Home Assistant 2026.9.3. Both run isolated HA fixtures,
with network access blocked and SMTP transport mocked, never a live deployment.
Do not update `uv.lock`
merely to bypass a failure against the supported minimum.

The extra packages support camera/TTS imports reached by the native SMTP
tests. SMTP transport is mocked; these dependencies do not authorize real email
or access to devices.

CI runs both environments on Python 3.14. It does not publish releases,
deploy to Home Assistant, or send email.

For a printed scenario using isolated HA fixtures and synthetic reports:

```sh
uv run python examples/showcase.py
```

This wraps `tests/test_showcase.py`; it does not start a browser dashboard or
connect to a live installation. Emails stay disabled. Its values are only
demonstration data.

## Change boundaries

- Keep the integration read-only with respect to the heat pump. Do not add
  Viessmann polling, credentials, setpoint changes, or equipment commands.
- Do not turn missing, stale, unknown, defrost, or incomparable data into
  healthy evidence. Do not count offline time toward persistence or recovery.
- Keep calibration explicit and the accepted reference fixed. Cleaning and
  acknowledgement must not silently clear incidents or replace the reference.
- Preserve the OFF-by-default email setting, including tests. The options form
  and switch must use the same persisted setting.
- Snooze affects reminders only. Do not suppress initial alert retries or
  urgent escalation, or show normal/learning while an active incident is
  retained during idle, startup, or excluded operation.
- Test recipient changes, disabled emails during dispatch, partial failures,
  restart/unknown outcomes, and re-enable behavior. Do not promise exactly-once
  delivery or infer inbox delivery from an SMTP result.
- Keep reports device-scoped, bounded, and allowlisted. Never add a raw
  attributes/diagnostics dump or expose location, serial numbers, or credentials.
- Treat all thresholds in fixtures and demos as synthetic, not manufacturer
  requirements. Keep reports diagnostic rather than prescriptive.

## Tests and documentation

Add regression tests for behavior you change. Important boundaries include:

- Explicit volumetric units and unit conversion, invalid numeric values, and
  pump-speed `%` validation.
- Operating-mode transitions, startup grace, defrost, missing pump status,
  stale reports, same-value reports, and fresh post-start evidence.
- Calibration sample count/duration, fixed reference comparability, hysteresis,
  sustained recovery, and maintenance actions.
- SMTP registry/subentry ownership, domain-only normalization, case-sensitive
  local parts, duplicate recipients, backoff, and uncertain dispatch results.
- Persistence, options/switch consistency, removed recipients, and per-recipient
  status reporting.

Use HA fixtures and fake services. Do not ask reviewers to reproduce on their
own heat pump. Keep tests deterministic and bounded.

Update the README, English architecture, and French guide when behavior changes.
Keep `strings.json` and all four catalogs in `translations/` (`en`, `fr`, `es`, `de`) aligned,
including configuration/options labels, descriptions, validation errors,
entity states, and action fields. Reason codes are API-like identifiers; human
explanations belong in translations.

`tests/test_localization.py` checks native HA catalog loading, key/placeholder
parity, all report types/locales, HTTP selector serialization, current-value
defaults, legacy fallback, per-instance independence and locale changes during
recipient dispatch/retries. Keep those changes presentation-only: no reload,
new mail, permission change or replay when only the language changes. Dynamic
backend UI text follows the HA system language, not the email locale.

The example dashboard must use only native HA cards and the default theme.
Keep visible button labels, text status explanations, responsive layout, and
confirmation for cleaning/calibration. Do not introduce custom cards, remote
assets, or color-only status distinctions. Example IDs are placeholders and
must be described as such.

## Issues and pull requests

Start with a short description of the observed behavior and what you expected.
Include versions, redacted source roles/units, and a minimal synthetic timeline.
Use the issue forms; do not post an unredacted HA diagnostic export.

Never include passwords, tokens, SMTP configuration secrets, private recipient
addresses, serial numbers, location, or a full HA backup. Replace real entity
names and values that identify people or property with neutral examples.
If a report accidentally contains a secret, remove it and rotate the secret
through its owning service rather than quoting it in another comment.

Keep pull requests focused, describe the checks you ran, and explain any
remaining limitation. Preserve the existing MIT license. No contributor is
authorized by this guide to deploy to someone else's installation.
