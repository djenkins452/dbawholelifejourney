# ==============================================================================
# File: apps/core/ai_eae/signal_aggregation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Signal aggregation service — computes daily SignalSnapshots
# Created: 2026-03-14 (Architecture Evolution Phase 4)
# ==============================================================================
"""
SignalAggregationService — Computes and persists daily signal snapshots.

Uses DailyActivityService (Phase 2) to gather completed actions, then
normalizes them into SignalSnapshot records per the Signal Taxonomy (Phase 3).

Part of the WLJ Architecture Evolution — Layer 3 (Signals).
"""

import logging

from apps.core.ai_eae.models import SignalSnapshot

logger = logging.getLogger(__name__)


# =============================================================================
# Signal Type Definitions — maps to SIGNAL_TAXONOMY.md
# =============================================================================

SIGNAL_TYPE_DOMAIN = {
    'health_activity': 'health',
    'health_biometrics': 'health',
    'medication_adherence': 'health',
    'nutrition_compliance': 'health',
    'faith_practice': 'faith',
    'mental_reflection': 'mind',
    'cognitive_fitness': 'mind',
    'productivity_progress': 'life',
    'financial_health': 'finance',
    'relational_engagement': 'relationships',
}


class SignalAggregationService:
    """
    Computes all signal types for a user for a given date.

    Each signal type has a dedicated compute method that:
    1. Queries domain completion records (via DailyActivityService or directly)
    2. Normalizes raw values to 0.0–1.0 score
    3. Assigns signal_class based on data source
    4. Returns a SignalSnapshot (upserted) or None if no data
    """

    @staticmethod
    def compute_daily_signals(user, date):
        """
        Compute all signal types for a user for a date.

        Returns list of upserted SignalSnapshot records.
        Skips signals with no data (returns fewer than 10 if some are empty).
        """
        results = []

        signal_computers = [
            SignalAggregationService._compute_health_activity,
            SignalAggregationService._compute_health_biometrics,
            SignalAggregationService._compute_medication_adherence,
            SignalAggregationService._compute_faith_practice,
            SignalAggregationService._compute_mental_reflection,
            SignalAggregationService._compute_cognitive_fitness,
            SignalAggregationService._compute_productivity_progress,
        ]

        for computer in signal_computers:
            try:
                snapshot = computer(user, date)
                if snapshot:
                    results.append(snapshot)
            except Exception as e:
                logger.warning(
                    "Signal computation %s failed for user %s on %s: %s",
                    computer.__name__, user.pk, date, e,
                    exc_info=True,
                )

        return results

    @staticmethod
    def _upsert_snapshot(user, date, signal_type, score, confidence,
                         signal_class, source_signals):
        """Create or update a SignalSnapshot record."""
        snapshot, created = SignalSnapshot.objects.update_or_create(
            user=user,
            date=date,
            signal_type=signal_type,
            defaults={
                'domain': SIGNAL_TYPE_DOMAIN.get(signal_type, 'life'),
                'signal_class': signal_class,
                'score': max(0.0, min(1.0, score)),  # Clamp to 0-1
                'confidence': max(0.0, min(1.0, confidence)),
                'source_signals': source_signals,
            },
        )
        action = "Created" if created else "Updated"
        logger.debug(
            "%s signal %s for user %s on %s: score=%.2f class=%s",
            action, signal_type, user.pk, date, score, signal_class,
        )
        return snapshot

    # ──────────────────────────────────────────────────────────
    # Individual Signal Computers
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _compute_health_activity(user, date):
        """
        Physical activity level.
        Sources: WorkoutSession, Steps.
        Normalization: 0.5 = 20 min exercise, 1.0 = 45+ min.
        """
        from apps.health.models import WorkoutSession

        sessions = WorkoutSession.objects.filter(user=user, date=date)
        total_minutes = sum(s.duration_minutes or 0 for s in sessions)
        session_count = sessions.count()

        if session_count == 0 and total_minutes == 0:
            return None  # No data — skip

        # Normalize: 0 min=0.0, 20 min=0.5, 45 min=1.0
        if total_minutes >= 45:
            score = 1.0
        elif total_minutes >= 20:
            score = 0.5 + (total_minutes - 20) * 0.5 / 25
        else:
            score = total_minutes * 0.5 / 20

        return SignalAggregationService._upsert_snapshot(
            user, date, 'health_activity',
            score=score,
            confidence=1.0,
            signal_class='verified_action',
            source_signals={
                'workout_sessions': session_count,
                'total_minutes': total_minutes,
            },
        )

    @staticmethod
    def _compute_health_biometrics(user, date):
        """
        Vital sign stability.
        Sources: Weight, Glucose, BP, Sleep.
        Normalization: average of available sub-scores.
        """
        from apps.health.models import (
            WeightEntry, GlucoseEntry, BloodPressureEntry, SleepEntry,
        )

        sub_scores = []
        source_data = {}

        # Weight sub-score
        weight = WeightEntry.objects.filter(
            user=user, recorded_at__date=date,
        ).first()
        if weight:
            # Simple: any weight logged = 0.8 (baseline presence score)
            # Full normalization (vs goal weight) deferred to when user weight goals exist
            sub_scores.append(0.8)
            source_data['weight'] = float(weight.value)

        # Glucose sub-score
        glucose_entries = GlucoseEntry.objects.filter(
            user=user, recorded_at__date=date,
        )
        if glucose_entries.exists():
            # Average glucose value
            avg_val = sum(float(g.value) for g in glucose_entries) / glucose_entries.count()
            if avg_val <= 100:
                g_score = 1.0
            elif avg_val <= 126:
                g_score = 1.0 - (avg_val - 100) * 0.5 / 26
            elif avg_val <= 150:
                g_score = 0.5 - (avg_val - 126) * 0.5 / 24
            else:
                g_score = 0.0
            sub_scores.append(g_score)
            source_data['glucose_avg'] = round(avg_val, 1)

        # Blood pressure sub-score
        bp = BloodPressureEntry.objects.filter(
            user=user, recorded_at__date=date,
        ).first()
        if bp:
            if bp.systolic < 120 and bp.diastolic < 80:
                bp_score = 1.0
            elif bp.systolic < 140 and bp.diastolic < 90:
                bp_score = 0.5
            else:
                bp_score = 0.0
            sub_scores.append(bp_score)
            source_data['bp'] = f"{bp.systolic}/{bp.diastolic}"

        # Sleep sub-score
        sleep = SleepEntry.objects.filter(
            user=user, sleep_date=date,
        ).first()
        if sleep and sleep.total_minutes:
            hours = sleep.total_minutes / 60
            if 7 <= hours <= 9:
                s_score = 1.0
            elif 6 <= hours < 7 or 9 < hours <= 10:
                s_score = 0.5
            else:
                s_score = 0.0
            sub_scores.append(s_score)
            source_data['sleep_hours'] = round(hours, 1)

        if not sub_scores:
            return None  # No biometric data

        score = sum(sub_scores) / len(sub_scores)

        return SignalAggregationService._upsert_snapshot(
            user, date, 'health_biometrics',
            score=score,
            confidence=1.0,
            signal_class='verified_measurement',
            source_signals=source_data,
        )

    @staticmethod
    def _compute_medication_adherence(user, date):
        """
        Medication compliance.
        Sources: MedicineLog vs MedicineSchedule.
        Normalization: taken_count / scheduled_count.
        """
        from apps.health.models import MedicineLog, MedicineSchedule

        # Get all active schedules for this user
        active_schedules = MedicineSchedule.objects.filter(
            medicine__user=user,
            is_active=True,
        )

        # Filter to schedules that apply today (by day_of_week)
        day_of_week = date.weekday()  # 0=Mon, 6=Sun
        applicable = [s for s in active_schedules if s.applies_to_day(day_of_week)]
        scheduled_count = len(applicable)

        if scheduled_count == 0:
            return None  # No meds scheduled today

        # Count taken logs
        logs = MedicineLog.objects.filter(
            user=user,
            scheduled_date=date,
        )
        taken = logs.filter(status='taken').count()
        late = logs.filter(status='late').count()

        # Late doses count at 80% credit
        effective_taken = taken + (late * 0.8)
        score = min(1.0, effective_taken / scheduled_count)

        return SignalAggregationService._upsert_snapshot(
            user, date, 'medication_adherence',
            score=score,
            confidence=1.0,
            signal_class='verified_action',
            source_signals={
                'scheduled': scheduled_count,
                'taken': taken,
                'late': late,
                'score': round(score, 2),
            },
        )

    @staticmethod
    def _compute_faith_practice(user, date):
        """
        Spiritual discipline engagement.
        Sources: UserReadingProgress, faith HabitEntries.
        """
        from apps.faith.models import UserReadingProgress
        from apps.purpose.models import HabitEntry

        sub_scores = []
        source_data = {}

        # Bible reading
        readings_completed = UserReadingProgress.objects.filter(
            user=user,
            is_completed=True,
            completed_at__date=date,
        ).count()
        if readings_completed > 0:
            sub_scores.append(1.0)
            source_data['readings_completed'] = readings_completed
        else:
            # Check if reading was expected (active plan exists)
            from apps.faith.models import UserReadingPlan
            has_active_plan = UserReadingPlan.objects.filter(
                user=user,
                plan_status='active',
            ).exists()
            if has_active_plan:
                sub_scores.append(0.0)
                source_data['readings_completed'] = 0

        # Faith habits
        faith_habits = HabitEntry.objects.filter(
            goal__user=user,
            date=date,
            goal__domain__slug='faith',
        )
        faith_completed = faith_habits.filter(completed=True).count()
        faith_total = faith_habits.count()
        if faith_total > 0:
            sub_scores.append(faith_completed / faith_total)
            source_data['faith_habits'] = {
                'completed': faith_completed,
                'total': faith_total,
            }

        if not sub_scores:
            return None

        score = sum(sub_scores) / len(sub_scores)

        return SignalAggregationService._upsert_snapshot(
            user, date, 'faith_practice',
            score=score,
            confidence=1.0,
            signal_class='verified_action',
            source_signals=source_data,
        )

    @staticmethod
    def _compute_mental_reflection(user, date):
        """
        Introspective activity.
        Sources: JournalEntry.
        """
        from apps.journal.models import JournalEntry

        entries = JournalEntry.objects.filter(
            user=user,
            entry_date=date,
        )

        if not entries.exists():
            return None

        # Score based on entry substance
        best_score = 0.0
        source_data = {'entry_count': entries.count()}

        for entry in entries:
            content = getattr(entry, 'content', '') or ''
            word_count = len(content.split())

            if word_count >= 100:
                entry_score = 1.0
            elif word_count >= 50:
                entry_score = 0.7
            elif word_count > 0:
                entry_score = 0.5
            else:
                entry_score = 0.3  # Entry created but minimal content

            # Mood tracking bonus
            if getattr(entry, 'mood', None):
                entry_score = min(1.0, entry_score + 0.2)

            best_score = max(best_score, entry_score)

        source_data['best_score'] = round(best_score, 2)

        return SignalAggregationService._upsert_snapshot(
            user, date, 'mental_reflection',
            score=best_score,
            confidence=1.0,
            signal_class='verified_action',
            source_signals=source_data,
        )

    @staticmethod
    def _compute_cognitive_fitness(user, date):
        """
        Brain training engagement.
        Sources: GameSession.
        """
        from apps.brain_training.models import GameSession

        sessions = GameSession.objects.filter(
            user=user,
            completed_at__date=date,
            status='completed',
        )

        count = sessions.count()
        if count == 0:
            return None

        # 1 session = 0.5, 2+ = 1.0
        if count >= 2:
            score = 1.0
        else:
            score = 0.5

        return SignalAggregationService._upsert_snapshot(
            user, date, 'cognitive_fitness',
            score=score,
            confidence=1.0,
            signal_class='verified_action',
            source_signals={'sessions_completed': count},
        )

    @staticmethod
    def _compute_productivity_progress(user, date):
        """
        Task and project execution.
        Sources: Task completions vs due tasks.
        """
        from apps.life.models import Task

        # Tasks due today
        due_today = Task.objects.filter(
            user=user,
            due_date=date,
        ).exclude(status='deleted')
        due_count = due_today.count()

        # Tasks completed today (may include tasks not due today)
        completed_today = Task.objects.filter(
            user=user,
            completed_at__date=date,
            completion_status='completed',
        ).count()

        if due_count == 0 and completed_today == 0:
            return None  # No productivity data

        if due_count == 0:
            # Nothing was due but something was completed — proactive work
            score = 0.8
        else:
            score = min(1.0, completed_today / due_count)

        return SignalAggregationService._upsert_snapshot(
            user, date, 'productivity_progress',
            score=score,
            confidence=1.0,
            signal_class='verified_action',
            source_signals={
                'due_today': due_count,
                'completed_today': completed_today,
            },
        )
