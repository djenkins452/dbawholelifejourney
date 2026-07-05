# ==============================================================================
# File: apps/ai/tests/test_executive_pattern.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Executive Pattern Discovery is whole-life executive synthesis, not a
#   restated domain trend. "What pattern do you see in my life that I probably don't
#   recognize yet?" previously fell to a generic LLM that surfaced "protein below
#   target" — a single-domain dashboard trend. An executive pattern must reveal
#   something NON-OBVIOUS, synthesized from already-computed whole-life sources (EAE
#   derived patterns → CDCE correlations → cross-domain insight/prediction), ranked by
#   executive value. A raw single-domain trend can NEVER be the pattern; if nothing
#   clears the bar, the answer is honest and explains why.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_intelligence import whole_life_patterns
from apps.ai.chatgpt_cos.executive_interpretation import _pattern_assessment
from apps.ai.chatgpt_cos.lanes import _executive_pattern_lane

User = get_user_model()
_PAT = "apps.ai.chatgpt_cos.lanes._executive_pattern"


def _derived_pattern(user, signal_type, score=0.8, confidence=0.7, domain="health"):
    from apps.core.ai_eae.models import SignalSnapshot
    return SignalSnapshot.objects.create(
        user=user, date=timezone.now().date(), signal_type=signal_type, domain=domain,
        signal_class="derived_pattern", score=score, confidence=confidence,
        source_signals={"pattern_rule": "test"})


def _correlation(user, a="sleep", b="journal", score=0.9, narrative="On 7h+ nights your mood entries are more positive."):
    from apps.core.ai_cross_domain.models import DomainCorrelation
    return DomainCorrelation.objects.create(
        user=user, domain_a=a, domain_b=b, correlation_type=f"{a}_{b}",
        strength="strong", strength_score=score, direction="positive",
        narrative=narrative, evidence_summary="42 nights", data_points=42,
        dedupe_key=f"c_{a}_{b}", status="active")


def _protein_trend(user):
    from apps.core.ai_insights.models import Insight
    return Insight.objects.create(
        user=user, module="nutrition", insight_type="protein_trend", severity="warning",
        title="Protein consistently below target", message="3 weeks under 60% of target",
        explain_why="from your logged meals", dedupe_key="pi1", confidence_score=0.82,
        status="new")


class WholeLifePatternSourceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="wlp@test.com", password="x")

    def test_single_domain_trend_is_observation_never_a_candidate(self):
        _protein_trend(self.user)
        data = whole_life_patterns(self.user)
        self.assertEqual(data["candidates"], [])                 # protein is NOT a pattern
        self.assertIsNotNone(data["observation"])
        self.assertIn("protein", data["observation"]["text"].lower())
        self.assertEqual(data["observation"]["module"], "nutrition")

    def test_eae_derived_pattern_is_a_candidate(self):
        _derived_pattern(self.user, "domain_neglect", confidence=0.7)
        data = whole_life_patterns(self.user)
        self.assertTrue(data["candidates"])
        self.assertEqual(data["candidates"][0]["source"], "eae_pattern")
        self.assertIn("sliding", data["candidates"][0]["text"])

    def test_cdce_correlation_is_a_candidate(self):
        _correlation(self.user)
        data = whole_life_patterns(self.user)
        srcs = [c["source"] for c in data["candidates"]]
        self.assertIn("cdce_correlation", srcs)

    def test_eae_pattern_outranks_correlation_by_source_priority(self):
        # CDCE correlation has HIGHER confidence, but EAE derived pattern wins on the
        # spec's source priority (EAE > CDCE > cross-domain).
        _correlation(self.user, score=0.95)
        _derived_pattern(self.user, "domain_neglect", confidence=0.6)
        assessed = _pattern_assessment(self.user)
        self.assertIn("action", assessed)
        self.assertIn("sliding", assessed["text"])               # the EAE pattern won


class PatternAssessmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="pa@test.com", password="x")

    def test_qualifying_pattern_becomes_the_assessment(self):
        _derived_pattern(self.user, "holistic_momentum", confidence=0.75)
        assessed = _pattern_assessment(self.user)
        self.assertIn("action", assessed)
        self.assertIn("momentum", assessed["text"].lower())

    def test_below_threshold_does_not_clear_the_bar(self):
        _derived_pattern(self.user, "recovery_risk", confidence=0.2)   # under 0.40 floor
        _protein_trend(self.user)
        assessed = _pattern_assessment(self.user)
        self.assertNotIn("action", assessed)                     # no executive pattern
        self.assertIsNotNone(assessed["observation"])            # protein held as observation

    def test_nothing_at_all_is_honest_empty(self):
        assessed = _pattern_assessment(self.user)
        self.assertNotIn("action", assessed)
        self.assertIsNone(assessed.get("observation"))


class ExecutivePatternLaneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="epl@test.com", password="x")

    Q = "What pattern do you see in my life that I probably don't recognize yet?"

    def test_presents_a_real_whole_life_pattern(self):
        pat = {"text": "one whole area of your life has been quietly sliding while your attention sits elsewhere",
               "basis": "a derived whole-life pattern (domain neglect) WLJ computed across your signals",
               "action": "give that neglected area one deliberate touch this week"}
        with mock.patch(_PAT, return_value=pat):
            out = _executive_pattern_lane(self.user, self.Q)
        self.assertEqual(out["lane"], "executive_pattern")
        low = out["answer"].lower()
        self.assertIn("pattern you probably haven't connected", low)
        self.assertIn("sliding", low)

    def test_no_pattern_is_honest_and_never_presents_protein_as_the_pattern(self):
        # The production failure: protein must NEVER be returned as the pattern. With no
        # whole-life pattern, the answer says so, names protein as an OBSERVATION (not a
        # pattern), and says what would promote it.
        with mock.patch(_PAT, return_value={"observation": {"text": "Protein consistently below target",
                                                            "module": "nutrition"}}):
            out = _executive_pattern_lane(self.user, self.Q)
        low = out["answer"].lower()
        self.assertIn("no whole-life pattern clears the bar", low)     # (1) honest
        self.assertIn("not a pattern", low)                            # (3) labeled NOT a pattern
        self.assertIn("nutrition observation", low)                    # (3) the strongest trend
        self.assertIn("would become an executive pattern", low)        # (4) promotion path
        # protein appears ONLY as the disqualified observation, never as "the pattern"
        self.assertNotIn("pattern you probably haven't connected", low)

    def test_no_pattern_and_no_observation_still_honest(self):
        with mock.patch(_PAT, return_value={"observation": None}):
            out = _executive_pattern_lane(self.user, self.Q)
        low = out["answer"].lower()
        self.assertIn("no whole-life pattern clears the bar", low)
        self.assertIn("enough evidence", low)

    def test_domain_scoped_pattern_yields_to_domain_reasoning(self):
        self.assertIsNone(_executive_pattern_lane(self.user, "what's the pattern in my sleep?"))
        self.assertIsNone(_executive_pattern_lane(self.user, "any pattern in my weight lately?"))

    def test_unrelated_message_not_claimed(self):
        self.assertIsNone(_executive_pattern_lane(self.user, "what's my glucose right now?"))
