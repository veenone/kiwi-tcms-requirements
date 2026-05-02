"""PDF report renderer (reportlab).

Sibling to docx_renderer. Produces the same two scopes with the same
section ordering so operators can compare outputs directly.

Uses reportlab Platypus for flowing layout; tables auto-paginate.
"""
import io
from datetime import datetime, timezone

from tcms_requirements import __version__


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _styles():
    from reportlab.lib.styles import getSampleStyleSheet  # noqa: WPS433
    return getSampleStyleSheet()


def _heading(text, level=1):
    from reportlab.platypus import Paragraph  # noqa: WPS433
    styles = _styles()
    key = "Heading1" if level == 1 else ("Heading2" if level == 2 else "Heading3")
    return Paragraph(text, styles[key])


def _para(text, style="Normal"):
    from reportlab.platypus import Paragraph  # noqa: WPS433
    return Paragraph(text, _styles()[style])


def _cell_style():
    """Compact paragraph style for table cells — wraps long text inside
    a fixed col-width without enlarging the row beyond the natural line
    height. Cached on the function to avoid rebuilding per table.
    """
    cached = getattr(_cell_style, "_cached", None)
    if cached is not None:
        return cached
    from reportlab.lib.styles import ParagraphStyle  # noqa: WPS433

    cached = ParagraphStyle(
        "tcms_cell",
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        wordWrap="CJK",  # break inside long unbroken tokens (URLs, identifiers)
        spaceBefore=0,
        spaceAfter=0,
    )
    _cell_style._cached = cached
    return cached


def _wrap_cell(value):
    """Convert a cell value to a wrappable Paragraph if it's a string.

    Pre-existing flowables (Paragraph, etc.) pass through unchanged.
    """
    from reportlab.platypus import Paragraph, Flowable  # noqa: WPS433
    if isinstance(value, Flowable):
        return value
    text = "" if value is None else str(value)
    # Escape HTML metacharacters so '&', '<', '>' in identifiers don't
    # confuse Paragraph's mini-XML parser.
    text = (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))
    return Paragraph(text, _cell_style())


def _table(data, col_widths=None):
    from reportlab.lib import colors  # noqa: WPS433
    from reportlab.platypus import Table, TableStyle

    # Wrap every body cell so text reflows inside its column width;
    # header row stays as raw strings (rendered with the bold style).
    wrapped = []
    for idx, row in enumerate(data or []):
        if idx == 0:
            wrapped.append(list(row))
        else:
            wrapped.append([_wrap_cell(c) for c in row])

    tbl = Table(wrapped, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#39a5dc")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tbl


def _spacer(height=8):
    from reportlab.platypus import Spacer  # noqa: WPS433
    return Spacer(1, height)


def _scaled_drawing(drawing, max_width_pts):
    """Scale a reportlab Drawing to fit max_width_pts, preserving aspect.

    Used for the SVG → RLG Sankey embedding so the diagram never overflows
    the platypus frame (which would raise LayoutError "Flowable too large").
    The caller passes the actual frame width after margins, not the raw
    page width.
    """
    if drawing.width <= 0:
        return drawing
    scale = max_width_pts / drawing.width
    if scale >= 1.0:
        # Drawing already fits; don't upscale (avoids tiny diagrams blowing
        # up to fill the page and looking pixelated).
        return drawing
    drawing.width = drawing.width * scale
    drawing.height = drawing.height * scale
    drawing.scale(scale, scale)
    return drawing


def _add_mixed_orientation_templates(doc, *, first="portrait"):
    """Register two named PageTemplates on a BaseDocTemplate so a single
    PDF can mix portrait + landscape pages.

    Names: ``"portrait"`` (A4) and ``"landscape"`` (rotated A4). Whichever
    one is named in ``first`` becomes page 1 — reportlab uses the first
    template added as the document's starting template. Switch templates
    later in the story with ``NextPageTemplate(name)`` + ``PageBreak()``.
    """
    from reportlab.lib.pagesizes import A4, landscape  # noqa: WPS433
    from reportlab.platypus import Frame, PageTemplate  # noqa: WPS433

    margin = 72  # 1 inch — matches SimpleDocTemplate default

    portrait_w, portrait_h = A4
    landscape_w, landscape_h = landscape(A4)

    portrait_template = PageTemplate(
        id="portrait",
        frames=[Frame(
            margin, margin,
            portrait_w - 2 * margin, portrait_h - 2 * margin,
            id="portrait_frame",
        )],
        pagesize=A4,
    )
    landscape_template = PageTemplate(
        id="landscape",
        frames=[Frame(
            margin, margin,
            landscape_w - 2 * margin, landscape_h - 2 * margin,
            id="landscape_frame",
        )],
        pagesize=landscape(A4),
    )
    if first == "landscape":
        doc.addPageTemplates([landscape_template, portrait_template])
    else:
        doc.addPageTemplates([portrait_template, landscape_template])


def build_requirement_list_pdf(queryset, *, title="Requirements report") -> bytes:
    from reportlab.lib.pagesizes import A4  # noqa: WPS433
    from reportlab.platypus import SimpleDocTemplate

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title)
    story = [
        _heading(title),
        _para(f"Generated: {_now_iso()} · kiwitcms-requirements v{__version__}"),
        _spacer(),
    ]

    reqs = list(queryset)
    story.append(_para(f"<b>Total requirements:</b> {len(reqs)}"))
    story.append(_spacer())

    if not reqs:
        story.append(_para("No requirements match the selected filters."))
        doc.build(story)
        return buf.getvalue()

    story.append(_heading("Requirements", level=2))
    rows = [["ID", "Title", "Level", "Status", "Priority", "Links"]]
    for r in reqs:
        rows.append([
            r.identifier,
            r.title,
            r.level.name if r.level_id else "—",
            r.get_status_display(),
            r.get_priority_display(),
            str(r.case_links.count()),
        ])
    story.append(_table(rows, col_widths=[60, 180, 70, 70, 60, 40]))

    doc.build(story)
    return buf.getvalue()


