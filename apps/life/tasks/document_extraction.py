# ==============================================================================
# File: apps/life/tasks/document_extraction.py
# Description: Phase 6A — Async document content + fact extraction Celery tasks
# Created: 2026-03-17
# ==============================================================================
"""
Document extraction pipeline (Celery tasks).

Pipeline:
1. extract_document_content — Download file, run PDF/OCR, store raw_text
2. extract_document_facts — LLM fact extraction → validation → facts
3. map_document_facts_to_signals — Deterministic mapping → signals → patterns

All three steps are chained: content → facts → signals.
Step 1 runs on every extractable document upload.
Steps 2-3 only run if raw_text was successfully extracted.
"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    name="life.extract_document_content",
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def extract_document_content_task(document_id):
    """
    Phase 6A Step 1: Extract text content from a document file.

    Downloads file from storage, runs PDF text extraction or OCR,
    stores result in Document.raw_text.
    """
    from apps.life.models import Document

    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.warning("Document %s not found for extraction", document_id)
        return {'success': False, 'error': 'Document not found'}

    # Gate: skip if already extracted with same content
    if document.extraction_status == 'completed' and document.content_hash:
        logger.debug("Document %s already extracted — skipping", document_id)
        return {'success': True, 'skipped': True}

    # Gate: skip non-extractable types
    if document.extraction_status == 'not_applicable':
        return {'success': True, 'skipped': True}

    # Mark as processing
    document.extraction_status = 'processing'
    document.save(update_fields=['extraction_status'])

    try:
        from apps.core.extraction.content_extractor import extract_document_content
        result = extract_document_content(document)
    except Exception as e:
        logger.error(
            "Content extraction failed for document %s: %s",
            document_id, e, exc_info=True,
        )
        document.extraction_status = 'failed'
        document.save(update_fields=['extraction_status'])
        _update_telemetry(success=False)
        return {'success': False, 'error': str(e)}

    # Check for content_hash dedup (file unchanged since last extraction)
    if (result.get('content_hash')
            and result['content_hash'] == document.content_hash
            and document.raw_text):
        document.extraction_status = 'completed'
        document.save(update_fields=['extraction_status'])
        return {'success': True, 'skipped': True, 'reason': 'unchanged'}

    # Store results
    document.raw_text = result.get('text', '')
    document.extraction_quality = result.get('quality', 0.0)
    document.content_hash = result.get('content_hash', '')
    document.extracted_at = timezone.now()

    if result.get('has_text'):
        document.extraction_status = 'completed'
    elif result.get('error'):
        document.extraction_status = 'failed'
    else:
        document.extraction_status = 'completed'  # No text but no error (empty doc)

    document.save(update_fields=[
        'raw_text', 'extraction_status', 'extraction_quality',
        'extracted_at', 'content_hash',
    ])

    _update_telemetry(
        success=result.get('has_text', False),
        method=result.get('method', 'unknown'),
    )

    # Chain: if text was extracted, dispatch fact extraction
    if result.get('has_text') and len(document.raw_text.strip()) >= 50:
        try:
            extract_document_facts_task.delay(document_id)
        except Exception as e:
            logger.warning(
                "Celery dispatch for fact extraction failed for %s: %s — "
                "running sync", document_id, e,
            )
            _run_fact_extraction_sync(document)

    return {
        'success': True,
        'document_id': document_id,
        'method': result.get('method'),
        'has_text': result.get('has_text'),
        'quality': result.get('quality'),
    }


@shared_task(
    name="life.extract_document_facts",
    soft_time_limit=60,
    time_limit=90,
    acks_late=True,
)
def extract_document_facts_task(document_id):
    """
    Phase 6A Step 2+3: Extract facts from raw_text, map to signals.

    Calls DocumentFactExtractor → FactSignalMapper pipeline.
    """
    from apps.life.models import Document

    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.warning("Document %s not found for fact extraction", document_id)
        return {'success': False, 'error': 'Document not found'}

    return _run_fact_extraction_sync(document)


def _run_fact_extraction_sync(document):
    """Run the full fact extraction + signal mapping pipeline synchronously."""
    from apps.life.services.document_fact_extractor import DocumentFactExtractor
    from apps.core.ai_eae.fact_signal_mapper import FactSignalMapper

    # Step 2: Extract facts
    try:
        facts = DocumentFactExtractor.extract_facts(document)
    except Exception as e:
        logger.error(
            "Fact extraction failed for document %s: %s",
            document.pk, e, exc_info=True,
        )
        _update_fact_telemetry(success=False)
        return {'success': False, 'error': str(e)}

    if not facts:
        _update_fact_telemetry(success=True, facts_created=0)
        return {'success': True, 'facts': 0, 'signals': 0}

    # Step 3: Map facts to signals
    try:
        result = FactSignalMapper.process_facts(
            document.user, facts, document=document,
        )
    except Exception as e:
        logger.error(
            "Fact→Signal mapping failed for document %s: %s",
            document.pk, e, exc_info=True,
        )
        _update_fact_telemetry(
            success=True, facts_created=len(facts),
        )
        return {
            'success': True,
            'facts': len(facts),
            'signals': 0,
            'mapping_error': str(e),
        }

    _update_fact_telemetry(
        success=True,
        facts_created=len(facts),
        signals_affected=len(result.get('signals_affected', set())),
        transactions_created=result.get('transactions_created', 0),
    )

    return {
        'success': True,
        'document_id': document.pk,
        'facts': len(facts),
        'signals': len(result.get('signals_affected', set())),
        'transactions': result.get('transactions_created', 0),
    }


def _update_telemetry(success=True, method='unknown'):
    """Update content extraction telemetry."""
    from django.core.cache import cache

    key = 'wlj:ops:document_content_extraction'
    existing = cache.get(key) or {
        'processed': 0, 'success': 0, 'failure': 0,
        'by_method': {}, 'last_run': None,
    }

    existing['processed'] += 1
    if success:
        existing['success'] += 1
    else:
        existing['failure'] += 1

    by_method = existing.get('by_method', {})
    by_method[method] = by_method.get(method, 0) + 1
    existing['by_method'] = by_method
    existing['last_run'] = timezone.now().isoformat()

    cache.set(key, existing, timeout=25 * 3600)


def _update_fact_telemetry(success=True, facts_created=0,
                            signals_affected=0, transactions_created=0):
    """Update fact extraction telemetry."""
    from django.core.cache import cache

    key = 'wlj:ops:document_fact_extraction'
    existing = cache.get(key) or {
        'processed': 0, 'success': 0, 'failure': 0,
        'facts_created': 0, 'signals_affected': 0,
        'transactions_created': 0, 'last_run': None,
    }

    existing['processed'] += 1
    if success:
        existing['success'] += 1
    else:
        existing['failure'] += 1
    existing['facts_created'] += facts_created
    existing['signals_affected'] += signals_affected
    existing['transactions_created'] += transactions_created
    existing['last_run'] = timezone.now().isoformat()

    cache.set(key, existing, timeout=25 * 3600)
