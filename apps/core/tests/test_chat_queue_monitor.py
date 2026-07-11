"""
OPS-3 — Chat Queue Monitor tests.

Proves the passive lifecycle capture + derived queue health:
  * enqueue → pending; start → active + recorded wait; complete → throughput,
  * queue depth and oldest-queued age computed from the pending set,
  * stuck detection when a task stays active past the time-limit,
  * worker-starvation detection (backlog with nothing running / draining),
  * graceful UNAVAILABLE when no Redis broker is configured (dev),
  * signal handlers only fire for chat task names.

A minimal in-memory fake stands in for the Redis client so the sorted-set /
list semantics the monitor relies on are exercised without a live server.

Path: apps/core/tests/test_chat_queue_monitor.py
"""

from unittest.mock import patch

from django.test import TestCase

from apps.core.ai_observability import chat_queue_monitor as cqm


class FakeRedis:
    """Tiny in-memory stand-in for the subset of Redis ops the monitor uses."""

    def __init__(self):
        self.zsets = {}   # key -> {member: score}
        self.lists = {}   # key -> [values] (index 0 = head, LPUSH prepends)

    # --- sorted sets ---
    def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update({str(k): float(v) for k, v in mapping.items()})

    def zscore(self, key, member):
        return self.zsets.get(key, {}).get(str(member))

    def zrem(self, key, member):
        self.zsets.get(key, {}).pop(str(member), None)

    def zcard(self, key):
        return len(self.zsets.get(key, {}))

    def zrange(self, key, start, stop, withscores=False):
        items = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1])
        if stop == -1:
            stop = len(items)
        else:
            stop = stop + 1
        sliced = items[start:stop]
        if withscores:
            return [(m.encode(), s) for m, s in sliced]
        return [m.encode() for m, _s in sliced]

    # --- lists ---
    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, str(value).encode())

    def ltrim(self, key, start, stop):
        lst = self.lists.get(key, [])
        self.lists[key] = lst[start:stop + 1]

    def lrange(self, key, start, stop):
        lst = self.lists.get(key, [])
        return lst[start:stop + 1]

    def expire(self, key, ttl):
        pass


class ChatQueueLifecycleTests(TestCase):
    def setUp(self):
        self.fake = FakeRedis()
        self._patcher = patch.object(cqm, "_redis", return_value=self.fake)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_enqueue_then_start_then_complete(self):
        cqm.record_enqueued("job1", now_epoch=1000.0)
        # Pending depth 1, oldest age computed at now=1005.
        out = cqm.get_chat_queue_telemetry_at(now_epoch=1005.0)
        self.assertEqual(out["queue_depth"], 1)
        self.assertEqual(out["oldest_age_s"], 5)

        cqm.record_started("job1", now_epoch=1005.0)
        out = cqm.get_chat_queue_telemetry_at(now_epoch=1006.0)
        self.assertEqual(out["queue_depth"], 0)
        self.assertEqual(out["active_count"], 1)
        # Waited 5s = 5000ms.
        self.assertEqual(out["avg_wait_ms"], 5000)

        cqm.record_completed("job1", success=True, now_epoch=1010.0)
        out = cqm.get_chat_queue_telemetry_at(now_epoch=1011.0)
        self.assertEqual(out["active_count"], 0)
        self.assertEqual(out["throughput_per_min"], 1)
        self.assertEqual(out["status"], "HEALTHY")

    def test_stuck_detection(self):
        cqm.record_enqueued("stuck", now_epoch=1000.0)
        cqm.record_started("stuck", now_epoch=1000.0)
        # Still active well past the time-limit → stuck → CRITICAL.
        out = cqm.get_chat_queue_telemetry_at(now_epoch=1000.0 + cqm.STUCK_ACTIVE_S + 5)
        self.assertEqual(out["stuck_count"], 1)
        self.assertEqual(out["status"], "CRITICAL")

    def test_worker_starvation(self):
        # Backlog present, nothing active, no completions, old enough → starved.
        cqm.record_enqueued("a", now_epoch=1000.0)
        cqm.record_enqueued("b", now_epoch=1000.0)
        out = cqm.get_chat_queue_telemetry_at(
            now_epoch=1000.0 + cqm.STARVATION_WINDOW_S + 10)
        self.assertTrue(out["worker_starved"])
        self.assertEqual(out["status"], "CRITICAL")

    def test_warning_on_depth(self):
        for i in range(cqm.WARN_DEPTH):
            cqm.record_enqueued(f"j{i}", now_epoch=2000.0)
        out = cqm.get_chat_queue_telemetry_at(now_epoch=2001.0)
        self.assertEqual(out["queue_depth"], cqm.WARN_DEPTH)
        self.assertEqual(out["status"], "WARNING")


class ChatQueueDegradationTests(TestCase):
    def test_unavailable_without_redis(self):
        with patch.object(cqm, "_redis", return_value=None):
            out = cqm.get_chat_queue_telemetry()
        self.assertEqual(out["status"], "UNAVAILABLE")
        self.assertIsNone(out["queue_depth"])

    def test_recorders_noop_without_redis(self):
        with patch.object(cqm, "_redis", return_value=None):
            # Must not raise.
            cqm.record_enqueued("x")
            cqm.record_started("x")
            cqm.record_completed("x")


class ChatQueueSignalFilterTests(TestCase):
    def setUp(self):
        self.fake = FakeRedis()
        self._patcher = patch.object(cqm, "_redis", return_value=self.fake)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_publish_handler_ignores_non_chat_tasks(self):
        cqm._on_publish(sender="apps.core.tasks.run_same_cycle_task",
                        headers={"id": "nope"})
        self.assertEqual(self.fake.zcard(cqm._PENDING_ZSET), 0)

    def test_publish_handler_records_chat_task(self):
        cqm._on_publish(sender="apps.ai.tasks.run_chat_generation",
                        headers={"id": "yes"})
        self.assertEqual(self.fake.zcard(cqm._PENDING_ZSET), 1)
