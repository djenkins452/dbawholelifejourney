"""
Context Signal PIE rules — lightweight life-context signals.

These signals explain WHY behavioral patterns may be disrupted.
They do NOT affect behavior scoring — only enrich coaching.

Rules:
  1. InjuryDetectedRule — journal mentions injury/pain keywords
  2. IllnessDetectedRule — journal mentions illness keywords
  3. FatigueDetectedRule — sleep deficit OR journal fatigue keywords
  4. TravelActiveRule — journal or calendar mentions travel keywords

Hardening layers:
  - Negation-aware keyword matching (3-word window)
  - Recovery phrase suppression (newer recovery overrides older evidence)
  - Time decay (per-type expiration windows)
  - Freshness tagging (recent vs aging)
  - Cooldown (48h per type)
  - Architecture-compliant: reads journal.body at signal layer, not CoS
"""

import logging
import re
from datetime import timedelta

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.rule_registry import register
from apps.core.ai_insights.utils import build_dedupe_key

logger = logging.getLogger(__name__)

# ── Keyword sets ──
_INJURY_HIGH = {'injured', 'injury', 'broken', 'fracture', 'sprain', 'sprained', 'twisted', 'tore', 'torn'}
_INJURY_MED = {'hurt', 'pain'}

_ILLNESS_HIGH = {'fever', 'flu', 'covid', 'infection', 'vomiting', 'hospitalized'}
_ILLNESS_MED = {'sick', 'unwell', 'headache', 'nausea', 'congestion', 'cough'}

_FATIGUE_KEYWORDS = {'tired', 'exhausted', 'drained', 'fatigued', 'burnout'}

_TRAVEL_KEYWORDS_JOURNAL = {'traveling', 'travelling', 'flight', 'airport', 'hotel', 'vacation'}
_TRAVEL_KEYWORDS_CALENDAR_STRONG = {'flight', 'airport', 'hotel', 'boarding'}

# Negation
_NEGATION_WORDS = {'not', 'no', "don't", "didn't", "isn't", "wasn't", "aren't", "won't"}
# Recovery phrases — if found in a NEWER entry than the evidence, suppress signal
_RECOVERY_PHRASES = {'feeling better', 'recovered', 'no longer', 'getting better', 'much better',
                     'back to normal', 'feeling good', 'feeling great'}

# Time decay windows (hours from last evidence before signal expires)
_DECAY_HOURS = {
    'injury_detected': 72,
    'illness_detected': 72,
    'fatigue_detected': 48,
    'travel_active': 48,
}

# Freshness boundary (hours) — evidence newer than this = "recent", older = "aging"
_FRESHNESS_BOUNDARY_HOURS = 24

_JOURNAL_LOOKBACK_DAYS = 3
_COOLDOWN_HOURS = 48


# ── Shared helpers ──

def _get_recent_journal_entries(user, days):
    """
    Get recent journal entries with timestamps for evidence tracking.

    Returns list of (body_lower, created_at) tuples, ordered newest first.
    """
    try:
        from apps.journal.models import JournalEntry
        from django.utils import timezone as _tz

        cutoff = _tz.now() - timedelta(days=days)
        entries = JournalEntry.objects.filter(
            user=user,
            status='active',
            created_at__gte=cutoff,
        ).order_by('-created_at').values_list('body', 'created_at')

        return [(body.lower(), created_at) for body, created_at in entries if body]
    except Exception:
        return []


