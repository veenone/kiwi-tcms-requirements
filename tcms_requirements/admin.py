"""Django admin registrations.

The main Requirement editing UI lives in plugin views under /requirements/.
The admin is scoped to the taxonomy (category / source / level / project /
feature) plus a read-only Requirement admin for back-office inspection.
"""
from django.contrib import admin

from tcms_requirements.models import (
    BaselineLinkSnapshot,
    BaselineRequirementSnapshot,
    Feature,
    JiraIntegrationConfig,
    Project,
    Requirement,
    RequirementBaseline,
    RequirementCategory,
    RequirementLevel,
    RequirementSource,
    RequirementTestCaseLink,
)


@admin.register(RequirementCategory)
class RequirementCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "description")
    search_fields = ("name", "description")


@admin.register(RequirementSource)
class RequirementSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "source_type", "version", "reference")
    list_filter = ("source_type",)
    search_fields = ("name", "reference")


@admin.register(RequirementLevel)
class RequirementLevelAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("code", "name")
    ordering = ("order", "code")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "product", "code", "updated_at")
    list_filter = ("product",)
    search_fields = ("name", "code", "description")


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "product", "parent_feature", "updated_at")
    list_filter = ("project", "product")
    search_fields = ("name", "code", "description")


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    list_display = (
        "identifier", "title", "level", "status", "priority",
        "category", "product", "project", "feature", "updated_at",
    )
    list_filter = ("status", "priority", "level", "category", "product", "project")
    search_fields = ("identifier", "title", "description", "rationale", "doc_id", "jira_issue_key")
    readonly_fields = ("created_at", "updated_at", "created_by")
    fieldsets = (
        ("Identity", {
            "fields": ("identifier", "title", "description", "rationale"),
        }),
        ("Taxonomy", {
            "fields": ("category", "source", "source_section", "level"),
        }),
        ("Organisation", {
            "fields": ("product", "project", "feature", "parent_requirement"),
        }),
        ("Lifecycle", {
            "fields": ("status", "priority", "verification_method", "verification_exemption_reason"),
        }),
        ("Safety / criticality", {
            "classes": ("collapse",),
            "fields": ("asil", "sil", "iec62304_class", "dal"),
        }),
        ("Document control (ISO 9001 §7.5)", {
            "classes": ("collapse",),
            "fields": ("doc_id", "doc_revision", "effective_date", "superseded_by", "change_reason"),
        }),
        ("External system keys", {
            "classes": ("collapse",),
            "fields": ("jira_issue_key", "external_refs"),
        }),
        ("Audit", {
            "classes": ("collapse",),
            "fields": ("created_by", "created_at", "updated_at"),
        }),
    )


@admin.register(RequirementTestCaseLink)
class RequirementTestCaseLinkAdmin(admin.ModelAdmin):
    list_display = ("requirement", "case", "link_type", "suspect", "created_at")
    list_filter = ("link_type", "suspect")
    search_fields = ("requirement__identifier", "requirement__title")
    # `case` is intentionally NOT in autocomplete_fields: Kiwi core's
    # TestCaseAdmin doesn't declare search_fields, which would trigger
    # admin.E040. The primary linking UI lives at /requirements/<pk>/link/
    # where users enter a TestCase id directly, so the admin dropdown is
    # only an occasional-use escape hatch.
    autocomplete_fields = ("requirement",)
    raw_id_fields = ("case",)


@admin.register(RequirementBaseline)
class RequirementBaselineAdmin(admin.ModelAdmin):
    list_display = ("name", "product", "version", "created_at", "created_by")
    list_filter = ("product",)
    readonly_fields = ("created_at", "created_by")


@admin.register(BaselineRequirementSnapshot)
class BaselineRequirementSnapshotAdmin(admin.ModelAdmin):
    list_display = ("baseline", "identifier", "title", "status", "level_code")
    list_filter = ("baseline",)
    search_fields = ("identifier", "title")


@admin.register(BaselineLinkSnapshot)
class BaselineLinkSnapshotAdmin(admin.ModelAdmin):
    list_display = ("baseline", "requirement_identifier", "case_id", "link_type", "suspect")
    list_filter = ("baseline",)


@admin.register(JiraIntegrationConfig)
class JiraIntegrationConfigAdmin(admin.ModelAdmin):
    """Singleton — only one row should exist."""
    list_display = ("backend", "base_url", "default_project_key", "updated_at")

    def has_add_permission(self, request):
        if JiraIntegrationConfig.objects.exists():
            return False
        return super().has_add_permission(request)
