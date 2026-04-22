"""Forms for Requirement CRUD + CSV import + link management.

Status-transition rules are enforced via state_machine.validate_transition
so both the web view and any programmatic save share the same logic.
"""
from django import forms

from tcms_requirements.models import (
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


class RequirementForm(forms.ModelForm):
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
