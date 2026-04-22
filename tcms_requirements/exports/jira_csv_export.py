"""JIRA-friendly CSV export.

Produces a CSV with JIRA's "External System Import" column names so
`System → External System Import → CSV` picks it up without manual field
mapping. Status and priority values are translated via the mapping
resolved in `tcms_requirements.conf.get_jira_export_mapping`.

Mapping priorities:
    critical → Highest, high → High, medium → Medium, low → Low
Status defaults:
    draft → To Do, in_review → In Progress, approved/implemented/verified → Done,
    deprecated/superseded → Closed

Operator overrides via Django setting REQUIREMENTS_JIRA_EXPORT_MAPPING.
"""
import csv
from typing import Iterable

from tcms_requirements.conf import get_jira_export_mapping


def _jira_columns(mapping: dict) -> list:
    """Static JIRA columns + dynamic custom-field columns from mapping.

    The order matters: summary first, description second matches JIRA's
    own sample CSVs, which reduces reviewer friction.
    """
    custom = mapping.get("custom_fields", {})
    return [
        "Issue Key",
        "Issue Type",
        "Summary",
        "Description",
        "Reporter",
        "Priority",
        "Status",
        "Component/s",
        "Labels",
        "External Issue ID",
        # Custom fields — emitted whenever at least one row has a value,
        # but we always emit the column for predictable schema round-trip.
        custom.get("level", "Requirement Level"),
        custom.get("source_document", "Source Document"),
        custom.get("parent_requirement", "Parent Requirement"),
        custom.get("linked_test_cases", "Linked Test Cases"),
        custom.get("asil", "ASIL"),
        custom.get("dal", "DAL"),
        custom.get("iec62304_class", "IEC 62304 Class"),
    ]


def _labels(req) -> str:
    """Semicolon-joined labels (JIRA's multi-value convention)."""
    out = []
    if req.source_id:
        out.append(req.source.source_type)
        if req.source.name:
            out.append(_slugify_label(req.source.name))
    if req.category_id:
        out.append(_slugify_label(req.category.name))
    # Stable de-dup preserving order.
    seen = set()
    deduped = []
    for label in out:
        if label and label not in seen:
            seen.add(label)
            deduped.append(label)
    return ";".join(deduped)


def _slugify_label(text: str) -> str:
    """JIRA labels can't contain spaces."""
    return (text or "").replace(" ", "-")


def _component(req) -> str:
    return req.category.name if req.category_id else ""


def _description(req) -> str:
    """Merge description + rationale into a single JIRA Description field.

    Rationale is appended under a sub-heading so reviewers can still read
    it; falls back to description-only if rationale is empty.
    """
    if req.rationale and req.description:
        return f"{req.description}\n\nh3. Rationale\n{req.rationale}"
    return req.description or req.rationale or ""


def _parent_identifier(req) -> str:
    return req.parent_requirement.identifier if req.parent_requirement_id else ""


def _linked_cases(req) -> str:
    identifiers = [f"TC-{link.case_id}" for link in req.case_links.all()]
    return ", ".join(identifiers)


def _source_document(req) -> str:
    pieces = [p for p in (req.doc_id, req.doc_revision) if p]
    return " ".join(pieces)


def _priority(req, mapping: dict) -> str:
    priority_map = mapping.get("priority", {})
    return priority_map.get(req.priority, req.priority.title())


def _status(req, mapping: dict) -> str:
    status_map = mapping.get("status", {})
    return status_map.get(req.status, req.status.replace("_", " ").title())


def _reporter(req) -> str:
    return req.created_by.username if req.created_by_id else ""


def _row(req, mapping: dict, columns: list) -> dict:
    row = {
        "Issue Key": req.jira_issue_key,
        "Issue Type": mapping.get("issue_type", "Story"),
        "Summary": req.title,
        "Description": _description(req),
        "Reporter": _reporter(req),
        "Priority": _priority(req, mapping),
        "Status": _status(req, mapping),
        "Component/s": _component(req),
        "Labels": _labels(req),
        "External Issue ID": req.identifier,
    }
    custom = mapping.get("custom_fields", {})
    row[custom.get("level", "Requirement Level")] = req.level.name if req.level_id else ""
    row[custom.get("source_document", "Source Document")] = _source_document(req)
    row[custom.get("parent_requirement", "Parent Requirement")] = _parent_identifier(req)
    row[custom.get("linked_test_cases", "Linked Test Cases")] = _linked_cases(req)
    row[custom.get("asil", "ASIL")] = req.asil
    row[custom.get("dal", "DAL")] = req.dal
    row[custom.get("iec62304_class", "IEC 62304 Class")] = req.iec62304_class
    # Guarantee every declared column is present even if dict typo crept in.
    return {col: row.get(col, "") for col in columns}


def write_jira_csv(queryset: Iterable, buf) -> None:
    mapping = get_jira_export_mapping()
    columns = _jira_columns(mapping)
    writer = csv.DictWriter(buf, fieldnames=columns, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for req in queryset:
        writer.writerow(_row(req, mapping, columns))
