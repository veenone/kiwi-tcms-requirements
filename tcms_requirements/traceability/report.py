"""Build flat row data + SVG-derived images for traceability reports.

Used by the DOCX and PDF traceability exporters. Pure Python — no
Django/Kiwi-specific orchestration. The view passes in the already-filtered
set of requirements and the client-submitted SVG blob.

Row shape (one per (requirement, case, plan) triple):
    {
        "req_identifier", "req_title", "level",
        "link_type", "suspect",
        "case_id", "case_summary",
        "plan_id", "plan_name",
    }

If a case has no linked plans, one row is emitted with `plan_*` None.
If a requirement has no linked cases, one row is emitted with `case_*` None.
"""
import io
import logging

logger = logging.getLogger("tcms_requirements")


def flatten_traceability(requirements, case_plans) -> list:
    """Return one row per (requirement, case, plan) triple.

    `requirements` is a queryset / iterable of Requirement objects with
    `case_links__case` prefetched. `case_plans` is `{case_id: [(plan_id, plan_name), ...]}`
    as produced by `traceability.diagram._case_to_plans`.
    """
    rows = []
    for req in requirements:
        level_name = req.level.name if req.level_id else ""
        links = list(req.case_links.all())
        if not links:
            rows.append({
                "req_identifier": req.identifier,
                "req_title": req.title,
                "level": level_name,
                "link_type": "",
                "suspect": False,
                "case_id": None,
                "case_summary": "",
                "plan_id": None,
                "plan_name": "",
            })
            continue
        for link in links:
            case_id = link.case_id
            case_summary = getattr(link.case, "summary", "") if link.case_id else ""
            plans = case_plans.get(case_id) or [(None, "")]
            for plan_id, plan_name in plans:
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
                })
    return rows


# ── SVG conversion helpers ───────────────────────────────────────────


def svg_to_png_bytes(svg_text: str, width: int = 1400) -> bytes | None:
    """Rasterise the client-submitted SVG for DOCX embedding.

    Returns PNG bytes, or None if rendering fails (svglib/Pillow missing,
    invalid SVG, etc.). Callers are expected to gracefully degrade.
    """
    if not svg_text:
        return None
    try:
        from svglib.svglib import svg2rlg  # noqa: WPS433
        from reportlab.graphics import renderPM  # noqa: WPS433
    except ImportError as exc:
        logger.warning("svglib or reportlab renderPM unavailable: %s", exc)
        return None

    try:
        drawing = svg2rlg(io.StringIO(svg_text))
        if drawing is None:
            return None
        # Scale to requested pixel width while preserving aspect ratio.
        scale = width / max(drawing.width, 1)
        drawing.width = drawing.width * scale
        drawing.height = drawing.height * scale
        drawing.scale(scale, scale)
        out = io.BytesIO()
        renderPM.drawToFile(drawing, out, fmt="PNG")
        return out.getvalue()
    except Exception as exc:  # noqa: BLE001 — SVG parsers throw many things
        logger.warning("SVG → PNG conversion failed: %s", exc)
        return None


def svg_to_rlg(svg_text: str):
    """Convert an SVG string to a reportlab Graphics Drawing.

    Returned object is a reportlab Flowable. Callers embed it directly
    in Platypus stories. Returns None on failure so callers can degrade.
    """
    if not svg_text:
        return None
    try:
        from svglib.svglib import svg2rlg  # noqa: WPS433
    except ImportError as exc:
        logger.warning("svglib unavailable: %s", exc)
        return None

    try:
        return svg2rlg(io.StringIO(svg_text))
    except Exception as exc:  # noqa: BLE001
        logger.warning("SVG → RLG conversion failed: %s", exc)
        return None
