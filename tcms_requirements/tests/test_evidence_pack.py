"""v0.4.0 evidence pack — zip bundle composition.

Run via:

    manage.py test tcms_requirements.tests.test_evidence_pack --settings=tcms.settings.test
"""
import io
import zipfile

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from tcms.management.models import Classification, Product

from tcms_requirements.models import (
    Project,
    ProjectBaseline,
    Requirement,
    RequirementLevel,
    RequirementSignature,
)


class _PackSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.classification = Classification.objects.create(name="PackTests")
        cls.product = Product.objects.create(
            name="Pack Product", classification=cls.classification,
        )
        cls.user = get_user_model().objects.create_user(
            username="pack-user", email="pack@example.com", password="pw",
            is_superuser=True, is_staff=True,
        )
        cls.level = RequirementLevel.objects.create(
            code="SYS", name="System", order=1,
        )
        cls.project = Project.objects.create(
            product=cls.product, name="Pack Project", code="PACK",
        )
        cls.req = Requirement.objects.create(
            product=cls.product, project=cls.project, level=cls.level,
            identifier="REQ-1", title="Title", status="approved",
            priority="medium", created_by=cls.user,
        )


class ZipContainsAllExpectedFilesTest(_PackSetup):
    def test_should_produce_zip_containing_all_expected_files(self):
        client = Client()
        client.force_login(self.user)

        response = client.get(
            reverse("requirement-project-evidence-pack", args=[self.project.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")

        zf = zipfile.ZipFile(io.BytesIO(response.content))
        names = set(zf.namelist())
        for expected in {
            "metadata.json",
            "requirements.docx",
            "requirements.pdf",
            "requirements.csv",
            "requirements-jira.csv",
            "requirements.json",
            "dashboard-snapshot.docx",
            "dashboard-snapshot.pdf",
            "signatures.csv",
        }:
            self.assertIn(expected, names, f"{expected} missing from evidence pack")


class ZipIncludesSignaturesAndBaselineTest(_PackSetup):
    def test_should_include_signatures_csv_when_signatures_exist(self):
        sig = RequirementSignature.objects.create(
            requirement=self.req,
            signed_by=self.user,
            signature_hash=RequirementSignature.compute_hash(
                self.req, self.user.pk, timezone.now(),
            ),
            comment="Audit attestation",
        )
        ProjectBaseline.freeze(self.project, "v1.0", created_by=self.user)

        client = Client()
        client.force_login(self.user)

        response = client.get(
            reverse("requirement-project-evidence-pack", args=[self.project.pk])
        )
        zf = zipfile.ZipFile(io.BytesIO(response.content))
        names = set(zf.namelist())

        # signatures.csv contains the signature row.
        sig_csv = zf.read("signatures.csv").decode("utf-8")
        self.assertIn("REQ-1", sig_csv)
        self.assertIn(sig.signature_hash, sig_csv)
        self.assertIn("Audit attestation", sig_csv)

        # latest baseline DOCX/PDF appear in the zip.
        baseline_files = [n for n in names if n.startswith("baseline-v1.0")]
        self.assertEqual(
            sorted(baseline_files),
            ["baseline-v1.0.docx", "baseline-v1.0.pdf"],
        )