def build_dashboard_pdf(snapshot: dict, *, title="Requirements dashboard snapshot") -> bytes:
    from reportlab.lib.pagesizes import A4  # noqa: WPS433
    from reportlab.platypus import SimpleDocTemplate

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title)
    story = [
        _heading(title),
        _para(f"Generated: {_now_iso()} · kiwitcms-requirements v{__version__}"),
        _spacer(),
    ]

    coverage = snapshot.get("coverage", {}) or {}
    story.append(_heading("Coverage", level=2))
    story.append(_table([
        ["Metric", "Value"],
        ["Total requirements", str(snapshot.get("total", 0))],
        ["Coverage %", f"{coverage.get('percent', 0)}%"],
        ["Linked / total", f"{coverage.get('linked', 0)} / {coverage.get('total', 0)}"],
        ["Orphan requirements", str(snapshot.get("orphan_requirements", 0))],
        ["Suspect links", str(snapshot.get("suspect_link_count", 0))],
    ], col_widths=[220, 220]))
    story.append(_spacer())

    _append_count_section(story, snapshot.get("by_status"), "By status", "Status")
    _append_count_section(story, snapshot.get("by_priority"), "By priority", "Priority")
    _append_count_section(story, snapshot.get("by_level"), "By level", "Level", row_key="name")
    _append_count_section(story, snapshot.get("by_category"), "By category", "Category")

    safety = snapshot.get("safety", {}) or {}
    if any(safety.values()):
        story.append(_heading("Safety / criticality distribution", level=2))
        for key, label in (("asil", "ASIL"), ("dal", "DAL"), ("iec62304_class", "IEC 62304 Class")):
            bucket = safety.get(key) or {}
            if not bucket:
                continue
            rows = [[label, "Count"]]
            for class_name, count in sorted(bucket.items()):
                rows.append([str(class_name), str(count)])
            story.append(_para(f"<b>{label}</b>"))
            story.append(_table(rows, col_widths=[220, 220]))
            story.append(_spacer())

    doc.build(story)
    return buf.getvalue()


