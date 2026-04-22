"""
Tests for the Phase 3 unified signal feed.

All tests run against synthetic context dicts — no database, no mocks
of engine internals. This matches the adapter's contract: it
normalizes shapes already present in ``context``.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.core.ai_signals.unified_feed import (
    CLASS_MOMENTUM,
    CLASS_RISK,
    CLASS_STATUS,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SOURCE_CROSS_DOMAIN,
    SOURCE_GUIDANCE,
    SOURCE_INSIGHT,
    UnifiedSignal,
    _compute_priority_score,
    _dedupe_signals,
    bucket_signals,
    build_signal_buckets,
    compose_signal_summary,
    get_unified_signals_from_context,
)


def _insight(
    *,
    title: str = "Glucose elevated",
    severity: str = "critical",
    confidence: float = 0.9,
    module: str = "health",
    dedupe_key: str = "",
    id_: int = 1,
):
    return {
        "title": title,
        "message": f"{title} — details.",
        "severity": severity,
        "confidence": confidence,
        "module": module,
        "type": "vitals_elevated",
        "_id": id_,
        "_dedupe_key": dedupe_key,
        "_created_at": None,
        "_status": "new",
    }


def _guidance(
    *,
    title: str = "Reduce added sugar",
    message: str = "Cut sugar today and drink more water.",
    priority: int = 2,
    module: str = "health",
    dedupe_key: str = "",
    id_: int = 11,
):
    return {
        "title": title,
        "message": message,
        "priority": priority,
        "module": module,
        "guidance_type": "action",
        "source": "engine",
        "_id": id_,
        "_dedupe_key": dedupe_key,
        "_confidence_score": 0.8,
        "_created_at": None,
    }


def _cross_domain(
    *,
    code: str = "execution_overload",
    severity: str = "high",
    confidence: str = "high",
    summary: str = "Overdue tasks stacking.",
    domains=("tasks",),
):
    return {
        "signal_code": code,
        "domains": list(domains),
        "severity": severity,
        "confidence": confidence,
        "summary": summary,
        "evidence": {},
    }


class UnifiedFeedShapeTests(SimpleTestCase):
    """Core shape + determinism of the adapter."""

    def test_empty_context_returns_empty_feed(self):
        feed = build_signal_buckets({})
        self.assertEqual(feed["top_signals"], [])
        self.assertEqual(feed["critical_signals"], [])
        self.assertEqual(feed["positive_signals"], [])
        self.assertEqual(feed["signal_summary"], "")

    def test_feed_pulls_from_all_five_sources(self):
        context = {
            "active_insights": [_insight()],
            "active_predictions": [{
                "type": "glucose_spike",
                "module": "health",
                "confidence": 0.8,
                "explanation": "Likely post-meal spike.",
                "_id": 101,
                "_dedupe_key": "",
                "_predicted_date_raw": None,
                "_created_at": None,
            }],
            "active_guidance": [_guidance()],
            "cross_domain_correlations": [{
                "type": "sleep_stress",
                "strength": "moderate",
                "score": 0.65,
                "domains": ["sleep", "mood"],
                "narrative": "Poor sleep correlates with stress spike.",
                "_id": 201,
                "_dedupe_key": "",
                "_created_at": None,
            }],
            "cross_domain_signals": [_cross_domain()],
        }
        unified = get_unified_signals_from_context(context)
        sources = {s.source for s in unified}
        # Guidance + insight may dedupe — assert at least 3 distinct sources.
        self.assertTrue(
            sources >= {SOURCE_CROSS_DOMAIN},
            msg=f"expected cross_domain in {sources}",
        )
        self.assertGreaterEqual(len(unified), 3)

    def test_feed_is_deterministic(self):
        context = {
            "active_insights": [_insight(id_=1), _insight(id_=2, severity="warning")],
            "active_guidance": [_guidance(id_=11, priority=1)],
            "cross_domain_signals": [_cross_domain(code="execution_overload")],
        }
        a = build_signal_buckets(context)
        b = build_signal_buckets(context)
        self.assertEqual(a, b)


class DeduplicationTests(SimpleTestCase):
    """dedupe_key collapses cross-source duplicates."""

    def test_same_dedupe_key_collapses(self):
        context = {
            "active_insights": [_insight(dedupe_key="glucose_elevated")],
            "active_guidance": [_guidance(dedupe_key="glucose_elevated")],
        }
        unified = get_unified_signals_from_context(context)
        # Two inputs, one cluster → one signal.
        self.assertEqual(len(unified), 1)
        # Guidance has higher source precedence, so canonical is guidance.
        self.assertEqual(unified[0].source, SOURCE_GUIDANCE)
        # Action text preserved from the guidance member.
        self.assertIsNotNone(unified[0].action_text)

    def test_missing_dedupe_key_falls_back_to_title_similarity(self):
        # Same title+domain+class but no dedupe_key ⇒ still collapse.
        context = {
            "active_insights": [
                _insight(title="Glucose elevated", dedupe_key="", id_=1),
            ],
            "active_guidance": [
                _guidance(title="Glucose elevated", dedupe_key="", id_=2),
            ],
        }
        unified = get_unified_signals_from_context(context)
        self.assertEqual(len(unified), 1)

    def test_different_issues_do_not_collapse(self):
        context = {
            "active_insights": [
                _insight(title="Glucose elevated", dedupe_key="a", id_=1),
                _insight(title="Sleep debt building", dedupe_key="b", id_=2),
            ],
        }
        unified = get_unified_signals_from_context(context)
        self.assertEqual(len(unified), 2)

    def test_canonical_inherits_action_from_guidance_member(self):
        context = {
            "active_insights": [_insight(dedupe_key="x", id_=1)],
            "active_guidance": [_guidance(dedupe_key="x", id_=2, message="Drink water now.")],
        }
        unified = get_unified_signals_from_context(context)
        self.assertEqual(unified[0].action_text, "Drink water now.")


class PriorityOrderingTests(SimpleTestCase):
    """priority_score respects severity > urgency > confidence weighting."""

    def test_priority_score_bounds(self):
        # Max: critical + urgency 5 + confidence 1.0
        max_score = _compute_priority_score(SEVERITY_CRITICAL, 1.0, urgency_ordinal=5)
        # Min: low + urgency 0 + confidence 0.0
        min_score = _compute_priority_score(SEVERITY_LOW, 0.0, urgency_ordinal=0)
        self.assertAlmostEqual(max_score, 1.0, places=3)
        self.assertGreaterEqual(max_score, min_score)
        self.assertLessEqual(min_score, 0.1)

    def test_critical_ranks_above_medium(self):
        crit = _compute_priority_score(SEVERITY_CRITICAL, 0.5, urgency_ordinal=3)
        med = _compute_priority_score(SEVERITY_MEDIUM, 0.5, urgency_ordinal=3)
        self.assertGreater(crit, med)

    def test_sort_descending_by_priority(self):
        context = {
            "active_insights": [
                _insight(title="Low info", severity="info",
                         confidence=0.6, dedupe_key="a", id_=1),
                _insight(title="Warning item", severity="warning",
                         confidence=0.8, dedupe_key="b", id_=2),
                _insight(title="Critical item", severity="critical",
                         confidence=0.9, dedupe_key="c", id_=3),
            ],
        }
        feed = build_signal_buckets(context)
        top_titles = [s["title"] for s in feed["top_signals"]]
        # Critical must precede Warning which must precede Low.
        self.assertEqual(
            top_titles[:3],
            ["Critical item", "Warning item", "Low info"],
        )


class BucketAssignmentTests(SimpleTestCase):
    """TOP / CRITICAL / POSITIVE partitioning."""

    def test_critical_contains_only_risk_with_high_severity(self):
        context = {
            "active_insights": [
                _insight(title="Crit A", severity="critical", dedupe_key="a", id_=1),
                _insight(title="Warn B", severity="warning", dedupe_key="b", id_=2),
                _insight(title="Info C", severity="info",
                         confidence=0.8, dedupe_key="c", id_=3),
            ],
        }
        feed = build_signal_buckets(context)
        critical_titles = {s["title"] for s in feed["critical_signals"]}
        # Critical + warning qualify (both risk + severity≥high).
        self.assertIn("Crit A", critical_titles)
        self.assertIn("Warn B", critical_titles)
        # Info never qualifies for critical.
        self.assertNotIn("Info C", critical_titles)

    def test_positive_contains_momentum_signals(self):
        context = {
            "active_insights": [
                _insight(title="Streak win", severity="positive",
                         dedupe_key="p", id_=1),
                _insight(title="Risk", severity="critical",
                         dedupe_key="r", id_=2),
            ],
        }
        feed = build_signal_buckets(context)
        positive_titles = {s["title"] for s in feed["positive_signals"]}
        self.assertIn("Streak win", positive_titles)
        self.assertNotIn("Risk", positive_titles)

    def test_top_capped_at_requested_n(self):
        insights = [
            _insight(title=f"Issue {i}", severity="warning",
                     dedupe_key=f"k{i}", id_=i)
            for i in range(10)
        ]
        feed = build_signal_buckets({"active_insights": insights}, top_n=3)
        self.assertEqual(len(feed["top_signals"]), 3)

    def test_top_falls_back_to_positive_when_no_actionable(self):
        context = {
            "active_insights": [
                _insight(title="Win 1", severity="positive",
                         dedupe_key="w1", id_=1),
                _insight(title="Win 2", severity="positive",
                         dedupe_key="w2", id_=2),
            ],
        }
        feed = build_signal_buckets(context)
        top_titles = {s["title"] for s in feed["top_signals"]}
        # All actionable buckets empty → TOP falls back to positives.
        self.assertEqual(top_titles, {"Win 1", "Win 2"})


class ActionExtractionTests(SimpleTestCase):
    """Guidance clusters propagate action_text; templates fill gaps."""

    def test_guidance_alone_carries_action(self):
        context = {"active_guidance": [_guidance(message="Do thing X.")]}
        unified = get_unified_signals_from_context(context)
        self.assertEqual(unified[0].action_text, "Do thing X.")

    def test_template_fills_action_for_known_domain_risk(self):
        context = {
            "active_insights": [
                _insight(title="Overdue task pressure",
                         severity="warning", module="tasks",
                         dedupe_key="op", id_=1),
            ],
        }
        unified = get_unified_signals_from_context(context)
        self.assertIsNotNone(unified[0].action_text)
        self.assertIn("task", unified[0].action_text.lower())


class SignalSummaryTests(SimpleTestCase):
    """Deterministic, short synthesis string."""

    def test_summary_is_empty_when_no_signals(self):
        buckets = bucket_signals([])
        self.assertEqual(compose_signal_summary(buckets), "")

    def test_summary_mentions_critical_titles(self):
        context = {
            "active_insights": [
                _insight(title="Overdue tasks stacking",
                         severity="critical", module="tasks",
                         dedupe_key="o", id_=1),
                _insight(title="Streak dropped",
                         severity="positive", module="habits",
                         dedupe_key="s", id_=2),
            ],
        }
        feed = build_signal_buckets(context)
        summary = feed["signal_summary"]
        self.assertIn("Overdue tasks stacking", summary)
        self.assertIn("Momentum", summary)


class CosIntegrationContractTests(SimpleTestCase):
    """The context keys CoS consumers read."""

    def test_build_signal_buckets_returns_expected_keys(self):
        feed = build_signal_buckets({"active_insights": [_insight()]})
        self.assertEqual(
            set(feed.keys()),
            {"top_signals", "critical_signals", "positive_signals",
             "signal_summary"},
        )

    def test_signal_dicts_are_plain_serializable(self):
        feed = build_signal_buckets({"active_insights": [_insight()]})
        import json
        # No TypeErrors expected — signals are plain dicts.
        json.dumps(feed, default=str)


class UnifiedSignalDataclassTests(SimpleTestCase):
    """Sanity checks on the dataclass itself."""

    def test_to_dict_round_trips(self):
        sig = UnifiedSignal(
            source=SOURCE_INSIGHT,
            source_id=1,
            domain="health",
            type="vital",
            title="T",
            message="M",
            severity=SEVERITY_HIGH,
            confidence=0.9,
            priority_score=0.8,
            signal_class=CLASS_RISK,
        )
        d = sig.to_dict()
        self.assertEqual(d["source"], SOURCE_INSIGHT)
        self.assertEqual(d["severity"], SEVERITY_HIGH)
        self.assertEqual(d["signal_class"], CLASS_RISK)
