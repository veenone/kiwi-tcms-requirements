"""Seed RequirementCategory, RequirementSource, RequirementLevel rows.

The level profile is driven by the `REQUIREMENTS_LEVEL_PROFILE` setting
(values: `aspice` (default), `iso9001`, `iec62304`, `do178c`, `generic`).
All seed rows are created idempotently — re-running migrate is safe.
"""
from django.conf import settings
from django.db import migrations


CATEGORY_SEEDS = [
    ("Functional", "Observable behaviour the system must exhibit.", "#39a5dc"),
    ("Non-functional", "Quality attributes (perf, usability, reliability).", "#72767b"),
    ("Safety", "Hazard-mitigating requirements (ISO 26262, IEC 61508).", "#cc0000"),
    ("Security", "Confidentiality, integrity, availability, auth.", "#ec7a08"),
    ("Performance", "Timing, throughput, resource usage.", "#3f9c35"),
    ("UI/UX", "User-facing presentation and interaction.", "#9c27b0"),
    ("Regulatory", "Legal or standards-mandated requirements.", "#d9534f"),
    ("Interoperability", "Interfaces with external systems and tools.", "#31708f"),
    ("Maintainability", "Ease of change, diagnosis, upgrade.", "#5bc0de"),
    ("Portability", "Platform, environment, locale independence.", "#777777"),
]

SOURCE_SEEDS = [
    ("Default customer document", "customer_doc", "", ""),
    ("Default technical specification", "tech_spec", "", ""),
    ("Default internal design note", "internal", "", ""),
]

LEVEL_PROFILES = {
    "aspice": [
        ("stakeholder", "Stakeholder requirements", 10,
         "Requirements elicited from end users, customers, or other stakeholders (ASPICE SYS.1)."),
        ("system", "System requirements", 20,
         "System-level requirements derived from stakeholder needs (ASPICE SYS.2)."),
        ("software", "Software requirements", 30,
         "Software-level requirements derived from system requirements (ASPICE SWE.1)."),
        ("component", "Component requirements", 40,
         "Requirements scoped to an individual software component (ASPICE SWE.2)."),
        ("unit", "Unit requirements", 50,
         "Fine-grained requirements at unit/module level (ASPICE SWE.3)."),
    ],
    "iso9001": [
        ("customer_requirement", "Customer requirement", 10,
         "Requirement from a customer or stakeholder (ISO 9001 §8.2)."),
        ("product_requirement", "Product requirement", 20,
         "Requirement derived for the product or service (ISO 9001 §8.3)."),
        ("process_requirement", "Process requirement", 30,
         "Requirement on a process that produces the product (ISO 9001 §4.4)."),
        ("quality_objective", "Quality objective", 40,
         "Measurable target aligned with the quality policy (ISO 9001 §6.2)."),
    ],
    "iec62304": [
        ("user_need", "User need", 10, "Clinical / user need for the medical device."),
        ("software_req", "Software requirement", 20, "Software requirement (IEC 62304 §5.2)."),
        ("arch_req", "Architectural requirement", 30, "Architecture-level requirement (IEC 62304 §5.3)."),
        ("detailed_design", "Detailed design requirement", 40, "Detailed design requirement (IEC 62304 §5.4)."),
        ("unit", "Unit requirement", 50, "Software unit requirement (IEC 62304 §5.5)."),
    ],
    "do178c": [
        ("high_level", "High-level requirement", 10, "High-level software requirement (DO-178C §5.1)."),
        ("low_level", "Low-level requirement", 20, "Low-level software requirement (DO-178C §5.2)."),
        ("source_code", "Source code requirement", 30, "Requirement pinned to source-code evidence (DO-178C §5.3)."),
    ],
    "generic": [
        ("requirement", "Requirement", 10, "Generic requirement level — no decomposition enforced."),
    ],
}


def seed_catalog(apps, schema_editor):
    RequirementCategory = apps.get_model("tcms_requirements", "RequirementCategory")
    RequirementSource = apps.get_model("tcms_requirements", "RequirementSource")
    RequirementLevel = apps.get_model("tcms_requirements", "RequirementLevel")

    for name, description, color in CATEGORY_SEEDS:
        RequirementCategory.objects.update_or_create(
            name=name,
            defaults={"description": description, "color": color},
        )

    for name, source_type, reference, version in SOURCE_SEEDS:
        RequirementSource.objects.update_or_create(
            name=name,
            version=version,
            defaults={
                "source_type": source_type,
                "reference": reference,
            },
        )

    profile_key = getattr(settings, "REQUIREMENTS_LEVEL_PROFILE", "aspice")
    rows = LEVEL_PROFILES.get(profile_key, LEVEL_PROFILES["aspice"])
    for code, name, order, description in rows:
        RequirementLevel.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "order": order,
                "description": description,
                "is_active": True,
            },
        )


def unseed_catalog(apps, schema_editor):
    # Reverse migration just deactivates the seeded rows — never drops them,
    # because user data may reference them.
    RequirementLevel = apps.get_model("tcms_requirements", "RequirementLevel")
    seeded_codes = {code for rows in LEVEL_PROFILES.values() for (code, *_rest) in rows}
    RequirementLevel.objects.filter(code__in=seeded_codes).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [("tcms_requirements", "0001_initial")]

    operations = [migrations.RunPython(seed_catalog, reverse_code=unseed_catalog)]
