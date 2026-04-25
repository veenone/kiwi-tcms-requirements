"""Data model for kiwitcms-requirements.

Entity map:

    Product (Kiwi core)
       │
    Project ── Feature (optional parent_feature self-FK)
                  │
             Requirement ── parent_requirement (self-FK decomposition)
                  │           superseded_by (self-FK, ISO 9001)
                  │
       RequirementTestCaseLink ── TestCase (Kiwi core)

Plus: RequirementCategory, RequirementSource, RequirementLevel (configurable
per standard), RequirementBaseline (+ snapshot tables, immutable at creation).

Every mutating model carries HistoricalRecords so the audit feed can reconstruct
who changed what and when — ASPICE SUP.10 and ISO 9001 §7.5 both require this.
"""
from django.conf import settings
from django.db import models
from django.urls import reverse
from simple_history.models import HistoricalRecords


class RequirementCategory(models.Model):
    """Taxonomy dimension: what *kind* of requirement is this.

    Functional / non-functional / safety / security / performance / UI /
    regulatory / … — seeded from data migration, admin-editable.
    """
    name = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True, default="")
    color = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text="Optional hex colour for UI badges (e.g. #ec7a08).",
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Requirement categories"

    def __str__(self):
        return self.name


class RequirementSource(models.Model):
    """Named source document a requirement was lifted from.

    Source *type* constrains the value; `reference` holds a document URL or
    path, and `version` lets the same source survive revisions.
    """
    SOURCE_TYPE_CHOICES = [
        ("customer_doc", "Customer document"),
        ("tech_spec", "Technical specification"),
        ("srs", "Software Requirements Specification"),
        ("system_spec", "System specification"),
        ("software_spec", "Software specification"),
        ("regulation", "Regulatory document"),
        ("standard", "Industry standard"),
        ("internal", "Internal design note"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=128)
    source_type = models.CharField(
        max_length=32,
        choices=SOURCE_TYPE_CHOICES,
        default="other",
        db_index=True,
    )
    reference = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="URL or path to the source document.",
    )
    version = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        ordering = ["source_type", "name"]
        unique_together = [("name", "version")]

    def __str__(self):
        if self.version:
            return f"{self.name} ({self.version})"
        return self.name


class RequirementLevel(models.Model):
    """Configurable level in the requirement decomposition hierarchy.

    ASPICE installs get stakeholder → system → software → component → unit.
    ISO 9001 installs get customer_requirement → product_requirement →
    process_requirement → quality_objective. The active profile is applied
    by a data migration; admin can edit/add rows at any time.
    """
    code = models.SlugField(
        max_length=48,
        unique=True,
        help_text="Stable identifier (e.g. 'system', 'customer_requirement').",
    )
    name = models.CharField(max_length=96)
    order = models.PositiveIntegerField(
        default=100,
        help_text=(
            "Rank; lower number = higher in the decomposition hierarchy. "
            "Used to sort level tiles and enforce parent/child ordering."
        ),
    )
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["order", "code"]

    def __str__(self):
        return self.name


