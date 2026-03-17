# ==============================================================================
# File: apps/life/tests/test_phase6b_email_pipeline.py
# Description: Phase 6B — Email Intelligence Pipeline tests
# Created: 2026-03-17
# ==============================================================================
"""
Tests for Phase 6B: Email Intelligence Pipeline

Test classes:
1. EmailClassifierRuleTests — Rule-based classification (KEEP/SKIP)
2. EmailClassifierLLMTests — LLM classification for UNCERTAIN emails
3. EmailFactExtractorRuleTests — Rule-based fact extraction from emails
4. EmailFactExtractorLLMTests — LLM fact extraction
5. EmailFactServiceTests — Orchestrator: classify → extract → map
6. TransactionDeduplicationTests — Cross-source transaction dedup
7. GmailSyncIntegrationTests — Integration with existing scan pipeline
8. ProcessedEmailModelTests — New fields and metadata tracking
9. IdempotencyTests — Duplicate prevention
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from apps.users.models import User


def _create_test_user(email='test-phase6b@example.com'):
    """Create a test user with required setup."""
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password='testpass123')
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.save()
    return user


def _make_email(
    gmail_id='msg_001', subject='Test Email', sender='test@example.com',
    body='This is a test email body.', date_str='2026-03-17',
):
    """Create a test email dict matching GmailService format."""
    return {
        'id': gmail_id,
        'subject': subject,
        'sender': sender,
        'body': body,
        'date': date_str,
        'date_parsed': None,
        'snippet': body[:200],
    }


# =========================================================================
# 1. Email Classifier Rule Tests
# =========================================================================

class EmailClassifierRuleTests(TestCase):
    """Test rule-based email classification."""

    def test_wlj_flagged_always_keep(self):
        from apps.life.services.email_classifier import classify_email
        email = _make_email(subject='[WLJ] My medical bill')
        result = classify_email(email)
        self.assertEqual(result['classification'], 'keep')
        self.assertEqual(result['confidence'], 1.0)
        self.assertTrue(result['wlj_flagged'])
        self.assertEqual(result['reason'], 'rule:wlj_flagged')

    def test_noreply_sender_skip(self):
        from apps.life.services.email_classifier import classify_email
        email = _make_email(sender='noreply@company.com')
        result = classify_email(email)
        self.assertEqual(result['classification'], 'skip')
        self.assertEqual(result['reason'], 'rule:skip_sender')

    def test_newsletter_subject_skip(self):
        from apps.life.services.email_classifier import classify_email
        email = _make_email(subject='Your Weekly Digest from Medium')
        result = classify_email(email)
        self.assertEqual(result['classification'], 'skip')
        self.assertEqual(result['reason'], 'rule:skip_subject')

    def test_empty_body_skip(self):
        from apps.life.services.email_classifier import classify_email
        email = _make_email(body='short')
        result = classify_email(email)
        self.assertEqual(result['classification'], 'skip')
        self.assertEqual(result['reason'], 'rule:empty_body')

    def test_financial_pattern_keep(self):
        from apps.life.services.email_classifier import classify_email
        email = _make_email(
            subject='Your payment of $45.99',
            body='Your payment of $45.99 to Netflix has been processed.',
        )
        result = classify_email(email)
        self.assertEqual(result['classification'], 'keep')
        self.assertEqual(result['reason'], 'rule:financial_pattern')

    def test_health_pattern_keep(self):
        from apps.life.services.email_classifier import classify_email
        email = _make_email(
            subject='Appointment confirmed',
            body='Your appointment on March 20 with Dr. Smith is confirmed.',
        )
        result = classify_email(email)
        self.assertEqual(result['classification'], 'keep')
        self.assertEqual(result['reason'], 'rule:health_pattern')

    def test_subscription_pattern_keep(self):
        from apps.life.services.email_classifier import classify_email
        email = _make_email(
            subject='Subscription renewal notice',
            body='Your subscription renewal is scheduled for April 1.',
        )
        result = classify_email(email)
        self.assertEqual(result['classification'], 'keep')
        self.assertEqual(result['reason'], 'rule:subscription_pattern')

    def test_uncertain_when_no_rules_match(self):
        from apps.life.services.email_classifier import classify_email
        email = _make_email(
            sender='friend@example.com',
            subject='Hey, how are you?',
            body='Just checking in. Hope everything is going well with you and your family. Let me know if you want to grab lunch sometime.',
        )
        result = classify_email(email)
        self.assertEqual(result['classification'], 'uncertain')
        self.assertEqual(result['method'], 'pending_llm')

    def test_dollar_amount_in_body_triggers_financial(self):
        from apps.life.services.email_classifier import classify_email
        email = _make_email(
            subject='Order confirmation',
            body='Your order total is $129.50. Thank you for shopping with us.',
        )
        result = classify_email(email)
        self.assertEqual(result['classification'], 'keep')

    def test_prescription_ready_triggers_health(self):
        from apps.life.services.email_classifier import classify_email
        email = _make_email(
            subject='Prescription ready for pickup',
            body='Your prescription is ready at CVS Pharmacy #1234.',
        )
        result = classify_email(email)
        self.assertEqual(result['classification'], 'keep')
        self.assertEqual(result['reason'], 'rule:health_pattern')


# =========================================================================
# 2. Email Classifier LLM Tests
# =========================================================================

class EmailClassifierLLMTests(TestCase):
    """Test LLM classification for UNCERTAIN emails."""

    @patch('apps.ai.services.get_openai_client')
    def test_llm_classifies_keep(self, mock_client):
        from apps.life.services.email_classifier import classify_with_llm
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"classification": "KEEP", "reason": "personal health info", '
            '"confidence": 0.85}'
        )
        mock_client.return_value.chat.completions.create.return_value = mock_response

        email = _make_email(body='Your lab results are available.')
        result = classify_with_llm(email)
        self.assertEqual(result['classification'], 'keep')
        self.assertGreater(result['confidence'], 0.8)

    @patch('apps.ai.services.get_openai_client')
    def test_llm_classifies_skip(self, mock_client):
        from apps.life.services.email_classifier import classify_with_llm
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"classification": "SKIP", "reason": "social notification", '
            '"confidence": 0.90}'
        )
        mock_client.return_value.chat.completions.create.return_value = mock_response

        email = _make_email(body='John liked your photo.')
        result = classify_with_llm(email)
        self.assertEqual(result['classification'], 'skip')

    @patch('apps.ai.services.get_openai_client')
    def test_llm_unavailable_defaults_to_skip(self, mock_client):
        from apps.life.services.email_classifier import classify_with_llm
        mock_client.return_value = None

        email = _make_email()
        result = classify_with_llm(email)
        self.assertEqual(result['classification'], 'skip')
        self.assertIn('unavailable', result['reason'])


# =========================================================================
# 3. Email Fact Extractor Rule Tests
# =========================================================================

class EmailFactExtractorRuleTests(TestCase):
    """Test rule-based fact extraction from emails."""

    def test_extracts_amount_from_email(self):
        from apps.life.services.email_fact_extractor import _extract_rules
        email = _make_email(
            subject='Payment received',
            body='Your payment of $45.99 from Netflix has been processed.',
        )
        candidates = _extract_rules(email)
        self.assertTrue(len(candidates) > 0)
        amount_facts = [c for c in candidates if c['fact_type'] == 'amount']
        self.assertTrue(len(amount_facts) > 0)
        self.assertEqual(amount_facts[0]['structured_value']['value'], 45.99)

    def test_extracts_obligation_from_email(self):
        from apps.life.services.email_fact_extractor import _extract_rules
        email = _make_email(
            subject='Electric bill due',
            body='Your bill of $142.00 is due by March 25, 2026.',
        )
        candidates = _extract_rules(email)
        obligation_facts = [
            c for c in candidates if c['fact_type'] == 'obligation'
        ]
        self.assertTrue(len(obligation_facts) > 0)
        self.assertEqual(
            obligation_facts[0]['structured_value']['amount'], 142.00,
        )

    def test_extracts_medication_from_email(self):
        from apps.life.services.email_fact_extractor import _extract_rules
        email = _make_email(
            subject='Prescription refill',
            body='Your prescription for Metformin is ready for pickup.',
        )
        candidates = _extract_rules(email)
        med_facts = [c for c in candidates if c['fact_type'] == 'medication']
        self.assertTrue(len(med_facts) > 0)
        self.assertIn('Metformin', med_facts[0]['structured_value']['name'])

    def test_extracts_appointment_from_email(self):
        from apps.life.services.email_fact_extractor import _extract_rules
        email = _make_email(
            subject='Appointment confirmation',
            body='Your appointment on March 20, 2026 is confirmed.',
        )
        candidates = _extract_rules(email)
        appt_facts = [
            c for c in candidates if c['fact_type'] == 'appointment'
        ]
        self.assertTrue(len(appt_facts) > 0)

    def test_no_facts_from_plain_email(self):
        from apps.life.services.email_fact_extractor import _extract_rules
        email = _make_email(
            subject='Hey there',
            body='Just checking in to see how you are doing today.',
        )
        candidates = _extract_rules(email)
        self.assertEqual(len(candidates), 0)

    def test_skips_tiny_amounts(self):
        from apps.life.services.email_fact_extractor import _extract_rules
        email = _make_email(body='Save $0.00 on your next purchase!')
        candidates = _extract_rules(email)
        amount_facts = [c for c in candidates if c['fact_type'] == 'amount']
        self.assertEqual(len(amount_facts), 0)


# =========================================================================
# 4. Email Fact Extractor LLM Tests
# =========================================================================

class EmailFactExtractorLLMTests(TestCase):
    """Test LLM-based fact extraction from emails."""

    @patch('apps.ai.services.get_openai_client')
    def test_llm_extracts_facts(self, mock_client):
        from apps.life.services.email_fact_extractor import _call_openai
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"facts": [{"fact_type": "amount", "confidence": 0.9, '
            '"extracted_text": "$45.99 payment", '
            '"structured_value": {"value": 45.99, "currency": "USD", '
            '"merchant": "Netflix"}, '
            '"effective_date": "2026-03-17", "domain_hint": "finance"}]}'
        )
        mock_client.return_value.chat.completions.create.return_value = mock_response

        email = _make_email(body='$45.99 Netflix payment')
        facts = _call_openai(email)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]['fact_type'], 'amount')

    @patch('apps.ai.services.get_openai_client')
    def test_llm_unavailable_returns_empty(self, mock_client):
        from apps.life.services.email_fact_extractor import _call_openai
        mock_client.return_value = None

        email = _make_email()
        facts = _call_openai(email)
        self.assertEqual(facts, [])


# =========================================================================
# 5. Email Fact Service (Orchestrator) Tests
# =========================================================================

class EmailFactServiceTests(TestCase):
    """Test the orchestration: classify → extract → map."""

    def setUp(self):
        self.user = _create_test_user()

    @patch('apps.ai.services.get_openai_client')
    @patch('apps.ai.services.get_openai_client')
    def test_skipped_email_not_extracted(self, mock_ext_client, mock_cls_client):
        from apps.life.services.email_fact_service import (
            EmailFactExtractionService,
        )
        from apps.life.models import ProcessedEmail

        # noreply sender → auto-SKIP → no fact extraction
        emails = [_make_email(
            gmail_id='skip_001',
            sender='noreply@marketing.com',
        )]
        service = EmailFactExtractionService(self.user)
        stats = service.process_emails(emails)

        self.assertEqual(stats['emails_skipped'], 1)
        self.assertEqual(stats['facts_created'], 0)

        pe = ProcessedEmail.objects.get(
            user=self.user, gmail_message_id='skip_001',
        )
        self.assertEqual(pe.classification, 'skip')
        self.assertFalse(pe.facts_extracted)  # Skipped — no extraction ran

    @patch('apps.ai.services.get_openai_client')
    def test_financial_email_creates_facts(self, mock_client):
        from apps.life.services.email_fact_service import (
            EmailFactExtractionService,
        )
        from apps.core.ai_eae.models import ExtractedFact

        # Financial pattern → auto-KEEP → rule extraction → facts
        emails = [_make_email(
            gmail_id='keep_001',
            subject='Payment received',
            body='Your payment of $99.50 from Acme Corp has been processed.',
        )]
        service = EmailFactExtractionService(self.user)
        stats = service.process_emails(emails)

        self.assertEqual(stats['emails_kept'], 1)
        self.assertGreater(stats['facts_created'], 0)

        # Verify ExtractedFact was created with source_type='email'
        facts = ExtractedFact.objects.filter(
            user=self.user, source_type='email',
        )
        self.assertTrue(facts.exists())

    @patch('apps.ai.services.get_openai_client')
    def test_processed_email_metadata_stored(self, mock_client):
        from apps.life.services.email_fact_service import (
            EmailFactExtractionService,
        )
        from apps.life.models import ProcessedEmail

        emails = [_make_email(
            gmail_id='meta_001',
            subject='Your $50.00 payment',
            sender='billing@company.com',
            body='Your payment of $50.00 has been received.',
        )]
        service = EmailFactExtractionService(self.user)
        service.process_emails(emails)

        pe = ProcessedEmail.objects.get(
            user=self.user, gmail_message_id='meta_001',
        )
        self.assertEqual(pe.subject, 'Your $50.00 payment')
        self.assertEqual(pe.sender, 'billing@company.com')
        self.assertIn('payment', pe.snippet)
        self.assertTrue(pe.facts_extracted)
        self.assertTrue(pe.classification_confidence > 0)


# =========================================================================
# 6. Transaction Deduplication Tests
# =========================================================================

class TransactionDeduplicationTests(TestCase):
    """Test cross-source transaction deduplication."""

    def setUp(self):
        self.user = _create_test_user('test-txdedup@example.com')
        from apps.finance.models import FinancialAccount
        self.account = FinancialAccount.objects.create(
            user=self.user,
            name='Checking',
            account_type='checking',
        )

    def test_no_duplicate_email_transaction(self):
        """Same email should not create duplicate transactions."""
        from apps.finance.models import Transaction
        from apps.life.services.email_fact_service import (
            _create_email_transactions,
        )
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import ProcessedEmail

        # Create ProcessedEmail source
        pe = ProcessedEmail.objects.create(
            user=self.user, gmail_message_id='tx_test_001',
        )
        ct = ContentType.objects.get_for_model(pe)

        # Create fact
        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='amount',
            structured_value={'value': 45.99, 'currency': 'USD', 'merchant': 'Test'},
            confidence=0.7,
            extracted_text='$45.99 payment',
            effective_date=date.today(),
        )

        # First creation
        count1 = _create_email_transactions(self.user, [fact])
        self.assertEqual(count1, 1)

        # Second attempt — should be deduped
        count2 = _create_email_transactions(self.user, [fact])
        self.assertEqual(count2, 0)

    def test_cross_source_dedup(self):
        """Transaction from another source with same amount/date blocks email tx."""
        from apps.finance.models import Transaction
        from apps.life.services.email_fact_service import (
            _create_email_transactions,
        )
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import ProcessedEmail

        today = date.today()

        # Existing transaction from a different source
        Transaction.objects.create(
            user=self.user,
            account=self.account,
            date=today,
            amount=Decimal('-45.99'),
            description='Netflix',
            source_type='import',
        )

        # Try to create from email fact
        pe = ProcessedEmail.objects.create(
            user=self.user, gmail_message_id='tx_dedup_001',
        )
        ct = ContentType.objects.get_for_model(pe)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='amount',
            structured_value={'value': 45.99, 'currency': 'USD', 'merchant': 'Netflix'},
            confidence=0.7,
            extracted_text='$45.99 Netflix',
            effective_date=today,
        )

        count = _create_email_transactions(self.user, [fact])
        self.assertEqual(count, 0)  # Deduped by cross-source check


# =========================================================================
# 7. Gmail Sync Integration Tests
# =========================================================================

class GmailSyncIntegrationTests(TestCase):
    """Test integration with existing GmailSyncService."""

    def setUp(self):
        self.user = _create_test_user('test-sync@example.com')

    def test_run_fact_extraction_method_exists(self):
        """GmailSyncService has the _run_fact_extraction method."""
        from apps.life.services.gmail_sync import GmailSyncService
        sync = GmailSyncService()
        self.assertTrue(hasattr(sync, '_run_fact_extraction'))

    def test_run_fact_extraction_handles_empty(self):
        """_run_fact_extraction returns empty dict on empty email list."""
        from apps.life.services.gmail_sync import GmailSyncService
        sync = GmailSyncService()
        result = sync._run_fact_extraction(self.user, [])
        self.assertEqual(result.get('facts_created', 0), 0)

    def test_run_fact_extraction_processes_emails(self):
        """_run_fact_extraction processes financial emails."""
        from apps.life.services.gmail_sync import GmailSyncService
        sync = GmailSyncService()
        emails = [_make_email(
            gmail_id='sync_001',
            subject='Payment of $50.00',
            body='Your payment of $50.00 has been received from Acme Corp.',
        )]
        result = sync._run_fact_extraction(self.user, emails)
        self.assertIn('facts_created', result)
        self.assertGreaterEqual(result['facts_created'], 0)


# =========================================================================
# 8. ProcessedEmail Model Tests
# =========================================================================

class ProcessedEmailModelTests(TestCase):
    """Test ProcessedEmail new fields."""

    def setUp(self):
        self.user = _create_test_user('test-pemodel@example.com')

    def test_new_fields_have_defaults(self):
        from apps.life.models import ProcessedEmail
        pe = ProcessedEmail.objects.create(
            user=self.user,
            gmail_message_id='model_test_001',
        )
        self.assertEqual(pe.subject, '')
        self.assertEqual(pe.sender, '')
        self.assertEqual(pe.snippet, '')
        self.assertIsNone(pe.received_date)
        self.assertEqual(pe.classification, '')
        self.assertEqual(pe.classification_reason, '')
        self.assertEqual(pe.classification_confidence, 0.0)
        self.assertFalse(pe.facts_extracted)
        self.assertEqual(pe.facts_created_count, 0)

    def test_classification_choices(self):
        from apps.life.models import ProcessedEmail
        pe = ProcessedEmail.objects.create(
            user=self.user,
            gmail_message_id='class_test_001',
            classification='keep',
            classification_reason='rule:financial_pattern',
            classification_confidence=0.85,
        )
        self.assertEqual(pe.classification, 'keep')

    def test_metadata_stored_correctly(self):
        from apps.life.models import ProcessedEmail
        pe = ProcessedEmail.objects.create(
            user=self.user,
            gmail_message_id='meta_test_001',
            subject='Test Subject',
            sender='test@example.com',
            snippet='This is a test snippet...',
            received_date=timezone.now(),
            facts_extracted=True,
            facts_created_count=3,
        )
        pe.refresh_from_db()
        self.assertEqual(pe.subject, 'Test Subject')
        self.assertEqual(pe.sender, 'test@example.com')
        self.assertTrue(pe.facts_extracted)
        self.assertEqual(pe.facts_created_count, 3)


# =========================================================================
# 9. Idempotency Tests
# =========================================================================

class IdempotencyTests(TestCase):
    """Test duplicate prevention across the pipeline."""

    def setUp(self):
        self.user = _create_test_user('test-idemp@example.com')

    def test_fact_extraction_idempotent(self):
        """Same email processed twice should not create duplicate facts."""
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import ProcessedEmail
        from apps.life.services.email_fact_extractor import EmailFactExtractor

        pe = ProcessedEmail.objects.create(
            user=self.user,
            gmail_message_id='idemp_001',
        )

        email = _make_email(
            gmail_id='idemp_001',
            body='Payment of $75.00 received from Netflix.',
        )

        # First extraction
        facts1 = EmailFactExtractor.extract_facts(
            self.user, email, pe,
        )

        # Second extraction — should skip (idempotency gate)
        facts2 = EmailFactExtractor.extract_facts(
            self.user, email, pe,
        )
        self.assertEqual(len(facts2), 0)

    @patch('apps.ai.services.get_openai_client')
    def test_service_skips_already_extracted(self, mock_client):
        """EmailFactExtractionService skips emails with facts_extracted=True."""
        from apps.life.models import ProcessedEmail
        from apps.life.services.email_fact_service import (
            EmailFactExtractionService,
        )

        # Pre-create ProcessedEmail with facts_extracted=True
        ProcessedEmail.objects.create(
            user=self.user,
            gmail_message_id='already_001',
            facts_extracted=True,
        )

        emails = [_make_email(gmail_id='already_001')]
        service = EmailFactExtractionService(self.user)
        stats = service.process_emails(emails)

        # Should have been skipped entirely
        self.assertEqual(stats['emails_classified'], 0)
        self.assertEqual(stats['facts_created'], 0)


# =========================================================================
# 10. Learning Override Tests
# =========================================================================

class LearningOverrideTests(TestCase):
    """Test EmailClassificationFeedback learning hook."""

    def setUp(self):
        self.user = _create_test_user('test-learning@example.com')

    def test_learned_keep_sender_overrides_rules(self):
        """A learned KEEP sender bypasses all rule checks."""
        from apps.life.models import EmailClassificationFeedback
        from apps.life.services.email_classifier import classify_email

        # This sender would normally be SKIP (noreply pattern)
        EmailClassificationFeedback.objects.create(
            user=self.user,
            sender='noreply@important-bank.com',
            original_classification='skip',
            corrected_classification='keep',
        )

        email = _make_email(sender='noreply@important-bank.com')
        result = classify_email(email, user=self.user)
        self.assertEqual(result['classification'], 'keep')
        self.assertEqual(result['method'], 'learned')

    def test_learned_skip_sender_overrides_rules(self):
        """A learned SKIP sender bypasses KEEP patterns."""
        from apps.life.models import EmailClassificationFeedback
        from apps.life.services.email_classifier import classify_email

        # This would normally be KEEP (financial pattern)
        EmailClassificationFeedback.objects.create(
            user=self.user,
            sender='spam@company.com',
            original_classification='keep',
            corrected_classification='skip',
        )

        email = _make_email(
            sender='spam@company.com',
            body='Your payment of $99.99 is due.',
        )
        result = classify_email(email, user=self.user)
        self.assertEqual(result['classification'], 'skip')
        self.assertEqual(result['method'], 'learned')

    def test_no_override_without_user(self):
        """Classifier works without user (dry run mode)."""
        from apps.life.services.email_classifier import classify_email
        email = _make_email(sender='noreply@company.com')
        result = classify_email(email, user=None)
        self.assertEqual(result['classification'], 'skip')
        self.assertEqual(result['method'], 'rule')

    def test_sender_normalized_to_lowercase(self):
        """Sender is normalized to lowercase for matching."""
        from apps.life.models import EmailClassificationFeedback
        fb = EmailClassificationFeedback.objects.create(
            user=self.user,
            sender='Test@EXAMPLE.COM',
            corrected_classification='keep',
        )
        fb.refresh_from_db()
        self.assertEqual(fb.sender, 'test@example.com')

    def test_feedback_model_unique_constraint(self):
        """Same user + sender can't have duplicate feedback."""
        from apps.life.models import EmailClassificationFeedback
        from django.db import IntegrityError
        EmailClassificationFeedback.objects.create(
            user=self.user,
            sender='test@example.com',
            corrected_classification='keep',
        )
        with self.assertRaises(IntegrityError):
            EmailClassificationFeedback.objects.create(
                user=self.user,
                sender='test@example.com',
                corrected_classification='skip',
            )


