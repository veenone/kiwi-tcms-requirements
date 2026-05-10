"""v0.4.3: CSV/XLSX import wires up the ``linked_cases`` column.

Before this slice, exporting requirements to CSV → editing → re-importing
silently dropped every test-case link. This module locks down:

  - bare integers (``42,57``) and JIRA-style ``TC-`` prefixes both parse
  - update_or_create flow synchronises links (replaces, doesn't merge)
  - empty cell clears links; absent column leaves links alone
  - typoed case ids surface as a per-row error and skip mutation

Run via::

    manage.py test tcms_requirements.tests.test_csv_import_linked_cases \\
        --settings=tcms.settings.test
"""
import io

from django.contrib.auth import get_user_model
from django.test import TestCase

from tcms.management.models import Classification, Product
from tcms.testcases.models import Category, TestCase as TestCaseModel

from tcms_requirements.imports.csv_import import import_bytes, import_csv
from tcms_requirements.models import (
    Requirement,
    RequirementLevel,
    RequirementTestCaseLink,
)


class _LinkedCasesSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.classification = Classification.objects.create(name="LinkedCasesCls")
        cls.product = Product.objects.create(
            name="Linked Cases Product", classification=cls.classification,
        )
        cls.user = get_user_model().objects.create_user(
            username="links-tester", email="links@example.com",
        )
        cls.level = RequirementLevel.objects.create(
            code="LCS", name="System", order=1,
        )
        cls.case_category = Category.objects.create(
            product=cls.product, name="Linked Cases Category",
        )
        cls.case_a = TestCaseModel.objects.create(
            summary="Linked case A",
            category=cls.case_category,
            author=cls.user,
        )
        cls.case_b = TestCaseModel.objects.create(
            summary="Linked case B",
            category=cls.case_category,
            author=cls.user,
        )
        cls.case_c = TestCaseModel.objects.create(
            summary="Linked case C",
            category=cls.case_category,
            author=cls.user,
        )

    def _csv(self, *rows):
        header = "identifier,title,linked_cases\n"
        body = "\n".join(rows) + "\n"
        return (header + body).encode("utf-8")


class CreateRequirementWithBareCaseIds(_LinkedCasesSetup):
    def test_should_create_links_from_comma_separated_integers(self):
        data = self._csv(
            f'LCS-1,"Bare ints","{self.case_a.pk},{self.case_b.pk}"',
        )
        result = import_bytes(data, "links.csv", dry_run=False, user=self.user)

        self.assertEqual(result.errors, [])
        req = Requirement.objects.get(identifier="LCS-1")
        linked = set(req.case_links.values_list("case_id", flat=True))
        self.assertEqual(linked, {self.case_a.pk, self.case_b.pk})


class CreateRequirementWithJiraStylePrefix(_LinkedCasesSetup):
    def test_should_accept_TC_prefix(self):
        data = self._csv(
            f'LCS-2,"TC prefix","TC-{self.case_a.pk}, TC-{self.case_c.pk}"',
        )
        result = import_bytes(data, "links.csv", dry_run=False, user=self.user)

        self.assertEqual(result.errors, [])
        req = Requirement.objects.get(identifier="LCS-2")
        linked = set(req.case_links.values_list("case_id", flat=True))
        self.assertEqual(linked, {self.case_a.pk, self.case_c.pk})


class LinksDefaultToVerifiesNotSuspect(_LinkedCasesSetup):
    def test_default_link_type_is_verifies(self):
        data = self._csv(f'LCS-3,"Default link","{self.case_a.pk}"')
        import_bytes(data, "links.csv", dry_run=False, user=self.user)
        link = RequirementTestCaseLink.objects.get(
            requirement__identifier="LCS-3", case_id=self.case_a.pk,
        )
        self.assertEqual(link.link_type, "verifies")
        self.assertFalse(link.suspect)


