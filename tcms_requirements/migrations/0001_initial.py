"""Initial schema for kiwitcms-requirements.

Covers every model in tcms_requirements.models. HistoricalRecords on
Requirement / RequirementTestCaseLink / Project / Feature produce
HistoricalRequirement / HistoricalRequirementTestCaseLink / HistoricalProject /
HistoricalFeature automatically via simple_history — they're declared here
so the migration is fully self-contained and doesn't rely on running
`./manage.py makemigrations` at install time.
"""
import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        # Kiwi's `management` app has a squashed 0003; `0001_initial` was
        # squashed away, so we pin to the squash that actually exists.
        ("management", "0003_squashed"),
        ("testcases", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RequirementCategory",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("color", models.CharField(blank=True, default="", max_length=16)),
            ],
            options={"ordering": ["name"], "verbose_name_plural": "Requirement categories"},
        ),
        migrations.CreateModel(
            name="RequirementSource",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("customer_doc", "Customer document"),
                            ("tech_spec", "Technical specification"),
                            ("srs", "Software Requirements Specification"),
                            ("system_spec", "System specification"),
                            ("software_spec", "Software specification"),
                            ("regulation", "Regulatory document"),
                            ("standard", "Industry standard"),
                            ("internal", "Internal design note"),
                            ("other", "Other"),
                        ],
                        db_index=True,
                        default="other",
                        max_length=32,
                    ),
                ),
                ("reference", models.CharField(blank=True, default="", max_length=512)),
                ("version", models.CharField(blank=True, default="", max_length=32)),
            ],
            options={"ordering": ["source_type", "name"], "unique_together": {("name", "version")}},
        ),
        migrations.CreateModel(
            name="RequirementLevel",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=48, unique=True)),
                ("name", models.CharField(max_length=96)),
                ("order", models.PositiveIntegerField(default=100)),
                ("description", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(db_index=True, default=True)),
            ],
            options={"ordering": ["order", "code"]},
        ),
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("code", models.CharField(blank=True, default="", max_length=32)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="requirement_projects",
                        to="management.product",
                    ),
                ),
            ],
            options={
                "ordering": ["product__name", "name"],
                "unique_together": {("product", "name"), ("product", "code")},
            },
        ),
        migrations.CreateModel(
            name="Feature",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("code", models.CharField(blank=True, default="", max_length=32)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "parent_feature",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sub_features",
                        to="tcms_requirements.feature",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="requirement_features",
                        to="management.product",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="features",
                        to="tcms_requirements.project",
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Requirement",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("identifier", models.CharField(db_index=True, max_length=64, unique=True)),
                ("title", models.CharField(db_index=True, max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("rationale", models.TextField(blank=True, default="")),
                ("source_section", models.CharField(blank=True, default="", max_length=128)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("in_review", "In review"),
                            ("approved", "Approved"),
                            ("implemented", "Implemented"),
                            ("verified", "Verified"),
                            ("deprecated", "Deprecated"),
                            ("superseded", "Superseded"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=24,
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        choices=[
                            ("critical", "Critical"),
                            ("high", "High"),
                            ("medium", "Medium"),
                            ("low", "Low"),
                        ],
                        db_index=True,
                        default="medium",
                        max_length=16,
                    ),
                ),
                (
                    "verification_method",
                    models.CharField(
                        choices=[
                            ("test", "Test"),
                            ("analysis", "Analysis"),
                            ("inspection", "Inspection"),
                            ("demonstration", "Demonstration"),
                            ("exempted", "Exempted (no verification required)"),
                        ],
                        default="test",
                        max_length=16,
                    ),
                ),
                (
                    "asil",
                    models.CharField(
                        blank=True,
                        choices=[("QM", "QM"), ("A", "ASIL A"), ("B", "ASIL B"), ("C", "ASIL C"), ("D", "ASIL D")],
                        default="",
                        max_length=4,
                    ),
                ),
                (
                    "sil",
                    models.CharField(
                        blank=True,
                        choices=[("1", "SIL 1"), ("2", "SIL 2"), ("3", "SIL 3"), ("4", "SIL 4")],
                        default="",
                        max_length=4,
                    ),
                ),
                (
                    "iec62304_class",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("A", "Class A (no injury or damage to health possible)"),
                            ("B", "Class B (non-serious injury possible)"),
                            ("C", "Class C (death or serious injury possible)"),
                        ],
                        default="",
                        max_length=4,
                    ),
                ),
                (
                    "dal",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("A", "DAL A (catastrophic)"),
                            ("B", "DAL B (hazardous)"),
                            ("C", "DAL C (major)"),
                            ("D", "DAL D (minor)"),
                            ("E", "DAL E (no effect)"),
                        ],
                        default="",
                        max_length=4,
                    ),
                ),
                ("doc_id", models.CharField(blank=True, default="", max_length=64)),
                ("doc_revision", models.CharField(blank=True, default="", max_length=16)),
                ("effective_date", models.DateField(blank=True, null=True)),
                ("change_reason", models.TextField(blank=True, default="")),
                ("verification_exemption_reason", models.TextField(blank=True, default="")),
                ("jira_issue_key", models.CharField(blank=True, db_index=True, default="", max_length=32)),
                ("external_refs", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="requirements",
                        to="tcms_requirements.requirementcategory",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_requirements",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "feature",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="requirements",
                        to="tcms_requirements.feature",
                    ),
                ),
                (
                    "level",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="requirements",
                        to="tcms_requirements.requirementlevel",
                    ),
                ),
                (
                    "parent_requirement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="child_requirements",
                        to="tcms_requirements.requirement",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="requirements",
                        to="management.product",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="requirements",
                        to="tcms_requirements.project",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="requirements",
                        to="tcms_requirements.requirementsource",
                    ),
                ),
                (
                    "superseded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="supersedes",
                        to="tcms_requirements.requirement",
                    ),
                ),
            ],
            options={"ordering": ["identifier"]},
        ),
        migrations.AddIndex(
            model_name="requirement",
            index=models.Index(fields=["status", "priority"], name="tcmsreq_status_prio_idx"),
        ),
        migrations.AddIndex(
            model_name="requirement",
            index=models.Index(fields=["product", "status"], name="tcmsreq_product_status_idx"),
        ),
        migrations.CreateModel(
            name="RequirementTestCaseLink",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "link_type",
                    models.CharField(
                        choices=[
                            ("verifies", "Verifies"),
                            ("validates", "Validates"),
                            ("derives_from", "Derives from"),
                            ("related", "Related"),
                        ],
                        db_index=True,
                        default="verifies",
                        max_length=16,
                    ),
                ),
                ("coverage_notes", models.TextField(blank=True, default="")),
                ("suspect", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="requirement_links",
                        to="testcases.testcase",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_requirement_links",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "requirement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="case_links",
                        to="tcms_requirements.requirement",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"], "unique_together": {("requirement", "case", "link_type")}},
        ),
        migrations.AddIndex(
            model_name="requirementtestcaselink",
            index=models.Index(fields=["requirement", "suspect"], name="tcmsreq_link_req_susp_idx"),
        ),
        migrations.AddField(
            model_name="requirement",
            name="cases",
            field=models.ManyToManyField(
                related_name="requirements_linked",
                through="tcms_requirements.RequirementTestCaseLink",
                to="testcases.testcase",
            ),
        ),
        migrations.CreateModel(
            name="RequirementBaseline",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_requirement_baselines",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="requirement_baselines",
                        to="management.product",
                    ),
                ),
                (
                    "version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="requirement_baselines",
                        to="management.version",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"], "unique_together": {("product", "name")}},
        ),
        migrations.CreateModel(
            name="BaselineRequirementSnapshot",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("identifier", models.CharField(max_length=64)),
                ("title", models.CharField(max_length=255)),
                ("status", models.CharField(max_length=24)),
                ("level_code", models.CharField(blank=True, default="", max_length=48)),
                ("payload", models.JSONField(default=dict)),
                (
                    "baseline",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="requirement_snapshots",
                        to="tcms_requirements.requirementbaseline",
                    ),
                ),
                (
                    "requirement",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="baseline_snapshots",
                        to="tcms_requirements.requirement",
                    ),
                ),
            ],
            options={"ordering": ["identifier"], "unique_together": {("baseline", "identifier")}},
        ),
        migrations.CreateModel(
            name="BaselineLinkSnapshot",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("requirement_identifier", models.CharField(max_length=64)),
                ("case_id", models.IntegerField()),
                ("link_type", models.CharField(max_length=16)),
                ("suspect", models.BooleanField(default=False)),
                ("payload", models.JSONField(default=dict)),
                (
                    "baseline",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="link_snapshots",
                        to="tcms_requirements.requirementbaseline",
                    ),
                ),
            ],
            options={"ordering": ["requirement_identifier", "case_id"]},
        ),
        migrations.CreateModel(
            name="JiraIntegrationConfig",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "backend",
                    models.CharField(
                        choices=[
                            ("disabled", "Disabled"),
                            ("jira_cloud", "JIRA Cloud"),
                            ("jira_dc", "JIRA Server / DC"),
                        ],
                        default="disabled",
                        max_length=24,
                    ),
                ),
                ("base_url", models.URLField(blank=True, default="")),
                ("api_token", models.CharField(blank=True, default="", max_length=255)),
                ("email", models.CharField(blank=True, default="", max_length=255)),
                ("default_project_key", models.CharField(blank=True, default="", max_length=32)),
                ("default_issue_type", models.CharField(blank=True, default="Story", max_length=48)),
                ("status_mapping", models.JSONField(blank=True, default=dict)),
                ("custom_field_mapping", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "JIRA integration configuration",
                "verbose_name_plural": "JIRA integration configuration",
            },
        ),
        # ── Historical paired models (django-simple-history) ──────────────
        migrations.CreateModel(
            name="HistoricalProject",
            fields=[
                ("id", models.IntegerField(auto_created=True, blank=True, db_index=True, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("code", models.CharField(blank=True, default="", max_length=32)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(blank=True, editable=False)),
                ("updated_at", models.DateTimeField(blank=True, editable=False)),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")], max_length=1
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="management.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical project",
                "verbose_name_plural": "historical projects",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="HistoricalFeature",
            fields=[
                ("id", models.IntegerField(auto_created=True, blank=True, db_index=True, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("code", models.CharField(blank=True, default="", max_length=32)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(blank=True, editable=False)),
                ("updated_at", models.DateTimeField(blank=True, editable=False)),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")], max_length=1
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "parent_feature",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="tcms_requirements.feature",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="management.product",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="tcms_requirements.project",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical feature",
                "verbose_name_plural": "historical features",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="HistoricalRequirement",
            fields=[
                ("id", models.IntegerField(auto_created=True, blank=True, db_index=True, verbose_name="ID")),
                ("identifier", models.CharField(db_index=True, max_length=64)),
                ("title", models.CharField(db_index=True, max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("rationale", models.TextField(blank=True, default="")),
                ("source_section", models.CharField(blank=True, default="", max_length=128)),
                ("status", models.CharField(db_index=True, default="draft", max_length=24)),
                ("priority", models.CharField(db_index=True, default="medium", max_length=16)),
                ("verification_method", models.CharField(default="test", max_length=16)),
                ("asil", models.CharField(blank=True, default="", max_length=4)),
                ("sil", models.CharField(blank=True, default="", max_length=4)),
                ("iec62304_class", models.CharField(blank=True, default="", max_length=4)),
                ("dal", models.CharField(blank=True, default="", max_length=4)),
                ("doc_id", models.CharField(blank=True, default="", max_length=64)),
                ("doc_revision", models.CharField(blank=True, default="", max_length=16)),
                ("effective_date", models.DateField(blank=True, null=True)),
                ("change_reason", models.TextField(blank=True, default="")),
                ("verification_exemption_reason", models.TextField(blank=True, default="")),
                ("jira_issue_key", models.CharField(blank=True, db_index=True, default="", max_length=32)),
                ("external_refs", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(blank=True, db_index=True, editable=False)),
                ("updated_at", models.DateTimeField(blank=True, editable=False)),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")], max_length=1
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="tcms_requirements.requirementcategory",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "feature",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="tcms_requirements.feature",
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "level",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="tcms_requirements.requirementlevel",
                    ),
                ),
                (
                    "parent_requirement",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="tcms_requirements.requirement",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="management.product",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="tcms_requirements.project",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="tcms_requirements.requirementsource",
                    ),
                ),
                (
                    "superseded_by",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="tcms_requirements.requirement",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical requirement",
                "verbose_name_plural": "historical requirements",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="HistoricalRequirementTestCaseLink",
            fields=[
                ("id", models.IntegerField(auto_created=True, blank=True, db_index=True, verbose_name="ID")),
                ("link_type", models.CharField(db_index=True, default="verifies", max_length=16)),
                ("coverage_notes", models.TextField(blank=True, default="")),
                ("suspect", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(blank=True, editable=False)),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")], max_length=1
                    ),
                ),
                (
                    "case",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="testcases.testcase",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "requirement",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="tcms_requirements.requirement",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical requirement test case link",
                "verbose_name_plural": "historical requirement test case links",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
