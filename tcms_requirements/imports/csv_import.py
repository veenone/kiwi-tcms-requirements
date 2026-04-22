"""Bulk import with dry-run preview.

Accepts the same column set `exports/csv_export.py::COLUMNS` produces, so
export → edit → import round-trips cleanly. Dry-run validates everything
in a transaction that's rolled back, reporting counts + errors without
touching the DB. A non-dry-run commits.

Two input formats:
 - CSV (any UTF-8 dialect `csv.Sniffer` can parse)
 - XLSX (first worksheet, first row as header)

FKs resolved by human-friendly names:
    category → RequirementCategory.name
    source → RequirementSource.name (first match)
    level → RequirementLevel.code
    product → Product.name
    project → Project.name
    feature → Feature.name
    parent_requirement / superseded_by → Requirement.identifier

Missing FK targets → error for that row; row is skipped but the import
continues so the user sees every error in one pass.
"""
import csv
import io
import json
import logging
from dataclasses import dataclass, field

from django.db import transaction

from tcms_requirements.models import (
    Feature,
    Project,
    Requirement,
    RequirementCategory,
    RequirementLevel,
    RequirementSource,
)

logger = logging.getLogger("tcms_requirements")


REQUIRED_COLUMNS = {"identifier", "title"}


@dataclass
class RowError:
    row_num: int
    identifier: str
    message: str


@dataclass
class ImportResult:
    rows_total: int = 0
    rows_ok: int = 0
    rows_created: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    errors: list = field(default_factory=list)


# ── dispatch ─────────────────────────────────────────────────────────


def import_bytes(data: bytes, filename: str, *, dry_run: bool = True, user=None) -> ImportResult:
    """Auto-detect CSV vs XLSX by filename extension and dispatch."""
    lower = (filename or "").lower()
    if lower.endswith(".xlsx") or lower.endswith(".xlsm"):
        rows, fieldnames = _read_xlsx(data)
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return _error_result("File must be UTF-8 encoded CSV or .xlsx.")
        reader = csv.DictReader(io.StringIO(text))
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    return _import_rows(rows, fieldnames, dry_run=dry_run, user=user)


def import_csv(raw_text: str, *, dry_run: bool = True, user=None) -> ImportResult:
    """Legacy entry point — callers that already have a CSV string."""
    reader = csv.DictReader(io.StringIO(raw_text))
    fieldnames = reader.fieldnames or []
    rows = list(reader)
    return _import_rows(rows, fieldnames, dry_run=dry_run, user=user)


# ── XLSX reader ──────────────────────────────────────────────────────


def _read_xlsx(data: bytes):
    from openpyxl import load_workbook  # noqa: WPS433

    wb = load_workbook(filename=io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    iterator = ws.iter_rows(values_only=True)
    try:
        header = next(iterator)
    except StopIteration:
        return [], []
    fieldnames = [str(h).strip() if h is not None else "" for h in header]
    rows = []
    for values in iterator:
        if all(v is None or str(v).strip() == "" for v in values):
            continue  # skip blank rows
        row = {}
        for idx, col in enumerate(fieldnames):
            if not col:
                continue
            if idx < len(values) and values[idx] is not None:
                cell = values[idx]
                if hasattr(cell, "isoformat"):
                    row[col] = cell.isoformat()
                else:
                    row[col] = str(cell)
            else:
                row[col] = ""
        rows.append(row)
    return rows, fieldnames


# ── shared row processing ────────────────────────────────────────────


def _error_result(message: str) -> ImportResult:
    r = ImportResult()
    r.errors.append(RowError(0, "", message))
    return r


def _import_rows(rows, fieldnames, *, dry_run, user) -> ImportResult:
    result = ImportResult()
    missing = REQUIRED_COLUMNS - set(fieldnames)
    if missing:
        result.errors.append(RowError(0, "", f"Missing required columns: {sorted(missing)}."))
        return result

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
        for row_num, row in enumerate(rows, start=2):
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
                    categories=categories,
                    sources=sources,
                    levels=levels,
                    products=products,
                    projects=projects,
                    features=features,
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
                identifier=identifier,
                defaults=defaults,
            )
            if created:
                result.rows_created += 1
            else:
                result.rows_updated += 1
            result.rows_ok += 1
            existing_requirements[identifier] = obj

        if dry_run:
            transaction.savepoint_rollback(sid)
        else:
            transaction.savepoint_commit(sid)
    except Exception:
        transaction.savepoint_rollback(sid)
        raise

    return result


def _resolve_fks(row, *, categories, sources, levels, products, projects, features, existing_requirements) -> dict:
    out = {}
    out["category"] = _pick(row.get("category"), categories, "category")
    out["source"] = _pick(row.get("source"), sources, "source")
    out["level"] = _pick(row.get("level"), levels, "level (expected slug like 'system')")
    out["product"] = _pick(row.get("product"), products, "product") if products else None
    out["project"] = _pick(row.get("project"), projects, "project")
    out["feature"] = _pick(row.get("feature"), features, "feature")
    out["parent_requirement"] = _pick(
        row.get("parent_requirement"), existing_requirements, "parent_requirement (identifier)"
    )
    out["superseded_by"] = _pick(
        row.get("superseded_by"), existing_requirements, "superseded_by (identifier)"
    )
    return out


def _pick(name, cache, label):
    if name is None:
        return None
    name = str(name).strip()
    if not name:
        return None
    obj = cache.get(name)
    if obj is None:
        raise ValueError(f"Unknown {label}: {name!r}")
    return obj


def _build_defaults(row, fk_values) -> dict:
    def cell(name, default=""):
        value = row.get(name)
        if isinstance(value, str):
            return value.strip()
        return value if value is not None else default

    defaults = {
        "title": cell("title"),
        "description": cell("description"),
        "rationale": cell("rationale"),
        "source_section": cell("source_section"),
        "status": cell("status") or "draft",
        "priority": cell("priority") or "medium",
        "verification_method": cell("verification_method") or "test",
        "verification_exemption_reason": cell("verification_exemption_reason"),
        "asil": cell("asil"),
        "sil": cell("sil"),
        "iec62304_class": cell("iec62304_class"),
        "dal": cell("dal"),
        "doc_id": cell("doc_id"),
        "doc_revision": cell("doc_revision"),
        "change_reason": cell("change_reason"),
        "jira_issue_key": cell("jira_issue_key"),
    }
    effective_date = cell("effective_date")
    if effective_date:
        defaults["effective_date"] = effective_date  # Django parses ISO date strings
    external_refs = cell("external_refs")
    if external_refs:
        try:
            defaults["external_refs"] = json.loads(external_refs)
        except json.JSONDecodeError:
            raise ValueError(f"external_refs must be valid JSON, got: {external_refs!r}")
    defaults.update({k: v for k, v in fk_values.items() if v is not None})
    return defaults