# =========================================================================
# 11. Transaction Fingerprint Tests
# =========================================================================

class TransactionFingerprintTests(TestCase):
    """Test fingerprint-based transaction dedup."""

    def setUp(self):
        self.user = _create_test_user('test-fp@example.com')
        from apps.finance.models import FinancialAccount
        self.account = FinancialAccount.objects.create(
            user=self.user,
            name='Checking',
            account_type='checking',
        )

    def test_compute_fingerprint_deterministic(self):
        from apps.life.services.email_fact_service import _compute_fingerprint
        fp1 = _compute_fingerprint('Netflix', 15.99, date(2026, 3, 17))
        fp2 = _compute_fingerprint('Netflix', 15.99, date(2026, 3, 17))
        self.assertEqual(fp1, fp2)

    def test_fingerprint_normalized(self):
        """Different casing/punctuation produces same fingerprint."""
        from apps.life.services.email_fact_service import _compute_fingerprint
        fp1 = _compute_fingerprint('Netflix Inc.', 15.99, date(2026, 3, 17))
        fp2 = _compute_fingerprint('netflix inc', 15.99, date(2026, 3, 17))
        self.assertEqual(fp1, fp2)

    def test_fingerprint_different_amount_differs(self):
        from apps.life.services.email_fact_service import _compute_fingerprint
        fp1 = _compute_fingerprint('Netflix', 15.99, date(2026, 3, 17))
        fp2 = _compute_fingerprint('Netflix', 25.99, date(2026, 3, 17))
        self.assertNotEqual(fp1, fp2)

    def test_fingerprint_blocks_duplicate_tx(self):
        """Transaction with same fingerprint is not created."""
        from apps.finance.models import Transaction
        from apps.life.services.email_fact_service import (
            _compute_fingerprint,
            _create_email_transactions,
        )
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import ProcessedEmail

        fp = _compute_fingerprint('Netflix', 15.99, date.today())

        # Pre-existing transaction with same fingerprint
        Transaction.objects.create(
            user=self.user,
            account=self.account,
            date=date.today(),
            amount=Decimal('-15.99'),
            description='Netflix',
            source_type='import',
            fingerprint=fp,
        )

        # Create fact for email transaction
        pe = ProcessedEmail.objects.create(
            user=self.user, gmail_message_id='fp_test_001',
        )
        ct = ContentType.objects.get_for_model(pe)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='amount',
            structured_value={'value': 15.99, 'merchant': 'Netflix'},
            confidence=0.7,
            extracted_text='$15.99 Netflix',
            effective_date=date.today(),
        )

        count = _create_email_transactions(self.user, [fact])
        self.assertEqual(count, 0)


