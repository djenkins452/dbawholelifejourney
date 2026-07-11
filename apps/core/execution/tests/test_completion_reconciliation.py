"""Execution Truth is the single producer of daily task state, and it reconciles recurring/
duplicate occurrences so a task can never be both completed AND overdue (the reported bug)."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.execution.decision_authority import current_action, execution_facts
from apps.core.execution.execution_state import build_execution_state
from apps.life.models import Task

User = get_user_model()


class CompletionReconciliationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="rec@example.com", password="x")
        self.today = timezone.localdate()

    def _task(self, title, *, status="pending", due=None, completed=False):
        return Task.objects.create(
            user=self.user, title=title, completion_status=status,
            due_date=due,
            completed_at=timezone.now() if completed else None,
        )

    def _buckets(self):
        st = build_execution_state(self.user)
        completed = [c.get("title") for c in st.get("completed_today", [])]
        overdue = [a.get("title") for a in st.get("overdue_actions", [])]
        return completed, overdue

    # 1 — completed-today task appears only in completed.
    def test_completed_today_only_in_completed(self):
        self._task("Work on WLJ", status="completed", due=self.today, completed=True)
        completed, overdue = self._buckets()
        self.assertIn("Work on WLJ", completed)
        self.assertNotIn("Work on WLJ", overdue)

    # 2 — overdue task appears only in overdue.
    def test_overdue_only_in_overdue(self):
        self._task("Pay the bill", status="pending", due=self.today - timedelta(days=1))
        completed, overdue = self._buckets()
        self.assertNotIn("Pay the bill", completed)
        self.assertIn("Pay the bill", overdue)

    # 3 & 4 — recurring/duplicate twin (completed + overdue same title) → completed only.
    def test_twin_reconciled_never_both(self):
        # The reported case: one occurrence completed today, a lagging occurrence overdue.
        self._task("Check on Von's House", status="completed", due=self.today, completed=True)
        self._task("Check on Von's House", status="pending",
                   due=self.today - timedelta(days=1))
        completed, overdue = self._buckets()
        self.assertIn("Check on Von's House", completed)
        self.assertNotIn("Check on Von's House", overdue)   # twin dropped
        self.assertEqual(set(completed) & set(overdue), set())  # never both

    # 5 — duplicate titles do not create a FALSE completion claim.
    def test_duplicate_titles_no_false_completion(self):
        # Only the genuinely-completed one is reported completed; the pending dup is not
        # promoted to completed (no fabricated completion), and no contradiction appears.
        self._task("Call mom", status="completed", due=self.today, completed=True)
        self._task("Call mom", status="pending", due=self.today - timedelta(days=1))
        completed, overdue = self._buckets()
        self.assertEqual(completed.count("Call mom"), 1)     # completed because ONE real completion
        self.assertNotIn("Call mom", overdue)
        self.assertEqual(set(completed) & set(overdue), set())

    # 6 — next-action selection is unchanged: completed items are non-actionable.
    def test_next_action_never_selects_completed(self):
        self._task("Already done", status="completed", due=self.today, completed=True)
        self._task("Do this now", status="pending", due=self.today - timedelta(days=1))
        primary = (current_action(self.user) or {}).get("primary_action") or {}
        self.assertNotEqual(primary.get("title"), "Already done")

    # 7 — momentum reflects reconciled completed truth only (count == reconciled bucket).
    def test_completed_count_is_reconciled(self):
        self._task("A", status="completed", due=self.today, completed=True)
        self._task("B", status="completed", due=self.today, completed=True)
        # A duplicate/overdue twin of A must NOT inflate the completed count.
        self._task("A", status="pending", due=self.today - timedelta(days=1))
        st = build_execution_state(self.user)
        self.assertEqual(len(st.get("completed_today", [])), 2)  # A, B — not 3

    # 8 — all consumers derive the same buckets (execution_facts == execution_state).
    def test_consumers_receive_the_same_bucket(self):
        self._task("Shared truth", status="completed", due=self.today, completed=True)
        st = build_execution_state(self.user)
        facts = execution_facts(self.user, state=st)
        state_titles = {c.get("title") for c in st.get("completed_today", [])}
        facts_titles = {c.get("title") for c in facts.get("completed", [])}
        self.assertEqual(state_titles, facts_titles)
        self.assertIn("Shared truth", facts_titles)
