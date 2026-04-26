"""v0.4.0 ProjectBaseline — freeze, immutability, diff.

Run via:

    manage.py test tcms_requirements.tests.test_project_baseline --settings=tcms.settings.test
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from tcms.management.models import Classification, Product

from tcms_requirements.models import (
    Project,
    ProjectBaseline,
    Requirement,
    RequirementLevel,
)
from tcms_requirements.views import _diff_baselines


class _BaselineSetup(TestCase):
    """Shared fixtures: one project with three requirements at known state."""

    @classmethod
    def setUpTestData(cls):
        cls.classification = Classification.objects.create(name="BaselineTests")
        cls.product = Product.objects.create(
            name="Baseline Product", classification=cls.classification,
        )
        cls.user = get_user_model().objects.create_user(
            username="baseline-tester", email="bt@example.com",
        )
        cls.level = RequirementLevel.objects.create(
            code="SYS", name="System", order=1,
        )
        cls.project = Project.objects.create(
            product=cls.product, name="Baseline Project", code="BP",
            status="active",
        )

        cls.req_alpha = Requirement.objects.create(
            product=cls.product, project=cls.project, level=cls.level,
            identifier="REQ-001", title="Alpha title", status="approved",
            priority="medium", created_by=cls.user,
        )
        cls.req_beta = Requirement.objects.create(
            product=cls.product, project=cls.project, level=cls.level,
            identifier="REQ-002", title="Beta title", status="draft",
            priority="high", created_by=cls.user,
        )
        cls.req_gamma = Requirement.objects.create(
            product=cls.product, project=cls.project, level=cls.level,
            identifier="REQ-003", title="Gamma title", status="approved",
            priority="low", created_by=cls.user,
        )


class FreezeCapturesCurrentRequirementsTest(_BaselineSetup):
    def test_should_freeze_current_requirements_when_baseline_created(self):
        baseline = ProjectBaseline.freeze(
            self.project, "v1.0",
            notes="Initial release", created_by=self.user,
        )

        identifiers = list(
            baseline.requirement_snapshots.order_by("identifier")
            .values_list("identifier", flat=True)
        )
        self.assertEqual(identifiers, ["REQ-001", "REQ-002", "REQ-003"])

        alpha_snap = baseline.requirement_snapshots.get(identifier="REQ-001")
        self.assertEqual(alpha_snap.title, "Alpha title")
        self.assertEqual(alpha_snap.status, "approved")
        self.assertEqual(alpha_snap.priority, "medium")
        self.assertEqual(alpha_snap.level_code, "SYS")
        self.assertEqual(alpha_snap.requirement_id, self.req_alpha.pk)
        self.assertEqual(baseline.created_by_id, self.user.pk)


class BaselineImmutableAfterEditTest(_BaselineSetup):
    def test_should_preserve_baseline_after_requirement_edited(self):
        baseline = ProjectBaseline.freeze(self.project, "v1.0")

        # Mutate the source requirement after the baseline was frozen.
        self.req_alpha.title = "MUTATED"
        self.req_alpha.status = "deprecated"
        self.req_alpha.save()

        snap = baseline.requirement_snapshots.get(identifier="REQ-001")
        self.assertEqual(snap.title, "Alpha title")
        self.assertEqual(snap.status, "approved")


class DiffBaselinesTest(_BaselineSetup):
    def test_should_diff_two_baselines_into_added_removed_modified_buckets(self):
        v1 = ProjectBaseline.freeze(self.project, "v1.0")

        # 1. modify REQ-001 (title change)
        self.req_alpha.title = "Alpha title (v2)"
        self.req_alpha.save()

        # 2. delete REQ-002 (removed in v2)
        self.req_beta.delete()

        # 3. add a brand-new requirement (added in v2)
        Requirement.objects.create(
            product=self.product, project=self.project, level=self.level,
            identifier="REQ-004", title="Delta title", status="draft",
            priority="medium", created_by=self.user,
        )

        v2 = ProjectBaseline.freeze(self.project, "v2.0")

        diff = _diff_baselines(v1, v2)

        added_ids = [s.identifier for s in diff["added"]]
        removed_ids = [s.identifier for s in diff["removed"]]
        modified_ids = [m["identifier"] for m in diff["modified"]]

        self.assertEqual(added_ids, ["REQ-004"])
        self.assertEqual(removed_ids, ["REQ-002"])
        self.assertEqual(modified_ids, ["REQ-001"])
        # Title change is reported.
        modification = diff["modified"][0]
        self.assertTrue(any(c["field"] == "title" for c in modification["changes"]))
