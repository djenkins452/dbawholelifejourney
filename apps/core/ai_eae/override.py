"""
EAE — Override State Machine (Phase 8.4).

Manages user signal overrides using the 3-strike doctrine:
    Strike 1: Clarify + recommend
    Strike 2: Confirm + consequences
    Strike 3: Comply + log + suppress (temporary or permanent)

Override types:
    PERMANENT: "don't ask again" → never surface this signal type again
    TEMPORARY: "not today" → 24h cooldown
    AMBIGUOUS: unclear intent → 12h cooldown (shorter)
"""
import logging
from datetime import timedelta
from typing import Dict, List, Optional

from django.utils import timezone

from apps.core.ai_eae.constants import (
    COOLDOWN_AMBIGUOUS_HOURS,
    COOLDOWN_TEMPORARY_HOURS,
    OVERRIDE_AUTO_ESCALATE_COUNT,
    OVERRIDE_AUTO_ESCALATE_WINDOW_DAYS,
    OVERRIDE_PERMANENT,
    OVERRIDE_STRIKE_MAX,
    OVERRIDE_TEMPORARY,
    apply_intensity,
)
from apps.core.ai_eae.models import EAEOverride

logger = logging.getLogger(__name__)


def get_active_overrides(user) -> Dict[str, EAEOverride]:
    """
    Load all active overrides for a user.
    Returns dict mapping signal_type → EAEOverride.
    """
    overrides = EAEOverride.objects.filter(user=user)
    active = {}
    for ov in overrides:
        if ov.is_active:
            active[ov.signal_type] = ov
    return active


def is_suppressed(signal_type: str, active_overrides: Dict[str, EAEOverride]) -> bool:
    """Check if a signal type is currently suppressed."""
    return signal_type in active_overrides


def filter_overridden_signals(signals, active_overrides: Dict[str, EAEOverride]) -> tuple:
    """
    Remove signals that are actively overridden/suppressed.

    Args:
        signals: List of ScoredSignal or CognitiveUnit.
        active_overrides: Active overrides from get_active_overrides().

    Returns:
        Tuple of (allowed_signals, override_events_audit).
    """
    if not active_overrides:
        return signals, []

    allowed = []
    override_events = []

    for sig in signals:
        # Build signal type key to check
        engine = getattr(sig, 'engine', getattr(sig, 'source_engine', ''))
        sig_type = getattr(sig, 'signal_type', getattr(sig, 'title', ''))
        check_key = f"{engine}:{sig_type}"

        if check_key in active_overrides:
            ov = active_overrides[check_key]
            override_events.append({
                'signal_type': check_key,
                'override_type': ov.override_type,
                'strike_count': ov.strike_count,
                'action': 'SUPPRESSED',
            })
            logger.debug("EAE override: Suppressed %s (type=%s)", check_key, ov.override_type)
        else:
            allowed.append(sig)

    return allowed, override_events


def record_override(
    user,
    signal_type: str,
    classification: str = 'temporary',
    intensity: float = 1.0,
) -> EAEOverride:
    """
    Record or update an override for a signal type.

    Args:
        user: Django User instance.
        signal_type: Signal type key (e.g., 'PIE:medication_adherence').
        classification: 'permanent', 'temporary', or 'ambiguous'.
        intensity: Intensity multiplier.

    Returns:
        The EAEOverride instance.
    """
    now = timezone.now()

    override, created = EAEOverride.objects.get_or_create(
        user=user,
        signal_type=signal_type,
        defaults={
            'override_type': OVERRIDE_TEMPORARY,
            'strike_count': 1,
        },
    )

    if not created:
        override.strike_count = min(override.strike_count + 1, OVERRIDE_STRIKE_MAX)

    # Classification determines override behavior
    if classification == 'permanent' or override.strike_count >= OVERRIDE_STRIKE_MAX:
        override.override_type = OVERRIDE_PERMANENT
        override.cooldown_until = None
        logger.info(
            "EAE override: PERMANENT suppression for %s (user=%s)",
            signal_type, user.pk,
        )
    elif classification == 'temporary':
        hours = apply_intensity(COOLDOWN_TEMPORARY_HOURS, intensity, inverse=True)
        override.override_type = OVERRIDE_TEMPORARY
        override.cooldown_until = now + timedelta(hours=hours)
        override.temporary_count_14d += 1
        logger.info(
            "EAE override: TEMPORARY cooldown for %s until %s (user=%s)",
            signal_type, override.cooldown_until, user.pk,
        )
    elif classification == 'ambiguous':
        hours = apply_intensity(COOLDOWN_AMBIGUOUS_HOURS, intensity, inverse=True)
        override.override_type = OVERRIDE_TEMPORARY
        override.cooldown_until = now + timedelta(hours=hours)
        override.temporary_count_14d += 1

    # Auto-escalation check: 3+ temporaries in 14 days → permanent
    auto_threshold = int(apply_intensity(
        OVERRIDE_AUTO_ESCALATE_COUNT, intensity, inverse=True,
    ))
    if (override.override_type == OVERRIDE_TEMPORARY
            and override.temporary_count_14d >= auto_threshold):
        override.override_type = OVERRIDE_PERMANENT
        override.cooldown_until = None
        logger.info(
            "EAE override: Auto-escalated to PERMANENT for %s "
            "(%d temporaries in 14d, user=%s)",
            signal_type, override.temporary_count_14d, user.pk,
        )

    override.save()
    return override


def cleanup_expired_overrides(user) -> int:
    """
    Remove expired temporary overrides.
    Returns count of cleaned up overrides.
    """
    now = timezone.now()
    expired = EAEOverride.objects.filter(
        user=user,
        override_type=OVERRIDE_TEMPORARY,
        cooldown_until__lt=now,
    )
    count = expired.count()
    if count > 0:
        expired.delete()
        logger.debug("EAE override: Cleaned up %d expired overrides for user %s", count, user.pk)
    return count
