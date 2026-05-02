"""Views for the Requirements plugin.

Class-based throughout, with `PermissionRequiredMixin` tags so Django's
permission framework owns access control. CSV / JIRA-CSV / JSON exports
dispatch through a small adapter so adding Excel / DOCX / PDF later is
a single new branch.
"""
import csv
import io
import json
import logging
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from tcms_requirements.dashboard.metrics import dashboard_snapshot
from tcms_requirements.exports.csv_export import write_csv
from tcms_requirements.exports.jira_csv_export import write_jira_csv
from tcms_requirements.exports.json_export import build_json_payload
from tcms_requirements.exports.templates import (
    build_xlsx_template,
    write_csv_template,
)
from tcms_requirements.exports.docx_renderer import (
    build_dashboard_docx,
    build_requirement_list_docx,
    build_traceability_docx,
)
from tcms_requirements.exports.pdf_renderer import (
    build_dashboard_pdf,
    build_requirement_list_pdf,
    build_traceability_pdf,
)
from tcms_requirements.forms import (
    CSVImportForm,
    LinkCaseForm,
    ProjectBaselineForm,
    ProjectForm,
    RequirementFilterForm,
    RequirementForm,
)
from tcms_requirements.imports.csv_import import import_bytes
from tcms_requirements.models import (
    Feature,
    Project,
    ProjectBaseline,
    Requirement,
    RequirementSignature,
    RequirementTestCaseLink,
)

logger = logging.getLogger("tcms_requirements")


# ── list ──────────────────────────────────────────────────────────────
class RequirementListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "tcms_requirements.view_requirement"
    model = Requirement
    template_name = "tcms_requirements/list.html"
    context_object_name = "requirements"
    paginate_by = 50

    def get_queryset(self):
        qs = (
            Requirement.objects
            .select_related("category", "source", "level", "product", "project", "feature")
            .prefetch_related("case_links")
            .order_by("identifier")
        )
        form = RequirementFilterForm(self.request.GET or None)
        if form.is_valid():
            data = form.cleaned_data
            if data.get("q"):
                q = data["q"]
                qs = qs.filter(
                    Q(identifier__icontains=q)
                    | Q(title__icontains=q)
                    | Q(description__icontains=q)
                    | Q(jira_issue_key__icontains=q)
                )
            for key in ("status", "priority"):
                if data.get(key):
                    qs = qs.filter(**{key: data[key]})
            for key in ("category", "level", "source", "project", "feature"):
                if data.get(key):
                    qs = qs.filter(**{key: data[key]})
        self._filter_form = form
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = self._filter_form
        return ctx


# ── CRUD ──────────────────────────────────────────────────────────────
class RequirementDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "tcms_requirements.view_requirement"
    model = Requirement
    template_name = "tcms_requirements/get.html"
    context_object_name = "requirement"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        req = self.object
        ctx["case_links"] = (
            req.case_links
            .select_related("case", "created_by")
            .order_by("-created_at")
        )
        ctx["child_requirements"] = req.child_requirements.all().order_by("identifier")
        ctx["history"] = req.history.all()[:100]
        ctx["signatures"] = (
            req.signatures.select_related("signed_by").order_by("-signed_at")
        )
        return ctx


class RequirementCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "tcms_requirements.add_requirement"
    model = Requirement
    form_class = RequirementForm
    template_name = "tcms_requirements/mutable.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Created requirement {self.object.identifier}.")
        return response


class RequirementUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "tcms_requirements.change_requirement"
    model = Requirement
    form_class = RequirementForm
    template_name = "tcms_requirements/mutable.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Updated requirement {self.object.identifier}.")
        return response


class RequirementDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    permission_required = "tcms_requirements.delete_requirement"
    model = Requirement
    template_name = "tcms_requirements/confirm_delete.html"
    success_url = reverse_lazy("requirement-list")


