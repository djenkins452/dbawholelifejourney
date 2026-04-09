"""
Phase 7 — Decision Contract enforcement tests.

Locks in the four additions to format_cos_system_injection's
Decision Contract block:

1. ACTION DISCIPLINE — "ONE primary action", forbidden weasel words,
   "Do this next:" / "Your priority is:" direct language.
2. PRIORITY ORDER — health risk → foundational → time-sensitive →
   optimization.
3. CROSS-DOMAIN PATTERNS — reasoning starters from
   ctx['cross_domain_signals'].
4. TOP-RANKED SIGNAL — fallback lead when right_now_focus is steady.

Also locks in the Phase 7 validator extension:
- Weasel-phrase rejection in validate_response.

Regression guards (protect what we built in Phase 4-6):
- RIGHT NOW FOCUS still rendered.
- FEATURED SIGNALS still rendered.
- TRUST RULES still rendered.
"""

from django.test import TestCase


def _fake_context(**overrides):
    """Minimal context dict with a stub user, just enough for
    format_cos_system_injection to emit the Decision Contract block."""
    ctx = {
        '_user': None,  # suppresses the locked-facts block
        'user_id': 99,
        'right_now_focus': {},
        'featured_signals': {},
        'decision_rules': {
            'lead_with_focus': True,
            'forbid_raw_data_only': True,
            'response_structure': 'situation → interpretation → action',
            'signal_selection': 'discuss only featured_signals',
        },
        'cross_domain_signals': [],
        'ranked_signals': {},
        'trust_reports': {},
    }
    ctx.update(overrides)
    return ctx


def _inject(ctx):
    from apps.core.ai_orchestrator.cos_context import (
        format_cos_system_injection,
    )
    return format_cos_system_injection(ctx, user_message='how am i doing')


# ── Phase 7: ACTION DISCIPLINE block ─────────────────────────────────

class ActionDisciplineBlockTests(TestCase):
    """The Phase 7 ACTION DISCIPLINE block must be emitted on every
    Decision Contract that has at least one signal source."""

    def test_action_discipline_block_present(self):
        injection = _inject(_fake_context(
            right_now_focus={'status': 'steady'},
        ))
        self.assertIn("ACTION DISCIPLINE", injection)

    def test_one_primary_action_wording(self):
        injection = _inject(_fake_context(
            right_now_focus={'status': 'steady'},
        ))
        self.assertIn("exactly ONE primary action", injection)

    def test_required_prefix_phrases_listed(self):
        """Do this next / Your priority is — the two required
        direct-action prefixes must be explicitly named."""
        injection = _inject(_fake_context(
            right_now_focus={'status': 'steady'},
        ))
        self.assertIn("Do this next", injection)
        self.assertIn("Your priority is", injection)

    def test_forbidden_weasel_words_listed(self):
        """The LLM must be told which softening phrases are banned."""
        injection = _inject(_fake_context(
            right_now_focus={'status': 'steady'},
        ))
        for banned in (
            "'consider'", "'you might'", "'it could help'",
            "'perhaps'", "'maybe'", "'you may want to'",
        ):
            self.assertIn(banned, injection)

    def test_secondary_guidance_marked_clearly(self):
        """Secondary guidance is allowed but must be tagged."""
        injection = _inject(_fake_context(
            right_now_focus={'status': 'steady'},
        ))
        self.assertIn("secondary", injection.lower())


# ── Phase 7: PRIORITY ORDER block ────────────────────────────────────

