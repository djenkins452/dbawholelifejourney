"""Health Analyze v1 — question differentiation, time-awareness, signal
prioritization, single-lever selection, bounded judgment. All deterministic."""

from datetime import datetime
from unittest import mock

from django.test import SimpleTestCase

from apps.ai.cognitive_mode import health_analyze_v1 as v1


_HEALTH = {
    "weight_current": 289.9, "weight_unit": "lb", "weight_trend": "decreasing",
    "weight_change_30d": -3.8,
    "glucose_summary": {"trend_7d_vs_30d": "improving", "average_7d": 105,
                        "time_in_range_pct_7d": 72},
    "glucose_context": "Normal", "glucose_avg_7d": 105,
    "sleep_avg_hours_7d": 6.3, "sleep_trend": "stable",
    "sleep_consistency_score": 45,
    "body_composition": {
        "delta": {"waist": -0.5, "lean_mass": 0.2, "arm_left": 0.3},
        "largest_improvement": {"metric": "waist", "label": "Waist down 0.5 in"},
        "largest_regression": {},
    },
}
_FITNESS = {"workouts_7d": 4, "workout_adherence_score": 80}
_NUTRITION = {"protein_compliance_pct": 60}


def _ctx(hour=13, health=None, fitness=None, nutrition=None):
    """Patch SAE state + user-local time."""
    state = {"health": health if health is not None else _HEALTH,
             "fitness": fitness if fitness is not None else _FITNESS,
             "nutrition": nutrition if nutrition is not None else _NUTRITION}

    def _fake_state(user, module, *a, **k):
        return state.get(module, {})

    def _fake_now(user):
        return datetime(2026, 6, 8, hour, 0, 0)

    return mock.patch.multiple(
        "apps.core.ai_state.state_engine", get_module_state=mock.DEFAULT
    ), _fake_state, _fake_now


def _run(qmsg, hour=13, **state_over):
    with mock.patch("apps.core.ai_state.state_engine.get_module_state") as gms, \
         mock.patch("apps.core.utils.get_user_now") as now:
        s = {"health": state_over.get("health", _HEALTH),
             "fitness": state_over.get("fitness", _FITNESS),
             "nutrition": state_over.get("nutrition", _NUTRITION)}
        gms.side_effect = lambda u, m, *a, **k: s.get(m, {})
        now.side_effect = lambda u: datetime(2026, 6, 8, hour, 0, 0)
        return v1.build_health_analyze(object(), qmsg)


class ClassificationTests(SimpleTestCase):
    def test_question_typing(self):
        self.assertEqual(v1.classify_analyze_question("what do you think about my weight history?"), "weight_history")
        self.assertEqual(v1.classify_analyze_question("how am i doing overall with my health?"), "overall")
        self.assertEqual(v1.classify_analyze_question("what patterns do you notice lately?"), "patterns")
        self.assertEqual(v1.classify_analyze_question("do you think i need to change anything?"), "one_thing")
        self.assertEqual(v1.classify_analyze_question("if you only picked one thing what would it be?"), "one_thing")
        self.assertEqual(v1.classify_analyze_question("what concerns you most?"), "concern")
        self.assertEqual(v1.classify_analyze_question("am i losing weight too quickly?"), "pace_check")
        self.assertEqual(v1.classify_analyze_question("am i overtraining?"), "overtraining")

    def test_judgment_trigger(self):
        self.assertTrue(v1.is_health_judgment_request("am i losing weight too quickly?"))
        self.assertTrue(v1.is_health_judgment_request("am i overtraining?"))
        self.assertFalse(v1.is_health_judgment_request("what is my weight?"))


