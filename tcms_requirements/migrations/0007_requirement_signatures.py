"""v0.4.0: lightweight electronic signatures on Requirements.

Wires up the `requirements.approve_requirement` permission (seeded since v0.2)
as tamper-evident SHA-256 attestations. NOT a state-machine extension; see
v0.4 plan.
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tcms_requirements", "0006_project_baseline"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RequirementSignature",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("signed_at", models.DateTimeField(auto_now_add=True)),
                ("signature_hash", models.CharField(db_index=True, max_length=64)),
                ("comment", models.TextField(blank=True, default="")),
                (
                    "requirement",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="signatures",
                        to="tcms_requirements.requirement",
                    ),
                ),
                (
                    "signed_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="requirement_signatures",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-signed_at"],
            },
        ),
        migrations.AddIndex(
            model_name="requirementsignature",
            index=models.Index(
                fields=["requirement", "-signed_at"],
                name="tcmsreq_sig_req_idx",
            ),
        ),
    ]