class PriorityOrderBlockTests(TestCase):
    """The Phase 7 PRIORITY ORDER block must enumerate all four
    tiers in the order specified by the task: health risk →
    foundational → time-sensitive → optimization."""

    def test_all_four_priority_levels_present(self):
        injection = _inject(_fake_context(
            right_now_focus={'status': 'steady'},
        ))
        self.assertIn("PRIORITY ORDER", injection)
        self.assertIn("Health risk", injection)
        self.assertIn("Foundational habits", injection)
        self.assertIn("Time-sensitive commitments", injection)
        self.assertIn("Optimization", injection)

    def test_priority_order_is_correct(self):
        """Health risk must appear before foundational, which must
        appear before time-sensitive, which must appear before
        optimization."""
        injection = _inject(_fake_context(
            right_now_focus={'status': 'steady'},
        ))
        hr_idx = injection.index("Health risk")
        fh_idx = injection.index("Foundational habits")
        ts_idx = injection.index("Time-sensitive commitments")
        op_idx = injection.index("Optimization")
        self.assertLess(hr_idx, fh_idx)
        self.assertLess(fh_idx, ts_idx)
        self.assertLess(ts_idx, op_idx)

    def test_lower_priority_never_outranks_higher(self):
        injection = _inject(_fake_context(
            right_now_focus={'status': 'steady'},
        ))
        self.assertIn("never outranks a higher-priority", injection)


# ── Phase 7: CROSS-DOMAIN PATTERNS block ─────────────────────────────

class CrossDomainPatternsBlockTests(TestCase):
    """Correlation-based patterns must be surfaced to the LLM as
    explicit reasoning starters, not buried inside the signal dict."""

    def test_cross_domain_block_emitted_when_signals_present(self):
        ctx = _fake_context(
            right_now_focus={'status': 'focused', 'domain': 'nutrition',
                              'priority': 'high'},
            cross_domain_signals=[
                {
                    'signal_code': 'routine_breakdown',
                    'severity': 'medium',
                    'summary': '5 of 10 routine items missed today.',
                    'recommended_action': 'Check in on what disrupted the routine',
                },
            ],
        )
        injection = _inject(ctx)
        self.assertIn(
            "CROSS-DOMAIN PATTERNS (Phase 7 — reasoning starters)",
            injection,
        )
        self.assertIn("routine_breakdown", injection)
        self.assertIn("5 of 10 routine items missed today.", injection)
        self.assertIn("Check in on what disrupted the routine", injection)

    def test_cross_domain_block_omitted_when_empty(self):
        injection = _inject(_fake_context(
            right_now_focus={'status': 'steady'},
            cross_domain_signals=[],
        ))
        # Assert the Phase 7 block header is missing. Don't assert on
        # "CROSS-DOMAIN" alone — that phrase appears in the pre-existing
        # COS_PROACTIVE_INTELLIGENCE_PROMPT and is not Phase 7 content.
        self.assertNotIn(
            "CROSS-DOMAIN PATTERNS (Phase 7 — reasoning starters)",
            injection,
        )

    def test_cross_domain_capped_at_six(self):
        """Keep the prompt size bounded."""
        signals = [
            {
                'signal_code': f'sig_{i}',
                'severity': 'low',
                'summary': f'summary {i}',
                'recommended_action': f'action {i}',
            }
            for i in range(10)
        ]
        injection = _inject(_fake_context(
            right_now_focus={'status': 'steady'},
            cross_domain_signals=signals,
        ))
        # First 6 must be present, 7-10 must not
        for i in range(6):
            self.assertIn(f'sig_{i}', injection)
        for i in range(6, 10):
            self.assertNotIn(f'sig_{i}', injection)

    def test_reasoning_example_included(self):
        """The sleep/workouts → recovery risk example must be in the
        prompt so the LLM knows what "connect signals" looks like."""
        ctx = _fake_context(
            right_now_focus={'status': 'steady'},
            cross_domain_signals=[{
                'signal_code': 'any',
                'severity': 'medium',
                'summary': 'anything',
                'recommended_action': 'anything',
            }],
        )
        injection = _inject(ctx)
        self.assertIn("recovery risk", injection)


# ── Phase 7: TOP-RANKED SIGNAL fallback ──────────────────────────────