class DifferentiationTests(SimpleTestCase):
    def test_four_questions_produce_distinct_answers(self):
        wh = _run("what do you think about my weight history?")
        ov = _run("how am i doing overall with my health?")
        pa = _run("what patterns do you notice lately?")
        ch = _run("do you think i need to change anything?")
        outs = [wh, ov, pa, ch]
        for o in outs:
            self.assertTrue(o)
        # Pairwise distinct — no shared template.
        self.assertEqual(len(set(outs)), 4)

    def test_weight_history_shape(self):
        out = _run("what do you think about my weight history?")
        self.assertIn("sustainable", out.lower())
        self.assertIn("glucose", out.lower())
        self.assertNotIn("What I notice:", out)  # not the v0 bullet template

    def test_overall_is_holistic_not_weight_only(self):
        out = _run("how am i doing overall with my health?")
        self.assertIn("overall", out.lower())
        self.assertTrue("consistency" in out.lower() or "recovery" in out.lower())

    def test_patterns_is_observational(self):
        out = _run("what patterns do you notice lately?")
        self.assertIn("pattern", out.lower())


class SignalPrioritizationTests(SimpleTestCase):
    def test_arm_measurement_noise_not_surfaced(self):
        # body_composition has arm_left delta, but it must NEVER appear.
        for q in ("what do you think about my weight history?",
                  "how am i doing overall with my health?"):
            out = _run(q)
            self.assertNotIn("arm", out.lower())


class TimeAwarenessTests(SimpleTestCase):
    def test_morning_no_compliance_guilt(self):
        # Morning + protein 0% must NOT produce a raw metric / "behind" guilt.
        out = _run("do you think i need to change anything?", hour=7,
                   nutrition={"protein_compliance_pct": 0})
        for bad in ("0.0", "/100", "behind", "under target"):
            self.assertNotIn(bad, out.lower())
        self.assertIn("early in the day", out.lower())

    def test_nutrition_lever_eligibility_by_time(self):
        # Nutrition refinement is excluded in the morning, eligible in the evening.
        sigs = {"weight": {"trend": "stable"}, "nutrition": {"protein_pct": 40}}
        morning = v1.leverage_ranked(sigs, "morning")
        evening = v1.leverage_ranked(sigs, "evening")
        self.assertFalse(any("protein" in p for _, p, _ in morning))
        self.assertTrue(any("protein" in p for _, p, _ in evening))


class LeverSelectionTests(SimpleTestCase):
    def test_lever_is_not_a_raw_metric(self):
        # The lever must be a coaching behavior, never a dashboard metric.
        out = _run("do you think i need to change anything?", hour=20,
                   fitness={"workouts_7d": 0},
                   nutrition={"protein_compliance_pct": 40})
        self.assertNotIn("compliance", out.lower())
        self.assertNotIn("0.0", out)
        self.assertIn("muscle", out.lower())  # highest-leverage during a cut

    def test_no_lever_when_stable_and_all_good(self):
        # Not in a cut (stable) + everything good → no change needed.
        out = _run("do you think i need to change anything?", hour=20,
                   fitness={"workouts_7d": 5},
                   nutrition={"protein_compliance_pct": 95},
                   health={**_HEALTH, "weight_trend": "stable",
                           "sleep_avg_hours_7d": 7.5,
                           "sleep_consistency_score": 85, "sleep_trend": "stable"})
        self.assertIn("wouldn't change anything", out.lower())


class BoundedJudgmentTests(SimpleTestCase):
    def test_pace_sustainable(self):
        out = _run("am i losing weight too quickly?")
        self.assertIn("don't think you're losing too quickly", out.lower())

    def test_pace_fast(self):
        # -22 lb/30d ≈ 1.77%/week → above the 1.25% sustainable ceiling.
        out = _run("am i losing weight too quickly?",
                   health={**_HEALTH, "weight_change_30d": -22.0})
        self.assertIn("faster", out.lower())

    def test_overtraining_low_risk(self):
        out = _run("am i overtraining?", fitness={"workouts_7d": 3})
        self.assertIn("overtraining", out.lower())


