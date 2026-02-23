"""
Phase 5A — Executive Commitment Contract (ECC) Tests.

Tests for:
1. Commitment detected
2. Missing time → tightening question
3. Missing done-definition → tightening question
4. CLEAN renegotiation allowed
5. EARLY_EROSION renegotiation blocked
6. Binary closure enforcement
7. Positive lock-in only on success
"""

from datetime import datetime

from django.test import TestCase

from apps.core.ai_orchestrator.commitment_contract import (
    Commitment,
    CommitmentDraft,
    MissingField,
    RenegotiationBlocked,
    apply_renegotiation_rules,
    close_commitment,
    detect_commitment_intent,
    extract_commitment_fields,
    format_ecc_injection,
    generate_tightening_question,
    normalize_commitment,
    process_ecc_detection,
    render_commitment_confirmation,
    render_positive_lock_in,
)


class CommitmentDetectionTest(TestCase):
    """Test 1: Commitment intent detected."""

    def test_i_will(self):
        self.assertTrue(detect_commitment_intent("I will start exercising"))

    def test_ill(self):
        self.assertTrue(detect_commitment_intent("I'll go to the gym"))

    def test_i_am_going_to(self):
        self.assertTrue(detect_commitment_intent("I am going to read more"))

    def test_im_going_to(self):
        self.assertTrue(detect_commitment_intent("I'm going to meditate"))

    def test_lets(self):
        self.assertTrue(detect_commitment_intent("Let's do this today"))

    def test_i_plan_to(self):
        self.assertTrue(detect_commitment_intent("I plan to finish the report"))

    def test_no_commitment(self):
        self.assertFalse(detect_commitment_intent("What's the weather today?"))

    def test_empty_input(self):
        self.assertFalse(detect_commitment_intent(""))

    def test_none_input(self):
        self.assertFalse(detect_commitment_intent(None))

    def test_curly_apostrophe(self):
        """Curly apostrophes should be normalized and detected."""
        self.assertTrue(detect_commitment_intent("I\u2019ll finish this"))

    def test_case_insensitive(self):
        self.assertTrue(detect_commitment_intent("I WILL do it"))


class MissingTimeBoundaryTest(TestCase):
    """Test 2: Missing time → tightening question."""

    def test_missing_time_returns_missing_field(self):
        result = extract_commitment_fields("I will start exercising")
        self.assertIsInstance(result, MissingField)
        self.assertEqual(result.field_name, 'time_boundary')

    def test_tightening_question_for_time(self):
        missing = MissingField('time_boundary')
        question = generate_tightening_question(missing)
        self.assertEqual(question, "When specifically will this be completed?")

    def test_pipeline_returns_tightening_for_missing_time(self):
        result = process_ecc_detection("I will start exercising", 'CLEAN')
        self.assertIsNotNone(result)
        self.assertTrue(result['detected'])
        self.assertEqual(
            result['response'],
            "When specifically will this be completed?"
        )
        self.assertIsNone(result['commitment'])


class MissingDoneDefinitionTest(TestCase):
    """Test 3: Missing done-definition → tightening question."""

    def test_missing_done_def_returns_missing_field(self):
        result = extract_commitment_fields("I will start exercising today")
        self.assertIsInstance(result, MissingField)
        self.assertEqual(result.field_name, 'done_definition')

    def test_tightening_question_for_done(self):
        missing = MissingField('done_definition')
        question = generate_tightening_question(missing)
        self.assertEqual(question, "What does 'done' mean in one sentence?")

    def test_pipeline_returns_tightening_for_missing_done(self):
        result = process_ecc_detection(
            "I will start exercising today", 'CLEAN'
        )
        self.assertIsNotNone(result)
        self.assertTrue(result['detected'])
        self.assertEqual(
            result['response'],
            "What does 'done' mean in one sentence?"
        )


