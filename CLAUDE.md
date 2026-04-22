# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Repository Overview

`kiwitcms-requirements` — a Django plugin for [Kiwi TCMS](https://kiwitcms.org/) that adds a first-class Requirement registry with many-to-many traceability to test cases, coverage analytics, document-control fields, and JIRA-native CSV export. Standards-agnostic by default with opt-in seed profiles for **ASPICE**, **ISO 9001**, **IEC 62304**, and **DO-178C**.

Ships as a `kiwitcms.plugins` entry point (`requirements = "tcms_requirements"`) and is discovered by Kiwi's plugin loader automatically.

## Commands

```bash
# Install in editable mode against a live Kiwi checkout
pip install -e .

# Run migrations (requires a live Kiwi Django project)
./manage.py migrate tcms_requirements
./manage.py collectstatic

# Run unit tests standalone (no Kiwi install required)
PYTHONPATH=. DJANGO_SETTINGS_MODULE=tcms_requirements.tests.settings \
    python -m unittest discover tcms_requirements/tests

# Byte-compile everything (quick sanity check)
python -m compileall -q tcms_requirements

# Build sdist + wheel
python -m build

# Publish (do NOT run through Claude — the pre-tool hook blocks it)
python -m twine upload dist/*
```

## Architecture

```
tcms_requirements/
├── __init__.py              # __version__, default_app_config
├── apps.py                  # AppConfig.ready(): RPC + middleware + signals + post_migrate perms
├── conf.py                  # DB-first / settings-fallback config (level profile, JIRA mapping)
├── menu.py                  # MENU_ITEMS appended to Kiwi's MORE menu
├── middleware.py            # InjectRequirementsBundleMiddleware (HTML response rewriting)
├── models.py                # Requirement + Project + Feature + Category + Source + Level + Link + Baseline + JiraIntegrationConfig
├── state_machine.py         # Status transitions (ISO 9001 change_reason enforcement, exemption, supersession)
├── signals.py               # Suspect-link flagging on Requirement edit
├── admin.py / permissions.py / rpc.py / checks.py / forms.py / urls.py / views.py
├── dashboard/metrics.py     # Coverage + orphan + by-status/level/category aggregations
├── exports/{csv,jira_csv,json}_export.py   # JIRA-native column mapping lives here
├── imports/csv_import.py    # With dry-run preview + FK resolution by name
├── integrations/jira/       # v0.3 live REST push (stubbed in v0.1)
├── migrations/              # 0001_initial hand-written (pinned to management.0003_squashed) + 0002_seed_catalog
├── static/tcms_requirements/
│   ├── css/requirements.css
│   └── js/inject.js         # Injected into every HTML response by middleware
├── templates/tcms_requirements/   # list / get / mutable / link / import / export_hub / dashboard
├── templatetags/requirements_extras.py
└── tests/                   # settings.py + test_state_machine.py + test_exports.py
```

## Key conventions — plugin ecosystem

- **Entry point**: Kiwi discovers this plugin via `[project.entry-points."kiwitcms.plugins"] requirements = "tcms_requirements"` in pyproject.toml.
- **`apps.py::ready()`**: registers RPC methods manually into modernrpc's registry (modernrpc has already scanned `MODERNRPC_METHODS_MODULES` before plugin apps run). Appends the middleware, wires signals, and schedules `post_migrate` permission grants.
- **Middleware**: rewrites HTML responses at `</body>`, injecting `static/tcms_requirements/js/inject.js`. The JS self-detects the page via `body[id]` and no-ops on unknown pages. Idempotent — refuses to inject a second time if `data-source="tcms_requirements"` is already in the response.
- **Two jQuery instances** (inherited from Kiwi host): `$` (3.6.1, has Bootstrap plugins) and `jQuery` (3.6.0, plain). IIFE wrappers MUST close with `})($)` — otherwise Bootstrap events like `show.bs.modal` won't fire. See `static/tcms_requirements/js/inject.js`.

## Key model relationships

- `Requirement.cases` M2M → `TestCase`, through `RequirementTestCaseLink` with `link_type` (verifies / validates / derives_from / related) + `suspect` flag.
- `Requirement.parent_requirement` self-FK for decomposition trees.
- `Requirement.superseded_by` self-FK for ISO 9001 §7.5 revision chains.
- `RequirementLevel` is a FK, NOT an enum — user-configurable per standard via seed profile (`REQUIREMENTS_LEVEL_PROFILE=aspice|iso9001|iec62304|do178c|generic`).
- `RequirementTestCaseLink.suspect` is automatically set to `True` when the linked Requirement's text fields change (title / description / rationale / source_section). Cleared by the reviewer explicitly via `/requirements/<pk>/link/<link_id>/clear-suspect/`.
- `Requirement.jira_issue_key` indexed; round-trips through the JIRA-import CSV export.

## Gotchas

- `TestCase.requirement` is a plain `CharField` on Kiwi core — this plugin does **not** deprecate it. Keep it untouched for backward-compat.
- Migrations depend on `('management', '0003_squashed')` — Kiwi's `management.0001_initial` was squashed away. Do NOT change to `0001_initial`.
- Never edit `0001_initial.py` after shipping — always add a new migration.
- The JIRA CSV export mapping is overridable via `REQUIREMENTS_JIRA_EXPORT_MAPPING`; merges shallow-per-key over defaults. Check `conf.py::get_jira_export_mapping`.
- Status transitions are enforced in `state_machine.validate_transition` — the form layer calls it, so programmatic saves should too.

## Don'ts

- Don't modify existing migration files — always add a new migration.
- Don't hand-edit `tcms_requirements/static/` vendor bundles.
- Don't add template tags inside `.js` files — use plain strings, translate server-side or via data attributes.
- Don't introduce new dependencies without updating `pyproject.toml`.
