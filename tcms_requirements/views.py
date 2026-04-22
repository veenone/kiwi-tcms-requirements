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
    RequirementFilterForm,
    RequirementForm,
)
from tcms_requirements.imports.csv_import import import_bytes
from tcms_requirements.models import (
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

    POST is used so the client can submit the rendered SVG payload. Query
    string still carries filters for the backend row set (dependent on
    how the user scoped the diagram, not the SVG contents).
    """
    permission_required = "tcms_requirements.view_requirement"

    def post(self, request, fmt):
        from tcms_requirements.traceability.diagram import _case_to_plans  # noqa: WPS433
        from tcms_requirements.traceability.report import (  # noqa: WPS433
            flatten_traceability,
            svg_to_png_bytes,
            svg_to_rlg,
        )

        filters = _parse_dashboard_filters(request.POST)
        svg_blob = request.POST.get("svg", "") or ""

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
        rows = flatten_traceability(requirements, case_plans)

        stamp = datetime.now().strftime("%Y%m%d")
        if fmt == "docx":
            png = svg_to_png_bytes(svg_blob) if svg_blob else None
            payload = build_traceability_docx(rows, diagram_png=png)
            return RequirementExportView._binary_download(
                payload,
                f"requirements-traceability-{stamp}.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        if fmt == "pdf":
            rlg = svg_to_rlg(svg_blob) if svg_blob else None
            payload = build_traceability_pdf(rows, diagram_rlg=rlg)
            return RequirementExportView._binary_download(
                payload,
                f"requirements-traceability-{stamp}.pdf",
                "application/pdf",
            )
        return HttpResponseBadRequest("Format must be 'docx' or 'pdf'.")


class RequirementTraceabilityView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """Interactive Sankey graph: Requirement -> TestCase -> TestPlan."""
    permission_required = "tcms_requirements.view_requirement"
    template_name = "tcms_requirements/traceability.html"

    def get_context_data(self, **kwargs):
        from tcms_requirements.traceability.diagram import build_sankey_payload  # noqa: WPS433

        ctx = super().get_context_data(**kwargs)
        filters = _parse_dashboard_filters(self.request.GET)
        ctx["filter_values"] = filters
        ctx["payload_json"] = json.dumps(
            build_sankey_payload(filters=filters),
            default=str,
        )
        ctx["products"] = _filter_options("product")
        ctx["projects"] = _filter_options("project")
        ctx["features"] = _filter_options("feature")
        return ctx