class CleanRenegotiationTest(TestCase):
    """Test 4: CLEAN renegotiation allowed."""

    def setUp(self):
        self.commitment = Commitment(
            normalized_text='finish the report',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 22, 17, 0),
            done_definition='Report submitted to manager.',
            status='pending',
        )

    def test_clean_renegotiation_with_new_time(self):
        result = apply_renegotiation_rules(
            self.commitment,
            "I'll do it by 9pm instead",
            'CLEAN',
        )
        # Should return updated commitment (not blocked)
        self.assertIsInstance(result, Commitment)

    def test_clean_renegotiation_without_time_blocked(self):
        result = apply_renegotiation_rules(
            self.commitment,
            "Can I do this later?",
            'CLEAN',
        )
        # Without explicit time → RenegotiationBlocked
        self.assertIsInstance(result, RenegotiationBlocked)
        self.assertEqual(len(result.choices), 2)

    def test_clean_renegotiation_scope_change_needs_done(self):
        result = apply_renegotiation_rules(
            self.commitment,
            "I'll write the presentation slides instead by tomorrow",
            'CLEAN',
        )
        # Scope changed, no new done-definition → MissingField
        self.assertIsInstance(result, MissingField)
        self.assertEqual(result.field_name, 'done_definition')


class ErosionRenegotiationBlockedTest(TestCase):
    """Test 5: EARLY_EROSION renegotiation blocked."""

    def setUp(self):
        self.commitment = Commitment(
            normalized_text='finish the report',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 22, 17, 0),
            done_definition='Report submitted to manager.',
            status='pending',
        )

    def test_early_erosion_blocks_renegotiation(self):
        result = apply_renegotiation_rules(
            self.commitment,
            "I'll push it to tomorrow by 5pm",
            'EARLY_EROSION',
        )
        self.assertIsInstance(result, RenegotiationBlocked)
        self.assertEqual(len(result.choices), 2)
        self.assertTrue(result.choices[0].startswith('A)'))
        self.assertTrue(result.choices[1].startswith('B)'))

    def test_structural_drift_blocks_renegotiation(self):
        result = apply_renegotiation_rules(
            self.commitment,
            "Let me reschedule to next week",
            'STRUCTURAL_DRIFT',
        )
        self.assertIsInstance(result, RenegotiationBlocked)
        self.assertEqual(len(result.choices), 2)

    def test_blocked_choices_are_deterministic(self):
        result = apply_renegotiation_rules(
            self.commitment,
            "I need more time",
            'EARLY_EROSION',
        )
        self.assertEqual(
            result.choices[0],
            "A) Keep original commitment with a 15\u201330 minute minimum version now",
        )
        self.assertEqual(
            result.choices[1],
            "B) Formally cancel and accept consequence",
        )


class BinaryClosureTest(TestCase):
    """Test 6: Binary closure enforcement."""

    def setUp(self):
        self.commitment = Commitment(
            normalized_text='finish the report',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 22, 17, 0),
            done_definition='Report submitted to manager.',
            status='pending',
        )

    def test_affirmative_closes_success(self):
        result = close_commitment(self.commitment, "Yes, it's done")
        self.assertIsInstance(result, Commitment)
        self.assertEqual(result.status, 'closed_success')

    def test_negative_closes_missed(self):
        result = close_commitment(self.commitment, "No, I didn't finish")
        self.assertIsInstance(result, Commitment)
        self.assertEqual(result.status, 'closed_missed')

    def test_ambiguous_asks_binary(self):
        result = close_commitment(self.commitment, "Sort of, mostly")
        self.assertIsInstance(result, str)
        self.assertEqual(result, "Is it done — yes or no?")

    def test_empty_response_asks_binary(self):
        result = close_commitment(self.commitment, "")
        self.assertEqual(result, "Is it done — yes or no?")

    def test_done_keyword_closes_success(self):
        commitment = Commitment(
            normalized_text='finish the report',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 22, 17, 0),
            done_definition='Report submitted.',
            status='pending',
        )
        result = close_commitment(commitment, "Done!")
        self.assertIsInstance(result, Commitment)
        self.assertEqual(result.status, 'closed_success')

    def test_not_yet_closes_missed(self):
        commitment = Commitment(
            normalized_text='finish the report',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 22, 17, 0),
            done_definition='Report submitted.',
            status='pending',
        )
        result = close_commitment(commitment, "Not yet")
        self.assertIsInstance(result, Commitment)
        self.assertEqual(result.status, 'closed_missed')


