"""v0.3.x: admin-managed dynamic custom fields.

Values are stored in the target entity's existing `external_refs` JSON column,
keyed by slug. Adding or removing a definition therefore needs no further
schema migration.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tcms_requirements", "0004_project_management_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomFieldDefinition",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_model", models.CharField(
                    choices=[
                        ("project", "Project"),
                        ("requirement", "Requirement"),
                    ],
                    db_index=True,
                    help_text="Which entity's create/edit form this field appears on.",
                    max_length=24,
                )),
                ("slug", models.SlugField(
                    help_text="Machine name; becomes the key in external_refs JSON.",
                    max_length=64,
                )),
                ("label", models.CharField(max_length=128)),
                ("field_type", models.CharField(
                    choices=[
                        ("text", "Single-line text"),
                        ("textarea", "Multi-line text"),
                        ("url", "URL"),
                        ("int", "Integer"),
                        ("date", "Date"),
                    ],
                    default="text",
                    max_length=16,
                )),
                ("help_text", models.CharField(blank=True, default="", max_length=255)),
                ("required", models.BooleanField(default=False)),
                ("order", models.PositiveSmallIntegerField(
                    default=100,
                    help_text="Lower numbers render first.",
                )),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["target_model", "order", "slug"],
                "unique_together": {("target_model", "slug")},
            },
        ),
    ]
