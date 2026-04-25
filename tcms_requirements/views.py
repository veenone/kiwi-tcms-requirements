"""Views for the Requirements plugin.

Class-based throughout, with `PermissionRequiredMixin` tags so Django's
permission framework owns access control. CSV / JIRA-CSV / JSON exports
dispatch through a small adapter so adding Excel / DOCX / PDF later is
a single new branch.
"""
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
    ProjectForm,
    RequirementFilterForm,
    RequirementForm,
)
from tcms_requirements.imports.csv_import import import_bytes
from tcms_requirements.models import (
    Project,
    Requirement,
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

            stamp = datetime.now().strftime("%Y%m%d")
            if fmt == "docx":
                png = svg_to_png_bytes(svg_blob) if svg_blob else None
                payload = build_traceability_docx(rows, diagram_png=png)
                return RequirementExportView._binary_download(
                    payload,
                    f"requirements-traceability-{stamp}.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            # fmt == "pdf"
            rlg = svg_to_rlg(svg_blob) if svg_blob else None
            payload = build_traceability_pdf(rows, diagram_rlg=rlg)
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


# ── projects (programme-record views) ────────────────────────────────
class ProjectListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Card grid of programmes with status, owner, and coverage at a glance."""
    permission_required = "tcms_requirements.view_requirement"
    model = Project
    template_name = "tcms_requirements/project_list.html"
    context_object_name = "projects"
    paginate_by = 24

    # Closed/cancelled programmes drop to the bottom; everything else
    # sorts by status priority then product/name for a stable display.
    _STATUS_ORDER = {
        "active": 0,
        "planning": 1,
        "on_hold": 2,
        "closed": 3,
        "cancelled": 4,
    }

    def get_queryset(self):
        return (
            Project.objects
            .select_related("product", "owner")
            .prefetch_related("test_plans", "stakeholders")
        )

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
            self._STATUS_ORDER.get(c["project"].status, 99),
            c["project"].product.name,
            c["project"].name,
        ))
        ctx["cards"] = cards
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
    """Download a project's requirements + metadata as DOCX or PDF."""
    permission_required = "tcms_requirements.view_requirement"
    ALLOWED_FORMATS = {"docx", "pdf"}

    def get(self, request, pk, fmt):
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
            payload = build_project_docx(project, requirements, snapshot)
            return RequirementExportView._binary_download(
                payload,
                f"project-{slug}-{stamp}.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        payload = build_project_pdf(project, requirements, snapshot)
        return RequirementExportView._binary_download(
            payload,
            f"project-{slug}-{stamp}.pdf",
            "application/pdf",
        )