# =========================================================================
# 12. Receipt → Document Tests
# =========================================================================

class ReceiptDocumentTests(TestCase):
    """Test receipt email → Document creation."""

    def setUp(self):
        self.user = _create_test_user('test-receipt@example.com')
        from apps.finance.models import FinancialAccount
        self.account = FinancialAccount.objects.create(
            user=self.user,
            name='Checking',
            account_type='checking',
        )

    def test_receipt_detection(self):
        from apps.life.services.email_fact_service import _is_receipt_email
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import ProcessedEmail

        pe = ProcessedEmail.objects.create(
            user=self.user, gmail_message_id='receipt_det_001',
        )
        ct = ContentType.objects.get_for_model(pe)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='amount',
            structured_value={'value': 45.99},
            confidence=0.7,
            extracted_text='$45.99',
        )

        email = _make_email(subject='Your receipt from Amazon')
        self.assertTrue(_is_receipt_email(email, [fact]))

    def test_non_receipt_not_detected(self):
        from apps.life.services.email_fact_service import _is_receipt_email
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import ProcessedEmail

        pe = ProcessedEmail.objects.create(
            user=self.user, gmail_message_id='no_receipt_001',
        )
        ct = ContentType.objects.get_for_model(pe)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='amount',
            structured_value={'value': 45.99},
            confidence=0.7,
            extracted_text='$45.99',
        )

        email = _make_email(subject='Hey how are you?')
        self.assertFalse(_is_receipt_email(email, [fact]))

    def test_receipt_creates_document(self):
        from apps.life.models import Document, ProcessedEmail
        from apps.life.services.email_fact_service import (
            _create_receipt_documents,
        )
        from apps.core.ai_eae.models import ExtractedFact

        pe = ProcessedEmail.objects.create(
            user=self.user,
            gmail_message_id='doc_test_001',
            received_date=timezone.now(),
        )
        ct = ContentType.objects.get_for_model(pe)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='amount',
            structured_value={'value': 99.50},
            confidence=0.7,
            extracted_text='$99.50',
        )

        email = _make_email(
            gmail_id='doc_test_001',
            subject='Your receipt from Best Buy',
            body='Thank you for your purchase of $99.50.',
        )

        count = _create_receipt_documents(
            self.user, [(email, pe, [fact])],
        )
        self.assertEqual(count, 1)

        doc = Document.objects.get(
            user=self.user, source='email', source_id='doc_test_001',
        )
        self.assertEqual(doc.category, 'financial')
        self.assertEqual(doc.subcategory, 'receipt')
        self.assertEqual(doc.source, 'email')
        self.assertIn('$99.50', doc.raw_text)

    def test_no_duplicate_receipt_document(self):
        from apps.life.models import Document, ProcessedEmail
        from apps.life.services.email_fact_service import (
            _create_receipt_documents,
        )
        from apps.core.ai_eae.models import ExtractedFact

        pe = ProcessedEmail.objects.create(
            user=self.user,
            gmail_message_id='dup_doc_001',
            received_date=timezone.now(),
        )
        ct = ContentType.objects.get_for_model(pe)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='amount',
            structured_value={'value': 50.00},
            confidence=0.7,
            extracted_text='$50.00',
        )

        email = _make_email(
            gmail_id='dup_doc_001',
            subject='Receipt for order',
            body='$50.00 payment.',
        )

        # First call creates
        _create_receipt_documents(self.user, [(email, pe, [fact])])
        # Second call skips
        count = _create_receipt_documents(
            self.user, [(email, pe, [fact])],
        )
        self.assertEqual(count, 0)
        self.assertEqual(
            Document.objects.filter(
                user=self.user, source='email', source_id='dup_doc_001',
            ).count(),
            1,
        )


