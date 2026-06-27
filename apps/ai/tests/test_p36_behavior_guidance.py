# ==============================================================================
# File: apps/ai/tests/test_p36_behavior_guidance.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P36 Personal Knowledge — Layer 4 (Behavior Guidance). Tests that Beth
#   UNDERSTANDS (not just remembers): knowledge compresses (one row per key), evolves
#   (confidence ↑ on reinforcement, ↓ on contradiction), is explainable (traces to
#   evidence), and — the whole point — CHANGES behavior downstream (a learned
#   "deprioritize" directive removes an item from the executive brief). Behavior
#   changes because KNOWLEDGE exists, not because a prompt changed.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.ai_memory.models import BehaviorDirective
from apps.ai.chatgpt_cos import behavior_guidance as bg
from apps.ai.chatgpt_cos import executive_brief as eb
from apps.ai.chatgpt_cos import executive_interpretation as ei

User = get_user_model()
_HZN = "apps.ai.chatgpt_cos.executive_interpretation._task_horizons"
_ESM = "apps.ai.chatgpt_cos.executive_interpretation._exec_summary"
_HEALTH = "apps.ai.chatgpt_cos.executive_interpretation._health_read"
_RHYTHM = "apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items"
_NOW = "apps.core.utils.get_user_now"


class KnowledgeLifecycleTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(email="p36k@example.com", password="x")

    def test_learning_compresses_not_duplicates(self):
        for _ in range(3):                      # "Danny journals" observed 3×
            bg.learn(self.u, "deprioritize:shower", observation="Delays weekend showers",
                     behavior_change="Don't elevate shower timing", source="observed")
        rows = BehaviorDirective.objects.filter(user=self.u, key="deprioritize:shower")
        self.assertEqual(rows.count(), 1)        # ONE row, not three
        d = rows.first()
        self.assertEqual(d.evidence_count, 3)    # but richer (reinforced)
        self.assertGreater(d.confidence, 0.55)   # confidence grew

    def test_source_sets_confidence(self):
        told = bg.learn(self.u, "tone:direct", observation="Asked for blunt feedback",
                        behavior_change="Be direct", source="told")
        observed = bg.learn(self.u, "recovery_activity:ride", observation="Rides to reset",
                            behavior_change="Suggest a ride", source="observed")
        self.assertGreater(told.confidence, observed.confidence)   # told > observed

    def test_contradiction_weakens_then_retires(self):
        bg.learn(self.u, "deprioritize:shower", observation="x",
                 behavior_change="don't elevate", source="observed")
        bg.contradict(self.u, "deprioritize:shower", by=0.2)
        d = BehaviorDirective.objects.get(user=self.u, key="deprioritize:shower")
        self.assertIn(d.status, ("weak", "retired"))
        bg.contradict(self.u, "deprioritize:shower", by=0.9)
        d.refresh_from_db()
        self.assertEqual(d.status, "retired")

    def test_explainability_traces_to_evidence(self):
        bg.learn(self.u, "tone:direct", observation="Danny asked for blunt feedback twice",
                 behavior_change="Challenge rather than over-reassure", source="told",
                 evidence="said so on 2026-06-01 and 2026-06-15")
        text = bg.explain(self.u, "tone:direct")
        self.assertIn("danny asked for blunt feedback", text.lower())
        self.assertIn("told", text.lower())          # source
        self.assertIn("confident", text.lower())     # confidence
        self.assertIn("challenge", text.lower())     # behavior change

    def test_low_confidence_directive_is_not_actionable(self):
        d = bg.learn(self.u, "deprioritize:shower", observation="x",
                     behavior_change="y", source="derived")  # starts at 0.5
        bg.contradict(self.u, "deprioritize:shower", by=0.2)  # -> 0.3, weak
        self.assertNotIn("deprioritize:shower", bg.directive_map(self.u))


class BehaviorChangesBecauseKnowledgeExistsTests(TestCase):
    """The core P36 proof: the SAME day produces a DIFFERENT brief once Beth has
    learned a behavior directive — no prompt change, just knowledge."""
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.u = User.objects.create_user(email="p36b@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()

    def _brief(self):
        from datetime import datetime, timezone as _tz
        noon = datetime(2026, 6, 27, 12, 5, tzinfo=_tz.utc)
        items = [{"title": "Shower", "scheduled_time": "13:00"},      # future
                 {"title": "Workout", "scheduled_time": "14:00"}]
        with mock.patch(_HZN, return_value={"today": 1, "overdue": 0, "soon": 2,
                                            "backlog": 5, "total": 8}), \
             mock.patch(_ESM, return_value={}), \
             mock.patch(_HEALTH, return_value={"recovery_needed": False, "read": "stable",
                                               "note": "", "sleep_hours": None}), \
             mock.patch(_RHYTHM, return_value=items), mock.patch(_NOW, return_value=noon):
            return eb.compose_executive_brief(self.u).lower()

    def test_learned_deprioritize_removes_item_from_brief(self):
        # before learning: the shower IS in the agenda
        before = self._brief()
        self.assertIn("shower", before)
        # Beth LEARNS that weekend shower timing isn't a useful priority
        bg.learn(self.u, "deprioritize:shower",
                 observation="Danny typically delays showering on weekends",
                 meaning="Weekend shower timing isn't an indicator of discipline",
                 behavior_change="Don't elevate weekend shower timing into priorities",
                 source="observed")
        bg.learn(self.u, "deprioritize:shower", observation="again", source="observed",
                 behavior_change="x")   # reinforce past the actionable threshold
        # after learning: the SAME day no longer surfaces the shower
        after = self._brief()
        self.assertNotIn("shower", after)
        self.assertIn("workout", after)        # other items unaffected

    def test_no_directives_means_no_behavior_change(self):
        # defensive: a user with nothing learned gets the unchanged brief
        sig = ei.interpret(mock.Mock())
        self.assertEqual(sig.deprioritized, [])
        self.assertEqual(sig.tone, "")
