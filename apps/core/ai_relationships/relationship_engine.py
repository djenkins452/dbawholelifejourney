"""
Whole Life Journey - Relationship Intelligence Engine

Project: Whole Life Journey
Path: apps/core/ai_relationships/relationship_engine.py
Purpose: Extract people, detect relational drift, generate suggestions

Description:
    Relationship intelligence that remembers what matters — people and
    milestones — and protects them proactively.

    Respects governance flags:
    - relationship_suggestions_enabled must be True for suggestions
    - Persona-aware suggestion generation
    - sensitivity_tags respected for relational topics

Public API:
    - extract_people_from_text(user, text, source_type, source_id) -> list[InteractionSignal]
    - compute_interaction_baselines(user) -> dict
    - detect_relational_drift(user) -> list[dict]
    - generate_relationship_suggestion(user, drift_alert) -> dict
    - suggest_opportunity_windows(user, person) -> list[dict]

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
import logging
import re
from typing import List, Optional

from django.db.models import Max
from django.utils import timezone

logger = logging.getLogger(__name__)

# Cadence target → expected interaction interval in days
CADENCE_DAYS = {
    'daily': 1,
    'weekly': 7,
    'biweekly': 14,
    'monthly': 30,
    'quarterly': 90,
}

# Drift threshold multiplier (1.5x cadence = drift alert)
DRIFT_MULTIPLIER = 1.5

# Suggestion templates by relationship type
SUGGESTION_TEMPLATES = {
    'family': [
        "It's been a while since you connected with {name}. Maybe a quick call?",
        "You haven't mentioned {name} in {days} days. Want to schedule some time?",
    ],
    'friend': [
        "{name} hasn't come up lately. Maybe reach out?",
        "It's been {days} days since {name} was last mentioned. Coffee catch-up?",
    ],
    'colleague': [
        "You haven't connected with {name} from work in a while.",
    ],
    'default': [
        "It's been {days} days since you last mentioned {name}.",
    ],
}


# =============================================================================
# EXTRACT PEOPLE FROM TEXT
# =============================================================================


def extract_people_from_text(user, text, source_type, source_id=''):
    """
    Extract people mentions from text and create InteractionSignals.

    Uses fuzzy name matching against existing Person records.
    Does NOT store raw text content — only extracted signals.

    Args:
        user: User instance
        text: Text to scan for people mentions
        source_type: 'journal', 'calendar', 'reflection', 'chat'
        source_id: Optional ID of the source record

    Returns:
        list of created InteractionSignal instances
    """
    from .models import InteractionSignal, Person

    if not text or not text.strip():
        return []

    # Get all active people for this user
    people = Person.objects.filter(user=user, is_active=True)
    if not people.exists():
        return []

    signals = []
    text_lower = text.lower()
    today = timezone.localdate()

    for person in people:
        name = person.display_name.lower()
        # Simple name matching — check if name appears in text
        # Use word boundary matching to avoid partial matches
        pattern = r'\b' + re.escape(name) + r'\b'
        if re.search(pattern, text_lower):
            # Check for duplicate signal on same day from same source
            existing = InteractionSignal.objects.filter(
                user=user,
                person=person,
                signal_date=today,
                source_type=source_type,
                source_id=source_id,
            ).exists()

            if not existing:
                signal = InteractionSignal.objects.create(
                    user=user,
                    person=person,
                    signal_date=today,
                    signal_type='mention',
                    confidence=0.8,
                    source_type=source_type,
                    source_id=source_id,
                )
                signals.append(signal)

                # Update last_interaction on Relationship
                _update_last_interaction(user, person, today)

    if signals:
        logger.info(
            "Extracted %d people mentions from %s for %s",
            len(signals), source_type, user.email,
        )

    return signals


# =============================================================================
# COMPUTE INTERACTION BASELINES
# =============================================================================


def compute_interaction_baselines(user):
    """
    Compute interaction frequency baselines for all relationships.

    Analyzes the last 90 days of interaction signals to determine
    actual interaction frequency per person.

    Args:
        user: User instance

    Returns:
        dict of person_id → {'avg_days': float, 'count_90d': int}
    """
    from .models import InteractionSignal, Relationship

    cutoff = timezone.localdate() - datetime.timedelta(days=90)
    relationships = Relationship.objects.filter(user=user).select_related('person')

    baselines = {}
    for rel in relationships:
        signals = InteractionSignal.objects.filter(
            user=user,
            person=rel.person,
            signal_date__gte=cutoff,
        ).order_by('signal_date').values_list('signal_date', flat=True)

        dates = list(set(signals))  # Dedupe same-day signals
        count = len(dates)

        if count >= 2:
            dates.sort()
            total_gap = (dates[-1] - dates[0]).days
            avg_days = total_gap / (count - 1)
        elif count == 1:
            avg_days = 90  # Only one signal in 90 days
        else:
            avg_days = None  # No data

        baselines[rel.person_id] = {
            'avg_days': avg_days,
            'count_90d': count,
            'person_name': rel.person.display_name,
            'cadence_target': rel.cadence_target,
            'importance_tier': rel.importance_tier,
        }

    return baselines


# =============================================================================
# DETECT RELATIONAL DRIFT
# =============================================================================


def detect_relational_drift(user):
    """
    Detect people the user hasn't interacted with within expected cadence.

    Compares last_interaction against cadence_target × DRIFT_MULTIPLIER.
    Only runs for users with relationship_suggestions_enabled.

    Args:
        user: User instance

    Returns:
        list of drift alert dicts sorted by importance_tier
    """
    from .models import Relationship
    from apps.core.blueprint.models import PersonalOperatingBlueprint

    # Check governance flag
    bp = PersonalOperatingBlueprint.get_or_create_for_user(user)
    if not bp.relationship_suggestions_enabled:
        return []

    today = timezone.localdate()
    alerts = []

    relationships = Relationship.objects.filter(
        user=user,
    ).select_related('person').order_by('importance_tier')

    for rel in relationships:
        if not rel.cadence_target:
            continue

        expected_days = CADENCE_DAYS.get(rel.cadence_target)
        if not expected_days:
            continue

        last = rel.last_interaction
        if last is None:
            # Never interacted since tracking started — alert
            gap_days = 999
        else:
            gap_days = (today - last).days

        threshold = expected_days * DRIFT_MULTIPLIER
        if gap_days > threshold:
            alerts.append({
                'person_id': rel.person_id,
                'person_name': rel.person.display_name,
                'person_type': rel.person.person_type,
                'relationship_type': rel.relationship_type,
                'importance_tier': rel.importance_tier,
                'cadence_target': rel.cadence_target,
                'expected_days': expected_days,
                'actual_gap_days': gap_days,
                'last_interaction': str(last) if last else None,
            })

    # Sort by importance (tier 1 first, then by gap)
    alerts.sort(key=lambda a: (a['importance_tier'], -a['actual_gap_days']))

    return alerts


# =============================================================================
# GENERATE RELATIONSHIP SUGGESTION
# =============================================================================


def generate_relationship_suggestion(user, drift_alert):
    """
    Generate a persona-aware relationship suggestion for a drift alert.

    Respects sensitivity_tags (won't push about 'relationships' if sensitive).

    Args:
        user: User instance
        drift_alert: dict from detect_relational_drift()

    Returns:
        dict with keys: title, message, suggestion_type, person_id
    """
    from apps.core.blueprint.models import PersonalOperatingBlueprint

    bp = PersonalOperatingBlueprint.get_or_create_for_user(user)

    # Check sensitivity
    if 'relationships' in (bp.sensitivity_tags or []):
        # Gentler framing when relationships is a sensitive topic
        return {
            'title': f"Thinking of {drift_alert['person_name']}",
            'message': (
                f"It's been a little while since {drift_alert['person_name']} "
                f"came up. No pressure — just wanted to mention it."
            ),
            'suggestion_type': 'gentle_mention',
            'person_id': drift_alert['person_id'],
        }

    person_type = drift_alert.get('person_type', 'other')
    templates = SUGGESTION_TEMPLATES.get(person_type, SUGGESTION_TEMPLATES['default'])
    template = templates[0]

    message = template.format(
        name=drift_alert['person_name'],
        days=drift_alert['actual_gap_days'],
    )

    return {
        'title': f"Reconnect with {drift_alert['person_name']}",
        'message': message,
        'suggestion_type': 'reconnect',
        'person_id': drift_alert['person_id'],
    }


# =============================================================================
# SUGGEST OPPORTUNITY WINDOWS
# =============================================================================


def suggest_opportunity_windows(user, person):
    """
    Find light windows in the weekly schedule for connecting with a person.

    Uses the weekly pressure engine to find opportunity windows.

    Args:
        user: User instance
        person: Person instance

    Returns:
        list of dicts with day, window_start, window_end
    """
    try:
        from apps.core.blueprint.weekly_pressure import compute_weekly_pressure
        pressure = compute_weekly_pressure(user)
        opportunities = pressure.get('opportunity_windows', [])

        windows = []
        for opp in opportunities[:3]:
            windows.append({
                'day': opp.get('day', ''),
                'date': opp.get('date', ''),
                'window_start': opp.get('start', ''),
                'window_end': opp.get('end', ''),
                'suggestion': f"Connect with {person.display_name}",
            })

        return windows
    except (ImportError, Exception) as e:
        logger.debug("Opportunity windows unavailable: %s", e)
        return []


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _update_last_interaction(user, person, date):
    """Update last_interaction on the Relationship record."""
    from .models import Relationship

    Relationship.objects.filter(
        user=user,
        person=person,
    ).update(last_interaction=date)
