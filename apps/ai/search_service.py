"""
Search Service for AI Assistant

Provides unified search across all WLJ modules with standardized result format.
Part of Task 9.1: Search Service Infrastructure.

Each search method returns:
{
    "module": "journal",
    "count": 5,
    "results": [
        {
            "id": 123,
            "title": "Entry title or summary",
            "snippet": "Matching text excerpt...",
            "date": "2026-01-15",
            "url": "/journal/entry/123/",
            "metadata": {}  # Module-specific extra data
        }
    ]
}
"""

import logging
from datetime import date
from typing import Dict, List, Optional, Tuple
from django.db.models import Q
from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)


class SearchService:
    """
    Unified search service for all WLJ modules.

    Provides keyword-based search with optional filters for date ranges,
    status, and module-specific parameters.
    """

    def __init__(self, user):
        self.user = user

    def _safe_reverse(self, view_name: str, args: Optional[list] = None) -> Optional[str]:
        """Reverse a named URL for a search result's `url`, NEVER fatally.

        A search result's URL is PRESENTATION only — a renamed or removed view must
        never crash a deterministic TRUTH read (the shared historical-search path is a
        truth surface the Chief of Staff reasons over). On failure we log the exact
        view (visible in production, not swallowed) and return None so the truth result
        is preserved with `url=None`. This eliminates the URL-rot crash CLASS across
        every searchable domain, not just the one that surfaced it.
        (Origin: `health:food_log` was renamed; NoReverseMatch turned the entire
        food-history tool call into status="error", so "when did I eat pizza?" reached
        the model as an error instead of the real record — 2026-07-19.)
        """
        try:
            return reverse(view_name, args=args) if args else reverse(view_name)
        except NoReverseMatch:
            logger.warning(
                "SearchService: result URL reverse failed for %r (args=%r); "
                "returning url=None (truth preserved). Fix the stale view name.",
                view_name, args,
            )
            return None

    def _create_result(
        self,
        id: int,
        title: str,
        snippet: str,
        date_value: Optional[date],
        url: str,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """Create a standardized result dict."""
        return {
            "id": id,
            "title": title,
            "snippet": self._truncate_snippet(snippet),
            "date": date_value.isoformat() if date_value else None,
            "url": url,
            "metadata": metadata or {}
        }

    def _truncate_snippet(self, text: str, max_length: int = 150) -> str:
        """Truncate text to max_length, preserving word boundaries."""
        if not text:
            return ""
        text = text.strip()
        if len(text) <= max_length:
            return text
        truncated = text[:max_length].rsplit(' ', 1)[0]
        return truncated + "..."

    def _build_keyword_filter(
        self,
        keywords: List[str],
        fields: List[str]
    ) -> Q:
        """
        Build a Q filter that matches any keyword in any field.

        Args:
            keywords: List of search terms
            fields: List of field names to search (e.g., ['title', 'body'])

        Returns:
            Q object for filtering
        """
        if not keywords:
            return Q()

        q_filter = Q()
        for keyword in keywords:
            keyword = keyword.strip().lower()
            if not keyword:
                continue
            for field in fields:
                q_filter |= Q(**{f"{field}__icontains": keyword})
        return q_filter

    def _parse_date_range(
        self,
        date_range: Optional[Tuple[date, date]]
    ) -> Tuple[Optional[date], Optional[date]]:
        """Parse and validate date range."""
        if not date_range:
            return None, None
        start, end = date_range
        return start, end

    # -------------------------------------------------------------------------
    # JOURNAL SEARCH
    # -------------------------------------------------------------------------

    def search_journal(
        self,
        keywords: Optional[List[str]] = None,
        date_range: Optional[Tuple[date, date]] = None,
        mood: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10
    ) -> Dict:
        """
        Search journal entries.

        Args:
            keywords: Search terms for title and body
            date_range: Tuple of (start_date, end_date)
            mood: Filter by mood (great, good, okay, low, difficult)
            tags: Filter by tag names
            limit: Maximum results

        Returns:
            Standardized search results dict
        """
        from apps.journal.models import JournalEntry

        entries = JournalEntry.objects.filter(user=self.user)

        # Apply keyword filter
        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['title', 'body_plain'])
            entries = entries.filter(keyword_q)

        # Apply date range filter
        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(entry_date__gte=start_date)
        if end_date:
            entries = entries.filter(entry_date__lte=end_date)

        # Apply mood filter
        if mood:
            entries = entries.filter(mood=mood)

        # Apply tags filter
        if tags:
            for tag in tags:
                entries = entries.filter(tags__name__iexact=tag)

        # Order and limit
        entries = entries.order_by('-entry_date')[:limit]

        results = []
        for entry in entries:
            results.append(self._create_result(
                id=entry.pk,
                title=entry.title or f"Journal Entry - {entry.entry_date}",
                snippet=entry.body_plain[:200] if entry.body_plain else "",
                date_value=entry.entry_date,
                url=self._safe_reverse('journal:entry_detail', args=[entry.pk]),
                metadata={
                    "mood": entry.mood,
                    "word_count": entry.word_count
                }
            ))

        return {
            "module": "journal",
            "count": len(results),
            "results": results
        }

    # -------------------------------------------------------------------------
    # HEALTH SEARCH
    # -------------------------------------------------------------------------

    def search_health(
        self,
        keywords: Optional[List[str]] = None,
        metric_type: Optional[str] = None,
        date_range: Optional[Tuple[date, date]] = None,
        limit: int = 10
    ) -> Dict:
        """
        Search health data across multiple metric types.

        Args:
            keywords: Search terms (mainly for notes fields)
            metric_type: Specific metric type to search:
                weight, sleep, blood_pressure, food, workout, fasting,
                heart_rate, steps, water, glucose, blood_oxygen, medicine,
                mobility, heart_rate_events, audio_exposure, dietary_nutrients
            date_range: Tuple of (start_date, end_date)
            limit: Maximum results

        Returns:
            Standardized search results dict
        """
        results = []

        if metric_type:
            # Search specific metric type
            method_name = f"_search_health_{metric_type}"
            if hasattr(self, method_name):
                results = getattr(self, method_name)(keywords, date_range, limit)
        else:
            # Search all health data types, combine results
            per_type_limit = max(2, limit // 12)
            for mtype in [
                'weight', 'sleep', 'food', 'workout', 'fasting', 'medicine',
                'steps', 'heart_rate', 'blood_pressure', 'glucose',
                'blood_oxygen', 'water', 'mobility', 'heart_rate_events',
                'audio_exposure', 'dietary_nutrients',
            ]:
                method_name = f"_search_health_{mtype}"
                if hasattr(self, method_name):
                    type_results = getattr(self, method_name)(
                        keywords, date_range, per_type_limit
                    )
                    results.extend(type_results)

        # Sort by date and limit
        results.sort(key=lambda x: x.get('date') or '', reverse=True)
        results = results[:limit]

        return {
            "module": "health",
            "count": len(results),
            "results": results
        }

    def search_nutrition(
        self,
        keywords: Optional[List[str]] = None,
        date_range: Optional[Tuple[date, date]] = None,
        limit: int = 10
    ) -> Dict:
        """Historical-search adapter for the NUTRITION domain (food log).

        Nutrition is a first-class truth domain (its own DomainTruth + capability-index
        entry), so it must be a first-class HISTORY-SEARCH domain too — otherwise the
        model, offered `nutrition` everywhere else, scopes a food-history search to it
        and gets `unsupported_domain`. This is a thin, explicit adapter that REUSES the
        canonical food search (`_search_health_food` via `search_health`, metric_type=
        'food'); no new search engine, no parallel index. It satisfies the same call
        contract every other registered domain does — `method(keywords=..., limit=...)`
        returning the standardized `{results: [...]}` shape.
        """
        out = self.search_health(
            keywords=keywords, metric_type="food",
            date_range=date_range, limit=limit,
        )
        return {
            "module": "nutrition",
            "count": out.get("count", 0),
            "results": out.get("results", []),
        }

    def _search_health_weight(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search weight entries."""
        from apps.health.models import WeightEntry

        entries = WeightEntry.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['notes'])
            entries = entries.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(recorded_at__date__gte=start_date)
        if end_date:
            entries = entries.filter(recorded_at__date__lte=end_date)

        entries = entries.order_by('-recorded_at')[:limit]

        results = []
        for entry in entries:
            results.append(self._create_result(
                id=entry.pk,
                title=f"Weight: {entry.value} {entry.unit}",
                snippet=entry.notes or "",
                date_value=entry.recorded_at.date(),
                url=self._safe_reverse('health:weight_list'),
                metadata={"metric_type": "weight", "value": float(entry.value), "unit": entry.unit}
            ))
        return results

    def _search_health_sleep(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search sleep entries."""
        from apps.health.models import SleepEntry

        entries = SleepEntry.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['notes'])
            entries = entries.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(sleep_date__gte=start_date)
        if end_date:
            entries = entries.filter(sleep_date__lte=end_date)

        entries = entries.order_by('-sleep_date')[:limit]

        results = []
        for entry in entries:
            duration_hrs = round(entry.asleep_duration_minutes / 60, 1) if entry.asleep_duration_minutes else 0
            results.append(self._create_result(
                id=entry.pk,
                title=f"Sleep: {duration_hrs} hours ({entry.quality or 'unrated'})",
                snippet=entry.notes or f"Slept {duration_hrs} hours on {entry.sleep_date}",
                date_value=entry.sleep_date,
                url=self._safe_reverse('health:sleep_list'),
                metadata={"metric_type": "sleep", "duration_hours": duration_hrs, "quality": entry.quality}
            ))
        return results

    def _search_health_food(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search food entries."""
        from apps.health.models import FoodEntry

        entries = FoodEntry.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['food_name', 'food_brand', 'notes'])
            entries = entries.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(logged_date__gte=start_date)
        if end_date:
            entries = entries.filter(logged_date__lte=end_date)

        entries = entries.order_by('-logged_date', '-logged_time')[:limit]

        results = []
        for entry in entries:
            results.append(self._create_result(
                id=entry.pk,
                title=f"{entry.food_name} ({entry.meal_type})",
                snippet=f"{entry.total_calories or 0} cal - {entry.notes or ''}".strip(),
                date_value=entry.logged_date,
                url=self._safe_reverse('health:food_entry_detail', args=[entry.pk]),
                metadata={
                    "metric_type": "food",
                    "meal_type": entry.meal_type,
                    "calories": float(entry.total_calories) if entry.total_calories else None
                }
            ))
        return results

    def _search_health_workout(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search workout sessions."""
        from apps.health.models import WorkoutSession

        sessions = WorkoutSession.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['name', 'notes'])
            sessions = sessions.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            sessions = sessions.filter(date__gte=start_date)
        if end_date:
            sessions = sessions.filter(date__lte=end_date)

        sessions = sessions.order_by('-date')[:limit]

        results = []
        for session in sessions:
            parts = []
            if session.workout_type:
                parts.append(session.workout_type)
            if session.duration_minutes:
                parts.append(f"{session.duration_minutes} min")
            if session.calories_burned:
                parts.append(f"{session.calories_burned} cal")
            if session.avg_heart_rate:
                parts.append(f"{session.avg_heart_rate} bpm avg HR")
            if session.distance_miles:
                parts.append(f"{float(session.distance_miles):.1f} mi")
            snippet = ', '.join(parts) if parts else (session.notes or "")
            metadata = {
                "metric_type": "workout",
                "name": session.name,
                "source": session.source,
            }
            if session.calories_burned:
                metadata["calories"] = session.calories_burned
            if session.avg_heart_rate:
                metadata["avg_heart_rate"] = session.avg_heart_rate
            if session.duration_minutes:
                metadata["duration_minutes"] = session.duration_minutes
            results.append(self._create_result(
                id=session.pk,
                title=f"Workout: {session.name or session.workout_type or 'Session'}",
                snippet=snippet,
                date_value=session.date,
                url=self._safe_reverse('health:workout_list'),
                metadata=metadata,
            ))
        return results

    def _search_health_fasting(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search fasting windows."""
        from apps.health.models import FastingWindow

        windows = FastingWindow.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['notes', 'fasting_type'])
            windows = windows.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            windows = windows.filter(started_at__date__gte=start_date)
        if end_date:
            windows = windows.filter(started_at__date__lte=end_date)

        windows = windows.order_by('-started_at')[:limit]

        results = []
        for window in windows:
            duration = ""
            if window.ended_at:
                hours = (window.ended_at - window.started_at).total_seconds() / 3600
                duration = f"{hours:.1f} hours"
            results.append(self._create_result(
                id=window.pk,
                title=f"Fast: {window.fasting_type}" + (f" ({duration})" if duration else " (in progress)"),
                snippet=window.notes or "",
                date_value=window.started_at.date(),
                url=self._safe_reverse('health:fasting_list'),
                metadata={"metric_type": "fasting", "fasting_type": window.fasting_type}
            ))
        return results

    def _search_health_medicine(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search medicine logs."""
        from apps.health.models import IntakeLog

        logs = IntakeLog.objects.filter(user=self.user).select_related('intake')

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['notes', 'intake__name'])
            logs = logs.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            logs = logs.filter(scheduled_date__gte=start_date)
        if end_date:
            logs = logs.filter(scheduled_date__lte=end_date)

        logs = logs.order_by('-scheduled_date', '-scheduled_time')[:limit]

        results = []
        for log in logs:
            results.append(self._create_result(
                id=log.pk,
                title=f"Medicine: {log.intake.name} ({log.log_status})",
                snippet=log.notes or "",
                date_value=log.scheduled_date,
                url=self._safe_reverse('health:intake_list'),
                metadata={"metric_type": "medicine", "status": log.log_status}
            ))
        return results

    def _search_health_steps(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search steps entries."""
        from apps.health.models import StepsEntry

        entries = StepsEntry.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['notes'])
            entries = entries.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(logged_date__gte=start_date)
        if end_date:
            entries = entries.filter(logged_date__lte=end_date)

        entries = entries.order_by('-logged_date')[:limit]

        results = []
        for entry in entries:
            parts = [f"{entry.count:,} steps"]
            if entry.distance_miles:
                parts.append(f"{entry.distance_miles:.1f} mi")
            if entry.exercise_minutes:
                parts.append(f"{entry.exercise_minutes} exercise min")
            results.append(self._create_result(
                id=entry.pk,
                title=f"Steps: {entry.count:,} on {entry.logged_date}",
                snippet=", ".join(parts),
                date_value=entry.logged_date,
                url=self._safe_reverse('health:steps_list'),
                metadata={"metric_type": "steps", "count": entry.count}
            ))
        return results

    def _search_health_heart_rate(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search heart rate entries."""
        from apps.health.models import HeartRateEntry

        entries = HeartRateEntry.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['notes'])
            entries = entries.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(recorded_at__date__gte=start_date)
        if end_date:
            entries = entries.filter(recorded_at__date__lte=end_date)

        entries = entries.order_by('-recorded_at')[:limit]

        results = []
        for entry in entries:
            context = f" ({entry.context})" if entry.context else ""
            results.append(self._create_result(
                id=entry.pk,
                title=f"Heart Rate: {entry.bpm} bpm{context}",
                snippet=entry.notes or f"{entry.bpm} bpm{context}",
                date_value=entry.recorded_at.date(),
                url=self._safe_reverse('health:heartrate_list'),
                metadata={"metric_type": "heart_rate", "bpm": entry.bpm, "context": entry.context}
            ))
        return results

    def _search_health_blood_pressure(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search blood pressure entries."""
        from apps.health.models import BloodPressureEntry

        entries = BloodPressureEntry.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['notes'])
            entries = entries.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(recorded_at__date__gte=start_date)
        if end_date:
            entries = entries.filter(recorded_at__date__lte=end_date)

        entries = entries.order_by('-recorded_at')[:limit]

        results = []
        for entry in entries:
            results.append(self._create_result(
                id=entry.pk,
                title=f"BP: {entry.systolic}/{entry.diastolic} mmHg",
                snippet=entry.notes or f"{entry.systolic}/{entry.diastolic} mmHg",
                date_value=entry.recorded_at.date(),
                url=self._safe_reverse('health:blood_pressure_list'),
                metadata={
                    "metric_type": "blood_pressure",
                    "systolic": entry.systolic,
                    "diastolic": entry.diastolic
                }
            ))
        return results

    def _search_health_glucose(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search glucose entries."""
        from apps.health.models import GlucoseEntry

        entries = GlucoseEntry.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['notes'])
            entries = entries.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(recorded_at__date__gte=start_date)
        if end_date:
            entries = entries.filter(recorded_at__date__lte=end_date)

        entries = entries.order_by('-recorded_at')[:limit]

        results = []
        for entry in entries:
            context = f" ({entry.context})" if entry.context else ""
            results.append(self._create_result(
                id=entry.pk,
                title=f"Glucose: {entry.value} {entry.unit}{context}",
                snippet=entry.notes or f"{entry.value} {entry.unit}{context}",
                date_value=entry.recorded_at.date(),
                url=self._safe_reverse('health:glucose_list'),
                metadata={
                    "metric_type": "glucose",
                    "value": float(entry.value),
                    "unit": entry.unit
                }
            ))
        return results

    def _search_health_blood_oxygen(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search blood oxygen entries."""
        from apps.health.models import BloodOxygenEntry

        entries = BloodOxygenEntry.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['notes'])
            entries = entries.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(recorded_at__date__gte=start_date)
        if end_date:
            entries = entries.filter(recorded_at__date__lte=end_date)

        entries = entries.order_by('-recorded_at')[:limit]

        results = []
        for entry in entries:
            results.append(self._create_result(
                id=entry.pk,
                title=f"SpO2: {entry.spo2}%",
                snippet=entry.notes or f"Blood Oxygen: {entry.spo2}%",
                date_value=entry.recorded_at.date(),
                url=self._safe_reverse('health:blood_oxygen_list'),
                metadata={"metric_type": "blood_oxygen", "spo2": entry.spo2}
            ))
        return results

    def _search_health_water(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search water entries."""
        from apps.health.models import WaterEntry

        entries = WaterEntry.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['notes'])
            entries = entries.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(logged_date__gte=start_date)
        if end_date:
            entries = entries.filter(logged_date__lte=end_date)

        entries = entries.order_by('-logged_date')[:limit]

        results = []
        for entry in entries:
            results.append(self._create_result(
                id=entry.pk,
                title=f"Water: {entry.amount} {entry.unit}",
                snippet=entry.notes or f"{entry.amount} {entry.unit} ({entry.container})",
                date_value=entry.logged_date,
                url=self._safe_reverse('health:water_list'),
                metadata={"metric_type": "water", "amount": float(entry.amount), "unit": entry.unit}
            ))
        return results

    def _search_health_mobility(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search mobility entries (walking asymmetry, steadiness, speed, etc.)."""
        from apps.health.models import MobilityEntry

        entries = MobilityEntry.objects.filter(user=self.user)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(metric_date__gte=start_date)
        if end_date:
            entries = entries.filter(metric_date__lte=end_date)

        entries = entries.order_by('-metric_date')[:limit]

        results = []
        for entry in entries:
            parts = []
            if entry.walking_speed is not None:
                parts.append(f"speed: {entry.walking_speed} m/s")
            if entry.walking_asymmetry is not None:
                parts.append(f"asymmetry: {entry.walking_asymmetry}%")
            if entry.walking_steadiness_score is not None:
                parts.append(f"steadiness: {entry.walking_steadiness_score}")
            snippet = ', '.join(parts) if parts else "Mobility data"
            results.append(self._create_result(
                id=entry.pk,
                title=f"Mobility ({entry.metric_date})",
                snippet=snippet,
                date_value=entry.metric_date,
                url=self._safe_reverse('health:home'),
                metadata={"metric_type": "mobility"}
            ))
        return results

    def _search_health_heart_rate_events(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search heart rate event entries (high HR, low HR, AFib)."""
        from apps.health.models import HeartRateEventEntry

        entries = HeartRateEventEntry.objects.filter(user=self.user)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(recorded_at__date__gte=start_date)
        if end_date:
            entries = entries.filter(recorded_at__date__lte=end_date)

        entries = entries.order_by('-recorded_at')[:limit]

        results = []
        for entry in entries:
            snippet = f"{entry.event_type}: {entry.heart_rate} bpm"
            if entry.threshold:
                snippet += f" (threshold: {entry.threshold} bpm)"
            results.append(self._create_result(
                id=entry.pk,
                title=f"HR Event: {entry.event_type} ({entry.recorded_at.strftime('%Y-%m-%d')})",
                snippet=snippet,
                date_value=entry.recorded_at.date(),
                url=self._safe_reverse('health:home'),
                metadata={"metric_type": "heart_rate_events", "event_type": entry.event_type}
            ))
        return results

    def _search_health_audio_exposure(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search audio exposure entries (headphone and environmental levels)."""
        from apps.health.models import AudioExposureEntry

        entries = AudioExposureEntry.objects.filter(user=self.user)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(metric_date__gte=start_date)
        if end_date:
            entries = entries.filter(metric_date__lte=end_date)

        entries = entries.order_by('-metric_date')[:limit]

        results = []
        for entry in entries:
            parts = []
            if entry.headphone_level_db is not None:
                parts.append(f"Headphone: {entry.headphone_level_db} dB")
            if entry.headphone_duration_minutes is not None:
                parts.append(f"{entry.headphone_duration_minutes} min")
            if entry.environmental_level_db is not None:
                parts.append(f"Environment: {entry.environmental_level_db} dB")
            results.append(self._create_result(
                id=entry.pk,
                title=f"Audio Exposure ({entry.metric_date})",
                snippet=', '.join(parts) if parts else "Audio data",
                date_value=entry.metric_date,
                url=self._safe_reverse('health:home'),
                metadata={"metric_type": "audio_exposure"}
            ))
        return results

    def _search_health_dietary_nutrients(
        self,
        keywords: Optional[List[str]],
        date_range: Optional[Tuple[date, date]],
        limit: int
    ) -> List[Dict]:
        """Search dietary nutrient entries from HealthKit."""
        from apps.health.models import DietaryNutrientEntry

        entries = DietaryNutrientEntry.objects.filter(user=self.user)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(metric_date__gte=start_date)
        if end_date:
            entries = entries.filter(metric_date__lte=end_date)

        entries = entries.order_by('-metric_date')[:limit]

        results = []
        for entry in entries:
            parts = []
            if entry.calories is not None:
                parts.append(f"{entry.calories} cal")
            if entry.protein_g is not None:
                parts.append(f"{entry.protein_g}g protein")
            if entry.carbohydrates_g is not None:
                parts.append(f"{entry.carbohydrates_g}g carbs")
            if entry.fat_g is not None:
                parts.append(f"{entry.fat_g}g fat")
            results.append(self._create_result(
                id=entry.pk,
                title=f"Nutrients ({entry.metric_date})",
                snippet=', '.join(parts) if parts else "Dietary data",
                date_value=entry.metric_date,
                url=self._safe_reverse('health:home'),
                metadata={"metric_type": "dietary_nutrients"}
            ))
        return results

    # -------------------------------------------------------------------------
    # GOALS/PURPOSE SEARCH
    # -------------------------------------------------------------------------

    def search_goals(
        self,
        keywords: Optional[List[str]] = None,
        status: Optional[str] = None,
        limit: int = 10
    ) -> Dict:
        """
        Search life goals and milestones.

        Args:
            keywords: Search terms for title, description, why_it_matters
            status: Filter by status (active, paused, completed, released)
            limit: Maximum results

        Returns:
            Standardized search results dict
        """
        from apps.purpose.models import LifeGoal

        # Search goals
        goals = LifeGoal.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(
                keywords,
                ['title', 'description_plain', 'why_it_matters_plain', 'success_looks_like_plain']
            )
            goals = goals.filter(keyword_q)

        if status:
            goals = goals.filter(status=status)

        goals = goals.select_related('domain').order_by('-created_at')[:limit]

        results = []
        for goal in goals:
            milestone_info = ""
            if goal.milestone_count > 0:
                milestone_info = f" ({goal.completed_milestone_count}/{goal.milestone_count} milestones)"
            results.append(self._create_result(
                id=goal.pk,
                title=f"{goal.title}{milestone_info}",
                snippet=goal.description_plain or goal.why_it_matters_plain or "",
                date_value=goal.target_date,
                url=self._safe_reverse('purpose:goal_detail', args=[goal.pk]),
                metadata={
                    "status": goal.status,
                    "domain": goal.domain.name if goal.domain else None,
                    "progress_percent": goal.milestone_progress_percent
                }
            ))

        return {
            "module": "purpose",
            "count": len(results),
            "results": results
        }

    # -------------------------------------------------------------------------
    # FAITH SEARCH
    # -------------------------------------------------------------------------

    def search_faith(
        self,
        keywords: Optional[List[str]] = None,
        content_type: Optional[str] = None,
        limit: int = 10
    ) -> Dict:
        """
        Search faith content: prayers, scriptures, reading plans.

        Args:
            keywords: Search terms
            content_type: Filter by type (prayer, scripture, reading_plan, milestone)
            limit: Maximum results

        Returns:
            Standardized search results dict
        """
        results = []

        if content_type:
            # Search specific content type
            method_name = f"_search_faith_{content_type}"
            if hasattr(self, method_name):
                results = getattr(self, method_name)(keywords, limit)
        else:
            # Search all faith content types (study_note included so a notes query is not
            # answered with reading plans while the notes stay invisible — Faith cert, prod).
            per_type_limit = max(2, limit // 5)
            for ctype in ['prayer', 'scripture', 'reading_plan', 'milestone', 'study_note']:
                method_name = f"_search_faith_{ctype}"
                if hasattr(self, method_name):
                    type_results = getattr(self, method_name)(keywords, per_type_limit)
                    results.extend(type_results)

        # Sort by date and limit
        results.sort(key=lambda x: x.get('date') or '', reverse=True)
        results = results[:limit]

        return {
            "module": "faith",
            "count": len(results),
            "results": results
        }

    def _search_faith_prayer(
        self,
        keywords: Optional[List[str]],
        limit: int
    ) -> List[Dict]:
        """Search prayer requests."""
        from apps.faith.models import PrayerRequest

        prayers = PrayerRequest.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(
                keywords,
                ['title', 'description_plain', 'person_or_situation', 'answer_notes_plain']
            )
            prayers = prayers.filter(keyword_q)

        prayers = prayers.order_by('-created_at')[:limit]

        results = []
        for prayer in prayers:
            status = "Answered" if prayer.is_answered else "Active"
            results.append(self._create_result(
                id=prayer.pk,
                title=f"Prayer: {prayer.title} ({status})",
                snippet=prayer.description_plain or "",
                date_value=prayer.created_at.date(),
                url=self._safe_reverse('faith:prayer_detail', args=[prayer.pk]),
                metadata={
                    "content_type": "prayer",
                    "is_answered": prayer.is_answered,
                    "priority": prayer.priority
                }
            ))
        return results

    def _search_faith_scripture(
        self,
        keywords: Optional[List[str]],
        limit: int
    ) -> List[Dict]:
        """Search saved verses."""
        from apps.faith.models import SavedVerse

        verses = SavedVerse.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(
                keywords,
                ['reference', 'text', 'notes']
            )
            verses = verses.filter(keyword_q)

        verses = verses.order_by('-created_at')[:limit]

        results = []
        for verse in verses:
            results.append(self._create_result(
                id=verse.pk,
                title=f"Scripture: {verse.reference}",
                snippet=verse.text[:200] if verse.text else "",
                date_value=verse.created_at.date(),
                url=self._safe_reverse('faith:scripture_list'),
                metadata={
                    "content_type": "scripture",
                    "translation": verse.translation,
                    "is_memory_verse": verse.is_memory_verse
                }
            ))
        return results

    def _search_faith_reading_plan(
        self,
        keywords: Optional[List[str]],
        limit: int
    ) -> List[Dict]:
        """Search user's reading plans."""
        from apps.faith.models import UserReadingPlan

        plans = UserReadingPlan.objects.filter(user=self.user).select_related('template')

        if keywords:
            # Match the plan's NAME only, NOT its (marketing) description. Plan descriptions
            # contain generic devotional language ("a study through the Bible", "family
            # preserved") that false-matched unrelated faith searches — a reading plan was
            # substituted for a study-notes query, and "Noah" surfaced in a family-prayer
            # search (Faith cert, prod). Users refer to a plan by its title.
            keyword_q = self._build_keyword_filter(keywords, ['template__title'])
            plans = plans.filter(keyword_q)

        plans = plans.order_by('-started_at')[:limit]

        results = []
        for plan in plans:
            progress = f"Day {plan.current_day}/{plan.template.duration_days}"
            results.append(self._create_result(
                id=plan.pk,
                title=f"Reading Plan: {plan.template.title} ({progress})",
                snippet=plan.template.description or "",
                date_value=plan.started_at.date(),
                url=self._safe_reverse('faith:reading_plan_progress', args=[plan.pk]),
                metadata={
                    "content_type": "reading_plan",
                    "status": plan.plan_status,
                    "progress_day": plan.current_day,
                    "total_days": plan.template.duration_days
                }
            ))
        return results

    def _search_faith_milestone(
        self,
        keywords: Optional[List[str]],
        limit: int
    ) -> List[Dict]:
        """Search faith milestones."""
        from apps.faith.models import FaithMilestone

        milestones = FaithMilestone.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(
                keywords,
                ['title', 'description_plain', 'scripture_reference']
            )
            milestones = milestones.filter(keyword_q)

        milestones = milestones.order_by('-date')[:limit]

        results = []
        for milestone in milestones:
            results.append(self._create_result(
                id=milestone.pk,
                title=f"Faith Milestone: {milestone.title}",
                snippet=milestone.description_plain or "",
                date_value=milestone.date,
                url=self._safe_reverse('faith:milestone_list'),
                metadata={
                    "content_type": "milestone",
                    "milestone_type": milestone.milestone_type
                }
            ))
        return results

    def _search_faith_study_note(
        self,
        keywords: Optional[List[str]],
        limit: int
    ) -> List[Dict]:
        """Search Bible study notes. Previously ABSENT — 'show my Bible study notes' matched
        reading-plan descriptions (which contain 'study'/'Bible') and returned reading plans
        while the actual notes stayed invisible to search (Faith cert, prod)."""
        from apps.faith.models import BibleStudyNote

        notes = BibleStudyNote.objects.filter(user=self.user)
        if keywords:
            notes = notes.filter(self._build_keyword_filter(
                keywords, ['title', 'content_plain', 'reference']))
        notes = notes.order_by('-created_at')[:limit]

        results = []
        for note in notes:
            title = note.title or f"Note on {note.reference}"
            results.append(self._create_result(
                id=note.pk,
                title=f"Study Note: {title}",
                snippet=(note.content_plain or "")[:200],
                date_value=note.created_at.date(),
                url=self._safe_reverse('faith:study_note_detail', args=[note.pk]),
                metadata={"content_type": "study_note", "reference": note.reference},
            ))
        return results

    def _search_faith_highlight(
        self,
        keywords: Optional[List[str]],
        limit: int
    ) -> List[Dict]:
        """Search Bible highlights (was absent from faith search)."""
        from apps.faith.models import BibleHighlight

        hls = BibleHighlight.objects.filter(user=self.user)
        if keywords:
            hls = hls.filter(self._build_keyword_filter(keywords, ['reference', 'text']))
        hls = hls.order_by('book_order', 'chapter', 'verse_start')[:limit]

        results = []
        for h in hls:
            results.append(self._create_result(
                id=h.pk,
                title=f"Highlight: {h.reference}",
                snippet=(h.text or "")[:200],
                date_value=h.created_at.date() if h.created_at else None,
                url=self._safe_reverse('faith:highlight_list'),
                metadata={"content_type": "highlight", "color": h.color},
            ))
        return results

    def _search_faith_bookmark(
        self,
        keywords: Optional[List[str]],
        limit: int
    ) -> List[Dict]:
        """Search Bible bookmarks (was absent from faith search)."""
        from apps.faith.models import BibleBookmark

        bms = BibleBookmark.objects.filter(user=self.user)
        if keywords:
            bms = bms.filter(self._build_keyword_filter(
                keywords, ['reference', 'title', 'notes']))
        bms = bms.order_by('-created_at')[:limit]

        results = []
        for b in bms:
            results.append(self._create_result(
                id=b.pk,
                title=f"Bookmark: {b.title or b.reference}",
                snippet=(b.notes or "")[:200],
                date_value=b.created_at.date() if b.created_at else None,
                url=self._safe_reverse('faith:bookmark_list'),
                metadata={"content_type": "bookmark", "reference": b.reference},
            ))
        return results

    # -------------------------------------------------------------------------
    # ORGANIZE (formerly Life) SEARCH
    # -------------------------------------------------------------------------

    def search_organize(
        self,
        keywords: Optional[List[str]] = None,
        item_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10
    ) -> Dict:
        """
        Search Organize module: tasks, projects, events, inventory.

        Args:
            keywords: Search terms
            item_type: Filter by type (task, project, event, inventory)
            status: Filter by status (varies by type)
            limit: Maximum results

        Returns:
            Standardized search results dict
        """
        results = []

        if item_type:
            # Search specific item type
            method_name = f"_search_organize_{item_type}"
            if hasattr(self, method_name):
                results = getattr(self, method_name)(keywords, status, limit)
        else:
            # Search all organize item types
            per_type_limit = max(2, limit // 4)
            for itype in ['task', 'project', 'event', 'inventory']:
                method_name = f"_search_organize_{itype}"
                if hasattr(self, method_name):
                    type_results = getattr(self, method_name)(keywords, status, per_type_limit)
                    results.extend(type_results)

        # Sort by date and limit
        results.sort(key=lambda x: x.get('date') or '', reverse=True)
        results = results[:limit]

        return {
            "module": "organize",
            "count": len(results),
            "results": results
        }

    def _search_organize_task(
        self,
        keywords: Optional[List[str]],
        status: Optional[str],
        limit: int
    ) -> List[Dict]:
        """Search tasks."""
        from apps.life.models import Task

        tasks = Task.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(keywords, ['title', 'notes'])
            tasks = tasks.filter(keyword_q)

        if status == 'completed':
            tasks = tasks.filter(completion_status='completed')
        elif status == 'incomplete':
            tasks = tasks.filter(completion_status='pending')

        tasks = tasks.order_by('-created_at')[:limit]

        results = []
        for task in tasks:
            status_text = "Completed" if task.is_completed else task.priority.title()
            results.append(self._create_result(
                id=task.pk,
                title=f"Task: {task.title} ({status_text})",
                snippet=task.notes or "",
                date_value=task.due_date,
                url=self._safe_reverse('life:task_update', args=[task.pk]),
                metadata={
                    "item_type": "task",
                    "is_completed": task.is_completed,
                    "priority": task.priority
                }
            ))
        return results

    def _search_organize_project(
        self,
        keywords: Optional[List[str]],
        status: Optional[str],
        limit: int
    ) -> List[Dict]:
        """Search projects."""
        from apps.life.models import Project

        projects = Project.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(
                keywords,
                ['title', 'description_plain', 'purpose_plain']
            )
            projects = projects.filter(keyword_q)

        if status:
            projects = projects.filter(status=status)

        projects = projects.order_by('-created_at')[:limit]

        results = []
        for project in projects:
            results.append(self._create_result(
                id=project.pk,
                title=f"Project: {project.title} ({project.status.title()})",
                snippet=project.description_plain or project.purpose_plain or "",
                date_value=project.target_date,
                url=self._safe_reverse('life:project_detail', args=[project.pk]),
                metadata={
                    "item_type": "project",
                    "status": project.status,
                    "priority": project.priority
                }
            ))
        return results

    def _search_organize_event(
        self,
        keywords: Optional[List[str]],
        status: Optional[str],
        limit: int
    ) -> List[Dict]:
        """Search events."""
        from apps.life.models import LifeEvent

        events = LifeEvent.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(
                keywords,
                ['title', 'description', 'location']
            )
            events = events.filter(keyword_q)

        events = events.order_by('-start_date')[:limit]

        results = []
        for event in events:
            results.append(self._create_result(
                id=event.pk,
                title=f"Event: {event.title}",
                snippet=event.description or event.location or "",
                date_value=event.start_date,
                url=self._safe_reverse('life:event_update', args=[event.pk]),
                metadata={
                    "item_type": "event",
                    "event_type": event.event_type,
                    "location": event.location
                }
            ))
        return results

    def _search_organize_inventory(
        self,
        keywords: Optional[List[str]],
        status: Optional[str],
        limit: int
    ) -> List[Dict]:
        """Search inventory items."""
        from apps.life.models import InventoryItem

        items = InventoryItem.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(
                keywords,
                ['name', 'description', 'brand', 'location', 'notes']
            )
            items = items.filter(keyword_q)

        items = items.order_by('-created_at')[:limit]

        results = []
        for item in items:
            results.append(self._create_result(
                id=item.pk,
                title=f"Inventory: {item.name}",
                snippet=item.description or f"Location: {item.location}" if item.location else "",
                date_value=item.purchase_date,
                url=self._safe_reverse('life:inventory_detail', args=[item.pk]),
                metadata={
                    "item_type": "inventory",
                    "category": item.category,
                    "location": item.location,
                    "condition": item.condition
                }
            ))
        return results

    # -------------------------------------------------------------------------
    # FINANCE SEARCH
    # -------------------------------------------------------------------------

    def search_finance(
        self,
        keywords: Optional[List[str]] = None,
        transaction_type: Optional[str] = None,
        date_range: Optional[Tuple[date, date]] = None,
        limit: int = 10
    ) -> Dict:
        """
        Search financial data: transactions, accounts, goals.

        Args:
            keywords: Search terms for description, payee, notes
            transaction_type: Filter by type (income, expense)
            date_range: Tuple of (start_date, end_date)
            limit: Maximum results

        Returns:
            Standardized search results dict
        """
        from apps.finance.models import Transaction

        transactions = Transaction.objects.filter(user=self.user)

        if keywords:
            keyword_q = self._build_keyword_filter(
                keywords,
                ['description', 'payee', 'notes']
            )
            transactions = transactions.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            transactions = transactions.filter(date__gte=start_date)
        if end_date:
            transactions = transactions.filter(date__lte=end_date)

        if transaction_type == 'income':
            transactions = transactions.filter(amount__gt=0)
        elif transaction_type == 'expense':
            transactions = transactions.filter(amount__lt=0)

        transactions = transactions.select_related('account', 'category').order_by('-date')[:limit]

        results = []
        for txn in transactions:
            amount_str = f"${abs(txn.amount):,.2f}"
            txn_type = "Income" if txn.amount > 0 else "Expense"
            results.append(self._create_result(
                id=txn.pk,
                title=f"{txn.description} - {amount_str} ({txn_type})",
                snippet=f"Payee: {txn.payee}" if txn.payee else (txn.notes or ""),
                date_value=txn.date,
                url=self._safe_reverse('finance:transaction_detail', args=[txn.pk]),
                metadata={
                    "amount": float(txn.amount),
                    "account": txn.account.name if txn.account else None,
                    "category": txn.category.name if txn.category else None,
                    "transaction_type": txn_type.lower()
                }
            ))

        return {
            "module": "finance",
            "count": len(results),
            "results": results
        }

    # -------------------------------------------------------------------------
    # CAPTURE SEARCH
    # -------------------------------------------------------------------------

    def search_capture(
        self,
        keywords: Optional[List[str]] = None,
        date_range: Optional[Tuple[date, date]] = None,
        limit: int = 10
    ) -> Dict:
        """
        Search capture entries (voice memos with transcripts).

        Args:
            keywords: Search terms for title, transcript, summary
            date_range: Tuple of (start_date, end_date)
            limit: Maximum results

        Returns:
            Standardized search results dict
        """
        from apps.capture.models import CaptureEntry

        entries = CaptureEntry.objects.filter(user=self.user, status='ready')

        if keywords:
            keyword_q = self._build_keyword_filter(
                keywords,
                ['title', 'transcript', 'summary']
            )
            entries = entries.filter(keyword_q)

        start_date, end_date = self._parse_date_range(date_range)
        if start_date:
            entries = entries.filter(created_at__date__gte=start_date)
        if end_date:
            entries = entries.filter(created_at__date__lte=end_date)

        entries = entries.order_by('-created_at')[:limit]

        results = []
        for entry in entries:
            duration = ""
            if entry.duration_seconds:
                mins = entry.duration_seconds // 60
                secs = entry.duration_seconds % 60
                duration = f" ({mins}:{secs:02d})"
            results.append(self._create_result(
                id=entry.pk,
                title=f"Capture: {entry.title or 'Voice Memo'}{duration}",
                snippet=entry.summary or entry.transcript[:200] if entry.transcript else "",
                date_value=entry.created_at.date(),
                url=self._safe_reverse('capture:detail', args=[entry.pk]),
                metadata={
                    "category": entry.category,
                    "subcategory": entry.subcategory,
                    "duration_seconds": entry.duration_seconds
                }
            ))

        return {
            "module": "capture",
            "count": len(results),
            "results": results
        }

    # -------------------------------------------------------------------------
    # GLOBAL SEARCH
    # -------------------------------------------------------------------------

    def search_all(
        self,
        keywords: List[str],
        limit: int = 20
    ) -> Dict:
        """
        Search across all modules.

        Args:
            keywords: Search terms
            limit: Maximum total results

        Returns:
            Combined search results from all modules
        """
        if not keywords:
            return {
                "module": "all",
                "count": 0,
                "results": [],
                "by_module": {}
            }

        # Search each module with proportional limits
        per_module_limit = max(3, limit // 7)

        module_results = {}
        all_results = []

        def _tag(results, domain):
            # Stamp every result with its TRUE source domain. Without this, the merged
            # cross-domain list is domain-blind and a health/mobility/audio record can
            # be mislabeled as a journal entry (the journal-contamination class). With
            # it, each record's origin is explicit and mislabeling is impossible.
            for r in results:
                r['domain'] = domain
                meta = r.get('metadata')
                if isinstance(meta, dict):
                    meta.setdefault('source_domain', domain)
            return results

        # Journal
        journal = self.search_journal(keywords=keywords, limit=per_module_limit)
        module_results['journal'] = journal['count']
        all_results.extend(_tag(journal['results'], 'journal'))

        # Health
        health = self.search_health(keywords=keywords, limit=per_module_limit)
        module_results['health'] = health['count']
        all_results.extend(_tag(health['results'], 'health'))

        # Goals/Purpose
        goals = self.search_goals(keywords=keywords, limit=per_module_limit)
        module_results['purpose'] = goals['count']
        all_results.extend(_tag(goals['results'], 'purpose'))

        # Faith
        faith = self.search_faith(keywords=keywords, limit=per_module_limit)
        module_results['faith'] = faith['count']
        all_results.extend(_tag(faith['results'], 'faith'))

        # Organize
        organize = self.search_organize(keywords=keywords, limit=per_module_limit)
        module_results['organize'] = organize['count']
        all_results.extend(_tag(organize['results'], 'organize'))

        # Finance
        finance = self.search_finance(keywords=keywords, limit=per_module_limit)
        module_results['finance'] = finance['count']
        all_results.extend(_tag(finance['results'], 'finance'))

        # Capture
        capture = self.search_capture(keywords=keywords, limit=per_module_limit)
        module_results['capture'] = capture['count']
        all_results.extend(_tag(capture['results'], 'capture'))

        # Sort all results by date (most recent first)
        all_results.sort(key=lambda x: x.get('date') or '', reverse=True)
        all_results = all_results[:limit]

        return {
            "module": "all",
            "count": len(all_results),
            "results": all_results,
            "by_module": module_results
        }
