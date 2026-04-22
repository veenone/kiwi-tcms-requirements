# kiwitcms-requirements

Requirements management and traceability plugin for
[Kiwi TCMS](https://kiwitcms.org/).

A first-class registry of requirements, mapped many-to-many to test cases,
with coverage analytics, document-control fields, and JIRA-native CSV
export. Standards-agnostic by default with opt-in seed profiles for
**ASPICE**, **ISO 9001**, **IEC 62304**, and **DO-178C**.

## Why

Kiwi TCMS ships with a single `TestCase.requirement` CharField (max 255
characters). That's a free-text label, not traceability. Teams working
to quality or safety standards need:

- A **first-class Requirement entity** with identity, source, and status
- **Many-to-many links** to test cases with typed relationships
- **Coverage analytics** — what's tested, what isn't, and by how much
- **Document-control fields** (doc ID, revision, effective date, supersession)
- **JIRA-ready CSV export** so reqs can be pushed into downstream ALM tools
- **Full audit trail** of every change via `django-simple-history`

This plugin adds that layer alongside the existing `TestCase.requirement`
CharField (which is left untouched).

## Features (v0.1.0)

- Requirement registry with configurable decomposition levels per
  standard (ASPICE / ISO 9001 / IEC 62304 / DO-178C / generic).
- Many-to-many links from Requirement to TestCase with typed
  relationships (`verifies`, `validates`, `derives_from`, `related`).
- **Suspect-link flagging** — when a requirement is edited, existing
  links are automatically flagged for re-confirmation.
- Dashboard with coverage %, orphan requirements, suspect links, plus
  breakdowns by status / priority / level / category / safety class.
- **JIRA-import CSV** export via `/requirements/export/jira-csv/` —
  columns match JIRA's "External System Import" format out of the box.
- Generic CSV export, JSON export, and CSV import with dry-run preview.
- Middleware-injected "Requirements" card on TestCase detail pages
  (no core-template edits required).
- Full audit trail via `django-simple-history`.
- Seed categories (functional / non-functional / safety / security /
  performance / UI / regulatory / interoperability / maintainability /
  portability) plus per-standard level seeds.
- Django admin for taxonomy management.

## Roadmap

| Version | Scope |
|---|---|
| **v0.1** | Registry + M2M + CSV/JIRA-CSV/JSON export + dashboard (this release) |
| **v0.2** | RTM matrix, D3 traceability diagram, Excel/DOCX/PDF audit, baselines, change-impact, ReqIF export |
| **v0.3** | Live JIRA REST push, role-based approval sign-off, kiwitcms-review integration, attachments |
| **v0.4** | ReqIF import, wiki sync (Outline/Confluence), JIRA webhook listener |
| **v0.5** | i18n, bulk edit, REST API, generic ALM connectors (Polarion, Azure DevOps) |

## Install

```bash
pip install kiwitcms-requirements
```

The package exposes a `kiwitcms.plugins` entry point; Kiwi discovers it
automatically on next start.

```bash
./manage.py migrate tcms_requirements
./manage.py collectstatic
```

That's it. The plugin registers its menu entries, admin tabs, and
middleware in `apps.py::ready()` — no manual `INSTALLED_APPS` or
`MIDDLEWARE` editing required.

## Level profiles

The `RequirementLevel` table is configurable. The seed migration applies
a profile based on your `REQUIREMENTS_LEVEL_PROFILE` setting (default:
`aspice`):

| Profile | Default levels |
|---|---|
| `aspice` *(default)* | stakeholder → system → software → component → unit |
| `iso9001` | customer_requirement → product_requirement → process_requirement → quality_objective |
| `iec62304` | user_need → software_req → arch_req → detailed_design → unit |
| `do178c` | high_level → low_level → source_code |
| `generic` | requirement *(single level, no decomposition enforced)* |

Add to `tcms_settings_dir/requirements.py`:

```python
REQUIREMENTS_LEVEL_PROFILE = "iso9001"
```

…and rerun `./manage.py migrate`. The seed migration is idempotent —
existing requirements keep their FK regardless of profile changes; the
operator can edit, add, or deactivate level rows from the Django admin
at any time.

## Exporting to JIRA

The JIRA-import CSV export lands at:

```
/requirements/export/jira-csv/
```

Append filter query-params (`?product=1&status=approved`) to scope the
export. The resulting file imports directly via JIRA's
*System → External System Import → CSV* with no manual field mapping.

Column mapping is overridable via `REQUIREMENTS_JIRA_EXPORT_MAPPING`:

```python
REQUIREMENTS_JIRA_EXPORT_MAPPING = {
    "issue_type": "Requirement",    # if your JIRA has a Requirement issue type
    "priority": {"critical": "Blocker", "high": "Critical"},
    "status": {"approved": "Approved"},
    "custom_fields": {
        "level": "customfield_10045",          # direct custom-field ID
        "parent_requirement": "Parent Link",
    },
}
```

The mapping merges over the defaults — only declare what you want to
change. `Issue Key` is populated on re-export after the first round-trip,
so JIRA-assigned keys round-trip cleanly back into `Requirement.jira_issue_key`.

## Permissions

Seeded on `post_migrate` and granted to the Tester / Administrator
groups:

- `requirements.view_requirement` / `add_` / `change_` / `delete_`
- `requirements.manage_baselines` *(v0.2+)*
- `requirements.approve_requirement` *(v0.3+ — gates approved/verified status)*

## Running the test suite

```bash
cd tcms_requirements
PYTHONPATH=.. DJANGO_SETTINGS_MODULE=tcms_requirements.tests.settings \
    python -m unittest discover tests
```

The unit tests don't require a live Kiwi install — they exercise
`state_machine` and `exports/jira_csv_export` in isolation.

## Compatibility

- Python 3.9 +
- Django 4.2 / 5.0 / 5.2
- Kiwi TCMS (current stable release)

## License

GPL-2.0-or-later. See `LICENSE`.
