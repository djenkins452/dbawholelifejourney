"""Bounded Executive Synthesis Phase (Phase 2) — unit + generate() wiring tests.

Phase 1 investigates + gathers evidence; Phase 2 (same model, no tools) synthesizes the
executive judgment over that evidence, only for turns that drew on >=2 independent
substantive truth surfaces. Not judge-the-judge (Phase 2 never sees Phase 1's prose);
on failure the grounded Phase-1 answer is kept.
"""
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from apps.ai.model_interface import synthesis as S
from apps.ai.model_interface.service import ModelInterfaceService
from apps.users.models import TermsAcceptance

try:
    from apps.users.models import User
except ImportError:
    from django.contrib.auth import get_user_model
    User = get_user_model()


def _user(email):
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    p = u.preferences
    p.has_completed_onboarding = True
    p.use_model_interface = True
    p.save()
    return u


class EligibilityTests(TestCase):
    def test_is_substantive_truth(self):
        self.assertTrue(S.is_substantive_truth("get_analysis", {"holds_data": True}))
        self.assertTrue(S.is_substantive_truth("get_history", {"status": "ready"}))
        self.assertFalse(S.is_substantive_truth("get_analysis", {"status": "empty"}))
        self.assertFalse(S.is_substantive_truth("mutate_task", {"holds_data": True}))
        self.assertFalse(S.is_substantive_truth("get_analysis", {"status": "unsupported"}))

    def test_eligibility_needs_two_distinct_surfaces(self):
        one = [{"tool": "get_analysis", "args": {"domain": "health", "subject": "overall"}}]
        dup = one + [{"tool": "get_analysis", "args": {"domain": "health", "subject": "overall"}}]
        two = one + [{"tool": "get_analysis", "args": {"domain": "nutrition", "subject": "overall"}}]
        self.assertFalse(S.synthesis_eligible([]))          # narrow: 0 surfaces
        self.assertFalse(S.synthesis_eligible(one))         # narrow: 1 surface
        self.assertFalse(S.synthesis_eligible(dup))         # same surface twice != 2
        self.assertTrue(S.synthesis_eligible(two))          # 2 distinct domains -> eligible

    def test_render_evidence_compact_facts_pooled_scaffolding_stripped(self):
        ev = [{"tool": "get_analysis", "args": {"domain": "health", "subject": "overall"},
               "result": {"status": "ready", "holds_data": True, "scope": "long prose…",
                          "note": "facts only", "schema_version": "1", "generated_at": "x",
                          "concepts": {"body": {"members": {"weight": {
                              "label": "Weight", "value": "274.5", "unit": "lb", "change": "-9.2"}}}},
                          "subjects": {"weight": {"present": True,
                              "change": {"first": "280", "last": "274.5", "delta": "-5.5",
                                         "direction": "falling"}}}}}]
        out = S.render_evidence(ev)
        self.assertIn("health", out)
        self.assertIn("274.5", out)          # current value fact preserved
        self.assertIn("-9.2", out)           # concept change preserved
        self.assertIn("falling", out)        # trend fact preserved
        self.assertNotIn("long prose", out)  # scope scaffolding stripped
        self.assertNotIn("facts only", out)  # note stripped
        self.assertNotIn("schema_version", out)
        self.assertNotIn("{", out)           # compact flat facts, not nested json

    def test_build_orientation_strips_predecided_verdicts_keeps_facts(self):
        # The Phase-2 orientation must carry FACTS (who Danny is / what he's working toward)
        # but NEVER a pre-decided progress/drift verdict (momentum score/band, biggest_risk,
        # strategic summary) — handed one, the model narrated it as its own judgment with no
        # lineage to defend on challenge (proven on the live runtime 2026-08-14).
        sc = {
            "missions": {"g1": {"title": "Serve Others", "why_it_matters": "beyond self",
                                "progress": {"milestone_percent": 0, "momentum_score": 25,
                                             "momentum_7d_avg": 22}}},
            "current_action": {"primary_action": "Work on WLJ", "reason": "overdue foundational"},
            "personal_truth": {"summary": "Danny, faith-centered"},
            "deterministic_understanding": {
                "executive": {"biggest_risk": "sleep debt is the main thing to watch",
                              "primary_challenge": "workload"},
                "priority": {"executive": "batch the overdue tasks"},
                "direction": {"momentum": 25, "strategic_summary": "drifting rather than progressing"},
            },
        }
        out = S.build_orientation(sc)
        # Facts survive
        self.assertIn("Serve Others", out)
        self.assertIn("milestone_percent", out)
        self.assertIn("Work on WLJ", out)          # deterministic current action
        self.assertIn("faith-centered", out)       # personal truth
        # Pre-decided verdicts are gone
        self.assertNotIn("25", out)                        # momentum score
        self.assertNotIn("momentum", out.lower())          # any momentum score/band
        self.assertNotIn("biggest_risk", out)
        self.assertNotIn("sleep debt is the main thing", out)
        self.assertNotIn("primary_challenge", out)
        self.assertNotIn("strategic_summary", out)
        self.assertNotIn("drifting rather than progressing", out)
        self.assertNotIn("understanding_read", out)        # the whole du verdict block dropped

    def test_render_evidence_drops_verdict_labels_keeps_metric_facts(self):
        # A domain STATE may carry a scalar verdict label (momentum='low',
        # momentum_summary='behind pace') beside real facts. The verdict is stripped from the
        # Phase-2 evidence; the numeric facts are kept.
        ev = [{"tool": "get_analysis", "args": {"domain": "goals", "subject": "overall"},
               "result": {"status": "ready", "holds_data": True,
                          "state": {"momentum": "low", "momentum_summary": "behind pace",
                                    "recommended_action": "complete a task today",
                                    "milestones_completed": 3, "milestones_overdue": 1}}}]
        out = S.render_evidence(ev)
        self.assertIn("milestones_completed: 3", out)   # fact kept
        self.assertIn("milestones_overdue: 1", out)     # fact kept
        self.assertNotIn("behind pace", out)            # verdict stripped
        self.assertNotIn("momentum", out.lower())       # verdict stripped
        self.assertNotIn("complete a task today", out)  # prescription stripped

    def test_render_evidence_includes_ranked_entities_and_records(self):
        # Phase 2 must SEE the ranked entities + their sub-items and the actual entity
        # records — else it fabricates names/values (the "which workouts had the most volume
        # + PRs" → invented "squats/deadlifts" class, 2026-08-14). It previously kept only
        # the ranked scalar totals + `holds_data`.
        from apps.core.truth import envelope as _env
        ranked = {"status": "ready", "granularity": "ranked_entity", "unit": "lb",
                  "results": [{"rank": 1, "name": "Adjusted Upper Body — 2026-08-12",
                               "value": 13500.0, "occurred_on": "2026-08-12",
                               "meta": {"exercises": [{"name": "Seated Cable Row"},
                                                      {"name": "Lat Pulldown"}]}}]}
        analysis = {"status": "ready", "holds_data": True,
                    "records": {"count": 5, "records": [
                        {"identity": "Preacher Curl — Max Weight",
                         "performance": {"weight_lb": 60.0, "estimated_1rm_lb": 80.0}}]}}
        # WRAP exactly as dispatch does (make_envelope nests payload under "value") — the fix
        # must survive that, else Phase 2 sees only freshness/confidence/source scaffolding.
        wr = _env.make_envelope(ranked, source="ranked_entity:workout_by_volume",
                                status=_env.STATUS_OK)
        wa = _env.make_envelope(analysis, source="analysis:health.personal_records",
                                status=_env.STATUS_OK)
        out = S.render_evidence([
            {"tool": "get_ranked_entity", "args": {"subject": "workout_by_volume"},
             "result": wr},
            {"tool": "get_analysis", "args": {"domain": "health", "subject": "personal_records"},
             "result": wa}])
        self.assertIn("Adjusted Upper Body", out)      # the real ranked workout name
        self.assertIn("13500", out)
        self.assertIn("Seated Cable Row", out)         # its REAL exercises
        self.assertIn("Lat Pulldown", out)
        self.assertIn("Preacher Curl", out)            # the REAL PR record + value
        self.assertIn("60.0", out)
        self.assertNotIn("holds_data", out)            # scaffolding still stripped

    def test_run_executive_synthesis_single_bounded_call(self):
        # Phase 2 is a single, hard-bounded, no-retry client call (bypasses _call_api's retry
        # loop/circuit breaker so it can never hang a turn), no tools, bounded timeout.
        from types import SimpleNamespace
        captured = {}

        class FakeCompletions:
            def create(self, **kw):
                captured.update(kw)
                msg = SimpleNamespace(content="  My read is you're progressing on X.  ")
                return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        ai = SimpleNamespace(model="gpt-4o",
                             client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())),
                             _call_api=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not use _call_api")))
        ans = S.run_executive_synthesis(
            ai, message="how am I doing overall?",
            evidence=[{"tool": "get_analysis", "args": {"domain": "health"},
                       "result": {"holds_data": True, "subjects": {}}}],
            standing_context={"missions": {"primary": "France 2027"}})
        self.assertEqual(ans, "My read is you're progressing on X.")
        self.assertEqual(captured.get("timeout"), S.SYNTHESIS_TIMEOUT_SECONDS)  # bounded
        msgs = captured.get("messages")
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("SECOND phase", msgs[0]["content"])
        self.assertIn("France 2027", msgs[1]["content"])   # orientation carried
        self.assertNotIn("tools", captured)                # no tools

    def test_run_executive_synthesis_returns_empty_on_error(self):
        # On any client error/timeout, return "" so the caller keeps the grounded Phase-1 answer.
        from types import SimpleNamespace

        class Boom:
            def create(self, **kw):
                raise RuntimeError("timeout")
        ai = SimpleNamespace(model="gpt-4o",
                             client=SimpleNamespace(chat=SimpleNamespace(completions=Boom())))
        self.assertEqual(S.run_executive_synthesis(
            ai, message="q", evidence=[], standing_context={}), "")


