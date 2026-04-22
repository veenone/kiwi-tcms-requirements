"""Seed a demo set of requirements + test-case links for screenshots / demos.

Idempotent by identifier — re-running updates in place rather than
duplicating rows. Will skip TestCase-linking if no test cases exist.

Usage:
    ./manage.py seed_demo_requirements            # uses the first Product, first 8 cases
    ./manage.py seed_demo_requirements --product "Infotainment ECU"
    ./manage.py seed_demo_requirements --flush    # delete existing demo rows first

The demo data covers:
  - 1 Project + 3 Features
  - 12 Requirements across 3 levels (stakeholder / system / software)
  - 1 decomposition chain (stakeholder -> system -> software)
  - 2 requirements with ASIL / IEC 62304 classifications
  - Links to the first N TestCases with mixed link types
  - 1 suspect link (for demo of the reviewer-action workflow)
"""
import random
from django.core.management.base import BaseCommand

from tcms_requirements.models import (
    Feature,
    Project,
    Requirement,
    RequirementCategory,
    RequirementLevel,
    RequirementSource,
    RequirementTestCaseLink,
)


DEMO_IDENTIFIER_PREFIX = "DEMO-"


PROJECT = {"name": "Platform 2026", "code": "PLAT26", "description": "Demo programme for v0.2.0 screenshots."}

FEATURES = [
    {"name": "Voice control", "code": "VOICE"},
    {"name": "Navigation", "code": "NAV"},
    {"name": "Connected services", "code": "CONN"},
]

REQUIREMENTS = [
    # (identifier, title, level, feature, status, priority, asil, iec62304, parent, category, desc)
    ("DEMO-STK-001", "The driver shall control infotainment hands-free.",
     "stakeholder", "Voice control", "approved", "high", "", "",
     None, "Functional",
     "Driver must operate all infotainment functions without removing hands from the wheel."),
    ("DEMO-SYS-010", "The system shall recognise 20 voice commands within 2s.",
     "system", "Voice control", "approved", "high", "B", "",
     "DEMO-STK-001", "Performance",
     "Response latency from end-of-utterance to recognition result must not exceed 2000ms."),
    ("DEMO-SW-050", "Voice engine shall emit an 'intent' event when confidence > 0.8.",
     "software", "Voice control", "implemented", "high", "B", "",
     "DEMO-SYS-010", "Functional",
     "VoiceEngine.onIntent(confidence > 0.8) publishes to event bus 'voice.intent'."),
    ("DEMO-SW-051", "Voice engine shall fall back to touch UI on confidence < 0.4.",
     "software", "Voice control", "implemented", "medium", "", "",
     "DEMO-SYS-010", "UI/UX",
     "When confidence < 0.4, prompt user to use touchscreen alternative."),

    ("DEMO-STK-002", "Drivers shall see turn-by-turn navigation.",
     "stakeholder", "Navigation", "approved", "critical", "", "",
     None, "Functional",
     "Core feature; drivers expect on-screen and audible turn-by-turn guidance."),
    ("DEMO-SYS-020", "Map tiles shall load within 500ms under LTE.",
     "system", "Navigation", "approved", "high", "", "",
     "DEMO-STK-002", "Performance",
     "Tile-fetch latency budget: 500ms median under LTE, 1500ms p95."),
    ("DEMO-SW-060", "The map renderer shall cache the last 50 tiles.",
     "software", "Navigation", "verified", "medium", "", "",
     "DEMO-SYS-020", "Performance",
     "LRU cache of 50 rendered map tiles. Cache survives app restart."),
    ("DEMO-SW-061", "Offline mode shall display a cached route when LTE drops.",
     "software", "Navigation", "approved", "high", "", "",
     "DEMO-SYS-020", "Functional",
     "If LTE becomes unavailable mid-route, continue using cached route data for up to 30 minutes."),

    ("DEMO-STK-003", "Vehicle data shall be transmitted to the back-end at 10 Hz.",
     "stakeholder", "Connected services", "approved", "high", "", "",
     None, "Functional",
     "Telemetry framework sends vehicle signals to the cloud at 10Hz sampling rate."),
    ("DEMO-SYS-030", "Telemetry shall be encrypted end-to-end (TLS 1.3).",
     "system", "Connected services", "approved", "critical", "", "",
     "DEMO-STK-003", "Security",
     "All connected-services traffic must use TLS 1.3 with certificate pinning."),
    ("DEMO-SW-070", "Telemetry agent shall retry with exp. backoff on network failure.",
     "software", "Connected services", "implemented", "medium", "", "",
     "DEMO-SYS-030", "Functional",
     "Backoff sequence: 1s, 2s, 4s, 8s, 16s (max). Cap at 16s retry window."),
    ("DEMO-SW-071", "Telemetry agent shall log dropped packets for later replay.",
     "software", "Connected services", "verified", "low", "", "",
     "DEMO-SYS-030", "Maintainability",
     "When a send fails after retries, journal the packet to disk with timestamp."),
]


