# ==============================================================================
# File: apps/core/ai_eae/tests/test_extraction_layer.py
# Description: Phase 5.5 — Tests for Capture/Document Extraction Layer
# Created: 2026-03-16
# ==============================================================================
"""
Tests for the Phase 5.5 extraction layer:
1. LLM output never writes signals directly
2. Validation layer filters correctly
3. Negative behavior mapping works
4. Confidence hierarchy enforced
5. Targeted recompute updates only affected signals
6. Patterns triggered after recompute
7. Source attribution present
"""

from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.test import TestCase
from django.utils import timezone


class ExtractionTestMixin:
    """Common setup for extraction tests."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.users.models import TermsAcceptance

        User = get_user_model()
        self.user = User.objects.create_user(
            email="extracttest@example.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.ai_enabled = True
        self.user.preferences.personal_assistant_enabled = True
        self.user.preferences.save()
        self.today = timezone.now().date()


class CaptureValidationTests(ExtractionTestMixin, TestCase):
    """Test the deterministic validation layer for capture extraction."""

    def _create_capture_entry(self, transcript="", summary=""):
        from apps.capture.models import CaptureEntry
        return CaptureEntry.objects.create(
            user=self.user,
            title="Test capture",
            transcript=transcript,
            summary=summary,
            status=CaptureEntry.STATUS_READY,
            duration_seconds=60,
            audio_file_url="https://example.com/audio.webm",
        )

    def test_validation_rejects_invalid_signal_type(self):
        """LLM output with invalid signal_type is discarded."""
        from apps.capture.services.signal_extractor import CaptureSignalExtractor

        entry = self._create_capture_entry("I went for a long run today")
        raw = {
            'signal_type': 'invalid_type',
            'confidence': 0.9,
            'extracted_text': 'went for a long run',
            'direction': 'positive',
            'extractor_type': 'health_behavior',
        }
        result = CaptureSignalExtractor._validate_and_create(entry, raw)
        self.assertIsNone(result)

    def test_validation_rejects_low_confidence(self):
        """Candidates below 0.6 threshold are discarded."""
        from apps.capture.services.signal_extractor import CaptureSignalExtractor

        entry = self._create_capture_entry("I went for a run")
        raw = {
            'signal_type': 'health_activity',
            'confidence': 0.5,
            'extracted_text': 'went for a run',
            'direction': 'positive',
            'extractor_type': 'health_behavior',
        }
        result = CaptureSignalExtractor._validate_and_create(entry, raw)
        self.assertIsNone(result)

    def test_validation_rejects_empty_text(self):
        """Candidates with no extracted_text are discarded."""
        from apps.capture.services.signal_extractor import CaptureSignalExtractor

        entry = self._create_capture_entry("test")
        raw = {
            'signal_type': 'health_activity',
            'confidence': 0.9,
            'extracted_text': '',
            'direction': 'positive',
            'extractor_type': 'health_behavior',
        }
        result = CaptureSignalExtractor._validate_and_create(entry, raw)
        self.assertIsNone(result)

    def test_validation_accepts_valid_candidate(self):
        """Valid candidates create CaptureSignal records."""
        from apps.capture.services.signal_extractor import CaptureSignalExtractor

        entry = self._create_capture_entry("I went for a run today")
        raw = {
            'signal_type': 'health_activity',
            'confidence': 0.85,
            'extracted_text': 'went for a run today',
            'direction': 'positive',
            'extractor_type': 'health_behavior',
        }
        result = CaptureSignalExtractor._validate_and_create(entry, raw)
        self.assertIsNotNone(result)
        self.assertEqual(result.signal_type, 'health_activity')
        self.assertEqual(result.domain, 'health')  # Deterministic mapping
        self.assertEqual(result.direction, 'positive')

    def test_validation_uses_deterministic_domain(self):
        """Domain is set by SIGNAL_TYPE_DOMAIN, not LLM output."""
        from apps.capture.services.signal_extractor import CaptureSignalExtractor

        entry = self._create_capture_entry("I prayed this morning")
        raw = {
            'signal_type': 'faith_practice',
            'confidence': 0.9,
            'extracted_text': 'prayed this morning',
            'direction': 'positive',
            'extractor_type': 'spiritual_faith',
            'domain': 'wrong_domain',  # LLM might put anything here
        }
        result = CaptureSignalExtractor._validate_and_create(entry, raw)
        self.assertIsNotNone(result)
        self.assertEqual(result.domain, 'faith')  # Deterministic, not LLM's

    def test_negative_behavior_accepted(self):
        """Negative behaviors are properly recorded."""
        from apps.capture.services.signal_extractor import CaptureSignalExtractor

        entry = self._create_capture_entry("I skipped my workout")
        raw = {
            'signal_type': 'health_activity',
            'confidence': 0.8,
            'extracted_text': 'skipped my workout',
            'direction': 'negative',
            'extractor_type': 'health_behavior',
        }
        result = CaptureSignalExtractor._validate_and_create(entry, raw)
        self.assertIsNotNone(result)
        self.assertEqual(result.direction, 'negative')

    def test_idempotency_gate(self):
        """Second extraction on same entry is skipped."""
        from apps.capture.models import CaptureSignal
        from apps.capture.services.signal_extractor import CaptureSignalExtractor

        entry = self._create_capture_entry("I went for a run today")
        CaptureSignal.objects.create(
            entry=entry, signal_type='health_activity', domain='health',
            confidence=0.8, extracted_text='test', extractor_type='test',
        )

        with patch.object(CaptureSignalExtractor, '_call_openai') as mock_llm:
            result = CaptureSignalExtractor.extract_signals(entry)
            mock_llm.assert_not_called()
            self.assertEqual(result, [])

    def test_llm_never_writes_signals_directly(self):
        """LLM output goes through validation — never direct to SignalSnapshot."""
        from apps.core.ai_eae.models import SignalSnapshot

        entry = self._create_capture_entry(
            "I went for a long run this morning and it felt great. "
            "The weather was perfect and I ran about three miles along the river trail."
        )
        mock_response = [
            {
                'signal_type': 'health_activity',
                'confidence': 0.9,
                'extracted_text': 'went for a long run',
                'direction': 'positive',
                'extractor_type': 'health_behavior',
            }
        ]

        with patch(
            'apps.capture.services.signal_extractor.CaptureSignalExtractor._call_openai',
            return_value=mock_response,
        ):
            from apps.capture.services.signal_extractor import CaptureSignalExtractor
            signals = CaptureSignalExtractor.extract_signals(entry)

        # CaptureSignal records created (intermediate)
        self.assertEqual(len(signals), 1)
        # But NO SignalSnapshot created (that's the blend step)
        snap_count = SignalSnapshot.objects.filter(
            user=self.user, signal_type='health_activity',
        ).count()
        self.assertEqual(snap_count, 0)


class DocumentExtractionTests(ExtractionTestMixin, TestCase):
    """Test document signal extraction (hybrid rule + conditional LLM).

    Note: Document post_save signal fires on create and extracts signals
    automatically. Tests that call the extractor directly must account
    for the idempotency gate (signals already created by post_save).
    """

    def _create_document(self, category='other', title='Test', description='', notes=''):
        """Create a document. Post_save signal will auto-extract signals."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.life.models import Document
        fake_file = SimpleUploadedFile("test.pdf", b"fake-pdf-content", content_type="application/pdf")
        return Document.objects.create(
            user=self.user,
            title=title,
            category=category,
            description=description,
            notes=notes,
            file=fake_file,
        )

    def test_category_rule_medical(self):
        """Medical category documents produce health_activity signal via post_save."""
        from apps.life.models import DocumentSignal

        doc = self._create_document(category='medical')
        # Post_save signal should have created the signal
        signals = DocumentSignal.objects.filter(document=doc)
        self.assertTrue(signals.filter(signal_type='health_activity').exists())

    def test_category_rule_education(self):
        """Education category produces cognitive_fitness signal."""
        from apps.life.models import DocumentSignal

        doc = self._create_document(category='education')
        signals = DocumentSignal.objects.filter(document=doc)
        self.assertTrue(signals.filter(signal_type='cognitive_fitness').exists())

    def test_keyword_detection_prescription(self):
        """Prescription keyword in notes produces medication_adherence signal."""
        from apps.life.models import DocumentSignal

        doc = self._create_document(
            category='other',
            notes='Prescription refill for blood pressure medication',
        )
        signals = DocumentSignal.objects.filter(document=doc)
        self.assertTrue(signals.filter(signal_type='medication_adherence').exists())

    def test_no_signal_for_generic_document(self):
        """Generic document with no relevant metadata produces no signals."""
        from apps.life.models import DocumentSignal

        doc = self._create_document(category='other', title='Random file')
        signals = DocumentSignal.objects.filter(document=doc)
        self.assertEqual(signals.count(), 0)

    def test_idempotency(self):
        """Second call to extract_signals is skipped (signals already created by post_save)."""
        from apps.life.models import DocumentSignal
        from apps.life.services.document_signal_extractor import DocumentSignalExtractor

        doc = self._create_document(category='medical')
        count_after_save = DocumentSignal.objects.filter(document=doc).count()
        # Direct call should return empty (idempotency gate)
        signals = DocumentSignalExtractor.extract_signals(doc)
        self.assertEqual(len(signals), 0)
        # No additional signals created
        self.assertEqual(DocumentSignal.objects.filter(document=doc).count(), count_after_save)

    def test_document_signals_lowest_confidence(self):
        """Document rule signals have appropriate confidence levels."""
        from apps.life.models import DocumentSignal

        doc = self._create_document(category='medical')
        for s in DocumentSignal.objects.filter(document=doc):
            if s.extractor_type == 'category_rule':
                self.assertLessEqual(s.confidence, 0.7)


