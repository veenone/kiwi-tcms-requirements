"""Tests for CSV / JIRA-CSV / JSON exports.

These tests don't need a live DB; they exercise the pure rendering
functions against lightweight stand-ins that quack like Requirement
instances. The goal is to freeze the JIRA column order + mapping
without requiring the full Django stack to spin up.
"""
import csv
import io
import unittest
from types import SimpleNamespace

from tcms_requirements.exports.jira_csv_export import (
    _jira_columns,
    _labels,
    _priority,
    _row,
    _status,
    write_jira_csv,
)


def _fake_mapping():
    return {
        "issue_type": "Story",
        "priority": {"critical": "Highest", "high": "High", "medium": "Medium", "low": "Low"},
        "status": {"draft": "To Do", "approved": "Done"},
        "custom_fields": {
            "level": "Requirement Level",
            "source_document": "Source Document",
            "parent_requirement": "Parent Requirement",
            "linked_test_cases": "Linked Test Cases",
            "asil": "ASIL",
            "dal": "DAL",
            "iec62304_class": "IEC 62304 Class",
        },
    }


def _fake_requirement(**overrides):
    """Build a SimpleNamespace that matches the attribute surface _row() reads."""
    defaults = SimpleNamespace(
        identifier="SYS-REQ-001",
        title="The system shall do X.",
        description="Long-form description.",
        rationale="We need X because Y.",
        status="approved",
        priority="high",
        jira_issue_key="",
        # FK id flags + objects
        source_id=1,
        source=SimpleNamespace(source_type="srs", name="SRS v1.0"),
        category_id=1,
        category=SimpleNamespace(name="Functional"),
        level_id=1,
        level=SimpleNamespace(name="System"),
        parent_requirement_id=None,
        parent_requirement=None,
        created_by_id=1,
        created_by=SimpleNamespace(username="admin"),
        doc_id="QMS-SRS-042",
        doc_revision="A",
        asil="B",
        dal="",
        iec62304_class="",
        # links: iterable of namespaces with case_id
        case_links=SimpleNamespace(all=lambda: [SimpleNamespace(case_id=42), SimpleNamespace(case_id=43)]),
    )
    for k, v in overrides.items():
        setattr(defaults, k, v)
    return defaults


class JiraCsvExportTests(unittest.TestCase):
    def test_priority_mapped(self):
        mapping = _fake_mapping()
        self.assertEqual(_priority(_fake_requirement(priority="critical"), mapping), "Highest")
        self.assertEqual(_priority(_fake_requirement(priority="low"), mapping), "Low")

    def test_priority_unmapped_falls_back_to_titlecase(self):
        self.assertEqual(
            _priority(_fake_requirement(priority="tbd"), {"priority": {}}),
            "Tbd",
        )

    def test_status_mapped(self):
        mapping = _fake_mapping()
        self.assertEqual(_status(_fake_requirement(status="approved"), mapping), "Done")
        self.assertEqual(_status(_fake_requirement(status="draft"), mapping), "To Do")

    def test_labels_dedupe_and_slugify(self):
        req = _fake_requirement()
        labels = _labels(req).split(";")
        self.assertIn("srs", labels)
        # Slugified from source name "SRS v1.0"
        self.assertIn("SRS-v1.0", labels)
        self.assertIn("Functional", labels)

    def test_row_includes_all_custom_fields(self):
        mapping = _fake_mapping()
        columns = _jira_columns(mapping)
        row = _row(_fake_requirement(), mapping, columns)
        self.assertEqual(row["External Issue ID"], "SYS-REQ-001")
        self.assertEqual(row["Requirement Level"], "System")
        self.assertEqual(row["Source Document"], "QMS-SRS-042 A")
        self.assertEqual(row["Linked Test Cases"], "TC-42, TC-43")
        self.assertEqual(row["ASIL"], "B")
        # Empty DAL/IEC columns still present (column always emitted).
        self.assertEqual(row["DAL"], "")
        self.assertEqual(row["IEC 62304 Class"], "")

    def test_issue_key_round_trips(self):
        req = _fake_requirement(jira_issue_key="PROJ-123")
        columns = _jira_columns(_fake_mapping())
        row = _row(req, _fake_mapping(), columns)
        self.assertEqual(row["Issue Key"], "PROJ-123")

    def test_description_merges_rationale(self):
        req = _fake_requirement(description="D.", rationale="R.")
        columns = _jira_columns(_fake_mapping())
        row = _row(req, _fake_mapping(), columns)
        self.assertIn("h3. Rationale", row["Description"])

    def test_write_csv_emits_header_and_rows(self):
        # Monkey-patch get_jira_export_mapping to return our fixed mapping.
        from tcms_requirements.exports import jira_csv_export as mod

        original = mod.get_jira_export_mapping
        mod.get_jira_export_mapping = _fake_mapping
        try:
            buf = io.StringIO()
            write_jira_csv([_fake_requirement(), _fake_requirement(identifier="SYS-REQ-002")], buf)
            buf.seek(0)
            rows = list(csv.DictReader(buf))
            self.assertEqual(len(rows), 2)
            self.assertIn("Issue Type", rows[0])
            self.assertEqual(rows[0]["Issue Type"], "Story")
        finally:
            mod.get_jira_export_mapping = original


if __name__ == "__main__":
    unittest.main()