class PositiveLockInTest(TestCase):
    """Test 7: Positive lock-in only on success."""

    def test_lock_in_on_success(self):
        commitment = Commitment(
            normalized_text='finish the report',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 22, 17, 0),
            done_definition='Report submitted.',
            status='closed_success',
        )
        result = render_positive_lock_in(commitment)
        self.assertEqual(result, "Time boundary honored. Repeat this structure.")

    def test_no_lock_in_on_missed(self):
        commitment = Commitment(
            normalized_text='finish the report',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 22, 17, 0),
            done_definition='Report submitted.',
            status='closed_missed',
        )
        result = render_positive_lock_in(commitment)
        self.assertIsNone(result)

    def test_no_lock_in_on_pending(self):
        commitment = Commitment(
            normalized_text='finish the report',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 22, 17, 0),
            done_definition='Report submitted.',
            status='pending',
        )
        result = render_positive_lock_in(commitment)
        self.assertIsNone(result)


class CommitmentNormalizationTest(TestCase):
    """Additional tests for normalize_commitment and type classification."""

    def test_do_type(self):
        draft = CommitmentDraft(
            action='finish the report',
            time_boundary_raw='today',
            done_definition='Report submitted.',
        )
        ref = datetime(2026, 2, 22, 10, 0)
        commitment = normalize_commitment(draft, reference_time=ref)
        self.assertEqual(commitment.commitment_type, 'DO')
        self.assertEqual(commitment.status, 'pending')

    def test_decide_type(self):
        draft = CommitmentDraft(
            action='decide on the vendor',
            time_boundary_raw='today',
            done_definition='Vendor chosen.',
        )
        ref = datetime(2026, 2, 22, 10, 0)
        commitment = normalize_commitment(draft, reference_time=ref)
        self.assertEqual(commitment.commitment_type, 'DECIDE')

    def test_schedule_type(self):
        draft = CommitmentDraft(
            action='schedule the dentist appointment',
            time_boundary_raw='tomorrow',
            done_definition='Appointment booked.',
        )
        ref = datetime(2026, 2, 22, 10, 0)
        commitment = normalize_commitment(draft, reference_time=ref)
        self.assertEqual(commitment.commitment_type, 'SCHEDULE')

    def test_stop_type(self):
        draft = CommitmentDraft(
            action='stop eating junk food',
            time_boundary_raw='today',
            done_definition='No junk food consumed.',
        )
        ref = datetime(2026, 2, 22, 10, 0)
        commitment = normalize_commitment(draft, reference_time=ref)
        self.assertEqual(commitment.commitment_type, 'STOP')


class CommitmentConfirmationTest(TestCase):
    """Test render_commitment_confirmation output format."""

    def test_confirmation_format(self):
        commitment = Commitment(
            normalized_text='finish the report',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 22, 5, 0),
            done_definition='Report submitted to manager.',
            status='pending',
        )
        result = render_commitment_confirmation(commitment)
        self.assertIn('Commitment set:', result)
        self.assertIn('finish the report', result)
        self.assertIn('Done means:', result)
        self.assertIn('Report submitted to manager.', result)


class ECCInjectionTest(TestCase):
    """Test format_ecc_injection for CoS prompt integration."""

    def test_no_commitments_empty(self):
        result = format_ecc_injection([])
        self.assertEqual(result, '')

    def test_no_pending_commitments_empty(self):
        commitment = Commitment(
            normalized_text='finish the report',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 22, 17, 0),
            done_definition='Report submitted.',
            status='closed_success',
        )
        result = format_ecc_injection([commitment])
        self.assertEqual(result, '')

    def test_pending_commitment_injected(self):
        commitment = Commitment(
            normalized_text='finish the report',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 22, 17, 0),
            done_definition='Report submitted.',
            status='pending',
        )
        result = format_ecc_injection([commitment])
        self.assertIn('ACTIVE COMMITMENTS (ECC)', result)
        self.assertIn('COMMITMENT [DO]', result)
        self.assertIn('finish the report', result)
        self.assertIn('ENFORCEMENT:', result)