def _keyword_matches_with_evidence(entries, keywords):
    """
    Find keyword matches across journal entries with evidence timestamps.

    Returns (matched_keywords: set, last_evidence_at: datetime or None).
    Negation-aware. Recovery-phrase entries are skipped.
    """
    confirmed = set()
    last_evidence_at = None

    for text, created_at in entries:
        # Recovery phrases suppress this entry entirely
        if any(phrase in text for phrase in _RECOVERY_PHRASES):
            continue

        words = text.split()
        entry_has_match = False
        for i, word in enumerate(words):
            clean = re.sub(r'[^\w]', '', word)
            if clean not in keywords:
                continue

            # Negation check — 3-word window before
            window_start = max(0, i - 3)
            preceding = words[window_start:i]
            preceding_clean = {re.sub(r'[^\w\']', '', w) for w in preceding}

            if preceding_clean & _NEGATION_WORDS:
                continue

            confirmed.add(clean)
            entry_has_match = True

        if entry_has_match:
            # Track newest evidence timestamp
            if last_evidence_at is None or created_at > last_evidence_at:
                last_evidence_at = created_at

    return confirmed, last_evidence_at


def _has_newer_recovery(entries, evidence_at):
    """
    Check if any journal entry NEWER than the evidence contains recovery language.

    If recovery is more recent than the signal evidence, the signal is stale.
    """
    if not evidence_at:
        return False

    for text, created_at in entries:
        if created_at <= evidence_at:
            continue  # Older than evidence — skip
        if any(phrase in text for phrase in _RECOVERY_PHRASES):
            return True
    return False


def _compute_freshness(last_evidence_at):
    """Compute freshness tag based on evidence age."""
    if not last_evidence_at:
        return 'aging'
    from django.utils import timezone as _tz
    age_hours = (_tz.now() - last_evidence_at).total_seconds() / 3600
    return 'recent' if age_hours <= _FRESHNESS_BOUNDARY_HOURS else 'aging'


def _within_decay_window(last_evidence_at, signal_type):
    """Check if evidence is within the decay window for this signal type."""
    if not last_evidence_at:
        return False
    from django.utils import timezone as _tz
    decay_hours = _DECAY_HOURS.get(signal_type, 72)
    return (_tz.now() - last_evidence_at).total_seconds() / 3600 <= decay_hours


def _has_recent_insight(user, insight_type, hours=_COOLDOWN_HOURS):
    """Check if this insight type was already fired recently (cooldown)."""
    try:
        from apps.core.ai_insights.models import Insight
        from django.utils import timezone as _tz

        cutoff = _tz.now() - timedelta(hours=hours)
        return Insight.objects.filter(
            user=user,
            insight_type=insight_type,
            created_at__gte=cutoff,
        ).exists()
    except Exception:
        return False


def _suppression_gate(entries, last_evidence_at, signal_type):
    """
    Unified pre-emission suppression check.

    Returns (suppressed: bool, reason: str or None).
    """
    # 1. Within decay window?
    if not _within_decay_window(last_evidence_at, signal_type):
        return True, 'outside_decay_window'

    # 2. Recovery language in newer entries?
    if _has_newer_recovery(entries, last_evidence_at):
        return True, 'recovery_override'

    return False, None


# ── Rules ──

@register
class InjuryDetectedRule(BaseInsightRule):
    """Detect injury mentions in recent journal entries."""

    rule_name = "injury_detected"
    module = "health"
    insight_type = "injury_detected"
    severity = "info"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        if _has_recent_insight(user, self.insight_type):
            return []

        entries = _get_recent_journal_entries(user, _JOURNAL_LOOKBACK_DAYS)
        if not entries:
            return []

        high_matches, high_evidence = _keyword_matches_with_evidence(entries, _INJURY_HIGH)
        med_matches, med_evidence = _keyword_matches_with_evidence(entries, _INJURY_MED)

        if not high_matches and not med_matches:
            return []

        last_evidence_at = high_evidence or med_evidence
        suppressed, reason = _suppression_gate(entries, last_evidence_at, self.insight_type)
        if suppressed:
            return []

        sources = ['journal']
        freshness = _compute_freshness(last_evidence_at)

        if high_matches:
            confidence = 0.80
            summary = f"Injury mentioned: {', '.join(sorted(high_matches)[:3])}"
        else:
            confidence = 0.55
            summary = f"Pain/discomfort mentioned: {', '.join(sorted(med_matches)[:3])}"

        from django.utils import timezone
        today_str = str(timezone.now().date())

        return [{
            'insight_type': self.insight_type,
            'module': self.module,
            'severity': self.severity,
            'title': 'Possible injury detected',
            'message': summary,
            'explain_why': 'Journal entries mention injury-related keywords.',
            'confidence_score': confidence,
            'evidence': {
                'rule_name': self.rule_name,
                'high_keywords': sorted(high_matches),
                'med_keywords': sorted(med_matches),
                'sources': sources,
                'last_evidence_at': last_evidence_at.isoformat() if last_evidence_at else None,
                'freshness': freshness,
            },
            'dedupe_key': build_dedupe_key(user.id, self.insight_type, today_str),
        }]


