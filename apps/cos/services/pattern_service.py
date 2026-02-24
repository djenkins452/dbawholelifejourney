"""
CosPatternService — Pattern Detection + Solution Suggestions for CoS v2.

Analyzes reflections and activity data to detect actionable patterns,
then generates evidence-based solution suggestions.

Pattern detectors:
1. Negative streak — Declining sentiment over consecutive days
2. Fatigue pattern — Repeated negative reflections around specific activities
3. Consistency drop — Activity frequency declining vs previous period
4. Positive momentum — Improving sentiment (reinforcement, not just warnings)
5. Activity gap — No reflections for a previously active type

Solution suggestions:
- Each pattern maps to 1-2 actionable suggestions
- Suggestions include evidence chain (reflection IDs, dates, sentiments)
- Dedup: same pattern+theme won't fire twice in the same analysis window
- Frequency control: suggestions checked against CosGoalSuggestion throttle

Integration:
- Can optionally fire PIE events via fire_intelligence()
- Feeds Phase 7 (Goal Suggestion Policy) via CosGoalSuggestion
"""

import datetime as dt
import hashlib
import logging
from collections import Counter
from typing import Any, Dict, List, Optional

from django.utils import timezone as dj_timezone

from apps.cos.models import CosGoalSuggestion, CosReflection
from apps.cos.services.reflection_service import CosReflectionService

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Data Classes (plain dicts for Python 3.9 compat)
# ──────────────────────────────────────────────────────────


def _pattern_result(
    pattern_type,
    activity_type,
    severity,
    confidence,
    title,
    message,
    evidence,
    suggestions=None,
):
    """Build a standardized pattern result dict."""
    return {
        "pattern_type": pattern_type,
        "activity_type": activity_type,
        "severity": severity,  # info, positive, warning, critical
        "confidence": confidence,  # 0.0-1.0
        "title": title,
        "message": message,
        "evidence": evidence,
        "suggestions": suggestions or [],
        "dedupe_key": _build_dedupe_key(pattern_type, activity_type, evidence),
    }


def _suggestion(theme, text, evidence_summary):
    """Build a standardized suggestion dict."""
    return {
        "theme": theme,
        "text": text,
        "evidence_summary": evidence_summary,
    }


