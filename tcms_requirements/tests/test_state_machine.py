"""Tests for Requirement status transition rules.

No DB touched — state_machine is pure logic, so we exercise TransitionContext
directly.
"""
import unittest

from tcms_requirements.state_machine import (
    StateTransitionError,
    TransitionContext,
    validate_transition,
)


def _ctx(**overrides) -> TransitionContext:
    defaults = {
        "current_status": "draft",
        "target_status": "draft",
        "change_reason": "",
        "verification_method": "test",
        "verification_exemption_reason": "",
        "superseded_by_id": None,
    }
    defaults.update(overrides)
    return TransitionContext(**defaults)


class TransitionTests(unittest.TestCase):
    def test_allows_self_transition_without_change_reason(self):
        validate_transition(_ctx(current_status="draft", target_status="draft"))

    def test_rejects_invalid_transition(self):
        with self.assertRaises(StateTransitionError):
            validate_transition(_ctx(current_status="draft", target_status="verified"))

    def test_terminal_requires_change_reason(self):
        with self.assertRaises(StateTransitionError):
            validate_transition(_ctx(current_status="verified", target_status="deprecated"))

        # OK once a reason is supplied.
        validate_transition(
            _ctx(
                current_status="verified",
                target_status="deprecated",
                change_reason="Obsoleted by PROJ-B",
            ),
        )

    def test_superseded_requires_replacement(self):
        with self.assertRaises(StateTransitionError):
            validate_transition(
                _ctx(
                    current_status="verified",
                    target_status="superseded",
                    change_reason="Rolled into SYS-REQ-200",
                ),
            )

        validate_transition(
            _ctx(
                current_status="verified",
                target_status="superseded",
                change_reason="Rolled into SYS-REQ-200",
                superseded_by_id=42,
            ),
        )

    def test_exempted_verification_requires_reason(self):
        with self.assertRaises(StateTransitionError):
            validate_transition(
                _ctx(verification_method="exempted"),
            )

        validate_transition(
            _ctx(
                verification_method="exempted",
                verification_exemption_reason="No functional behaviour — label only.",
            ),
        )


if __name__ == "__main__":
    unittest.main()
