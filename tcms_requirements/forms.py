"""Forms for Requirement CRUD + CSV import + link management.

Status-transition rules are enforced via state_machine.validate_transition
so both the web view and any programmatic save share the same logic.
"""
from django import forms

from tcms_requirements.models import (
    CustomFieldDefinition,
    Feature,
    Project,
    Requirement,
    RequirementCategory,
    RequirementLevel,
    RequirementSource,
    RequirementTestCaseLink,
)
from tcms_requirements.state_machine import (
    StateTransitionError,
    TransitionContext,
    validate_transition,
)


class CustomFieldsMixin:
    """Add admin-defined dynamic fields to a ModelForm.

    Subclass declares `custom_fields_target` (matches `CustomFieldDefinition.target_model`).
    Field values are persisted into the model's `external_refs` JSONField.
    """

    custom_fields_target: str = ""
    custom_field_prefix: str = "cf_"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.custom_fields_target:
            return
        existing = (self.instance.external_refs or {}) if self.instance.pk else {}
        for definition in self._iter_definitions():
            field_name = self.custom_field_prefix + definition.slug
            self.fields[field_name] = self._build_field(definition, existing.get(definition.slug))

    def custom_field_iter(self):
        for name in self.fields:
            if name.startswith(self.custom_field_prefix):
                yield self[name]

    def save(self, commit=True):
        external_refs = dict(self.instance.external_refs or {})
        for name, value in self.cleaned_data.items():
            if not name.startswith(self.custom_field_prefix):
                continue
            slug = name[len(self.custom_field_prefix):]
            if value in (None, ""):
                external_refs.pop(slug, None)
                continue
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            external_refs[slug] = value
        self.instance.external_refs = external_refs
        return super().save(commit=commit)

    def _iter_definitions(self):
        return CustomFieldDefinition.objects.filter(
            target_model=self.custom_fields_target,
            is_active=True,
        ).order_by("order", "slug")

    @staticmethod
    def _build_field(definition, initial):
        kwargs = {
            "label": definition.label,
            "required": definition.required,
            "help_text": definition.help_text or "",
            "initial": "" if initial is None else initial,
        }
        if definition.field_type == "url":
            return forms.URLField(**kwargs)
        if definition.field_type == "int":
            return forms.IntegerField(**kwargs)
        if definition.field_type == "date":
            return forms.DateField(**kwargs, widget=forms.DateInput(attrs={"type": "date"}))
        if definition.field_type == "textarea":
            return forms.CharField(**kwargs, widget=forms.Textarea(attrs={"rows": 3}))
        return forms.CharField(**kwargs)


class RequirementForm(CustomFieldsMixin, forms.ModelForm):
    custom_fields_target = "requirement"

    """Form for creating and editing a Requirement."""

    class Meta:
        model = Requirement
        fields = [
            # identity
            "identifier", "title", "description", "rationale",
            # taxonomy
            "category", "source", "source_section", "level",
            # organisation
            "product", "project", "feature", "parent_requirement",
            # lifecycle
            "status", "priority", "verification_method",
            "verification_exemption_reason",
            # safety / criticality
            "asil", "sil", "iec62304_class", "dal",
            # document control
            "doc_id", "doc_revision", "effective_date",
            "superseded_by", "change_reason",
            # external keys
            "jira_issue_key",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "rationale": forms.Textarea(attrs={"rows": 3}),
            "change_reason": forms.Textarea(attrs={"rows": 2}),
            "verification_exemption_reason": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active levels by default — operator can override by
        # editing the row in admin.
        self.fields["level"].queryset = RequirementLevel.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        current_status = self.instance.status if self.instance.pk else "draft"
        target_status = cleaned.get("status", "draft")
        ctx = TransitionContext(
            current_status=current_status,
            target_status=target_status,
            change_reason=cleaned.get("change_reason") or "",
            verification_method=cleaned.get("verification_method") or "test",
            verification_exemption_reason=cleaned.get("verification_exemption_reason") or "",
            superseded_by_id=(cleaned.get("superseded_by").pk if cleaned.get("superseded_by") else None),
        )
        try:
            validate_transition(ctx)
        except StateTransitionError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return cleaned


class ProjectForm(CustomFieldsMixin, forms.ModelForm):
    """Form for creating and editing a programme-record Project."""

    custom_fields_target = "project"

    class Meta:
        model = Project
        fields = [
            # identity
            "product", "name", "code", "description",
            # programme record
            "status", "owner", "stakeholders",
            "start_date", "target_end_date", "actual_end_date",
            # scope
            "test_plans",
            # external system keys
            "jira_project_key", "external_refs",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "target_end_date": forms.DateInput(attrs={"type": "date"}),
            "actual_end_date": forms.DateInput(attrs={"type": "date"}),
            "external_refs": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": '{"polarion": "PROJ-X", "ado": "12345"}',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Lazy-import Kiwi's TestPlan so the form module imports cleanly
        # in unit-test contexts where Kiwi isn't on the path.
        from tcms.testplans.models import TestPlan  # noqa: WPS433
        self.fields["test_plans"].queryset = TestPlan.objects.order_by("name")


class CSVImportForm(forms.Form):
    """Upload a CSV or XLSX for dry-run preview + commit."""
    csv_file = forms.FileField(
        label="Requirements file",
        help_text=(
            "CSV (UTF-8) or XLSX with a header row. Required columns: "
            "identifier, title. Optional: description, rationale, level, "
            "category, source, status, priority, product, project, feature, "
            "parent_requirement, verification_method, doc_id, doc_revision, "
            "asil, dal, iec62304_class, effective_date, change_reason, "
            "jira_issue_key, external_refs. Download a template to see the full shape."
        ),
    )
    dry_run = forms.BooleanField(
        required=False,
        initial=True,
        label="Dry run",
        help_text="Validate only — no rows written to the database.",
    )


class LinkCaseForm(forms.Form):
    """Link a TestCase to the current Requirement with a typed relationship.

    The `case_id` is populated by the TestCase browser modal (see
    `link.html` + `static/tcms_requirements/js/link_picker.js`) — the
    user searches by summary/ID and clicks a row. A hidden input carries
    the selected id, so the view-layer contract is still a single int.
    """
    case_id = forms.IntegerField(
        label="Test case",
        min_value=1,
        widget=forms.HiddenInput(),
        help_text="",
    )
    link_type = forms.ChoiceField(
        choices=RequirementTestCaseLink.LINK_TYPE_CHOICES,
        initial="verifies",
    )
    coverage_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class RequirementFilterForm(forms.Form):
    """Filters for the list view. All fields optional."""
    q = forms.CharField(required=False, label="Search")
    status = forms.ChoiceField(
        choices=[("", "— any —")] + list(Requirement.STATUS_CHOICES),
        required=False,
    )
    priority = forms.ChoiceField(
        choices=[("", "— any —")] + list(Requirement.PRIORITY_CHOICES),
        required=False,
    )
    category = forms.ModelChoiceField(
        queryset=RequirementCategory.objects.all(),
        required=False,
        empty_label="— any —",
    )
    level = forms.ModelChoiceField(
        queryset=RequirementLevel.objects.filter(is_active=True),
        required=False,
        empty_label="— any —",
    )
    source = forms.ModelChoiceField(
        queryset=RequirementSource.objects.all(),
        required=False,
        empty_label="— any —",
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.all(),
        required=False,
        empty_label="— any —",
    )
    feature = forms.ModelChoiceField(
        queryset=Feature.objects.all(),
        required=False,
        empty_label="— any —",
    )