def _build_dedupe_key(pattern_type, activity_type, evidence):
    """Build a unique key for dedup within an analysis window."""
    parts = [
        pattern_type,
        activity_type,
        str(evidence.get("window_start", "")),
        str(evidence.get("window_end", "")),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ──────────────────────────────────────────────────────────
# Pattern Thresholds
# ──────────────────────────────────────────────────────────

# Minimum reflections needed to detect patterns
MIN_REFLECTIONS_FOR_PATTERN = 3

# Confidence thresholds
HIGH_CONFIDENCE = 0.85
MEDIUM_CONFIDENCE = 0.7
LOW_CONFIDENCE = 0.5

# Streak thresholds
NEGATIVE_STREAK_DAYS = 3  # 3+ consecutive negative days = pattern
POSITIVE_STREAK_DAYS = 5  # 5+ consecutive positive days = momentum

# Consistency drop threshold
CONSISTENCY_DROP_PCT = 0.5  # 50% drop in activity = pattern

# Fatigue detection
FATIGUE_NEGATIVE_RATIO = 0.6  # 60%+ negative reflections = fatigue

# Suggestion frequency (days between same-theme suggestions)
SUGGESTION_COOLDOWN_DAYS = 30


# ──────────────────────────────────────────────────────────
# CosPatternService
# ──────────────────────────────────────────────────────────


class CosPatternService:
    """
    Analyzes reflection data to detect patterns and generate suggestions.

    Usage:
        svc = CosPatternService(user)
        patterns = svc.detect_all_patterns()
        suggestions = svc.generate_suggestions(patterns)
    """

    def __init__(self, user):
        self.user = user
        self._reflection_svc = CosReflectionService(user)

    # ── Main Entry Points ──────────────────────────────────

    def detect_all_patterns(self, days=30):
        """
        Run all pattern detectors and return combined results.

        Returns: list of pattern result dicts, sorted by confidence desc.
        """
        patterns = []
        today = dj_timezone.now().date()
        window_start = today - dt.timedelta(days=days)

        # Get active activity types
        active_types = self._reflection_svc.get_active_types(days=days)
        if not active_types:
            return []

        for activity_type, count in active_types:
            if count < MIN_REFLECTIONS_FOR_PATTERN:
                continue

            # Run each detector
            patterns.extend(
                self._detect_negative_streak(activity_type, days, today)
            )
            patterns.extend(
                self._detect_fatigue(activity_type, days, today)
            )
            patterns.extend(
                self._detect_positive_momentum(activity_type, days, today)
            )

        # Cross-type detectors (don't need per-type loop)
        patterns.extend(self._detect_consistency_drop(days, today))
        patterns.extend(self._detect_activity_gap(days, today))

        # Deduplicate by dedupe_key
        seen = set()
        unique = []
        for p in patterns:
            if p["dedupe_key"] not in seen:
                seen.add(p["dedupe_key"])
                unique.append(p)

        # Sort by confidence descending
        unique.sort(key=lambda p: p["confidence"], reverse=True)
        return unique

    def generate_suggestions(self, patterns, max_suggestions=3):
        """
        Generate solution suggestions from detected patterns.

        Applies frequency control:
        - Skips themes that are opted out
        - Skips themes suggested within SUGGESTION_COOLDOWN_DAYS
        - Limits total suggestions per run

        Returns: list of suggestion dicts ready for storage.
        """
        suggestions = []
        today = dj_timezone.now().date()

        for pattern in patterns:
            if len(suggestions) >= max_suggestions:
                break

            for sug in pattern.get("suggestions", []):
                if len(suggestions) >= max_suggestions:
                    break

                theme = sug["theme"]

                # Check opt-out
                if CosGoalSuggestion.is_theme_opted_out(self.user, theme):
                    logger.debug(
                        "Skipping suggestion for opted-out theme: %s", theme
                    )
                    continue

                # Check cooldown
                last_date = CosGoalSuggestion.last_suggestion_date(
                    self.user, theme
                )
                if last_date:
                    days_since = (today - last_date).days
                    if days_since < SUGGESTION_COOLDOWN_DAYS:
                        logger.debug(
                            "Skipping suggestion for theme %s — "
                            "last suggested %d days ago (cooldown: %d)",
                            theme, days_since, SUGGESTION_COOLDOWN_DAYS,
                        )
                        continue

                suggestions.append({
                    "theme": theme,
                    "text": sug["text"],
                    "evidence_summary": sug["evidence_summary"],
                    "pattern_type": pattern["pattern_type"],
                    "activity_type": pattern["activity_type"],
                    "confidence": pattern["confidence"],
                })

        return suggestions

    def detect_and_suggest(self, days=30, max_suggestions=3):
        """
        Convenience method: detect patterns + generate suggestions.

        Returns: {"patterns": [...], "suggestions": [...]}
        """
        patterns = self.detect_all_patterns(days=days)
        suggestions = self.generate_suggestions(
            patterns, max_suggestions=max_suggestions
        )
        return {
            "patterns": patterns,
            "suggestions": suggestions,
        }

    # ── Pattern Detectors ──────────────────────────────────

    def _detect_negative_streak(self, activity_type, days, today):
        """
        Detect consecutive days of negative sentiment for an activity type.

        Pattern: 3+ consecutive days of negative/mixed reflections.
        Suggestion: "Consider adjusting your routine" or "Take a rest day."
        """
        results = []
        streak_data = self._reflection_svc.get_streak_reflections(
            activity_type, days=days
        )
        date_groups = streak_data.get("date_groups", {})
        if not date_groups:
            return results

        # Find consecutive negative days
        sorted_dates = sorted(date_groups.keys(), reverse=True)
        neg_streak = 0
        neg_streak_dates = []

        for d in sorted_dates:
            day_refs = date_groups[d]
            day_sentiments = [r.sentiment for r in day_refs]
            dominant = Counter(day_sentiments).most_common(1)[0][0]

            if dominant in ("negative", "mixed"):
                neg_streak += 1
                neg_streak_dates.append(d)
            else:
                if neg_streak >= NEGATIVE_STREAK_DAYS:
                    break  # Found a streak, stop
                neg_streak = 0
                neg_streak_dates = []

        if neg_streak >= NEGATIVE_STREAK_DAYS:
            type_label = activity_type.replace("_", " ")
            confidence = min(
                HIGH_CONFIDENCE,
                MEDIUM_CONFIDENCE + (neg_streak - NEGATIVE_STREAK_DAYS) * 0.05,
            )

            window_start = min(neg_streak_dates)
            window_end = max(neg_streak_dates)

            # Collect evidence reflection IDs
            evidence_ids = []
            for d in neg_streak_dates:
                evidence_ids.extend(r.pk for r in date_groups[d])

            results.append(
                _pattern_result(
                    pattern_type="negative_streak",
                    activity_type=activity_type,
                    severity="warning",
                    confidence=confidence,
                    title="{} days of tough {} reflections".format(
                        neg_streak, type_label,
                    ),
                    message=(
                        "Your {} reflections have been negative or mixed "
                        "for {} consecutive days ({} to {}). "
                        "This might indicate burnout or that something "
                        "needs to change."
                    ).format(
                        type_label, neg_streak,
                        window_start.isoformat(), window_end.isoformat(),
                    ),
                    evidence={
                        "negative_days": neg_streak,
                        "dates": [d.isoformat() for d in neg_streak_dates],
                        "reflection_ids": evidence_ids,
                        "window_start": window_start.isoformat(),
                        "window_end": window_end.isoformat(),
                    },
                    suggestions=[
                        _suggestion(
                            theme="{}_recovery".format(activity_type),
                            text=(
                                "Consider adjusting your {} routine — "
                                "modify the intensity, timing, or format "
                                "to see if it helps."
                            ).format(type_label),
                            evidence_summary=(
                                "{} consecutive days of negative {} reflections "
                                "({} to {})."
                            ).format(
                                neg_streak, type_label,
                                window_start.isoformat(),
                                window_end.isoformat(),
                            ),
                        ),
                    ],
                )
            )

        return results

    def _detect_fatigue(self, activity_type, days, today):
        """
        Detect fatigue pattern: high ratio of negative reflections.

        Pattern: 60%+ of reflections in the period are negative.
        Suggestion: "Take a break" or "Reduce frequency."
        """
        results = []
        cutoff = today - dt.timedelta(days=days)
        reflections = list(
            CosReflection.objects.filter(
                user=self.user,
                activity_type=activity_type,
                activity_date__gte=cutoff,
            )
        )

        if len(reflections) < MIN_REFLECTIONS_FOR_PATTERN:
            return results

        sentiments = [r.sentiment for r in reflections]
        neg_count = sum(1 for s in sentiments if s in ("negative", "mixed"))
        neg_ratio = neg_count / len(sentiments)

        if neg_ratio >= FATIGUE_NEGATIVE_RATIO:
            type_label = activity_type.replace("_", " ")
            confidence = min(
                HIGH_CONFIDENCE,
                MEDIUM_CONFIDENCE + (neg_ratio - FATIGUE_NEGATIVE_RATIO) * 0.5,
            )

            results.append(
                _pattern_result(
                    pattern_type="fatigue",
                    activity_type=activity_type,
                    severity="warning",
                    confidence=confidence,
                    title="{} may be causing fatigue".format(
                        type_label.title()
                    ),
                    message=(
                        "{}% of your {} reflections over the last {} days "
                        "have been negative or mixed ({} of {}). "
                        "You might be pushing too hard."
                    ).format(
                        int(neg_ratio * 100), type_label, days,
                        neg_count, len(reflections),
                    ),
                    evidence={
                        "negative_ratio": round(neg_ratio, 2),
                        "negative_count": neg_count,
                        "total_count": len(reflections),
                        "reflection_ids": [r.pk for r in reflections],
                        "window_start": cutoff.isoformat(),
                        "window_end": today.isoformat(),
                    },
                    suggestions=[
                        _suggestion(
                            theme="{}_rest".format(activity_type),
                            text=(
                                "Consider reducing your {} frequency or "
                                "taking a rest period to recover."
                            ).format(type_label),
                            evidence_summary=(
                                "{}% of {} reflections were negative over "
                                "the last {} days."
                            ).format(
                                int(neg_ratio * 100), type_label, days,
                            ),
                        ),
                    ],
                )
            )

        return results

    def _detect_positive_momentum(self, activity_type, days, today):
        """
        Detect positive momentum: improving trend + streak.

        Pattern: Sentiment improving AND 5+ day streak.
        This is a reinforcement pattern — encouraging, not a warning.
        """
        results = []
        trend = self._reflection_svc.get_sentiment_trend(
            activity_type, days=days
        )
        streak = self._reflection_svc.get_streak_reflections(
            activity_type, days=days
        )

        if (
            trend["trend"] == "improving"
            and streak["streak_length"] >= POSITIVE_STREAK_DAYS
        ):
            type_label = activity_type.replace("_", " ")
            confidence = min(
                HIGH_CONFIDENCE,
                MEDIUM_CONFIDENCE
                + (streak["streak_length"] - POSITIVE_STREAK_DAYS) * 0.03,
            )

            results.append(
                _pattern_result(
                    pattern_type="positive_momentum",
                    activity_type=activity_type,
                    severity="positive",
                    confidence=confidence,
                    title="Great {} momentum!".format(type_label),
                    message=(
                        "You've reflected on {} for {} consecutive days "
                        "and your sentiment is improving. Keep it up!"
                    ).format(type_label, streak["streak_length"]),
                    evidence={
                        "streak_length": streak["streak_length"],
                        "trend": trend["trend"],
                        "dates": [
                            d.isoformat() for d in streak["dates"]
                        ],
                        "window_start": (
                            today - dt.timedelta(days=days)
                        ).isoformat(),
                        "window_end": today.isoformat(),
                    },
                    suggestions=[
                        _suggestion(
                            theme="{}_consistency".format(activity_type),
                            text=(
                                "You're on a great {} streak — "
                                "consider setting a consistency goal to "
                                "keep the momentum going."
                            ).format(type_label),
                            evidence_summary=(
                                "{}-day {} streak with improving sentiment."
                            ).format(streak["streak_length"], type_label),
                        ),
                    ],
                )
            )

        return results

    def _detect_consistency_drop(self, days, today):
        """
        Detect activity types where frequency has dropped significantly.

        Compares this period to previous period (e.g., last 15 days vs prior 15 days).
        Pattern: 50%+ drop in reflection count.
        """
        results = []
        half = days // 2
        recent_start = today - dt.timedelta(days=half)
        prior_start = today - dt.timedelta(days=days)

        # Get per-type counts for each half
        recent_refs = CosReflection.objects.filter(
            user=self.user,
            activity_date__gte=recent_start,
            activity_date__lte=today,
        )
        prior_refs = CosReflection.objects.filter(
            user=self.user,
            activity_date__gte=prior_start,
            activity_date__lt=recent_start,
        )

        recent_counts = Counter(
            r.activity_type for r in recent_refs if r.activity_type
        )
        prior_counts = Counter(
            r.activity_type for r in prior_refs if r.activity_type
        )

        for activity_type, prior_count in prior_counts.items():
            if prior_count < MIN_REFLECTIONS_FOR_PATTERN:
                continue

            recent_count = recent_counts.get(activity_type, 0)
            if prior_count > 0:
                drop_ratio = 1 - (recent_count / prior_count)
            else:
                continue

            if drop_ratio >= CONSISTENCY_DROP_PCT:
                type_label = activity_type.replace("_", " ")
                confidence = min(
                    HIGH_CONFIDENCE,
                    MEDIUM_CONFIDENCE + (drop_ratio - CONSISTENCY_DROP_PCT) * 0.3,
                )

                results.append(
                    _pattern_result(
                        pattern_type="consistency_drop",
                        activity_type=activity_type,
                        severity="warning",
                        confidence=confidence,
                        title="{} activity dropped {}%".format(
                            type_label.title(), int(drop_ratio * 100),
                        ),
                        message=(
                            "Your {} reflections dropped from {} to {} "
                            "compared to the prior period. "
                            "Has something changed?"
                        ).format(type_label, prior_count, recent_count),
                        evidence={
                            "prior_count": prior_count,
                            "recent_count": recent_count,
                            "drop_ratio": round(drop_ratio, 2),
                            "window_start": prior_start.isoformat(),
                            "window_end": today.isoformat(),
                        },
                        suggestions=[
                            _suggestion(
                                theme="{}_reengagement".format(activity_type),
                                text=(
                                    "Your {} activity has dropped — "
                                    "consider scheduling regular time "
                                    "to get back on track."
                                ).format(type_label),
                                evidence_summary=(
                                    "{} reflections dropped {}% ({} → {})."
                                ).format(
                                    type_label.title(),
                                    int(drop_ratio * 100),
                                    prior_count, recent_count,
                                ),
                            ),
                        ],
                    )
                )

        return results

    def _detect_activity_gap(self, days, today):
        """
        Detect activity types that were active but have gone silent.

        Pattern: Activity type had reflections in prior period but zero in recent.
        Requires at least MIN_REFLECTIONS_FOR_PATTERN in the prior period.
        """
        results = []
        gap_days = days // 2  # Look at most recent half
        gap_start = today - dt.timedelta(days=gap_days)
        full_start = today - dt.timedelta(days=days)

        # Types active in prior period
        prior_types = set(
            CosReflection.objects.filter(
                user=self.user,
                activity_date__gte=full_start,
                activity_date__lt=gap_start,
            )
            .exclude(activity_type="")
            .values_list("activity_type", flat=True)
            .distinct()
        )

        # Types active recently
        recent_types = set(
            CosReflection.objects.filter(
                user=self.user,
                activity_date__gte=gap_start,
            )
            .exclude(activity_type="")
            .values_list("activity_type", flat=True)
            .distinct()
        )

        # Types that disappeared
        gone = prior_types - recent_types
        for activity_type in gone:
            # Verify min reflections in prior period
            prior_count = CosReflection.objects.filter(
                user=self.user,
                activity_type=activity_type,
                activity_date__gte=full_start,
                activity_date__lt=gap_start,
            ).count()

            if prior_count < MIN_REFLECTIONS_FOR_PATTERN:
                continue

            type_label = activity_type.replace("_", " ")

            results.append(
                _pattern_result(
                    pattern_type="activity_gap",
                    activity_type=activity_type,
                    severity="info",
                    confidence=MEDIUM_CONFIDENCE,
                    title="No recent {} reflections".format(type_label),
                    message=(
                        "You had {} {} reflections before, but none in "
                        "the last {} days. Everything okay?"
                    ).format(prior_count, type_label, gap_days),
                    evidence={
                        "prior_count": prior_count,
                        "gap_days": gap_days,
                        "window_start": full_start.isoformat(),
                        "window_end": today.isoformat(),
                    },
                    suggestions=[
                        _suggestion(
                            theme="{}_restart".format(activity_type),
                            text=(
                                "You used to reflect on {} regularly — "
                                "would you like to pick it back up?"
                            ).format(type_label),
                            evidence_summary=(
                                "{} {} reflections in prior period, "
                                "none in last {} days."
                            ).format(prior_count, type_label, gap_days),
                        ),
                    ],
                )
            )

        return results

    # ── PIE Integration (optional) ─────────────────────────

    def fire_patterns_to_pie(self, patterns):
        """
        Optionally fire detected patterns into PIE as insight events.

        This allows PIE to include CoS patterns in its cross-domain analysis
        and PGE to surface them as guidance items.
        """
        try:
            from apps.core.ai_orchestrator.intelligence_hook import (
                fire_intelligence,
            )

            for pattern in patterns:
                if pattern["confidence"] >= HIGH_CONFIDENCE:
                    fire_intelligence(
                        user=self.user,
                        module="cos",
                        action="pattern_detected",
                        record_id=None,
                    )
                    # One event is enough to trigger PIE rules
                    break
        except ImportError:
            logger.debug("Intelligence hook not available")
        except Exception as e:
            logger.debug("PIE integration failed (non-fatal): %s", e)