class Project(models.Model):
    """Release line / programme within a Product.

    Example: product "Infotainment ECU" → project "Platform 2026" with its
    own requirement set. FK back to Kiwi's `tcms.management.Product`.

    Since v0.3.0 the Project carries enough programme-record data to
    serve as a lightweight PM layer: status workflow, owner/stakeholder
    assignment, date milestones, M2M link to Kiwi's `TestPlan`
    (defines the set of plans in scope), and cross-tool keys.
    """

    STATUS_CHOICES = [
        ("planning", "Planning"),
        ("active", "Active"),
        ("on_hold", "On hold"),
        ("closed", "Closed"),
        ("cancelled", "Cancelled"),
    ]

    product = models.ForeignKey(
        "management.Product",
        on_delete=models.CASCADE,
        related_name="requirement_projects",
    )
    name = models.CharField(max_length=128)
    code = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Short identifier unique within the product (e.g. 'PLAT26').",
    )
    description = models.TextField(blank=True, default="")

    # ── programme record ─────────────────────────────────────────────
    status = models.CharField(
        max_length=24,
        choices=STATUS_CHOICES,
        default="active",
        db_index=True,
        help_text="Programme lifecycle state. Drives list filters and dashboard priority.",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_requirement_projects",
        help_text="Single accountable stakeholder.",
    )
    stakeholders = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="stakeholder_requirement_projects",
        blank=True,
        help_text="CC list for notifications and reports.",
    )
    start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Target or actual programme kickoff.",
    )
    target_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Planned completion date; used in timeline KPIs.",
    )
    actual_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Populated when the programme closes.",
    )

    # ── scope (link to Kiwi's own test-scope primitive) ──────────────
    test_plans = models.ManyToManyField(
        "testplans.TestPlan",
        related_name="requirement_projects",
        blank=True,
        help_text="Test plans in scope for this project. Drives coverage-gap detection.",
    )

    # ── external-system keys ─────────────────────────────────────────
    jira_project_key = models.CharField(
        max_length=32,
        blank=True,
        default="",
        db_index=True,
        help_text="JIRA project key (e.g. 'PROJ') for cross-tool mapping.",
    )
    external_refs = models.JSONField(
        default=dict,
        blank=True,
        help_text="Open-ended map for other ALM / PM tool IDs (Polarion, Azure DevOps, …).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["product__name", "name"]
        unique_together = [("product", "name"), ("product", "code")]

    def __str__(self):
        return f"{self.product.name} / {self.name}"

    @property
    def is_terminal(self) -> bool:
        return self.status in {"closed", "cancelled"}

    def get_absolute_url(self):
        from django.urls import reverse  # noqa: WPS433 — already imported, keeping block-local
        return reverse("requirement-project-get", args=[self.pk])


class CustomFieldDefinition(models.Model):
    """Admin-managed extra fields, rendered dynamically on a target form.

    Values are stored in the target entity's existing `external_refs`
    JSON column keyed by `slug`, so adding or removing a definition does
    not require a schema migration.

    Example: an admin defines `slug="request_id"`, `label="Request ID"`,
    `field_type="text"`, `target_model="project"`. From then on the
    Project create/edit form renders an extra "Request ID" text field
    and persists it under `project.external_refs["request_id"]`.
    """

    TARGET_CHOICES = [
        ("project", "Project"),
        ("requirement", "Requirement"),
    ]

    FIELD_TYPE_CHOICES = [
        ("text", "Single-line text"),
        ("textarea", "Multi-line text"),
        ("url", "URL"),
        ("int", "Integer"),
        ("date", "Date"),
    ]

    target_model = models.CharField(
        max_length=24,
        choices=TARGET_CHOICES,
        db_index=True,
        help_text="Which entity's create/edit form this field appears on.",
    )
    slug = models.SlugField(
        max_length=64,
        help_text="Machine name; becomes the key in external_refs JSON.",
    )
    label = models.CharField(max_length=128)
    field_type = models.CharField(
        max_length=16,
        choices=FIELD_TYPE_CHOICES,
        default="text",
    )
    help_text = models.CharField(max_length=255, blank=True, default="")
    required = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(
        default=100,
        help_text="Lower numbers render first.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["target_model", "order", "slug"]
        unique_together = [("target_model", "slug")]

    def __str__(self):
        return f"{self.get_target_model_display()} :: {self.label} ({self.slug})"


class Feature(models.Model):
    """Nestable feature within a Project (or directly under a Product)."""
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="features",
        null=True,
        blank=True,
    )
    product = models.ForeignKey(
        "management.Product",
        on_delete=models.CASCADE,
        related_name="requirement_features",
        null=True,
        blank=True,
        help_text="Set when the feature isn't scoped to a specific project.",
    )
    parent_feature = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sub_features",
    )
    name = models.CharField(max_length=128)
    code = models.CharField(max_length=32, blank=True, default="")
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        if self.project_id:
            return f"{self.project} :: {self.name}"
        return self.name