# =========================================================================
# 13. Intent Type Tests
# =========================================================================

class IntentTypeTests(TestCase):
    """Test intent_type assignment on ExtractedFact."""

    def setUp(self):
        self.user = _create_test_user('test-intent@example.com')

    def test_obligation_gets_bill_due(self):
        from apps.life.services.email_fact_service import _assign_intent_types
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import ProcessedEmail

        pe = ProcessedEmail.objects.create(
            user=self.user, gmail_message_id='intent_001',
        )
        ct = ContentType.objects.get_for_model(pe)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='obligation',
            structured_value={'amount': 100, 'description': 'Electric bill'},
            confidence=0.7,
            extracted_text='bill of $100',
        )

        _assign_intent_types([fact])
        fact.refresh_from_db()
        self.assertEqual(fact.intent_type, 'bill_due')

    def test_appointment_gets_schedule_commitment(self):
        from apps.life.services.email_fact_service import _assign_intent_types
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import ProcessedEmail

        pe = ProcessedEmail.objects.create(
            user=self.user, gmail_message_id='intent_002',
        )
        ct = ContentType.objects.get_for_model(pe)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='appointment',
            structured_value={'provider': 'Dr. Smith', 'datetime': '2026-03-20'},
            confidence=0.8,
            extracted_text='appointment on March 20',
        )

        _assign_intent_types([fact])
        fact.refresh_from_db()
        self.assertEqual(fact.intent_type, 'schedule_commitment')

    def test_subscription_gets_recurring_obligation(self):
        from apps.life.services.email_fact_service import _assign_intent_types
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import ProcessedEmail

        pe = ProcessedEmail.objects.create(
            user=self.user, gmail_message_id='intent_003',
        )
        ct = ContentType.objects.get_for_model(pe)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='subscription',
            structured_value={'service': 'Netflix', 'amount': 15.99},
            confidence=0.75,
            extracted_text='Netflix subscription $15.99',
        )

        _assign_intent_types([fact])
        fact.refresh_from_db()
        self.assertEqual(fact.intent_type, 'recurring_obligation')

    def test_amount_has_no_intent(self):
        """Plain amount facts don't get intent_type."""
        from apps.life.services.email_fact_service import _assign_intent_types
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import ProcessedEmail

        pe = ProcessedEmail.objects.create(
            user=self.user, gmail_message_id='intent_004',
        )
        ct = ContentType.objects.get_for_model(pe)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='amount',
            structured_value={'value': 42.00},
            confidence=0.7,
            extracted_text='$42.00',
        )

        _assign_intent_types([fact])
        fact.refresh_from_db()
        self.assertEqual(fact.intent_type, '')


