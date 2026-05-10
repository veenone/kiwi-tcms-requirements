"""Django admin registrations.

The main Requirement editing UI lives in plugin views under /requirements/.
The admin is scoped to the taxonomy (category / source / level / project /
feature) plus a read-only Requirement admin for back-office inspection.
"""
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse

from tcms_requirements.level_profiles import (
    LEVEL_PROFILES,
    PROFILE_DISPLAY,
    detect_active_profile,
)
from tcms_requirements.models import (
    BaselineLinkSnapshot,
    BaselineRequirementSnapshot,
    CustomFieldDefinition,
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
    change_list_template = "admin/tcms_requirements/requirementlevel/change_list.html"

    def get_urls(self):
        return [
            path(
                "profiles/",
                self.admin_site.admin_view(self.profiles_view),
                name="tcms_requirements_requirementlevel_profiles",
            ),
        ] + super().get_urls()

    def profiles_view(self, request):
        if request.method == "POST":
            profile_key = request.POST.get("profile", "").strip()
            if profile_key not in LEVEL_PROFILES:
                messages.error(request, f"Unknown profile: {profile_key!r}")
                return redirect(request.path)
            self._apply_profile(request, profile_key)
            return redirect(reverse("admin:tcms_requirements_requirementlevel_changelist"))

        active_profile = detect_active_profile(RequirementLevel)
        in_use_codes = set(
            Requirement.objects.exclude(level__isnull=True)
            .values_list("level__code", flat=True).distinct()
        )
        cards = []
        for key, rows in LEVEL_PROFILES.items():
            cards.append({
                "key": key,
                "label": PROFILE_DISPLAY.get(key, key),
                "rows": rows,
                "is_active": key == active_profile,
                "would_orphan": sorted(
                    in_use_codes - {code for (code, *_r) in rows}
                ),
            })
        ctx = {
            **self.admin_site.each_context(request),
            "title": "Requirement level profiles",
            "cards": cards,
            "active_profile": active_profile,
            "in_use_codes": sorted(in_use_codes),
            "opts": self.model._meta,
        }
        return render(
            request, "admin/tcms_requirements/requirementlevel/profiles.html", ctx,
        )

    def _apply_profile(self, request, profile_key):
        rows = LEVEL_PROFILES[profile_key]
        target_codes = {code for (code, *_r) in rows}
        in_use_codes = set(
            Requirement.objects.exclude(level__isnull=True)
            .values_list("level__code", flat=True).distinct()
        )

        for code, name, order, description in rows:
            RequirementLevel.objects.update_or_create(
                code=code,
                defaults={
                    "name": name, "order": order,
                    "description": description, "is_active": True,
                },
            )

        # Levels not in the profile are deactivated only if no requirement
        # references them; orphaning live data silently is too dangerous.
        deactivated = (
            RequirementLevel.objects
            .exclude(code__in=target_codes)
            .filter(is_active=True)
            .exclude(code__in=in_use_codes)
            .update(is_active=False)
        )
        skipped = sorted(in_use_codes - target_codes)

        messages.success(
            request,
            f"Applied profile {PROFILE_DISPLAY.get(profile_key, profile_key)}: "
            f"{len(rows)} levels active, {deactivated} deactivated.",
        )
        if skipped:
            messages.warning(
                request,
                f"Kept {len(skipped)} level(s) outside the profile because "
                f"requirements still reference them: {', '.join(skipped)}. "
                f"Reassign those requirements then re-apply to clean up.",
            )


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "product",
        "code",
        "status",
        "owner",
        "target_end_date",
        "updated_at",
    )
    list_filter = ("status", "product")
    search_fields = ("name", "code", "description", "jira_project_key")
    # Kiwi's TestPlanAdmin lacks search_fields, so autocomplete on
    # test_plans would trigger admin.E040. Use raw_id_fields instead.
    raw_id_fields = ("test_plans",)
    autocomplete_fields = ("owner", "stakeholders")
    fieldsets = (
        ("Identity", {
            "fields": ("name", "code", "description", "product"),
        }),
        ("Programme", {
            "fields": (
                "status",
                "owner",
                "stakeholders",
                "start_date",
                "target_end_date",
                "actual_end_date",
            ),
        }),
        ("Scope", {
            "fields": ("test_plans",),
        }),
        ("External system keys", {
            "classes": ("collapse",),
            "fields": ("jira_project_key", "external_refs"),
        }),
    )


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


@admin.register(CustomFieldDefinition)
class CustomFieldDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "label", "slug", "target_model", "field_type",
        "required", "order", "is_active", "updated_at",
    )
    list_filter = ("target_model", "field_type", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("slug", "label", "help_text")
    fieldsets = (
        ("Targeting", {"fields": ("target_model", "slug", "label")}),
        ("Type & input", {"fields": ("field_type", "required", "help_text")}),
        ("Display", {"fields": ("order", "is_active")}),
    )


@admin.register(JiraIntegrationConfig)
class JiraIntegrationConfigAdmin(admin.ModelAdmin):
    """Singleton — only one row should exist."""
    list_display = ("backend", "base_url", "default_project_key", "updated_at")

    def has_add_permission(self, request):
        if JiraIntegrationConfig.objects.exists():
            return False
        return super().has_add_permission(request)
