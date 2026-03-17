# ==============================================================================
# File: apps/life/services/email_fact_service.py
# Description: Phase 6B — Email fact extraction orchestrator
# Created: 2026-03-17
# ==============================================================================
"""
EmailFactExtractionService — Orchestrate email → facts → signals pipeline.

Pipeline:
  1. Classify each email (learning overrides → rules → LLM for uncertain)
  2. Extract facts from KEEP emails (with intent_type)
  3. Batch all facts → FactSignalMapper → signals → patterns
  4. Create transactions from financial facts (with fingerprint dedup)
  5. Create Documents from receipt emails
  6. Update telemetry

Runs parallel to existing EmailProcessingService (task extraction).
"""

import hashlib
import logging
import re
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# Regex for detecting receipts in email subject/body
_RECEIPT_PATTERNS = re.compile(
    r'receipt|invoice|order\s+confirm|purchase\s+confirm|payment\s+confirm',
    re.IGNORECASE,
)


class EmailFactExtractionService:
    """
    Orchestrate email fact extraction for a single scan batch.

    Called by GmailSyncService alongside EmailProcessingService.
    """

    def __init__(self, user):
        self.user = user

    def process_emails(self, emails):
        """
        Process a batch of emails: classify → extract facts → map to signals.

        Args:
            emails: list of email dicts from GmailService

        Returns:
            dict with: emails_classified, facts_created, signals_affected,
                       transactions_created, documents_created, errors
        """
        from apps.life.services.email_classifier import (
            classify_email,
            classify_with_llm,
        )
        from apps.life.services.email_fact_extractor import EmailFactExtractor
        from apps.core.ai_eae.fact_signal_mapper import FactSignalMapper

        stats = {
            'emails_classified': 0,
            'emails_kept': 0,
            'emails_skipped': 0,
            'facts_created': 0,
            'signals_affected': 0,
            'transactions_created': 0,
            'documents_created': 0,
            'errors': [],
        }

        all_facts = []
        receipt_emails = []  # Track receipt emails for Document creation

        for email in emails:
            try:
                # Step 1: Get or create ProcessedEmail (may already exist
                # from task extraction in the same scan)
                processed_email = self._get_or_update_processed_email(email)
                if not processed_email:
                    continue

                # Skip if facts already extracted
                if processed_email.facts_extracted:
                    continue

                stats['emails_classified'] += 1

                # Step 2: Classify (with learning overrides)
                result = classify_email(email, user=self.user)
                wlj_flagged = result.get('wlj_flagged', False)

                # Resolve UNCERTAIN via LLM
                if result['classification'] == 'uncertain':
                    result = classify_with_llm(email)

                # Update ProcessedEmail with classification
                processed_email.classification = result['classification']
                processed_email.classification_reason = result.get(
                    'reason', ''
                )[:200]
                processed_email.classification_confidence = result.get(
                    'confidence', 0.0
                )
                processed_email.save(update_fields=[
                    'classification', 'classification_reason',
                    'classification_confidence',
                ])

                if result['classification'] != 'keep':
                    stats['emails_skipped'] += 1
                    continue

                stats['emails_kept'] += 1

                # Step 3: Extract facts
                facts = EmailFactExtractor.extract_facts(
                    self.user, email, processed_email,
                    wlj_flagged=wlj_flagged,
                )

                # Step 3b: Assign intent_type to facts
                _assign_intent_types(facts)

                # Update ProcessedEmail with fact results
                processed_email.facts_extracted = True
                processed_email.facts_created_count = len(facts)
                processed_email.save(update_fields=[
                    'facts_extracted', 'facts_created_count',
                ])

                all_facts.extend(facts)
                stats['facts_created'] += len(facts)

                # Track receipt emails for Document creation
                if _is_receipt_email(email, facts):
                    receipt_emails.append((email, processed_email, facts))

            except Exception as e:
                logger.error(
                    "Error processing email %s for facts: %s",
                    email.get('id', 'unknown'), e, exc_info=True,
                )
                stats['errors'].append(
                    f"{email.get('subject', '')[:50]}: {str(e)[:100]}"
                )

        # Step 4: Batch signal mapping (single recompute)
        if all_facts:
            try:
                mapping_result = FactSignalMapper.process_facts(
                    self.user, all_facts, document=None,
                )
                stats['signals_affected'] = len(
                    mapping_result.get('signals_affected', set())
                )
            except Exception as e:
                logger.error(
                    "Fact->Signal mapping failed for email batch: %s",
                    e, exc_info=True,
                )
                stats['errors'].append(f"signal_mapping: {str(e)[:100]}")

        # Step 5: Create transactions from financial facts (with fingerprint)
        financial_facts = [
            f for f in all_facts if f.fact_type in (
                'amount', 'obligation', 'subscription',
            )
        ]
        if financial_facts:
            tx_count = _create_email_transactions(
                self.user, financial_facts, receipt_emails,
            )
            stats['transactions_created'] = tx_count

        # Step 6: Create Documents from receipt emails
        if receipt_emails:
            doc_count = _create_receipt_documents(
                self.user, receipt_emails,
            )
            stats['documents_created'] = doc_count

        # Step 7: Telemetry
        _update_email_telemetry(stats)

        return stats

    def _get_or_update_processed_email(self, email):
        """
        Get or create ProcessedEmail, populating Phase 6B metadata fields.

        The record may already exist from EmailProcessingService (task
        extraction). If so, we just add our metadata fields.
        """
        from apps.life.models import ProcessedEmail

        gmail_id = email.get('id', '')
        if not gmail_id:
            return None

        processed_email, created = ProcessedEmail.objects.get_or_create(
            user=self.user,
            gmail_message_id=gmail_id,
            defaults={
                'subject': (email.get('subject', '') or '')[:500],
                'sender': (email.get('sender', '') or '')[:255],
                'snippet': (email.get('body', '') or '')[:500],
                'received_date': email.get('date_parsed'),
            },
        )

        # If record existed (from task extraction), add metadata if missing
        if not created and not processed_email.subject:
            processed_email.subject = (
                email.get('subject', '') or ''
            )[:500]
            processed_email.sender = (
                email.get('sender', '') or ''
            )[:255]
            processed_email.snippet = (
                email.get('body', '') or ''
            )[:500]
            processed_email.received_date = email.get('date_parsed')
            processed_email.save(update_fields=[
                'subject', 'sender', 'snippet', 'received_date',
            ])

        return processed_email