# =========================================================================
# 14. Email Body Cleaner Tests (Phase 6B.5)
# =========================================================================

class EmailBodyCleanerTests(TestCase):
    """Test clean_email_body() deterministic cleaning."""

    def test_strips_html_tags(self):
        from apps.life.services.email_body_cleaner import clean_email_body

        html_body = '<p>Your receipt for <b>$42.00</b> from Amazon</p>'
        result = clean_email_body(html_body)
        self.assertNotIn('<p>', result)
        self.assertNotIn('<b>', result)
        self.assertIn('$42.00', result)
        self.assertIn('Amazon', result)

    def test_decodes_html_entities(self):
        from apps.life.services.email_body_cleaner import clean_email_body

        body = 'Total: $42.00 &amp; tax &lt;included&gt;'
        result = clean_email_body(body)
        self.assertIn('& tax', result)
        self.assertIn('<included>', result)

    def test_removes_script_style_blocks(self):
        from apps.life.services.email_body_cleaner import clean_email_body

        body = (
            '<style>.hidden { display: none; }</style>'
            '<p>Receipt: $100</p>'
            '<script>trackEvent("open");</script>'
        )
        result = clean_email_body(body)
        self.assertNotIn('hidden', result)
        self.assertNotIn('trackEvent', result)
        self.assertIn('Receipt: $100', result)

    def test_removes_footer_noise(self):
        from apps.life.services.email_body_cleaner import clean_email_body

        body = (
            'Your payment of $50.00 was received.\n'
            '---\n'
            'Unsubscribe from these notifications\n'
            'Privacy Policy | Terms of Service\n'
            '© 2026 Example Corp. All rights reserved.'
        )
        result = clean_email_body(body)
        self.assertIn('$50.00', result)
        self.assertNotIn('Unsubscribe', result)

    def test_normalizes_whitespace(self):
        from apps.life.services.email_body_cleaner import clean_email_body

        body = 'Line one   \n\n\n\n\n  Line two    \n\n\n   Line three'
        result = clean_email_body(body)
        # Should not have 3+ consecutive newlines
        self.assertNotIn('\n\n\n', result)
        self.assertIn('Line one', result)
        self.assertIn('Line two', result)

    def test_truncates_to_max_length(self):
        from apps.life.services.email_body_cleaner import clean_email_body

        body = 'x' * 5000
        result = clean_email_body(body, max_length=100)
        self.assertLessEqual(len(result), 100)

    def test_empty_body_returns_empty(self):
        from apps.life.services.email_body_cleaner import clean_email_body

        self.assertEqual(clean_email_body(''), '')
        self.assertEqual(clean_email_body(None), '')

    def test_preserves_receipt_content(self):
        from apps.life.services.email_body_cleaner import clean_email_body

        body = (
            '<html><body>'
            '<h1>Order Confirmation</h1>'
            '<p>Order #12345</p>'
            '<p>Item: Widget - $29.99</p>'
            '<p>Tax: $2.40</p>'
            '<p>Total: $32.39</p>'
            '</body></html>'
        )
        result = clean_email_body(body)
        self.assertIn('Order Confirmation', result)
        self.assertIn('Order #12345', result)
        self.assertIn('$29.99', result)
        self.assertIn('$32.39', result)


