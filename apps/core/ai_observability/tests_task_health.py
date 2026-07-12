"""
OPS-7 — Background task health monitor tests.

Redis-mocked for deterministic reader/aggregation logic; verifies the
UNAVAILABLE path, recorder fail-safety, stuck/failure/retry roll-up, and
recurring-vs-isolated detection. Worker-side capture, telemetry-only.
"""
import time
from unittest import mock

from django.test import TestCase

from apps.core.ai_observability import task_health_monitor as thm


class AggregationTests(TestCase):
    def test_aggregate_counts_and_recurring(self):
        entries = [b"1.0:a.x", b"2.0:a.x", b"3.0:a.x", b"4.0:a.y"]
        total, top, recurring = thm._aggregate_by_name(entries)
        self.assertEqual(total, 4)
        self.assertEqual(top[0], {"name": "a.x", "count": 3})
        self.assertTrue(recurring)  # a.x hit RECURRING_THRESHOLD (3)

    def test_aggregate_isolated_not_recurring(self):
        _, _, recurring = thm._aggregate_by_name([b"1.0:a.x", b"2.0:a.y"])
        self.assertFalse(recurring)


class RecorderFailSafeTests(TestCase):
    def test_recorders_noop_without_redis(self):
        with mock.patch.object(thm, "_redis", return_value=None):
            # None of these may raise even with no Redis.
            thm.record_started("t1", "a.x")
            thm.record_finished("t1")
            thm.record_failure("a.x")
            thm.record_retry("a.x")
            thm.record_revoked("a.x")


class ReaderTests(TestCase):
    def _client(self, active, names, failures, retries, revoked):
        client = mock.MagicMock()
        client.zrange.return_value = active
        client.hget.side_effect = lambda key, tid: names.get(tid)
        def lrange(key, *a):
            return {
                thm._FAILURES_LIST: failures,
                thm._RETRIES_LIST: retries,
                thm._REVOKED_LIST: revoked,
            }.get(key, [])
        client.lrange.side_effect = lrange
        return client

    def test_unavailable_without_redis(self):
        with mock.patch.object(thm, "_redis", return_value=None):
            result = thm.get_task_health_telemetry()
        self.assertEqual(result["status"], "UNAVAILABLE")

    def test_stuck_and_recurring_failures_warning(self):
        now = time.time()
        client = self._client(
            active=[(b"t1", now - 200), (b"t2", now - 5)],  # t1 stuck (>130s)
            names={b"t1": b"apps.core.tasks.slow"},
            failures=[b"1:a.x", b"2:a.x", b"3:a.x"],  # recurring
            retries=[b"1:a.y"],
            revoked=[],
        )
        with mock.patch.object(thm, "_redis", return_value=client):
            r = thm.get_task_health_telemetry()
        self.assertEqual(r["active"]["count"], 2)
        self.assertEqual(r["active"]["stuck_count"], 1)
        self.assertEqual(r["active"]["stuck_tasks"][0]["task"], "apps.core.tasks.slow")
        self.assertTrue(r["failures"]["recurring"])
        self.assertEqual(r["failures"]["recent_count"], 3)
        self.assertEqual(r["retries"]["recent_count"], 1)
        self.assertEqual(r["status"], "WARNING")

    def test_many_stuck_is_critical(self):
        now = time.time()
        client = self._client(
            active=[(f"t{i}".encode(), now - 200) for i in range(3)],  # 3 stuck
            names={f"t{i}".encode(): b"apps.x" for i in range(3)},
            failures=[], retries=[], revoked=[],
        )
        with mock.patch.object(thm, "_redis", return_value=client):
            r = thm.get_task_health_telemetry()
        self.assertEqual(r["active"]["stuck_count"], 3)
        self.assertEqual(r["status"], "CRITICAL")

    def test_healthy_when_quiet(self):
        now = time.time()
        client = self._client(
            active=[(b"t1", now - 5)], names={}, failures=[], retries=[], revoked=[],
        )
        with mock.patch.object(thm, "_redis", return_value=client):
            r = thm.get_task_health_telemetry()
        self.assertEqual(r["status"], "HEALTHY")
        self.assertEqual(r["active"]["stuck_count"], 0)


class SignalHelperTests(TestCase):
    def test_task_name_extraction(self):
        sender = mock.Mock(name="s"); sender.name = "apps.core.tasks.foo"
        self.assertEqual(thm._task_name(sender), "apps.core.tasks.foo")
        req = mock.Mock(); req.task = "apps.core.tasks.bar"
        self.assertEqual(thm._task_name(None, request=req), "apps.core.tasks.bar")
