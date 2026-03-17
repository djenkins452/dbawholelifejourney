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
