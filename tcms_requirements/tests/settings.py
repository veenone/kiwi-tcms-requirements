"""Minimal Django settings for running plugin unit tests in isolation.

These tests don't talk to the Kiwi TCMS app — they exercise pure Python
helpers (state_machine, exports/jira_csv_export). Only enough settings
to satisfy Django's import-time checks.
"""
SECRET_KEY = "tcms-requirements-unit-tests"
DEBUG = False
USE_TZ = True
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