class LeverageCoachingTests(SimpleTestCase):
    """Failure 2/3 — leverage ranking (not lowest-score) + time-aware coaching."""

    def test_concern_leads_with_protect_not_lowest_metric(self):
        # protein 0 (the 'lowest metric') must NOT be the headline concern.
        out = _run("what concerns you most?", hour=20,
                   nutrition={"protein_compliance_pct": 0})
        self.assertNotIn("0.0", out)
        self.assertNotIn("compliance", out.lower())
        self.assertIn("encouraged", out.lower())  # positive framing
        self.assertIn("muscle", out.lower())       # highest-leverage protect

    def test_one_thing_at_5am_skips_nutrition(self):
        # Failure 2: a raw "macro compliance 0.0/100" must NOT be the answer.
        out = _run("if you only picked one thing, what would it be?", hour=5,
                   nutrition={"protein_compliance_pct": 0})
        for bad in ("0.0", "/100", "behind", "under target"):
            self.assertNotIn(bad, out.lower())
        self.assertIn("early in the day", out.lower())  # temporal awareness
        self.assertIn("muscle", out.lower())            # high-leverage lever

    def test_muscle_preservation_is_top_lever_when_losing_well(self):
        # Lean mass dropping → muscle preservation must rank first.
        out = _run("if you picked one thing?", hour=14,
                   health={**_HEALTH, "body_composition": {
                       "delta": {"lean_mass": -1.2}, "largest_improvement": {},
                       "largest_regression": {}}})
        self.assertIn("muscle", out.lower())


class ContinuityTests(SimpleTestCase):
    """Failure 4 — bounded thread continuity."""

    def test_followup_detection(self):
        self.assertTrue(v1.is_health_followup("why?"))
        self.assertTrue(v1.is_health_followup("tell me more"))
        self.assertTrue(v1.is_health_followup("what would you do?"))
        self.assertFalse(v1.is_health_followup("what is my weight?"))
        # bare 'why' only on short messages
        self.assertFalse(v1.is_health_followup(
            "why does the app keep logging me out when i open the journal page"))

    def test_store_and_deepen_round_trip(self):
        from django.core.cache import cache
        conv = type("C", (), {"id": 99})()
        cache.delete("beth:hctx:99")
        # Produce an analysis (stores context)
        with mock.patch("apps.core.ai_state.state_engine.get_module_state") as g, \
             mock.patch("apps.core.utils.get_user_now") as now:
            s = {"health": _HEALTH, "fitness": _FITNESS, "nutrition": _NUTRITION}
            g.side_effect = lambda u, m, *a, **k: s.get(m, {})
            now.side_effect = lambda u: datetime(2026, 6, 8, 14, 0, 0)
            v1.build_health_analyze(object(), "what concerns you most?", conversation=conv)
            # Follow-up inherits the thread
            deep = v1.build_deepen(object(), "why?", conv)
        self.assertTrue(deep)
        self.assertNotIn("what concerns", deep.lower())  # not a restart
        cache.delete("beth:hctx:99")

    def test_deepen_without_context_returns_none(self):
        conv = type("C", (), {"id": 12345})()
        from django.core.cache import cache
        cache.delete("beth:hctx:12345")
        self.assertIsNone(v1.build_deepen(object(), "why?", conv))

    def test_continuity_disabled(self):
        conv = type("C", (), {"id": 77})()
        with self.settings(WLJ_BETH_HEALTH_CONTINUITY=False):
            v1.store_health_context(conv, "concern", {}, "midday")
            self.assertIsNone(v1.get_health_context(conv))


class V16CoachingRoutingTests(SimpleTestCase):
    """v1.6 — coaching questions reach the leverage lane (root fix for the
    'macro compliance 0.0/100' overfitting)."""

    def test_coaching_triggers_recognized(self):
        for q in ("what concerns you most?",
                  "if you only picked one thing what would it be?",
                  "should i change anything?",
                  "what would you do if you were me?"):
            self.assertTrue(v1.is_health_coaching_request(q), msg=q)

    def test_other_domain_excluded(self):
        self.assertTrue(v1.mentions_non_health_domain("what concerns you most about my budget?"))
        self.assertTrue(v1.mentions_non_health_domain("what would you do about my project deadline?"))
        self.assertFalse(v1.mentions_non_health_domain("what concerns you most?"))

    def test_standalone_concern_is_leverage_not_macro(self):
        # No health token, no thread — still answers via leverage, not macros.
        out = _run("what concerns you most?", hour=14,
                   nutrition={"protein_compliance_pct": 0})
        self.assertNotIn("0.0", out)
        self.assertNotIn("/100", out)
        self.assertIn("muscle", out.lower())


