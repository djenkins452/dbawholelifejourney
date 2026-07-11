# ==============================================================================
# CI CONTRACT — daily task completion state has ONE producer: Execution Truth.
# Fails the build if any surface computes "completed today" from an independent
# query instead of reading Execution Truth's reconciled bucket.
# ==============================================================================
"""
Completion single-source contract.

The reported trust failure ("completed AND overdue for the same task") happened because
`completed today` was produced by a SECOND pipeline (`TaskQueries.completed_on` → SAE
`state_builder`), unreconciled with overdue. Execution Truth
(`build_today_execution`/`build_execution_state`) is now the single producer of daily task
state — completed/overdue/pending/due — reconciled so a task lands in exactly one bucket.

`TaskQueries.completed_on` may be CALLED only inside the execution package (which owns the
single reconciled producer) and the query layer itself. Any other module that calls it is
introducing a competing completion source — the exact class we are eliminating.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

_ROOT = Path(settings.BASE_DIR)
_APPS = _ROOT / "apps"

# Only these may call TaskQueries.completed_on: the single-producer package + the query layer.
_ALLOWED = (
    "apps/core/execution/",
    "apps/life/services/task_queries.py",
)

_TARGET = "TaskQueries.completed_on("


def _rel(p):
    return str(p.relative_to(_ROOT))


def _source_files():
    for p in _APPS.rglob("*.py"):
        s = _rel(p)
        if "/migrations/" in s or "/tests/" in s or "__pycache__" in s:
            continue
        if p.name.startswith("test_"):
            continue
        yield p


class CompletionSingleSourceContractTests(SimpleTestCase):

    def test_taskqueries_completed_on_only_in_execution_truth(self):
        violations = []
        for p in _source_files():
            rel = _rel(p)
            if any(rel.startswith(a) or rel == a for a in _ALLOWED):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            # Ignore comment lines; catch real call sites only.
            for i, line in enumerate(text.splitlines(), 1):
                if _TARGET in line and not line.lstrip().startswith("#"):
                    violations.append(f"{rel}:{i}")
        self.assertEqual(
            violations, [],
            "These surfaces compute completed-today from an independent query instead of "
            "reading Execution Truth's reconciled `completed_today` bucket "
            "(build_execution_state). Route them through Execution Truth:\n  "
            + "\n  ".join(violations),
        )

    def test_execution_truth_produces_the_completed_bucket(self):
        """The single producer must actually expose the reconciled completed bucket."""
        import inspect

        from apps.core.execution import execution_state
        src = inspect.getsource(execution_state.build_execution_state)
        self.assertIn("completed_today", src,
                      "build_execution_state must expose the reconciled completed_today bucket")