class ExactConfirmationFormatTest(TestCase):
    """Test exact confirmation output format — no contamination, proper case."""

    def test_exact_confirmation_full_input(self):
        """
        Input:  "I'll finish the compensation model by Friday at 3 PM.
                 Done means the revised ranges are finalized and exported
                 to Excel."
        Output: "Commitment set: Finish the compensation model by Friday
                 at 3 PM. Done means: The revised ranges are finalized and
                 exported to Excel."
        """
        result = process_ecc_detection(
            "I'll finish the compensation model by Friday at 3 PM. "
            "Done means the revised ranges are finalized and exported "
            "to Excel.",
            'CLEAN',
        )
        self.assertIsNotNone(result)
        self.assertTrue(result['detected'])
        self.assertIsNotNone(result['commitment'])
        self.assertEqual(
            result['response'],
            "Commitment set: Finish the compensation model by Friday "
            "at 3 PM. Done means: The revised ranges are finalized and "
            "exported to Excel."
        )

    def test_action_not_contaminated_with_done_def(self):
        """Action text must not contain done-definition content."""
        result = process_ecc_detection(
            "I will finish the report by 5pm today. "
            "Done means the report is submitted to my manager.",
            'CLEAN',
        )
        self.assertIsNotNone(result['commitment'])
        # Action should NOT contain done-def text
        self.assertNotIn(
            'submitted',
            result['commitment'].normalized_text,
        )
        self.assertEqual(
            result['commitment'].normalized_text,
            'Finish the report',
        )

    def test_capitalization_preserved(self):
        """First letter capitalized, rest preserves original case."""
        result = process_ecc_detection(
            "I'll finish the Excel model today. "
            "Done means the spreadsheet is exported.",
            'CLEAN',
        )
        self.assertIsNotNone(result['commitment'])
        # 'Excel' keeps its capital, first letter capitalized
        self.assertIn('Excel', result['commitment'].normalized_text)
        self.assertTrue(result['commitment'].normalized_text[0].isupper())

    def test_no_double_period(self):
        """Done-definition ending with period should not produce '..'"""
        result = process_ecc_detection(
            "I will finish the report today. "
            "Done means the report is submitted.",
            'CLEAN',
        )
        self.assertNotIn('..', result['response'])

    def test_time_display_human_readable(self):
        """Time display uses original phrase, not datetime format."""
        result = process_ecc_detection(
            "I'll finish the compensation model by Friday at 3 PM. "
            "Done means the model is complete.",
            'CLEAN',
        )
        self.assertIsNotNone(result['commitment'])
        self.assertEqual(
            result['commitment'].time_boundary_display,
            'by Friday at 3 PM',
        )
        # Confirmation should contain the original phrase
        self.assertIn('by Friday at 3 PM', result['response'])
        # Should NOT contain datetime format
        self.assertNotIn('2026-', result['response'])


class PipelineIntegrationTest(TestCase):
    """Test process_ecc_detection pipeline entry point."""

    def test_no_commitment_returns_none(self):
        result = process_ecc_detection("What's the weather?", 'CLEAN')
        self.assertIsNone(result)

    def test_commitment_detected_flag(self):
        result = process_ecc_detection("I will start exercising", 'CLEAN')
        self.assertIsNotNone(result)
        self.assertTrue(result['detected'])

    def test_renegotiation_on_existing_commitment(self):
        existing = Commitment(
            normalized_text='finish the report',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 22, 17, 0),
            done_definition='Report submitted.',
            status='pending',
        )
        result = process_ecc_detection(
            "I'll push it to tomorrow by 5pm",
            'EARLY_EROSION',
            active_commitments=[existing],
        )
        self.assertIsNotNone(result)
        self.assertTrue(result['detected'])
        self.assertIsInstance(result['renegotiation'], RenegotiationBlocked)
        # Response contains the formatted choices
        self.assertIn('A)', result['response'])
        self.assertIn('B)', result['response'])


