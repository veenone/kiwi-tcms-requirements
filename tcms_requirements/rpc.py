"""JSON-RPC methods exposed via modernrpc.

Registered into modernrpc's registry from apps.py::ready(). The inject.js
bundle on TestCase detail calls `Requirement.filter({cases: <case_id>})`
to populate the "Requirements" card.
"""
from modernrpc.core import rpc_method

from tcms_requirements.models import Requirement, RequirementTestCaseLink


@rpc_method(name="Requirement.filter")
def requirement_filter(query=None, **_kwargs):
    """List requirements; supports `cases=<int>` to filter to a TestCase.

    Response shape is intentionally small so inject.js doesn't need extra
    round-trips. Fuller RPCs are added in later versions.
    """
    query = query or {}
    qs = Requirement.objects.all()

    case_filter = query.get("cases") if isinstance(query, dict) else None
    if case_filter is not None:
        links = (
            RequirementTestCaseLink.objects
            .filter(case_id=int(case_filter))
            .select_related("requirement")
        )
        out = []
        for link in links:
            req = link.requirement
            out.append({
                "id": req.pk,
                "identifier": req.identifier,
                "title": req.title,
                "status": req.status,
                "level": req.level.code if req.level_id else None,
                "link_type": link.link_type,
                "suspect": link.suspect,
                "coverage_notes": link.coverage_notes,
            })
        return out

    # Default filter — identifier/title partial match.
    if isinstance(query, dict):
        for key in ("identifier", "status", "priority"):
            value = query.get(key)
            if value:
                qs = qs.filter(**{key: value})
        q = query.get("q")
        if q:
            qs = qs.filter(title__icontains=q)
    return [
        {
            "id": r.pk,
            "identifier": r.identifier,
            "title": r.title,
            "status": r.status,
            "priority": r.priority,
            "level": r.level.code if r.level_id else None,
            "jira_issue_key": r.jira_issue_key,
        }
        for r in qs[:200]
    ]


@rpc_method(name="Requirement.coverage")
def requirement_coverage(requirement_id, **_kwargs):
    """Return coverage stats for a single requirement."""
    try:
        req = Requirement.objects.get(pk=int(requirement_id))
    except Requirement.DoesNotExist:
        return None

    links = list(req.case_links.all())
    suspect = sum(1 for link in links if link.suspect)
    return {
        "id": req.pk,
        "identifier": req.identifier,
        "link_count": len(links),
        "suspect_count": suspect,
        "link_types": {
            link_type: sum(1 for link in links if link.link_type == link_type)
            for link_type in {link.link_type for link in links}
        },
    }
