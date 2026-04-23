"""Seed demo bugs so the Sankey traceability diagram renders the Bug column.

Run after `seed_demo_requirements` (which attaches requirements to test
cases) and against a live Kiwi install:

    ./manage.py seed_demo_bugs

What it does:
  1. Finds every TestCase linked to a DEMO-* requirement.
  2. For each such case, ensures at least one TestExecution exists.
     If none do, creates a demo TestRun on an existing TestPlan that
     contains the case (or on any plan if the case isn't in one),
     then fills the run with executions for the demo cases.
  3. Creates 4 demo bugs (3 open, 1 closed) and attaches each to one or
     two TestExecutions — mixing one bug across multiple executions so
     the Sankey shows a fan-in.

Idempotent — re-running updates-in-place by bug title (`[DEMO]` prefix).

Safe to run on production: every seeded object is tagged with `DEMO` or
`[DEMO]` so a single filter lets you delete them later.
"""
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from tcms_requirements.models import Requirement


DEMO_REQ_PREFIX = "DEMO-"
DEMO_RUN_SUMMARY = "[DEMO] Seeded test run for traceability demo"

BUG_SEEDS = [
    {
        "summary": "[DEMO] Voice engine fails to recognise accented words",
        "severity": "Major",
        "status": True,  # open
        "spread": 2,      # attach to 2 executions
    },
    {
        "summary": "[DEMO] Map tile cache leaks memory over long sessions",
        "severity": "Major",
        "status": True,
        "spread": 1,
    },
    {
        "summary": "[DEMO] Telemetry retry backoff not honoured on cell tower switch",
        "severity": "Critical",
        "status": True,
        "spread": 1,
    },
    {
        "summary": "[DEMO] Closed — offline-mode cached route expires too early",
        "severity": "Minor",
        "status": False,  # closed
        "spread": 1,
    },
]