class RenegotiationPrecedenceTest(TestCase):
    """Renegotiation must take precedence over new commitment formation."""

    def setUp(self):
        self.existing = Commitment(
            normalized_text='Finish the compensation model',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 28, 15, 0),
            done_definition='Revised ranges finalized and exported to Excel',
            status='pending',
        )

    def test_move_triggers_renegotiation_not_new_commitment(self):
        """
        'I'm going to move it to next week instead.' must route to
        renegotiation, NOT new commitment formation.
        """
        result = process_ecc_detection(
            "I'm going to move it to next week instead.",
            'CLEAN',
            active_commitments=[self.existing],
        )
        self.assertIsNotNone(result)
        self.assertTrue(result['detected'])
        # Renegotiation path produced a result (updated commitment, not new)
        # No new MissingField tightening question
        self.assertNotEqual(
            result.get('response'),
            "When specifically will this be completed?",
        )
        self.assertNotEqual(
            result.get('response'),
            "What does 'done' mean in one sentence?",
        )

    def test_move_without_commitment_trigger_still_renegotiates(self):
        """
        'Move it to next week instead.' (no I'll/I will) must still
        route to renegotiation when active commitment exists.
        """
        result = process_ecc_detection(
            "Move it to next week instead.",
            'CLEAN',
            active_commitments=[self.existing],
        )
        self.assertIsNotNone(result, "Renegotiation must fire without 'I will'")
        self.assertTrue(result['detected'])

    def test_push_triggers_renegotiation(self):
        """'Push' is a renegotiation trigger."""
        result = process_ecc_detection(
            "Push this to Friday.",
            'CLEAN',
            active_commitments=[self.existing],
        )
        self.assertIsNotNone(result)
        self.assertTrue(result['detected'])

    def test_delay_triggers_renegotiation(self):
        """'Delay' is a renegotiation trigger."""
        result = process_ecc_detection(
            "I need to delay this.",
            'CLEAN',
            active_commitments=[self.existing],
        )
        self.assertIsNotNone(result)
        self.assertTrue(result['detected'])

    def test_reschedule_triggers_renegotiation(self):
        """'Reschedule' is a renegotiation trigger."""
        result = process_ecc_detection(
            "Reschedule for tomorrow.",
            'CLEAN',
            active_commitments=[self.existing],
        )
        self.assertIsNotNone(result)
        self.assertTrue(result['detected'])

    def test_later_triggers_renegotiation(self):
        """'Later' is a renegotiation trigger."""
        result = process_ecc_detection(
            "Can we do this later?",
            'CLEAN',
            active_commitments=[self.existing],
        )
        self.assertIsNotNone(result)
        self.assertTrue(result['detected'])

    def test_early_erosion_blocks_renegotiation(self):
        """
        EARLY_EROSION tier: renegotiation blocked with A/B choices.
        """
        result = process_ecc_detection(
            "I'm going to move it to next week instead.",
            'EARLY_EROSION',
            active_commitments=[self.existing],
        )
        self.assertIsNotNone(result)
        self.assertTrue(result['detected'])
        self.assertIsInstance(result['renegotiation'], RenegotiationBlocked)
        self.assertEqual(len(result['renegotiation'].choices), 2)
        # Response contains formatted choices
        self.assertIn('A)', result['response'])
        self.assertIn('B)', result['response'])

    def test_no_renegotiation_without_active_commitment(self):
        """
        Renegotiation triggers without active commitment must NOT
        fire renegotiation — fall through to normal detection.
        """
        result = process_ecc_detection(
            "Move it to next week instead.",
            'CLEAN',
            active_commitments=[],
        )
        # No commitment trigger (no I'll/I will) and no active commitment
        # → should return None
        self.assertIsNone(result)

    def test_commitment_formation_skipped_on_renegotiation(self):
        """
        Verify extract_commitment_fields is NOT called when
        renegotiation path executes.
        """
        from unittest.mock import patch
        with patch(
            'apps.core.ai_orchestrator.commitment_contract'
            '.extract_commitment_fields'
        ) as mock_extract:
            process_ecc_detection(
                "I'm going to move it to next week instead.",
                'CLEAN',
                active_commitments=[self.existing],
            )
            mock_extract.assert_not_called()


