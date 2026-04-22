---
alwaysApply: true
---

# Testing

- Write tests that verify behaviour, not implementation details.
- Run the specific test module after changes, not the full suite — faster feedback. Example:
  `PYTHONPATH=. DJANGO_SETTINGS_MODULE=tcms_requirements.tests.settings python -m unittest tcms_requirements.tests.test_exports`
- If a test is flaky, fix or delete it. Never retry to make it pass.
- Prefer real implementations over mocks. Only mock at system boundaries (network, filesystem, clock, Kiwi core models when the test runs standalone).
- One assertion per test. If the name needs "and", split it.
- Test names describe behaviour: `test_terminal_requires_change_reason`, not `test_1`.
- Arrange-Act-Assert structure. No logic (`if`/`for`) in tests.
- Never assert on internal state without also asserting on observable output.

## Framework

- Standard library `unittest` — the plugin doesn't require pytest. Tests live in `tcms_requirements/tests/`.
- `tcms_requirements/tests/settings.py` provides a minimal Django settings module so pure-logic tests (state machine, export rendering) run without a live Kiwi install.
- DB-touching tests belong in a future integration suite run against a live Kiwi instance — for v0.1 we only ship unit tests that don't need a migrated DB.

## Django-specific notes

- Integration tests that do touch the DB must use `django.test.TestCase` (wraps each test in a transaction) — never `unittest.TestCase` with DB ops.
- When testing models that use `django-simple-history`, assert against the `.history` manager, not the raw `Historical*` table.
- Never call `send_mail` in tests — monkey-patch or mock it to avoid accidentally hitting a real SMTP server.