class ExplicitHealthIntentTests(SimpleTestCase):
    """Regression: explicit health-status intent must hard-route to the health
    analyze lane, outranking continuity / check-in / operational routing.
    (Bug: 'How am I doing with my health?' returned the operational task
    backlog because is_analyze_request didn't recognize the phrasing.)"""

    def test_explicit_health_phrasings_recognized(self):
        for q in ("how am i doing with my health?",
                  "how is my health?",
                  "how am i doing physically?",
                  "am i healthy?",
                  "am i in good health?",
                  "what concerns you about my health?"):
            self.assertTrue(v1.is_explicit_health_intent(q), msg=q)

    def test_operational_and_cross_domain_not_hijacked(self):
        # Must NOT trip on operational, ambiguous, or other-domain phrasings.
        for q in ("check in",
                  "what should i do next?",
                  "how is my progress?",          # ambiguous (goals) — defer
                  "how am i doing on protein today?",  # nutrition route owns this
                  "how am i doing with my work?",
                  "how am i doing with my prayer life?",
                  "tell me more",
                  "how am i doing"):
            self.assertFalse(v1.is_explicit_health_intent(q), msg=q)

    def test_router_wires_explicit_health_ahead_of_continuity(self):
        import inspect
        from apps.ai import deterministic_router as dr
        src = inspect.getsource(dr.classify_and_route)
        self.assertIn("is_explicit_health_intent", src)
        # continuity follow-up must yield to explicit health intent
        self.assertIn("not _explicit_health", src)


class OverallFrameVariationTests(SimpleTestCase):
    """Polish: near-identical health phrasings get distinct FRAMING but the same
    facts (deterministic, no randomness, no new data)."""

    SIG = {"weight": {"trend": "decreasing"}, "glucose": {"trend": "improving"},
           "workouts": {"count": 4}, "sleep": {"avg": 6.4},
           "nutrition": {"band": "midday", "protein_pct": 70}}

    def test_frame_classification(self):
        self.assertEqual(v1._overall_frame("how am i doing with my health"), "executive")
        self.assertEqual(v1._overall_frame("how is my health"), "state")
        self.assertEqual(v1._overall_frame("how am i doing physically"), "physical")
        self.assertEqual(v1._overall_frame("am i healthy"), "evaluative")

    def test_four_phrasings_produce_distinct_leads(self):
        outs = {f: v1._compose_overall(self.SIG, f)
                for f in ("executive", "state", "physical", "evaluative")}
        leads = {o.split(".")[0] for o in outs.values()}
        self.assertEqual(len(leads), 4, "framing must differ across the 4 phrasings")
        self.assertIn("executive read", outs["executive"])
        self.assertIn("Physically", outs["physical"])
        self.assertIn("Healthier than you were", outs["evaluative"])

    def test_same_facts_across_frames(self):
        # The underlying signal facts (improving set, opportunity, closing) are
        # identical — only framing changes.
        for f in ("executive", "state", "physical", "evaluative"):
            out = v1._compose_overall(self.SIG, f)
            self.assertIn("weight, glucose and workout consistency are improving", out.lower())
            self.assertIn("recovery and consistency", out)
            self.assertIn("don't think you need dramatic changes", out)

    def test_evaluative_verdict_gated_on_momentum(self):
        # No momentum -> must NOT claim 'healthier than you were' (ungrounded).
        flat = {"weight": {"trend": "stable"}, "glucose": {"trend": "stable"},
                "workouts": {"count": 1}, "sleep": {"avg": 7.5}}
        out = v1._compose_overall(flat, "evaluative")
        self.assertNotIn("Healthier than you were", out)
        self.assertIn("stable shape", out)


