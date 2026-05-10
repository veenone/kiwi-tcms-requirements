"""v0.4.0 RequirementSignature — record, immutability, hash detection.

Run via:

    manage.py test tcms_requirements.tests.test_signatures --settings=tcms.settings.test
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from tcms.management.models import Classification, Product

from tcms_requirements.models import (
    Project,
    Requirement,
    RequirementLevel,
    RequirementSignature,
)


class _SignSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.classification = Classification.objects.create(name="SignTests")
        cls.product = Product.objects.create(
            name="Sign Product", classification=cls.classification,
        )
        cls.user = get_user_model().objects.create_user(
            username="signer", email="signer@example.com", password="pw",
        )
        cls.user.user_permissions.add(
            Permission.objects.get(codename="approve_requirement"),
        )
        cls.user.user_permissions.add(
            Permission.objects.get(codename="view_requirement"),
        )
        cls.level = RequirementLevel.objects.create(
            code="SYS", name="System", order=1,
        )
        cls.project = Project.objects.create(
            product=cls.product, name="Sign Project", code="SP",
        )
        cls.requirement = Requirement.objects.create(
            product=cls.product, project=cls.project, level=cls.level,
            identifier="REQ-100", title="Original title", status="approved",
            description="Original description", rationale="Because audit.",
            created_by=cls.user,
        )


class RecordSignatureTest(_SignSetup):
    def test_should_record_signature_with_tamper_evident_hash(self):
        client = Client()
        client.force_login(self.user)

        response = client.post(
            reverse("requirement-sign", args=[self.requirement.pk]),
            data={"comment": "Reviewed at audit meeting"},
        )

        self.assertEqual(response.status_code, 302)
        sig = RequirementSignature.objects.get(requirement=self.requirement)
        self.assertEqual(sig.signed_by_id, self.user.pk)
        self.assertEqual(len(sig.signature_hash), 64)  # SHA-256 hex digest length
        self.assertEqual(
            sig.signature_hash,
            RequirementSignature.compute_hash(
                self.requirement, self.user.pk, sig.signed_at,
            ),
        )


class SignaturePersistsAfterEditTest(_SignSetup):
    def test_should_preserve_existing_signature_when_requirement_edited(self):
        sig = RequirementSignature.objects.create(
            requirement=self.requirement,
            signed_by=self.user,
            signature_hash=RequirementSignature.compute_hash(
                self.requirement, self.user.pk, timezone.now(),
            ),
            comment="initial",
        )
        original_hash = sig.signature_hash

        # Edit the source requirement after the signature was recorded.
        self.requirement.title = "Edited title"
        self.requirement.save()

        sig.refresh_from_db()
        self.assertEqual(sig.signature_hash, original_hash)
        # Recomputing the hash against the current row produces a *different*
        # digest — auditors can detect drift this way.
        new_hash = RequirementSignature.compute_hash(
            self.requirement, self.user.pk, sig.signed_at,
        )
        self.assertNotEqual(sig.signature_hash, new_hash)


class SignWithoutPermissionTest(_SignSetup):
    def test_should_reject_sign_when_user_lacks_approve_permission(self):
        unprivileged = get_user_model().objects.create_user(
            username="readonly", email="ro@example.com", password="pw",
        )
        unprivileged.user_permissions.add(
            Permission.objects.get(codename="view_requirement"),
        )
        client = Client()
        client.force_login(unprivileged)

        response = client.post(
            reverse("requirement-sign", args=[self.requirement.pk]),
            data={"comment": ""},
        )

        # PermissionRequiredMixin returns 403 (or redirects depending on config).
        self.assertIn(response.status_code, (302, 403))
        self.assertEqual(
            RequirementSignature.objects.filter(requirement=self.requirement).count(),
            0,
        )
