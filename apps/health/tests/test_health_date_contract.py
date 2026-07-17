# ==============================================================================
# File: apps/health/tests/test_health_date_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The canonical health DATE contract — ONE definition, every consumer.
#   Production regression (2026-07-17): health.build_user_health_summary crashed with
#   "ValueError: unconverted data remains: T17:33:35Z" because it re-implemented the
#   contract as strptime("%Y-%m-%d") while the iOS HealthKit ingest forwards ISO-8601
#   sample timestamps. The backfill caller (str(date)) succeeded — hence adjacent
#   executions behaving differently. Two parsers for one contract was the defect.
# ==============================================================================
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.health.services.health_dates import parse_health_date

User = get_user_model()


class HealthDateContractTests(TestCase):
    """The contract: "YYYY-MM-DD" | ISO-8601 instant | date/datetime → a calendar date.
    Anything else raises ValueError. Never sliced."""

    def test_plain_calendar_date(self):
        self.assertEqual(parse_health_date("2026-07-16"), date(2026, 7, 16))

    def test_iso8601_utc_timestamp_z_suffix(self):
        # The exact production input that crashed the task.
        self.assertEqual(parse_health_date("2026-07-16T17:33:35Z"), date(2026, 7, 16))

    def test_iso8601_with_explicit_utc_offset(self):
        self.assertEqual(parse_health_date("2026-07-16T17:33:35+00:00"),
                         date(2026, 7, 16))

    def test_iso8601_with_non_utc_offset_resolves_to_its_own_calendar_date(self):
        # -05:00 local instant — the calendar date carried by the timestamp itself.
        self.assertEqual(parse_health_date("2026-07-16T17:33:35-05:00"),
                         date(2026, 7, 16))

    def test_iso8601_with_fractional_seconds(self):
        self.assertEqual(parse_health_date("2026-07-16T17:33:35.123456Z"),
                         date(2026, 7, 16))

    def test_naive_iso8601_timestamp(self):
        self.assertEqual(parse_health_date("2026-07-16T17:33:35"), date(2026, 7, 16))

    def test_timezone_aware_datetime_object(self):
        dt = datetime(2026, 7, 16, 17, 33, 35, tzinfo=dt_timezone.utc)
        self.assertEqual(parse_health_date(dt), date(2026, 7, 16))

    def test_naive_datetime_object(self):
        self.assertEqual(parse_health_date(datetime(2026, 7, 16, 17, 33)),
                         date(2026, 7, 16))

    def test_date_object_passes_through(self):
        self.assertEqual(parse_health_date(date(2026, 7, 16)), date(2026, 7, 16))

    def test_whitespace_is_tolerated(self):
        self.assertEqual(parse_health_date("  2026-07-16  "), date(2026, 7, 16))


class HealthDateInvalidInputTests(TestCase):
    """Invalid input must still FAIL — loudly, never guessed at."""

    def test_invalid_formats_raise(self):
        for bad in ("07/16/2026", "16-07-2026", "2026-13-45", "not-a-date",
                    "2026-07-16T99:99:99Z", "", "   ", "2026-07", None, 12345, []):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_health_date(bad)

    def test_never_slices_a_malformed_string(self):
        # value[:10] would silently "accept" this garbage as 2026-07-16. Parsing rejects it.
        with self.assertRaises(ValueError):
            parse_health_date("2026-07-16GARBAGE")


class BuildUserHealthSummaryContractTests(TestCase):
    """The reported production failure, at the task boundary."""

    def setUp(self):
        self.user = User.objects.create_user(email="hd@test.com", password="x")

    def _run(self, target_date_str):
        from apps.health.tasks import build_user_health_summary
        with mock.patch("apps.health.services.score_pipeline.ScorePipeline.full_build",
                        return_value=mock.Mock(health_score=77)) as m:
            result = build_user_health_summary(self.user.id, target_date_str)
        return result, m

    def test_iso8601_timestamp_no_longer_crashes(self):
        # PRODUCTION REGRESSION: previously ValueError: unconverted data remains: T17:33:35Z
        result, m = self._run("2026-07-16T17:33:35Z")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["date"], "2026-07-16")
        self.assertEqual(m.call_args[0][1], date(2026, 7, 16))   # resolved date reached the pipeline

    def test_plain_date_still_works(self):
        result, m = self._run("2026-07-16")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["date"], "2026-07-16")
        self.assertEqual(m.call_args[0][1], date(2026, 7, 16))

    def test_none_defaults_to_yesterday(self):
        result, _ = self._run(None)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["date"], str(date.today() - timedelta(days=1)))

    def test_invalid_date_still_fails(self):
        from apps.health.tasks import build_user_health_summary
        with self.assertRaises(ValueError):
            build_user_health_summary(self.user.id, "16/07/2026")


class HealthDateSingleDefinitionTests(TestCase):
    """The class fix: the ingest and the summary task must not drift apart again —
    both call the ONE canonical parser."""

    def test_ingest_and_summary_task_share_the_parser(self):
        import inspect
        from apps.health import tasks as health_tasks
        from apps.mobile import views as mobile_views

        self.assertIn("parse_health_date",
                      inspect.getsource(health_tasks.build_user_health_summary))
        self.assertIn("parse_health_date",
                      inspect.getsource(mobile_views.process_health_metric))
        # and the old duplicated parse is gone from the ingest
        src = inspect.getsource(mobile_views.process_health_metric)
        self.assertNotIn('strptime(metric_date, "%Y-%m-%d")', src)

    def test_both_consumers_agree_on_every_contract_input(self):
        # Same input → same calendar date, whichever consumer parses it.
        for value in ("2026-07-16", "2026-07-16T17:33:35Z",
                      "2026-07-16T00:00:00+00:00"):
            with self.subTest(value=value):
                self.assertEqual(parse_health_date(value), date(2026, 7, 16))