class UpdateRequirementReplacesLinks(_LinkedCasesSetup):
    def test_existing_links_are_replaced_with_csv_contents(self):
        # Pre-seed: requirement linked to case_a + case_b
        seed = Requirement.objects.create(
            product=self.product, level=self.level,
            identifier="LCS-4", title="Pre-seeded",
            created_by=self.user,
        )
        RequirementTestCaseLink.objects.create(
            requirement=seed, case=self.case_a, link_type="verifies",
        )
        RequirementTestCaseLink.objects.create(
            requirement=seed, case=self.case_b, link_type="verifies",
        )

        # Re-import with linked_cases pointing only at case_c
        data = self._csv(f'LCS-4,"Pre-seeded","{self.case_c.pk}"')
        result = import_bytes(data, "links.csv", dry_run=False, user=self.user)

        self.assertEqual(result.errors, [])
        linked = set(seed.case_links.values_list("case_id", flat=True))
        self.assertEqual(linked, {self.case_c.pk})


class EmptyLinkedCasesClearsLinks(_LinkedCasesSetup):
    def test_empty_cell_drops_existing_links(self):
        seed = Requirement.objects.create(
            product=self.product, level=self.level,
            identifier="LCS-5", title="Will be cleared",
            created_by=self.user,
        )
        RequirementTestCaseLink.objects.create(
            requirement=seed, case=self.case_a,
        )

        data = self._csv('LCS-5,"Will be cleared",""')
        result = import_bytes(data, "links.csv", dry_run=False, user=self.user)

        self.assertEqual(result.errors, [])
        self.assertEqual(seed.case_links.count(), 0)


class AbsentColumnPreservesLinks(_LinkedCasesSetup):
    def test_csv_without_linked_cases_column_leaves_existing_links_alone(self):
        seed = Requirement.objects.create(
            product=self.product, level=self.level,
            identifier="LCS-6", title="Untouched links",
            created_by=self.user,
        )
        RequirementTestCaseLink.objects.create(
            requirement=seed, case=self.case_a,
        )

        # No linked_cases column at all
        data = b'identifier,title\nLCS-6,"Untouched links"\n'
        import_bytes(data, "no-links.csv", dry_run=False, user=self.user)

        self.assertEqual(seed.case_links.count(), 1)


class UnknownCaseIdYieldsRowError(_LinkedCasesSetup):
    def test_typoed_case_id_surfaces_as_error_without_partial_mutation(self):
        seed = Requirement.objects.create(
            product=self.product, level=self.level,
            identifier="LCS-7", title="Typo guard",
            created_by=self.user,
        )
        RequirementTestCaseLink.objects.create(
            requirement=seed, case=self.case_a,
        )

        # 99999 is a TestCase that doesn't exist
        data = self._csv(f'LCS-7,"Typo guard","{self.case_b.pk},99999"')
        result = import_bytes(data, "links.csv", dry_run=False, user=self.user)

        self.assertTrue(any("99999" in err.message for err in result.errors))
        # Existing link must remain intact — no half-applied state
        linked = set(seed.case_links.values_list("case_id", flat=True))
        self.assertEqual(linked, {self.case_a.pk})


class MalformedTokenYieldsRowError(_LinkedCasesSetup):
    def test_non_integer_token_surfaces_as_error(self):
        data = self._csv('LCS-8,"Bad token","not-a-number"')
        result = import_bytes(data, "links.csv", dry_run=False, user=self.user)

        self.assertTrue(any(
            "not-a-number" in err.message for err in result.errors
        ))


class DryRunDoesNotPersistLinks(_LinkedCasesSetup):
    def test_dry_run_rolls_back_link_changes(self):
        data = self._csv(f'LCS-9,"Dry run","{self.case_a.pk}"')
        result = import_bytes(data, "links.csv", dry_run=True, user=self.user)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.rows_created, 1)  # Reported as created
        self.assertFalse(
            Requirement.objects.filter(identifier="LCS-9").exists()
        )