@register
class IllnessDetectedRule(BaseInsightRule):
    """Detect illness mentions in journal entries or sleep logs."""

    rule_name = "illness_detected"
    module = "health"
    insight_type = "illness_detected"
    severity = "info"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        if _has_recent_insight(user, self.insight_type):
            return []

        entries = _get_recent_journal_entries(user, _JOURNAL_LOOKBACK_DAYS)

        # SleepEntry structured illness factor
        has_sleep_illness = False
        sleep_evidence_at = None
        try:
            from apps.health.models import SleepEntry
            from django.utils import timezone as _tz
            cutoff = _tz.now() - timedelta(days=_JOURNAL_LOOKBACK_DAYS)
            sleep_entry = SleepEntry.objects.filter(
                user=user,
                status='active',
                created_at__gte=cutoff,
                factors__contains=['illness'],
            ).order_by('-created_at').first()
            if sleep_entry:
                has_sleep_illness = True
                sleep_evidence_at = sleep_entry.created_at
        except Exception:
            pass

        high_matches, high_ev = _keyword_matches_with_evidence(entries, _ILLNESS_HIGH) if entries else (set(), None)
        med_matches, med_ev = _keyword_matches_with_evidence(entries, _ILLNESS_MED) if entries else (set(), None)

        if not high_matches and not med_matches and not has_sleep_illness:
            return []

        # Determine last evidence across all sources
        candidates = [t for t in [high_ev, med_ev, sleep_evidence_at] if t]
        last_evidence_at = max(candidates) if candidates else None

        suppressed, reason = _suppression_gate(entries, last_evidence_at, self.insight_type)
        if suppressed:
            return []

        sources = []
        if high_matches or med_matches:
            sources.append('journal')
        if has_sleep_illness:
            sources.append('sleep')

        freshness = _compute_freshness(last_evidence_at)

        if high_matches or has_sleep_illness:
            confidence = 0.80
            parts = []
            if high_matches:
                parts.append(f"journal: {', '.join(sorted(high_matches)[:3])}")
            if has_sleep_illness:
                parts.append("sleep log: feeling unwell")
            summary = f"Illness indicators: {'; '.join(parts)}"
        else:
            confidence = 0.55
            summary = f"Illness mentioned: {', '.join(sorted(med_matches)[:3])}"

        from django.utils import timezone
        today_str = str(timezone.now().date())

        return [{
            'insight_type': self.insight_type,
            'module': self.module,
            'severity': self.severity,
            'title': 'Possible illness detected',
            'message': summary,
            'explain_why': 'Journal entries or sleep logs mention illness indicators.',
            'confidence_score': confidence,
            'evidence': {
                'rule_name': self.rule_name,
                'high_keywords': sorted(high_matches),
                'med_keywords': sorted(med_matches),
                'sleep_illness_factor': has_sleep_illness,
                'sources': sources,
                'last_evidence_at': last_evidence_at.isoformat() if last_evidence_at else None,
                'freshness': freshness,
            },
            'dedupe_key': build_dedupe_key(user.id, self.insight_type, today_str),
        }]


