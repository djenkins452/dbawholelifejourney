"""
Context Signal PIE rules — lightweight life-context signals.

These signals explain WHY behavioral patterns may be disrupted.
They do NOT affect behavior scoring — only enrich coaching.

Rules:
  1. InjuryDetectedRule — journal mentions injury/pain keywords
  2. IllnessDetectedRule — journal mentions illness keywords
  3. FatigueDetectedRule — sleep deficit OR journal fatigue keywords
  4. TravelActiveRule — journal or calendar mentions travel keywords

All rules:
  - Run on scheduled_check (not real-time)
  - Max one signal per type per day (via dedupe_key)
  - 2-day cooldown (via created_at check on existing insights)
  - Negation-aware: "not sick", "no pain" suppresses detection
  - Architecture-compliant: read journal.body at signal layer, not CoS
"""

import logging
import re
from datetime import timedelta

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.rule_registry import register
from apps.core.ai_insights.utils import build_dedupe_key

logger = logging.getLogger(__name__)

# ── Keyword sets (hardened — Step 2) ──
_INJURY_HIGH = {'injured', 'injury', 'broken', 'fracture', 'sprain', 'sprained', 'twisted', 'tore', 'torn'}
_INJURY_MED = {'hurt', 'pain'}  # Removed: sore, ache, fell, fall, pulled (too ambiguous)

_ILLNESS_HIGH = {'fever', 'flu', 'covid', 'infection', 'vomiting', 'hospitalized'}
_ILLNESS_MED = {'sick', 'unwell', 'headache', 'nausea', 'congestion', 'cough'}  # Removed: cold (too ambiguous)

_FATIGUE_KEYWORDS = {'tired', 'exhausted', 'drained', 'fatigued', 'burnout'}  # Removed: worn, burned (ambiguous)

_TRAVEL_KEYWORDS_JOURNAL = {'traveling', 'travelling', 'flight', 'airport', 'hotel', 'vacation'}
# Calendar requires STRONG keywords only (Step 4)
_TRAVEL_KEYWORDS_CALENDAR_STRONG = {'flight', 'airport', 'hotel', 'boarding'}

# Negation patterns (Step 1) — suppress keyword within 3-word window
_NEGATION_WORDS = {'not', 'no', "don't", "didn't", "isn't", "wasn't", "aren't", "won't"}
_RECOVERY_PHRASES = {'feeling better', 'recovered', 'no longer', 'getting better', 'much better'}

# How many days back to scan journal entries
_JOURNAL_LOOKBACK_DAYS = 3

# Cooldown: don't re-fire same signal if one was created within this window
_COOLDOWN_HOURS = 48


def _get_recent_journal_texts(user, days):
    """Get list of lowercase journal body texts from recent entries."""
    try:
        from apps.journal.models import JournalEntry
        from django.utils import timezone as _tz

        cutoff = _tz.now() - timedelta(days=days)
        entries = JournalEntry.objects.filter(
            user=user,
            status='active',
            created_at__gte=cutoff,
        ).values_list('body', flat=True)

        return [body.lower() for body in entries if body]
    except Exception:
        return []


def _keyword_matches_with_negation(texts, keywords):
    """
    Find keyword matches in journal texts, filtering out negated occurrences.

    Returns set of confirmed (non-negated) keyword matches.

    Negation check: if any negation word appears within 3 words BEFORE the
    keyword, or if a recovery phrase appears in the same sentence, suppress.
    """
    confirmed = set()

    for text in texts:
        # Check recovery phrases first — suppress entire text
        if any(phrase in text for phrase in _RECOVERY_PHRASES):
            continue

        words = text.split()
        for i, word in enumerate(words):
            # Strip punctuation for matching
            clean = re.sub(r'[^\w]', '', word)
            if clean not in keywords:
                continue

            # Check 3-word window before for negation
            window_start = max(0, i - 3)
            preceding = words[window_start:i]
            preceding_clean = {re.sub(r'[^\w\']', '', w) for w in preceding}

            if preceding_clean & _NEGATION_WORDS:
                continue  # Negated — skip this match

            confirmed.add(clean)

    return confirmed


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


@register
class InjuryDetectedRule(BaseInsightRule):
    """Detect injury mentions in recent journal entries (negation-aware)."""

    rule_name = "injury_detected"
    module = "health"
    insight_type = "injury_detected"
    severity = "info"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        if _has_recent_insight(user, self.insight_type):
            return []

        texts = _get_recent_journal_texts(user, _JOURNAL_LOOKBACK_DAYS)
        if not texts:
            return []

        high_matches = _keyword_matches_with_negation(texts, _INJURY_HIGH)
        med_matches = _keyword_matches_with_negation(texts, _INJURY_MED)

        if not high_matches and not med_matches:
            return []

        sources = ['journal']

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
            },
            'dedupe_key': build_dedupe_key(user.id, self.insight_type, today_str),
        }]


