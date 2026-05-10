"""v0.3.0: extend Project with programme-management fields + TestPlan M2M.

All new columns are nullable or default-empty so existing Project rows
survive the migration unchanged. The TestPlan M2M is additive; existing
querysets that don't care about test_plans keep working.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tcms_requirements", "0003_help_text_safety"),
        # Kiwi squashed testplans/0001_initial; depend on the earliest extant node.
        ("testplans", "0005_squashed"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="status",
            field=models.CharField(
                choices=[
                    ("planning", "Planning"),
                    ("active", "Active"),
                    ("on_hold", "On hold"),
                    ("closed", "Closed"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="active",
                help_text="Programme lifecycle state. Drives list filters and dashboard priority.",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                help_text="Single accountable stakeholder.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="owned_requirement_projects",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="stakeholders",
            field=models.ManyToManyField(
                blank=True,
                help_text="CC list for notifications and reports.",
                related_name="stakeholder_requirement_projects",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="start_date",
            field=models.DateField(
                blank=True,
                help_text="Target or actual programme kickoff.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="target_end_date",
            field=models.DateField(
                blank=True,
                help_text="Planned completion date; used in timeline KPIs.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="actual_end_date",
            field=models.DateField(
                blank=True,
                help_text="Populated when the programme closes.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="test_plans",
            field=models.ManyToManyField(
                blank=True,
                help_text="Test plans in scope for this project. Drives coverage-gap detection.",
                related_name="requirement_projects",
                to="testplans.testplan",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="jira_project_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="JIRA project key (e.g. 'PROJ') for cross-tool mapping.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="external_refs",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Open-ended map for other ALM / PM tool IDs (Polarion, Azure DevOps, …).",
            ),
        ),
        # Mirror the new programme-record fields onto the historical table
        # so django-simple-history doesn't drift out of sync.
        migrations.AddField(
            model_name="historicalproject",
            name="status",
            field=models.CharField(
                db_index=True,
                default="active",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="historicalproject",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="historicalproject",
            name="start_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalproject",
            name="target_end_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalproject",
            name="actual_end_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalproject",
            name="jira_project_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="historicalproject",
            name="external_refs",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
