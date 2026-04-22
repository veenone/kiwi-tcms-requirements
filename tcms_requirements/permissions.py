"""Post-migrate permission grants.

Adds the plugin's CRUD permissions to Kiwi's Tester group (so testers can
author and link requirements) and the Administrator group (full control).
Safe to run multiple times.
"""
import logging

from django.contrib.auth.models import Group, Permission

logger = logging.getLogger("tcms_requirements")


# Name → set of permission codenames. Codenames follow Django's default
# scheme (add_, change_, delete_, view_ per model).
TESTER_PERMISSIONS = {
    "view_requirement", "add_requirement", "change_requirement",
    "view_requirementtestcaselink", "add_requirementtestcaselink",
    "change_requirementtestcaselink", "delete_requirementtestcaselink",
    "view_requirementcategory", "view_requirementsource", "view_requirementlevel",
    "view_project", "view_feature",
    "view_requirementbaseline",
}

ADMIN_PERMISSIONS = TESTER_PERMISSIONS | {
    "delete_requirement",
    "add_project", "change_project", "delete_project",
    "add_feature", "change_feature", "delete_feature",
    "add_requirementcategory", "change_requirementcategory", "delete_requirementcategory",
    "add_requirementsource", "change_requirementsource", "delete_requirementsource",
    "add_requirementlevel", "change_requirementlevel", "delete_requirementlevel",
    "add_requirementbaseline", "change_requirementbaseline", "delete_requirementbaseline",
    "add_jiraintegrationconfig", "change_jiraintegrationconfig",
}


def grant_permissions_to_groups():
    """Best-effort grant. Never raises — failures are logged."""
    try:
        _grant("Tester", TESTER_PERMISSIONS)
        _grant("Administrator", ADMIN_PERMISSIONS)
    except Exception as exc:  # noqa: BLE001 — we don't want migration to fail
        logger.warning("Permission grant failed: %s", exc)


def _grant(group_name, codenames):
    try:
        group = Group.objects.get(name=group_name)
    except Group.DoesNotExist:
        # Kiwi seeds these groups itself; if they don't exist, we're probably
        # running on a fresh install before the core post_migrate finished —
        # next migrate pass will call us again.
        return

    perms = Permission.objects.filter(
        codename__in=codenames,
        content_type__app_label="tcms_requirements",
    )
    if not perms.exists():
        return

    group.permissions.add(*perms)
