"""Build the Sankey-graph payload for /requirements/traceability/.

Default layout (4 columns, left → right):
    0: Requirement
    1: TestCase
    2: TestPlan
    3: Bug

Bugs are connected through the plan whose TestExecution logged them
(`Bug.executions → TestExecution.run → TestRun.plan`), so they end up
in their own column 3. Cases with no plan are still shown — their
chain just terminates at column 1.

Two alternative builders exist for the extra views:
    build_feature_sankey_payload        — Req → Feature → Case
    build_verification_sankey_payload   — Req → Case → Latest exec status

Edge weight is `1` per link. D3-Sankey assigns node ordinals
automatically; we feed it `{nodes: [{name}], links: [{source, target, value}]}`
where `source`/`target` are indices into `nodes`.

Payload is capped at `MAX_NODES` to keep client-side rendering responsive;
over-limit sets are narrowed to the most-connected requirements and
`truncated=True` is returned so the template can surface a warning.
"""
from collections import defaultdict

from tcms_requirements.dashboard.metrics import _apply_filters
from tcms_requirements.models import Requirement, RequirementTestCaseLink


MAX_NODES = 600


def build_sankey_payload(filters=None) -> dict:
    """Default 4-column layout: Req → Case → Plan → Bug.

    Bugs flow via the plan whose TestExecution logged them so they sit
    in their own rightmost column instead of sharing rank 2 with plans.
    """
    # Delegate to the linear builder — they're now the same layout.
    return build_linear_sankey_payload(filters=filters)


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


def _case_to_bugs(case_ids):
    """Return {case_id: [(bug_id, bug_summary, is_open), ...]}.

    Walks the Kiwi relationship `Bug.executions` → `TestExecution.case`.
    A single bug can reference multiple executions of the same case, so
    we de-dupe by bug id per case. Lazy-imports so the plugin still runs
    on installs without the `bugs` app loaded.
    """
    if not case_ids:
        return {}
    try:
        from tcms.bugs.models import Bug  # noqa: WPS433
    except ImportError:
        return {}

    mapping = defaultdict(dict)  # case_id -> {bug_id: (summary, is_open)}
    bugs_qs = (
        Bug.objects
        .filter(executions__case_id__in=list(set(case_ids)))
        .values("pk", "summary", "status", "executions__case_id")
        .distinct()
    )
    for row in bugs_qs:
        case_pk = row["executions__case_id"]
        if case_pk is None:
            continue
        # Bug.status=True means "still open" per Kiwi's model comment.
        mapping[case_pk][row["pk"]] = (row["summary"] or "", bool(row["status"]))

    return {
        case_pk: [
            (bug_id, summary, is_open)
            for bug_id, (summary, is_open) in sorted(bugs.items())
        ]
        for case_pk, bugs in mapping.items()
    }


def build_linear_sankey_payload(filters=None) -> dict:
    """Strict 4-column flow: Requirement → TestCase → TestPlan → Bug.

    Bugs come *via* the plan rather than directly off the case. The data
    edge is `Bug.executions → TestExecution.run → TestRun.plan`, so a bug
    is associated with a plan when it was found during a run of that
    plan. This produces a clean linear left-to-right flow with no shared
    rightmost rank.

    Plans without bugs end at column 2 (still drawn). Bugs without plans
    (rare — a bug always belongs to an execution that's in a run) fall
    back to a direct case→bug edge so they don't disappear.
    """
    scoped = _apply_filters(Requirement.objects.all(), filters)
    requirement_ids = list(scoped.values_list("pk", flat=True))

    links_qs = (
        RequirementTestCaseLink.objects
        .filter(requirement_id__in=requirement_ids)
        .select_related("requirement", "case")
    )
    case_ids = [link.case_id for link in links_qs]
    case_plans = _case_to_plans(case_ids)
    plan_bugs = _plan_to_bugs(case_ids)

    nodes, node_index, links_out = [], {}, []

    def _add(key, label, kind, extra=None):
        if key in node_index:
            return node_index[key]
        node_index[key] = len(nodes)
        node = {"name": label, "kind": kind, "id": key}
        if extra:
            node.update(extra)
        nodes.append(node)
        return node_index[key]

    for link in links_qs:
        req = link.requirement
        req_idx = _add(("req", req.pk), f"{req.identifier} {req.title}", "requirement")
        case_idx = _add(
            ("case", link.case_id),
            f"TC-{link.case_id} {getattr(link.case, 'summary', '')}".strip(),
            "case",
        )
        links_out.append({
            "source": req_idx, "target": case_idx, "value": 1,
            "link_type": link.link_type, "suspect": link.suspect,
        })
        plans = case_plans.get(link.case_id) or []
        for plan_id, plan_name in plans:
            plan_idx = _add(("plan", plan_id), plan_name, "plan")
            links_out.append({
                "source": case_idx, "target": plan_idx, "value": 1,
                "link_type": "in_plan", "suspect": False,
            })
            for bug_id, summary, is_open in plan_bugs.get(plan_id, []):
                bug_idx = _add(
                    ("bug", bug_id),
                    f"BUG-{bug_id} {summary}".strip(),
                    "bug",
                    extra={"is_open": is_open},
                )
                links_out.append({
                    "source": plan_idx, "target": bug_idx, "value": 1,
                    "link_type": "found_in_plan", "suspect": False,
                    "bug_open": is_open,
                })

    truncated = False
    if len(nodes) > MAX_NODES:
        truncated = True
        nodes, links_out = _truncate(nodes, links_out, MAX_NODES)

    return {
        "nodes": nodes, "links": links_out,
        "filters": filters or {}, "truncated": truncated,
    }


