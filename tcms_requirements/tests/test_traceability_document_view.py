"""Source-document Sankey: Document → Requirement → Test case.

Run via:

    manage.py test tcms_requirements.tests.test_traceability_document_view --settings=tcms.settings.test
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from tcms.management.models import Classification, Product
from tcms.testcases.models import TestCase as KiwiTestCase, Category

from tcms_requirements.models import (
    Requirement,
    RequirementLevel,
    RequirementTestCaseLink,
)
from tcms_requirements.traceability.diagram import (
    build_document_sankey_payload,
)


class _DocSankeySetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.classification = Classification.objects.create(name="DocSankey")
        cls.product = Product.objects.create(
            name="Doc Sankey Product", classification=cls.classification,
        )
        cls.category = Category.objects.filter(product=cls.product).first()
        cls.user = get_user_model().objects.create_user(
            username="doc-sankey", email="doc-sankey@example.com",
        )
        cls.level = RequirementLevel.objects.create(
            code="SYS-DS", name="System (DocSankey)", order=1,
        )
        cls.case_alpha = KiwiTestCase.objects.create(
            summary="Boot timing test",
            category=cls.category,
            author=cls.user,
            case_status_id=1,
            priority_id=1,
        )
        cls.case_beta = KiwiTestCase.objects.create(
            summary="Login lockout test",
            category=cls.category,
            author=cls.user,
            case_status_id=1,
            priority_id=1,
        )
        cls.req_with_title = Requirement.objects.create(
            product=cls.product, level=cls.level,
            identifier="DOCSV-1", title="Boot under 3 seconds",
            document_title="Customer RFP — Platform 2026",
            document_file_name="customer-rfp_v2.pdf",
            created_by=cls.user,
        )
        cls.req_filename_only = Requirement.objects.create(
            product=cls.product, level=cls.level,
            identifier="DOCSV-2", title="Lock after 5 failed logins",
            document_title="",
            document_file_name="tech-spec_v1.4.pdf",
            created_by=cls.user,
        )
        cls.req_no_document = Requirement.objects.create(
            product=cls.product, level=cls.level,
            identifier="DOCSV-3", title="Logo on every page",
            document_title="",
            document_file_name="",
            created_by=cls.user,
        )
        RequirementTestCaseLink.objects.create(
            requirement=cls.req_with_title, case=cls.case_alpha,
            link_type="verifies",
        )
        RequirementTestCaseLink.objects.create(
            requirement=cls.req_filename_only, case=cls.case_beta,
            link_type="verifies",
        )


class DocumentSankeyPayloadTest(_DocSankeySetup):
    def test_should_label_document_node_from_document_title(self):
        payload = build_document_sankey_payload()

        doc_labels = {
            node["name"] for node in payload["nodes"] if node["kind"] == "document"
        }
        self.assertIn("Customer RFP — Platform 2026", doc_labels)


class DocumentSankeyFallbackTest(_DocSankeySetup):
    def test_should_fall_back_to_filename_when_title_blank(self):
        payload = build_document_sankey_payload()

        doc_labels = {
            node["name"] for node in payload["nodes"] if node["kind"] == "document"
        }
        self.assertIn("tech-spec_v1.4.pdf", doc_labels)


class DocumentSankeyEmptyDocumentTest(_DocSankeySetup):
    def test_should_render_no_source_document_node_when_both_blank(self):
        payload = build_document_sankey_payload()

        doc_labels = {
            node["name"] for node in payload["nodes"] if node["kind"] == "document"
        }
        self.assertIn("(no source document)", doc_labels)


class DocumentSankeyEdgeShapeTest(_DocSankeySetup):
    def test_should_emit_document_to_requirement_edge_per_requirement(self):
        payload = build_document_sankey_payload()

        cites_edges = [
            link for link in payload["links"]
            if link.get("link_type") == "cites_document"
        ]
        # One edge per requirement onto its source document node.
        self.assertEqual(len(cites_edges), 3)


class DocumentSankeyViewTest(_DocSankeySetup):
    def test_should_register_document_view_in_switcher_catalogue(self):
        self.user.user_permissions.add(
            Permission.objects.get(codename="view_requirement"),
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("requirement-traceability-document"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "By source document")