class AmbiguousProgressTests(SimpleTestCase):
    """Polish: 'how is my progress?' is thread-aware, not rigidly health."""

    def test_ambiguous_detected(self):
        for q in ("how is my progress?", "how am i progressing?",
                  "am i making progress?"):
            self.assertTrue(v1.is_ambiguous_progress_query(q), msg=q)

    def test_domain_specific_progress_not_ambiguous(self):
        for q in ("how is my health progress?", "how is my weight progress",
                  "how is my work progress?", "how am i doing with my health?"):
            self.assertFalse(v1.is_ambiguous_progress_query(q), msg=q)

    def test_thread_aware_framing_instruction(self):
        from django.core.cache import cache
        from apps.ai.personal_assistant import _build_progress_framing_instruction as f

        class _C:
            id = 9911
        cache.clear()
        conv = _C()
        # No health thread -> holistic
        self.assertIn("HOLISTICALLY", f("how is my progress?", conv))
        # Health thread active -> health progress
        v1.store_health_context(conv, "overall", {"weight": {"trend": "decreasing"}}, "midday")
        self.assertIn("HEALTH progress", f("how is my progress?", conv))
        # Non-progress question -> no instruction
        self.assertEqual(f("how is my health?", conv), "")


class V16IntensityTests(SimpleTestCase):
    """v1.6 Failure 3 — situational judgment, not reflexive agreement."""

    def test_train_harder_routes_and_pushes_back(self):
        self.assertEqual(v1.classify_analyze_question("should i work out harder?"), "intensity_check")
        self.assertTrue(v1.is_health_judgment_request("should i work out harder?"))
        out = _run("should i work out harder?", hour=14)
        self.assertIn("not convinced", out.lower())
        self.assertNotIn("sure", out.lower())

    def test_train_harder_when_recovery_lagging(self):
        out = _run("should i train harder?", hour=14,
                   health={**_HEALTH, "sleep_avg_hours_7d": 5.2, "sleep_trend": "declining"})
        self.assertIn("recovery", out.lower())


class V16DeepenTests(SimpleTestCase):
    """v1.6 Failure 2 — 'go deeper' gives substantive depth."""

    def test_go_deeper_gives_muscle_depth(self):
        from django.core.cache import cache
        conv = type("C", (), {"id": 808})()
        cache.delete("beth:hctx:808")
        with mock.patch("apps.core.ai_state.state_engine.get_module_state") as g, \
             mock.patch("apps.core.utils.get_user_now") as now:
            s = {"health": _HEALTH, "fitness": _FITNESS, "nutrition": _NUTRITION}
            g.side_effect = lambda u, m, *a, **k: s.get(m, {})
            now.side_effect = lambda u: datetime(2026, 6, 9, 14, 0, 0)
            v1.build_health_analyze(object(), "what concerns you most?", conversation=conv)
            deep = v1.build_deepen(object(), "go deeper", conv)
        self.assertIn("muscle", deep.lower())
        self.assertTrue("metabolism" in deep.lower() or "sustainable" in deep.lower())
        cache.delete("beth:hctx:808")


