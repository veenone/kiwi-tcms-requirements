"""Status transitions for Requirement.

Enforces:
 - Terminal status (deprecated / superseded) requires change_reason.
 - exempted verification requires verification_exemption_reason.
 - superseded status requires a populated superseded_by FK.

This file is deliberately thin; it's called from Requirement form
validation and from the view layer's save() wrappers. The state names
themselves live on Requirement.STATUS_CHOICES.
"""
from dataclasses import dataclass
from typing import Optional


class StateTransitionError(ValueError):
    """Raised when a requirement update violates a status-transition rule."""


# Explicit adjacency list. Keys are source states, values are the set of
# allowed target states. Self-transitions (no change) are always allowed
# and aren't modelled here — callers skip the check when status is unchanged.
ALLOWED_TRANSITIONS = {
    "draft":       {"in_review", "approved", "deprecated"},
    "in_review":   {"draft", "approved", "deprecated"},
    "approved":    {"implemented", "deprecated", "superseded", "in_review"},
    "implemented": {"verified", "deprecated", "superseded"},
    "verified":    {"deprecated", "superseded"},
    "deprecated":  {"draft"},  # allow reanimation if needed
    "superseded":  set(),      # terminal — cannot transition back
}


@dataclass
class TransitionContext:
    """Inputs to validate_transition — keeps the signature small."""
    current_status: str
    target_status: str
    change_reason: str
    verification_method: str
    verification_exemption_reason: str
    superseded_by_id: Optional[int]


def validate_transition(ctx: TransitionContext) -> None:
    """Raise StateTransitionError if the requested transition is invalid."""
    current = ctx.current_status
    target = ctx.target_status

    if current != target:
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise StateTransitionError(
                f"Invalid status transition: {current!r} → {target!r}. "
                f"Allowed from {current!r}: {sorted(allowed) or '(none)'}."
            )

    if target in {"deprecated", "superseded"} and not ctx.change_reason.strip():
        raise StateTransitionError(
            f"A change_reason is required when status={target!r}."
        )

    if target == "superseded" and not ctx.superseded_by_id:
        raise StateTransitionError(
            "status='superseded' requires superseded_by to point at a replacement requirement."
        )

    if ctx.verification_method == "exempted" and not ctx.verification_exemption_reason.strip():
        raise StateTransitionError(
            "verification_method='exempted' requires a verification_exemption_reason."
        )