# =========================================================================
# 15. Merchant Normalizer Tests (Phase 6B.5)
# =========================================================================

class MerchantNormalizerTests(TestCase):
    """Test normalize_merchant() deterministic normalization."""

    def test_basic_lowercase_cleanup(self):
        from apps.life.services.merchant_normalizer import normalize_merchant

        self.assertEqual(normalize_merchant('  Netflix  '), 'netflix')

    def test_alias_resolution_amzn(self):
        from apps.life.services.merchant_normalizer import normalize_merchant

        self.assertEqual(normalize_merchant('AMZN'), 'amazon')
        self.assertEqual(normalize_merchant('AMZN MKTPLACE'), 'amazon')
        self.assertEqual(normalize_merchant('Amazon.com'), 'amazon')

    def test_alias_resolution_apple(self):
        from apps.life.services.merchant_normalizer import normalize_merchant

        self.assertEqual(normalize_merchant('APPLE.COM/STORE/BILL'), 'apple')
        self.assertEqual(normalize_merchant('iTunes'), 'apple')

    def test_noise_token_removal(self):
        from apps.life.services.merchant_normalizer import normalize_merchant

        result = normalize_merchant('Acme Corp Inc')
        self.assertEqual(result, 'acme')

    def test_punctuation_stripped(self):
        from apps.life.services.merchant_normalizer import normalize_merchant

        result = normalize_merchant('Joe\'s Pizza & Grill')
        self.assertNotIn("'", result)
        self.assertNotIn('&', result)

    def test_empty_returns_empty(self):
        from apps.life.services.merchant_normalizer import normalize_merchant

        self.assertEqual(normalize_merchant(''), '')
        self.assertEqual(normalize_merchant(None), '')

    def test_deterministic(self):
        from apps.life.services.merchant_normalizer import normalize_merchant

        a = normalize_merchant('AMZN Digital')
        b = normalize_merchant('AMZN Digital')
        self.assertEqual(a, b)

    def test_fingerprint_uses_normalized(self):
        """Fingerprints for AMZN and Amazon should match."""
        from apps.life.services.email_fact_service import _compute_fingerprint

        fp1 = _compute_fingerprint('AMZN', 42.00, date(2026, 3, 17))
        fp2 = _compute_fingerprint('Amazon.com', 42.00, date(2026, 3, 17))
        self.assertEqual(fp1, fp2)


# =========================================================================
# 16. Intent Propagation Tests (Phase 6B.5)
# =========================================================================

class IntentPropagationTests(TestCase):
    """Test intent_type propagation into SignalSnapshot metadata."""

    def setUp(self):
        self.user = _create_test_user('test-intent-prop@example.com')

    def test_intent_type_in_fact_info(self):
        """intent_type should appear in fact_info dict from _map_facts_to_signals."""
        from apps.core.ai_eae.fact_signal_mapper import _map_facts_to_signals
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import ProcessedEmail

        pe = ProcessedEmail.objects.create(
            user=self.user, gmail_message_id='intent_prop_001',
        )
        ct = ContentType.objects.get_for_model(pe)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='obligation',
            structured_value={'amount': 100, 'description': 'Electric bill'},
            confidence=0.7,
            extracted_text='bill of $100',
            intent_type='bill_due',
        )

        signal_map = _map_facts_to_signals([fact])
        # Should have one date with financial_health signal
        for date_key, by_type in signal_map.items():
            for signal_type, fact_infos in by_type.items():
                self.assertEqual(fact_infos[0]['intent_type'], 'bill_due')

    def test_no_intent_type_when_empty(self):
        """Facts without intent_type should not include the key."""
        from apps.core.ai_eae.fact_signal_mapper import _map_facts_to_signals
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import ProcessedEmail

        pe = ProcessedEmail.objects.create(
            user=self.user, gmail_message_id='intent_prop_002',
        )
        ct = ContentType.objects.get_for_model(pe)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=pe.pk,
            source_type='email',
            fact_type='amount',
            structured_value={'value': 42.00},
            confidence=0.7,
            extracted_text='$42.00',
        )

        signal_map = _map_facts_to_signals([fact])
        for date_key, by_type in signal_map.items():
            for signal_type, fact_infos in by_type.items():
                self.assertNotIn('intent_type', fact_infos[0])


# =========================================================================
# 17. Document Dedup Constraint Tests (Phase 6B.5)
# =========================================================================

class DocumentDedupConstraintTests(TestCase):
    """Test DB-level unique constraint for email-sourced Documents."""

    def setUp(self):
        self.user = _create_test_user('test-doc-dedup@example.com')

    def test_db_prevents_duplicate_email_document(self):
        """Creating two Documents with same user+source+source_id raises IntegrityError."""
        from django.db import IntegrityError
        from apps.life.models import Document

        Document.objects.create(
            user=self.user,
            title='Receipt 1',
            source='email',
            source_id='msg_dup_001',
            category='financial',
        )

        with self.assertRaises(IntegrityError):
            Document.objects.create(
                user=self.user,
                title='Receipt 1 duplicate',
                source='email',
                source_id='msg_dup_001',
                category='financial',
            )

    def test_different_source_id_allowed(self):
        """Different source_ids should work fine."""
        from apps.life.models import Document

        Document.objects.create(
            user=self.user,
            title='Receipt 1',
            source='email',
            source_id='msg_001',
            category='financial',
        )
        doc2 = Document.objects.create(
            user=self.user,
            title='Receipt 2',
            source='email',
            source_id='msg_002',
            category='financial',
        )
        self.assertIsNotNone(doc2.pk)

    def test_upload_source_not_constrained(self):
        """Upload-sourced documents don't trigger the email constraint."""
        from apps.life.models import Document

        Document.objects.create(
            user=self.user,
            title='Upload 1',
            source='upload',
            source_id='',
            category='financial',
        )
        doc2 = Document.objects.create(
            user=self.user,
            title='Upload 2',
            source='upload',
            source_id='',
            category='financial',
        )
        self.assertIsNotNone(doc2.pk)

    def test_service_handles_integrity_error(self):
        """_create_receipt_documents handles IntegrityError gracefully."""
        from apps.life.models import Document, ProcessedEmail
        from apps.life.services.email_fact_service import _create_receipt_documents

        # Pre-create a document for the email
        Document.objects.create(
            user=self.user,
            title='Existing Receipt',
            source='email',
            source_id='msg_integrity_001',
            category='financial',
        )

        pe = ProcessedEmail.objects.create(
            user=self.user,
            gmail_message_id='msg_integrity_001',
            received_date=timezone.now(),
        )

        email = _make_email(
            gmail_id='msg_integrity_001',
            subject='Receipt for $50',
            body='Payment confirmed',
        )

        # Should not raise — handles gracefully
        count = _create_receipt_documents(
            self.user, [(email, pe, [])],
        )
        self.assertEqual(count, 0)


# =========================================================================
# 18. Telemetry Visibility Tests (Phase 6B.5)
# =========================================================================

