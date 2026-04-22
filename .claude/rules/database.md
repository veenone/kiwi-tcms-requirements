---
paths:
  - "tcms_requirements/migrations/**"
  - "tcms_requirements/models.py"
---

# Database Migrations

- **Never modify an existing migration** — always create a new migration for changes. Existing migrations may have already run in production.
- Every migration must be reversible — implement both up/forward and down/rollback. Data migrations (like `0002_seed_catalog`) must provide `reverse_code`.
- Migration filenames are ordered by leading number — new migrations go at the end.
- Never use raw SQL when Django's migration framework provides a method for the operation.
- Never seed production data in migration files that isn't idempotent — use `update_or_create` (see `0002_seed_catalog.py`).
- Never drop columns or tables without first confirming the data is no longer needed.
- Add indexes in their own migration, not bundled with schema changes — easier to rollback independently.
- Dependencies on Kiwi core apps: pin to a migration that actually exists (e.g. `("management", "0003_squashed")`, NOT `"0001_initial"` — that was squashed away).
- Cross-app FKs to `management.Product`, `management.Version`, `testcases.TestCase`, `AUTH_USER_MODEL` must be declared in the migration's `dependencies`.
- HistoricalRecords (django-simple-history) creates paired `Historical*` tables. When adding a new tracked field, regenerate the historical model CreateModel op by running `makemigrations` on a live Kiwi install — don't try to hand-edit history tables.
- The `RequirementLevel` table is user-editable in admin. Seed migrations use `update_or_create` on `code` so re-running them won't corrupt operator customisations.