class Requirement(models.Model):
    """A single requirement — the core entity the plugin registers.

    Fields are grouped by concern:
        - identity (identifier, title, description, rationale)
        - taxonomy (category, source, level)
        - organisation (product, project, feature)
        - hierarchy (parent_requirement)
        - lifecycle (status, priority, verification_method)
        - safety/criticality (asil/sil/iec62304_class/dal) — all blank-safe
        - document control (doc_id, doc_revision, effective_date, superseded_by)
        - change control (change_reason, verification_exemption_reason)
        - external-system keys (jira_issue_key, external_refs)
        - audit fields (created_by, created_at, updated_at, history)
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("in_review", "In review"),
        ("approved", "Approved"),
        ("implemented", "Implemented"),
        ("verified", "Verified"),
        ("deprecated", "Deprecated"),
        ("superseded", "Superseded"),
    ]
    TERMINAL_STATUSES = {"deprecated", "superseded"}

    PRIORITY_CHOICES = [
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    VERIFICATION_METHOD_CHOICES = [
        ("test", "Test"),
        ("analysis", "Analysis"),
        ("inspection", "Inspection"),
        ("demonstration", "Demonstration"),
        ("exempted", "Exempted (no verification required)"),
    ]

    ASIL_CHOICES = [
        ("QM", "QM"),
        ("A", "ASIL A"),
        ("B", "ASIL B"),
        ("C", "ASIL C"),
        ("D", "ASIL D"),
    ]
    SIL_CHOICES = [("1", "SIL 1"), ("2", "SIL 2"), ("3", "SIL 3"), ("4", "SIL 4")]
    IEC62304_CLASS_CHOICES = [
        ("A", "Class A (no injury or damage to health possible)"),
        ("B", "Class B (non-serious injury possible)"),
        ("C", "Class C (death or serious injury possible)"),
    ]
    DAL_CHOICES = [
        ("A", "DAL A (catastrophic)"),
        ("B", "DAL B (hazardous)"),
        ("C", "DAL C (major)"),
        ("D", "DAL D (minor)"),
        ("E", "DAL E (no effect)"),
    ]

    # ── identity ─────────────────────────────────────────────────────
    identifier = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Stable human ID (e.g. 'SYS-REQ-042'). Round-trips to external tools.",
    )
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, default="")
    rationale = models.TextField(
        blank=True,
        default="",
        help_text="Why this requirement exists — ASPICE and ISO 9001 both value this.",
    )

    # ── taxonomy ─────────────────────────────────────────────────────
    category = models.ForeignKey(
        RequirementCategory,
        on_delete=models.PROTECT,
        related_name="requirements",
        null=True,
        blank=True,
    )
    source = models.ForeignKey(
        RequirementSource,
        on_delete=models.PROTECT,
        related_name="requirements",
        null=True,
        blank=True,
    )
    source_section = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Section or page reference within the source doc (e.g. '§4.2.1').",
    )
    level = models.ForeignKey(
        RequirementLevel,
        on_delete=models.PROTECT,
        related_name="requirements",
        null=True,
        blank=True,
    )

    # ── organisation ─────────────────────────────────────────────────
    product = models.ForeignKey(
        "management.Product",
        on_delete=models.SET_NULL,
        related_name="requirements",
        null=True,
        blank=True,
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        related_name="requirements",
        null=True,
        blank=True,
    )
    feature = models.ForeignKey(
        Feature,
        on_delete=models.SET_NULL,
        related_name="requirements",
        null=True,
        blank=True,
    )

    # ── hierarchy ────────────────────────────────────────────────────
    parent_requirement = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_requirements",
        help_text="Parent in the decomposition tree (system → software → etc.).",
    )

    # ── lifecycle ────────────────────────────────────────────────────
    status = models.CharField(
        max_length=24,
        choices=STATUS_CHOICES,
        default="draft",
        db_index=True,
    )
    priority = models.CharField(
        max_length=16,
        choices=PRIORITY_CHOICES,
        default="medium",
        db_index=True,
    )
    verification_method = models.CharField(
        max_length=16,
        choices=VERIFICATION_METHOD_CHOICES,
        default="test",
    )

    # ── safety / criticality (all blank-safe) ───────────────────────
    asil = models.CharField(
        max_length=4,
        choices=ASIL_CHOICES,
        blank=True,
        default="",
        help_text=(
            "Automotive Safety Integrity Level per ISO 26262. QM = quality "
            "managed (no safety impact); A → D is increasing safety risk, "
            "D being the most stringent (e.g. airbag deployment). Leave "
            "blank for non-automotive or non-safety requirements."
        ),
    )
    sil = models.CharField(
        max_length=4,
        choices=SIL_CHOICES,
        blank=True,
        default="",
        help_text=(
            "Safety Integrity Level per IEC 61508 (industrial functional "
            "safety). 1 = lowest risk reduction, 4 = highest. Used for "
            "process-industry and machinery safety; leave blank otherwise."
        ),
    )
    iec62304_class = models.CharField(
        max_length=4,
        choices=IEC62304_CLASS_CHOICES,
        blank=True,
        default="",
        help_text=(
            "Medical-device software safety class per IEC 62304. "
            "A = no injury possible, B = non-serious injury possible, "
            "C = death or serious injury possible. Leave blank for "
            "non-medical software."
        ),
    )
    dal = models.CharField(
        max_length=4,
        choices=DAL_CHOICES,
        blank=True,
        default="",
        help_text=(
            "Design Assurance Level per DO-178C (aviation software). "
            "A = catastrophic failure condition, E = no effect on safety. "
            "Leave blank for non-aviation software."
        ),
    )

    # ── document control (ISO 9001 §7.5) ─────────────────────────────
    doc_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="External controlled-document ID (e.g. 'QMS-SRS-042').",
    )
    doc_revision = models.CharField(max_length=16, blank=True, default="")
    effective_date = models.DateField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supersedes",
        help_text="Set when status=superseded — points at the replacement requirement.",
    )

    # ── change control ───────────────────────────────────────────────
    change_reason = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Required when status transitions to deprecated or superseded. "
            "Feeds ISO 9001 §10 corrective/preventive action evidence."
        ),
    )
    verification_exemption_reason = models.TextField(
        blank=True,
        default="",
        help_text="Required when verification_method=exempted.",
    )

    # ── external system keys ─────────────────────────────────────────
    jira_issue_key = models.CharField(
        max_length=32,
        blank=True,
        default="",
        db_index=True,
        help_text="JIRA issue key (e.g. 'PROJ-123'). Populated on push or round-trip import.",
    )
    external_refs = models.JSONField(
        default=dict,
        blank=True,
        help_text="Open-ended map for other ALM IDs (Polarion, DOORS, Jama, …).",
    )

    # ── audit ────────────────────────────────────────────────────────
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_requirements",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Cases linked via the through model RequirementTestCaseLink.
    cases = models.ManyToManyField(
        "testcases.TestCase",
        through="RequirementTestCaseLink",
        related_name="requirements_linked",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["identifier"]
        indexes = [
            models.Index(fields=["status", "priority"], name="tcmsreq_status_prio_idx"),
            models.Index(fields=["product", "status"], name="tcmsreq_product_status_idx"),
        ]

    def __str__(self):
        return f"{self.identifier}: {self.title}"

    def get_absolute_url(self):
        return reverse("requirement-get", args=[self.pk])

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES

    @property
    def needs_change_reason(self) -> bool:
        """True when the form MUST require change_reason (enforced by state_machine)."""
        return self.status in self.TERMINAL_STATUSES

    @property
    def needs_exemption_reason(self) -> bool:
        return self.verification_method == "exempted"


class RequirementTestCaseLink(models.Model):
    """Typed many-to-many between Requirement and TestCase.

    `suspect` flips to True when the linked requirement is edited after the
    link was created — reviewers clear the flag when they've re-confirmed
    the case still verifies the new requirement text. Follows the standard
    DOORS/Polarion "suspect link" pattern.
    """
    LINK_TYPE_CHOICES = [
        ("verifies", "Verifies"),
        ("validates", "Validates"),
        ("derives_from", "Derives from"),
        ("related", "Related"),
    ]

    requirement = models.ForeignKey(
        Requirement,
        on_delete=models.CASCADE,
        related_name="case_links",
    )
    case = models.ForeignKey(
        "testcases.TestCase",
        on_delete=models.CASCADE,
        related_name="requirement_links",
    )
    link_type = models.CharField(
        max_length=16,
        choices=LINK_TYPE_CHOICES,
        default="verifies",
        db_index=True,
    )
    coverage_notes = models.TextField(blank=True, default="")
    suspect = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Set true when the linked requirement is edited; cleared by reviewer.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_requirement_links",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("requirement", "case", "link_type")]
        indexes = [
            models.Index(fields=["requirement", "suspect"], name="tcmsreq_link_req_susp_idx"),
        ]

    def __str__(self):
        return f"{self.requirement.identifier} -[{self.link_type}]-> TC-{self.case_id}"


class RequirementBaseline(models.Model):
    """Immutable snapshot of the requirement set (+ links) at a release point.

    Created once, never edited. Used for ASPICE SUP.8 configuration evidence
    and ISO 9001 controlled-document retention.
    """
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, default="")
    product = models.ForeignKey(
        "management.Product",
        on_delete=models.PROTECT,
        related_name="requirement_baselines",
    )
    version = models.ForeignKey(
        "management.Version",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requirement_baselines",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_requirement_baselines",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("product", "name")]

    def __str__(self):
        return f"Baseline {self.name} ({self.product})"


class BaselineRequirementSnapshot(models.Model):
    """One row per Requirement frozen into a Baseline."""
    baseline = models.ForeignKey(
        RequirementBaseline,
        on_delete=models.CASCADE,
        related_name="requirement_snapshots",
    )
    requirement = models.ForeignKey(
        Requirement,
        on_delete=models.SET_NULL,
        null=True,
        related_name="baseline_snapshots",
    )
    # Denormalised copy so the snapshot survives requirement deletion/edits.
    identifier = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=24)
    level_code = models.CharField(max_length=48, blank=True, default="")
    payload = models.JSONField(
        default=dict,
        help_text="Full-fidelity field dump at snapshot time.",
    )

    class Meta:
        ordering = ["identifier"]
        unique_together = [("baseline", "identifier")]


class BaselineLinkSnapshot(models.Model):
    """One row per RequirementTestCaseLink frozen into a Baseline."""
    baseline = models.ForeignKey(
        RequirementBaseline,
        on_delete=models.CASCADE,
        related_name="link_snapshots",
    )
    requirement_identifier = models.CharField(max_length=64)
    case_id = models.IntegerField()
    link_type = models.CharField(max_length=16)
    suspect = models.BooleanField(default=False)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["requirement_identifier", "case_id"]


class JiraIntegrationConfig(models.Model):
    """Singleton config for live JIRA push. Populated in v0.3, unused in v0.1.

    Stored in v0.1 so installs that want to experiment with the REST push
    don't need a fresh migration later. `backend='disabled'` is the safe default.
    """
    BACKEND_CHOICES = [("disabled", "Disabled"), ("jira_cloud", "JIRA Cloud"), ("jira_dc", "JIRA Server / DC")]

    backend = models.CharField(max_length=24, choices=BACKEND_CHOICES, default="disabled")
    base_url = models.URLField(blank=True, default="")
    api_token = models.CharField(max_length=255, blank=True, default="")
    email = models.CharField(max_length=255, blank=True, default="")
    default_project_key = models.CharField(max_length=32, blank=True, default="")
    default_issue_type = models.CharField(max_length=48, blank=True, default="Story")
    status_mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text='Map plugin status → JIRA status, e.g. {"approved": "Done"}.',
    )
    custom_field_mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text="Map our field names → JIRA custom_field IDs (e.g. 'level' → 'customfield_10011').",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "JIRA integration configuration"
        verbose_name_plural = "JIRA integration configuration"

    def __str__(self):
        return f"JiraIntegrationConfig ({self.backend})"

    @property
    def is_enabled(self) -> bool:
        return self.backend != "disabled" and bool(self.base_url) and bool(self.api_token)