class SynthesisTimeoutTests(TestCase):
    def test_synthesis_endpoint_has_full_timeout_not_utility(self):
        # Phase 2 is a large-prompt executive-judgment call; it must get the model_interface
        # timeout, never the 8s utility default (which would silently time out -> no synthesis).
        from apps.ai.services import (
            ENDPOINT_TIMEOUTS, LLM_TIMEOUT_MODEL_INTERFACE, LLM_TIMEOUT_UTILITY,
        )
        self.assertEqual(ENDPOINT_TIMEOUTS.get("model_interface_synthesis"),
                         LLM_TIMEOUT_MODEL_INTERFACE)
        self.assertNotEqual(ENDPOINT_TIMEOUTS.get("model_interface_synthesis"),
                            LLM_TIMEOUT_UTILITY)


class GenerateTwoPhaseWiringTests(TestCase):
    """generate() routes an eligible turn through Phase 2, keeps Phase-1 on failure,
    and stays single-phase for a narrow turn."""

    def setUp(self):
        self.user = _user("synth_wire@test.com")
        self.svc = ModelInterfaceService(self.user)
        from apps.ai.models import AssistantConversation
        self.conv = AssistantConversation.get_or_create_active(self.user)

    def _run(self, *, eligible, synth_answer):
        with patch.object(self.svc, "build_standing_context", return_value={"missions": {}}), \
             patch.object(self.svc, "_system_prompt", return_value="sys"), \
             patch.object(self.svc.ai, "_call_api_with_tools", return_value="PHASE1 DASHBOARD"), \
             patch("apps.ai.model_interface.synthesis.synthesis_eligible", return_value=eligible), \
             patch("apps.ai.model_interface.synthesis.run_executive_synthesis",
                   return_value=synth_answer):
            return self.svc.generate(self.conv, "how am I doing overall in my life?")

    def test_eligible_turn_uses_phase2_answer(self):
        out = self._run(eligible=True, synth_answer="PHASE2 JUDGMENT")
        self.assertEqual(out["answer"], "PHASE2 JUDGMENT")
        self.assertTrue(out["synthesis_used"])

    def test_phase2_failure_keeps_grounded_phase1_answer(self):
        out = self._run(eligible=True, synth_answer="")   # synthesis failed/empty
        self.assertEqual(out["answer"], "PHASE1 DASHBOARD")  # durable turn not lost
        self.assertFalse(out["synthesis_used"])

    def test_narrow_turn_stays_single_phase(self):
        out = self._run(eligible=False, synth_answer="PHASE2 JUDGMENT")
        self.assertEqual(out["answer"], "PHASE1 DASHBOARD")
        self.assertFalse(out["synthesis_used"])


