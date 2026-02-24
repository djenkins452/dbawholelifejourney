"""
CosReflectionService — Reflection Storage + Retrieval for CoS v2.

Manages the lifecycle of reflections:
- CRUD operations for entity-attached reflections
- Temporal comparison queries (yesterday vs today, this week vs last)
- Contextual retrieval for enriching future prompts
- Sentiment trend analysis for pattern detection
- SLCME integration for long-term context memory

Reflections are stored indefinitely and used to:
1. Personalize future prompts ("Yesterday was tough — how was today?")
2. Feed pattern detection (Phase 6)
3. Provide evidence for goal suggestions (Phase 7)
"""

import datetime as dt
import logging
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, QuerySet
from django.utils import timezone as dj_timezone

from apps.cos.models import CosReflection

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Sentiment Detection (keyword-based, fast)
# ──────────────────────────────────────────────────────────

POSITIVE_WORDS = {
    "great", "good", "amazing", "awesome", "excellent", "fantastic",
    "wonderful", "happy", "love", "loved", "blessed", "grateful",
    "thankful", "accomplished", "energized", "strong", "proud",
    "refreshed", "motivated", "inspired", "peaceful", "calm",
    "productive", "successful", "fun", "enjoyed", "better",
    "improved", "progress", "breakthrough", "best",
}

NEGATIVE_WORDS = {
    "bad", "terrible", "awful", "horrible", "struggled", "hard",
    "tough", "difficult", "tired", "exhausted", "frustrated",
    "stressed", "anxious", "worried", "overwhelmed", "sad",
    "disappointed", "failed", "worse", "painful", "sore",
    "sick", "weak", "unmotivated", "lazy", "didn't", "couldn't",
    "skipped", "missed", "hurt", "rough", "worst", "terribly",
}


def detect_sentiment(text):
    """
    Fast keyword-based sentiment detection.

    Returns: "positive", "negative", "neutral", or "mixed"
    """
    if not text:
        return "neutral"

    words = set(re.findall(r'\b\w+\b', text.lower()))
    pos_count = len(words & POSITIVE_WORDS)
    neg_count = len(words & NEGATIVE_WORDS)

    if pos_count > 0 and neg_count > 0:
        return "mixed"
    elif pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    return "neutral"


# ──────────────────────────────────────────────────────────
# CosReflectionService
# ──────────────────────────────────────────────────────────