class TargetedRecomputeTests(ExtractionTestMixin, TestCase):
    """Test TargetedSignalRecomputeService."""

    def test_capture_blend_creates_inferred_snapshot(self):
        """Capture signals blend into new inferred_behavior snapshots."""
        from apps.capture.models import CaptureEntry, CaptureSignal
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.ai_eae.targeted_recompute import TargetedSignalRecomputeService

        entry = CaptureEntry.objects.create(
            user=self.user, title="Test", transcript="test",
            status=CaptureEntry.STATUS_READY,
            duration_seconds=60,
            audio_file_url="https://example.com/audio.webm",
        )
        cs = CaptureSignal.objects.create(
            entry=entry, signal_type='health_activity', domain='health',
            confidence=0.85, extracted_text='went for a run',
            direction='positive', extractor_type='health_behavior',
        )

        affected = TargetedSignalRecomputeService.recompute_for_capture(
            self.user, self.today, [cs],
        )

        self.assertIn('health_activity', affected)
        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        self.assertEqual(snap.signal_class, 'inferred_behavior')
        self.assertAlmostEqual(snap.confidence, 0.85 * 0.6, places=2)
        self.assertEqual(snap.source_signals['source'], 'capture_extraction')

    def test_verified_snapshot_not_overridden(self):
        """Capture signals annotate but don't override verified snapshots."""
        from apps.capture.models import CaptureEntry, CaptureSignal
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.ai_eae.targeted_recompute import TargetedSignalRecomputeService

        # Create verified snapshot first
        SignalSnapshot.objects.create(
            user=self.user, date=self.today, signal_type='health_activity',
            domain='health', signal_class='verified_action',
            score=0.8, confidence=1.0,
            source_signals={'workout_sessions': 2},
        )

        entry = CaptureEntry.objects.create(
            user=self.user, title="Test", transcript="test",
            status=CaptureEntry.STATUS_READY,
            duration_seconds=60,
            audio_file_url="https://example.com/audio.webm",
        )
        cs = CaptureSignal.objects.create(
            entry=entry, signal_type='health_activity', domain='health',
            confidence=0.9, extracted_text='went for a run',
            direction='positive', extractor_type='health_behavior',
        )

        TargetedSignalRecomputeService.recompute_for_capture(
            self.user, self.today, [cs],
        )

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        # Score and class unchanged
        self.assertEqual(snap.signal_class, 'verified_action')
        self.assertEqual(snap.score, 0.8)
        # But capture annotation added
        self.assertIn('capture_inferred', snap.source_signals)

    def test_highest_confidence_wins_between_inferred(self):
        """When multiple inferred sources exist, highest confidence wins."""
        from apps.capture.models import CaptureEntry, CaptureSignal
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.ai_eae.targeted_recompute import TargetedSignalRecomputeService

        # Create existing journal-inferred snapshot (conf=0.49)
        SignalSnapshot.objects.create(
            user=self.user, date=self.today, signal_type='faith_practice',
            domain='faith', signal_class='inferred_behavior',
            score=0.49, confidence=0.49,
            source_signals={'source': 'journal_nlp'},
        )

        entry = CaptureEntry.objects.create(
            user=self.user, title="Test", transcript="test",
            status=CaptureEntry.STATUS_READY,
            duration_seconds=60,
            audio_file_url="https://example.com/audio.webm",
        )
        # Capture signal: 0.9 * 0.6 = 0.54 > 0.49
        cs = CaptureSignal.objects.create(
            entry=entry, signal_type='faith_practice', domain='faith',
            confidence=0.9, extracted_text='prayed this morning',
            direction='positive', extractor_type='spiritual_faith',
        )

        TargetedSignalRecomputeService.recompute_for_capture(
            self.user, self.today, [cs],
        )

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='faith_practice',
        )
        # Capture wins because 0.54 > 0.49
        self.assertAlmostEqual(snap.confidence, 0.54, places=2)
        self.assertEqual(snap.source_signals['source'], 'capture_extraction')

    def test_lower_confidence_annotates_only(self):
        """Lower confidence inferred source annotates but doesn't override."""
        from apps.capture.models import CaptureEntry, CaptureSignal
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.ai_eae.targeted_recompute import TargetedSignalRecomputeService

        # Existing high-confidence journal inferred
        SignalSnapshot.objects.create(
            user=self.user, date=self.today, signal_type='health_activity',
            domain='health', signal_class='inferred_behavior',
            score=0.63, confidence=0.63,
            source_signals={'source': 'journal_nlp'},
        )

        entry = CaptureEntry.objects.create(
            user=self.user, title="Test", transcript="test",
            status=CaptureEntry.STATUS_READY,
            duration_seconds=60,
            audio_file_url="https://example.com/audio.webm",
        )
        # Capture: 0.7 * 0.6 = 0.42 < 0.63
        cs = CaptureSignal.objects.create(
            entry=entry, signal_type='health_activity', domain='health',
            confidence=0.7, extracted_text='went running',
            direction='positive', extractor_type='health_behavior',
        )

        TargetedSignalRecomputeService.recompute_for_capture(
            self.user, self.today, [cs],
        )

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        # Journal keeps its score
        self.assertAlmostEqual(snap.confidence, 0.63, places=2)
        self.assertEqual(snap.source_signals['source'], 'journal_nlp')
        # Capture annotation added
        self.assertIn('capture_inferred', snap.source_signals)

    def test_negative_direction_score_inverted(self):
        """Negative behaviors produce inverted score."""
        from apps.capture.models import CaptureEntry, CaptureSignal
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.ai_eae.targeted_recompute import TargetedSignalRecomputeService

        entry = CaptureEntry.objects.create(
            user=self.user, title="Test", transcript="test",
            status=CaptureEntry.STATUS_READY,
            duration_seconds=60,
            audio_file_url="https://example.com/audio.webm",
        )
        cs = CaptureSignal.objects.create(
            entry=entry, signal_type='health_activity', domain='health',
            confidence=0.8, extracted_text='skipped my workout',
            direction='negative', extractor_type='health_behavior',
        )

        TargetedSignalRecomputeService.recompute_for_capture(
            self.user, self.today, [cs],
        )

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        # Score inverted: 1.0 - (0.8 * 0.6) = 1.0 - 0.48 = 0.52
        self.assertAlmostEqual(snap.score, 0.52, places=2)

    def test_source_attribution_present(self):
        """All extraction signals include proper source attribution."""
        from apps.capture.models import CaptureEntry, CaptureSignal
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.ai_eae.targeted_recompute import TargetedSignalRecomputeService

        entry = CaptureEntry.objects.create(
            user=self.user, title="Test", transcript="test",
            status=CaptureEntry.STATUS_READY,
            duration_seconds=60,
            audio_file_url="https://example.com/audio.webm",
        )
        cs = CaptureSignal.objects.create(
            entry=entry, signal_type='relational_engagement',
            domain='relationships', confidence=0.9,
            extracted_text='had dinner with family',
            direction='positive', extractor_type='relationship',
        )

        TargetedSignalRecomputeService.recompute_for_capture(
            self.user, self.today, [cs],
        )

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='relational_engagement',
        )
        source = snap.source_signals
        self.assertEqual(source['source'], 'capture_extraction')
        self.assertIn('capture_entry_id', source)
        self.assertEqual(len(source['extractions']), 1)
        self.assertIn('text', source['extractions'][0])
        self.assertIn('confidence', source['extractions'][0])
        self.assertIn('direction', source['extractions'][0])
        self.assertIn('extractor', source['extractions'][0])

    def test_patterns_triggered_after_recompute(self):
        """Pattern engine is called after targeted recompute."""
        from apps.capture.models import CaptureEntry, CaptureSignal
        from apps.core.ai_eae.targeted_recompute import TargetedSignalRecomputeService

        entry = CaptureEntry.objects.create(
            user=self.user, title="Test", transcript="test",
            status=CaptureEntry.STATUS_READY,
            duration_seconds=60,
            audio_file_url="https://example.com/audio.webm",
        )
        cs = CaptureSignal.objects.create(
            entry=entry, signal_type='health_activity', domain='health',
            confidence=0.9, extracted_text='ran 5 miles',
            direction='positive', extractor_type='health_behavior',
        )

        with patch(
            'apps.core.ai_eae.targeted_recompute._recompute_affected_patterns'
        ) as mock_patterns:
            TargetedSignalRecomputeService.recompute_for_capture(
                self.user, self.today, [cs],
            )
            mock_patterns.assert_called_once_with(self.user, self.today)

    def test_document_blend_lower_confidence_than_capture(self):
        """Document signals have lower effective confidence than capture."""
        from apps.core.ai_eae.models import SignalSnapshot
        from apps.core.ai_eae.targeted_recompute import TargetedSignalRecomputeService
        from apps.life.models import Document, DocumentSignal

        from django.core.files.uploadedfile import SimpleUploadedFile
        fake_file = SimpleUploadedFile("test.pdf", b"fake", content_type="application/pdf")
        doc = Document.objects.create(
            user=self.user, title="Medical record", category='medical',
            file=fake_file,
        )
        ds = DocumentSignal.objects.create(
            document=doc, signal_type='health_activity', domain='health',
            confidence=0.65, extracted_text='medical category',
            direction='positive', extractor_type='category_rule',
        )

        TargetedSignalRecomputeService.recompute_for_document(
            self.user, self.today, [ds],
        )

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        # Rule discount: 0.65 * 0.4 = 0.26
        self.assertAlmostEqual(snap.confidence, 0.26, places=2)
        self.assertEqual(snap.source_signals['source'], 'document_extraction')