class EvidenceSurvivesCompactionContractTests(SimpleTestCase):
    """Contract — DECISION-DETERMINATIVE EVIDENCE MUST SURVIVE THE PHASE-1 → PHASE-2
    HANDOFF.

    Production friction 2026-08-25. A turn retrieved BOTH the person's own regimen
    record and an authoritative product label (`tools_called: ["get_entity",
    "get_entity"]`, `synthesis_used: true`) and still answered generically. Proven by
    replaying the REAL production envelopes through the REAL renderer — no provider
    call — Phase 2 had received exactly:

        [medicine] name: Mounjaro
        [medication_reference] name: Mounjaro

    `_facts_from_result` had no branch for either `get_entity` shape (`entity` by
    name, `entities` by type), so both collapsed to the top-level-scalar fallback.
    The model did not ignore the evidence; the evidence never reached it. This is the
    THIRD instance of the documented evidence-lineage class (after envelope-unwrap and
    ranked-entity), so these tests assert the CLASS: a composed entity's deterministic
    facts — numeric or not — survive compaction, and authoritative text is not edited.

    Nothing here asserts a drug, a domain, or any answer wording.
    """

    def _entity_envelope(self, entity, key="entity"):
        """The canonical shape a get_entity read reaches synthesis in."""
        return {"source": "entity:x.y", "freshness": "current", "status": "ok",
                "value": {"status": "ready", "domain": "d", "schema_version": "1.0",
                          "granularity": "record_detail", "name": entity.get("identity"),
                          key: entity if key == "entity" else [entity]}}

    def _entity(self, **over):
        base = {
            "kind": "thing", "identity": "Subject A", "status": "active",
            "definition": {"category": "c", "quantity": "12.5 units"},
            "plan": {"schedule": ["7:00 AM"],
                     "schedule_detail": [{"time": "7:00 AM", "days_of_week": "3"}],
                     "recorded_note": "a non-numeric deterministic fact"},
            "standing": {"today": {"expected": 0, "taken": 0}},
            "performance": {"rate_7d": 61, "last_event": "2026-08-18"},
        }
        base.update(over)
        return base

    # -- the exact defect ----------------------------------------------------
    def test_by_name_entity_does_not_collapse_to_its_name(self):
        from apps.ai.model_interface.synthesis import render_evidence
        ev = [{"tool": "get_entity", "args": {"domain": "d", "name": "Subject A"},
               "result": self._entity_envelope(self._entity())}]
        rendered = render_evidence(ev)
        self.assertNotEqual(rendered.strip(), "[d] name: Subject A",
                            "the entity collapsed to its name — the proven defect")
        for fact in ("7:00 AM", "12.5 units", "rate_7d"):
            self.assertIn(fact, rendered, f"deterministic fact {fact!r} was destroyed")

    def test_by_type_entity_list_survives_too(self):
        from apps.ai.model_interface.synthesis import render_evidence
        ev = [{"tool": "get_entity", "args": {"domain": "d", "entity_type": "thing"},
               "result": self._entity_envelope(self._entity(), key="entities")}]
        rendered = render_evidence(ev)
        self.assertIn("Subject A", rendered)
        self.assertIn("7:00 AM", rendered)

    def test_non_numeric_facts_survive(self):
        """The prior entity handling kept only NUMERIC performance values, so
        schedules, instructions and identifiers were silently dropped."""
        from apps.ai.model_interface.synthesis import _facts_from_entity
        facts = " ".join(_facts_from_entity(self._entity()))
        self.assertIn("a non-numeric deterministic fact", facts)

    # -- authoritative text is never edited by compaction --------------------
    def test_verbatim_blocks_are_never_truncated(self):
        """A cap is a guess about where the meaning is, and that guess is provably
        unsafe: in the reproducer the decisive sentence began at offset EXACTLY 1600
        of a 3,852-character authoritative section. A surface that marks content
        `verbatim` is asserting the text IS the fact."""
        from apps.ai.model_interface.synthesis import (
            _ENTITY_VALUE_CAP, _TRUNCATION_MARK, _facts_from_entity,
        )
        decisive = "THE DECISIVE CONDITION APPLIES HERE."
        long_text = ("x" * (_ENTITY_VALUE_CAP + 500)) + decisive
        ent = self._entity(plan={"authoritative_text": long_text, "verbatim": True})
        facts = " ".join(_facts_from_entity(ent))
        self.assertIn(decisive, facts,
                      "a verbatim block was truncated and lost the decisive fact")
        self.assertNotIn(_TRUNCATION_MARK, facts)

    def test_non_verbatim_truncation_is_explicit_never_silent(self):
        from apps.ai.model_interface.synthesis import (
            _ENTITY_VALUE_CAP, _TRUNCATION_MARK, _facts_from_entity,
        )
        ent = self._entity(plan={"blob": "y" * (_ENTITY_VALUE_CAP + 500)})
        facts = " ".join(_facts_from_entity(ent))
        self.assertIn(_TRUNCATION_MARK, facts,
                      "silent truncation hides from the model that something was cut")

    # -- the two kinds of truth stay distinguishable -------------------------
    def test_rendered_evidence_preserves_which_surface_a_fact_came_from(self):
        """Phase 2 must be able to tell a person's own record from impersonal
        authoritative reference truth — blurring them is its own trust failure."""
        from apps.ai.model_interface.synthesis import render_evidence
        personal = self._entity(identity="Subject A")
        reference = self._entity(identity="Subject A", kind="product_label",
                                 plan={"authoritative_text": "T", "verbatim": True})
        rendered = render_evidence([
            {"tool": "get_entity", "args": {"domain": "personal_domain",
                                            "name": "Subject A"},
             "result": self._entity_envelope(personal)},
            {"tool": "get_entity", "args": {"domain": "reference_domain",
                                            "name": "Subject A"},
             "result": self._entity_envelope(reference)},
        ])
        self.assertIn("[personal_domain]", rendered)
        self.assertIn("[reference_domain]", rendered)
        self.assertIn("kind: product_label", rendered)

    # -- what was deliberately NOT changed -----------------------------------
    def test_eligibility_rule_is_unchanged(self):
        """Runtime evidence proved eligibility was NOT the failing condition — with the
        evidence rendered correctly, Phase 2 had what it needed. The ≥2-independent-
        surfaces rule therefore stays exactly as it was."""
        from apps.ai.model_interface.synthesis import synthesis_eligible
        two = [{"tool": "get_entity", "args": {"domain": "a", "name": "x"}},
               {"tool": "get_entity", "args": {"domain": "b", "name": "x"}}]
        self.assertTrue(synthesis_eligible(two))
        one = [{"tool": "get_entity", "args": {"domain": "a", "name": "x"}}]
        self.assertFalse(synthesis_eligible(one))

    def test_no_domain_or_subject_specific_logic_in_synthesis(self):
        """The fix must be a general compaction fix, never a domain carve-out.

        Asserts the CODE, not the prose: comments and docstrings legitimately record
        the production reproducer that motivated the change (the codebase documents
        real incidents with real specifics). What must never appear is a branch,
        constant or key that special-cases one domain, product or question.
        """
        import io
        import inspect
        import tokenize

        from apps.ai.model_interface import synthesis
        src = inspect.getsource(synthesis)

        # strip COMMENT tokens; keep code and string literals (a domain-specific
        # literal in code is exactly what this test exists to catch)
        code = "".join(
            "" if tok.type == tokenize.COMMENT else tok.string
            for tok in tokenize.generate_tokens(io.StringIO(src).readline)
        )
        # drop module/function docstrings too — prose, not logic
        import ast
        tree = ast.parse(src)
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                d = ast.get_docstring(node, clean=False)
                if d:
                    docstrings.add(d)
        for d in docstrings:
            code = code.replace(d, "")
        code = code.lower()

        for banned in ("mounjaro", "tirzepatide", "dailymed", "missed dose",
                       "medication_reference", "dosage_and_administration",
                       "medicine", "spl_setid"):
            self.assertNotIn(banned, code,
                             f"synthesis must stay domain-agnostic: {banned!r}")