def build_traceability_pdf(rows, *, title="Requirements traceability report", diagram_rlg=None) -> bytes:
    """Traceability export: optional RLG Sankey drawing + table of rows.

    `rows` is the flattened row list from `traceability.report.flatten_traceability`.
    `diagram_rlg` is an optional reportlab Graphics Drawing (from `svg_to_rlg`);
    when present, it's added as a flowable above the table.
    """
    from reportlab.lib.pagesizes import A4, landscape  # noqa: WPS433
    from reportlab.platypus import (  # noqa: WPS433
        BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    )

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, title=title)
    # When we have a Sankey, page 1 must be landscape — register that
    # template first so the document opens on it.
    _add_mixed_orientation_templates(
        doc, first="landscape" if diagram_rlg is not None else "portrait",
    )
    story = []

    if diagram_rlg is not None:
        story.append(_heading("Traceability diagram", level=1))
        story.append(_para(f"<b>{title}</b>"))
        story.append(_para(f"Generated: {_now_iso()} · kiwitcms-requirements v{__version__}"))
        story.append(_spacer(12))
        landscape_width = landscape(A4)[0] - (2 * 72)  # 1 inch margins
        story.append(_scaled_drawing(diagram_rlg, landscape_width))
        story.append(_para(
            "Blue = requirements, orange = test cases, green = test plans, "
            "red strokes = suspect links."
        ))
        story.append(NextPageTemplate("portrait"))
        story.append(PageBreak())

    story.append(_heading(title))
    story.append(_para(f"Generated: {_now_iso()} · kiwitcms-requirements v{__version__}"))
    story.append(_spacer())
    story.append(_heading("Traceability table", level=2))
    story.append(_para(f"<b>{len(rows)} row(s).</b>"))
    story.append(_spacer())

    if not rows:
        story.append(_para("No traceability rows match the current filters."))
        doc.build(story)
        return buf.getvalue()

    table_rows = [["Requirement", "Title", "Level", "Link", "Test case", "Test plan", "Bug", "Suspect?"]]
    for row in rows:
        table_rows.append([
            row["req_identifier"],
            row["req_title"],
            row["level"] or "—",
            row["link_type"] or "—",
            f"TC-{row['case_id']}" if row["case_id"] else "—",
            row["plan_name"] or "—",
            _pdf_bug_cell(row),
            "SUSPECT" if row["suspect"] else "",
        ])
    # Portrait A4 frame is ~451pt wide. Total of these cols = 451pt.
    story.append(_table(
        table_rows,
        col_widths=[55, 110, 50, 45, 45, 70, 50, 26],
    ))

    doc.build(story)
    return buf.getvalue()


