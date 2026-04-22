"""Build the Sankey-graph payload for /requirements/traceability/.

Node columns (left → right):
    0: Requirement
    1: TestCase
    2: TestPlan

Edge weight is `1` per link. D3-Sankey assigns node ordinals
automatically; we feed it `{nodes: [{name}], links: [{source, target, value}]}`
where `source`/`target` are indices into `nodes`.

The payload can get large — we cap to 600 nodes total to keep client-side
rendering responsive. If the filtered set exceeds that, we narrow to the
most-linked requirements and report `truncated=True`.
"""
from collections import defaultdict

from tcms_requirements.dashboard.metrics import _apply_filters
from tcms_requirements.models import Requirement, RequirementTestCaseLink


MAX_NODES = 600


def build_sankey_payload(filters=None) -> dict:
    scoped = _apply_filters(Requirement.objects.all(), filters)
    requirement_ids = list(scoped.values_list("pk", flat=True))

    links_qs = (
        RequirementTestCaseLink.objects
        .filter(requirement_id__in=requirement_ids)
        .select_related("requirement", "case")
    )

    # Pre-compute case → testplans mapping (lazy import Kiwi).
    case_plans = _case_to_plans([link.case_id for link in links_qs])

    nodes = []
    node_index = {}

    def _add(key, label, kind):
        if key in node_index:
            return node_index[key]
        node_index[key] = len(nodes)
        nodes.append({"name": label, "kind": kind, "id": key})
        return node_index[key]

    links_out = []
    for link in links_qs:
        req = link.requirement
        req_key = ("req", req.pk)
        req_idx = _add(req_key, f"{req.identifier} {req.title}", "requirement")
        case_key = ("case", link.case_id)
        case_idx = _add(case_key, f"TC-{link.case_id} {getattr(link.case, 'summary', '')}".strip(), "case")
        links_out.append({
            "source": req_idx,
            "target": case_idx,
            "value": 1,
            "link_type": link.link_type,
            "suspect": link.suspect,
        })
        for plan_id, plan_name in case_plans.get(link.case_id, []):
            plan_key = ("plan", plan_id)
            plan_idx = _add(plan_key, plan_name, "plan")
            links_out.append({
                "source": case_idx,
                "target": plan_idx,
                "value": 1,
                "link_type": "in_plan",
                "suspect": False,
            })

    truncated = False
    if len(nodes) > MAX_NODES:
        truncated = True
        nodes, links_out = _truncate(nodes, links_out, MAX_NODES)

    return {
        "nodes": nodes,
        "links": links_out,
        "filters": filters or {},
        "truncated": truncated,
    }


def _case_to_plans(case_ids):
    """Return {case_id: [(plan_id, plan_name), ...]}. Lazy-imports Kiwi."""
    if not case_ids:
        return {}
    try:
        from tcms.testcases.models import TestCase  # noqa: WPS433
    except ImportError:
        return {}

    mapping = defaultdict(list)
    qs = (
        TestCase.objects
        .filter(pk__in=list(set(case_ids)))
        .prefetch_related("plan")
    )
    for case in qs:
        for plan in case.plan.all():
            mapping[case.pk].append((plan.pk, plan.name))
    return mapping


def _truncate(nodes, links_out, limit):
    """Keep the most-connected requirements, drop the rest."""
    degree = defaultdict(int)
    for link in links_out:
        degree[link["source"]] += 1
        degree[link["target"]] += 1
    top_indexes = sorted(range(len(nodes)), key=lambda i: degree[i], reverse=True)[:limit]
    keep = set(top_indexes)
    remap = {old: new for new, old in enumerate(sorted(keep))}
    new_nodes = [nodes[i] for i in sorted(keep)]
    new_links = [
        {
            **link,
            "source": remap[link["source"]],
            "target": remap[link["target"]],
        }
        for link in links_out
        if link["source"] in keep and link["target"] in keep
    ]
    return new_nodes, new_links
