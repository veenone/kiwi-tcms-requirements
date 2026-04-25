"""v0.3.0 Project layer — ordering on the list page and scoped metrics.

These tests need a live ORM (Product, Project, Requirement) so they
extend `django.test.TestCase`. Run via:

    manage.py test tcms_requirements.tests.test_project_v030 --settings=tcms.settings.test
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from tcms.management.models import Classification, Product, Version

from tcms_requirements.dashboard.metrics import dashboard_snapshot
from tcms_requirements.forms import ProjectForm
from tcms_requirements.models import (
    CustomFieldDefinition,
    Project,
    Requirement,
    RequirementLevel,
)
from tcms_requirements.views import ProjectListView


class DashboardSnapshotScopingTest(TestCase):
    """`dashboard_snapshot(filters={"project": pk})` returns only that project's totals."""

    @classmethod
    def setUpTestData(cls):
        cls.classification = Classification.objects.create(name="Tests")
        cls.product = Product.objects.create(
            name="Test Product", classification=cls.classification,
        )
        Version.objects.create(value="1.0", product=cls.product)
        cls.user = get_user_model().objects.create_user(
            username="rqv030", email="rqv030@example.com",
        )
        cls.level = RequirementLevel.objects.create(
            code="SYS", name="System", order=1,
        )
        cls.project_a = Project.objects.create(
            product=cls.product, name="Programme A", code="PA", status="active",
        )
        cls.project_b = Project.objects.create(
            product=cls.product, name="Programme B", code="PB", status="active",
        )

        for i in range(3):
            Requirement.objects.create(
                product=cls.product,
                project=cls.project_a,
                level=cls.level,
                identifier=f"REQ-A-{i:03d}",
                title=f"Programme A requirement {i}",
                created_by=cls.user,
            )
        for i in range(2):
            Requirement.objects.create(
                product=cls.product,
                project=cls.project_b,
                level=cls.level,
                identifier=f"REQ-B-{i:03d}",
                title=f"Programme B requirement {i}",
                created_by=cls.user,
            )

    def test_should_count_only_requirements_in_filtered_project(self):
        snapshot = dashboard_snapshot(filters={"project": self.project_a.pk})

        self.assertEqual(snapshot["total"], 3)


class ProjectListViewOrderingTest(TestCase):
    """Closed/cancelled programmes drop below active/planning/on_hold ones."""

    @classmethod
    def setUpTestData(cls):
        cls.classification = Classification.objects.create(name="Tests")
        cls.product = Product.objects.create(
            name="Ordering Product", classification=cls.classification,
        )
        Version.objects.create(value="1.0", product=cls.product)
        cls.closed = Project.objects.create(
            product=cls.product, name="Old Programme", code="OLD", status="closed",
        )
        cls.active = Project.objects.create(
            product=cls.product, name="Current Programme", code="CUR", status="active",
        )

    def test_should_place_active_project_before_closed_project(self):
        view = ProjectListView()
        view.request = RequestFactory().get("/requirements/projects/")
        view.kwargs = {}
        view.object_list = view.get_queryset()

        ctx = view.get_context_data()

        statuses = [card["project"].status for card in ctx["cards"]]
        self.assertEqual(statuses, ["active", "closed"])


class ProjectCreateViewTest(TestCase):
    """`POST /requirements/projects/new/` writes a new Project and redirects."""

    @classmethod
    def setUpTestData(cls):
        cls.classification = Classification.objects.create(name="Tests")
        cls.product = Product.objects.create(
            name="CRUD Product", classification=cls.classification,
        )
        Version.objects.create(value="1.0", product=cls.product)
        cls.user = get_user_model().objects.create_user(
            username="creator", email="creator@example.com", password="pw",
        )
        cls.user.user_permissions.add(
            Permission.objects.get(codename="add_project"),
        )

    def test_should_persist_project_and_redirect_to_list(self):
        client = Client()
        client.force_login(self.user)

        response = client.post(reverse("requirement-project-new"), data={
            "product": self.product.pk,
            "name": "Brand New Programme",
            "code": "BNP",
            "description": "",
            "status": "planning",
            "stakeholders": [],
            "test_plans": [],
            "jira_project_key": "",
            "external_refs": "{}",
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("requirement-project-list"))
        self.assertTrue(Project.objects.filter(name="Brand New Programme").exists())


class CustomFieldRenderTest(TestCase):
    """An active CustomFieldDefinition shows up on the matching form."""

    @classmethod
    def setUpTestData(cls):
        cls.classification = Classification.objects.create(name="Tests")
        cls.product = Product.objects.create(
            name="CF Render Product", classification=cls.classification,
        )
        Version.objects.create(value="1.0", product=cls.product)
        CustomFieldDefinition.objects.create(
            target_model="project",
            slug="request_id",
            label="Request ID",
            field_type="text",
        )

    def test_should_expose_definition_as_form_field(self):
        form = ProjectForm()

        self.assertIn("cf_request_id", form.fields)


class CustomFieldPersistTest(TestCase):
    """Submitting a value writes it into Project.external_refs[slug]."""

    @classmethod
    def setUpTestData(cls):
        cls.classification = Classification.objects.create(name="Tests")
        cls.product = Product.objects.create(
            name="CF Persist Product", classification=cls.classification,
        )
        Version.objects.create(value="1.0", product=cls.product)
        cls.user = get_user_model().objects.create_user(
            username="cf-user", email="cf@example.com", password="pw",
        )
        cls.user.user_permissions.add(
            Permission.objects.get(codename="add_project"),
        )
        CustomFieldDefinition.objects.create(
            target_model="project",
            slug="request_id",
            label="Request ID",
            field_type="text",
        )

    def test_should_persist_value_into_external_refs(self):
        client = Client()
        client.force_login(self.user)

        client.post(reverse("requirement-project-new"), data={
            "product": self.product.pk,
            "name": "Programme With CF",
            "code": "PWC",
            "description": "",
            "status": "active",
            "stakeholders": [],
            "test_plans": [],
            "jira_project_key": "",
            "external_refs": "{}",
            "cf_request_id": "REQ-7421",
        })

        project = Project.objects.get(name="Programme With CF")
        self.assertEqual(project.external_refs.get("request_id"), "REQ-7421")


class ProjectUpdateViewTest(TestCase):
    """`POST /requirements/projects/<pk>/edit/` updates the row + redirects to detail."""

    @classmethod
    def setUpTestData(cls):
        cls.classification = Classification.objects.create(name="Tests")
        cls.product = Product.objects.create(
            name="Edit Product", classification=cls.classification,
        )
        Version.objects.create(value="1.0", product=cls.product)
        cls.user = get_user_model().objects.create_user(
            username="editor", email="editor@example.com", password="pw",
        )
        cls.user.user_permissions.add(
            Permission.objects.get(codename="change_project"),
        )
        cls.project = Project.objects.create(
            product=cls.product,
            name="To Be Closed",
            code="TBC",
            status="active",
        )

    def test_should_apply_status_change(self):
        client = Client()
        client.force_login(self.user)

        response = client.post(
            reverse("requirement-project-edit", args=[self.project.pk]),
            data={
                "product": self.product.pk,
                "name": self.project.name,
                "code": self.project.code,
                "description": "",
                "status": "closed",
                "stakeholders": [],
                "test_plans": [],
                "jira_project_key": "",
                "external_refs": "{}",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "closed")
