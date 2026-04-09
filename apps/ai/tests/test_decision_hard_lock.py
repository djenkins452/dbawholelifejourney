"""
Phase 8 — Decision Hard Lock tests.

Verifies the structural enforcement layer that guarantees decision
queries produce Action-First responses. Tests cover:

1. _build_focus_query_response Action-First format (never-None)
2. _is_decision_query semantic + phrase detection
3. _try_decision_query_route never returns None for decision queries
4. validate_response Rule 0 (action-first), Rule 0-b (forbidden
   starters), Rule 0-c (single action), Rule 1c (passive phrases)
5. Regression guards for Phase 4, 4.5, 7 rules
"""

from datetime import date
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.users.models import User


def _make_user(email):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(
        email=email, password="testpass123",
        date_of_birth=date(1990, 1, 1),
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ══════════════════════════════════════════════════════════════
# A. _is_decision_query classifier
# ══════════════════════════════════════════════════════════════

class DecisionQueryClassifierTests(TestCase):
    """The classifier must catch all five required categories plus
    semantic paraphrases, and must NOT over-fire on non-decision
    queries."""

    def _cls(self, msg):
        from apps.ai.deterministic_router import _is_decision_query
        if msg is None:
            return _is_decision_query(None)
        return _is_decision_query(msg.lower())

    # ── Category 1: "what should I do" ────────────────────────
    def test_what_should_i_do(self):
        self.assertTrue(self._cls("What should I do next?"))
        self.assertTrue(self._cls("what should i do right now"))
        self.assertTrue(self._cls("what should i focus on today"))

    def test_what_should_i_fix(self):
        self.assertTrue(self._cls("what should i fix first"))
        self.assertTrue(self._cls("What should I fix?"))

    # ── Category 2: "what is the biggest risk" ────────────────
    def test_biggest_risk(self):
        self.assertTrue(self._cls("what is my biggest risk"))
        self.assertTrue(self._cls("what's the biggest risk"))
        self.assertTrue(self._cls("biggest risk right now"))

    def test_biggest_problem(self):
        self.assertTrue(self._cls("what's my biggest problem"))
        self.assertTrue(self._cls("what is my biggest concern"))
        self.assertTrue(self._cls("biggest issue today"))

    # ── Category 3: "what is not working" ─────────────────────
    def test_not_working(self):
        self.assertTrue(self._cls("what's not working"))
        self.assertTrue(self._cls("what is not working"))
        self.assertTrue(self._cls("whats not working"))
        self.assertTrue(self._cls("what isn't working"))

    def test_whats_broken(self):
        self.assertTrue(self._cls("what's broken"))
        self.assertTrue(self._cls("whats broken"))

    # ── Category 4: "help me decide" ──────────────────────────
    def test_help_me_decide(self):
        self.assertTrue(self._cls("help me decide"))
        self.assertTrue(self._cls("can you help me decide"))
        self.assertTrue(self._cls("help me pick"))
        self.assertTrue(self._cls("help me choose between these"))
        self.assertTrue(self._cls("decide for me"))
        self.assertTrue(self._cls("make the call"))

    # ── Semantic paraphrases (non-exact) ──────────────────────
    def test_semantic_what_do_i_fix(self):
        self.assertTrue(self._cls("what do i fix"))

    def test_semantic_what_do_i_tackle(self):
        self.assertTrue(self._cls("what do i tackle first"))

    def test_semantic_biggest_concern(self):
        self.assertTrue(self._cls("biggest concern in my life"))

    # ── Regression: existing Phase 4 focus queries still match ─
    def test_am_i_behind_still_matches(self):
        self.assertTrue(self._cls("am i behind"))

    def test_how_am_i_doing_still_matches(self):
        self.assertTrue(self._cls("how am i doing today"))

    # ── Negative cases — must NOT over-fire ───────────────────
    def test_log_my_weight_not_decision(self):
        self.assertFalse(self._cls("log my weight"))

    def test_what_is_my_heart_rate_not_decision(self):
        self.assertFalse(self._cls("what is my heart rate trend"))

    def test_empty_not_decision(self):
        self.assertFalse(self._cls(""))
        self.assertFalse(self._cls(None))


# ══════════════════════════════════════════════════════════════
# B. _build_focus_query_response — Action-First + never-None
# ══════════════════════════════════════════════════════════════

class FocusResponseActionFirstTests(TestCase):
    def setUp(self):
        self.user = _make_user("focus_action_first@test.com")

    def _build(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        return _build_focus_query_response(self.user)

    def test_first_line_starts_with_do_this_next(self):
        """The first non-empty line MUST start with 'Do this next:'."""
        resp = self._build()
        lines = [ln for ln in resp.splitlines() if ln.strip()]
        self.assertTrue(lines, "response must not be empty")
        self.assertTrue(
            lines[0].startswith("Do this next:"),
            f"first line must start with 'Do this next:', got {lines[0]!r}",
        )

    def test_never_returns_none(self):
        resp = self._build()
        self.assertIsNotNone(resp)
        self.assertIsInstance(resp, str)
        self.assertTrue(len(resp) > 0)

    def test_contains_reason_block(self):
        resp = self._build()
        self.assertIn("Reason:", resp)

    def test_no_passive_phrases(self):
        resp = self._build().lower()
        for bad in ("keep logging", "continue tracking", "monitor this",
                    "keep an eye on", "stay the course"):
            self.assertNotIn(
                bad, resp,
                f"focus response must not contain passive phrase {bad!r}",
            )

    def test_empty_state_still_returns_action_first(self):
        """Even with a brand new user (no trust reports, no focus),
        the response must still be Action-First."""
        fresh_user = _make_user("empty_state@test.com")
        from apps.ai.deterministic_router import _build_focus_query_response
        resp = _build_focus_query_response(fresh_user)
        self.assertIsNotNone(resp)
        lines = [ln for ln in resp.splitlines() if ln.strip()]
        self.assertTrue(lines)
        self.assertTrue(
            lines[0].startswith("Do this next:"),
            f"empty state fallback must still lead with action, got {lines[0]!r}",
        )

    def test_builder_exception_safe_fallback(self):
        """If compute_right_now_focus raises, _build_focus_query_response
        must still return an Action-First string — not None, not empty."""
        from apps.ai.deterministic_router import _build_focus_query_response
        with patch(
            "apps.core.ai_state.right_now.compute_right_now_focus",
            side_effect=RuntimeError("signal pipeline exploded"),
        ):
            resp = _build_focus_query_response(self.user)
        self.assertIsNotNone(resp)
        lines = [ln for ln in resp.splitlines() if ln.strip()]
        self.assertTrue(lines[0].startswith("Do this next:"))


# ══════════════════════════════════════════════════════════════
# C. _try_decision_query_route — hard override, never None
# ══════════════════════════════════════════════════════════════

class DecisionQueryRouteTests(TestCase):
    def setUp(self):
        self.user = _make_user("decision_route@test.com")

    def _route(self, msg):
        from apps.ai.deterministic_router import _try_decision_query_route
        return _try_decision_query_route(msg.lower(), self.user)

    def test_biggest_risk_returns_route_result(self):
        r = self._route("what is my biggest risk")
        self.assertIsNotNone(r)
        self.assertTrue(r.is_terminal)
        # Phase 11: route_name now includes the intent suffix
        self.assertTrue(
            r.route_name.startswith("decision_query"),
            f"expected decision_query prefix, got {r.route_name!r}",
        )
        self.assertTrue("Do this next:" in r.response or "Your priority is:" in r.response, f"Missing Action-First prefix: {r.response[:80]!r}")

    def test_not_working_returns_route_result(self):
        r = self._route("what's not working")
        self.assertIsNotNone(r)
        self.assertTrue("Do this next:" in r.response or "Your priority is:" in r.response, f"Missing Action-First prefix: {r.response[:80]!r}")

    def test_help_me_decide_returns_route_result(self):
        r = self._route("help me decide")
        self.assertIsNotNone(r)
        self.assertTrue("Do this next:" in r.response or "Your priority is:" in r.response, f"Missing Action-First prefix: {r.response[:80]!r}")

    def test_non_decision_query_returns_none(self):
        r = self._route("log my weight at 180")
        self.assertIsNone(r)

    def test_never_none_even_on_handler_exception(self):
        """Even if ALL handlers raise, the route must still return a
        valid RouteResult with Action-First."""
        from apps.ai.deterministic_router import _try_decision_query_route
        with patch(
            "apps.ai.deterministic_router._build_biggest_risk_response",
            side_effect=RuntimeError("boom"),
        ), patch(
            "apps.ai.deterministic_router._build_focus_query_response",
            side_effect=RuntimeError("boom"),
        ):
            r = _try_decision_query_route(
                "what is my biggest risk", self.user,
            )
        self.assertIsNotNone(r)
        self.assertTrue("Do this next:" in r.response or "Your priority is:" in r.response, f"Missing Action-First prefix: {r.response[:80]!r}")


# ══════════════════════════════════════════════════════════════
# D. validate_response — Phase 8 Rules 0, 0-b, 0-c, 1c
# ══════════════════════════════════════════════════════════════

class ValidatorPhase8RulesTests(TestCase):
    def _validate(self, text, is_decision=False, domain=None):
        from apps.ai.deterministic_router import validate_response
        return validate_response(
            text, user=None, query_domain=domain,
            is_decision_query=is_decision,
        )

    # ── Rule 0: action-first requirement ─────────────────────
    def test_rejects_missing_action_first_line(self):
        ok, reason = self._validate(
            "Your adherence is 62% this week. The trend is declining. "
            "You're at below the target threshold.",
            is_decision=True,
        )
        self.assertFalse(ok)
        self.assertIn("first line", reason)

    def test_accepts_do_this_next_first_line(self):
        ok, reason = self._validate(
            "Do this next: Take your overdue doses now.\n\n"
            "Reason:\nAdherence is at 62% this week, below the target.",
            is_decision=True,
        )
        self.assertTrue(ok, f"expected ok, got: {reason}")

    def test_accepts_your_priority_is_first_line(self):
        ok, reason = self._validate(
            "Your priority is: Complete today's foundational prayer.\n\n"
            "Reason:\nFoundational habits are at 0/10 so far.",
            is_decision=True,
        )
        self.assertTrue(ok, f"expected ok, got: {reason}")

    # ── Rule 0-b: forbidden summary-first starters ────────────
    def test_rejects_end_of_day_starter(self):
        ok, reason = self._validate(
            "End of day recap: you completed 5 routines and missed 3.",
            is_decision=True,
        )
        self.assertFalse(ok)
        self.assertIn("summary-first", reason)

    def test_rejects_heres_what_happened_starter(self):
        ok, reason = self._validate(
            "Here's what happened today: adherence is 62%, workouts are 9.",
            is_decision=True,
        )
        self.assertFalse(ok)
        self.assertIn("summary-first", reason)

    def test_rejects_today_you_starter(self):
        ok, reason = self._validate(
            "Today you completed 5 of 10 routines. That's progress.",
            is_decision=True,
        )
        self.assertFalse(ok)
        self.assertIn("summary-first", reason)

    def test_rejects_summary_starter(self):
        ok, reason = self._validate(
            "Summary: your adherence is 62%, sleep is 6.5h, "
            "workouts are strong.",
            is_decision=True,
        )
        self.assertFalse(ok)
        self.assertIn("summary-first", reason)

    def test_rejects_you_completed_starter(self):
        ok, reason = self._validate(
            "You completed 5 routines but missed 2 medications "
            "and your sleep was 6.2 hours.",
            is_decision=True,
        )
        self.assertFalse(ok)
        self.assertIn("summary-first", reason)

    # ── Rule 0-c: single action enforcement ──────────────────
    def test_rejects_multiple_action_lines(self):
        ok, reason = self._validate(
            "Do this next: Take your overdue meds.\n\n"
            "Reason:\nAdherence slipping.\n\n"
            "Do this next: Also log your workout.",
            is_decision=True,
        )
        self.assertFalse(ok)
        self.assertIn("action lines", reason)

    def test_accepts_single_action_with_reason(self):
        ok, reason = self._validate(
            "Do this next: Log your overdue dose now.\n\n"
            "Reason:\nAdherence is at 62% (below target threshold).\n\n"
            "Schedule: on track.",
            is_decision=True,
        )
        self.assertTrue(ok, f"expected ok, got: {reason}")

    # ── Rule 1c: passive-action phrases ──────────────────────
    def test_rejects_keep_logging_on_decision(self):
        ok, reason = self._validate(
            "Do this next: Log today's meals now.\n\nReason:\n"
            "Adherence is below target. Keep logging to build data.",
            is_decision=True,
        )
        self.assertFalse(ok)
        self.assertIn("passive", reason)

    def test_rejects_continue_tracking_on_non_decision(self):
        ok, reason = self._validate(
            "Your sleep is at 6.2h this week (high confidence). "
            "Continue tracking to see the trend.",
            is_decision=False,
        )
        self.assertFalse(ok)
        self.assertIn("passive", reason)

    def test_rejects_monitor_this_on_non_decision(self):
        ok, reason = self._validate(
            "Your heart rate is averaging 68 bpm (above target range). "
            "Monitor this for any spikes.",
            is_decision=False,
        )
        self.assertFalse(ok)
        self.assertIn("passive", reason)

    def test_rejects_stay_the_course(self):
        ok, reason = self._validate(
            "Your workouts are at 9 this week (high confidence). "
            "Stay the course — you're on track.",
            is_decision=False,
        )
        self.assertFalse(ok)
        self.assertIn("passive", reason)


# ══════════════════════════════════════════════════════════════
# E. Regression guards — protect Phase 4, 4.5, 7 work
# ══════════════════════════════════════════════════════════════

class Phase4To7RegressionTests(TestCase):
    """Phase 8 additions must not break any prior enforcement rule."""

    def _validate(self, text, **kwargs):
        from apps.ai.deterministic_router import validate_response
        return validate_response(text, **kwargs)

    def test_phase_4_generic_phrases_still_rejected(self):
        ok, reason = self._validate(
            "Your adherence is 62%. Keep it up!",
        )
        self.assertFalse(ok)
        self.assertIn("generic", reason)

    def test_phase_7_weasel_phrases_still_rejected(self):
        ok, reason = self._validate(
            "Your adherence is 62% this week (limited data). "
            "You might want to try setting a reminder.",
        )
        self.assertFalse(ok)
        self.assertIn("weasel", reason)

    def test_phase_4_focus_query_phrases_still_match(self):
        """_FOCUS_QUERY_PHRASES still catches the Phase 4 set."""
        from apps.ai.deterministic_router import _is_focus_query
        self.assertTrue(_is_focus_query("am i behind"))
        self.assertTrue(_is_focus_query("how am i doing"))
        self.assertTrue(_is_focus_query("what's my focus"))
        self.assertTrue(_is_focus_query("whats most important"))

    def test_phase_4_next_action_phrases_still_match(self):
        from apps.ai.deterministic_router import _is_next_action_query
        self.assertTrue(_is_next_action_query("what's next"))
        self.assertTrue(_is_next_action_query("what should i do next"))

    def test_phase_4_5_too_short_still_rejected(self):
        ok, reason = self._validate("Ok.")
        self.assertFalse(ok)
        self.assertIn("too short", reason)

    def test_phase_7_cross_domain_block_still_renders(self):
        """The Phase 7 CROSS-DOMAIN PATTERNS block must still appear
        when cross_domain_signals exist."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection,
        )
        ctx = {
            "_user": None, "user_id": 99,
            "right_now_focus": {"status": "focused", "domain": "nutrition",
                                 "priority": "high", "confidence": 97,
                                 "reason": "test"},
            "featured_signals": {},
            "decision_rules": {"lead_with_focus": True},
            "cross_domain_signals": [
                {"signal_code": "routine_breakdown", "severity": "medium",
                 "summary": "5 of 10 missed.",
                 "recommended_action": "Check in"},
            ],
            "ranked_signals": {},
            "trust_reports": {},
        }
        inj = format_cos_system_injection(ctx, user_message="test")
        self.assertIn(
            "CROSS-DOMAIN PATTERNS (Phase 7 — reasoning starters)",
            inj,
        )

    def test_phase_7_priority_order_block_still_renders(self):
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection,
        )
        ctx = {
            "_user": None, "user_id": 99,
            "right_now_focus": {"status": "steady"},
            "featured_signals": {},
            "decision_rules": {"lead_with_focus": True},
            "cross_domain_signals": [],
            "ranked_signals": {},
            "trust_reports": {},
        }
        inj = format_cos_system_injection(ctx, user_message="test")
        self.assertIn("PRIORITY ORDER", inj)
        self.assertIn("Health risk", inj)
        self.assertIn("Foundational habits", inj)


# ══════════════════════════════════════════════════════════════
# F. Phase 8 prompt additions
# ══════════════════════════════════════════════════════════════

class PromptActionFirstBlockTests(TestCase):
    def _inject(self):
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection,
        )
        ctx = {
            "_user": None, "user_id": 99,
            "right_now_focus": {"status": "steady"},
            "featured_signals": {},
            "decision_rules": {"lead_with_focus": True},
            "cross_domain_signals": [],
            "ranked_signals": {},
            "trust_reports": {},
        }
        return format_cos_system_injection(ctx, user_message="test")

    def test_action_first_ordering_block_present(self):
        inj = self._inject()
        self.assertIn("ACTION-FIRST ORDERING", inj)

    def test_forbidden_starters_listed_in_prompt(self):
        inj = self._inject()
        for bad in ("End of day", "Here's what happened", "Today you",
                    "Summary", "Your day so far"):
            self.assertIn(bad, inj)

    def test_passive_phrases_listed_in_prompt(self):
        inj = self._inject()
        self.assertIn("keep logging", inj.lower())
        self.assertIn("continue tracking", inj.lower())
        self.assertIn("monitor this", inj.lower())

    def test_decision_query_categories_listed(self):
        inj = self._inject()
        # All 5 categories the task spec enumerates
        self.assertIn("What should I do", inj)
        self.assertIn("biggest risk", inj.lower())
        self.assertIn("not working", inj.lower())
        self.assertIn("Help me decide", inj)
        self.assertIn("What should I fix", inj)