# =============================================================================
# Intent Type Assignment
# =============================================================================

# Fact type → intent type mapping
INTENT_RULES = {
    'obligation': 'bill_due',
    'appointment': 'schedule_commitment',
    'subscription': 'recurring_obligation',
}


def _assign_intent_types(facts):
    """
    Assign intent_type to facts based on deterministic rules.

    Modifies facts in-place (saves to DB).
    """
    for fact in facts:
        intent = INTENT_RULES.get(fact.fact_type, '')
        if intent and not fact.intent_type:
            fact.intent_type = intent
            fact.save(update_fields=['intent_type'])


# =============================================================================
# Receipt Detection
# =============================================================================

def _is_receipt_email(email, facts):
    """
    Determine if an email is a receipt/invoice that should create a Document.

    Returns True if:
    - Subject/body matches receipt patterns AND has financial facts
    """
    if not facts:
        return False

    has_financial = any(
        f.fact_type in ('amount', 'obligation', 'subscription')
        for f in facts
    )
    if not has_financial:
        return False

    subject = email.get('subject', '') or ''
    body = (email.get('body', '') or '')[:500]
    text = f"{subject} {body}"

    return bool(_RECEIPT_PATTERNS.search(text))


# =============================================================================
# Transaction Fingerprint
# =============================================================================

