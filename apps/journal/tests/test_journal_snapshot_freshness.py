# ==============================================================================
# File: apps/journal/tests/test_journal_snapshot_freshness.py
# Description: Journal SAE snapshot freshness — the CoS read path must self-heal a
#              stale journal snapshot with the SAME shared guard (ensure_fresh) the
#              dashboard uses, so the Journal page and the Chief of Staff never
#              disagree about the latest entry / period counts.
#              Root cause (2026-07-19): get_domain_state / DomainTruth.state() read
#              the SAE snapshot WITHOUT calling ensure_fresh, so a missed/lagged async
#              refresh left the CoS reporting stale truth while the page self-healed.
# ==============================================================================
from contextlib import contextmanager
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase

from apps.ai.cos_services.domain_state import get_domain_state
from apps.ai.signals import invalidate_insights_on_journal_save
from apps.core.ai_state.state_engine import get_module_state
from apps.core.ai_state.state_updater import update_user_state
from apps.core.truth.domain import get_domain_truth
from apps.journal.models import JournalEntry
from apps.journal.services.journal_queries import JournalQueries

User = get_user_model()


@contextmanager
def _refresh_signal_muted():
    """Simulate a MISSED async SAE refresh (broker down / worker backed up / a
    signal-bypassing write like bulk_create) by disconnecting the journal SAE
    refresh receiver. The snapshot then only becomes current via the read-path
    self-heal — which is exactly the fix under test."""
    post_save.disconnect(invalidate_insights_on_journal_save,
                         sender='journal.JournalEntry')
    try:
        yield
    finally:
        post_save.connect(invalidate_insights_on_journal_save,
                          sender='journal.JournalEntry')


def _entry(user, d, **kw):
    return JournalEntry.objects.create(user=user, title=f"e-{d}",
                                       body_plain="x", entry_date=d, **kw)


class JournalSnapshotSelfHealTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="jfresh@example.com", password="x")

    def setUp(self):
        # Baseline entry + a built snapshot that will go stale.
        self.base = _entry(self.user, date(2026, 7, 1))
        update_user_state(self.user, "journal")

    def _snap_last(self):
        return (get_module_state(self.user, "journal", allow_rebuild=False) or {}).get("last_entry")

    # 1 + 2 — a newer entry the async refresh missed is self-healed on the CoS read,
    # and the rebuilt snapshot reports it as last_entry.
    def test_get_domain_state_selfheals_missed_newer_entry(self):
        with _refresh_signal_muted():
            _entry(self.user, date(2026, 7, 10))
            self.assertEqual(self._snap_last(), "2026-07-01")   # snapshot IS stale
            gds = get_domain_state(self.user, "journal")
        self.assertEqual(gds["state"]["last_entry"], "2026-07-10")  # self-healed

    def test_domaintruth_current_selfheals(self):
        with _refresh_signal_muted():
            _entry(self.user, date(2026, 7, 12))
            cur = get_domain_truth(self.user, "journal").current("last_entry")
        self.assertEqual(getattr(cur, "value", None), "2026-07-12")

    # 3 — editing an entry's date to become the newest updates ordering.
    def test_editing_date_updates_latest(self):
        older = _entry(self.user, date(2026, 7, 5))
        with _refresh_signal_muted():
            older.entry_date = date(2026, 7, 20)
            older.save()
            gds = get_domain_state(self.user, "journal")
        self.assertEqual(gds["state"]["last_entry"], "2026-07-20")

    # 4 — soft-deleting the latest entry makes the prior entry latest.
    def test_soft_delete_latest_promotes_prior(self):
        latest = _entry(self.user, date(2026, 7, 15))
        update_user_state(self.user, "journal")
        self.assertEqual(self._snap_last(), "2026-07-15")
        with _refresh_signal_muted():
            latest.soft_delete()
            gds = get_domain_state(self.user, "journal")
        # prior valid entry (July 1) becomes latest; SoftDeleteManager excludes deleted
        self.assertEqual(gds["state"]["last_entry"], "2026-07-01")

    # 5 — restoring an entry refreshes the snapshot.
    def test_restore_refreshes(self):
        e = _entry(self.user, date(2026, 7, 18))
        e.soft_delete()
        update_user_state(self.user, "journal")
        self.assertEqual(self._snap_last(), "2026-07-01")   # restored one excluded
        with _refresh_signal_muted():
            e.restore()
            gds = get_domain_state(self.user, "journal")
        self.assertEqual(gds["state"]["last_entry"], "2026-07-18")

    # 6 — consistency facts refresh after a write.
    def test_consistency_counts_refresh(self):
        with _refresh_signal_muted():
            _entry(self.user, date.today())
            _entry(self.user, date.today() - timedelta(days=1))
            gds = get_domain_state(self.user, "journal")["state"]
        self.assertEqual(gds["days_since_entry"], 0)
        self.assertGreaterEqual(gds["entries_7d"], 2)
        self.assertGreaterEqual(gds["entries_30d"], 2)
        self.assertGreater(gds["entry_frequency"], 0)

    # 7 — the page producer and the CoS DomainTruth agree on the latest entry.
    def test_page_and_domaintruth_agree(self):
        with _refresh_signal_muted():
            _entry(self.user, date(2026, 7, 14))
            page_latest = JournalQueries.last_entry(self.user).entry_date.isoformat()
            cur = get_domain_truth(self.user, "journal").current("last_entry")
        self.assertEqual(page_latest, getattr(cur, "value", None))


class FreshnessFailureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="jfail@example.com", password="x")
        _entry(cls.user, date(2026, 7, 1))
        update_user_state(cls.user, "journal")

    # 8 — a rebuild failure is observable (logged) and never crashes the read nor
    # silently blocks it; the read still returns the last-known snapshot.
    def test_refresh_failure_is_logged_not_swallowed_silently(self):
        with mock.patch("apps.core.ai_state.state_freshness.ensure_fresh",
                        side_effect=RuntimeError("boom")):
            with self.assertLogs("apps.ai.cos_services.domain_state", level="WARNING") as cm:
                gds = get_domain_state(self.user, "journal")
        self.assertEqual(gds["status"], "ready")            # read still succeeds
        self.assertTrue(any("freshness check failed" in m for m in cm.output))


class NonManualDomainNotRegressedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="jother@example.com", password="x")

    # 9 — a non-manual domain's read still works; ensure_fresh is a no-op for it.
    def test_non_manual_domain_read_unaffected(self):
        from apps.core.ai_state.state_freshness import ensure_fresh
        # goals is not a manual-entry module → ensure_fresh rebuilds nothing.
        self.assertEqual(ensure_fresh(self.user, ["goals"]), set())
        gds = get_domain_state(self.user, "goals")
        self.assertIn(gds["status"], ("ready", "pending", "no_state_source"))
