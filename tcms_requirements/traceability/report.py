"""Build flat row data + SVG-derived images for traceability reports.

Used by the DOCX and PDF traceability exporters. Pure Python — no
Django/Kiwi-specific orchestration. The view passes in the already-filtered
set of requirements and the client-submitted SVG blob.

Row shape (one per (requirement, case, plan, bug) combination):
    {
        "req_identifier", "req_title", "level",
        "link_type", "suspect",
        "case_id", "case_summary",
        "plan_id", "plan_name",
        "bug_id", "bug_summary", "bug_open",
    }

Edge cases:
  - Requirement with no linked cases → one row, case_* and plan_* and bug_* None.
  - Case with no plans and no bugs → one row, plan_* and bug_* None.
  - Case with plans only → one row per plan, bug_* None.
  - Case with bugs only → one row per bug, plan_* None.
  - Case with both → rows fanned across the Cartesian product of plans × bugs.
"""
import io
import logging

logger = logging.getLogger("tcms_requirements")


def _empty_row(req_identifier, req_title, level_name):
    return {
        "req_identifier": req_identifier,
        "req_title": req_title,
        "level": level_name,
        "link_type": "",
        "suspect": False,
        "case_id": None,
        "case_summary": "",
        "plan_id": None,
        "plan_name": "",
        "bug_id": None,
        "bug_summary": "",
        "bug_open": None,
    }


def flatten_traceability(requirements, case_plans, case_bugs=None) -> list:
    """Return one row per (requirement, case, plan, bug) triple.

    `requirements` is a queryset / iterable of Requirement objects with
    `case_links__case` prefetched. `case_plans` is `{case_id: [(plan_id, plan_name), ...]}`
    from `traceability.diagram._case_to_plans`. `case_bugs` (optional) is
    `{case_id: [(bug_id, summary, is_open), ...]}` from `_case_to_bugs`.
    """
    case_bugs = case_bugs or {}
    rows = []
    for req in requirements:
        level_name = req.level.name if req.level_id else ""
        links = list(req.case_links.all())
        if not links:
            rows.append(_empty_row(req.identifier, req.title, level_name))
            continue

        for link in links:
            case_id = link.case_id
            case_summary = getattr(link.case, "summary", "") if link.case_id else ""
            plans = case_plans.get(case_id) or [(None, "")]
            bugs = case_bugs.get(case_id) or [(None, "", None)]

            for plan_id, plan_name in plans:
                for bug_id, bug_summary, bug_open in bugs:
                    rows.append({
                        "req_identifier": req.identifier,
                        "req_title": req.title,
                        "level": level_name,
                        "link_type": link.link_type,
                        "suspect": link.suspect,
                        "case_id": case_id,
                        "case_summary": case_summary,
                        "plan_id": plan_id,
                        "plan_name": plan_name,
                        "bug_id": bug_id,
                        "bug_summary": bug_summary,
                        "bug_open": bug_open,
                    })
    return rows


# ── SVG conversion helpers ───────────────────────────────────────────


def svg_to_png_bytes(svg_text: str, width: int = 1400) -> bytes | None:
    """Rasterise the client-submitted SVG for DOCX embedding.

    Returns PNG bytes, or None if rendering fails (svglib/Pillow missing,
    invalid SVG, etc.). Callers are expected to gracefully degrade.
    """
    if not svg_text:
        logger.info("svg_to_png_bytes: empty SVG payload — skipping image.")
        return None
    try:
        from svglib.svglib import svg2rlg  # noqa: WPS433
        from reportlab.graphics import renderPM  # noqa: WPS433
    except ImportError as exc:
        logger.warning("svglib or reportlab.renderPM unavailable: %s", exc)
        return None

    logger.info(
        "svg_to_png_bytes: parsing SVG (%d bytes, opens with %r)",
        len(svg_text),
        svg_text[:80],
    )
    try:
        drawing = svg2rlg(io.StringIO(svg_text))
        if drawing is None:
            logger.warning("svg_to_png_bytes: svg2rlg returned None.")
            return None
        # Scale to requested pixel width while preserving aspect ratio.
        scale = width / max(drawing.width, 1)
        drawing.width = drawing.width * scale
        drawing.height = drawing.height * scale
        drawing.scale(scale, scale)
        out = io.BytesIO()
        renderPM.drawToFile(drawing, out, fmt="PNG")
        logger.info("svg_to_png_bytes: OK — %d bytes PNG", out.tell())
        return out.getvalue()
    except Exception:  # noqa: BLE001 — SVG parsers throw many things
        logger.exception("SVG → PNG conversion failed (falling back to table-only).")
        return None


def svg_to_rlg(svg_text: str):
    """Convert an SVG string to a reportlab Graphics Drawing.

    Returned object is a reportlab Flowable. Callers embed it directly
    in Platypus stories. Returns None on failure so callers can degrade.
    """
    if not svg_text:
        logger.info("svg_to_rlg: empty SVG payload — skipping image.")
        return None
    try:
        from svglib.svglib import svg2rlg  # noqa: WPS433
    except ImportError as exc:
        logger.warning("svglib unavailable: %s", exc)
        return None

    logger.info(
        "svg_to_rlg: parsing SVG (%d bytes, opens with %r)",
        len(svg_text),
        svg_text[:80],
    )
    try:
        drawing = svg2rlg(io.StringIO(svg_text))
        if drawing is None:
            logger.warning("svg_to_rlg: svg2rlg returned None.")
        return drawing
    except Exception:  # noqa: BLE001
        logger.exception("SVG → RLG conversion failed (falling back to table-only).")
        return None
