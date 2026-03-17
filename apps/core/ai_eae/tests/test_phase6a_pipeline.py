# ==============================================================================
# File: apps/core/ai_eae/tests/test_phase6a_pipeline.py
# Description: Phase 6A — Knowledge Intelligence Pipeline tests
# Created: 2026-03-17
# ==============================================================================
"""
Tests for Phase 6A: Document Intelligence + Extracted Fact Layer

Test classes:
1. ContentExtractorTests — PDF/OCR extraction routing
2. ExtractedFactModelTests — Model creation + validation
3. FactExtractionTests — LLM fact extraction + deterministic validation
4. FactSignalMappingTests — Deterministic fact → signal mapping
5. RecomputeIntegrationTests — Targeted recompute after fact creation
6. TransactionCreationTests — Financial fact → Transaction
7. DocumentPipelineTests — Full async pipeline integration
8. IdempotencyTests — Duplicate prevention
"""

import io
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.users.models import User


def _create_test_user(email='test-phase6a@example.com'):
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


# =========================================================================
# 1. Content Extractor Tests
# =========================================================================

class ContentExtractorTests(TestCase):
    """Test shared content extractor routing and quality estimation."""

    def test_empty_result_when_no_file(self):
        from apps.core.extraction.content_extractor import extract_document_content
        doc = MagicMock()
        doc.file = None
        result = extract_document_content(doc)
        self.assertFalse(result['has_text'])
        self.assertEqual(result['error'], 'No file attached')

    def test_unsupported_file_type(self):
        from apps.core.extraction.content_extractor import extract_document_content
        doc = MagicMock()
        doc.file_type = 'word'
        doc.file = MagicMock()
        doc.file.open = MagicMock()
        doc.file.read = MagicMock(return_value=b'test content')
        doc.file.close = MagicMock()
        doc.pk = 1

        result = extract_document_content(doc)
        self.assertFalse(result['has_text'])
        self.assertIn('Unsupported file type', result['error'])
        self.assertTrue(result['content_hash'])  # Hash still computed

    def test_quality_estimation_text_method(self):
        from apps.core.extraction.content_extractor import _estimate_quality
        result = {'has_text': True, 'text': ' '.join(['word'] * 100), 'method': 'text'}
        quality = _estimate_quality(result)
        self.assertEqual(quality, 0.9)  # text method, 100 words

    def test_quality_estimation_ocr_method(self):
        from apps.core.extraction.content_extractor import _estimate_quality
        result = {'has_text': True, 'text': ' '.join(['word'] * 100), 'method': 'ocr'}
        quality = _estimate_quality(result)
        self.assertEqual(quality, 0.6)  # OCR lower quality

    def test_quality_zero_when_no_text(self):
        from apps.core.extraction.content_extractor import _estimate_quality
        result = {'has_text': False, 'text': '', 'method': 'text'}
        self.assertEqual(_estimate_quality(result), 0.0)


# =========================================================================
# 2. ExtractedFact Model Tests
# =========================================================================