class RenegotiationReturnDisciplineTest(TestCase):
    """
    Phase 5B: Blocked renegotiation must return RenegotiationBlocked,
    never render a commitment confirmation.
    """

    def setUp(self):
        self.existing = Commitment(
            normalized_text='Finish the compensation model',
            commitment_type='DO',
            time_boundary=datetime(2026, 2, 28, 15, 0),
            done_definition='Revised ranges finalized and exported to Excel',
            status='pending',
        )

    def test_blocked_renegotiation_returns_exact_choices(self):
        """
        EARLY_EROSION + renegotiation trigger → exact A/B deterministic output.
        """
        result = process_ecc_detection(
            "I'm going to move it to next week instead.",
            'EARLY_EROSION',
            active_commitments=[self.existing],
        )
        self.assertIsNotNone(result)
        self.assertTrue(result['detected'])
        # Must be RenegotiationBlocked, NOT Commitment
        self.assertIsInstance(result['renegotiation'], RenegotiationBlocked)
        self.assertIsNone(result['commitment'])
        # Response equals exactly two deterministic A/B lines
        expected = (
            "A) Keep original commitment with a 15\u201330 minute "
            "minimum version now\n"
            "B) Formally cancel and accept consequence"
        )
        self.assertEqual(result['response'], expected)

    def test_blocked_renegotiation_never_renders_confirmation(self):
        """
        Confirmation renderer must NOT be called on blocked renegotiation.
        """
        from unittest.mock import patch
        with patch(
            'apps.core.ai_orchestrator.commitment_contract'
            '.render_commitment_confirmation'
        ) as mock_render:
            result = process_ecc_detection(
                "Push it to Friday.",
                'EARLY_EROSION',
                active_commitments=[self.existing],
            )
            mock_render.assert_not_called()
        # Verify it's blocked
        self.assertIsInstance(result['renegotiation'], RenegotiationBlocked)
        self.assertIsNone(result['commitment'])

    def test_structural_drift_also_blocked(self):
        """STRUCTURAL_DRIFT tier produces same blocking behavior."""
        result = process_ecc_detection(
            "Delay this to next week.",
            'STRUCTURAL_DRIFT',
            active_commitments=[self.existing],
        )
        self.assertIsInstance(result['renegotiation'], RenegotiationBlocked)
        self.assertIsNone(result['commitment'])
        self.assertIn('A)', result['response'])
        self.assertIn('B)', result['response'])

    def test_clean_tier_allows_renegotiation_with_time(self):
        """CLEAN tier with new time → Commitment returned, NOT blocked."""
        result = process_ecc_detection(
            "Move it to tomorrow instead.",
            'CLEAN',
            active_commitments=[self.existing],
        )
        self.assertIsNotNone(result)
        # Should return updated commitment (not blocked)
        self.assertIsNotNone(result.get('commitment'))
        self.assertIsNone(result.get('renegotiation'))
        self.assertIn('Commitment set:', result['response'])

    def test_clean_tier_blocks_without_time(self):
        """CLEAN tier without explicit time → RenegotiationBlocked."""
        result = process_ecc_detection(
            "Can we do this later?",
            'CLEAN',
            active_commitments=[self.existing],
        )
        self.assertIsNotNone(result)
        self.assertIsInstance(result['renegotiation'], RenegotiationBlocked)
        self.assertIsNone(result['commitment'])