class CosReflectionService:
    """
    Manages the lifecycle of CoS reflections:
    create → query → enrich prompts → feed patterns
    """

    def __init__(self, user):
        self.user = user

    # ── CRUD ────────────────────────────────────────────────

    def create_reflection(
        self,
        source_entity,
        text,
        activity_type="",
        activity_date=None,
        sentiment="",
        prompt_text="",
        auto_sentiment=True,
    ):
        """
        Create a reflection attached to a source entity.

        Args:
            source_entity: The entity to attach to (CalendarEvent, JournalEntry, etc.)
            text: Reflection content
            activity_type: Type of activity (workout, meeting, etc.)
            activity_date: Date of the activity (defaults to today)
            sentiment: User-provided sentiment. If empty and auto_sentiment=True, auto-detected.
            prompt_text: The prompt that triggered this reflection (if any)
            auto_sentiment: Auto-detect sentiment if not provided

        Returns:
            CosReflection instance
        """
        if not source_entity:
            raise ValueError("source_entity is required for create_reflection")

        ct = ContentType.objects.get_for_model(source_entity)
        if not activity_date:
            if hasattr(source_entity, "start_dt") and source_entity.start_dt:
                activity_date = source_entity.start_dt.date()
            elif hasattr(source_entity, "entry_date"):
                activity_date = source_entity.entry_date
            else:
                activity_date = dj_timezone.now().date()

        if not sentiment and auto_sentiment:
            sentiment = detect_sentiment(text)

        reflection = CosReflection.objects.create(
            user=self.user,
            content_type=ct,
            object_id=source_entity.pk,
            text=text,
            sentiment=sentiment,
            activity_date=activity_date,
            activity_type=activity_type,
            prompt_text=prompt_text,
        )

        # Store in SLCME for long-term context
        self._store_in_slcme(reflection)

        logger.debug(
            "Created reflection: user=%s type=%s date=%s sentiment=%s",
            self.user.id, activity_type, activity_date, sentiment,
        )
        return reflection

    def get_reflection(self, reflection_id):
        """Get a single reflection by ID (scoped to user)."""
        try:
            return CosReflection.objects.get(
                pk=reflection_id, user=self.user,
            )
        except CosReflection.DoesNotExist:
            return None

    def update_reflection(self, reflection_id, text=None, sentiment=None):
        """
        Update a reflection's text and/or sentiment.

        Returns: Updated CosReflection or None if not found.
        """
        reflection = self.get_reflection(reflection_id)
        if not reflection:
            return None

        if text is not None:
            reflection.text = text
            if not sentiment:
                reflection.sentiment = detect_sentiment(text)
        if sentiment is not None:
            reflection.sentiment = sentiment

        reflection.save()
        return reflection

    def delete_reflection(self, reflection_id):
        """
        Delete a reflection.

        Returns: True if deleted, False if not found.
        """
        reflection = self.get_reflection(reflection_id)
        if not reflection:
            return False
        reflection.delete()
        return True

    # ── Entity Retrieval ────────────────────────────────────

    def get_reflections_for_entity(self, entity):
        """Get all reflections attached to a specific entity."""
        ct = ContentType.objects.get_for_model(entity)
        return CosReflection.objects.filter(
            user=self.user,
            content_type=ct,
            object_id=entity.pk,
        )

    # ── Date-Based Retrieval ────────────────────────────────

    def get_reflections_for_date(self, date):
        """Get all reflections for a specific date."""
        return CosReflection.objects.filter(
            user=self.user,
            activity_date=date,
        )

    def get_reflections_for_date_range(self, start_date, end_date):
        """Get all reflections within a date range (inclusive)."""
        return CosReflection.objects.filter(
            user=self.user,
            activity_date__gte=start_date,
            activity_date__lte=end_date,
        )

    def get_recent_reflections(self, days=7, limit=20):
        """Get recent reflections within the last N days."""
        cutoff = dj_timezone.now().date() - dt.timedelta(days=days)
        return CosReflection.objects.filter(
            user=self.user,
            activity_date__gte=cutoff,
        )[:limit]

    # ── Activity Type Retrieval ────────────────────────────

    def get_reflections_by_type(self, activity_type, limit=20):
        """Get reflections for a specific activity type."""
        return CosReflection.objects.filter(
            user=self.user,
            activity_type=activity_type,
        )[:limit]

    def get_active_types(self, days=30):
        """
        Get activity types the user has reflected on recently.

        Returns: list of (activity_type, count) tuples, ordered by count desc.
        """
        cutoff = dj_timezone.now().date() - dt.timedelta(days=days)
        return list(
            CosReflection.objects.filter(
                user=self.user,
                activity_date__gte=cutoff,
            )
            .exclude(activity_type="")
            .values("activity_type")
            .annotate(count=Count("id"))
            .order_by("-count")
            .values_list("activity_type", "count")
        )

    # ── Temporal Comparison Queries ─────────────────────────

    def get_yesterday_vs_today(self):
        """
        Compare yesterday's reflections with today's.

        Returns dict with "yesterday" and "today" reflection lists,
        plus "yesterday_sentiment" and "today_sentiment" summaries.

        Used for contextual prompts:
        "Yesterday you felt exhausted after your workout — how was today?"
        """
        today = dj_timezone.now().date()
        yesterday = today - dt.timedelta(days=1)

        yesterday_refs = list(
            CosReflection.objects.filter(
                user=self.user, activity_date=yesterday,
            )
        )
        today_refs = list(
            CosReflection.objects.filter(
                user=self.user, activity_date=today,
            )
        )

        return {
            "yesterday": yesterday_refs,
            "today": today_refs,
            "yesterday_sentiment": self._aggregate_sentiment(yesterday_refs),
            "today_sentiment": self._aggregate_sentiment(today_refs),
            "yesterday_date": yesterday,
            "today_date": today,
        }

    def get_this_week_vs_last_week(self):
        """
        Compare this week's reflections with last week's.

        Returns dict with "this_week" and "last_week" reflection lists,
        plus sentiment summaries and counts by activity type.

        Used for weekly pattern insights.
        """
        today = dj_timezone.now().date()
        # Monday = start of week
        week_start = today - dt.timedelta(days=today.weekday())
        last_week_start = week_start - dt.timedelta(days=7)

        this_week_refs = list(
            CosReflection.objects.filter(
                user=self.user,
                activity_date__gte=week_start,
                activity_date__lte=today,
            )
        )
        last_week_refs = list(
            CosReflection.objects.filter(
                user=self.user,
                activity_date__gte=last_week_start,
                activity_date__lt=week_start,
            )
        )

        return {
            "this_week": this_week_refs,
            "last_week": last_week_refs,
            "this_week_sentiment": self._aggregate_sentiment(this_week_refs),
            "last_week_sentiment": self._aggregate_sentiment(last_week_refs),
            "this_week_types": self._count_types(this_week_refs),
            "last_week_types": self._count_types(last_week_refs),
            "this_week_start": week_start,
            "last_week_start": last_week_start,
        }

    def get_streak_reflections(self, activity_type, days=14):
        """
        Get consecutive-day reflections for a specific activity type.

        Returns: list of (date, reflections) tuples for consecutive days,
        plus streak_length (longest current streak).

        Used for streak detection and encouragement:
        "You've reflected on workouts 5 days in a row — nice consistency!"
        """
        cutoff = dj_timezone.now().date() - dt.timedelta(days=days)
        reflections = list(
            CosReflection.objects.filter(
                user=self.user,
                activity_type=activity_type,
                activity_date__gte=cutoff,
            ).order_by("activity_date")
        )

        if not reflections:
            return {"streak_length": 0, "dates": [], "reflections": []}

        # Group by date
        date_groups = {}
        for r in reflections:
            date_groups.setdefault(r.activity_date, []).append(r)

        # Find current streak (consecutive days ending today or yesterday)
        sorted_dates = sorted(date_groups.keys(), reverse=True)
        today = dj_timezone.now().date()
        streak_length = 0
        streak_dates = []

        for i, d in enumerate(sorted_dates):
            expected = today - dt.timedelta(days=i)
            # Allow streak to start from yesterday (haven't reflected today yet)
            if i == 0 and d == today - dt.timedelta(days=1):
                expected = today - dt.timedelta(days=1)
                # Re-check from yesterday
                for j, d2 in enumerate(sorted_dates):
                    expected2 = (today - dt.timedelta(days=1)) - dt.timedelta(days=j)
                    if d2 == expected2:
                        streak_length = j + 1
                        streak_dates.append(d2)
                    else:
                        break
                break
            elif d == expected:
                streak_length = i + 1
                streak_dates.append(d)
            else:
                break

        return {
            "streak_length": streak_length,
            "dates": streak_dates,
            "reflections": reflections,
            "date_groups": date_groups,
        }

    def get_sentiment_trend(self, activity_type="", days=30):
        """
        Get sentiment distribution over time for a given activity type.

        Returns: dict with daily_sentiments (date→sentiment), overall distribution,
        and trend direction (improving, declining, stable).

        Used for pattern detection (Phase 6) and weekly summaries.
        """
        cutoff = dj_timezone.now().date() - dt.timedelta(days=days)
        qs = CosReflection.objects.filter(
            user=self.user,
            activity_date__gte=cutoff,
        )
        if activity_type:
            qs = qs.filter(activity_type=activity_type)

        reflections = list(qs.order_by("activity_date"))
        if not reflections:
            return {
                "trend": "no_data",
                "distribution": {},
                "daily_sentiments": {},
                "total": 0,
            }

        # Daily sentiment (latest per day)
        daily_sentiments = {}
        for r in reflections:
            daily_sentiments[r.activity_date] = r.sentiment

        # Overall distribution
        distribution = Counter(r.sentiment for r in reflections)

        # Trend detection — compare first half vs second half
        mid = len(reflections) // 2
        if mid > 0:
            first_half = reflections[:mid]
            second_half = reflections[mid:]
            first_score = self._sentiment_score(first_half)
            second_score = self._sentiment_score(second_half)
            diff = second_score - first_score
            if diff > 0.2:
                trend = "improving"
            elif diff < -0.2:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return {
            "trend": trend,
            "distribution": dict(distribution),
            "daily_sentiments": daily_sentiments,
            "total": len(reflections),
        }

    # ── Contextual Retrieval for Prompts ────────────────────

    def get_context_for_prompt(self, source_entity, activity_type=""):
        """
        Get contextual reflection data to enrich a prompt.

        Pulls yesterday's reflections for the same activity type,
        recent entity reflections, and overall sentiment trend.

        Returns dict suitable for template rendering:
        {
            "has_context": bool,
            "yesterday_reflection": str or None,
            "yesterday_sentiment": str or None,
            "recent_streak": int,
            "sentiment_trend": str,
            "related_reflections": list,
        }
        """
        today = dj_timezone.now().date()
        yesterday = today - dt.timedelta(days=1)

        context = {
            "has_context": False,
            "yesterday_reflection": None,
            "yesterday_sentiment": None,
            "recent_streak": 0,
            "sentiment_trend": "no_data",
            "related_reflections": [],
        }

        # Yesterday's reflection for same activity type
        if activity_type:
            yesterday_ref = (
                CosReflection.objects.filter(
                    user=self.user,
                    activity_type=activity_type,
                    activity_date=yesterday,
                )
                .first()
            )
            if yesterday_ref:
                context["yesterday_reflection"] = yesterday_ref.text
                context["yesterday_sentiment"] = yesterday_ref.sentiment
                context["has_context"] = True

            # Streak
            streak = self.get_streak_reflections(activity_type, days=14)
            context["recent_streak"] = streak["streak_length"]

            # Trend
            trend = self.get_sentiment_trend(activity_type, days=14)
            context["sentiment_trend"] = trend["trend"]

        # Related reflections for this entity (if entity already has reflections)
        ct = ContentType.objects.get_for_model(source_entity)
        related = list(
            CosReflection.objects.filter(
                user=self.user,
                content_type=ct,
                object_id=source_entity.pk,
            )[:5]
        )
        if related:
            context["related_reflections"] = related
            context["has_context"] = True

        return context

    def get_related_reflections(self, activity_type, days_back=7, limit=10):
        """
        Get recent reflections of the same activity type.

        Used for enriching prompts and pattern detection.
        """
        cutoff = dj_timezone.now().date() - dt.timedelta(days=days_back)
        return CosReflection.objects.filter(
            user=self.user,
            activity_type=activity_type,
            activity_date__gte=cutoff,
        )[:limit]

    def build_contextual_prompt_prefix(self, activity_type):
        """
        Build a context-aware prefix for prompts based on recent reflections.

        Examples:
        - "Yesterday you said your workout was 'exhausting but rewarding'."
        - "You've been consistent with prayer for 5 days — nice streak!"
        - "Your workout sentiment has been improving this week."

        Returns: str prefix or empty string if no context.
        """
        parts = []
        today = dj_timezone.now().date()
        yesterday = today - dt.timedelta(days=1)

        # Yesterday's reflection
        yesterday_ref = (
            CosReflection.objects.filter(
                user=self.user,
                activity_type=activity_type,
                activity_date=yesterday,
            )
            .first()
        )
        if yesterday_ref:
            # Truncate for prefix
            snippet = yesterday_ref.text[:100]
            if len(yesterday_ref.text) > 100:
                snippet += "..."
            parts.append(
                'Yesterday you said: "{}"'.format(snippet)
            )

        # Streak (only if >= 3 days)
        streak = self.get_streak_reflections(activity_type, days=14)
        if streak["streak_length"] >= 3:
            type_label = activity_type.replace("_", " ")
            parts.append(
                "You've reflected on {} for {} days in a row.".format(
                    type_label, streak["streak_length"],
                )
            )

        # Sentiment trend (only if clear improving or declining)
        trend = self.get_sentiment_trend(activity_type, days=14)
        if trend["trend"] == "improving":
            type_label = activity_type.replace("_", " ")
            parts.append(
                "Your {} reflections have been trending more positive lately.".format(
                    type_label,
                )
            )
        elif trend["trend"] == "declining":
            type_label = activity_type.replace("_", " ")
            parts.append(
                "Your recent {} reflections suggest things have been tough.".format(
                    type_label,
                )
            )

        return " ".join(parts)

    # ── SLCME Integration ──────────────────────────────────

    def _store_in_slcme(self, reflection):
        """
        Store reflection context in SLCME for long-term memory.

        Uses store_context_snapshot to record the latest reflection
        per activity type, enabling contextual resolution.
        """
        try:
            from apps.core.ai_memory import store_context_snapshot

            metadata = {
                "text": reflection.text[:200],  # Truncate for snapshot
                "sentiment": reflection.sentiment,
                "activity_date": str(reflection.activity_date),
                "reflection_id": reflection.pk,
            }

            context_identifier = "{}:{}".format(
                reflection.activity_type or "general",
                reflection.activity_date,
            )

            store_context_snapshot(
                user=self.user,
                context_type="cos_reflection",
                context_identifier=context_identifier,
                metadata=metadata,
            )
        except ImportError:
            logger.debug("SLCME not available — reflection stored in-model only")
        except Exception as e:
            logger.debug("SLCME storage failed (non-fatal): %s", e)

    def get_reflection_memory(self, activity_type):
        """
        Get SLCME-enriched context for an activity type.

        Falls back to direct DB query if SLCME unavailable.
        """
        try:
            from apps.core.ai_memory import get_current_context

            snapshot = get_current_context(
                user=self.user,
                context_type="cos_reflection",
            )
            if snapshot and snapshot.metadata:
                return {
                    "source": "slcme",
                    "text": snapshot.metadata.get("text", ""),
                    "sentiment": snapshot.metadata.get("sentiment", ""),
                    "activity_date": snapshot.metadata.get("activity_date", ""),
                }
        except ImportError:
            pass
        except Exception as e:
            logger.debug("SLCME retrieval failed: %s", e)

        # Fallback: direct query
        latest = (
            CosReflection.objects.filter(
                user=self.user,
                activity_type=activity_type,
            )
            .first()
        )
        if latest:
            return {
                "source": "direct",
                "text": latest.text[:200],
                "sentiment": latest.sentiment,
                "activity_date": str(latest.activity_date),
            }
        return None

    # ── Summary / Stats ─────────────────────────────────────

    def get_reflection_stats(self, days=30):
        """
        Get summary stats for a user's reflections.

        Returns: dict with total, by_type, by_sentiment, average_per_day.
        """
        cutoff = dj_timezone.now().date() - dt.timedelta(days=days)
        reflections = CosReflection.objects.filter(
            user=self.user,
            activity_date__gte=cutoff,
        )

        total = reflections.count()
        by_type = dict(
            reflections.exclude(activity_type="")
            .values_list("activity_type")
            .annotate(count=Count("id"))
            .values_list("activity_type", "count")
        )
        by_sentiment = dict(
            reflections.exclude(sentiment="")
            .values_list("sentiment")
            .annotate(count=Count("id"))
            .values_list("sentiment", "count")
        )

        # Active days (days with at least one reflection)
        active_days = (
            reflections.values("activity_date")
            .distinct()
            .count()
        )

        return {
            "total": total,
            "by_type": by_type,
            "by_sentiment": by_sentiment,
            "active_days": active_days,
            "avg_per_day": round(total / max(active_days, 1), 1),
            "period_days": days,
        }

    # ── Private Helpers ─────────────────────────────────────

    @staticmethod
    def _aggregate_sentiment(reflections):
        """Get the dominant sentiment from a list of reflections."""
        if not reflections:
            return "no_data"
        sentiments = [r.sentiment for r in reflections if r.sentiment]
        if not sentiments:
            return "neutral"
        counter = Counter(sentiments)
        return counter.most_common(1)[0][0]

    @staticmethod
    def _count_types(reflections):
        """Count reflections by activity type."""
        counter = Counter(r.activity_type for r in reflections if r.activity_type)
        return dict(counter)

    @staticmethod
    def _sentiment_score(reflections):
        """
        Calculate a numeric sentiment score for trend comparison.

        positive=1.0, neutral=0.5, negative=0.0, mixed=0.5
        """
        scores = {
            "positive": 1.0,
            "neutral": 0.5,
            "negative": 0.0,
            "mixed": 0.5,
        }
        if not reflections:
            return 0.5
        total = sum(scores.get(r.sentiment, 0.5) for r in reflections)
        return total / len(reflections)
