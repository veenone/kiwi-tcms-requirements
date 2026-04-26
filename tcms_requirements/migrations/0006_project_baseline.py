"""v0.4.0: Project-scoped baselines (audit replay).

Adds three additive tables. Mirrors the existing RequirementBaseline (product-
scoped, v0.2) at Project granularity so an auditor can ask "show me the spec
for release X of programme Y" and get a frozen, immutable answer.

Depends on 0004_project_management_fields (the last v0.3 migration). If a
deployment also has the v0.3.x in-flight 0005_custom_field_definitions
migration applied, Django will surface a fork via `makemigrations --merge`.
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tcms_requirements", "0004_project_management_fields"),
        # Kiwi squashed management/0001+0002 into 0003_squashed.
        ("management", "0003_squashed"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectBaseline",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="baselines",
                        to="tcms_requirements.project",
                    ),
                ),
                (
                    "version",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional Kiwi Version this baseline corresponds to.",
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="project_baselines",
                        to="management.version",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="created_project_baselines",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "unique_together": {("project", "name")},
            },
        ),
        migrations.CreateModel(
            name="ProjectBaselineRequirementSnapshot",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("identifier", models.CharField(max_length=64)),
                ("title", models.CharField(max_length=255)),
                ("status", models.CharField(max_length=24)),
                ("priority", models.CharField(blank=True, default="", max_length=16)),
                ("level_code", models.CharField(blank=True, default="", max_length=48)),
                ("asil", models.CharField(blank=True, default="", max_length=4)),
                ("sil", models.CharField(blank=True, default="", max_length=4)),
                ("iec62304_class", models.CharField(blank=True, default="", max_length=4)),
                ("dal", models.CharField(blank=True, default="", max_length=4)),
                (
                    "payload",
                    models.JSONField(
                        default=dict,
                        help_text="Full-fidelity field dump at snapshot time.",
                    ),
                ),
                (
                    "baseline",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="requirement_snapshots",
                        to="tcms_requirements.projectbaseline",
                    ),
                ),
                (
                    "requirement",
                    models.ForeignKey(
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="project_baseline_snapshots",
                        to="tcms_requirements.requirement",
                    ),
                ),
            ],
            options={
                "ordering": ["identifier"],
                "unique_together": {("baseline", "identifier")},
            },
        ),
        migrations.CreateModel(
            name="ProjectBaselineLinkSnapshot",
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
                        on_delete=models.deletion.CASCADE,
                        related_name="link_snapshots",
                        to="tcms_requirements.projectbaseline",
                    ),
                ),
            ],
            options={
                "ordering": ["requirement_identifier", "case_id"],
            },
        ),
    ]
