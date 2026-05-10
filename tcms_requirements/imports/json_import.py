"""JSON importer — consumes the shape produced by ``exports/json_export.py``.

JSON has higher round-trip fidelity than CSV/XLSX:
  - link_type, suspect and coverage_notes survive (CSV only carries
    case_id and assumes ``verifies`` + ``suspect=False``)
  - external_refs travels as a real dict, not a JSON-string-in-CSV-cell
  - source carries name/type/version/reference (CSV emits just the name)

Accepts either the full ``{"requirements": [...]}`` envelope or a bare
list of requirement dicts so users can paste a slice. Otherwise the
import contract matches CSV: dry-run validates and rolls back, errors
report row-by-row, FKs resolved by their human-friendly identifiers.
"""
import json
import logging
from typing import Iterable

from django.db import transaction

from tcms_requirements.imports.csv_import import (
    ImportResult,
    RowError,
    _build_defaults,
    _error_result,
    _parse_case_ids,
    _resolve_fks,
)
from tcms_requirements.models import (
    Feature,
    Project,
    Requirement,
    RequirementCategory,
    RequirementLevel,
    RequirementSource,
    RequirementTestCaseLink,
)

logger = logging.getLogger("tcms_requirements")


def import_json_bytes(data: bytes, *, dry_run: bool = True, user=None) -> ImportResult:
    """Top-level entry point — accepts the json_export envelope or a list.

    Returns an ``ImportResult`` with the same shape CSV uses so the view
    layer renders one shared template.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _error_result("File must be UTF-8 encoded JSON.")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return _error_result(f"Invalid JSON: {exc.msg} at line {exc.lineno}.")

    if isinstance(payload, dict):
        rows = payload.get("requirements") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        return _error_result(
            "JSON must be either {'requirements': [...]} or a top-level list."
        )

    if not isinstance(rows, list):
        return _error_result("'requirements' must be a list.")

    return _import_json_rows(rows, dry_run=dry_run, user=user)


def _import_json_rows(rows, *, dry_run, user) -> ImportResult:
    result = ImportResult()
    result.rows_total = len(rows)
    if not rows:
        return result

    categories = {c.name: c for c in RequirementCategory.objects.all()}
    sources = {s.name: s for s in RequirementSource.objects.all()}
    levels = {lv.code: lv for lv in RequirementLevel.objects.all()}
    features = {f.name: f for f in Feature.objects.all()}
    projects = {p.name: p for p in Project.objects.all()}
    existing_requirements = {r.identifier: r for r in Requirement.objects.all()}

    try:
        from tcms.management.models import Product  # noqa: WPS433
        products = {p.name: p for p in Product.objects.all()}
    except (ImportError, Exception):  # noqa: BLE001
        products = {}

    sid = transaction.savepoint()
    try:
        for row_num, entry in enumerate(rows, start=1):
            if not isinstance(entry, dict):
                result.errors.append(RowError(row_num, "", "Entry is not a JSON object."))
                result.rows_skipped += 1
                continue

            # Translate JSON-specific shapes into the flat dict the CSV
            # row processor expects, then reuse its FK resolution.
            row = _flatten_json_entry(entry)

            identifier = (row.get("identifier") or "").strip()
            title = (row.get("title") or "").strip()
            if not identifier:
                result.errors.append(RowError(row_num, "", "Empty identifier."))
                result.rows_skipped += 1
                continue
            if not title:
                result.errors.append(RowError(row_num, identifier, "Empty title."))
                result.rows_skipped += 1
                continue

            try:
                fk_values = _resolve_fks(
                    row,
                    categories=categories, sources=sources, levels=levels,
                    products=products, projects=projects, features=features,
                    existing_requirements=existing_requirements,
                )
            except ValueError as exc:
                result.errors.append(RowError(row_num, identifier, str(exc)))
                result.rows_skipped += 1
                continue

            try:
                defaults = _build_defaults(row, fk_values)
            except ValueError as exc:
                result.errors.append(RowError(row_num, identifier, str(exc)))
                result.rows_skipped += 1
                continue

            if not dry_run and user is not None and "created_by" not in defaults:
                defaults["created_by"] = user

            obj, created = Requirement.objects.update_or_create(
                identifier=identifier, defaults=defaults,
            )
            if created:
                result.rows_created += 1
            else:
                result.rows_updated += 1
            result.rows_ok += 1
            existing_requirements[identifier] = obj

            # Restore links with full fidelity from the JSON ``links`` array.
            try:
                _sync_json_links(obj, entry.get("links") or [], user=user)
            except ValueError as exc:
                result.errors.append(RowError(row_num, identifier, str(exc)))

        if dry_run:
            transaction.savepoint_rollback(sid)
        else:
            transaction.savepoint_commit(sid)
    except Exception:
        transaction.savepoint_rollback(sid)
        raise

    return result


def _flatten_json_entry(entry: dict) -> dict:
    """Project the nested JSON shape onto the flat dict csv_import expects."""
    flat = dict(entry)  # shallow copy

    # source: either {"name": "..."} or null
    source = entry.get("source")
    if isinstance(source, dict):
        flat["source"] = source.get("name") or ""
    elif source is None:
        flat["source"] = ""

    # external_refs: pass through as-is; _build_defaults expects a JSON
    # string OR a dict — _build_defaults' json.loads call would choke on
    # a dict, so serialise back to string.
    refs = entry.get("external_refs")
    if isinstance(refs, dict) and refs:
        flat["external_refs"] = json.dumps(refs)
    elif refs is None or refs == {}:
        flat["external_refs"] = ""

    # Drop keys that aren't part of the row contract (links, created_at,
    # updated_at) so they don't accidentally get fed to update_or_create.
    for key in ("links", "created_at", "updated_at"):
        flat.pop(key, None)

    return flat


def _sync_json_links(requirement, links, *, user=None) -> None:
    """Replace ``requirement.case_links`` with the JSON ``links`` array.

    JSON preserves link_type, suspect, and coverage_notes — this is what
    distinguishes a JSON round-trip from a CSV one.
    """
    case_ids = []
    metadata = {}
    for link in links:
        if not isinstance(link, dict):
            raise ValueError("Each link must be a JSON object.")
        case_id = link.get("case_id")
        if case_id is None:
            continue
        try:
            case_id = int(case_id)
        except (TypeError, ValueError):
            raise ValueError(f"link.case_id {case_id!r} is not an integer.")
        case_ids.append(case_id)
        metadata[case_id] = {
            "link_type": link.get("link_type") or "verifies",
            "suspect": bool(link.get("suspect", False)),
            "coverage_notes": link.get("coverage_notes") or "",
        }

    if not case_ids:
        requirement.case_links.all().delete()
        return

    from django.apps import apps  # noqa: WPS433
    try:
        TestCase = apps.get_model("testcases", "TestCase")
    except LookupError as exc:
        raise ValueError(f"testcases.TestCase model not available: {exc}")

    found_ids = set(
        TestCase.objects.filter(pk__in=case_ids).values_list("pk", flat=True)
    )
    missing = [str(cid) for cid in case_ids if cid not in found_ids]
    if missing:
        raise ValueError(f"Unknown TestCase id(s): {', '.join(missing)}")

    existing = {link.case_id: link for link in requirement.case_links.all()}
    desired = set(case_ids)

    to_delete = [link.pk for cid, link in existing.items() if cid not in desired]
    if to_delete:
        RequirementTestCaseLink.objects.filter(pk__in=to_delete).delete()

    for case_id in case_ids:
        meta = metadata[case_id]
        if case_id in existing:
            link = existing[case_id]
            link.link_type = meta["link_type"]
            link.suspect = meta["suspect"]
            link.coverage_notes = meta["coverage_notes"]
            link.save(update_fields=["link_type", "suspect", "coverage_notes"])
        else:
            kwargs = {
                "requirement": requirement,
                "case_id": case_id,
                "link_type": meta["link_type"],
                "suspect": meta["suspect"],
                "coverage_notes": meta["coverage_notes"],
            }
            if user is not None and getattr(user, "is_authenticated", False):
                kwargs["created_by"] = user
            RequirementTestCaseLink.objects.create(**kwargs)