def build_feature_sankey_payload(filters=None) -> dict:
    """3-column flow: Requirement → Feature → TestCase.

    Each requirement flows into its parent feature; each feature fans
    out to the test cases that verify any of its requirements. Useful
    for "which features have weak test coverage?" — you can spot a
    feature with many requirements feeding it but few cases on the right.

    Requirements with no feature get grouped into a synthetic
    `(no feature)` node so they aren't dropped silently.
    """
    scoped = _apply_filters(
        Requirement.objects.select_related("feature").all(),
        filters,
    )
    requirements = list(scoped)
    requirement_ids = [r.pk for r in requirements]

    links_qs = (
        RequirementTestCaseLink.objects
        .filter(requirement_id__in=requirement_ids)
        .select_related("case")
    )
    case_summaries = {
        case_id: (summary or "")
        for case_id, summary in links_qs.values_list("case_id", "case__summary")
    }
    req_to_feature = {
        r.pk: (r.feature_id, r.feature.name if r.feature_id else None)
        for r in requirements
    }

    # Aggregate (req, feature) and (feature, case) edges with weight.
    feature_to_case_weights = {}  # (feature_key, case_id) -> weight
    for link in links_qs:
        feature_key = req_to_feature.get(link.requirement_id, (None, None))
        feature_to_case_weights[(feature_key, link.case_id)] = (
            feature_to_case_weights.get((feature_key, link.case_id), 0) + 1
        )

    nodes, node_index, links_out = [], {}, []

    def _add(key, label, kind):
        if key in node_index:
            return node_index[key]
        node_index[key] = len(nodes)
        nodes.append({"name": label, "kind": kind, "id": key})
        return node_index[key]

    for req in requirements:
        req_idx = _add(("req", req.pk), f"{req.identifier} {req.title}", "requirement")
        feat_id, feat_name = req_to_feature.get(req.pk, (None, None))
        feat_label = feat_name or "(no feature)"
        feat_idx = _add(("feat", feat_id), feat_label, "feature")
        links_out.append({
            "source": req_idx, "target": feat_idx, "value": 1,
            "link_type": "in_feature", "suspect": False,
        })

    for (feature_key, case_id), weight in feature_to_case_weights.items():
        feat_id, feat_name = feature_key
        feat_label = feat_name or "(no feature)"
        feat_idx = node_index.get(("feat", feat_id))
        if feat_idx is None:
            # Feature only appeared via cases (not via reqs) — add it.
            feat_idx = _add(("feat", feat_id), feat_label, "feature")
        case_idx = _add(
            ("case", case_id),
            f"TC-{case_id} {case_summaries.get(case_id, '')}".strip(),
            "case",
        )
        links_out.append({
            "source": feat_idx, "target": case_idx, "value": weight,
            "link_type": "verifies", "suspect": False,
        })

    truncated = False
    if len(nodes) > MAX_NODES:
        truncated = True
        nodes, links_out = _truncate(nodes, links_out, MAX_NODES)

    return {
        "nodes": nodes, "links": links_out,
        "filters": filters or {}, "truncated": truncated,
    }