@register
class FatigueDetectedRule(BaseInsightRule):
    """Detect fatigue from sleep deficit OR journal keywords. Single signal only."""

    rule_name = "fatigue_detected"
    module = "health"
    insight_type = "fatigue_detected"
    severity = "info"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        if _has_recent_insight(user, self.insight_type):
            return []

        # Source 1: SAE sleep state (always "recent" — computed from 7d rolling)
        sleep_deficit = False
        sleep_avg = None
        sleep_evidence_at = None
        try:
            from apps.core.ai_state import get_module_state
            from django.utils import timezone as _tz
            health_state = get_module_state(user, 'health')
            if health_state:
                sleep_avg = health_state.get('sleep_avg_duration_7d')
                if sleep_avg and sleep_avg < 390:
                    sleep_deficit = True
                    sleep_evidence_at = _tz.now()  # SAE state is current
        except Exception:
            pass

        # Source 2: Journal fatigue keywords
        entries = _get_recent_journal_entries(user, _JOURNAL_LOOKBACK_DAYS)
        fatigue_words, journal_evidence_at = _keyword_matches_with_evidence(
            entries, _FATIGUE_KEYWORDS
        ) if entries else (set(), None)
        fatigue_words = sorted(fatigue_words)
        journal_fatigue = bool(fatigue_words)

        if not sleep_deficit and not journal_fatigue:
            return []

        # Last evidence across sources
        candidates = [t for t in [sleep_evidence_at, journal_evidence_at] if t]
        last_evidence_at = max(candidates) if candidates else None

        # Suppression: journal recovery overrides journal fatigue (but not sleep deficit)
        if journal_fatigue and not sleep_deficit:
            suppressed, reason = _suppression_gate(entries, journal_evidence_at, self.insight_type)
            if suppressed:
                return []
        elif journal_fatigue and sleep_deficit:
            # Both sources — only suppress if recovery AND sleep has recovered
            if _has_newer_recovery(entries, journal_evidence_at) and not sleep_deficit:
                return []

        sources = []
        if sleep_deficit:
            sources.append('sleep')
        if journal_fatigue:
            sources.append('journal')

        freshness = _compute_freshness(last_evidence_at)

        if sleep_deficit and journal_fatigue:
            confidence = 0.85
            parts = []
            if sleep_avg:
                parts.append(f"sleep avg {sleep_avg // 60}h {sleep_avg % 60}m")
            parts.append(f"journal: {', '.join(fatigue_words[:3])}")
            summary = f"Fatigue indicators: {'; '.join(parts)}"
        elif sleep_deficit:
            confidence = 0.60
            summary = f"Sleep deficit: averaging {sleep_avg // 60}h {sleep_avg % 60}m (below 6.5h)"
        else:
            confidence = 0.55
            summary = f"Fatigue mentioned: {', '.join(fatigue_words[:3])}"

        from django.utils import timezone
        today_str = str(timezone.now().date())

        return [{
            'insight_type': self.insight_type,
            'module': self.module,
            'severity': self.severity,
            'title': 'Fatigue detected',
            'message': summary,
            'explain_why': 'Sleep data or journal entries indicate fatigue.',
            'confidence_score': confidence,
            'evidence': {
                'rule_name': self.rule_name,
                'sleep_deficit': sleep_deficit,
                'sleep_avg_minutes': sleep_avg,
                'journal_fatigue': journal_fatigue,
                'fatigue_words': fatigue_words,
                'sources': sources,
                'last_evidence_at': last_evidence_at.isoformat() if last_evidence_at else None,
                'freshness': freshness,
            },
            'dedupe_key': build_dedupe_key(user.id, self.insight_type, today_str),
        }]