def build_project_pdf(project, requirements, snapshot, *, diagram_rlg=None) -> bytes:
    """Project programme report: metadata header + scoped requirement list.

    ``diagram_rlg`` is an optional reportlab Graphics Drawing produced by
    ``traceability.report.svg_to_rlg``; when supplied, the diagram lands
    on a dedicated landscape A4 first page, with the rest of the report
    flowing in portrait.
    """
    from reportlab.lib.pagesizes import A4, landscape  # noqa: WPS433
    from reportlab.platypus import (  # noqa: WPS433
        BaseDocTemplate, NextPageTemplate, PageBreak,
    )

    title = _project_doc_title(project)
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, title=title)
    _add_mixed_orientation_templates(
        doc, first="landscape" if diagram_rlg is not None else "portrait",
    )
    story = []

    if diagram_rlg is not None:
        story.append(_heading("Traceability diagram", level=1))
        story.append(_para(f"<b>{title}</b>"))
        story.append(_para(f"Generated: {_now_iso()} · kiwitcms-requirements v{__version__}"))
        story.append(_spacer(12))
        landscape_width = landscape(A4)[0] - (2 * 72)
        story.append(_scaled_drawing(diagram_rlg, landscape_width))
        story.append(_para(
            "Project-scoped Sankey rendered from the browser at the time "
            "of export. Blue = requirements, orange = test cases, "
            "green = test plans, purple = bugs, red strokes = suspect links."
        ))
        story.append(NextPageTemplate("portrait"))
        story.append(PageBreak())

    story.append(_heading(title))
    story.append(_para(f"Generated: {_now_iso()} · kiwitcms-requirements v{__version__}"))
    story.append(_spacer())
    story.append(_heading("Programme metadata", level=2))
    story.append(_table(
        [["Field", "Value"]] + _project_metadata_kv(project),
        col_widths=[160, 290],
    ))
    story.append(_spacer())

    coverage = (snapshot or {}).get("coverage", {}) or {}
    story.append(_heading("Coverage snapshot", level=2))
    story.append(_table([
        ["Metric", "Value"],
        ["Total requirements", str((snapshot or {}).get("total", 0))],
        ["Coverage %", f"{coverage.get('percent', 0)}%"],
        ["Linked / total",
         f"{coverage.get('linked', 0)} / {coverage.get('total', 0)}"],
        ["Orphan requirements", str((snapshot or {}).get("orphan_requirements", 0))],
        ["Suspect links", str((snapshot or {}).get("suspect_link_count", 0))],
    ], col_widths=[225, 225]))
    story.append(_spacer())

    plans = list(project.test_plans.all())
    if plans:
        story.append(_heading("Test plans in scope", level=2))
        plan_rows = [["ID", "Name"]]
        for plan in plans:
            plan_rows.append([f"TP-{plan.pk}", getattr(plan, "name", "") or ""])
        story.append(_table(plan_rows, col_widths=[60, 420]))
        story.append(_spacer())

    reqs = list(requirements)
    story.append(_heading("Requirements", level=2))
    story.append(_para(f"<b>{len(reqs)}</b> requirement(s) in this project."))
    story.append(_spacer())

    if reqs:
        rows = [["ID", "Title", "Level", "Status", "Priority", "Links"]]
        for r in reqs:
            rows.append([
                r.identifier,
                r.title,
                r.level.name if r.level_id else "—",
                r.get_status_display(),
                r.get_priority_display(),
                str(r.case_links.count()),
            ])
        story.append(_table(rows, col_widths=[60, 180, 70, 70, 60, 40]))

    doc.build(story)
    return buf.getvalue()


def _project_doc_title(project) -> str:
    """Single-line title used as the PDF/document title.

    Includes product + project name + project code so the file makes
    sense out of context (e.g. when emailed to a stakeholder).
    """
    parts = [f"Project: {project.name}"]
    if project.code:
        parts.append(f"({project.code})")
    if project.product_id:
        parts.append(f"— {project.product.name}")
    return " ".join(parts)


def _project_metadata_kv(project) -> list:
    owner = "—"
    if project.owner_id:
        owner = project.owner.get_full_name() or project.owner.username
    return [
        ["Code", project.code or "—"],
        ["Product", str(project.product)],
        ["Status", project.get_status_display()],
        ["Owner", owner],
        ["Start date", _pdf_format_date_with_week(project.start_date)],
        ["Target end date", _pdf_format_date_with_week(project.target_end_date)],
        ["Actual end date", _pdf_format_date_with_week(project.actual_end_date)],
        ["JIRA project key", project.jira_project_key or "—"],
    ]


def _pdf_format_date_with_week(value) -> str:
    if not value:
        return "—"
    return f"{value.isoformat()} (W{value.isocalendar()[1]})"


def _pdf_bug_cell(row) -> str:
    if not row.get("bug_id"):
        return "—"
    suffix = " [open]" if row.get("bug_open") else " [closed]"
    summary = row.get("bug_summary") or ""
    return f"BUG-{row['bug_id']}{suffix} {summary}".strip()


def _append_count_section(story, rows, title, row_label, row_key=None):
    story.append(_heading(title, level=2))
    if not rows:
        story.append(_para("—"))
        story.append(_spacer())
        return
    table_rows = [[row_label, "Count"]]
    for row in rows:
        key = row_key or row_label.lower()
        table_rows.append([str(row.get(key, "—")), str(row.get("count", 0))])
    story.append(_table(table_rows, col_widths=[220, 220]))
    story.append(_spacer())