class NightlyBlendTests(ExtractionTestMixin, TestCase):
    """Test extraction blending within nightly aggregation pipeline."""

    def test_blend_extraction_signals_called_in_nightly(self):
        """_blend_extraction_signals is called during compute_daily_signals."""
        from apps.core.ai_eae.signal_aggregation import SignalAggregationService

        with patch.object(
            SignalAggregationService, '_blend_extraction_signals'
        ) as mock_blend:
            SignalAggregationService.compute_daily_signals(self.user, self.today)
            mock_blend.assert_called_once()


class ConfidenceHierarchyTests(ExtractionTestMixin, TestCase):
    """Test the confidence discount hierarchy."""

    def test_capture_discount_is_0_6(self):
        from apps.core.ai_eae.targeted_recompute import CAPTURE_CONFIDENCE_DISCOUNT
        self.assertEqual(CAPTURE_CONFIDENCE_DISCOUNT, 0.6)

    def test_document_llm_discount_is_0_5(self):
        from apps.core.ai_eae.targeted_recompute import DOCUMENT_LLM_CONFIDENCE_DISCOUNT
        self.assertEqual(DOCUMENT_LLM_CONFIDENCE_DISCOUNT, 0.5)

    def test_document_rule_discount_is_0_4(self):
        from apps.core.ai_eae.targeted_recompute import DOCUMENT_RULE_CONFIDENCE_DISCOUNT
        self.assertEqual(DOCUMENT_RULE_CONFIDENCE_DISCOUNT, 0.4)