class Command(BaseCommand):
    help = "Seed a demo set of requirements + test-case links (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--product",
            default=None,
            help="Product name to scope the seed under. Defaults to the first Product.",
        )
        parser.add_argument(
            "--cases",
            type=int,
            default=8,
            help="Number of existing TestCases to link (default: 8).",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing DEMO-* requirements + their links before seeding.",
        )

    def handle(self, *args, **options):
        product = self._resolve_product(options.get("product"))
        if options["flush"]:
            removed_count = self._flush()
            self.stdout.write(self.style.WARNING(f"Flushed {removed_count} existing demo requirements."))

        # Category lookup (seeded by 0002_seed_catalog).
        categories = {c.name: c for c in RequirementCategory.objects.all()}
        sources = list(RequirementSource.objects.all())
        source = sources[0] if sources else None
        levels = {lv.code: lv for lv in RequirementLevel.objects.filter(is_active=True)}

        project, _ = Project.objects.update_or_create(
            product=product,
            name=PROJECT["name"],
            defaults={"code": PROJECT["code"], "description": PROJECT["description"]},
        )
        self.stdout.write(self.style.SUCCESS(f"Project: {project}"))

        features = {}
        for spec in FEATURES:
            feat, _ = Feature.objects.update_or_create(
                project=project,
                name=spec["name"],
                defaults={"code": spec["code"]},
            )
            features[spec["name"]] = feat

        # First pass: create requirements without parent FKs.
        created_map = {}
        for spec in REQUIREMENTS:
            ident, title, level_code, feat_name, status, priority, asil, iec, parent, cat_name, desc = spec
            level = levels.get(level_code)
            if level is None:
                self.stdout.write(self.style.WARNING(
                    f"Level {level_code!r} not found (active level profile may differ). Skipping {ident}."
                ))
                continue
            req, _ = Requirement.objects.update_or_create(
                identifier=ident,
                defaults={
                    "title": title,
                    "description": desc,
                    "rationale": "",
                    "category": categories.get(cat_name),
                    "source": source,
                    "level": level,
                    "product": product,
                    "project": project,
                    "feature": features.get(feat_name),
                    "status": status,
                    "priority": priority,
                    "asil": asil,
                    "iec62304_class": iec,
                    "verification_method": "test",
                },
            )
            created_map[ident] = req
        self.stdout.write(self.style.SUCCESS(f"Upserted {len(created_map)} requirements."))

        # Second pass: wire parent FKs (parent identifier is tuple index 8).
        for spec in REQUIREMENTS:
            ident = spec[0]
            parent = spec[8]
            if parent and ident in created_map and parent in created_map:
                created_map[ident].parent_requirement = created_map[parent]
                created_map[ident].save(update_fields=["parent_requirement"])

        # Link a handful of test cases.
        self._link_testcases(created_map, n=options["cases"])

    def _resolve_product(self, name):
        try:
            from tcms.management.models import Product  # noqa: WPS433
        except ImportError:
            raise SystemExit("Kiwi TCMS is not importable from this shell — run this command inside the Kiwi virtualenv.")

        if name:
            try:
                return Product.objects.get(name=name)
            except Product.DoesNotExist:
                raise SystemExit(f"Product {name!r} not found. Create it in Kiwi's admin first.")
        product = Product.objects.order_by("pk").first()
        if not product:
            raise SystemExit("No Products exist in Kiwi TCMS. Create at least one before seeding.")
        return product

    def _flush(self) -> int:
        qs = Requirement.objects.filter(identifier__startswith=DEMO_IDENTIFIER_PREFIX)
        count = qs.count()
        qs.delete()
        return count

    def _link_testcases(self, created_map, n):
        try:
            from tcms.testcases.models import TestCase  # noqa: WPS433
        except ImportError:
            self.stdout.write(self.style.WARNING("Kiwi TestCase model not importable — skipping link seeding."))
            return

        cases = list(TestCase.objects.order_by("pk")[:n])
        if not cases:
            self.stdout.write(self.style.WARNING("No TestCases exist — skipping link seeding (run /requirements/ empty)."))
            return

        link_types = ["verifies", "validates", "verifies", "verifies", "derives_from", "related"]
        rng = random.Random(42)  # deterministic seed for reproducible demos
        # Link each SW-level requirement to 1-2 cases; leaf reqs carry the verification.
        software_reqs = [r for r in created_map.values() if r.level and r.level.code == "software"]
        if not software_reqs:
            software_reqs = list(created_map.values())[:6]

        created = 0
        for req in software_reqs:
            picks = rng.sample(cases, k=min(2, len(cases)))
            for case in picks:
                lt = rng.choice(link_types)
                _, was_created = RequirementTestCaseLink.objects.update_or_create(
                    requirement=req,
                    case=case,
                    link_type=lt,
                    defaults={"suspect": False, "coverage_notes": "Seeded by seed_demo_requirements."},
                )
                if was_created:
                    created += 1

        # Also link the top-level stakeholder req to one case via "validates" for a multi-hop graph.
        stakeholder_reqs = [r for r in created_map.values() if r.level and r.level.code == "stakeholder"]
        for req in stakeholder_reqs[:1]:
            case = cases[0]
            _, was_created = RequirementTestCaseLink.objects.update_or_create(
                requirement=req,
                case=case,
                link_type="validates",
                defaults={"suspect": False, "coverage_notes": "Demo validation link."},
            )
            if was_created:
                created += 1

        # Flip one link to suspect for demo purposes.
        any_link = RequirementTestCaseLink.objects.filter(
            requirement__identifier__startswith=DEMO_IDENTIFIER_PREFIX,
        ).first()
        if any_link is not None:
            any_link.suspect = True
            any_link.save(update_fields=["suspect"])

        total = RequirementTestCaseLink.objects.filter(
            requirement__identifier__startswith=DEMO_IDENTIFIER_PREFIX,
        ).count()
        self.stdout.write(self.style.SUCCESS(
            f"Linked {created} new (total {total}) — 1 flagged suspect for demo."
        ))
