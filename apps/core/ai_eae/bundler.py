"""
EAE — Cognitive Unit Bundler (Phase 8.3).

Groups related signals into bundles (cognitive units) to reduce attention cost.
A bundle counts as ONE cognitive unit regardless of how many signals it contains.

Bundling triggers:
    1. Same module + same action type → "Medications (3 due)"
    2. Same module + opposing signals → "Weight Trajectory"
    3. Causal chain (sleep → mood → journal) → "Recovery Priority"
"""
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from apps.core.ai_eae.constants import (
    BUNDLE_MAX_ITEMS,
    BUNDLE_MIN_ITEMS,
    BUNDLE_SCORE_BONUS,
)
from apps.core.ai_eae.scorer import ScoredSignal

logger = logging.getLogger(__name__)


# =============================================================================
# COGNITIVE UNIT — Output unit consumed by budget
# =============================================================================


@dataclass
class CognitiveUnit:
    """A single cognitive unit — the atomic unit of user attention."""

    unit_id: str            # UUID string
    rank: int = 0           # Assigned after budgeting (1 = highest)
    unit_type: str = 'single'  # 'single' or 'bundle'

    # Content
    title: str = ''
    why_this_matters: str = ''
    source_engine: str = ''
    module: str = ''
    severity: str = 'info'

    # Scoring
    normalized_score: float = 0.0
    confidence: float = 0.0
    drift_anchor_weight: float = 0.0

    # Bundle info
    bundle_label: str = ''
    bundled_count: int = 1

    # Actionability
    actionable: bool = False
    action_url: str = ''

    # Source signals
    signals: List[ScoredSignal] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Serialize for JSON storage in EAEDecisionLog."""
        return {
            'unit_id': self.unit_id,
            'rank': self.rank,
            'unit_type': self.unit_type,
            'title': self.title,
            'why_this_matters': self.why_this_matters,
            'source_engine': self.source_engine,
            'module': self.module,
            'severity': self.severity,
            'normalized_score': round(self.normalized_score, 2),
            'confidence': round(self.confidence, 2),
            'drift_anchor_weight': round(self.drift_anchor_weight, 2),
            'bundle_label': self.bundle_label,
            'bundled_count': self.bundled_count,
            'actionable': self.actionable,
            'action_url': self.action_url,
            'source_items': [
                {
                    'engine': s.engine,
                    'object_type': s.object_type,
                    'object_id': s.object_id,
                    'local_score': round(s.raw.local_score, 2),
                    'confidence': round(s.confidence, 2),
                }
                for s in self.signals
            ],
        }


# =============================================================================
# BUNDLING LOGIC
# =============================================================================


def _create_single_unit(signal: ScoredSignal) -> CognitiveUnit:
    """Create a single cognitive unit from one signal."""
    return CognitiveUnit(
        unit_id=str(uuid.uuid4()),
        unit_type='single',
        title=signal.title,
        why_this_matters=signal.message[:200] if signal.message else '',
        source_engine=signal.engine,
        module=signal.module,
        severity=signal.severity,
        normalized_score=signal.normalized_score,
        confidence=signal.confidence,
        drift_anchor_weight=signal.drift_anchor_weight,
        actionable=signal.actionable,
        action_url=signal.action_url,
        signals=[signal],
    )


def _create_bundle(
    signals: List[ScoredSignal],
    label: str,
    module: str,
) -> CognitiveUnit:
    """Create a bundle cognitive unit from multiple signals."""
    # Bundle inherits highest severity
    severity_order = {'critical': 4, 'warning': 3, 'positive': 2, 'info': 1}
    best_severity = max(signals, key=lambda s: severity_order.get(s.severity, 0))

    # Bundle score = max score + bonus
    max_score = max(s.normalized_score for s in signals)
    bundle_score = min(100.0, max_score + BUNDLE_SCORE_BONUS)

    # Bundle confidence = average
    avg_confidence = sum(s.confidence for s in signals) / len(signals)

    # Primary engine = engine of highest-scored signal
    primary = max(signals, key=lambda s: s.normalized_score)

    return CognitiveUnit(
        unit_id=str(uuid.uuid4()),
        unit_type='bundle',
        title=label,
        why_this_matters=f"{len(signals)} related items",
        source_engine=primary.engine,
        module=module,
        severity=best_severity.severity,
        normalized_score=bundle_score,
        confidence=avg_confidence,
        drift_anchor_weight=max(s.drift_anchor_weight for s in signals),
        bundle_label=label,
        bundled_count=len(signals),
        actionable=any(s.actionable for s in signals),
        action_url=primary.action_url,
        signals=signals,
    )


def _try_bundle_by_key(signals: List[ScoredSignal]) -> tuple:
    """
    Group signals by bundle_key and create bundles where applicable.
    Returns (bundles, unbundled_signals).
    """
    groups = defaultdict(list)
    for sig in signals:
        if sig.bundle_key:
            groups[sig.bundle_key].append(sig)
        else:
            groups[f"_solo_{sig.object_type}_{sig.object_id}"].append(sig)

    bundles = []
    unbundled = []

    for key, group in groups.items():
        if len(group) >= BUNDLE_MIN_ITEMS:
            # Cap bundle size
            group = sorted(group, key=lambda s: s.normalized_score, reverse=True)
            bundle_signals = group[:BUNDLE_MAX_ITEMS]
            remainder = group[BUNDLE_MAX_ITEMS:]

            # Create label from bundle key
            parts = key.split(':')
            engine = parts[0] if parts else ''
            module = parts[1] if len(parts) > 1 else ''
            detail = parts[2] if len(parts) > 2 else ''

            label = f"{module.title()} ({len(bundle_signals)} items)"
            if detail:
                label = f"{detail.replace('_', ' ').title()} ({len(bundle_signals)} items)"

            bundles.append(_create_bundle(bundle_signals, label, module))

            # Remainder becomes unbundled
            unbundled.extend(remainder)
        else:
            unbundled.extend(group)

    return bundles, unbundled


def bundle_signals(signals: List[ScoredSignal]) -> List[CognitiveUnit]:
    """
    Convert scored signals into cognitive units with bundling.

    Args:
        signals: Scored, deduped signals sorted by score descending.

    Returns:
        List of CognitiveUnit, sorted by normalized_score descending.
    """
    if not signals:
        return []

    # Try bundling by key
    bundles, unbundled = _try_bundle_by_key(signals)

    # Convert remaining unbundled to single units
    singles = [_create_single_unit(sig) for sig in unbundled]

    # Combine and sort
    all_units = bundles + singles
    all_units.sort(key=lambda u: u.normalized_score, reverse=True)

    logger.debug(
        "EAE bundler: %d signals → %d units (%d bundles, %d singles)",
        len(signals), len(all_units), len(bundles), len(singles),
    )

    return all_units
