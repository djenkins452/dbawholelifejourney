# ==============================================================================
# File: apps/core/ai_eae/fact_signal_mapper.py
# Description: Phase 6A — Deterministic Fact → Signal mapping
# Created: 2026-03-17
# ==============================================================================
"""
FactSignalMapper — Map ExtractedFacts to signals via deterministic rules.

This is NOT a new mapping system. It extends the existing signal pipeline:
1. Facts are mapped to signal_types using deterministic rules
2. Signals are blended via TargetedSignalRecomputeService
3. Patterns are recomputed for affected domains

NO LLM involvement. NO new signal types. Reuses existing taxonomy.
"""

import logging
from collections import defaultdict

from django.utils import timezone

logger = logging.getLogger(__name__)

# Fact → Signal confidence discount (facts are lower trust than verified data)
FACT_CONFIDENCE_DISCOUNT = 0.5

# Fact type → (signal_type, domain, direction)
FACT_SIGNAL_RULES = {
    'amount': ('financial_health', 'finance', 'positive'),
    'obligation': ('financial_health', 'finance', 'negative'),
    'subscription': ('financial_health', 'finance', 'positive'),
    'appointment': ('health_activity', 'health', 'positive'),
    'medication': ('medication_adherence', 'health', 'positive'),
}

# Person domain_hint → signal mapping
PERSON_DOMAIN_RULES = {
    'health': ('health_activity', 'health', 'positive'),
    'relationships': ('relational_engagement', 'relationships', 'positive'),
}

# Categories that indicate receipt/bill (for Transaction creation)
FINANCIAL_CATEGORIES = {'financial', 'tax', 'insurance'}
FINANCIAL_FACT_TYPES = {'amount', 'obligation', 'subscription'}


class FactSignalMapper:
    """
    Map ExtractedFacts to signals and optionally create Transactions.

    All mapping is deterministic. Uses existing TargetedSignalRecomputeService.
    """

    @staticmethod
    def process_facts(user, facts, document=None):
        """
        Process a list of ExtractedFacts: map to signals + create transactions.

        Args:
            user: User instance
            facts: list of ExtractedFact records
            document: Document instance (for transaction creation context)

        Returns:
            dict with 'signals_affected', 'transactions_created'
        """
        if not facts:
            return {'signals_affected': set(), 'transactions_created': 0}

        # Phase 1: Map facts to signal types
        signal_map = _map_facts_to_signals(facts)

        # Phase 2: Blend into SignalSnapshots via targeted recompute
        all_affected = set()
        for date, by_type in signal_map.items():
            affected = _blend_fact_signals(user, date, by_type)
            all_affected.update(affected)

        # Phase 3: Create transactions for financial facts
        tx_count = 0
        if document:
            tx_count = _create_transactions(user, facts, document)

        return {
            'signals_affected': all_affected,
            'transactions_created': tx_count,
        }


def _map_facts_to_signals(facts):
    """
    Map facts to signal types grouped by date.

    Returns:
        dict[date, dict[signal_type, list[fact_info]]]
    """
    result = defaultdict(lambda: defaultdict(list))

    for fact in facts:
        signal_info = _get_signal_for_fact(fact)
        if not signal_info:
            continue

        signal_type, domain, direction = signal_info
        # Use effective_date if available, otherwise creation date
        date = fact.effective_date or fact.created_at.date()

        result[date][signal_type].append({
            'confidence': fact.confidence,
            'direction': direction,
            'fact_type': fact.fact_type,
            'fact_id': fact.pk,
            'text': fact.extracted_text[:100],
        })

    return dict(result)


def _get_signal_for_fact(fact):
    """
    Get (signal_type, domain, direction) for a fact, or None.
    """
    if fact.fact_type == 'person':
        hint = fact.domain_hint or ''
        return PERSON_DOMAIN_RULES.get(hint)

    return FACT_SIGNAL_RULES.get(fact.fact_type)