class Command(BaseCommand):
    help = "Seed demo bugs attached to executions of demo-requirement-linked cases."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing [DEMO] bugs before re-seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        # Lazy import Kiwi models — plugin is installable without Kiwi.
        from tcms.bugs.models import Bug, Severity  # noqa: WPS433
        from tcms.management.models import Build, Version  # noqa: WPS433
        from tcms.testcases.models import TestCase  # noqa: WPS433
        from tcms.testruns.models import TestRun, TestExecutionStatus  # noqa: WPS433

        if options["flush"]:
            removed = Bug.objects.filter(summary__startswith="[DEMO]").count()
            Bug.objects.filter(summary__startswith="[DEMO]").delete()
            self.stdout.write(self.style.WARNING(f"Flushed {removed} demo bugs."))

        # Collect cases linked to any DEMO-* requirement.
        case_ids = set(
            Requirement.objects
            .filter(identifier__startswith=DEMO_REQ_PREFIX)
            .values_list("case_links__case_id", flat=True)
        )
        case_ids.discard(None)
        if not case_ids:
            self.stdout.write(self.style.WARNING(
                "No DEMO-* requirements with linked cases found. "
                "Run ./manage.py seed_demo_requirements first."
            ))
            return

        cases = list(TestCase.objects.filter(pk__in=case_ids))
        self.stdout.write(f"Found {len(cases)} demo-linked test cases.")

        # Ensure every case has at least one TestExecution.
        executions = self._ensure_executions(cases, TestRun, TestExecutionStatus, Build)
        if not executions:
            self.stdout.write(self.style.ERROR(
                "Could not find or create TestExecutions — no TestPlan contains "
                "any of the demo-linked cases. Add a case to a plan and retry."
            ))
            return

        # Pick product/version/build scoped to the first execution's run for
        # consistency. Bug FKs are loose anyway (Kiwi doesn't enforce match
        # with the execution's own product).
        reference_run = executions[0].run
        product = reference_run.plan.product
        version = Version.objects.filter(product=product).first()
        build = reference_run.build

        if not version:
            version = Version.objects.create(product=product, value="demo-0.1")
            self.stdout.write(f"Created version for bugs: {version}")

        reporter = self._pick_user()
        # Seed severities in case Kiwi didn't.
        severities = {sv.name: sv for sv in Severity.objects.all()}
        for name in ("Critical", "Major", "Minor"):
            if name not in severities:
                severities[name] = Severity.objects.create(
                    name=name, weight=3, icon="fa-bug", color="#cc0000",
                )

        rng = random.Random(23)
        rng.shuffle(executions)

        created = 0
        for spec in BUG_SEEDS:
            severity = severities.get(spec["severity"])
            bug, was_created = Bug.objects.update_or_create(
                summary=spec["summary"],
                defaults={
                    "status": spec["status"],
                    "reporter": reporter,
                    "product": product,
                    "version": version,
                    "build": build,
                    "severity": severity,
                },
            )
            if was_created:
                created += 1
            # Pick N executions and attach.
            spread = max(1, spec.get("spread", 1))
            bug.executions.clear()
            for execution in executions[:spread]:
                bug.executions.add(execution)
            # Rotate the queue so different executions get different bugs.
            executions = executions[spread:] + executions[:spread]

        total = Bug.objects.filter(summary__startswith="[DEMO]").count()
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {created} new demo bugs (total {total}). "
            f"Refresh /requirements/traceability/ — the Sankey now has a Bug column."
        ))

    # ── helpers ──────────────────────────────────────────────────────

    def _pick_user(self):
        User = get_user_model()
        return User.objects.filter(is_superuser=True).first() or User.objects.first()

    def _ensure_executions(self, cases, TestRun, TestExecutionStatus, Build):
        """Return a list of TestExecutions — one per case, reusing existing
        executions where possible, creating a demo run when none exists."""
        existing = {
            case.pk: case.executions.first()
            for case in cases
            if case.executions.exists()
        }

        cases_without_exec = [c for c in cases if c.pk not in existing]
        if cases_without_exec:
            run = self._find_or_create_demo_run(cases_without_exec, TestRun, Build)
            if run is None:
                # Nothing we can do — user must add the cases to a plan.
                return list(existing.values())

            idle_status = (
                TestExecutionStatus.objects.filter(weight=0).first()
                or TestExecutionStatus.objects.first()
            )
            if idle_status is None:
                self.stdout.write(self.style.ERROR(
                    "Kiwi has no TestExecutionStatus rows seeded."
                ))
                return list(existing.values())

            assignee = self._pick_user()
            for case in cases_without_exec:
                # Case must belong to the run's plan to produce a valid trace.
                if case.plan.filter(pk=run.plan_id).exists():
                    execution = run._create_single_execution(  # noqa: SLF001
                        case=case, assignee=assignee, build=run.build, sortkey=case.pk,
                    )
                    existing[case.pk] = execution

        return list(existing.values())

    def _find_or_create_demo_run(self, cases, TestRun, Build):
        """Find an existing TestPlan containing at least one of the demo cases,
        then reuse or create a [DEMO] run on it."""
        from tcms.testplans.models import TestPlan  # noqa: WPS433

        plans = TestPlan.objects.filter(cases__in=cases).distinct()
        plan = plans.first()
        if plan is None:
            return None

        existing_run = TestRun.objects.filter(
            plan=plan, summary=DEMO_RUN_SUMMARY,
        ).first()
        if existing_run is not None:
            return existing_run

        build = (
            Build.objects.filter(version__product=plan.product).order_by("pk").first()
            or Build.objects.first()
        )
        if build is None:
            return None

        run = TestRun.objects.create(
            summary=DEMO_RUN_SUMMARY,
            notes="Auto-generated by seed_demo_bugs to power the Sankey Bug column.",
            plan=plan,
            build=build,
            manager=self._pick_user(),
        )
        self.stdout.write(self.style.SUCCESS(
            f"Created demo TestRun on plan {plan.name!r}: {run}"
        ))
        return run
