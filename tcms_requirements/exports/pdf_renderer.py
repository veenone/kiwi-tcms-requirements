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


def _table(data, col_widths=None):
    from reportlab.lib import colors  # noqa: WPS433
    from reportlab.platypus import Table, TableStyle

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
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
    ]))
    return tbl


def _spacer(height=8):
    from reportlab.platypus import Spacer  # noqa: WPS433
    return Spacer(1, height)


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
    from reportlab.platypus import SimpleDocTemplate

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=title)
    story = [
        _heading(title),
        _para(f"Generated: {_now_iso()} · kiwitcms-requirements v{__version__}"),
        _spacer(),
    ]

    if diagram_rlg is not None:
        # Scale the drawing to fit the usable width of a landscape A4 page.
        from reportlab.lib.units import cm  # noqa: WPS433

        usable_width_pts = landscape(A4)[0] - (2 * cm)
        scale = usable_width_pts / max(diagram_rlg.width, 1)
        diagram_rlg.width = diagram_rlg.width * scale
        diagram_rlg.height = diagram_rlg.height * scale
        diagram_rlg.scale(scale, scale)
        story.append(_heading("Traceability diagram", level=2))
        story.append(diagram_rlg)
        story.append(_para(
            "Blue = requirements, orange = test cases, green = test plans, "
            "red strokes = suspect links."
        ))
        story.append(_spacer(12))

    story.append(_heading("Traceability table", level=2))
    story.append(_para(f"<b>{len(rows)} row(s).</b>"))
    story.append(_spacer())

    if not rows:
        story.append(_para("No traceability rows match the current filters."))
        doc.build(story)
        return buf.getvalue()

    table_rows = [["Requirement", "Title", "Level", "Link", "Test case", "Test plan", "Suspect?"]]
    for row in rows:
        table_rows.append([
            row["req_identifier"],
            row["req_title"],
            row["level"] or "—",
            row["link_type"] or "—",
            f"TC-{row['case_id']}" if row["case_id"] else "—",
            row["plan_name"] or "—",
            "SUSPECT" if row["suspect"] else "",
        ])
    story.append(_table(table_rows, col_widths=[80, 220, 60, 60, 60, 140, 50]))

    doc.build(story)
    return buf.getvalue()


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