class TelemetryVisibilityTests(TestCase):
    """Test email intelligence telemetry is exposed in ops stream."""

    def test_telemetry_getter_returns_empty_when_no_cache(self):
        from apps.core.ai_observability.ops_telemetry import (
            _get_email_intelligence_telemetry,
        )
        from django.core.cache import cache

        cache.delete('wlj:ops:email_fact_extraction')
        result = _get_email_intelligence_telemetry()
        self.assertEqual(result['scans'], 0)
        self.assertIsNone(result['last_run'])

    def test_telemetry_getter_reads_cached_data(self):
        from apps.core.ai_observability.ops_telemetry import (
            _get_email_intelligence_telemetry,
        )
        from django.core.cache import cache

        data = {
            'scans': 5,
            'emails_classified': 50,
            'emails_kept': 20,
            'emails_skipped': 25,
            'facts_created': 15,
            'signals_affected': 3,
            'transactions_created': 2,
            'documents_created': 1,
            'last_run': '2026-03-17T10:00:00',
        }
        cache.set('wlj:ops:email_fact_extraction', data, timeout=60)

        result = _get_email_intelligence_telemetry()
        self.assertEqual(result['scans'], 5)
        self.assertEqual(result['emails_kept'], 20)
        self.assertEqual(result['documents_created'], 1)
        self.assertEqual(result['last_run'], '2026-03-17T10:00:00')

        cache.delete('wlj:ops:email_fact_extraction')

    def test_telemetry_in_stream_payload(self):
        """email_intelligence key should appear in the ops stream payload."""
        from apps.core.ai_observability.ops_telemetry import build_ops_stream_payload

        payload = build_ops_stream_payload()
        self.assertIn('email_intelligence', payload)
        self.assertIn('scans', payload['email_intelligence'])


# =========================================================================
# 19. Phase 6B.6A — Body Cleaner Footer Fix Tests
# =========================================================================

class BodyCleanerFooterFixTests(TestCase):
    """Validate that footer stripping no longer truncates mid-body content."""

    def test_mid_body_copyright_preserves_subsequent_content(self):
        """Receipt with copyright line mid-body must keep content after it."""
        from apps.life.services.email_body_cleaner import clean_email_body

        body = (
            'Order Confirmation #12345\n'
            'Item: Widget - $29.99\n'
            '© 2026 Amazon Inc.\n'
            'Order Total: $32.39\n'
            'Confirmation Number: ABC-789\n'
        )
        result = clean_email_body(body)
        # Copyright LINE should be removed
        self.assertNotIn('© 2026', result)
        # Content AFTER copyright must survive
        self.assertIn('Order Total: $32.39', result)
        self.assertIn('Confirmation Number: ABC-789', result)
        # Content BEFORE copyright must survive
        self.assertIn('Order Confirmation #12345', result)
        self.assertIn('$29.99', result)

    def test_all_rights_reserved_mid_body_preserves_content(self):
        """'All rights reserved' mid-body must not eat subsequent lines."""
        from apps.life.services.email_body_cleaner import clean_email_body

        body = (
            'Payment Received\n'
            'All rights reserved.\n'
            'Amount: $100.00\n'
            'Reference: XYZ-456\n'
        )
        result = clean_email_body(body)
        self.assertIn('Amount: $100.00', result)
        self.assertIn('Reference: XYZ-456', result)

    def test_true_footer_block_still_removed(self):
        """Traditional footer at end-of-email is still cleaned."""
        from apps.life.services.email_body_cleaner import clean_email_body

        body = (
            'Your payment of $50.00 was received.\n'
            '---\n'
            'Unsubscribe from these notifications\n'
            'Privacy Policy | Terms of Service\n'
            '© 2026 Example Corp. All rights reserved.'
        )
        result = clean_email_body(body)
        self.assertIn('$50.00', result)
        self.assertNotIn('Unsubscribe', result)
        self.assertNotIn('Privacy Policy', result)

    def test_separator_line_does_not_eat_subsequent_content(self):
        """A --- separator mid-body must only remove that line."""
        from apps.life.services.email_body_cleaner import clean_email_body

        body = (
            'Section 1: Items\n'
            '---\n'
            'Section 2: Totals\n'
            'Grand Total: $200.00\n'
        )
        result = clean_email_body(body)
        self.assertIn('Section 1: Items', result)
        # Separator line removed but content after preserved
        self.assertIn('Section 2: Totals', result)
        self.assertIn('Grand Total: $200.00', result)


# =========================================================================
# 20. Phase 6B.6A — Intent Type in CoS Context Tests
# =========================================================================

class IntentInCosContextTests(TestCase):
    """Validate that intent_type reaches CoS context as a list."""

    def setUp(self):
        self.user = _create_test_user('test-intent-cos@example.com')

    def test_single_intent_in_daily_signals(self):
        """Signal with one intent fact should produce intents list."""
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        SignalSnapshot.objects.create(
            user=self.user,
            date=today,
            signal_type='financial_health',
            domain='finance',
            score=0.4,
            signal_class='medium',
            confidence=0.7,
            source_signals={
                'source': 'fact_extraction',
                'facts': [
                    {'intent_type': 'bill_due', 'confidence': 0.7, 'fact_type': 'obligation'},
                ],
            },
        )

        from apps.core.ai_orchestrator.cos_context import _build_signal_aware_context
        result = _build_signal_aware_context(self.user)
        signals = result.get('daily_signals', [])
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]['intents'], ['bill_due'])

    def test_multiple_intents_deduplicated_and_sorted(self):
        """Multiple facts with different intents produce sorted unique list."""
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        SignalSnapshot.objects.create(
            user=self.user,
            date=today,
            signal_type='financial_health',
            domain='finance',
            score=0.5,
            signal_class='medium',
            confidence=0.8,
            source_signals={
                'source': 'fact_extraction',
                'facts': [
                    {'intent_type': 'bill_due', 'confidence': 0.7, 'fact_type': 'obligation'},
                    {'intent_type': 'recurring_obligation', 'confidence': 0.6, 'fact_type': 'subscription'},
                    {'intent_type': 'bill_due', 'confidence': 0.5, 'fact_type': 'obligation'},  # duplicate
                ],
            },
        )

        from apps.core.ai_orchestrator.cos_context import _build_signal_aware_context
        result = _build_signal_aware_context(self.user)
        signals = result.get('daily_signals', [])
        self.assertEqual(len(signals), 1)
        # Deduplicated and sorted
        self.assertEqual(signals[0]['intents'], ['bill_due', 'recurring_obligation'])

    def test_no_intents_key_when_no_intent_types(self):
        """Signal without intent facts should NOT have 'intents' key."""
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        SignalSnapshot.objects.create(
            user=self.user,
            date=today,
            signal_type='journal_consistency',
            domain='journal',
            score=0.8,
            signal_class='high',
            confidence=0.9,
            source_signals={
                'source': 'journal_engine',
                'facts': [
                    {'confidence': 0.9, 'fact_type': 'entry'},
                ],
            },
        )

        from apps.core.ai_orchestrator.cos_context import _build_signal_aware_context
        result = _build_signal_aware_context(self.user)
        signals = result.get('daily_signals', [])
        self.assertEqual(len(signals), 1)
        self.assertNotIn('intents', signals[0])

    def test_empty_source_signals_no_crash(self):
        """Signal with empty/null source_signals should not crash."""
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        SignalSnapshot.objects.create(
            user=self.user,
            date=today,
            signal_type='sleep_quality',
            domain='health',
            score=0.6,
            signal_class='medium',
            confidence=0.7,
            source_signals={},
        )

        from apps.core.ai_orchestrator.cos_context import _build_signal_aware_context
        result = _build_signal_aware_context(self.user)
        signals = result.get('daily_signals', [])
        self.assertEqual(len(signals), 1)
        self.assertNotIn('intents', signals[0])


