"""One-shot end-to-end demo seed.

Calls (or inlines) every seed step in order so a blank Kiwi install ends
up with a complete, renderable Sankey chain:

    Product → Version → Build → TestPlan
                                   │
                                   ├─ TestCases (demo)
                                   │      │
                                   ├─ TestRun
                                   │      │
                                   │      └─ TestExecutions
                                   │               │
                                   │               └─ Bugs (open + closed)
                                   │
                                   └─ Requirements ← (separate tree)
                                          └─ RequirementTestCaseLink → case

Each created object has a `DEMO` / `[DEMO]` marker in its name or summary
so you can find and delete them later with one filter per model.

Usage:
    ./manage.py seed_demo_all
    ./manage.py seed_demo_all --flush       # remove existing DEMO rows first

Idempotent — reruns update objects in place.
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction


DEMO_PRODUCT_NAME = "Demo product"
DEMO_VERSION_VALUE = "demo-0.1"
DEMO_BUILD_NAME = "demo-build"
DEMO_PLAN_NAME = "[DEMO] Platform 2026 master plan"
DEMO_CATEGORY_NAME = "DEMO-feature"

DEMO_CASES = [
    "[DEMO] Boot and reach home screen",
    "[DEMO] OAuth sign-in happy path",
    "[DEMO] OAuth sign-in — bad credentials locks after 5 attempts",
    "[DEMO] Password reset token expires after 30 min",
    "[DEMO] Invoice totals round correctly",
    "[DEMO] Map tiles load within 500ms on LTE",
    "[DEMO] Offline route cached for 30 min when LTE drops",
    "[DEMO] Telemetry agent retries with exp. backoff",
]


class Command(BaseCommand):
    help = "End-to-end demo seed: product, plan, cases, run, executions, requirements, bugs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete previously-seeded DEMO-* requirements, bugs, run, cases, plan before re-seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        # Lazy-import Kiwi models.
        from tcms.management.models import (  # noqa: WPS433
            Build,
            Classification,
            Priority,
            Product,
            Version,
        )
        from tcms.testcases.models import Category, TestCase, TestCaseStatus  # noqa: WPS433
        from tcms.testplans.models import PlanType, TestPlan  # noqa: WPS433

        if options["flush"]:
            self._flush()

        user = self._pick_user()
        product = self._ensure_product(Product, Classification)
        version = self._ensure_version(Version, product)
        build = self._ensure_build(Build, version)
        plan_type = PlanType.objects.first() or PlanType.objects.create(name="Unit")
        plan = self._ensure_plan(TestPlan, product, version, plan_type, user)
        category = self._ensure_category(Category, product)
        case_status = (
            TestCaseStatus.objects.filter(is_confirmed=True).first()
            or TestCaseStatus.objects.first()
        )
        if case_status is None:
            self.stderr.write(self.style.ERROR(
                "Kiwi has no TestCaseStatus rows — run migrations first."
            ))
            return

        priority = Priority.objects.first()
        if priority is None:
            self.stderr.write(self.style.ERROR(
                "Kiwi has no Priority rows — run migrations first."
            ))
            return

        cases = self._ensure_cases(
            TestCase, plan, category, case_status, priority, user,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Prepared {len(cases)} demo test cases on plan {plan.name!r}."
        ))

        # Delegate to the existing narrower seeders so all business logic
        # lives in one place.
        self.stdout.write(self.style.MIGRATE_HEADING("--- seeding requirements ---"))
        call_command("seed_demo_requirements", "--product", product.name, "--cases", "8")

        self.stdout.write(self.style.MIGRATE_HEADING("--- seeding bugs ---"))
        call_command("seed_demo_bugs")

        self.stdout.write(self.style.MIGRATE_HEADING("--- wiring project chain ---"))
        self._wire_project_to_plan(plan)
        self._spread_execution_statuses(plan)

        self.stdout.write(self.style.SUCCESS(
            "\nDone. Visit /requirements/projects/ — every demo project now has "
            "the demo plan in its scope, mixed pass/fail executions for the "
            "verification view, and the Sankey populates end-to-end."
        ))

    # ── helpers ──────────────────────────────────────────────────────

    def _pick_user(self):
        User = get_user_model()
        return User.objects.filter(is_superuser=True).first() or User.objects.first()

    def _ensure_product(self, Product, Classification):
        product = Product.objects.filter(name=DEMO_PRODUCT_NAME).first()
        if product:
            self.stdout.write(f"Using existing product: {product.name!r}")
            return product

        existing = Product.objects.first()
        if existing:
            self.stdout.write(f"Using first existing product: {existing.name!r}")
            return existing

        classification, _ = Classification.objects.get_or_create(name="Demo classification")
        product = Product.objects.create(name=DEMO_PRODUCT_NAME, classification=classification)
        self.stdout.write(self.style.SUCCESS(f"Created product: {product.name!r}"))
        return product

    def _ensure_version(self, Version, product):
        version, created = Version.objects.get_or_create(
            product=product, value=DEMO_VERSION_VALUE,
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created version: {version.value!r}"))
        else:
            existing = Version.objects.filter(product=product).first()
            if existing and existing != version:
                # Prefer whatever already exists on the product.
                self.stdout.write(f"Using existing version: {existing.value!r}")
                return existing
        return version

    def _ensure_build(self, Build, version):
        build = Build.objects.filter(version=version, name=DEMO_BUILD_NAME).first()
        if build:
            return build
        existing = Build.objects.filter(version=version).first()
        if existing:
            self.stdout.write(f"Using existing build: {existing.name!r}")
            return existing
        build = Build.objects.create(version=version, name=DEMO_BUILD_NAME)
        self.stdout.write(self.style.SUCCESS(f"Created build: {build.name!r}"))
        return build

    def _ensure_plan(self, TestPlan, product, version, plan_type, user):
        plan = TestPlan.objects.filter(name=DEMO_PLAN_NAME, product=product).first()
        if plan:
            return plan
        plan = TestPlan.objects.create(
            name=DEMO_PLAN_NAME,
            text="Auto-generated demo plan for the traceability Sankey.",
            product=product,
            product_version=version,
            author=user,
            type=plan_type,
        )
        self.stdout.write(self.style.SUCCESS(f"Created plan: {plan.name!r}"))
        return plan

    def _ensure_category(self, Category, product):
        category, created = Category.objects.get_or_create(
            product=product, name=DEMO_CATEGORY_NAME,
            defaults={"description": "Demo category for auto-seeded cases."},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created category: {category.name!r}"))
        return category

    def _ensure_cases(self, TestCase, plan, category, case_status, priority, user):
        cases = []
        for idx, summary in enumerate(DEMO_CASES, start=1):
            case = TestCase.objects.filter(summary=summary).first()
            if case is None:
                case = TestCase.objects.create(
                    summary=summary,
                    text=f"Auto-generated demo test case #{idx}.",
                    case_status=case_status,
                    category=category,
                    priority=priority,
                    author=user,
                    is_automated=(idx % 2 == 0),
                )
                self.stdout.write(f"  Created case: TC-{case.pk} {summary!r}")
            # Ensure case is attached to the demo plan.
            plan.add_case(case)
            cases.append(case)
        return cases

    def _wire_project_to_plan(self, plan):
        """Attach the demo plan plus every plan that hosts demo-linked
        executions to each demo Project's `test_plans` M2M.

        seed_demo_bugs may have placed its demo TestRun on a pre-existing
        plan (whichever already contained the demo cases) rather than our
        own [DEMO] plan, so we union both into project scope.
        """
        from tcms.testplans.models import TestPlan  # noqa: WPS433
        from tcms.testruns.models import TestRun  # noqa: WPS433

        from tcms_requirements.models import Project  # noqa: WPS433

        projects = Project.objects.filter(product=plan.product)
        if not projects.exists():
            self.stdout.write(self.style.WARNING(
                "No projects found on the demo product — skipping plan wiring."
            ))
            return

        plan_ids = {plan.pk}
        plan_ids.update(
            TestRun.objects.filter(summary__startswith="[DEMO]")
            .values_list("plan_id", flat=True)
        )
        plans = list(TestPlan.objects.filter(pk__in=plan_ids))
        for project in projects:
            project.test_plans.add(*plans)
            names = ", ".join(repr(p.name) for p in plans)
            self.stdout.write(
                f"Linked {len(plans)} plan(s) to project {project.name!r}: {names}"
            )

    def _spread_execution_statuses(self, plan):
        """Flip a slice of demo TestExecutions to PASSED/FAILED so the
        verification Sankey view shows mixed outcomes instead of all-IDLE.

        Targets executions in [DEMO] runs (regardless of which plan they
        landed on) since seed_demo_bugs may pick a non-demo plan.
        """
        from tcms.testruns.models import TestExecution, TestExecutionStatus  # noqa: WPS433

        passed = (
            TestExecutionStatus.objects.filter(weight__gt=0).order_by("weight").first()
        )
        failed = (
            TestExecutionStatus.objects.filter(weight__lt=0).order_by("-weight").first()
        )
        if passed is None or failed is None:
            self.stdout.write(self.style.WARNING(
                "Kiwi has no positive-weight or negative-weight TestExecutionStatus "
                "rows — leaving demo executions at IDLE."
            ))
            return

        executions = list(
            TestExecution.objects.filter(run__summary__startswith="[DEMO]")
            .order_by("pk")
        )
        if not executions:
            self.stdout.write(self.style.WARNING(
                "No executions found on [DEMO] runs — verification view will be all-IDLE."
            ))
            return

        # 60% pass, 30% fail, 10% remain idle — mirrors a realistic dev cycle.
        for idx, execution in enumerate(executions):
            if idx % 10 < 6:
                execution.status = passed
            elif idx % 10 < 9:
                execution.status = failed
            else:
                continue
            execution.save(update_fields=["status"])

        self.stdout.write(self.style.SUCCESS(
            f"Spread statuses across {len(executions)} executions "
            f"(~60% pass / 30% fail)."
        ))

    def _flush(self):
        """Best-effort removal of previously-seeded DEMO rows.

        Order matters — delete the leaf objects first so FKs don't block.
        Errors are logged and move on (e.g. if an object model changed).
        """
        from tcms.bugs.models import Bug  # noqa: WPS433
        from tcms.testcases.models import Category, TestCase  # noqa: WPS433
        from tcms.testplans.models import TestPlan  # noqa: WPS433
        from tcms.testruns.models import TestRun  # noqa: WPS433

        from tcms_requirements.models import (  # noqa: WPS433
            Feature,
            Project,
            Requirement,
        )

        summary_markers = {
            "Bug": Bug.objects.filter(summary__startswith="[DEMO]"),
            "Requirement": Requirement.objects.filter(identifier__startswith="DEMO-"),
            "Feature": Feature.objects.filter(code__startswith="DEMO-"),
            "Project": Project.objects.filter(code__startswith="DEMO-"),
            "TestRun": TestRun.objects.filter(summary__startswith="[DEMO]"),
            "TestCase": TestCase.objects.filter(summary__startswith="[DEMO]"),
            "TestPlan": TestPlan.objects.filter(name__startswith="[DEMO]"),
            "Category": Category.objects.filter(name__startswith="DEMO-"),
        }
        for label, qs in summary_markers.items():
            try:
                n = qs.count()
            except Exception:  # noqa: BLE001
                n = 0
            if n:
                qs.delete()
                self.stdout.write(self.style.WARNING(f"Flushed {n} demo {label}(s)."))