def build_verification_sankey_payload(filters=None) -> dict:
    """3-column flow: Requirement → TestCase → Latest execution status.

    For each linked test case, look up its most recent TestExecution and
    map onto a status node (PASSED / FAILED / BLOCKED / IDLE / UNTESTED).
    Cases with no executions land on UNTESTED so the gap is visible.

    This is the audit-evidence view: at a glance you see what proportion
    of requirements is actually backed by passing tests *right now*. The
    only Sankey here that surfaces current verification state, not
    organisational structure.
    """
    scoped = _apply_filters(Requirement.objects.all(), filters)
    requirement_ids = list(scoped.values_list("pk", flat=True))

    links_qs = (
        RequirementTestCaseLink.objects
        .filter(requirement_id__in=requirement_ids)
        .select_related("requirement", "case")
    )
    case_ids = [link.case_id for link in links_qs]
    case_status = _case_latest_status(case_ids)

    nodes, node_index, links_out = [], {}, []

    def _add(key, label, kind, extra=None):
        if key in node_index:
            return node_index[key]
        node_index[key] = len(nodes)
        node = {"name": label, "kind": kind, "id": key}
        if extra:
            node.update(extra)
        nodes.append(node)
        return node_index[key]

    for link in links_qs:
        req = link.requirement
        req_idx = _add(("req", req.pk), f"{req.identifier} {req.title}", "requirement")
        case_idx = _add(
            ("case", link.case_id),
            f"TC-{link.case_id} {getattr(link.case, 'summary', '')}".strip(),
            "case",
        )
        links_out.append({
            "source": req_idx, "target": case_idx, "value": 1,
            "link_type": link.link_type, "suspect": link.suspect,
        })
        status_label = case_status.get(link.case_id, "UNTESTED")
        status_kind = _status_node_kind(status_label)
        status_idx = _add(
            ("status", status_label),
            status_label,
            status_kind,
            extra={"status_label": status_label},
        )
        links_out.append({
            "source": case_idx, "target": status_idx, "value": 1,
            "link_type": "latest_execution", "suspect": False,
        })

    truncated = False
    if len(nodes) > MAX_NODES:
        truncated = True
        nodes, links_out = _truncate(nodes, links_out, MAX_NODES)

    return {
        "nodes": nodes, "links": links_out,
        "filters": filters or {}, "truncated": truncated,
    }


# ── helpers for the new views ────────────────────────────────────────


def _plan_to_bugs(case_ids):
    """Map plan_id → list of (bug_id, summary, is_open) found in any
    execution of any run of that plan. Lazy-imports Kiwi.

    Filtering by case_ids first narrows the bug → execution → run → plan
    walk so we don't scan unrelated plans.
    """
    if not case_ids:
        return {}
    try:
        from tcms.bugs.models import Bug  # noqa: WPS433
    except ImportError:
        return {}

    mapping = defaultdict(dict)  # plan_id -> {bug_id: (summary, is_open)}
    rows = (
        Bug.objects
        .filter(executions__case_id__in=list(set(case_ids)))
        .values("pk", "summary", "status", "executions__run__plan_id")
        .distinct()
    )
    for row in rows:
        plan_id = row["executions__run__plan_id"]
        if plan_id is None:
            continue
        mapping[plan_id][row["pk"]] = (row["summary"] or "", bool(row["status"]))

    return {
        plan_id: [
            (bug_id, summary, is_open)
            for bug_id, (summary, is_open) in sorted(bugs.items())
        ]
        for plan_id, bugs in mapping.items()
    }


def _case_latest_status(case_ids):
    """Map case_id → label of the latest execution status for that case.

    "Latest" = highest TestExecution.pk. Cases with no executions get
    `UNTESTED`. Status names are returned upper-cased so the palette
    can switch on them deterministically.
    """
    if not case_ids:
        return {}
    try:
        from tcms.testruns.models import TestExecution  # noqa: WPS433
    except ImportError:
        return {}

    latest_by_case = {}
    for row in (
        TestExecution.objects
        .filter(case_id__in=list(set(case_ids)))
        .values("case_id", "status__name")
        .order_by("case_id", "-pk")
    ):
        case_id = row["case_id"]
        if case_id not in latest_by_case:
            latest_by_case[case_id] = (row["status__name"] or "IDLE").upper()

    # Cases with no executions → UNTESTED.
    out = {}
    for case_id in case_ids:
        out[case_id] = latest_by_case.get(case_id, "UNTESTED")
    return out


def _status_node_kind(label):
    """Map an upper-cased status label to a node `kind` string used by
    the JS palette. Anything unknown is grey via `status_idle`."""
    upper = (label or "").upper()
    if upper in {"PASSED", "PASS"}:
        return "status_passed"
    if upper in {"FAILED", "FAIL"}:
        return "status_failed"
    if upper in {"BLOCKED", "ERROR"}:
        return "status_blocked"
    if upper in {"WAIVED", "SKIP"}:
        return "status_blocked"
    if upper in {"UNTESTED",}:
        return "status_untested"
    return "status_idle"


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
