# ==============================================================================
# File: apps/life/services/email_fact_service.py
# Description: Phase 6B — Email fact extraction orchestrator
# Created: 2026-03-17
# ==============================================================================
"""
EmailFactExtractionService — Orchestrate email → facts → signals pipeline.

Pipeline:
  1. Classify each email (rules → LLM for uncertain)
  2. Extract facts from KEEP emails
  3. Batch all facts → FactSignalMapper → signals → patterns
  4. Create transactions from financial facts
  5. Update telemetry

Runs parallel to existing EmailProcessingService (task extraction).
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)


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
                       transactions_created, errors
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
            'errors': [],
        }

        all_facts = []

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

                # Step 2: Classify
                result = classify_email(email)
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

                # Update ProcessedEmail with fact results
                processed_email.facts_extracted = True
                processed_email.facts_created_count = len(facts)
                processed_email.save(update_fields=[
                    'facts_extracted', 'facts_created_count',
                ])

                all_facts.extend(facts)
                stats['facts_created'] += len(facts)

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
                    "Fact→Signal mapping failed for email batch: %s",
                    e, exc_info=True,
                )
                stats['errors'].append(f"signal_mapping: {str(e)[:100]}")

        # Step 5: Create transactions from financial facts (with dedup)
        financial_facts = [
            f for f in all_facts if f.fact_type in (
                'amount', 'obligation', 'subscription',
            )
        ]
        if financial_facts:
            tx_count = _create_email_transactions(
                self.user, financial_facts,
            )
            stats['transactions_created'] = tx_count

        # Step 6: Telemetry
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


def _create_email_transactions(user, financial_facts):
    """
    Create Transaction records from financial email facts.

    Includes cross-source dedup: checks for existing transactions
    within ±2 days and similar amount before creating.
    """
    from apps.finance.models import FinancialAccount, Transaction

    account = FinancialAccount.objects.filter(user=user).first()
    if not account:
        return 0

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

            # Cross-source dedup: ±2 days, ±$0.50 (compare absolute values)
            tx_date = fact.effective_date or timezone.now().date()
            abs_amount = Decimal(str(round(abs(amount), 2)))
            # Check both positive and negative ranges
            pos_range = (abs_amount - Decimal('0.50'), abs_amount + Decimal('0.50'))
            neg_range = (-abs_amount - Decimal('0.50'), -abs_amount + Decimal('0.50'))
            from django.db.models import Q
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

            # Determine sign: obligations/subscriptions are expenses
            if fact.fact_type in ('obligation', 'subscription'):
                amount = -abs(amount)
            else:
                amount = -abs(amount)  # Default negative for email receipts

            description = (
                sv.get('merchant')
                or sv.get('service')
                or sv.get('description', '')
            )
            if not description:
                description = f"Email transaction"

            Transaction.objects.create(
                user=user,
                account=account,
                date=tx_date,
                amount=Decimal(str(round(amount, 2))),
                description=str(description)[:300],
                source_type='email',
                source_id=source_id,
                notes="Auto-extracted from email",
            )
            created += 1

        except Exception as e:
            logger.warning(
                "Failed to create transaction from email fact %s: %s",
                fact.pk, e,
            )

    return created


def _update_email_telemetry(stats):
    """Update email fact extraction telemetry."""
    from django.core.cache import cache

    key = 'wlj:ops:email_fact_extraction'
    existing = cache.get(key) or {
        'scans': 0, 'emails_classified': 0, 'emails_kept': 0,
        'emails_skipped': 0, 'facts_created': 0, 'signals_affected': 0,
        'transactions_created': 0, 'last_run': None,
    }

    existing['scans'] += 1
    existing['emails_classified'] += stats.get('emails_classified', 0)
    existing['emails_kept'] += stats.get('emails_kept', 0)
    existing['emails_skipped'] += stats.get('emails_skipped', 0)
    existing['facts_created'] += stats.get('facts_created', 0)
    existing['signals_affected'] += stats.get('signals_affected', 0)
    existing['transactions_created'] += stats.get('transactions_created', 0)
    existing['last_run'] = timezone.now().isoformat()

    cache.set(key, existing, timeout=25 * 3600)
