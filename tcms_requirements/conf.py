"""Plugin configuration with DB-first / settings-fallback resolution.

Mirrors the pattern in tcms_review/conf.py — DB reads are guarded against
ProgrammingError / OperationalError so the helpers are safe to call during
`migrate` before the tables exist.
"""
from django.conf import settings
from django.db import OperationalError, ProgrammingError


DEFAULT_LEVEL_PROFILE = "aspice"

DEFAULT_JIRA_EXPORT_MAPPING = {
    "issue_type": "Story",
    "priority": {
        "critical": "Highest",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    },
    "status": {
        "draft": "To Do",
        "in_review": "In Progress",
        "approved": "Done",
        "implemented": "Done",
        "verified": "Done",
        "deprecated": "Closed",
        "superseded": "Closed",
    },
    # Custom-field headers emitted into the JIRA CSV — override to match
    # your JIRA instance's custom-field names.
    "custom_fields": {
        "level": "Requirement Level",
        "source_document": "Source Document",
        "parent_requirement": "Parent Requirement",
        "linked_test_cases": "Linked Test Cases",
        "asil": "ASIL",
        "dal": "DAL",
        "iec62304_class": "IEC 62304 Class",
    },
}


def _safe_db_lookup(fn, default):
    try:
        return fn()
    except (ProgrammingError, OperationalError):
        return default


def get_level_profile() -> str:
    """Resolve the active level profile name.

    Used by the seed-data migration to pick which profile's levels are
    inserted into RequirementLevel. Runtime code usually doesn't need
    this — it queries the RequirementLevel table directly.
    """
    return getattr(settings, "REQUIREMENTS_LEVEL_PROFILE", DEFAULT_LEVEL_PROFILE)


def get_jira_export_mapping() -> dict:
    """Resolve JIRA-CSV export field/priority/status mapping.

    Settings override (REQUIREMENTS_JIRA_EXPORT_MAPPING) is shallow-merged
    over the default so operators can override just the fields they care
    about (e.g. status map only) without re-declaring the full dict.
    """
    overrides = getattr(settings, "REQUIREMENTS_JIRA_EXPORT_MAPPING", {}) or {}
    merged = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_JIRA_EXPORT_MAPPING.items()}
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def get_jira_integration_config():
    """Resolve the live-push JIRA integration singleton. Used in v0.3+."""
    from tcms_requirements.models import JiraIntegrationConfig  # noqa: WPS433

    def _lookup():
        return JiraIntegrationConfig.objects.first()

    return _safe_db_lookup(_lookup, None)
