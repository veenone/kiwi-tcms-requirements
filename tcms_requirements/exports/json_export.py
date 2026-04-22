"""JSON export — open-schema dump including the link graph.

Structure:
    {
        "generated_at": iso datetime,
        "plugin_version": "x.y.z",
        "level_profile": "aspice",
        "requirements": [
            {
                ...all Requirement fields...,
                "external_refs": {...},
                "links": [{"case_id": 42, "link_type": "verifies", "suspect": false}, ...]
            }
        ]
    }
"""
from datetime import datetime, timezone
from typing import Iterable

from tcms_requirements import __version__
from tcms_requirements.conf import get_level_profile


def _requirement_payload(req) -> dict:
    return {
        "identifier": req.identifier,
        "title": req.title,
        "description": req.description,
        "rationale": req.rationale,
        "category": req.category.name if req.category_id else None,
        "source": {
            "name": req.source.name,
            "type": req.source.source_type,
            "version": req.source.version,
            "reference": req.source.reference,
        } if req.source_id else None,
        "source_section": req.source_section,
        "level": req.level.code if req.level_id else None,
        "product": req.product.name if req.product_id else None,
        "project": req.project.name if req.project_id else None,
        "feature": req.feature.name if req.feature_id else None,
        "parent_requirement": req.parent_requirement.identifier if req.parent_requirement_id else None,
        "status": req.status,
        "priority": req.priority,
        "verification_method": req.verification_method,
        "verification_exemption_reason": req.verification_exemption_reason,
        "asil": req.asil or None,
        "sil": req.sil or None,
        "iec62304_class": req.iec62304_class or None,
        "dal": req.dal or None,
        "doc_id": req.doc_id,
        "doc_revision": req.doc_revision,
        "effective_date": req.effective_date.isoformat() if req.effective_date else None,
        "superseded_by": req.superseded_by.identifier if req.superseded_by_id else None,
        "change_reason": req.change_reason,
        "jira_issue_key": req.jira_issue_key,
        "external_refs": req.external_refs or {},
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "updated_at": req.updated_at.isoformat() if req.updated_at else None,
        "links": [
            {
                "case_id": link.case_id,
                "link_type": link.link_type,
                "suspect": link.suspect,
                "coverage_notes": link.coverage_notes,
            }
            for link in req.case_links.all()
        ],
    }


def build_json_payload(queryset: Iterable) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plugin_version": __version__,
        "level_profile": get_level_profile(),
        "requirements": [_requirement_payload(req) for req in queryset],
    }
