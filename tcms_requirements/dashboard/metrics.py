"""Aggregations powering the requirements dashboard + diagram.

All ORM queries are kept in this file so views stay thin. The filter
dict (product_id / project_id / feature_id) scopes every aggregate
consistently, so a single switch on the dashboard re-scopes every tile.
"""
from collections import Counter

from django.db.models import Count, Q

from tcms_requirements.models import (
    Requirement,
    RequirementTestCaseLink,
)


def _apply_filters(qs, filters):
    filters = filters or {}
    if filters.get("product"):
        qs = qs.filter(product_id=filters["product"])
    if filters.get("project"):
        qs = qs.filter(project_id=filters["project"])
    if filters.get("feature"):
        qs = qs.filter(feature_id=filters["feature"])
    return qs


def dashboard_snapshot(filters=None) -> dict:
    qs = _apply_filters(Requirement.objects.all(), filters)
    total = qs.count()
    snapshot = {
        "total": total,
        "filters": filters or {},
        "coverage": _coverage(qs),
        "by_status": _by_status(qs),
        "by_priority": _by_priority(qs),
        "by_level": _by_level(qs),
        "by_category": _by_category(qs),
        "safety": _safety_distribution(qs),
        "orphan_requirement_ids": list(_orphan_requirement_ids(qs)),
        "suspect_link_count": _suspect_link_count(qs),
    }
    snapshot["orphan_requirements"] = len(snapshot["orphan_requirement_ids"])
    return snapshot


def _coverage(qs) -> dict:
    total = qs.count()
    if not total:
        return {"percent": 0.0, "linked": 0, "total": 0}
    linked = (
        qs.annotate(link_count=Count("case_links"))
        .filter(link_count__gt=0)
        .count()
    )
    return {
        "percent": round(linked * 100.0 / total, 1),
        "linked": linked,
        "total": total,
    }


def _by_status(qs) -> list:
    rows = qs.values("status").annotate(n=Count("pk")).order_by("-n")
    return [{"status": r["status"], "count": r["n"]} for r in rows]


def _by_priority(qs) -> list:
    rows = qs.values("priority").annotate(n=Count("pk")).order_by("-n")
    return [{"priority": r["priority"], "count": r["n"]} for r in rows]


def _by_level(qs) -> list:
    rows = (
        qs.values("level__code", "level__name", "level__order")
        .annotate(n=Count("pk"))
        .order_by("level__order", "level__code")
    )
    return [
        {
            "code": r["level__code"] or "(none)",
            "name": r["level__name"] or "— unassigned —",
            "count": r["n"],
        }
        for r in rows
    ]


def _by_category(qs) -> list:
    rows = qs.values("category__name").annotate(n=Count("pk")).order_by("-n")
    return [
        {"category": r["category__name"] or "— uncategorised —", "count": r["n"]}
        for r in rows
    ]


def _safety_distribution(qs) -> dict:
    asil = Counter(
        r["asil"] for r in qs.exclude(asil="").values("asil")
    )
    dal = Counter(
        r["dal"] for r in qs.exclude(dal="").values("dal")
    )
    iec = Counter(
        r["iec62304_class"]
        for r in qs.exclude(iec62304_class="").values("iec62304_class")
    )
    return {
        "asil": dict(asil),
        "dal": dict(dal),
        "iec62304_class": dict(iec),
    }


def _orphan_requirement_ids(qs):
    return (
        qs.annotate(link_count=Count("case_links"))
        .filter(link_count=0)
        .exclude(status__in={"deprecated", "superseded"})
        .exclude(verification_method="exempted")
        .values_list("pk", flat=True)
    )


def _suspect_link_count(qs) -> int:
    return RequirementTestCaseLink.objects.filter(
        requirement__in=qs,
        suspect=True,
    ).count()