class V17ProgressiveDeepeningTests(SimpleTestCase):
    """v1.7 — follow-ups serve NEW reasoning layers, never repeat the same one."""

    def _thread(self, conv_id):
        from django.core.cache import cache
        conv = type("C", (), {"id": conv_id})()
        cache.delete(f"beth:hctx:{conv_id}")
        with mock.patch("apps.core.ai_state.state_engine.get_module_state") as g, \
             mock.patch("apps.core.utils.get_user_now") as now:
            s = {"health": _HEALTH, "fitness": _FITNESS, "nutrition": _NUTRITION}
            g.side_effect = lambda u, m, *a, **k: s.get(m, {})
            now.side_effect = lambda u: datetime(2026, 6, 9, 14, 0, 0)
            concern = v1.build_health_analyze(object(), "what concerns you most?", conversation=conv)
            seq = [v1.build_deepen(object(), q, conv) for q in
                   ("why?", "what would you do?", "go deeper", "go deeper")]
        cache.delete(f"beth:hctx:{conv_id}")
        return concern, seq

    def test_each_followup_is_distinct(self):
        _, seq = self._thread(1710)
        # The four follow-up answers must all differ — no looped sentence.
        self.assertEqual(len(set(seq)), 4, msg=seq)

    def test_layers_progress_in_order(self):
        _, seq = self._thread(1711)
        why, action, deeper, longterm = seq
        self.assertIn("cost muscle", why.lower())
        # action layer is now practical/specific (lifting + protein, not abstract)
        self.assertIn("lifting", action.lower())
        self.assertIn("protein", action.lower())
        self.assertIn("insulin", deeper.lower())
        self.assertTrue("rebound" in longterm.lower() or "long term" in longterm.lower())

    def test_exhaustion_synthesizes_not_repeats(self):
        from django.core.cache import cache
        conv = type("C", (), {"id": 1712})()
        cache.delete("beth:hctx:1712")
        with mock.patch("apps.core.ai_state.state_engine.get_module_state") as g, \
             mock.patch("apps.core.utils.get_user_now") as now:
            s = {"health": _HEALTH, "fitness": _FITNESS, "nutrition": _NUTRITION}
            g.side_effect = lambda u, m, *a, **k: s.get(m, {})
            now.side_effect = lambda u: datetime(2026, 6, 9, 14, 0, 0)
            v1.build_health_analyze(object(), "what concerns you most?", conversation=conv)
            for q in ("why?", "what would you do?", "go deeper", "go deeper"):
                v1.build_deepen(object(), q, conv)
            final = v1.build_deepen(object(), "go deeper", conv)
        self.assertIn("core of it", final.lower())
        cache.delete("beth:hctx:1712")

    def test_lever_key_mapping(self):
        self.assertEqual(v1._lever_key("protecting muscle while the weight comes down"), "muscle")
        self.assertEqual(v1._lever_key("improving sleep consistency"), "sleep")
        self.assertEqual(v1._lever_key("getting workout frequency back up"), "workout")

    def test_concern_is_high_level_not_mechanism(self):
        # v1.7.1: concern stays high-level so 'Why?' adds the mechanism (no overlap).
        out = _run("what concerns you most?", hour=14)
        self.assertIn("muscle", out.lower())
        self.assertNotIn("because", out.lower())  # mechanism moved to the Why? layer

    def test_why_after_concern_adds_mechanism(self):
        from django.core.cache import cache
        conv = type("C", (), {"id": 1720})()
        cache.delete("beth:hctx:1720")
        with mock.patch("apps.core.ai_state.state_engine.get_module_state") as g, \
             mock.patch("apps.core.utils.get_user_now") as now:
            s = {"health": _HEALTH, "fitness": _FITNESS, "nutrition": _NUTRITION}
            g.side_effect = lambda u, m, *a, **k: s.get(m, {})
            now.side_effect = lambda u: datetime(2026, 6, 9, 14, 0, 0)
            concern = v1.build_health_analyze(object(), "what concerns you most?", conversation=conv)
            why = v1.build_deepen(object(), "why?", conv)
            first_deeper = v1.build_deepen(object(), "go deeper", conv)
        # Why adds mechanism; first 'go deeper' advances (action), not a why repeat.
        self.assertIn("cost muscle", why.lower())
        self.assertNotEqual(why, first_deeper)
        self.assertIn("lifting", first_deeper.lower())  # action layer, not why again
        cache.delete("beth:hctx:1720")


class V16VariationTests(SimpleTestCase):
    def test_variant_is_deterministic_and_bounded(self):
        opts = ["a", "b", "c"]
        self.assertEqual(v1._variant(opts, "seed1"), v1._variant(opts, "seed1"))
        self.assertIn(v1._variant(opts, "seed1"), opts)

    def test_concern_opener_varies_across_questions(self):
        a = _run("what concerns you most?", hour=14)
        b = _run("what worries you most right now?", hour=14)
        # Both still encouraging, but not necessarily identical wording.
        self.assertIn("encouraged", a.lower())
        self.assertIn("encouraged", b.lower())


class FallbackTests(SimpleTestCase):
    def test_no_data_returns_none(self):
        out = _run("what do you think about my weight history?",
                   health={}, fitness={}, nutrition={})
        self.assertIsNone(out)

    def test_disabled_returns_none(self):
        with self.settings(WLJ_BETH_HEALTH_ANALYZE_V1=False):
            out = _run("how am i doing overall?")
        self.assertIsNone(out)
