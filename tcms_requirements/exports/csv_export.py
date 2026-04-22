"""Generic CSV export — flat dump of every first-class Requirement field.

Sibling to jira_csv_export (JIRA-import-friendly shape). This one is a
straight column-per-field rendering; the row shape is what our own CSV
importer expects, so `write_csv` → `import_csv` round-trips.
"""
import csv
from typing import Iterable

from tcms_requirements.models import Requirement


COLUMNS = [
    "identifier",
    "title",
    "description",
    "rationale",
    "category",
    "source",
    "source_section",
    "level",
    "product",
    "project",
    "feature",
    "parent_requirement",
    "status",
    "priority",
    "verification_method",
    "verification_exemption_reason",
    "asil",
    "sil",
    "iec62304_class",
    "dal",
    "doc_id",
    "doc_revision",
    "effective_date",
    "superseded_by",
    "change_reason",
    "jira_issue_key",
    "external_refs",
    "linked_cases",
]


def _flatten(req) -> dict:
    linked_cases = ",".join(
        str(link.case_id) for link in req.case_links.all()
    )
    return {
        "identifier": req.identifier,
        "title": req.title,
        "description": req.description,
        "rationale": req.rationale,
        "category": req.category.name if req.category_id else "",
        "source": req.source.name if req.source_id else "",
        "source_section": req.source_section,
        "level": req.level.code if req.level_id else "",
        "product": req.product.name if req.product_id else "",
        "project": req.project.name if req.project_id else "",
        "feature": req.feature.name if req.feature_id else "",
        "parent_requirement": (
            req.parent_requirement.identifier if req.parent_requirement_id else ""
        ),
        "status": req.status,
        "priority": req.priority,
        "verification_method": req.verification_method,
        "verification_exemption_reason": req.verification_exemption_reason,
        "asil": req.asil,
        "sil": req.sil,
        "iec62304_class": req.iec62304_class,
        "dal": req.dal,
        "doc_id": req.doc_id,
        "doc_revision": req.doc_revision,
        "effective_date": req.effective_date.isoformat() if req.effective_date else "",
        "superseded_by": (
            req.superseded_by.identifier if req.superseded_by_id else ""
        ),
        "change_reason": req.change_reason,
        "jira_issue_key": req.jira_issue_key,
        "external_refs": _json_ish(req.external_refs),
        "linked_cases": linked_cases,
    }


def _json_ish(value) -> str:
    import json
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def write_csv(queryset: Iterable, buf) -> None:
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for req in queryset:
        writer.writerow(_flatten(req))