@register
class TravelActiveRule(BaseInsightRule):
    """Detect travel from journal, calendar (strong keywords only), or sleep logs."""

    rule_name = "travel_active"
    module = "life"
    insight_type = "travel_active"
    severity = "info"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        if _has_recent_insight(user, self.insight_type):
            return []

        entries = _get_recent_journal_entries(user, _JOURNAL_LOOKBACK_DAYS)

        # Source 1: Journal travel keywords
        travel_words, journal_evidence_at = _keyword_matches_with_evidence(
            entries, _TRAVEL_KEYWORDS_JOURNAL
        ) if entries else (set(), None)
        travel_words = sorted(travel_words)
        journal_travel = bool(travel_words)

        # Source 2: Calendar event titles — STRONG keywords only
        calendar_travel = False
        calendar_evidence_at = None
        try:
            from apps.calendar_engine.models import CalendarEvent
            from django.utils import timezone as _tz
            cutoff = _tz.now() - timedelta(days=_JOURNAL_LOOKBACK_DAYS)
            events = CalendarEvent.objects.filter(
                user=user,
                start_dt__gte=cutoff,
            ).order_by('-start_dt').values_list('title', 'start_dt')[:50]

            for title, start_dt in events:
                if title:
                    title_words = set(re.sub(r'[^\w\s]', '', title.lower()).split())
                    if title_words & _TRAVEL_KEYWORDS_CALENDAR_STRONG:
                        calendar_travel = True
                        calendar_evidence_at = start_dt
                        break
        except Exception:
            pass

        # Source 3: SleepEntry travel factor
        sleep_travel = False
        sleep_evidence_at = None
        try:
            from apps.health.models import SleepEntry
            from django.utils import timezone as _tz
            cutoff = _tz.now() - timedelta(days=_JOURNAL_LOOKBACK_DAYS)
            sleep_entry = SleepEntry.objects.filter(
                user=user,
                status='active',
                created_at__gte=cutoff,
                factors__contains=['travel'],
            ).order_by('-created_at').first()
            if sleep_entry:
                sleep_travel = True
                sleep_evidence_at = sleep_entry.created_at
        except Exception:
            pass

        # Calendar-only is NOT sufficient — need journal or sleep
        if calendar_travel and not journal_travel and not sleep_travel:
            return []

        if not journal_travel and not calendar_travel and not sleep_travel:
            return []

        # Last evidence across sources
        candidates = [t for t in [journal_evidence_at, calendar_evidence_at, sleep_evidence_at] if t]
        last_evidence_at = max(candidates) if candidates else None

        # Decay check
        if not _within_decay_window(last_evidence_at, self.insight_type):
            return []

        sources = []
        if journal_travel:
            sources.append('journal')
        if calendar_travel:
            sources.append('calendar')
        if sleep_travel:
            sources.append('sleep')

        freshness = _compute_freshness(last_evidence_at)
        confidence = 0.80 if len(sources) >= 2 else 0.55

        parts = []
        if journal_travel:
            parts.append(f"journal: {', '.join(travel_words[:3])}")
        if calendar_travel:
            parts.append("calendar: travel event")
        if sleep_travel:
            parts.append("sleep log: travel/jet lag")
        summary = f"Travel indicators: {'; '.join(parts)}"

        from django.utils import timezone
        today_str = str(timezone.now().date())

        return [{
            'insight_type': self.insight_type,
            'module': self.module,
            'severity': self.severity,
            'title': 'Travel activity detected',
            'message': summary,
            'explain_why': 'Journal, calendar, or sleep logs indicate travel.',
            'confidence_score': confidence,
            'evidence': {
                'rule_name': self.rule_name,
                'journal_travel': journal_travel,
                'calendar_travel': calendar_travel,
                'sleep_travel': sleep_travel,
                'travel_words': travel_words,
                'sources': sources,
                'last_evidence_at': last_evidence_at.isoformat() if last_evidence_at else None,
                'freshness': freshness,
            },
            'dedupe_key': build_dedupe_key(user.id, self.insight_type, today_str),
        }]