def _complete_top_signal(**overrides):
    """A schema-complete top_signal dict that both the pre-existing
    signal-arbitration block at cos_context.py:6614 AND the new
    Phase 7 TOP-RANKED SIGNAL block can consume without KeyError."""
    sig = {
        'title': 'Protein below target on workout days',
        'message': 'Protein intake 140g vs 180g target on lift days',
        'tier': 3,
        'tier_label': 'advisory',
        'confidence': 0.78,
        'module': 'nutrition',
        'arbitration_score': 280,
        'delivery_mode': 'support',
    }
    sig.update(overrides)
    return sig


class TopRankedSignalFallbackTests(TestCase):
    def test_surfaced_when_focus_steady(self):
        ctx = _fake_context(
            right_now_focus={'status': 'steady'},
            ranked_signals={
                'top_signal': _complete_top_signal(),
                'supporting_signals': [],
                'selection_reason': 'highest-tier with confidence floor',
            },
        )
        injection = _inject(ctx)
        # Phase 7 block header — distinct from the pre-existing
        # "TOP SIGNAL [ADVISORY]" arbitration block that also renders.
        self.assertIn(
            "TOP-RANKED SIGNAL (Phase 7 — fallback lead",
            injection,
        )
        self.assertIn("Protein below target on workout days", injection)
        self.assertIn("tier 3", injection)

    def test_suppressed_when_focus_focused(self):
        """When right_now_focus is focused, the Phase 7 TOP-RANKED
        fallback block must NOT appear — focus already leads."""
        ctx = _fake_context(
            right_now_focus={
                'status': 'focused',
                'domain': 'nutrition',
                'priority': 'high',
                'confidence': 97,
                'reason': 'macro compliance 0/100',
            },
            ranked_signals={
                'top_signal': _complete_top_signal(
                    title='Something else', tier=6,
                ),
                'supporting_signals': [],
            },
        )
        injection = _inject(ctx)
        self.assertNotIn(
            "TOP-RANKED SIGNAL (Phase 7 — fallback lead",
            injection,
        )

    def test_suppressed_when_no_top_signal(self):
        ctx = _fake_context(
            right_now_focus={'status': 'steady'},
            ranked_signals={'top_signal': {}},
        )
        injection = _inject(ctx)
        self.assertNotIn(
            "TOP-RANKED SIGNAL (Phase 7 — fallback lead",
            injection,
        )


# ── Regression guards — protect what we built ────────────────────────

class Phase4EnforcementStillPresentTests(TestCase):
    """Phase 4 blocks must still render after Phase 7 additions."""

    def test_right_now_focus_still_rendered(self):
        ctx = _fake_context(right_now_focus={
            'status': 'focused',
            'domain': 'nutrition',
            'priority': 'high',
            'confidence': 97,
            'reason': 'test reason',
        })
        injection = _inject(ctx)
        self.assertIn("RIGHT NOW FOCUS", injection)
        self.assertIn("nutrition", injection)
        self.assertIn("test reason", injection)

    def test_featured_signals_still_rendered(self):
        ctx = _fake_context(
            right_now_focus={'status': 'steady'},
            featured_signals={
                'sleep': {
                    'confidence': 100,
                    'priority_level': 'medium',
                    'sufficiency': 'high',
                    'priority_reason': 'Averaging 6.7h',
                },
            },
        )
        injection = _inject(ctx)
        self.assertIn("FEATURED SIGNALS", injection)
        self.assertIn("sleep", injection)
        self.assertIn("Averaging 6.7h", injection)

    def test_trust_rules_still_rendered(self):
        injection = _inject(_fake_context(
            right_now_focus={'status': 'steady'},
        ))
        self.assertIn("TRUST RULES", injection)
        self.assertIn("situation", injection.lower())

    def test_situation_interpretation_action_preserved(self):
        injection = _inject(_fake_context(
            right_now_focus={'status': 'steady'},
        ))
        self.assertIn("Situation → Interpretation → Action", injection)


# ── Phase 7: Validator extension ─────────────────────────────────────

