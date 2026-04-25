"""URL routing for the Requirements plugin.

Mounted by the host project under /requirements/ (exact prefix up to the
operator's urls.py). All names are plugin-unique so `reverse()` in menu.py
and templates resolves correctly.
"""
from django.urls import path

from tcms_requirements import views

urlpatterns = [
    # ── dashboard & landing ──────────────────────────────────────────
    path("", views.RequirementListView.as_view(), name="requirement-list"),
    path("dashboard/", views.RequirementDashboardView.as_view(), name="requirement-dashboard"),
    path(
        "dashboard/export/<str:fmt>/",
        views.RequirementDashboardExportView.as_view(),
        name="requirement-dashboard-export",
    ),
    path(
        "traceability/",
        views.RequirementTraceabilityView.as_view(),
        name="requirement-traceability",
    ),
    # Backward-compat: /traceability/linear/ used to be a separate view
    # before the default was switched to the 4-column linear layout.
    path(
        "traceability/linear/",
        views.RequirementTraceabilityView.as_view(),
        name="requirement-traceability-linear",
    ),
    path(
        "traceability/feature/",
        views.RequirementTraceabilityFeatureView.as_view(),
        name="requirement-traceability-feature",
    ),
    path(
        "traceability/verification/",
        views.RequirementTraceabilityVerificationView.as_view(),
        name="requirement-traceability-verification",
    ),
    path(
        "traceability/export/<str:fmt>/",
        views.RequirementTraceabilityExportView.as_view(),
        name="requirement-traceability-export",
    ),

    # ── projects ─────────────────────────────────────────────────────
    path(
        "projects/",
        views.ProjectListView.as_view(),
        name="requirement-project-list",
    ),
    path(
        "projects/<int:pk>/",
        views.ProjectDetailView.as_view(),
        name="requirement-project-get",
    ),
    path(
        "projects/new/",
        views.ProjectCreateView.as_view(),
        name="requirement-project-new",
    ),
    path(
        "projects/<int:pk>/edit/",
        views.ProjectUpdateView.as_view(),
        name="requirement-project-edit",
    ),
    path(
        "projects/<int:pk>/delete/",
        views.ProjectDeleteView.as_view(),
        name="requirement-project-delete",
    ),
    path(
        "projects/<int:pk>/export/<str:fmt>/",
        views.ProjectExportView.as_view(),
        name="requirement-project-export",
    ),

    # ── CRUD ─────────────────────────────────────────────────────────
    path("new/", views.RequirementCreateView.as_view(), name="requirement-new"),
    path("<int:pk>/", views.RequirementDetailView.as_view(), name="requirement-get"),
    path("<int:pk>/edit/", views.RequirementUpdateView.as_view(), name="requirement-edit"),
    path("<int:pk>/delete/", views.RequirementDeleteView.as_view(), name="requirement-delete"),

    # ── test case linking ────────────────────────────────────────────
    path("<int:pk>/link/", views.RequirementLinkCasesView.as_view(), name="requirement-link-cases"),
    path(
        "<int:pk>/link/<int:link_id>/clear-suspect/",
        views.ClearSuspectView.as_view(),
        name="requirement-link-clear-suspect",
    ),

    # ── import / export ──────────────────────────────────────────────
    path("import/", views.RequirementImportView.as_view(), name="requirement-import"),
    path(
        "import/template/<str:fmt>/",
        views.ImportTemplateView.as_view(),
        name="requirement-import-template",
    ),
    path("export/", views.RequirementExportHubView.as_view(), name="requirement-export-hub"),
    path("export/<str:fmt>/", views.RequirementExportView.as_view(), name="requirement-export"),
]
