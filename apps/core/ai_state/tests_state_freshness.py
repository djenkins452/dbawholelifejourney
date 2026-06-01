"""
Tests for the SAE manual-entry freshness guard (apps/core/ai_state/state_freshness.py).

Reproduces the reported bug: a manual entry (journal / nutrition) logged after
the snapshot was built, with the async Celery refresh not yet landed, must be
reflected on the next dashboard read — not next morning.
"""

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_state.models import UserState
from apps.core.ai_state.state_freshness import ensure_fresh
from apps.users.models import User


class ManualFreshnessGuardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="freshness@test.com", password="testpass123"
        )

    def _stale_snapshot(self, state_data, *, age_minutes=60):
        """Persist a snapshot then backdate last_updated past auto_now."""
        UserState.objects.update_or_create(
            user=self.user, defaults={"state_data": state_data}
        )
        stale_ts = timezone.now() - timedelta(minutes=age_minutes)
        # .update() bypasses auto_now so we can simulate a snapshot built before
        # the user's latest write.
        UserState.objects.filter(user=self.user).update(last_updated=stale_ts)

    def _read(self, module):
        return UserState.objects.get(user=self.user).state_data.get(module, {})

    # ── Journal ──────────────────────────────────────────────────────────

    def test_journal_entry_after_stale_snapshot_is_refreshed(self):
        # The exact reported scenario: snapshot says 0/wk, user journals, the
        # async refresh hasn't landed — the guard must repair it on read.
        from apps.journal.models import JournalEntry
        JournalEntry.objects.create(
            user=self.user, title="Today", body="A real entry",
            entry_date=date.today(), mood="good",
        )
        self._stale_snapshot({"journal": {"entries_7d": 0}})

        refreshed = ensure_fresh(self.user, ["journal"])

        self.assertIn("journal", refreshed)
        self.assertEqual(self._read("journal").get("entries_7d"), 1)

    def test_journal_fresh_snapshot_is_not_recomputed(self):
        # No raw write newer than the snapshot → no rebuild (cheap no-op path).
        from apps.journal.models import JournalEntry
        JournalEntry.objects.create(
            user=self.user, title="Old", body="Older entry",
            entry_date=date.today(), mood="good",
        )
        # Snapshot built AFTER the entry (last_updated = now via save()).
        UserState.objects.update_or_create(
            user=self.user, defaults={"state_data": {"journal": {"entries_7d": 1}}}
        )

        refreshed = ensure_fresh(self.user, ["journal"])

        self.assertEqual(refreshed, set())

    # ── Nutrition ────────────────────────────────────────────────────────

    def test_food_entry_after_stale_snapshot_is_refreshed(self):
        from apps.health.models import FoodEntry
        FoodEntry.objects.create(
            user=self.user, food_name="Eggs", serving_size=2,
            serving_unit="large", logged_date=date.today(), status="active",
            total_calories=140, total_protein_g=12,
        )
        self._stale_snapshot({"nutrition": {"enabled": True, "food_entries_today": 0}})

        refreshed = ensure_fresh(self.user, ["nutrition"])

        self.assertIn("nutrition", refreshed)
        self.assertEqual(self._read("nutrition").get("food_entries_today"), 1)

    # ── Guard safety ─────────────────────────────────────────────────────

    def test_non_manual_module_is_ignored(self):
        # Heavy device/aggregate modules must never be force-rebuilt on the
        # request path by this guard.
        self._stale_snapshot({"health": {}})
        refreshed = ensure_fresh(self.user, ["health", "fitness"])
        self.assertEqual(refreshed, set())

    def test_missing_snapshot_is_safe_noop(self):
        # No UserState yet → guard does nothing (first read will full-rebuild).
        self.assertFalse(UserState.objects.filter(user=self.user).exists())
        refreshed = ensure_fresh(self.user, ["journal", "nutrition"])
        self.assertEqual(refreshed, set())

    def test_clears_per_request_sae_cache_after_refresh(self):
        from apps.journal.models import JournalEntry
        JournalEntry.objects.create(
            user=self.user, title="Cached", body="Body",
            entry_date=date.today(), mood="good",
        )
        self._stale_snapshot({"journal": {"entries_7d": 0}})
        # Simulate a per-request cache set earlier in the same request.
        self.user._sae_cache = {"journal": {"entries_7d": 0}}

        ensure_fresh(self.user, ["journal"])

        self.assertIsNone(getattr(self.user, "_sae_cache", None))