@register
class IllnessDetectedRule(BaseInsightRule):
    """Detect illness mentions in journal entries or sleep logs (negation-aware)."""

    rule_name = "illness_detected"
    module = "health"
    insight_type = "illness_detected"
    severity = "info"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        if _has_recent_insight(user, self.insight_type):
            return []

        texts = _get_recent_journal_texts(user, _JOURNAL_LOOKBACK_DAYS)

        # SleepEntry structured illness factor
        has_sleep_illness = False
        try:
            from apps.health.models import SleepEntry
            from django.utils import timezone as _tz
            cutoff = _tz.now() - timedelta(days=_JOURNAL_LOOKBACK_DAYS)
            has_sleep_illness = SleepEntry.objects.filter(
                user=user,
                status='active',
                created_at__gte=cutoff,
                factors__contains=['illness'],
            ).exists()
        except Exception:
            pass

        high_matches = _keyword_matches_with_negation(texts, _ILLNESS_HIGH) if texts else set()
        med_matches = _keyword_matches_with_negation(texts, _ILLNESS_MED) if texts else set()

        if not high_matches and not med_matches and not has_sleep_illness:
            return []

        sources = []
        if high_matches or med_matches:
            sources.append('journal')
        if has_sleep_illness:
            sources.append('sleep')

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

        # Source 1: SAE sleep state
        sleep_deficit = False
        sleep_avg = None
        try:
            from apps.core.ai_state import get_module_state
            health_state = get_module_state(user, 'health')
            if health_state:
                sleep_avg = health_state.get('sleep_avg_duration_7d')
                if sleep_avg and sleep_avg < 390:  # < 6.5 hours
                    sleep_deficit = True
        except Exception:
            pass

        # Source 2: Journal fatigue keywords (negation-aware)
        texts = _get_recent_journal_texts(user, _JOURNAL_LOOKBACK_DAYS)
        fatigue_words = sorted(_keyword_matches_with_negation(texts, _FATIGUE_KEYWORDS)) if texts else []
        journal_fatigue = bool(fatigue_words)

        if not sleep_deficit and not journal_fatigue:
            return []

        # Single signal with appropriate confidence (Step 3)
        sources = []
        if sleep_deficit:
            sources.append('sleep')
        if journal_fatigue:
            sources.append('journal')

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

        # Source 1: Journal travel keywords (negation-aware)
        texts = _get_recent_journal_texts(user, _JOURNAL_LOOKBACK_DAYS)
        travel_words = sorted(_keyword_matches_with_negation(texts, _TRAVEL_KEYWORDS_JOURNAL)) if texts else []
        journal_travel = bool(travel_words)

        # Source 2: Calendar event titles — STRONG keywords only (Step 4)
        calendar_travel = False
        try:
            from apps.calendar_engine.models import CalendarEvent
            from django.utils import timezone as _tz
            cutoff = _tz.now() - timedelta(days=_JOURNAL_LOOKBACK_DAYS)
            events = CalendarEvent.objects.filter(
                user=user,
                start_dt__gte=cutoff,
            ).values_list('title', flat=True)[:50]

            for title in events:
                if title:
                    title_words = set(re.sub(r'[^\w\s]', '', title.lower()).split())
                    if title_words & _TRAVEL_KEYWORDS_CALENDAR_STRONG:
                        calendar_travel = True
                        break
        except Exception:
            pass

        # Source 3: SleepEntry travel factor
        sleep_travel = False
        try:
            from apps.health.models import SleepEntry
            from django.utils import timezone as _tz
            cutoff = _tz.now() - timedelta(days=_JOURNAL_LOOKBACK_DAYS)
            sleep_travel = SleepEntry.objects.filter(
                user=user,
                status='active',
                created_at__gte=cutoff,
                factors__contains=['travel'],
            ).exists()
        except Exception:
            pass

        # Calendar-only is NOT sufficient (Step 4) — need journal or sleep confirmation
        if calendar_travel and not journal_travel and not sleep_travel:
            return []  # Calendar alone is too noisy

        if not journal_travel and not calendar_travel and not sleep_travel:
            return []

        sources = []
        if journal_travel:
            sources.append('journal')
        if calendar_travel:
            sources.append('calendar')
        if sleep_travel:
            sources.append('sleep')

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
            },
            'dedupe_key': build_dedupe_key(user.id, self.insight_type, today_str),
        }]
