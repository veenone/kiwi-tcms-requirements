---
paths:
  - "tcms_requirements/views.py"
  - "tcms_requirements/forms.py"
  - "tcms_requirements/rpc.py"
  - "tcms_requirements/permissions.py"
  - "tcms_requirements/middleware.py"
  - "tcms_requirements/integrations/**"
  - "tcms_requirements/exports/**"
  - "tcms_requirements/imports/**"
---

# Security

- Validate all user input at the system boundary. Never trust request parameters.
- Use parameterized queries — never concatenate user input into SQL or shell commands.
- Sanitize output to prevent XSS. Django's auto-escape is on; only use `|safe`/`mark_safe` after confirming the source is not user-controlled.
- Authentication tokens (JIRA API tokens, webhook secrets) must live in `JiraIntegrationConfig` or settings — never hardcode in code.
- Never log secrets, tokens, passwords, or PII. The JIRA token in `JiraIntegrationConfig.api_token` must never appear in logs.
- Use constant-time comparison for secrets and tokens (`hmac.compare_digest`).
- Plugin RPC methods must honour Django permissions — check `request.user.has_perm('tcms_requirements.…')` before mutating state.
- Middleware response rewriting: do NOT inject JS that echoes request data without escaping. See `middleware.py::_script_tag` for the safe pattern.
- CSV import: refuse rows whose `external_refs` isn't valid JSON; never `eval` user-provided strings.
- Rate-limit import/export endpoints in production — large CSVs can DoS the server.
