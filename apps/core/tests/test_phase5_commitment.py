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
        # Without explicit time → blocked
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get('blocked'))

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
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get('blocked'))
        self.assertEqual(len(result['choices']), 2)
        self.assertEqual(result['choices'][0]['option'], 'A')
        self.assertEqual(result['choices'][1]['option'], 'B')

    def test_structural_drift_blocks_renegotiation(self):
        result = apply_renegotiation_rules(
            self.commitment,
            "Let me reschedule to next week",
            'STRUCTURAL_DRIFT',
        )
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get('blocked'))
        self.assertEqual(len(result['choices']), 2)

    def test_blocked_choices_are_deterministic(self):
        result = apply_renegotiation_rules(
            self.commitment,
            "I need more time",
            'EARLY_EROSION',
        )
        # Choice A: keep with smaller timebox
        self.assertIn('Keep original commitment', result['choices'][0]['description'])
        # Choice B: formally cancel
        self.assertIn('cancel', result['choices'][1]['description'].lower())


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
        self.assertIsNotNone(result['renegotiation'])
        self.assertTrue(result['renegotiation']['blocked'])
