# ==============================================================================
# File: apps/mobile/tests/test_sleep_ingest.py
# Description: Permanent regression for the HealthKit SLEEP import path. A new Apple
#   Health sleep payload must create/update the correct SleepEntry and become the
#   latest canonical sleep record. Origin: last night (6h30m asleep, bedtime 10:07 PM
#   → wake ~4:57 AM, crossing midnight) landed on the WRONG day — the record was dated
#   by a per-sample local end-date instead of the wake instant, so Jul 4's sleep
#   appeared under Jul 3 (or split across both). The server now derives the night's
#   date from the actual WAKE instant in the user's timezone.
# ==============================================================================
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.health.models import SleepEntry
from apps.health.services.sleep_queries import last_night
from apps.mobile.views import process_health_metric

User = get_user_model()


def _sleep_metric(*, date, wake_time, bedtime, deep=0, rem=0, light=0, awake=0,
                  total=None, source="apple_health", sync_id=None):
    total = total if total is not None else (deep + rem + light + awake)
    return {
        "type": "sleep", "date": date, "source": source,
        "sync_id": sync_id or f"sleep-{date}",
        "bedtime": bedtime, "wake_time": wake_time,
        "total_minutes": total, "deep_minutes": deep, "rem_minutes": rem,
        "light_minutes": light, "awake_minutes": awake,
    }


class SleepIngestTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="sleepimp@test.com", password="x")
        self.user.preferences.timezone = "America/New_York"
        self.user.preferences.save()

    # ── Stages + time-asleep vs time-in-bed ────────────────────────────────────
    def test_stages_and_asleep_excludes_awake(self):
        # 6 hr 30 min asleep (deep 70 + rem 95 + core/light 225 = 390) within a night
        # that also has 20 min awake → time in bed 410, time ASLEEP 390.
        process_health_metric(self.user, _sleep_metric(
            date="2026-07-04", bedtime="2026-07-04T02:07:00Z",
            wake_time="2026-07-04T08:57:00Z", deep=70, rem=95, light=225, awake=20))
        e = SleepEntry.objects.get(user=self.user, sleep_date="2026-07-04")
        self.assertEqual(e.stage_deep_minutes, 70)
        self.assertEqual(e.stage_rem_minutes, 95)
        self.assertEqual(e.total_duration_minutes, 410)
        self.assertEqual(e.asleep_duration_minutes, 390)     # asleep = total − awake

    # ── ROOT CAUSE: a midnight-crossing night is dated by WAKE, not the client date ─
    def test_night_dated_by_wake_instant_not_client_date(self):
        # Client MIS-DATES last night to Jul 3 (per-sample grouping fragmented it), but
        # the real wake instant is 4:57 AM EDT Jul 4 (08:57 UTC). The server must date
        # the record Jul 4 from the wake instant.
        process_health_metric(self.user, _sleep_metric(
            date="2026-07-03",                                  # wrong client date
            bedtime="2026-07-04T02:07:00Z", wake_time="2026-07-04T08:57:00Z",
            deep=70, rem=95, light=225, awake=20, sync_id="sleep-2026-07-04"))
        self.assertTrue(SleepEntry.objects.filter(
            user=self.user, sleep_date="2026-07-04").exists())
        self.assertFalse(SleepEntry.objects.filter(
            user=self.user, sleep_date="2026-07-03").exists())

    def test_jul4_after_existing_jul3_becomes_latest(self):
        # The exact production scenario: an older Jul 3 record already exists; a new
        # Jul 4 night must be CREATED (not overwrite Jul 3) and become the latest.
        SleepEntry.objects.create(
            user=self.user, sleep_date="2026-07-03", source="apple_health",
            sync_id="sleep-2026-07-03", total_duration_minutes=288,
            asleep_duration_minutes=270, bedtime="2026-07-02T23:38:00-04:00",
            wake_time="2026-07-03T04:29:00-04:00")
        process_health_metric(self.user, _sleep_metric(
            date="2026-07-04", bedtime="2026-07-04T02:07:00Z",
            wake_time="2026-07-04T08:57:00Z", deep=70, rem=95, light=225, awake=20))
        self.assertEqual(SleepEntry.objects.filter(user=self.user).count(), 2)
        # Jul 3 untouched, Jul 4 is the canonical latest night at ~6.5h.
        self.assertEqual(SleepEntry.objects.get(
            user=self.user, sleep_date="2026-07-03").asleep_duration_minutes, 270)
        ln = last_night(self.user)
        self.assertEqual(ln["date"].isoformat(), "2026-07-04")
        self.assertAlmostEqual(ln["hours"], 6.5, delta=0.15)

    # ── Duplicate / update behavior ────────────────────────────────────────────
    def test_resync_same_night_updates_not_duplicates(self):
        m = _sleep_metric(date="2026-07-04", bedtime="2026-07-04T02:07:00Z",
                          wake_time="2026-07-04T08:57:00Z", deep=70, rem=95, light=225, awake=20)
        self.assertEqual(process_health_metric(self.user, m), "created")
        self.assertEqual(process_health_metric(self.user, m), "skipped")   # unchanged
        m2 = dict(m, deep_minutes=80, total_minutes=420)                    # value changed
        self.assertEqual(process_health_metric(self.user, m2), "updated")
        self.assertEqual(SleepEntry.objects.filter(user=self.user).count(), 1)

    # ── Multiple segments for one night collapse onto the one wake-dated record ─
    def test_multiple_segments_same_wake_date_merge(self):
        # Even if the client sends two fragments that share the same wake DATE and
        # sync_id, they resolve to a single SleepEntry for that night (no duplicates).
        for i in range(2):
            process_health_metric(self.user, _sleep_metric(
                date="2026-07-04", bedtime="2026-07-04T02:07:00Z",
                wake_time="2026-07-04T08:57:00Z", deep=70, rem=95, light=225, awake=20))
        self.assertEqual(SleepEntry.objects.filter(
            user=self.user, sleep_date="2026-07-04").count(), 1)

    # ── Historical replay corrects a previously mis-imported night IN PLACE ────
    def test_replay_corrects_previously_misimported_night(self):
        # A night that the OLD buggy importer stored with wrong values (same
        # sync_id "sleep-<date>"). Re-sending the CORRECT payload through the same
        # importer (what the historical replay does) must overwrite it in place —
        # no duplicate, correct values, and it is the canonical latest.
        SleepEntry.objects.create(
            user=self.user, sleep_date="2026-07-04", source="apple_health",
            sync_id="sleep-2026-07-04", total_duration_minutes=281,
            asleep_duration_minutes=281, stage_deep_minutes=22, stage_rem_minutes=72,
            stage_light_minutes=187, bedtime="2026-07-04T03:49:00Z",
            wake_time="2026-07-04T08:40:00Z")
        process_health_metric(self.user, _sleep_metric(
            date="2026-07-04", bedtime="2026-07-04T02:07:00Z",
            wake_time="2026-07-04T08:57:00Z", deep=70, rem=95, light=225, awake=20))
        self.assertEqual(SleepEntry.objects.filter(
            user=self.user, sleep_date="2026-07-04").count(), 1)     # no duplicate
        e = SleepEntry.objects.get(user=self.user, sleep_date="2026-07-04")
        self.assertEqual(e.asleep_duration_minutes, 390)             # corrected in place
        self.assertEqual(last_night(self.user)["date"].isoformat(), "2026-07-04")

    # ── An oversized total is CLAMPED, never dropped (a night must never vanish) ─
    def test_oversized_total_is_clamped_not_dropped(self):
        r = process_health_metric(self.user, _sleep_metric(
            date="2026-07-04", bedtime="2026-07-04T02:07:00Z",
            wake_time="2026-07-04T08:57:00Z", deep=200, rem=300, light=900, awake=200,
            total=1600))
        self.assertEqual(r, "created")
        e = SleepEntry.objects.get(user=self.user, sleep_date="2026-07-04")
        self.assertEqual(e.total_duration_minutes, 1440)       # clamped, not rejected