def _compute_fingerprint(merchant, amount, date):
    """
    Compute a transaction fingerprint for dedup.

    fingerprint = SHA-256(normalized_merchant + rounded_amount + date_bucket)
    date_bucket = date rounded to nearest 3 days
    """
    # Normalize merchant: lowercase, strip whitespace, remove punctuation
    norm_merchant = re.sub(r'[^a-z0-9]', '', (merchant or '').lower())

    # Round amount to nearest dollar
    rounded = round(abs(float(amount)))

    # Date bucket: round to nearest 3-day window
    if date:
        day_bucket = (date.toordinal() // 3) * 3
    else:
        day_bucket = 0

    raw = f"{norm_merchant}:{rounded}:{day_bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# =============================================================================
# Transaction Creation (with fingerprint dedup)
# =============================================================================

def _create_email_transactions(user, financial_facts, receipt_emails=None):
    """
    Create Transaction records from financial email facts.

    Uses fingerprint-based dedup + cross-source dedup.
    """
    from apps.finance.models import FinancialAccount, Transaction

    account = FinancialAccount.objects.filter(user=user).first()
    if not account:
        return 0

    # Build map of receipt email facts for Document linking
    receipt_fact_ids = set()
    if receipt_emails:
        for _, _, facts in receipt_emails:
            for f in facts:
                receipt_fact_ids.add(f.pk)

    created = 0
    for fact in financial_facts:
        try:
            sv = fact.structured_value or {}
            amount = sv.get('amount') or sv.get('value')
            if not amount:
                continue

            try:
                amount = float(amount)
            except (TypeError, ValueError):
                continue

            if abs(amount) < 0.01:
                continue

            # Same-source dedup: check by source_type + source_id
            source_id = str(fact.source_object_id)
            if Transaction.objects.filter(
                user=user,
                source_type='email',
                source_id=source_id,
            ).exists():
                continue

            tx_date = fact.effective_date or timezone.now().date()
            description = (
                sv.get('merchant')
                or sv.get('service')
                or sv.get('description', '')
            )
            if not description:
                description = "Email transaction"

            # Fingerprint dedup
            fp = _compute_fingerprint(description, amount, tx_date)
            if fp and Transaction.objects.filter(
                user=user,
                fingerprint=fp,
            ).exists():
                logger.debug(
                    "Fingerprint dedup: skipping email tx %s $%.2f",
                    description, amount,
                )
                continue

            # Cross-source dedup: ±2 days, ±$0.50
            abs_amount = Decimal(str(round(abs(amount), 2)))
            pos_range = (
                abs_amount - Decimal('0.50'),
                abs_amount + Decimal('0.50'),
            )
            neg_range = (
                -abs_amount - Decimal('0.50'),
                -abs_amount + Decimal('0.50'),
            )
            if Transaction.objects.filter(
                Q(amount__range=pos_range) | Q(amount__range=neg_range),
                user=user,
                date__range=(
                    tx_date - timedelta(days=2),
                    tx_date + timedelta(days=2),
                ),
            ).exists():
                logger.debug(
                    "Cross-source dedup: skipping email tx $%.2f near %s",
                    amount, tx_date,
                )
                continue

            # Determine sign: all email-extracted amounts are expenses
            if fact.fact_type in ('obligation', 'subscription'):
                amount = -abs(amount)
            else:
                amount = -abs(amount)

            tx = Transaction.objects.create(
                user=user,
                account=account,
                date=tx_date,
                amount=Decimal(str(round(amount, 2))),
                description=str(description)[:300],
                source_type='email',
                source_id=source_id,
                fingerprint=fp,
                notes="Auto-extracted from email",
            )
            created += 1

        except Exception as e:
            logger.warning(
                "Failed to create transaction from email fact %s: %s",
                fact.pk, e,
            )

    return created


# =============================================================================
# Receipt → Document Creation
# =============================================================================

def _create_receipt_documents(user, receipt_emails):
    """
    Create Document records from receipt emails.

    Each receipt email → one Document (category=financial, subcategory=receipt).
    Stores cleaned email text in raw_text (no full body stored long-term).
    """
    from apps.life.models import Document

    created = 0
    for email, processed_email, facts in receipt_emails:
        try:
            gmail_id = email.get('id', '')

            # Dedup: don't create duplicate documents for same email
            if Document.objects.filter(
                user=user,
                source='email',
                source_id=gmail_id,
            ).exists():
                continue

            subject = (email.get('subject', '') or '')[:200]
            body = (email.get('body', '') or '')[:2000]

            doc = Document.objects.create(
                user=user,
                title=subject or 'Email Receipt',
                description=f"Auto-created from email receipt ({gmail_id})",
                category='financial',
                subcategory='receipt',
                source='email',
                source_id=gmail_id,
                raw_text=body,
                extraction_status='completed',
                extracted_at=timezone.now(),
                document_date=processed_email.received_date.date()
                if processed_email.received_date else timezone.now().date(),
            )

            # Link transactions to this document
            from apps.finance.models import Transaction
            Transaction.objects.filter(
                user=user,
                source_type='email',
                source_id=str(processed_email.pk),
            ).update(receipt_document=doc)

            created += 1
            logger.info(
                "Created receipt document %s from email %s",
                doc.pk, gmail_id,
            )

        except Exception as e:
            logger.warning(
                "Failed to create receipt document from email %s: %s",
                email.get('id', 'unknown'), e,
            )

    return created


# =============================================================================
# Telemetry
# =============================================================================

def _update_email_telemetry(stats):
    """Update email fact extraction telemetry."""
    from django.core.cache import cache

    key = 'wlj:ops:email_fact_extraction'
    existing = cache.get(key) or {
        'scans': 0, 'emails_classified': 0, 'emails_kept': 0,
        'emails_skipped': 0, 'facts_created': 0, 'signals_affected': 0,
        'transactions_created': 0, 'documents_created': 0, 'last_run': None,
    }

    existing['scans'] += 1
    existing['emails_classified'] += stats.get('emails_classified', 0)
    existing['emails_kept'] += stats.get('emails_kept', 0)
    existing['emails_skipped'] += stats.get('emails_skipped', 0)
    existing['facts_created'] += stats.get('facts_created', 0)
    existing['signals_affected'] += stats.get('signals_affected', 0)
    existing['transactions_created'] += stats.get('transactions_created', 0)
    existing['documents_created'] += stats.get('documents_created', 0)
    existing['last_run'] = timezone.now().isoformat()

    cache.set(key, existing, timeout=25 * 3600)
