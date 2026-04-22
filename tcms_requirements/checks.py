"""Django system checks for tcms_requirements.

Run at `./manage.py check` time; surface configuration problems early
instead of letting them blow up on the first request.
"""
from django.conf import settings
from django.core.checks import Warning, register


KNOWN_LEVEL_PROFILES = {"aspice", "iso9001", "iec62304", "do178c", "generic"}


@register()
def check_jira_export_mapping(app_configs, **kwargs):  # noqa: ARG001
    """If the operator has overridden REQUIREMENTS_JIRA_EXPORT_MAPPING, verify
    it's a dict — a scalar override is a common typo that would break the
    JIRA CSV export silently."""
    override = getattr(settings, "REQUIREMENTS_JIRA_EXPORT_MAPPING", None)
    if override is not None and not isinstance(override, dict):
        return [
            Warning(
                "REQUIREMENTS_JIRA_EXPORT_MAPPING must be a dict.",
                hint="Set to {} to accept defaults, or provide a partial mapping dict.",
                id="tcms_requirements.W001",
            )
        ]
    return []


@register()
def check_level_profile(app_configs, **kwargs):  # noqa: ARG001
    """Warn if REQUIREMENTS_LEVEL_PROFILE names an unknown profile."""
    profile = getattr(settings, "REQUIREMENTS_LEVEL_PROFILE", None)
    if profile is None:
        return []
    if profile not in KNOWN_LEVEL_PROFILES:
        return [
            Warning(
                f"REQUIREMENTS_LEVEL_PROFILE={profile!r} is not a known profile.",
                hint=f"Known profiles: {sorted(KNOWN_LEVEL_PROFILES)}.",
                id="tcms_requirements.W002",
            )
        ]
    return []
