"""
Truth Presentation Contract — Dimension 2 (Lifecycle Truth) enforcement.

Governing doc: docs/WLJ_VISUAL_TRUTH_CONTRACT.md (the expanded Truth Presentation
Contract). Dimension 1 (Visual) is enforced by test_visual_truth_contract.py; this
suite enforces Dimension 2 (Lifecycle): a customer-facing status must represent the
highest VERIFIED deterministic stage — never an optimistic future stage.

These tests pin the PRODUCT RULE in apps/core/truth/lifecycle.py so a future change
cannot silently let "complete" be claimed from a transmission/initiation event, or
let partial/stale be rounded up to success.
"""

from django.test import SimpleTestCase

from apps.core.truth import freshness
from apps.core.truth import lifecycle as lc


class CompletionClaimRuleTests(SimpleTestCase):
    """`may_claim_complete` is the single gate on any "done / up to date" claim."""

    def test_completion_requires_current_stage(self):
        # Nothing below CURRENT may claim completion.
        for stage in (lc.INITIATED, lc.RECEIVED, lc.PERSISTED, lc.DERIVED):
            self.assertFalse(
                lc.may_claim_complete(stage),
                f"{stage} must NOT be allowed to claim completion",
            )
        self.assertTrue(lc.may_claim_complete(lc.CURRENT))

    def test_blocking_qualifiers_forbid_completion_even_at_current(self):
        # Partial / failed / stale can never look complete — the core class we kill.
        for q in (lc.PARTIAL, lc.FAILED, lc.STALE):
            self.assertFalse(
                lc.may_claim_complete(lc.CURRENT, qualifier=q),
                f"CURRENT+{q} must NOT be allowed to claim completion",
            )

    def test_persisted_is_saveable_but_not_complete(self):
        # "Saved" is honest at PERSISTED; "up to date" is not.
        self.assertTrue(lc.may_claim_saved(lc.PERSISTED))
        self.assertFalse(lc.may_claim_complete(lc.PERSISTED))

    def test_failed_before_persist_forbids_saved_claim(self):
        self.assertFalse(lc.may_claim_saved(lc.RECEIVED, qualifier=lc.FAILED))


class ClaimKeyTests(SimpleTestCase):
    """`claim_key` never emits a claim more optimistic than the verified stage."""

    def test_partial_run_reports_partial_not_complete(self):
        self.assertEqual(
            lc.claim_key(lc.PERSISTED, qualifier=lc.PARTIAL), lc.CLAIM_PARTIAL
        )

    def test_stale_derived_reports_updating_not_complete(self):
        self.assertEqual(
            lc.claim_key(lc.DERIVED, qualifier=lc.STALE), lc.CLAIM_UPDATING
        )

    def test_only_clean_current_reports_up_to_date(self):
        self.assertEqual(lc.claim_key(lc.CURRENT), lc.CLAIM_UP_TO_DATE)

    def test_clean_persist_reports_saved(self):
        self.assertEqual(lc.claim_key(lc.PERSISTED), lc.CLAIM_SAVED)


class SyncLifecycleTests(SimpleTestCase):
    """`sync_lifecycle` interprets ingestion-run counts into verified truth."""

    def test_clean_persist_without_derived_caps_at_saved(self):
        # A just-finished sync that persisted rows, with derived freshness unknown,
        # is SAVED — never "up to date". This is the Health Sync fix in miniature.
        r = lc.sync_lifecycle(received=100, created=80, updated=20,
                              skipped=0, failed=0)
        self.assertEqual(r["stage"], lc.PERSISTED)
        self.assertIsNone(r["qualifier"])
        self.assertEqual(r["claim"], lc.CLAIM_SAVED)

    def test_some_failures_make_the_run_partial(self):
        r = lc.sync_lifecycle(received=100, created=90, updated=0,
                              skipped=5, failed=5)
        self.assertEqual(r["qualifier"], lc.PARTIAL)
        self.assertEqual(r["claim"], lc.CLAIM_PARTIAL)
        self.assertFalse(lc.may_claim_complete(r["stage"], qualifier=r["qualifier"]))

    def test_all_failed_nothing_persisted_is_failed(self):
        r = lc.sync_lifecycle(received=10, created=0, updated=0,
                              skipped=0, failed=10)
        self.assertEqual(r["stage"], lc.RECEIVED)
        self.assertEqual(r["qualifier"], lc.FAILED)
        self.assertEqual(r["claim"], lc.CLAIM_FAILED)

    def test_skips_only_are_persisted_no_change(self):
        # Dedup: everything already stored. Durably persisted, nothing new — SAVED.
        r = lc.sync_lifecycle(received=50, created=0, updated=0,
                              skipped=50, failed=0)
        self.assertEqual(r["stage"], lc.PERSISTED)
        self.assertIsNone(r["qualifier"])

    def test_derived_current_promotes_clean_run_to_current(self):
        r = lc.sync_lifecycle(received=100, created=100, updated=0, skipped=0,
                              failed=0, derived=freshness.CURRENT)
        self.assertEqual(r["stage"], lc.CURRENT)
        self.assertEqual(r["claim"], lc.CLAIM_UP_TO_DATE)

    def test_derived_stale_reports_updating_not_complete(self):
        r = lc.sync_lifecycle(received=100, created=100, updated=0, skipped=0,
                              failed=0, derived=freshness.STALE)
        self.assertEqual(r["stage"], lc.DERIVED)
        self.assertEqual(r["qualifier"], lc.STALE)
        self.assertFalse(lc.may_claim_complete(r["stage"], qualifier=r["qualifier"]))

    def test_empty_run_is_initiated(self):
        r = lc.sync_lifecycle(received=0, created=0, updated=0, skipped=0, failed=0)
        self.assertEqual(r["stage"], lc.INITIATED)


class DerivedStateTests(SimpleTestCase):
    """`derived_state` exposes stale/updating derived data instead of hiding it."""

    def _dt(self, y, mo, d, h=0, mi=0):
        from datetime import datetime, timezone
        return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)

    def test_never_built_is_pending(self):
        s = lc.derived_state(persisted_at=self._dt(2026, 7, 14), derived_at=None)
        self.assertEqual(s["verdict"], freshness.PENDING)
        self.assertEqual(s["stage"], lc.PERSISTED)

    def test_persist_newer_than_derived_is_stale(self):
        s = lc.derived_state(
            persisted_at=self._dt(2026, 7, 14, 9, 0),
            derived_at=self._dt(2026, 7, 14, 8, 0),
        )
        self.assertEqual(s["verdict"], freshness.STALE)
        self.assertEqual(s["qualifier"], lc.STALE)
        # A stale derived layer must not be presentable as complete.
        self.assertFalse(lc.may_claim_complete(s["stage"], qualifier=s["qualifier"]))

    def test_derived_at_or_after_persist_is_current(self):
        s = lc.derived_state(
            persisted_at=self._dt(2026, 7, 14, 8, 0),
            derived_at=self._dt(2026, 7, 14, 9, 0),
        )
        self.assertEqual(s["verdict"], freshness.CURRENT)
        self.assertEqual(s["stage"], lc.CURRENT)
        self.assertTrue(lc.may_claim_complete(s["stage"], qualifier=s["qualifier"]))
