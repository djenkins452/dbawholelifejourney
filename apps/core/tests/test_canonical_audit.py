"""
Tests for Canonical Query Audit (Ops Wall 2.0 — Phase 7).

Tests cover:
  - scan_file() pattern detection
  - Allowed path exclusion
  - Comment/string handling
  - Global path exclusion
  - run_audit() compliance scoring
  - Management command output

Project: Whole Life Journey
Path: apps/core/tests/test_canonical_audit.py
"""

import os
import tempfile
import shutil

from django.test import TestCase


class ScanFileTests(TestCase):
    """Test scan_file() pattern detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write_file(self, name, content):
        """Write a test file and return its path relative to tmpdir."""
        filepath = os.path.join(self.tmpdir, name)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(content)
        return name

    def test_detects_objects_filter(self):
        """Should detect Model.objects.filter() calls."""
        from apps.core.canonical_audit import scan_file

        path = self._write_file(
            "apps/dashboard/views.py",
            "from apps.life.models import Task\n"
            "tasks = Task.objects.filter(user=request.user)\n",
        )
        rules = {
            "Task": {
                "domain": "life",
                "canonical_service": "TaskQueries",
                "allowed_paths": ["apps/life/services/"],
                "suggested_usage": "TaskQueries.pending(user)",
            }
        }
        violations = scan_file(path, rules, base_dir=self.tmpdir)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].model, "Task")
        self.assertEqual(violations[0].line, 2)
        self.assertEqual(violations[0].domain, "life")

    def test_detects_objects_get(self):
        """Should detect Model.objects.get() calls."""
        from apps.core.canonical_audit import scan_file

        path = self._write_file(
            "apps/dashboard/views.py",
            "task = Task.objects.get(pk=1)\n",
        )
        rules = {
            "Task": {
                "domain": "life",
                "canonical_service": "TaskQueries",
                "allowed_paths": [],
                "suggested_usage": "TaskQueries.pending(user)",
            }
        }
        violations = scan_file(path, rules, base_dir=self.tmpdir)
        self.assertEqual(len(violations), 1)

    def test_detects_objects_exclude(self):
        """Should detect Model.objects.exclude() calls."""
        from apps.core.canonical_audit import scan_file

        path = self._write_file(
            "apps/dashboard/views.py",
            "qs = Insight.objects.exclude(status='dismissed')\n",
        )
        rules = {
            "Insight": {
                "domain": "intelligence",
                "canonical_service": "ai_insights.services",
                "allowed_paths": [],
                "suggested_usage": "services.get_insights()",
            }
        }
        violations = scan_file(path, rules, base_dir=self.tmpdir)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].model, "Insight")

    def test_skips_allowed_paths(self):
        """Should not flag queries in allowed service files."""
        from apps.core.canonical_audit import scan_file

        path = self._write_file(
            "apps/life/services/task_queries.py",
            "tasks = Task.objects.filter(user=user)\n",
        )
        rules = {
            "Task": {
                "domain": "life",
                "canonical_service": "TaskQueries",
                "allowed_paths": ["apps/life/services/"],
                "suggested_usage": "TaskQueries.pending(user)",
            }
        }
        violations = scan_file(path, rules, base_dir=self.tmpdir)
        self.assertEqual(len(violations), 0)

    def test_skips_migration_files(self):
        """Should not flag queries in migration files."""
        from apps.core.canonical_audit import scan_file

        path = self._write_file(
            "apps/life/migrations/0001_initial.py",
            "Task.objects.filter()\n",
        )
        rules = {
            "Task": {
                "domain": "life",
                "canonical_service": "TaskQueries",
                "allowed_paths": [],
                "suggested_usage": "TaskQueries.pending(user)",
            }
        }
        violations = scan_file(path, rules, base_dir=self.tmpdir)
        self.assertEqual(len(violations), 0)

    def test_skips_test_files(self):
        """Should not flag queries in test files."""
        from apps.core.canonical_audit import scan_file

        path = self._write_file(
            "apps/life/tests/test_views.py",
            "Task.objects.filter()\n",
        )
        rules = {
            "Task": {
                "domain": "life",
                "canonical_service": "TaskQueries",
                "allowed_paths": [],
                "suggested_usage": "TaskQueries.pending(user)",
            }
        }
        violations = scan_file(path, rules, base_dir=self.tmpdir)
        self.assertEqual(len(violations), 0)

    def test_skips_comments(self):
        """Should not flag commented-out queries."""
        from apps.core.canonical_audit import scan_file

        path = self._write_file(
            "apps/dashboard/views.py",
            "# Task.objects.filter(user=user)\n"
            "  # old: Task.objects.get(pk=1)\n",
        )
        rules = {
            "Task": {
                "domain": "life",
                "canonical_service": "TaskQueries",
                "allowed_paths": [],
                "suggested_usage": "TaskQueries.pending(user)",
            }
        }
        violations = scan_file(path, rules, base_dir=self.tmpdir)
        self.assertEqual(len(violations), 0)

    def test_multiple_violations_in_one_file(self):
        """Should find multiple violations in a single file."""
        from apps.core.canonical_audit import scan_file

        path = self._write_file(
            "apps/dashboard/views.py",
            "a = Task.objects.filter(user=u)\n"
            "b = Task.objects.get(pk=1)\n"
            "c = Insight.objects.all()\n",
        )
        rules = {
            "Task": {
                "domain": "life",
                "canonical_service": "TaskQueries",
                "allowed_paths": [],
                "suggested_usage": "TaskQueries.pending(user)",
            },
            "Insight": {
                "domain": "intelligence",
                "canonical_service": "services",
                "allowed_paths": [],
                "suggested_usage": "services.get()",
            },
        }
        violations = scan_file(path, rules, base_dir=self.tmpdir)
        self.assertEqual(len(violations), 3)

    def test_no_false_positive_on_similar_names(self):
        """Should not flag TaskLog.objects when rule is for Task."""
        from apps.core.canonical_audit import scan_file

        path = self._write_file(
            "apps/dashboard/views.py",
            "logs = TaskLog.objects.filter(user=u)\n",
        )
        rules = {
            "Task": {
                "domain": "life",
                "canonical_service": "TaskQueries",
                "allowed_paths": [],
                "suggested_usage": "TaskQueries.pending(user)",
            }
        }
        violations = scan_file(path, rules, base_dir=self.tmpdir)
        self.assertEqual(len(violations), 0)


class RunAuditTests(TestCase):
    """Test run_audit() aggregation and compliance scoring."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write_file(self, rel_path, content):
        filepath = os.path.join(self.tmpdir, rel_path)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(content)

    def test_empty_directory_returns_100(self):
        """Empty directory should return 100% compliance."""
        from apps.core.canonical_audit import run_audit

        result = run_audit(self.tmpdir, {"Task": {
            "domain": "life", "canonical_service": "T",
            "allowed_paths": [], "suggested_usage": "T.x()",
        }})
        self.assertEqual(result.compliance_score, 100.0)
        self.assertEqual(len(result.violations), 0)

    def test_clean_files_return_100(self):
        """Files without violations should return 100%."""
        from apps.core.canonical_audit import run_audit

        self._write_file("apps/views.py", "from apps.life import TaskQueries\ntasks = TaskQueries.pending(user)\n")
        result = run_audit(self.tmpdir, {"Task": {
            "domain": "life", "canonical_service": "T",
            "allowed_paths": [], "suggested_usage": "T.x()",
        }})
        self.assertEqual(result.compliance_score, 100.0)

    def test_violation_reduces_score(self):
        """Violations should reduce compliance score below 100%."""
        from apps.core.canonical_audit import run_audit

        self._write_file("apps/bad.py", "Task.objects.filter()\n")
        self._write_file("apps/good.py", "pass\n")
        result = run_audit(self.tmpdir, {"Task": {
            "domain": "life", "canonical_service": "T",
            "allowed_paths": [], "suggested_usage": "T.x()",
        }})
        self.assertEqual(len(result.violations), 1)
        self.assertLess(result.compliance_score, 100.0)
        self.assertGreater(result.compliance_score, 0.0)

    def test_excludes_pycache_directories(self):
        """Should skip __pycache__ directories entirely."""
        from apps.core.canonical_audit import run_audit

        self._write_file("apps/__pycache__/bad.py", "Task.objects.filter()\n")
        self._write_file("apps/good.py", "pass\n")
        result = run_audit(self.tmpdir, {"Task": {
            "domain": "life", "canonical_service": "T",
            "allowed_paths": [], "suggested_usage": "T.x()",
        }})
        self.assertEqual(len(result.violations), 0)

    def test_result_structure(self):
        """AuditResult should have all expected attributes."""
        from apps.core.canonical_audit import AuditResult

        result = AuditResult(files_scanned=10, models_audited=5)
        self.assertEqual(result.files_scanned, 10)
        self.assertEqual(result.models_audited, 5)
        self.assertEqual(result.violations, [])
        self.assertEqual(result.compliance_score, 100.0)


class ManagementCommandTests(TestCase):
    """Test the management command runs without errors."""

    def test_command_runs(self):
        """Command should execute without crashing."""
        from io import StringIO
        from django.core.management import call_command

        out = StringIO()
        # Command will exit(1) if violations found, so catch SystemExit
        try:
            call_command("audit_canonical_queries", stdout=out)
        except SystemExit:
            pass  # Expected if violations exist

        output = out.getvalue()
        self.assertIn("CANONICAL QUERY AUDIT", output)
        self.assertIn("Files scanned:", output)

    def test_json_output(self):
        """JSON mode should produce valid JSON."""
        import json
        from io import StringIO
        from django.core.management import call_command

        out = StringIO()
        try:
            call_command("audit_canonical_queries", json=True, stdout=out)
        except SystemExit:
            pass

        output = out.getvalue()
        data = json.loads(output)
        self.assertIn("files_scanned", data)
        self.assertIn("compliance_score", data)
        self.assertIn("violations", data)
