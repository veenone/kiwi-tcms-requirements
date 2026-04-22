"""Template tags used by tcms_requirements templates.

Mirrors the tcms_review/templatetags/review_extras.py shape: small,
focused helpers that emit inline HTML rather than pulling in partial
templates (cheaper to render and easier to debug).
"""
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


_STATUS_COLOURS = {
    "draft": "label-default",
    "in_review": "label-info",
    "approved": "label-primary",
    "implemented": "label-warning",
    "verified": "label-success",
    "deprecated": "label-danger",
    "superseded": "label-danger",
}

_PRIORITY_COLOURS = {
    "critical": "label-danger",
    "high": "label-warning",
    "medium": "label-info",
    "low": "label-default",
}

_LINK_TYPE_ICONS = {
    "verifies": "fa fa-check",
    "validates": "fa fa-certificate",
    "derives_from": "fa fa-sitemap",
    "related": "fa fa-link",
}


@register.simple_tag
def status_badge(status: str):
    css = _STATUS_COLOURS.get(status, "label-default")
    label = status.replace("_", " ").title() if status else "—"
    return mark_safe(
        f'<span class="label {css}" role="status">{escape(label)}</span>'
    )


@register.simple_tag
def priority_badge(priority: str):
    css = _PRIORITY_COLOURS.get(priority, "label-default")
    label = priority.title() if priority else "—"
    return mark_safe(
        f'<span class="label {css}" role="status">{escape(label)}</span>'
    )


@register.simple_tag
def link_type_icon(link_type: str):
    cls = _LINK_TYPE_ICONS.get(link_type, "fa fa-link")
    label = link_type.replace("_", " ").title() if link_type else "Link"
    return mark_safe(
        f'<span title="{escape(label)}"><i class="{cls}"></i> {escape(label)}</span>'
    )


@register.simple_tag
def suspect_badge(suspect: bool):
    if not suspect:
        return ""
    return mark_safe(
        '<span class="label label-danger" role="status" '
        'title="Requirement has changed since this link was created — reviewer should re-confirm">'
        '<i class="fa fa-exclamation-triangle"></i> Suspect</span>'
    )


@register.filter
def case_identifier(case_id):
    if case_id is None or case_id == "":
        return ""
    return f"TC-{case_id}"