class ValidatorWeaselPhraseTests(TestCase):
    def test_rejects_consider(self):
        from apps.ai.deterministic_router import validate_response
        ok, reason = validate_response(
            "Your sleep is at 6.2h this week, 12% confidence. "
            "You might want to try going to bed earlier.",
        )
        self.assertFalse(ok)
        self.assertIn("weasel", reason)

    def test_rejects_it_could_help(self):
        from apps.ai.deterministic_router import validate_response
        ok, reason = validate_response(
            "Your adherence is 62% this week (limited data). "
            "It could help to set a reminder.",
        )
        self.assertFalse(ok)
        self.assertIn("weasel", reason)

    def test_rejects_perhaps_you(self):
        from apps.ai.deterministic_router import validate_response
        ok, reason = validate_response(
            "Situation: 3 of 5 nights below 7h. Perhaps you should "
            "consider adjusting your schedule.",
        )
        self.assertFalse(ok)
        # This one contains 'perhaps you' first, but 'consider' would
        # also trigger via the _GENERIC path if the first check missed it.
        # Either weasel or generic rejection is acceptable.
        self.assertTrue(
            "weasel" in reason or "consider" in reason,
            f"Expected weasel/consider rejection, got: {reason}",
        )

    def test_accepts_direct_action_phrase(self):
        from apps.ai.deterministic_router import validate_response
        ok, reason = validate_response(
            "**Situation**\n"
            "Adherence is 62% this week (7d confidence: high). "
            "**Interpretation**\n"
            "Below the 80% threshold — you're slipping.\n"
            "**Action**\n"
            "Do this next: take your 2 overdue doses now.",
            query_domain='medicine',
        )
        self.assertTrue(ok, f"Expected ok, got rejection: {reason}")

    def test_still_rejects_phase_4_generic_phrases(self):
        """Phase 4 generic-phrase check must still fire."""
        from apps.ai.deterministic_router import validate_response
        ok, reason = validate_response(
            "Your adherence is 62%. Keep it up!",
        )
        self.assertFalse(ok)
        self.assertIn("generic", reason)


# ── Danny's live data end-to-end smoke test ──────────────────────────

class DannyLiveDataSmokeTests(TestCase):
    """Not a regression guard — this is a shape check against a
    synthetic Danny-like context to make sure the full stack still
    emits every new Phase 7 block when realistic data is present."""

    def test_full_stack_emits_all_phase_7_blocks(self):
        ctx = _fake_context(
            right_now_focus={
                'status': 'focused',
                'domain': 'nutrition',
                'priority': 'high',
                'confidence': 97,
                'reason': 'Macro compliance at 0.0/100',
            },
            featured_signals={
                'sleep': {
                    'confidence': 100,
                    'priority_level': 'medium',
                    'sufficiency': 'high',
                    'priority_reason': 'Averaging 6.7h',
                },
                'nutrition': {
                    'confidence': 97,
                    'priority_level': 'high',
                    'sufficiency': 'high',
                    'priority_reason': 'Macro compliance at 0.0/100',
                },
            },
            cross_domain_signals=[
                {
                    'signal_code': 'routine_breakdown',
                    'severity': 'medium',
                    'summary': '5 of 10 routine items missed today.',
                    'recommended_action': 'Check in on what disrupted the routine',
                },
                {
                    'signal_code': 'medication_adherence_risk',
                    'severity': 'medium',
                    'summary': '0 missed dose(s) today + 2 overdue.',
                    'recommended_action': 'Take overdue medications if safe to do so',
                },
            ],
        )
        injection = _inject(ctx)

        # All Phase 7 blocks
        self.assertIn("ACTION DISCIPLINE", injection)
        self.assertIn("PRIORITY ORDER", injection)
        self.assertIn(
            "CROSS-DOMAIN PATTERNS (Phase 7 — reasoning starters)",
            injection,
        )
        self.assertIn("routine_breakdown", injection)
        self.assertIn("medication_adherence_risk", injection)

        # All preserved Phase 4 blocks
        self.assertIn("RIGHT NOW FOCUS", injection)
        self.assertIn("FEATURED SIGNALS", injection)
        self.assertIn("TRUST RULES", injection)
