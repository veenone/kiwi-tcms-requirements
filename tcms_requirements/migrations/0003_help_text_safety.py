"""Add help_text to the four safety-classification fields on Requirement.

Metadata-only — no DB schema change. Django still wants a migration so
subsequent `makemigrations` runs don't leave a pending step behind.

Only alters the live Requirement model. The paired HistoricalRequirement
table doesn't expose form fields, so help_text there is cosmetic; we skip
it to keep the migration small. django-simple-history regenerates
historical field metadata at runtime from the live model in any case.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("tcms_requirements", "0002_seed_catalog")]

    operations = [
        migrations.AlterField(
            model_name="requirement",
            name="asil",
            field=models.CharField(
                blank=True,
                choices=[
                    ("QM", "QM"),
                    ("A", "ASIL A"),
                    ("B", "ASIL B"),
                    ("C", "ASIL C"),
                    ("D", "ASIL D"),
                ],
                default="",
                help_text=(
                    "Automotive Safety Integrity Level per ISO 26262. QM = quality "
                    "managed (no safety impact); A → D is increasing safety risk, "
                    "D being the most stringent (e.g. airbag deployment). Leave "
                    "blank for non-automotive or non-safety requirements."
                ),
                max_length=4,
            ),
        ),
        migrations.AlterField(
            model_name="requirement",
            name="sil",
            field=models.CharField(
                blank=True,
                choices=[("1", "SIL 1"), ("2", "SIL 2"), ("3", "SIL 3"), ("4", "SIL 4")],
                default="",
                help_text=(
                    "Safety Integrity Level per IEC 61508 (industrial functional "
                    "safety). 1 = lowest risk reduction, 4 = highest. Used for "
                    "process-industry and machinery safety; leave blank otherwise."
                ),
                max_length=4,
            ),
        ),
        migrations.AlterField(
            model_name="requirement",
            name="iec62304_class",
            field=models.CharField(
                blank=True,
                choices=[
                    ("A", "Class A (no injury or damage to health possible)"),
                    ("B", "Class B (non-serious injury possible)"),
                    ("C", "Class C (death or serious injury possible)"),
                ],
                default="",
                help_text=(
                    "Medical-device software safety class per IEC 62304. "
                    "A = no injury possible, B = non-serious injury possible, "
                    "C = death or serious injury possible. Leave blank for "
                    "non-medical software."
                ),
                max_length=4,
            ),
        ),
        migrations.AlterField(
            model_name="requirement",
            name="dal",
            field=models.CharField(
                blank=True,
                choices=[
                    ("A", "DAL A (catastrophic)"),
                    ("B", "DAL B (hazardous)"),
                    ("C", "DAL C (major)"),
                    ("D", "DAL D (minor)"),
                    ("E", "DAL E (no effect)"),
                ],
                default="",
                help_text=(
                    "Design Assurance Level per DO-178C (aviation software). "
                    "A = catastrophic failure condition, E = no effect on safety. "
                    "Leave blank for non-aviation software."
                ),
                max_length=4,
            ),
        ),
    ]