class ExtractedFactModelTests(TestCase):
    """Test ExtractedFact model creation and constraints."""

    def setUp(self):
        self.user = _create_test_user('fact-model@example.com')

    def test_create_amount_fact(self):
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import Document

        doc = Document.objects.create(
            user=self.user,
            title='Test Receipt',
            category='financial',
            file=SimpleUploadedFile('test.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )
        ct = ContentType.objects.get_for_model(doc)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=doc.pk,
            source_type='document',
            fact_type='amount',
            structured_value={'value': 42.99, 'currency': 'USD', 'merchant': 'Walmart'},
            confidence=0.7,
            extracted_text='Total: $42.99',
            effective_date=date.today(),
            domain_hint='finance',
        )
        self.assertEqual(fact.fact_type, 'amount')
        self.assertEqual(fact.structured_value['value'], 42.99)
        self.assertEqual(fact.source_type, 'document')

    def test_generic_fk_resolves(self):
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import Document

        doc = Document.objects.create(
            user=self.user,
            title='Test Doc',
            category='other',
            file=SimpleUploadedFile('test.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )
        ct = ContentType.objects.get_for_model(doc)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=doc.pk,
            source_type='document',
            fact_type='person',
            structured_value={'name': 'Dr. Smith', 'role': 'physician'},
            confidence=0.65,
            extracted_text='Dr. Smith',
        )
        # Verify GenericForeignKey resolves
        self.assertEqual(fact.source, doc)


# =========================================================================
# 3. Fact Extraction Validation Tests
# =========================================================================

class FactExtractionTests(TestCase):
    """Test LLM candidate validation in DocumentFactExtractor."""

    def setUp(self):
        self.user = _create_test_user('fact-extract@example.com')

    def test_rejects_invalid_fact_type(self):
        from apps.life.services.document_fact_extractor import _validate_and_create
        from apps.life.models import Document

        doc = Document.objects.create(
            user=self.user, title='Test', category='other',
            file=SimpleUploadedFile('t.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )
        result = _validate_and_create(doc, {
            'fact_type': 'invented_type',
            'confidence': 0.9,
            'extracted_text': 'something',
            'structured_value': {'value': 1},
        })
        self.assertIsNone(result)

    def test_rejects_low_confidence(self):
        from apps.life.services.document_fact_extractor import _validate_and_create
        from apps.life.models import Document

        doc = Document.objects.create(
            user=self.user, title='Test', category='other',
            file=SimpleUploadedFile('t.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )
        result = _validate_and_create(doc, {
            'fact_type': 'amount',
            'confidence': 0.3,  # Below 0.6 threshold
            'extracted_text': '$10.00',
            'structured_value': {'value': 10.0},
        })
        self.assertIsNone(result)

    def test_rejects_empty_extracted_text(self):
        from apps.life.services.document_fact_extractor import _validate_and_create
        from apps.life.models import Document

        doc = Document.objects.create(
            user=self.user, title='Test', category='other',
            file=SimpleUploadedFile('t.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )
        result = _validate_and_create(doc, {
            'fact_type': 'amount',
            'confidence': 0.9,
            'extracted_text': '',
            'structured_value': {'value': 10.0},
        })
        self.assertIsNone(result)

    def test_accepts_valid_amount_fact(self):
        from apps.life.services.document_fact_extractor import _validate_and_create
        from apps.life.models import Document

        doc = Document.objects.create(
            user=self.user, title='Receipt', category='financial',
            file=SimpleUploadedFile('t.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )
        result = _validate_and_create(doc, {
            'fact_type': 'amount',
            'confidence': 0.9,
            'extracted_text': 'Total: $42.99',
            'structured_value': {'value': 42.99, 'currency': 'USD', 'merchant': 'Target'},
            'effective_date': '2026-03-15',
            'domain_hint': 'finance',
        })
        self.assertIsNotNone(result)
        self.assertEqual(result.fact_type, 'amount')
        # Confidence = 0.9 * 0.7 (source weight) = 0.63
        self.assertAlmostEqual(result.confidence, 0.63, places=2)
        self.assertEqual(result.effective_date, date(2026, 3, 15))

    def test_accepts_valid_medication_fact(self):
        from apps.life.services.document_fact_extractor import _validate_and_create
        from apps.life.models import Document

        doc = Document.objects.create(
            user=self.user, title='Prescription', category='medical',
            file=SimpleUploadedFile('t.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )
        result = _validate_and_create(doc, {
            'fact_type': 'medication',
            'confidence': 0.85,
            'extracted_text': 'Metformin 500mg twice daily',
            'structured_value': {
                'name': 'Metformin',
                'dosage': '500mg',
                'frequency': 'twice daily',
            },
            'domain_hint': 'health',
        })
        self.assertIsNotNone(result)
        self.assertEqual(result.structured_value['name'], 'Metformin')

    def test_rejects_medication_without_name(self):
        from apps.life.services.document_fact_extractor import _validate_and_create
        from apps.life.models import Document

        doc = Document.objects.create(
            user=self.user, title='Test', category='medical',
            file=SimpleUploadedFile('t.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )
        result = _validate_and_create(doc, {
            'fact_type': 'medication',
            'confidence': 0.9,
            'extracted_text': 'take medicine',
            'structured_value': {'name': '', 'dosage': ''},
        })
        self.assertIsNone(result)

    def test_confidence_applies_source_weight(self):
        """Verify confidence = LLM_confidence × DOCUMENT_SOURCE_WEIGHT (0.7)."""
        from apps.life.services.document_fact_extractor import (
            _validate_and_create,
            DOCUMENT_SOURCE_WEIGHT,
        )
        from apps.life.models import Document

        doc = Document.objects.create(
            user=self.user, title='Test', category='other',
            file=SimpleUploadedFile('t.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )
        result = _validate_and_create(doc, {
            'fact_type': 'appointment',
            'confidence': 1.0,
            'extracted_text': 'Dr appointment March 20',
            'structured_value': {'provider': 'Dr Smith', 'datetime': '2026-03-20'},
        })
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.confidence, DOCUMENT_SOURCE_WEIGHT, places=2)


# =========================================================================
# 4. Fact → Signal Mapping Tests
# =========================================================================

class FactSignalMappingTests(TestCase):
    """Test deterministic fact-to-signal mapping rules."""

    def setUp(self):
        self.user = _create_test_user('fact-signal@example.com')

    def test_amount_maps_to_financial_health(self):
        from apps.core.ai_eae.fact_signal_mapper import _get_signal_for_fact
        fact = MagicMock(fact_type='amount', domain_hint='finance')
        result = _get_signal_for_fact(fact)
        self.assertEqual(result, ('financial_health', 'finance', 'positive'))

    def test_obligation_maps_to_financial_health_negative(self):
        from apps.core.ai_eae.fact_signal_mapper import _get_signal_for_fact
        fact = MagicMock(fact_type='obligation', domain_hint='finance')
        result = _get_signal_for_fact(fact)
        self.assertEqual(result, ('financial_health', 'finance', 'negative'))

    def test_appointment_maps_to_health_activity(self):
        from apps.core.ai_eae.fact_signal_mapper import _get_signal_for_fact
        fact = MagicMock(fact_type='appointment', domain_hint='health')
        result = _get_signal_for_fact(fact)
        self.assertEqual(result, ('health_activity', 'health', 'positive'))

    def test_medication_maps_to_adherence(self):
        from apps.core.ai_eae.fact_signal_mapper import _get_signal_for_fact
        fact = MagicMock(fact_type='medication', domain_hint='health')
        result = _get_signal_for_fact(fact)
        self.assertEqual(result, ('medication_adherence', 'health', 'positive'))

    def test_person_with_health_hint_maps(self):
        from apps.core.ai_eae.fact_signal_mapper import _get_signal_for_fact
        fact = MagicMock(fact_type='person', domain_hint='health')
        result = _get_signal_for_fact(fact)
        self.assertEqual(result, ('health_activity', 'health', 'positive'))

    def test_person_without_valid_hint_returns_none(self):
        from apps.core.ai_eae.fact_signal_mapper import _get_signal_for_fact
        fact = MagicMock(fact_type='person', domain_hint='')
        result = _get_signal_for_fact(fact)
        self.assertIsNone(result)


# =========================================================================
# 5. Recompute Integration Tests
# =========================================================================

class RecomputeIntegrationTests(TestCase):
    """Test targeted recompute after fact creation."""

    def setUp(self):
        self.user = _create_test_user('recompute-6a@example.com')

    def test_fact_creates_inferred_signal(self):
        """A fact with no existing snapshot creates an inferred_behavior signal."""
        from apps.core.ai_eae.fact_signal_mapper import _blend_fact_signals
        from apps.core.ai_eae.models import SignalSnapshot

        today = date.today()
        signals_by_type = {
            'financial_health': [{
                'confidence': 0.5,
                'direction': 'positive',
                'fact_type': 'amount',
                'fact_id': 1,
                'text': 'receipt total $42.99',
            }],
        }

        affected = _blend_fact_signals(self.user, today, signals_by_type)
        self.assertIn('financial_health', affected)

        snapshot = SignalSnapshot.objects.get(
            user=self.user, date=today, signal_type='financial_health',
        )
        self.assertEqual(snapshot.signal_class, 'inferred_behavior')
        self.assertIn('fact_extraction', snapshot.source_signals.get('source', ''))

    def test_verified_signal_not_overridden(self):
        """Facts never override verified signals."""
        from apps.core.ai_eae.fact_signal_mapper import _blend_fact_signals
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.ai_eae.signal_aggregation import SignalAggregationService

        today = date.today()

        # Create verified signal first
        SignalAggregationService._upsert_snapshot(
            self.user, today, 'health_activity',
            score=0.8, confidence=1.0,
            signal_class='verified_action',
            source_signals={'workout': True},
        )

        # Now blend a fact signal
        signals_by_type = {
            'health_activity': [{
                'confidence': 0.7,
                'direction': 'positive',
                'fact_type': 'appointment',
                'fact_id': 2,
                'text': 'doctor appointment',
            }],
        }

        _blend_fact_signals(self.user, today, signals_by_type)

        snapshot = SignalSnapshot.objects.get(
            user=self.user, date=today, signal_type='health_activity',
        )
        # Score unchanged — verified not overridden
        self.assertAlmostEqual(snapshot.score, 0.8)
        self.assertEqual(snapshot.signal_class, 'verified_action')
        # But fact was annotated
        self.assertIn('fact_inferred', snapshot.source_signals)


# =========================================================================
# 6. Transaction Creation Tests
# =========================================================================

class TransactionCreationTests(TestCase):
    """Test financial fact → Transaction creation."""

    def setUp(self):
        self.user = _create_test_user('tx-create@example.com')

    def test_creates_transaction_from_financial_fact(self):
        from apps.core.ai_eae.fact_signal_mapper import _create_transactions
        from apps.core.ai_eae.models import ExtractedFact
        from apps.finance.models import FinancialAccount, Transaction
        from apps.life.models import Document

        # Create account
        account = FinancialAccount.objects.create(
            user=self.user,
            name='Checking',
            account_type='checking',
            current_balance=1000,
        )

        doc = Document.objects.create(
            user=self.user, title='Electric Bill', category='financial',
            file=SimpleUploadedFile('bill.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )
        ct = ContentType.objects.get_for_model(doc)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=doc.pk,
            source_type='document',
            fact_type='obligation',
            structured_value={
                'description': 'Electric bill',
                'amount': 150.00,
                'due_date': '2026-03-25',
            },
            confidence=0.7,
            extracted_text='Amount due: $150.00',
            effective_date=date(2026, 3, 25),
            domain_hint='finance',
        )

        created = _create_transactions(self.user, [fact], doc)
        self.assertEqual(created, 1)

        tx = Transaction.objects.get(user=self.user, source_type='document')
        self.assertEqual(tx.amount, -150.00)  # Obligation = negative
        self.assertEqual(tx.source_id, str(doc.pk))

    def test_no_transaction_for_non_financial_category(self):
        from apps.core.ai_eae.fact_signal_mapper import _create_transactions
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import Document

        doc = Document.objects.create(
            user=self.user, title='Medical Record', category='medical',
            file=SimpleUploadedFile('record.pdf', b'%PDF-1.4', content_type='application/pdf'),
        )
        ct = ContentType.objects.get_for_model(doc)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=doc.pk,
            source_type='document',
            fact_type='amount',
            structured_value={'value': 50.0, 'merchant': 'Lab'},
            confidence=0.7,
            extracted_text='$50.00',
        )

        created = _create_transactions(self.user, [fact], doc)
        self.assertEqual(created, 0)  # medical category doesn't create transactions

    def test_no_duplicate_transaction(self):
        """Transaction is not created twice for the same document."""
        from apps.core.ai_eae.fact_signal_mapper import _create_single_transaction
        from apps.core.ai_eae.models import ExtractedFact
        from apps.finance.models import FinancialAccount, Transaction
        from apps.life.models import Document

        account = FinancialAccount.objects.create(
            user=self.user, name='Checking', account_type='checking',
            current_balance=1000,
        )

        doc = Document.objects.create(
            user=self.user, title='Bill', category='financial',
            file=SimpleUploadedFile('b.pdf', b'%PDF-1.4', content_type='application/pdf'),
        )
        ct = ContentType.objects.get_for_model(doc)

        fact = ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=doc.pk,
            source_type='document',
            fact_type='amount',
            structured_value={'value': 100.0},
            confidence=0.7,
            extracted_text='$100',
        )

        # First call creates
        tx1 = _create_single_transaction(self.user, fact, doc)
        self.assertIsNotNone(tx1)

        # Second call returns None (dedup)
        tx2 = _create_single_transaction(self.user, fact, doc)
        self.assertIsNone(tx2)


# =========================================================================
# 7. Document Pipeline Integration Tests
# =========================================================================

class DocumentPipelineTests(TestCase):
    """Test the full document pipeline integration."""

    def setUp(self):
        self.user = _create_test_user('pipeline-6a@example.com')

    @patch('apps.core.extraction.content_extractor.extract_document_content')
    def test_extraction_task_stores_raw_text(self, mock_extract):
        """Content extraction task stores raw_text on Document."""
        from apps.life.models import Document
        from apps.life.tasks.document_extraction import extract_document_content_task

        doc = Document.objects.create(
            user=self.user, title='Test PDF', category='medical',
            file=SimpleUploadedFile('test.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )

        mock_extract.return_value = {
            'text': 'Patient: John Doe. Diagnosis: Hypertension. Medication: Lisinopril 10mg daily.',
            'method': 'text',
            'page_count': 1,
            'has_text': True,
            'quality': 0.9,
            'content_hash': 'abc123',
            'error': None,
        }

        with patch('apps.life.tasks.document_extraction.extract_document_facts_task') as mock_facts:
            mock_facts.delay = MagicMock()
            result = extract_document_content_task(doc.pk)

        self.assertTrue(result['success'])
        doc.refresh_from_db()
        self.assertEqual(doc.extraction_status, 'completed')
        self.assertIn('Hypertension', doc.raw_text)
        self.assertEqual(doc.content_hash, 'abc123')
        self.assertAlmostEqual(doc.extraction_quality, 0.9)

    def test_extraction_task_skips_already_extracted(self):
        from apps.life.models import Document
        from apps.life.tasks.document_extraction import extract_document_content_task

        doc = Document.objects.create(
            user=self.user, title='Already Done', category='other',
            file=SimpleUploadedFile('t.pdf', b'%PDF-1.4', content_type='application/pdf'),
            extraction_status='completed',
            content_hash='existing_hash',
        )

        result = extract_document_content_task(doc.pk)
        self.assertTrue(result.get('skipped'))

    def test_extraction_task_skips_non_extractable(self):
        from apps.life.models import Document
        from apps.life.tasks.document_extraction import extract_document_content_task

        doc = Document.objects.create(
            user=self.user, title='Spreadsheet', category='other',
            file=SimpleUploadedFile('test.xlsx', b'PK...', content_type='application/xlsx'),
        )
        # Force non-applicable status
        doc.extraction_status = 'not_applicable'
        doc.save(update_fields=['extraction_status'])

        result = extract_document_content_task(doc.pk)
        self.assertTrue(result.get('skipped'))


# =========================================================================
# 8. Idempotency Tests
# =========================================================================

class IdempotencyTests(TestCase):
    """Test duplicate prevention across the pipeline."""

    def setUp(self):
        self.user = _create_test_user('idempotent-6a@example.com')

    def test_fact_extraction_idempotent(self):
        """DocumentFactExtractor.extract_facts() skips if facts already exist."""
        from apps.core.ai_eae.models import ExtractedFact
        from apps.life.models import Document
        from apps.life.services.document_fact_extractor import DocumentFactExtractor

        doc = Document.objects.create(
            user=self.user, title='Test', category='financial',
            file=SimpleUploadedFile('t.pdf', b'%PDF-1.4', content_type='application/pdf'),
            raw_text='This is a test document with enough text to be processed. ' * 5,
        )

        # Pre-create a fact
        ct = ContentType.objects.get_for_model(doc)
        ExtractedFact.objects.create(
            user=self.user,
            source_content_type=ct,
            source_object_id=doc.pk,
            source_type='document',
            fact_type='amount',
            structured_value={'value': 10.0},
            confidence=0.7,
            extracted_text='$10',
        )

        # Extraction should skip (idempotency gate)
        facts = DocumentFactExtractor.extract_facts(doc)
        self.assertEqual(len(facts), 0)

    def test_content_hash_prevents_reextraction(self):
        """Same content_hash skips re-extraction."""
        from apps.life.models import Document
        from apps.life.tasks.document_extraction import extract_document_content_task

        doc = Document.objects.create(
            user=self.user, title='Test', category='other',
            file=SimpleUploadedFile('t.pdf', b'%PDF-1.4', content_type='application/pdf'),
            extraction_status='completed',
            content_hash='same_hash',
            raw_text='existing text',
        )

        result = extract_document_content_task(doc.pk)
        self.assertTrue(result.get('skipped'))


# =========================================================================
# Document Model Field Tests
# =========================================================================

class DocumentModelTests(TestCase):
    """Test Phase 6A Document model extensions."""

    def setUp(self):
        self.user = _create_test_user('doc-model-6a@example.com')

    def test_new_fields_have_defaults(self):
        from apps.life.models import Document
        doc = Document.objects.create(
            user=self.user, title='Test', category='other',
            file=SimpleUploadedFile('t.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )
        self.assertEqual(doc.raw_text, '')
        self.assertEqual(doc.extraction_status, 'pending')
        self.assertIsNone(doc.extraction_quality)
        self.assertIsNone(doc.extracted_at)
        self.assertEqual(doc.content_hash, '')

    def test_word_doc_sets_not_applicable(self):
        from apps.life.models import Document
        doc = Document.objects.create(
            user=self.user, title='Test', category='other',
            file=SimpleUploadedFile('test.docx', b'PK test', content_type='application/docx'),
        )
        self.assertEqual(doc.extraction_status, 'not_applicable')

    def test_pdf_stays_pending(self):
        from apps.life.models import Document
        doc = Document.objects.create(
            user=self.user, title='Test', category='other',
            file=SimpleUploadedFile('test.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )
        self.assertEqual(doc.extraction_status, 'pending')
