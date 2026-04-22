---
paths:
  - "tcms_requirements/views.py"
  - "tcms_requirements/forms.py"
  - "tcms_requirements/rpc.py"
  - "tcms_requirements/signals.py"
  - "tcms_requirements/integrations/**"
  - "tcms_requirements/imports/**"
---

# Error Handling

- Use typed exceptions — `state_machine.StateTransitionError`, Django's `ValidationError`, `PermissionDenied`. Don't raise bare `Exception`.
- Never swallow errors silently. Log via `logging.getLogger("tcms_requirements")` with added context about the operation.
- Status transition rules live in `state_machine.validate_transition`. Both form validation and programmatic saves should call it — do not duplicate the rules.
- HTTP error responses: return a Django `HttpResponseBadRequest` / 404 / 403 with a short, non-technical message. Never expose stack traces, internal paths, or raw database errors to the user.
- JIRA / wiki / external-service calls run in daemon threads with try/except that logs a one-line warning and drops — see the pattern in `tcms_review.signals._fire_wiki_sync` and `_safe_mailto`. External failures must never block the request.
- Retry transient errors (network timeouts, rate limits) with exponential backoff. Fail fast on validation and auth errors — don't retry.
- Signal handlers (`tcms_requirements/signals.py`) must be defensive — any raise there will abort the user's save. Wrap risky operations in try/except and log.
- CSV import collects per-row errors and surfaces all of them at once — do not short-circuit on first failure.
- Never `fail_silently=False` on `send_mail` inside a thread — see tcms_review v0.7.4 for the lesson learned (SMTP tracebacks spammed the log).
