---
paths:
  - "tcms_requirements/templates/**"
  - "tcms_requirements/**/*.html"
  - "tcms_requirements/static/**"
  - "tcms_requirements/**/*.js"
  - "tcms_requirements/**/*.css"
---

# Frontend (Django templates + jQuery + Bootstrap 3 / PatternFly)

This plugin ships minimal frontend code — Django templates that extend Kiwi's `base.html`, one CSS file, and one injected JS bundle. No React / Vue / Svelte.

## Templates

- All templates extend `base.html` and start with `{% load i18n %}` `{% load static %}` (and `{% load requirements_extras %}` where badges are needed).
- User-facing strings go through `{% trans %}` / `{% blocktrans %}`. Never hardcode translatable text.
- Use `{% url %}` and `{% static %}` — never hand-build paths.
- Auto-escaping is on. Only mark safe (`|safe`, `mark_safe`) after confirming the source is not user-controlled. `templatetags/requirements_extras.py::status_badge` and friends use `escape()` before `mark_safe()`.

## JavaScript

- **Two jQuery instances coexist on Kiwi host pages**: `$` is jQuery 3.6.1 with Bootstrap plugins, `jQuery` is 3.6.0 plain. IIFE wrappers MUST close with `})($)`, otherwise Bootstrap events (`show.bs.modal`, etc.) will not fire. See `static/tcms_requirements/js/inject.js` for the reference pattern.
- JS files **cannot** use Django template tags — no `{% trans %}` inside `.js`. Use plain strings or pass values through `data-*` attributes on the injected `<script>` tag (see `middleware.py::_script_tag` for the `data-current-user-id` pattern).
- Never drop `<script src="cdn...">` into a template. Static JS belongs under `tcms_requirements/static/tcms_requirements/js/` and is served via the middleware-injected bundle or a `{% static %}` tag.
- The injected bundle self-detects pages via `body[id]` and no-ops on unknown pages. When adding detection for a new page, branch inside `$(function() {...})`.

## Accessibility

- Form inputs need an associated `<label>` (Bootstrap's `.control-label`).
- Keep focus visible on interactive elements.
- Status / priority badges use `role="status"` for screen readers.