# ── test case linking ────────────────────────────────────────────────
class RequirementLinkCasesView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    permission_required = "tcms_requirements.add_requirementtestcaselink"
    template_name = "tcms_requirements/link.html"
    form_class = LinkCaseForm

    def dispatch(self, request, *args, **kwargs):
        self.requirement = get_object_or_404(Requirement, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["requirement"] = self.requirement
        ctx["case_links"] = (
            self.requirement.case_links
            .select_related("case", "created_by")
            .order_by("-created_at")
        )
        return ctx

    def form_valid(self, form):
        # Lazy-import the Kiwi TestCase model.
        from tcms.testcases.models import TestCase  # noqa: WPS433

        case = get_object_or_404(TestCase, pk=form.cleaned_data["case_id"])

        link, created = RequirementTestCaseLink.objects.get_or_create(
            requirement=self.requirement,
            case=case,
            link_type=form.cleaned_data["link_type"],
            defaults={
                "coverage_notes": form.cleaned_data.get("coverage_notes") or "",
                "created_by": self.request.user,
                "suspect": False,
            },
        )
        if not created:
            link.coverage_notes = form.cleaned_data.get("coverage_notes") or link.coverage_notes
            link.suspect = False
            link.save(update_fields=["coverage_notes", "suspect"])
            messages.info(
                self.request,
                f"Updated existing link to TC-{case.pk} ({link.get_link_type_display()}).",
            )
        else:
            messages.success(
                self.request,
                f"Linked TC-{case.pk} as {link.get_link_type_display()}.",
            )
        return redirect("requirement-link-cases", pk=self.requirement.pk)


class ClearSuspectView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "tcms_requirements.change_requirementtestcaselink"

    def post(self, request, pk, link_id):
        link = get_object_or_404(
            RequirementTestCaseLink,
            pk=link_id,
            requirement_id=pk,
        )
        link.suspect = False
        link.save(update_fields=["suspect"])
        messages.success(
            request,
            f"Cleared suspect flag on TC-{link.case_id}.",
        )
        return redirect("requirement-get", pk=pk)


# ── import ───────────────────────────────────────────────────────────
class RequirementImportView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    permission_required = "tcms_requirements.add_requirement"
    template_name = "tcms_requirements/import.html"
    form_class = CSVImportForm

    def form_valid(self, form):
        uploaded = form.cleaned_data["csv_file"]
        dry_run = form.cleaned_data.get("dry_run", True)
        data = uploaded.read()
        result = import_bytes(
            data,
            filename=uploaded.name,
            dry_run=dry_run,
            user=self.request.user,
        )
        ctx = self.get_context_data(form=form)
        ctx["import_result"] = result
        ctx["dry_run_used"] = dry_run
        if dry_run:
            messages.info(
                self.request,
                f"Dry run: {result.rows_ok} valid, {len(result.errors)} errors.",
            )
        else:
            messages.success(
                self.request,
                f"Imported {result.rows_created} new + {result.rows_updated} updated "
                f"({len(result.errors)} errors).",
            )
        return self.render_to_response(ctx)


# ── templates (CSV + XLSX import scaffolds) ─────────────────────────
class ImportTemplateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Download a CSV or XLSX template pre-populated with headers + 3 sample rows."""
    permission_required = "tcms_requirements.view_requirement"

    def get(self, request, fmt):
        if fmt == "csv":
            buf = io.StringIO()
            write_csv_template(buf)
            resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = 'attachment; filename="requirements-template.csv"'
            return resp
        if fmt == "xlsx":
            payload = build_xlsx_template()
            resp = HttpResponse(
                payload,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            resp["Content-Disposition"] = 'attachment; filename="requirements-template.xlsx"'
            return resp
        return HttpResponseBadRequest("Unknown template format. Use 'csv' or 'xlsx'.")


# ── export ───────────────────────────────────────────────────────────
class RequirementExportHubView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = "tcms_requirements.view_requirement"
    template_name = "tcms_requirements/export_hub.html"


class RequirementExportView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "tcms_requirements.view_requirement"
    ALLOWED_FORMATS = {"csv", "jira-csv", "json", "docx", "pdf"}

    def get(self, request, fmt):
        if fmt not in self.ALLOWED_FORMATS:
            return HttpResponseBadRequest(
                f"Unknown format {fmt!r}. Allowed: {sorted(self.ALLOWED_FORMATS)}."
            )

        qs = (
            Requirement.objects
            .select_related("category", "source", "level", "product", "project", "feature", "parent_requirement")
            .prefetch_related("case_links__case")
            .order_by("identifier")
        )
        qs = self._apply_filters(qs, request.GET)

        stamp = datetime.now().strftime("%Y%m%d")
        if fmt == "csv":
            buf = io.StringIO()
            write_csv(qs, buf)
            return self._download(buf.getvalue(), f"requirements-{stamp}.csv", "text/csv")

        if fmt == "jira-csv":
            buf = io.StringIO()
            write_jira_csv(qs, buf)
            return self._download(
                buf.getvalue(),
                f"requirements-jira-{stamp}.csv",
                "text/csv",
            )

        if fmt == "json":
            payload = build_json_payload(qs)
            return JsonResponse(
                payload,
                json_dumps_params={"indent": 2, "default": str},
            )

        if fmt == "docx":
            payload = build_requirement_list_docx(qs)
            return self._binary_download(
                payload,
                f"requirements-{stamp}.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        if fmt == "pdf":
            payload = build_requirement_list_pdf(qs)
            return self._binary_download(
                payload,
                f"requirements-{stamp}.pdf",
                "application/pdf",
            )

        return HttpResponseBadRequest("unreachable")

    @staticmethod
    def _apply_filters(qs, params):
        for key in ("status", "priority", "category", "level", "source", "product", "project", "feature"):
            value = params.get(key)
            if not value:
                continue
            if key in {"category", "level", "source", "product", "project", "feature"}:
                qs = qs.filter(**{f"{key}_id": value})
            else:
                qs = qs.filter(**{key: value})
        q = params.get("q")
        if q:
            qs = qs.filter(
                Q(identifier__icontains=q)
                | Q(title__icontains=q)
                | Q(description__icontains=q)
            )
        return qs

    @staticmethod
    def _download(payload: str, filename: str, content_type: str) -> HttpResponse:
        resp = HttpResponse(payload, content_type=f"{content_type}; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @staticmethod
    def _binary_download(payload: bytes, filename: str, content_type: str) -> HttpResponse:
        resp = HttpResponse(payload, content_type=content_type)
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["Content-Length"] = str(len(payload))
        return resp


# ── dashboard ────────────────────────────────────────────────────────
class RequirementDashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = "tcms_requirements.view_requirement"
    template_name = "tcms_requirements/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        filters = _parse_dashboard_filters(self.request.GET)
        ctx["filter_values"] = filters
        ctx["snapshot"] = dashboard_snapshot(filters=filters)
        ctx["snapshot_json"] = json.dumps(ctx["snapshot"], default=str)
        ctx["products"] = _filter_options("product")
        ctx["projects"] = _filter_options("project")
        ctx["features"] = _filter_options("feature")
        return ctx


class RequirementDashboardExportView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Download the current dashboard snapshot as DOCX or PDF."""
    permission_required = "tcms_requirements.view_requirement"

    def get(self, request, fmt):
        filters = _parse_dashboard_filters(request.GET)
        snapshot = dashboard_snapshot(filters=filters)
        stamp = datetime.now().strftime("%Y%m%d")
        if fmt == "docx":
            payload = build_dashboard_docx(snapshot)
            return RequirementExportView._binary_download(
                payload,
                f"requirements-dashboard-{stamp}.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        if fmt == "pdf":
            payload = build_dashboard_pdf(snapshot)
            return RequirementExportView._binary_download(
                payload,
                f"requirements-dashboard-{stamp}.pdf",
                "application/pdf",
            )
        return HttpResponseBadRequest("Format must be 'docx' or 'pdf'.")


# ── filter helpers (used by dashboard + diagram views) ───────────────
def _parse_dashboard_filters(params):
    out = {}
    for key in ("product", "project", "feature"):
        value = params.get(key)
        if value:
            try:
                out[key] = int(value)
            except ValueError:
                continue
    return out


def _filter_options(kind):
    """Build (id, label) tuples for the dashboard filter dropdowns.

    Kiwi core models are lazy-imported so the plugin doesn't break when
    Kiwi isn't installed (e.g. during standalone unit tests).
    """
    if kind == "product":
        try:
            from tcms.management.models import Product  # noqa: WPS433
            return [(p.pk, p.name) for p in Product.objects.order_by("name")]
        except Exception:  # noqa: BLE001
            return []
    if kind == "project":
        from tcms_requirements.models import Project  # noqa: WPS433
        return [(p.pk, str(p)) for p in Project.objects.select_related("product").order_by("product__name", "name")]
    if kind == "feature":
        from tcms_requirements.models import Feature  # noqa: WPS433
        return [(f.pk, str(f)) for f in Feature.objects.order_by("name")]
    return []


# ── traceability (sankey) ────────────────────────────────────────────
class RequirementTraceabilityExportView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Export the traceability view as DOCX or PDF.

    Accepts both GET (table-only, no diagram) and POST (client submits the
    rendered SVG payload in `svg`). GET is handy for direct-URL debugging
    and for teams that just want the row table without the Sankey image.
    """
    permission_required = "tcms_requirements.view_requirement"

    def post(self, request, fmt):
        return self._export(request, fmt, request.POST)

    def get(self, request, fmt):
        return self._export(request, fmt, request.GET)

    def _export(self, request, fmt, params):
        if fmt not in {"docx", "pdf"}:
            return HttpResponseBadRequest("Format must be 'docx' or 'pdf'.")

        try:
            from tcms_requirements.traceability.diagram import (  # noqa: WPS433
                _case_to_bugs,
                _case_to_plans,
            )
            from tcms_requirements.traceability.report import (  # noqa: WPS433
                flatten_traceability,
                svg_to_png_bytes,
                svg_to_rlg,
            )

            filters = _parse_dashboard_filters(params)
            svg_blob = params.get("svg", "") or ""

            qs = (
                Requirement.objects
                .select_related("level")
                .prefetch_related("case_links__case")
                .order_by("identifier")
            )
            if filters.get("product"):
                qs = qs.filter(product_id=filters["product"])
            if filters.get("project"):
                qs = qs.filter(project_id=filters["project"])
            if filters.get("feature"):
                qs = qs.filter(feature_id=filters["feature"])

            requirements = list(qs)
            all_case_ids = [
                link.case_id
                for req in requirements
                for link in req.case_links.all()
            ]
            case_plans = _case_to_plans(all_case_ids)
            case_bugs = _case_to_bugs(all_case_ids)
            rows = flatten_traceability(requirements, case_plans, case_bugs=case_bugs)

            title = self._build_traceability_title(filters)
            stamp = datetime.now().strftime("%Y%m%d")
            if fmt == "docx":
                png = svg_to_png_bytes(svg_blob) if svg_blob else None
                payload = build_traceability_docx(rows, title=title, diagram_png=png)
                return RequirementExportView._binary_download(
                    payload,
                    f"requirements-traceability-{stamp}.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            # fmt == "pdf"
            rlg = svg_to_rlg(svg_blob) if svg_blob else None
            payload = build_traceability_pdf(rows, title=title, diagram_rlg=rlg)
            return RequirementExportView._binary_download(
                payload,
                f"requirements-traceability-{stamp}.pdf",
                "application/pdf",
            )
        except Exception:
            logger.exception(
                "traceability export failed (fmt=%s, has_svg=%s)",
                fmt,
                bool(params.get("svg")),
            )
            return HttpResponse(
                "Traceability export failed. Check the server log for the "
                "traceback. Common cause: missing dependencies — run "
                "`pip install -e .` after upgrading the plugin so svglib, "
                "Pillow, python-docx, and reportlab are installed.",
                status=500,
                content_type="text/plain; charset=utf-8",
            )

    @staticmethod
    def _build_traceability_title(filters):
        """Add product / project / feature names to the export title so a
        filtered export reads as 'Requirements traceability — Product A ·
        Platform 2026 · Voice Control' rather than the bare report name.
        """
        bits = []
        product_id = filters.get("product")
        project_id = filters.get("project")
        feature_id = filters.get("feature")
        if product_id:
            from tcms.management.models import Product  # noqa: WPS433
            product = Product.objects.filter(pk=product_id).first()
            if product:
                bits.append(product.name)
        if project_id:
            project = Project.objects.filter(pk=project_id).first()
            if project:
                code = f" ({project.code})" if project.code else ""
                bits.append(f"{project.name}{code}")
        if feature_id:
            feature = Feature.objects.filter(pk=feature_id).first()
            if feature:
                bits.append(feature.name)
        suffix = " · ".join(bits)
        if suffix:
            return f"Requirements traceability — {suffix}"
        return "Requirements traceability report"


class _BaseTraceabilityView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """Shared base for the four Sankey views — DRY common context."""
    permission_required = "tcms_requirements.view_requirement"
    template_name = "tcms_requirements/traceability.html"
    view_key = ""
    view_title = ""
    view_subtitle = ""
    show_export_buttons = False

    # Shared catalogue used to render the view-switcher tabs at the top
    # of every Sankey page. (key, icon, label, subtitle, url_name.)
    VIEWS = [
        ("default", "fa-sitemap", "Full chain",
         "Requirement → Test case → Test plan → Bug",
         "requirement-traceability"),
        ("feature", "fa-th-large", "By feature",
         "Requirement → Feature → Test case",
         "requirement-traceability-feature"),
        ("verification", "fa-check-circle", "Verification status",
         "Requirement → Test case → Latest execution result",
         "requirement-traceability-verification"),
        ("document", "fa-file-text-o", "By source document",
         "Source document → Requirement → Test case",
         "requirement-traceability-document"),
    ]

    def _build_payload(self, filters):
        raise NotImplementedError

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        filters = _parse_dashboard_filters(self.request.GET)
        ctx["filter_values"] = filters
        ctx["payload_json"] = json.dumps(
            self._build_payload(filters=filters),
            default=str,
        )
        ctx["products"] = _filter_options("product")
        ctx["projects"] = _filter_options("project")
        ctx["features"] = _filter_options("feature")
        ctx["view_key"] = self.view_key
        ctx["view_title"] = self.view_title
        ctx["view_subtitle"] = self.view_subtitle
        ctx["available_views"] = self.VIEWS
        ctx["show_export_buttons"] = self.show_export_buttons
        return ctx


class RequirementTraceabilityView(_BaseTraceabilityView):
    """Default 4-column chain: Requirement → TestCase → TestPlan → Bug.

    Also serves `requirement-traceability-linear` for backward compat —
    the separate linear view was folded in once the default adopted
    the 4-column layout.
    """
    view_key = "default"
    view_title = "Full traceability chain"
    view_subtitle = "Requirement → Test case → Test plan → Bug"
    show_export_buttons = True

    def _build_payload(self, filters):
        from tcms_requirements.traceability.diagram import build_sankey_payload  # noqa: WPS433
        return build_sankey_payload(filters=filters)


class RequirementTraceabilityFeatureView(_BaseTraceabilityView):
    """3-column flow: Requirement → Feature → TestCase."""
    view_key = "feature"
    view_title = "By feature"
    view_subtitle = "Requirement → Feature → Test case"
    show_export_buttons = True

    def _build_payload(self, filters):
        from tcms_requirements.traceability.diagram import build_feature_sankey_payload  # noqa: WPS433
        return build_feature_sankey_payload(filters=filters)


class RequirementTraceabilityVerificationView(_BaseTraceabilityView):
    """3-column flow: Requirement → TestCase → Latest execution status.

    The audit-evidence view — shows what proportion of requirements is
    backed by passing tests right now. The single most useful one for
    release-go/no-go conversations.
    """
    view_key = "verification"
    view_title = "Verification status"
    view_subtitle = "Requirement → Test case → Latest execution result"
    show_export_buttons = True

    def _build_payload(self, filters):
        from tcms_requirements.traceability.diagram import build_verification_sankey_payload  # noqa: WPS433
        return build_verification_sankey_payload(filters=filters)


class RequirementTraceabilityDocumentView(_BaseTraceabilityView):
    """3-column flow: Source document → Requirement → Test case.

    Aggregates requirements by their `document_title` (with file-name and
    blank-document fallbacks) so reviewers can see which source documents
    have weak verification coverage.
    """
    view_key = "document"
    view_title = "By source document"
    view_subtitle = "Source document → Requirement → Test case"
    show_export_buttons = True

    def _build_payload(self, filters):
        from tcms_requirements.traceability.diagram import build_document_sankey_payload  # noqa: WPS433
        return build_document_sankey_payload(filters=filters)


# ── projects (programme-record views) ────────────────────────────────
class ProjectListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Kanban grid of programmes — one column per lifecycle status."""
    permission_required = "tcms_requirements.view_requirement"
    model = Project
    template_name = "tcms_requirements/project_list.html"
    context_object_name = "projects"
    paginate_by = None  # Kanban view shows everything; status filter narrows.

    # Programme lifecycle. Drives column order on the Kanban board and
    # the within-status sort fallback on the legacy card grid.
    _LIFECYCLE = ("planning", "active", "on_hold", "closed", "cancelled")

    def get_queryset(self):
        qs = (
            Project.objects
            .select_related("product", "owner")
            .prefetch_related("test_plans", "stakeholders")
        )
        status = self.request.GET.get("status", "").strip()
        if status and status in dict(Project.STATUS_CHOICES):
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cards = []
        for project in ctx["projects"]:
            snapshot = dashboard_snapshot(filters={"project": project.pk})
            cards.append({
                "project": project,
                "coverage": snapshot["coverage"],
                "total": snapshot["total"],
                "orphans": snapshot["orphan_requirements"],
                "suspects": snapshot["suspect_link_count"],
            })
        cards.sort(key=lambda c: (
            c["project"].product.name,
            c["project"].name,
        ))

        active_status = self.request.GET.get("status", "").strip()
        # When a status filter is active, only show that one column.
        # Otherwise render every lifecycle column so empty lanes still
        # signal "no work in this stage" instead of disappearing.
        visible_lifecycle = (
            (active_status,) if active_status in self._LIFECYCLE else self._LIFECYCLE
        )

        status_labels = dict(Project.STATUS_CHOICES)
        columns = []
        for status in visible_lifecycle:
            columns.append({
                "key": status,
                "label": status_labels.get(status, status),
                "cards": [c for c in cards if c["project"].status == status],
            })

        ctx["cards"] = cards
        ctx["columns"] = columns
        ctx["active_status"] = active_status
        ctx["status_choices"] = Project.STATUS_CHOICES
        return ctx


class ProjectDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Single project: metadata + scoped dashboard + Sankey + exports."""
    permission_required = "tcms_requirements.view_requirement"
    model = Project
    template_name = "tcms_requirements/project_get.html"
    context_object_name = "project"

    def get_queryset(self):
        return (
            Project.objects
            .select_related("product", "owner")
            .prefetch_related("test_plans", "stakeholders")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project = self.object
        filters = {"project": project.pk}
        snapshot = dashboard_snapshot(filters=filters)
        ctx["snapshot"] = snapshot
        ctx["snapshot_json"] = json.dumps(snapshot, default=str)

        from tcms_requirements.traceability.diagram import build_sankey_payload  # noqa: WPS433
        ctx["sankey_payload_json"] = json.dumps(
            build_sankey_payload(filters=filters),
            default=str,
        )

        ctx["requirements"] = (
            Requirement.objects
            .filter(project=project)
            .select_related("level", "feature", "category")
            .prefetch_related("case_links")
            .order_by("identifier")
        )
        ctx["features"] = project.features.all().order_by("name")
        return ctx


class ProjectCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "tcms_requirements.add_project"
    model = Project
    form_class = ProjectForm
    template_name = "tcms_requirements/project_mutable.html"
    success_url = reverse_lazy("requirement-project-list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Created project {self.object.name}.")
        return response


class ProjectUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "tcms_requirements.change_project"
    model = Project
    form_class = ProjectForm
    template_name = "tcms_requirements/project_mutable.html"

    def get_success_url(self):
        return reverse("requirement-project-get", args=[self.object.pk])

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Updated project {self.object.name}.")
        return response


class ProjectDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    permission_required = "tcms_requirements.delete_project"
    model = Project
    template_name = "tcms_requirements/project_confirm_delete.html"
    success_url = reverse_lazy("requirement-project-list")


class ProjectExportView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Download a project's requirements + metadata as DOCX or PDF.

    GET delivers a table-only export (works from any link). POST accepts a
    ``svg`` field carrying the live-rendered project Sankey, which is
    rasterised and embedded above the requirements table — same flow as
    the traceability-page export.
    """
    permission_required = "tcms_requirements.view_requirement"
    ALLOWED_FORMATS = {"docx", "pdf"}

    def get(self, request, pk, fmt):
        return self._export(request, pk, fmt, svg_blob="")

    def post(self, request, pk, fmt):
        return self._export(request, pk, fmt, svg_blob=request.POST.get("svg", "") or "")

    def _export(self, request, pk, fmt, svg_blob):
        if fmt not in self.ALLOWED_FORMATS:
            return HttpResponseBadRequest(
                f"Format must be one of {sorted(self.ALLOWED_FORMATS)}."
            )
        project = get_object_or_404(
            Project.objects.select_related("product", "owner"),
            pk=pk,
        )

        from tcms_requirements.exports.docx_renderer import build_project_docx  # noqa: WPS433
        from tcms_requirements.exports.pdf_renderer import build_project_pdf  # noqa: WPS433
        from tcms_requirements.traceability.report import (  # noqa: WPS433
            svg_to_png_bytes,
            svg_to_rlg,
        )

        snapshot = dashboard_snapshot(filters={"project": project.pk})
        requirements = (
            Requirement.objects
            .filter(project=project)
            .select_related("level", "category", "product", "project", "feature")
            .prefetch_related("case_links__case")
            .order_by("identifier")
        )

        stamp = datetime.now().strftime("%Y%m%d")
        slug = project.code or f"project-{project.pk}"
        if fmt == "docx":
            png = svg_to_png_bytes(svg_blob) if svg_blob else None
            payload = build_project_docx(project, requirements, snapshot, diagram_png=png)
            return RequirementExportView._binary_download(
                payload,
                f"project-{slug}-{stamp}.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        rlg = svg_to_rlg(svg_blob) if svg_blob else None
        payload = build_project_pdf(project, requirements, snapshot, diagram_rlg=rlg)
        return RequirementExportView._binary_download(
            payload,
            f"project-{slug}-{stamp}.pdf",
            "application/pdf",
        )


# ── v0.4: project baselines (audit replay) ────────────────────────────
class ProjectBaselineListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """All baselines belonging to one project."""
    permission_required = "tcms_requirements.view_requirement"
    template_name = "tcms_requirements/project_baseline_list.html"
    context_object_name = "baselines"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(Project, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            ProjectBaseline.objects
            .filter(project=self.project)
            .select_related("created_by", "version")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["project"] = self.project
        return ctx


class ProjectBaselineCreateView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """Freeze the project's current requirement set as a named baseline."""
    permission_required = "tcms_requirements.add_project"
    template_name = "tcms_requirements/project_baseline_mutable.html"
    form_class = ProjectBaselineForm

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(Project, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.project
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["project"] = self.project
        return ctx

    def form_valid(self, form):
        baseline = ProjectBaseline.freeze(
            self.project,
            form.cleaned_data["name"],
            notes=form.cleaned_data.get("notes", ""),
            version=form.cleaned_data.get("version"),
            created_by=self.request.user if self.request.user.is_authenticated else None,
        )
        messages.success(
            self.request,
            f"Froze baseline '{baseline.name}' "
            f"({baseline.requirement_snapshots.count()} requirements, "
            f"{baseline.link_snapshots.count()} links).",
        )
        return redirect(reverse(
            "requirement-project-baseline-get",
            args=[self.project.pk, baseline.pk],
        ))


class ProjectBaselineDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Frozen requirement table + link table for one baseline."""
    permission_required = "tcms_requirements.view_requirement"
    model = ProjectBaseline
    template_name = "tcms_requirements/project_baseline_get.html"
    context_object_name = "baseline"
    pk_url_kwarg = "bid"

    def get_queryset(self):
        return (
            ProjectBaseline.objects
            .filter(project_id=self.kwargs["pk"])
            .select_related("project", "project__product", "created_by", "version")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["project"] = self.object.project
        ctx["requirement_snapshots"] = (
            self.object.requirement_snapshots.all().order_by("identifier")
        )
        ctx["link_snapshots"] = (
            self.object.link_snapshots.all().order_by("requirement_identifier", "case_id")
        )
        # Other baselines (for diff target dropdown).
        ctx["sibling_baselines"] = (
            ProjectBaseline.objects
            .filter(project=self.object.project)
            .exclude(pk=self.object.pk)
            .order_by("-created_at")
        )
        return ctx


class ProjectBaselineDiffView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """Diff two baselines into added / removed / modified buckets."""
    permission_required = "tcms_requirements.view_requirement"
    template_name = "tcms_requirements/project_baseline_diff.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project = get_object_or_404(Project, pk=kwargs["pk"])
        base = get_object_or_404(ProjectBaseline, pk=kwargs["bid"], project=project)
        other = get_object_or_404(ProjectBaseline, pk=kwargs["other_bid"], project=project)

        ctx["project"] = project
        ctx["base"] = base
        ctx["other"] = other
        ctx["diff"] = _diff_baselines(base, other)
        return ctx


def _diff_baselines(base, other):
    """Bucket requirement snapshots into added / removed / modified."""
    base_by_id = {s.identifier: s for s in base.requirement_snapshots.all()}
    other_by_id = {s.identifier: s for s in other.requirement_snapshots.all()}

    added = sorted(set(other_by_id) - set(base_by_id))
    removed = sorted(set(base_by_id) - set(other_by_id))
    modified = []
    for ident in sorted(set(base_by_id) & set(other_by_id)):
        b = base_by_id[ident]
        o = other_by_id[ident]
        changed_fields = []
        for field in ("title", "status", "priority", "level_code", "asil", "sil",
                      "iec62304_class", "dal"):
            if getattr(b, field) != getattr(o, field):
                changed_fields.append({
                    "field": field,
                    "base": getattr(b, field),
                    "other": getattr(o, field),
                })
        if b.payload != o.payload:
            for key in sorted(set(b.payload) | set(o.payload)):
                if b.payload.get(key) != o.payload.get(key):
                    changed_fields.append({
                        "field": f"payload.{key}",
                        "base": b.payload.get(key),
                        "other": o.payload.get(key),
                    })
        if changed_fields:
            modified.append({"identifier": ident, "changes": changed_fields})

    return {
        "added": [other_by_id[i] for i in added],
        "removed": [base_by_id[i] for i in removed],
        "modified": modified,
    }


class ProjectBaselineExportView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Download a baseline's frozen state as DOCX / PDF / CSV."""
    permission_required = "tcms_requirements.view_requirement"
    ALLOWED_FORMATS = {"docx", "pdf", "csv"}

    def get(self, request, pk, bid, fmt):
        if fmt not in self.ALLOWED_FORMATS:
            return HttpResponseBadRequest(
                f"Format must be one of {sorted(self.ALLOWED_FORMATS)}."
            )
        baseline = get_object_or_404(
            ProjectBaseline.objects
            .filter(project_id=pk)
            .select_related("project", "project__product", "version", "created_by"),
            pk=bid,
        )
        snapshots = list(baseline.requirement_snapshots.all().order_by("identifier"))
        link_snapshots = list(baseline.link_snapshots.all())

        from tcms_requirements.exports.baseline_export import (  # noqa: WPS433
            build_baseline_csv,
            build_baseline_docx,
            build_baseline_pdf,
        )

        slug = (baseline.project.code or f"project-{baseline.project_id}") + f"-{baseline.name}"
        slug = slug.replace(" ", "-")
        if fmt == "csv":
            payload = build_baseline_csv(baseline, snapshots, link_snapshots)
            return RequirementExportView._binary_download(
                payload,
                f"baseline-{slug}.csv",
                "text/csv",
            )
        if fmt == "docx":
            payload = build_baseline_docx(baseline, snapshots, link_snapshots)
            return RequirementExportView._binary_download(
                payload,
                f"baseline-{slug}.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        payload = build_baseline_pdf(baseline, snapshots, link_snapshots)
        return RequirementExportView._binary_download(
            payload,
            f"baseline-{slug}.pdf",
            "application/pdf",
        )


# ── v0.4: compliance evidence pack ───────────────────────────────────
class ProjectEvidencePackView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Bundle every audit artefact for a project into one .zip."""
    permission_required = "tcms_requirements.view_requirement"

    def get(self, request, pk):
        import zipfile  # noqa: WPS433
        from tcms_requirements import __version__  # noqa: WPS433

        project = get_object_or_404(
            Project.objects.select_related("product", "owner"), pk=pk,
        )
        requirements = list(
            Requirement.objects
            .filter(project=project)
            .select_related("level", "category", "product", "feature")
            .prefetch_related("case_links__case")
            .order_by("identifier")
        )
        snapshot = dashboard_snapshot(filters={"project": project.pk})
        latest_baseline = (
            ProjectBaseline.objects.filter(project=project)
            .select_related("project__product", "version", "created_by")
            .order_by("-created_at").first()
        )
        signature_rows = (
            RequirementSignature.objects
            .filter(requirement__project=project)
            .select_related("requirement", "signed_by")
            .order_by("requirement__identifier", "-signed_at")
        )

        from tcms_requirements.exports.docx_renderer import build_project_docx  # noqa: WPS433
        from tcms_requirements.exports.pdf_renderer import build_project_pdf  # noqa: WPS433
        from tcms_requirements.exports.csv_export import write_csv  # noqa: WPS433
        from tcms_requirements.exports.jira_csv_export import write_jira_csv  # noqa: WPS433
        from tcms_requirements.exports.json_export import build_json_payload  # noqa: WPS433
        from tcms_requirements.exports.baseline_export import (  # noqa: WPS433
            build_baseline_csv, build_baseline_docx, build_baseline_pdf,
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            metadata = {
                "project": {
                    "id": project.pk,
                    "name": project.name,
                    "code": project.code,
                    "status": project.status,
                    "product": str(project.product),
                    "owner": (
                        project.owner.get_full_name() or project.owner.username
                        if project.owner_id else None
                    ),
                    "start_date": project.start_date.isoformat() if project.start_date else None,
                    "target_end_date": (
                        project.target_end_date.isoformat()
                        if project.target_end_date else None
                    ),
                    "actual_end_date": (
                        project.actual_end_date.isoformat()
                        if project.actual_end_date else None
                    ),
                    "jira_project_key": project.jira_project_key,
                },
                "plugin_version": __version__,
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "requirement_count": len(requirements),
                "signature_count": signature_rows.count(),
                "latest_baseline": latest_baseline.name if latest_baseline else None,
            }
            zf.writestr("metadata.json", json.dumps(metadata, indent=2))

            zf.writestr(
                "requirements.docx",
                build_project_docx(project, requirements, snapshot),
            )
            zf.writestr(
                "requirements.pdf",
                build_project_pdf(project, requirements, snapshot),
            )

            csv_buf = io.StringIO()
            write_csv(requirements, csv_buf)
            zf.writestr("requirements.csv", csv_buf.getvalue().encode("utf-8"))

            jira_buf = io.StringIO()
            write_jira_csv(requirements, jira_buf)
            zf.writestr("requirements-jira.csv", jira_buf.getvalue().encode("utf-8"))

            zf.writestr(
                "requirements.json",
                json.dumps(build_json_payload(requirements), indent=2, default=str).encode("utf-8"),
            )

            zf.writestr(
                "dashboard-snapshot.docx",
                build_dashboard_docx(snapshot),
            )
            zf.writestr(
                "dashboard-snapshot.pdf",
                build_dashboard_pdf(snapshot),
            )

            sig_csv = io.StringIO()
            sig_writer = csv.writer(sig_csv)
            sig_writer.writerow([
                "requirement_identifier", "signed_by", "signed_at",
                "signature_hash", "comment",
            ])
            for sig in signature_rows:
                sig_writer.writerow([
                    sig.requirement.identifier,
                    (sig.signed_by.get_full_name() or sig.signed_by.username)
                    if sig.signed_by_id else "",
                    sig.signed_at.isoformat(),
                    sig.signature_hash,
                    sig.comment,
                ])
            zf.writestr("signatures.csv", sig_csv.getvalue().encode("utf-8"))

            if latest_baseline:
                snaps = list(latest_baseline.requirement_snapshots.all())
                links = list(latest_baseline.link_snapshots.all())
                zf.writestr(
                    f"baseline-{latest_baseline.name}.docx",
                    build_baseline_docx(latest_baseline, snaps, links),
                )
                zf.writestr(
                    f"baseline-{latest_baseline.name}.pdf",
                    build_baseline_pdf(latest_baseline, snaps, links),
                )

        slug = project.code or f"project-{project.pk}"
        stamp = datetime.now().strftime("%Y%m%d")
        return RequirementExportView._binary_download(
            buf.getvalue(),
            f"evidence-pack-{slug}-{stamp}.zip",
            "application/zip",
        )


# ── v0.4: lightweight electronic signatures ──────────────────────────
class RequirementSignView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """POST creates a tamper-evident `RequirementSignature` row for a Requirement.

    Gated on the `requirements.approve_requirement` permission seeded since
    v0.2 but unused until now. NOT a state-machine extension — the signature
    records *who* attested *what state* of the requirement, but doesn't move
    the requirement between states.
    """
    permission_required = "tcms_requirements.approve_requirement"

    def get(self, request, pk):
        # Render a confirmation page so the operator sees what they're signing.
        from django.shortcuts import render  # noqa: WPS433
        requirement = get_object_or_404(Requirement, pk=pk)
        return render(
            request,
            "tcms_requirements/requirement_sign_confirm.html",
            {"requirement": requirement},
        )

    def post(self, request, pk):
        from django.utils import timezone  # noqa: WPS433
        requirement = get_object_or_404(Requirement, pk=pk)
        comment = (request.POST.get("comment") or "").strip()
        signed_at = timezone.now()
        digest = RequirementSignature.compute_hash(
            requirement, request.user.pk, signed_at,
        )
        sig = RequirementSignature.objects.create(
            requirement=requirement,
            signed_by=request.user,
            signature_hash=digest,
            comment=comment,
        )
        # auto_now_add overrides our signed_at; recompute hash so it matches DB.
        sig.signature_hash = RequirementSignature.compute_hash(
            requirement, request.user.pk, sig.signed_at,
        )
        sig.save(update_fields=["signature_hash"])
        messages.success(
            request,
            f"Signed {requirement.identifier}; hash {sig.signature_hash[:12]}…",
        )
        return redirect(reverse("requirement-get", args=[pk]))
