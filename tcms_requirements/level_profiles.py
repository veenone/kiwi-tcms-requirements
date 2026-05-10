"""Built-in RequirementLevel profiles — single source of truth.

Both the seed migration (0002_seed_catalog.py) and the admin profile-switcher
import from here so adding a new profile only needs one edit. Each profile
is a list of ``(code, name, order, description)`` tuples.
"""

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
        ("user_need", "User need", 10,
         "Clinical / user need for the medical device."),
        ("software_req", "Software requirement", 20,
         "Software requirement (IEC 62304 §5.2)."),
        ("arch_req", "Architectural requirement", 30,
         "Architecture-level requirement (IEC 62304 §5.3)."),
        ("detailed_design", "Detailed design requirement", 40,
         "Detailed design requirement (IEC 62304 §5.4)."),
        ("unit", "Unit requirement", 50,
         "Software unit requirement (IEC 62304 §5.5)."),
    ],
    "do178c": [
        ("high_level", "High-level requirement", 10,
         "High-level software requirement (DO-178C §5.1)."),
        ("low_level", "Low-level requirement", 20,
         "Low-level software requirement (DO-178C §5.2)."),
        ("source_code", "Source code requirement", 30,
         "Requirement pinned to source-code evidence (DO-178C §5.3)."),
    ],
    "generic": [
        ("requirement", "Requirement", 10,
         "Generic requirement level — no decomposition enforced."),
    ],
}

PROFILE_DISPLAY = {
    "aspice": "ASPICE / ISO 26262",
    "iso9001": "ISO 9001 / ISO 13485",
    "iec62304": "IEC 62304 (medical software)",
    "do178c": "DO-178C (avionics)",
    "generic": "Generic (single level)",
}


def detect_active_profile(RequirementLevel) -> str:
    """Best-effort guess of the profile currently in the DB.

    Compares active level codes against each profile's codes. Returns the
    first profile whose codes are an exact match, or ``"custom"`` if no
    profile fits — which means the operator has hand-edited levels.
    """
    active = set(
        RequirementLevel.objects.filter(is_active=True).values_list("code", flat=True)
    )
    if not active:
        return "none"
    for key, rows in LEVEL_PROFILES.items():
        if active == {code for (code, *_rest) in rows}:
            return key
    return "custom"
