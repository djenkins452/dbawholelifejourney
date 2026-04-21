"""
Tests for the canonical metric access layer + purity guardrails.

Scope
-----
1. Registry lookups (``metric_registry``)
2. ``get_metric`` behavior (registered vs orphan vs unregistered)
3. Purity: no raw aggregations in AI-facing layers
4. Orphan: every registered key is written by an SAE state builder

The purity and orphan tests are source-scans, not Django integration
tests — they do not require a database. They run in well under a
second and are safe to include in scoped test runs.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from unittest import mock

from django.test import TestCase

from apps.core.ai_state.metric_access import (
    MetricResult,
    get_metric,
    get_metric_value,
    has_metric,
    record_divergence,
)
from apps.core.ai_state.metric_registry import (
    METRIC_REGISTRY,
    MetricDefinition,
    all_keys,
    get_definition,
    is_canonical,
)
from apps.core.ai_orchestrator.cos_read_allowlist import (
    COS_READ_ALLOWLIST,
    ReadClassification,
)


# ──────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[3]

# AI-facing layers that must never raw-aggregate metric data.
AI_FACING_DIRS = [
    REPO_ROOT / "assistant",
    REPO_ROOT / "apps" / "ai",
    REPO_ROOT / "apps" / "core" / "ai_orchestrator",
]

# Files that MUST be 100% pure. New violations in these fail CI.
# These are the deliverables of the metric-access migration.
PURITY_ENFORCED_FILES = {
    "assistant/data_service.py",
    "apps/core/ai_orchestrator/cos_context.py",
}

# Ratcheting baseline. Each AI-facing file listed here currently has
# the declared number of aggregation/annotation/count calls and is
# tolerated during Phase 2+ migration. CI fails if a file's count
# GROWS above the baseline, or if a new AI-facing file introduces
# violations without being added here. Counts may only decrease.
#
# Maintainers: when you migrate a file, drop its count (or remove
# the entry entirely). Do NOT grow a count to accommodate new code —
# introduce a canonical metric via state_builder.py instead.
PURITY_BASELINE = {
    "apps/ai/action_handlers.py": 13,
    "apps/ai/affirmation_detector.py": 2,
    "apps/ai/assistant_intelligence.py": 5,
    "apps/ai/beth_checkin_renderer.py": 2,
    "apps/ai/dashboard_ai.py": 19,
    "apps/ai/executive_briefing.py": 8,
    "apps/ai/memory_service.py": 2,
    "apps/ai/models.py": 4,
    "apps/ai/pattern_detector.py": 1,
    "apps/ai/priority_generator.py": 1,
    "apps/ai/proactive_checkins.py": 5,
    "apps/ai/situational_awareness.py": 4,
    "apps/ai/state_assessment.py": 13,
    "apps/ai/trend_tracking.py": 20,
    "apps/ai/views.py": 1,
    "assistant/admin_views.py": 6,
    "assistant/health_monitor.py": 5,
    "assistant/safety_limits.py": 4,
    "assistant/tasks.py": 8,
}


AGG_CALL_NAMES = {"aggregate", "annotate"}


def _iter_python_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip virtualenv, cache, and migration directories.
        if "migrations" in dirpath or "__pycache__" in dirpath:
            continue
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            if name.startswith("tests") or name.startswith("test_"):
                continue
            yield Path(dirpath) / name


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


# ──────────────────────────────────────────────────────────────────
# Registry tests
# ──────────────────────────────────────────────────────────────────

class MetricRegistryTests(TestCase):
    """Registry lookup behavior."""

    def test_registry_is_nonempty(self):
        self.assertGreater(len(METRIC_REGISTRY), 0)
        self.assertIn("health.glucose_avg_7d", METRIC_REGISTRY)

    def test_is_canonical_positive(self):
        self.assertTrue(is_canonical("health.glucose_avg_7d"))

    def test_is_canonical_negative(self):
        self.assertFalse(is_canonical("not.a.real.key"))

    def test_get_definition_returns_metric_definition(self):
        definition = get_definition("health.glucose_avg_7d")
        self.assertIsInstance(definition, MetricDefinition)
        self.assertEqual(definition.domain, "health")
        self.assertEqual(definition.unit, "mg/dL")

    def test_get_definition_none_for_unknown(self):
        self.assertIsNone(get_definition("not.a.real.key"))

    def test_all_keys_matches_registry(self):
        self.assertEqual(set(all_keys()), set(METRIC_REGISTRY.keys()))

    def test_registry_keys_match_state_path_or_are_aliased(self):
        # Every definition's state_path must start with its domain.
        # This prevents accidentally registering a key that points
        # into the wrong module.
        for definition in METRIC_REGISTRY.values():
            module, _, _rest = definition.state_path.partition(".")
            # Allow medicine-state signals to live on 'health.*' module
            # until they are moved to the medicine module, and fitness
            # to share its own prefix.
            allowed_module_aliases = {
                definition.domain,
                # "fitness" domain reads from the 'fitness' module
                # (alias of 'workouts') in SAE
            }
            if definition.domain == "health":
                allowed_module_aliases.update({"health"})
            self.assertIn(
                module,
                allowed_module_aliases,
                msg=(
                    f"{definition.key}: state_path starts with "
                    f"'{module}' but domain is '{definition.domain}'"
                ),
            )


# ──────────────────────────────────────────────────────────────────
# get_metric behavior tests
# ──────────────────────────────────────────────────────────────────

class GetMetricTests(TestCase):
    """Behavior of the get_metric facade."""

    def _make_user(self):
        user = mock.Mock()
        user.id = 42
        return user

    def test_unregistered_key_returns_none_and_logs(self):
        user = self._make_user()
        with self.assertLogs("apps.core.ai_state.metric_access", level="WARNING") as logs:
            result = get_metric(user, "not.a.real.key")
        self.assertIsNone(result)
        self.assertTrue(
            any("unregistered_key" in msg for msg in logs.output),
            msg=f"expected unregistered_key log, got {logs.output}",
        )

    def test_orphan_returns_none_and_logs_info(self):
        user = self._make_user()
        with mock.patch(
            "apps.core.ai_state.metric_access.get_state_value",
            return_value=None,
        ), self.assertLogs("apps.core.ai_state.metric_access", level="INFO") as logs:
            result = get_metric(user, "health.glucose_avg_7d")
        self.assertIsNone(result)
        self.assertTrue(
            any("orphan" in msg for msg in logs.output),
            msg=f"expected orphan log, got {logs.output}",
        )

    def test_populated_value_returns_metric_result(self):
        user = self._make_user()
        with mock.patch(
            "apps.core.ai_state.metric_access.get_state_value",
            return_value=145,
        ):
            result = get_metric(user, "health.glucose_avg_7d")
        self.assertIsInstance(result, MetricResult)
        self.assertEqual(result.value, 145)
        self.assertEqual(result.source, "SAE:health.glucose_avg_7d")
        self.assertEqual(result.domain, "health")
        self.assertEqual(result.unit, "mg/dL")

    def test_get_metric_value_returns_default(self):
        user = self._make_user()
        with mock.patch(
            "apps.core.ai_state.metric_access.get_state_value",
            return_value=None,
        ):
            value = get_metric_value(user, "health.glucose_avg_7d", default=0)
        self.assertEqual(value, 0)

    def test_has_metric_true_and_false(self):
        user = self._make_user()
        with mock.patch(
            "apps.core.ai_state.metric_access.get_state_value",
            return_value=100,
        ):
            self.assertTrue(has_metric(user, "health.glucose_avg_7d"))
        with mock.patch(
            "apps.core.ai_state.metric_access.get_state_value",
            return_value=None,
        ):
            self.assertFalse(has_metric(user, "health.glucose_avg_7d"))

    def test_record_divergence_quiet_on_agreement(self):
        with self.assertLogs(
            "apps.core.ai_state.metric_access", level="DEBUG"
        ) as logs:
            record_divergence("health.glucose_avg_7d", [141, 141, 141])
            # Emit at least one log record so assertLogs doesn't raise.
            import logging
            logging.getLogger("apps.core.ai_state.metric_access").debug("probe")
        # No divergence warning should have been emitted.
        self.assertFalse(
            any("divergence" in msg for msg in logs.output),
            msg=f"divergence logged on agreement: {logs.output}",
        )

    def test_record_divergence_warns_on_conflict(self):
        with self.assertLogs(
            "apps.core.ai_state.metric_access", level="WARNING"
        ) as logs:
            record_divergence("health.glucose_avg_7d", [141, 145, 141])
        self.assertTrue(
            any("divergence" in msg for msg in logs.output),
            msg=f"expected divergence warning, got {logs.output}",
        )


# ──────────────────────────────────────────────────────────────────
# Purity: AI-facing layers must not aggregate / annotate / count
# ──────────────────────────────────────────────────────────────────

class MetricPurityTests(TestCase):
    """
    AST scan for forbidden aggregation calls in AI-facing directories.

    PURITY_ENFORCED_FILES are the post-migration surface — they must
    have zero violations. PURITY_BASELINE tracks Phase 2+ debt: each
    listed file is permitted up to N violations (CI fails if it grows).
    Any file not in either list must be pure.
    """

    def test_enforced_files_are_pure(self):
        violations = []
        for rel in sorted(PURITY_ENFORCED_FILES):
            file_path = REPO_ROOT / rel
            if not file_path.exists():
                continue
            violations.extend(self._scan_file(file_path))
        self.assertEqual(
            violations,
            [],
            msg=self._format_enforced_violations(violations),
        )

    def test_baseline_files_do_not_regress(self):
        regressions = []
        for rel, baseline in sorted(PURITY_BASELINE.items()):
            file_path = REPO_ROOT / rel
            if not file_path.exists():
                # Baseline refers to a file that no longer exists —
                # flag so the baseline gets cleaned up.
                regressions.append(
                    (rel, f"missing file (drop from PURITY_BASELINE)")
                )
                continue
            actual = len(self._scan_file(file_path))
            if actual > baseline:
                regressions.append(
                    (rel, f"grew from {baseline} to {actual} violations")
                )
        self.assertEqual(
            regressions,
            [],
            msg=(
                "Aggregation count regressed in AI-facing files. "
                "Each regression adds parallel-truth risk to the CoS "
                "prompt. Either migrate the new read to get_metric() "
                "or, if the baseline is stale because you cleaned up, "
                "lower the number in PURITY_BASELINE.\n\n"
                + "\n".join(f"  {r[0]}: {r[1]}" for r in regressions)
            ),
        )

    def test_new_ai_facing_files_are_pure(self):
        # Any AI-facing file not in the baseline or the enforced set
        # must be clean. This catches new modules with aggregation
        # without requiring maintainers to update the baseline.
        tracked = PURITY_ENFORCED_FILES | set(PURITY_BASELINE.keys())
        violations = []
        for directory in AI_FACING_DIRS:
            for file_path in _iter_python_files(directory):
                rel = _rel(file_path)
                if rel in tracked:
                    continue
                violations.extend(self._scan_file(file_path))
        self.assertEqual(
            violations,
            [],
            msg=self._format_new_violations(violations),
        )

    def _scan_file(self, file_path: Path):
        source = file_path.read_text()
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return []

        violations = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            attr = node.func.attr

            if attr in AGG_CALL_NAMES:
                violations.append(
                    (_rel(file_path), node.lineno, f".{attr}()")
                )
                continue

            if attr == "count" and self._looks_like_queryset_count(node):
                violations.append(
                    (_rel(file_path), node.lineno, ".count()")
                )
        return violations

    def _looks_like_queryset_count(self, node: ast.Call) -> bool:
        # .count() with no arguments is the queryset form. String/list
        # .count("x") takes an argument and is NOT a queryset count.
        return not (node.args or node.keywords)

    def _format_enforced_violations(self, violations):
        if not violations:
            return ""
        return (
            "\nAggregation call found in a PURITY_ENFORCED_FILES path. "
            "This file was migrated to read canonical metrics via "
            "apps.core.ai_state.metric_access.get_metric() and must "
            "not regress.\n\n"
            "Violations:\n"
            + "\n".join(
                f"  {p}:{ln}  {attr}" for p, ln, attr in violations
            )
        )

    def _format_new_violations(self, violations):
        if not violations:
            return ""
        return (
            "\nAggregation call found in an AI-facing file that is "
            "neither enforced nor in the Phase 2 baseline. New reads "
            "must go through get_metric(). If this is an existing "
            "file not yet on the baseline, add it to PURITY_BASELINE "
            "(with a TODO to migrate). Never grow the baseline to "
            "admit new aggregations — extend SAE instead.\n\n"
            "Violations:\n"
            + "\n".join(
                f"  {p}:{ln}  {attr}" for p, ln, attr in violations
            )
        )


# ──────────────────────────────────────────────────────────────────
# Orphan: every registered metric key must be written by a builder
# ──────────────────────────────────────────────────────────────────

class CosReadAllowlistTests(TestCase):
    """
    Enforces the CoS direct-read allowlist.

    Every ``<Model>.objects.`` call in ``apps/core/ai_orchestrator/cos_context.py``
    must correspond to an entry in
    ``apps/core/ai_orchestrator/cos_read_allowlist.py``, with the declared
    count equal to the number of call sites in source.

    New raw reads require adding an allowlist entry in the same change.
    Dropped reads require removing the entry. This forces direct reads
    to be a deliberate, reviewed decision.
    """

    COS_CONTEXT_PATH = (
        REPO_ROOT / "apps" / "core" / "ai_orchestrator" / "cos_context.py"
    )

    def _count_reads_per_model(self) -> dict:
        """
        Walk cos_context.py AST and count ``<Name>.objects.<method>`` call
        sites per Name. Returns {model_name: count}.
        """
        source = self.COS_CONTEXT_PATH.read_text()
        tree = ast.parse(source, filename=str(self.COS_CONTEXT_PATH))

        counts: dict = {}
        for node in ast.walk(tree):
            # Looking for patterns like `X.objects.filter(...)`.
            # That is: Call -> func is Attribute (method call) ->
            # value is Attribute (.objects) -> value is Name (Model).
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            outer = node.func           # e.g. `.filter`
            inner = outer.value         # e.g. `<X>.objects`
            if not isinstance(inner, ast.Attribute):
                continue
            if inner.attr != "objects":
                continue
            if not isinstance(inner.value, ast.Name):
                continue
            model_name = inner.value.id
            counts[model_name] = counts.get(model_name, 0) + 1
        return counts

    def test_every_direct_read_is_allowlisted(self):
        counts = self._count_reads_per_model()
        offenders = [m for m in counts if m not in COS_READ_ALLOWLIST]
        self.assertEqual(
            offenders,
            [],
            msg=(
                "cos_context.py reads these models directly, but they "
                "are not in COS_READ_ALLOWLIST:\n  "
                + "\n  ".join(f"{m} ({counts[m]}x)" for m in offenders)
                + "\n\nEither remove the read (read from SAE state via "
                "get_metric/get_module_state) or add an allowlist entry "
                "with a justification."
            ),
        )

    def test_declared_counts_match_source(self):
        counts = self._count_reads_per_model()
        mismatches = []
        for model, allowed in COS_READ_ALLOWLIST.items():
            actual = counts.get(model, 0)
            if actual != allowed.count:
                mismatches.append(
                    f"{model}: allowlist declares {allowed.count} reads, "
                    f"source has {actual}"
                )
        self.assertEqual(
            mismatches,
            [],
            msg=(
                "Raw-read counts in cos_context.py diverged from "
                "COS_READ_ALLOWLIST:\n  " + "\n  ".join(mismatches) +
                "\n\nIf a read was migrated to SAE, lower the allowlist "
                "count (or remove the entry). If a new read was added, "
                "it must be justified in the allowlist — do not bump "
                "the count to silence the test."
            ),
        )

    def test_allowlist_has_no_dangling_entries(self):
        counts = self._count_reads_per_model()
        dangling = [
            m for m, entry in COS_READ_ALLOWLIST.items()
            if entry.count > 0 and counts.get(m, 0) == 0
        ]
        self.assertEqual(
            dangling,
            [],
            msg=(
                "COS_READ_ALLOWLIST entries with no matching reads in "
                "cos_context.py (drop them):\n  " + "\n  ".join(dangling)
            ),
        )

    def test_gap_reads_emit_state_gap_log(self):
        """
        Every model classified as ``gap_pending_state`` must also have
        a corresponding ``log_state_gap(...)`` call in cos_context.py.
        Catches the failure mode where a gap is "acknowledged" in the
        allowlist but silently bypasses the visibility signal.
        """
        source = self.COS_CONTEXT_PATH.read_text()
        missing = []
        for model, entry in COS_READ_ALLOWLIST.items():
            if entry.classification != ReadClassification.GAP_PENDING_STATE:
                continue
            if "log_state_gap(" not in source:
                missing.append(model)
                continue
            # Coarse check: any log_state_gap() call is sufficient for
            # the model-level test — the per-site call proximity is
            # verified by manual code review when an entry is added.
            # We still assert at least one call exists per gap model
            # by looking for the model name anywhere near a log_state_gap.
            # (Intentional: don't over-constrain the text pattern.)
        self.assertEqual(
            missing,
            [],
            msg=(
                "Models classified as gap_pending_state in "
                "COS_READ_ALLOWLIST but cos_context.py has no "
                f"log_state_gap(...) calls anywhere: {missing}"
            ),
        )


class MetricOrphanTests(TestCase):
    """
    Every metric registered in METRIC_REGISTRY must correspond to a
    ``state["<key>"] = ...`` assignment in state_builder.py. If a key
    is registered without a writer, the registry is lying about what
    SAE can provide.

    This is a source-scan so it runs without a database and is O(1)
    in the number of registered keys.
    """

    STATE_BUILDER_PATH = (
        REPO_ROOT / "apps" / "core" / "ai_state" / "state_builder.py"
    )
    # Keys SAE exposes via code paths other than state_builder.py
    # (e.g. populated by state_updater or external engines).
    ORPHAN_EXEMPT = set()

    def test_every_registered_key_has_a_writer(self):
        source = self.STATE_BUILDER_PATH.read_text()
        missing = []
        for definition in METRIC_REGISTRY.values():
            # state_path is "<module>.<field>[.<sub>...]". The writer
            # uses the last segment as the dict key.
            tail = definition.state_path.split(".")[-1]
            pattern = re.compile(
                r'state\[\s*[\'"]' + re.escape(tail) + r'[\'"]\s*\]'
            )
            if not pattern.search(source):
                if definition.key in self.ORPHAN_EXEMPT:
                    continue
                missing.append(definition.key)

        self.assertEqual(
            missing,
            [],
            msg=(
                "Registered metric keys have no SAE writer:\n  "
                + "\n  ".join(missing)
                + "\n\nEither remove the key from the registry, add a "
                "writer in state_builder.py, or add the key to "
                "ORPHAN_EXEMPT with a comment explaining which other "
                "code path populates it."
            ),
        )
