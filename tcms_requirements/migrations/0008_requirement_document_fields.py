"""v0.4.x: add `document_file_name` and `document_title` to Requirement.

Two CharField columns in the taxonomy block so each requirement can record
the source document's file name + formal title alongside source / category /
level. HistoricalRequirement gets the same fields so `simple_history` mirrors
correctly.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tcms_requirements", "0007_requirement_signatures"),
    ]

    operations = [
        migrations.AddField(
            model_name="requirement",
            name="document_file_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="File name of the source document (e.g. 'system-spec_v1.2.pdf').",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="requirement",
            name="document_title",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Formal title of the source document "
                          "(e.g. 'System Requirements Specification — Platform 2026').",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="historicalrequirement",
            name="document_file_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="File name of the source document (e.g. 'system-spec_v1.2.pdf').",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="historicalrequirement",
            name="document_title",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Formal title of the source document "
                          "(e.g. 'System Requirements Specification — Platform 2026').",
                max_length=255,
            ),
        ),
    ]
