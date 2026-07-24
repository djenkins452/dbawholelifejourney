"""
Operations Recovery Stabilization — acceptance tests built on the real
2026-07-23 production incident.

Proves the executive status no longer flaps: a transient recovery above the
threshold does not immediately announce recovery, repeated oscillation does not
toggle HEALTHY (so notifications cannot spam), and recovery only occurs after the
deterministic stability criteria (N consecutive healthy cycles + no significant
active incident) are satisfied. Degradation stays immediate.
"""
from django.test import SimpleTestCase, override_settings
from django.core.cache import cache

from apps.core.ai_observability.ops_executive import (
    RECOVERING,
    RECOVERY_STABLE_CYCLES,
    stabilize_status,
)

P1 = [{"severity": "P1"}]
P2 = [{"severity": "P2"}]
NONE = []


def _run(sequence):
    """Thread the pure stabilizer over a [(raw, incidents), ...] sequence."""
    state, out = None, []
    for raw, inc in sequence:
        status, state, _meta = stabilize_status(state, raw, inc)
        out.append(status)
    return out


class RecoveryHysteresisTest(SimpleTestCase):
    def test_degradation_is_immediate(self):
        # Healthy → degraded flips the same cycle (never dampen a real problem).
        out = _run([("HEALTHY", NONE), ("DEGRADED", P1)])
        self.assertEqual(out, ["HEALTHY", "DEGRADED"])

    def test_transient_recovery_does_not_announce_recovery(self):
        # DEGRADED then ONE cycle of raw-HEALTHY must NOT become HEALTHY.
        out = _run([("DEGRADED", P1), ("HEALTHY", NONE)])
        self.assertEqual(out[-1], RECOVERING)
        self.assertNotEqual(out[-1], "HEALTHY")

    def test_recovery_requires_sustained_stability(self):
        seq = [("DEGRADED", P1)] + [("HEALTHY", NONE)] * RECOVERY_STABLE_CYCLES
        out = _run(seq)
        # Not healthy until the Nth consecutive healthy cycle.
        for i in range(1, RECOVERY_STABLE_CYCLES):
            self.assertEqual(out[i], RECOVERING, f"cycle {i} should be RECOVERING")
        self.assertEqual(out[-1], "HEALTHY")

    def test_incident_aware_blocks_recovery(self):
        # Raw HEALTHY (score ≥70, no P1) but a P2 incident is still active →
        # never HEALTHY while the significant incident remains.
        seq = [("DEGRADED", P1)] + [("HEALTHY", P2)] * (RECOVERY_STABLE_CYCLES + 2)
        out = _run(seq)
        self.assertNotIn("HEALTHY", out[1:], "must not recover while a P2 is active")
        self.assertEqual(out[-1], RECOVERING)

    def test_oscillation_never_flaps_to_healthy(self):
        """The exact 2026-07-23 curve: 50→51→76.5→67→76.5→69.5→98 with
        P1 then P2 active until the end. Stabilized status must NOT become
        HEALTHY during the oscillation (09:47–10:43)."""
        incident = [
            ("DEGRADED", P1),   # 09:47  50
            ("DEGRADED", P1),   # 09:50  51
            ("HEALTHY", P2),    # 09:54  76.5 (P1 cleared, GLOE P2 active)
            ("DEGRADED", P2),   # 10:06  67
            ("HEALTHY", P2),    # 10:09  76.5
            ("HEALTHY", P2),    # 10:13  88.5 (GLOE still active)
            ("DEGRADED", P2),   # 10:38  69.5
        ]
        out = _run(incident)
        self.assertNotIn("HEALTHY", out, "executive flapped to HEALTHY mid-incident")
        # Then a genuine sustained recovery with all incidents resolved.
        resolved = [("HEALTHY", NONE)] * RECOVERY_STABLE_CYCLES
        state = None
        for raw, inc in incident + resolved:
            status, state, _ = stabilize_status(state, raw, inc)
        self.assertEqual(status, "HEALTHY")

    def test_recovery_resets_on_re_degradation(self):
        # A blip back to DEGRADED resets the stability counter.
        out = _run([
            ("DEGRADED", NONE), ("HEALTHY", NONE), ("HEALTHY", NONE),
            ("DEGRADED", NONE),                       # reset
            ("HEALTHY", NONE), ("HEALTHY", NONE),     # only 2 → still RECOVERING
        ])
        self.assertEqual(out[-1], RECOVERING)


LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                      "LOCATION": "recov-stab"}}


@override_settings(CACHES=LOCMEM)
class BannerRecoveringMappingTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_recovering_status_is_not_shown_as_healthy(self):
        from apps.ai.operations_banner import get_customer_operations_status
        from apps.core.ai_observability.ops_telemetry import OPS_STREAM_CACHE_KEY
        cache.set(OPS_STREAM_CACHE_KEY, {"executive": {"overall_status": "RECOVERING"}}, 60)
        s = get_customer_operations_status()
        self.assertEqual(s["state"], "recovering")
        self.assertNotEqual(s["state"], "healthy")  # no premature green
        self.assertTrue(any("recovering" in ln.lower() for ln in s["lines"]))