# =========================================================================
# 21. Phase 6C — Signal Interpreter Tests
# =========================================================================

class SignalInterpreterTests(TestCase):
    """Test interpret_signals() deterministic semantic normalization."""

    def test_bill_due_produces_semantic_entry(self):
        """bill_due intent produces correct meaning_code and semantic_class."""
        from apps.core.ai_orchestrator.signal_interpreter import interpret_signals

        signals = [{
            'signal_type': 'financial_health',
            'domain': 'finance',
            'score': 0.4,
            'confidence': 0.7,
            'intents': ['bill_due'],
        }]
        result = interpret_signals(signals)
        self.assertIn('interpreted_signals', result)
        self.assertEqual(len(result['interpreted_signals']), 1)

        entry = result['interpreted_signals'][0]
        self.assertEqual(entry['intent'], 'bill_due')
        self.assertEqual(entry['semantic_class'], 'financial_obligation')
        self.assertEqual(entry['meaning_code'], 'upcoming_financial_obligation')
        self.assertEqual(entry['priority_hint'], 'time_sensitive')
        self.assertEqual(entry['domain'], 'finance')
        self.assertEqual(entry['confidence'], 0.7)
        self.assertEqual(entry['source_refs'], ['financial_health'])

    def test_multiple_intents_across_signals(self):
        """Multiple signals with different intents produce all entries."""
        from apps.core.ai_orchestrator.signal_interpreter import interpret_signals

        signals = [
            {
                'signal_type': 'financial_health',
                'domain': 'finance',
                'score': 0.4,
                'confidence': 0.7,
                'intents': ['bill_due'],
            },
            {
                'signal_type': 'schedule_load',
                'domain': 'life',
                'score': 0.6,
                'confidence': 0.8,
                'intents': ['schedule_commitment'],
            },
        ]
        result = interpret_signals(signals)
        entries = result['interpreted_signals']
        self.assertEqual(len(entries), 2)
        meaning_codes = {e['meaning_code'] for e in entries}
        self.assertEqual(meaning_codes, {
            'upcoming_financial_obligation',
            'upcoming_schedule_block',
        })

    def test_no_intents_returns_empty(self):
        """Signals without intents produce empty dict."""
        from apps.core.ai_orchestrator.signal_interpreter import interpret_signals

        signals = [
            {'signal_type': 'sleep_quality', 'domain': 'health', 'score': 0.8, 'confidence': 0.9},
        ]
        result = interpret_signals(signals)
        self.assertEqual(result, {})

    def test_empty_signals_returns_empty(self):
        """Empty input returns empty dict."""
        from apps.core.ai_orchestrator.signal_interpreter import interpret_signals

        self.assertEqual(interpret_signals([]), {})
        self.assertEqual(interpret_signals(None), {})

    def test_duplicate_intents_deduplicated(self):
        """Same intent in multiple signals produces only one entry."""
        from apps.core.ai_orchestrator.signal_interpreter import interpret_signals

        signals = [
            {'signal_type': 'financial_health', 'domain': 'finance', 'confidence': 0.7, 'intents': ['bill_due']},
            {'signal_type': 'financial_stress', 'domain': 'finance', 'confidence': 0.6, 'intents': ['bill_due']},
        ]
        result = interpret_signals(signals)
        self.assertEqual(len(result['interpreted_signals']), 1)

    def test_unknown_intent_ignored(self):
        """Unrecognized intent values are silently skipped."""
        from apps.core.ai_orchestrator.signal_interpreter import interpret_signals

        signals = [
            {'signal_type': 'financial_health', 'domain': 'finance', 'confidence': 0.7, 'intents': ['unknown_type']},
        ]
        result = interpret_signals(signals)
        self.assertEqual(result, {})

    def test_no_natural_language_in_output(self):
        """Output must contain only machine-readable codes, no sentences."""
        from apps.core.ai_orchestrator.signal_interpreter import interpret_signals

        signals = [
            {'signal_type': 'financial_health', 'domain': 'finance', 'confidence': 0.7, 'intents': ['bill_due']},
        ]
        result = interpret_signals(signals)
        entry = result['interpreted_signals'][0]
        # No freeform text fields — only structured codes
        for key in ('semantic_class', 'meaning_code', 'priority_hint'):
            value = entry[key]
            self.assertFalse(
                value != value.replace(' ', '').replace('_', ' ').replace(' ', '_'),
                f"{key} contains unexpected spaces: {value}",
            )
        # No 'text', 'insight', 'label', or 'description' keys
        for forbidden_key in ('text', 'insight', 'label', 'description', 'message'):
            self.assertNotIn(forbidden_key, entry)

    def test_output_contract_structure(self):
        """Verify exact output contract fields per the spec."""
        from apps.core.ai_orchestrator.signal_interpreter import interpret_signals

        signals = [{
            'signal_type': 'financial_health',
            'domain': 'finance',
            'score': 0.4,
            'confidence': 0.7,
            'intents': ['recurring_obligation'],
        }]
        result = interpret_signals(signals)
        entry = result['interpreted_signals'][0]
        required_keys = {
            'signal_type', 'domain', 'intent', 'semantic_class',
            'meaning_code', 'priority_hint', 'confidence', 'source_refs',
        }
        self.assertEqual(set(entry.keys()), required_keys)


class SignalInterpreterIntegrationTests(TestCase):
    """Test interpreter wired into _build_signal_aware_context."""

    def setUp(self):
        self.user = _create_test_user('test-interp-integration@example.com')

    def test_interpretation_in_context(self):
        """Signal with intent produces signal_interpretation in context."""
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        SignalSnapshot.objects.create(
            user=self.user,
            date=today,
            signal_type='financial_health',
            domain='finance',
            score=0.4,
            signal_class='medium',
            confidence=0.7,
            source_signals={
                'source': 'fact_extraction',
                'facts': [
                    {'intent_type': 'bill_due', 'confidence': 0.7, 'fact_type': 'obligation'},
                ],
            },
        )

        from apps.core.ai_orchestrator.cos_context import _build_signal_aware_context
        result = _build_signal_aware_context(self.user)
        self.assertIn('signal_interpretation', result)
        interp = result['signal_interpretation']
        self.assertEqual(len(interp['interpreted_signals']), 1)
        self.assertEqual(interp['interpreted_signals'][0]['meaning_code'], 'upcoming_financial_obligation')

    def test_no_interpretation_when_no_intents(self):
        """Context without intents should not include signal_interpretation."""
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        SignalSnapshot.objects.create(
            user=self.user,
            date=today,
            signal_type='sleep_quality',
            domain='health',
            score=0.8,
            signal_class='high',
            confidence=0.9,
            source_signals={},
        )

        from apps.core.ai_orchestrator.cos_context import _build_signal_aware_context
        result = _build_signal_aware_context(self.user)
        self.assertNotIn('signal_interpretation', result)