def _blend_fact_signals(user, date, signals_by_type):
    """
    Blend fact-derived signals into SignalSnapshots.

    Uses the same pattern as targeted_recompute but with fact-specific
    confidence discounting.
    """
    from apps.core.ai_eae.models import SignalSnapshot
    from apps.core.ai_eae.signal_aggregation import (
        SIGNAL_TYPE_DOMAIN,
        SignalAggregationService,
    )
    from apps.core.ai_eae.targeted_recompute import (
        _compute_score,
        _recompute_affected_patterns,
    )

    affected = set()

    for signal_type, fact_infos in signals_by_type.items():
        # Take the best confidence fact for this signal type
        best = max(fact_infos, key=lambda f: f['confidence'])
        discounted = best['confidence'] * FACT_CONFIDENCE_DISCOUNT

        source_data = {
            'source': 'fact_extraction',
            'facts': fact_infos,
        }

        existing = SignalSnapshot.objects.filter(
            user=user, date=date, signal_type=signal_type,
        ).first()

        if existing and existing.signal_class in (
            'verified_action', 'verified_measurement',
        ):
            # Annotate only — never override verified
            source = existing.source_signals or {}
            source['fact_inferred'] = fact_infos
            existing.source_signals = source
            existing.save(update_fields=['source_signals'])
            affected.add(signal_type)

        elif existing and existing.signal_class == 'inferred_behavior':
            # Highest confidence wins
            if discounted > existing.confidence:
                score = _compute_score(discounted, best['direction'])
                SignalAggregationService._upsert_snapshot(
                    user, date, signal_type,
                    score=score,
                    confidence=discounted,
                    signal_class='inferred_behavior',
                    source_signals=source_data,
                )
                affected.add(signal_type)
            else:
                source = existing.source_signals or {}
                source['fact_inferred'] = fact_infos
                existing.source_signals = source
                existing.save(update_fields=['source_signals'])

        else:
            # No existing snapshot — create inferred
            score = _compute_score(discounted, best['direction'])
            SignalAggregationService._upsert_snapshot(
                user, date, signal_type,
                score=score,
                confidence=discounted,
                signal_class='inferred_behavior',
                source_signals=source_data,
            )
            affected.add(signal_type)

    # Trigger pattern recompute
    if affected:
        _recompute_affected_patterns(user, date)

    return affected


def _create_transactions(user, facts, document):
    """
    Create Transaction records from financial facts.

    Only creates transactions for amount/obligation/subscription facts
    when the document category suggests a financial document.
    """
    category = getattr(document, 'category', '') or ''
    if category not in FINANCIAL_CATEGORIES:
        return 0

    financial_facts = [
        f for f in facts if f.fact_type in FINANCIAL_FACT_TYPES
    ]
    if not financial_facts:
        return 0

    created = 0
    for fact in financial_facts:
        try:
            tx = _create_single_transaction(user, fact, document)
            if tx:
                created += 1
        except Exception as e:
            logger.warning(
                "Failed to create transaction from fact %s: %s",
                fact.pk, e,
            )

    return created


def _create_single_transaction(user, fact, document):
    """Create a single Transaction from a financial fact."""
    from apps.finance.models import FinancialAccount, Transaction

    sv = fact.structured_value or {}
    amount = sv.get('amount') or sv.get('value')
    if not amount:
        return None

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return None

    # Skip tiny amounts
    if abs(amount) < 0.01:
        return None

    # Check for existing transaction from this document
    existing = Transaction.objects.filter(
        user=user,
        source_type='document',
        source_id=str(document.pk),
    ).exists()
    if existing:
        return None

    # Get or use default account
    account = FinancialAccount.objects.filter(
        user=user,
    ).first()
    if not account:
        return None

    # Determine sign: obligations/subscriptions are expenses (negative)
    if fact.fact_type in ('obligation', 'subscription'):
        amount = -abs(amount)
    # amounts could be either — default negative for bills/receipts
    elif fact.fact_type == 'amount' and document.category in ('financial', 'tax'):
        amount = -abs(amount)

    description = sv.get('merchant') or sv.get('service') or sv.get('description', '')
    if not description:
        description = f"From document: {document.title}"

    tx_date = fact.effective_date or document.document_date
    if not tx_date:
        tx_date = document.created_at.date()

    return Transaction.objects.create(
        user=user,
        account=account,
        date=tx_date,
        amount=amount,
        description=str(description)[:300],
        source_type='document',
        source_id=str(document.pk),
        notes=f"Auto-extracted from document: {document.title}",
    )
