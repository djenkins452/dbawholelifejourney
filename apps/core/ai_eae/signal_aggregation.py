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
from apps.core.ai_eae.signal_confidence import (
    confidence_for_state,
    CONFIDENCE_EXPLICIT,
    CONFIDENCE_DERIVED,
    CONFIDENCE_ABSENCE,
    CONFIDENCE_NOT_EXPECTED,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Signal Type Definitions — maps to SIGNAL_TAXONOMY.md
# =============================================================================

SIGNAL_TYPE_DOMAIN = {
    # Base signal types (Phase 4)
    'health_activity': 'health',
    'health_biometrics': 'health',
    'medication_adherence': 'health',
    'nutrition_compliance': 'health',
    'faith_practice': 'faith',
    'mental_reflection': 'journal',           # Phase 4: aligned with Domain Registry (was 'mind')
    'cognitive_fitness': 'brain_training',     # Phase 4: aligned with Domain Registry (was 'mind')
    'productivity_progress': 'life',
    'financial_health': 'finance',
    'relational_engagement': 'relationships',
    # Phase 5: Cross-domain pattern signal types (derived_pattern)
    'recovery_risk': 'health',                # health_activity + health_biometrics
    'holistic_momentum': 'purpose',           # 3+ signals across 2+ domains → life purpose
    'domain_neglect': 'life',                 # domain-level decline → organize/life management
    'compliance_drift': 'health',             # medication_adherence + health_biometrics
    'wellbeing_convergence': 'journal',       # reflection + relational + faith → inner life
    # Emotion-derived signal types (deterministic, from structured journal emotion selections)
    'emotional_stress': 'emotional',          # stressed/overwhelmed/anxious
    'emotional_low_mood': 'emotional',        # sad/angry/low/difficult/tired
    'emotional_positive': 'emotional',        # great/good/excited/grateful/hopeful/calm/energetic
}

# Signal types intentionally stubbed (domain exists but data pipeline not yet mature)
STUBBED_SIGNAL_TYPES = {
    'financial_health': 'Finance module is coming_soon — no deterministic data source yet',
    'emotional_stress': 'Produced by journal blending pipeline (_blend_journal_signals), not a direct computer',
    'emotional_low_mood': 'Produced by journal blending pipeline (_blend_journal_signals), not a direct computer',
    'emotional_positive': 'Produced by journal blending pipeline (_blend_journal_signals), not a direct computer',
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
        Every base signal type produces a daily snapshot (zero-fill for no activity).
        Each snapshot includes expected (bool) and state (enum) from the ETE.
        """
        from apps.core.execution.expected_map import (
            get_expected_map, SIGNAL_EXPECTED_KEYS,
        )

        results = []

        # Get expected map from Execution Truth Engine (single call)
        expected_map = get_expected_map(user, date)

        signal_computers = [
            SignalAggregationService._compute_health_activity,
            SignalAggregationService._compute_health_biometrics,
            SignalAggregationService._compute_medication_adherence,
            SignalAggregationService._compute_nutrition_compliance,    # Phase 4
            SignalAggregationService._compute_faith_practice,
            SignalAggregationService._compute_mental_reflection,
            SignalAggregationService._compute_cognitive_fitness,
            SignalAggregationService._compute_productivity_progress,
            SignalAggregationService._compute_relational_engagement,   # Phase 4
            SignalAggregationService._compute_financial_health,        # Phase 4 (stub)
        ]

        for computer in signal_computers:
            try:
                snapshot = computer(user, date, expected_map)
                if snapshot:
                    results.append(snapshot)
            except Exception as e:
                logger.warning(
                    "Signal computation %s failed for user %s on %s: %s",
                    computer.__name__, user.pk, date, e,
                    exc_info=True,
                )

        # Zero-fill: guarantee daily coverage for all base signal types.
        # Uses expected_map to set correct state (missed vs not_expected).
        produced_types = {s.signal_type for s in results}
        _ZERO_FILL_TYPES = [
            'health_activity', 'health_biometrics', 'medication_adherence',
            'nutrition_compliance', 'faith_practice', 'mental_reflection',
            'cognitive_fitness', 'productivity_progress', 'relational_engagement',
        ]
        for sig_type in _ZERO_FILL_TYPES:
            if sig_type not in produced_types:
                try:
                    expected_key = SIGNAL_EXPECTED_KEYS.get(sig_type, '')
                    is_expected = expected_map.get(expected_key, False)
                    state = 'missed' if is_expected else 'not_expected'
                    snapshot = SignalAggregationService._upsert_snapshot(
                        user, date, sig_type,
                        score=0.0,
                        confidence=confidence_for_state(state),
                        signal_class='verified_action',
                        source_signals={'source': 'zero_fill', 'reason': 'no_activity'},
                        expected=is_expected,
                        state=state,
                    )
                    results.append(snapshot)
                except Exception as e:
                    logger.debug(
                        "Zero-fill snapshot %s failed for user %s: %s",
                        sig_type, user.pk, e,
                    )

        # Phase 7: Blend journal-inferred signals into existing snapshots
        try:
            SignalAggregationService._blend_journal_signals(user, date, results)
        except Exception as e:
            logger.warning(
                "Journal signal blending failed for user %s on %s: %s",
                user.pk, date, e,
            )

        # Phase 5.5: Blend capture/document extraction signals
        # During nightly aggregation, blend any CaptureSignal/DocumentSignal
        # records that were created since last run. Uses the same targeted
        # recompute logic but called within the nightly pipeline.
        try:
            SignalAggregationService._blend_extraction_signals(user, date, results)
        except Exception as e:
            logger.warning(
                "Extraction signal blending failed for user %s on %s: %s",
                user.pk, date, e,
            )

        return results

    @staticmethod
    def _upsert_snapshot(user, date, signal_type, score, confidence,
                         signal_class, source_signals,
                         expected=True, state=''):
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
                'expected': expected,
                'state': state,
            },
        )
        action = "Created" if created else "Updated"
        logger.debug(
            "%s signal %s for user %s on %s: score=%.2f state=%s expected=%s",
            action, signal_type, user.pk, date, score, state, expected,
        )
        return snapshot

    # ──────────────────────────────────────────────────────────
    # Individual Signal Computers
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _compute_health_activity(user, date, expected_map):
        """
        Physical activity level.
        Sources: WorkoutSession, WorkoutScheduleLog (for skip evidence).
        Normalization: 0.5 = 20 min exercise, 1.0 = 45+ min.
        """
        from apps.health.models import WorkoutSession

        is_expected = expected_map.get('workout', False)

        sessions = WorkoutSession.objects.filter(
            user=user, date=date, completed_at__isnull=False,
        )
        total_minutes = sum(s.duration_minutes or 0 for s in sessions)
        session_count = sessions.count()

        if session_count == 0 and total_minutes == 0:
            # Check for explicit skip via WorkoutScheduleLog
            try:
                from apps.health.models import WorkoutScheduleLog
                skip_count = WorkoutScheduleLog.objects.filter(
                    user=user, scheduled_date=date, log_status='skipped',
                ).count()
                if skip_count > 0 and is_expected:
                    return SignalAggregationService._upsert_snapshot(
                        user, date, 'health_activity',
                        score=0.0,
                        confidence=confidence_for_state('skipped'),
                        signal_class='verified_action',
                        source_signals={
                            'source': 'workout_schedule_log',
                            'skipped_count': skip_count,
                        },
                        expected=True,
                        state='skipped',
                    )
            except ImportError:
                pass
            return None  # Zero-fill will handle

        # Normalize: 0 min=0.0, 20 min=0.5, 45 min=1.0
        if total_minutes >= 45:
            score = 1.0
            state = 'completed'
        elif total_minutes >= 20:
            score = 0.5 + (total_minutes - 20) * 0.5 / 25
            state = 'partial'
        else:
            score = total_minutes * 0.5 / 20
            state = 'partial'

        return SignalAggregationService._upsert_snapshot(
            user, date, 'health_activity',
            score=score,
            confidence=confidence_for_state(state),
            signal_class='verified_action',
            source_signals={
                'workout_sessions': session_count,
                'total_minutes': total_minutes,
            },
            expected=is_expected,
            state=state,
        )

    @staticmethod
    def _compute_health_biometrics(user, date, expected_map):
        """
        Vital sign stability.
        Sources: Weight, Glucose, BP, Sleep.
        Normalization: average of available sub-scores.
        """
        from apps.health.models import (
            WeightEntry, GlucoseEntry, BloodPressureEntry, SleepEntry,
        )

        is_expected = expected_map.get('biometrics', False)
        sub_scores = []
        source_data = {}

        # Weight sub-score
        weight = WeightEntry.objects.filter(
            user=user, recorded_at__date=date,
        ).first()
        if weight:
            sub_scores.append(0.8)
            source_data['weight'] = float(weight.value)

        # Glucose sub-score
        glucose_entries = GlucoseEntry.objects.filter(
            user=user, recorded_at__date=date,
        )
        if glucose_entries.exists():
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
            return None  # Zero-fill will handle

        score = sum(sub_scores) / len(sub_scores)
        state = 'completed' if score >= 0.7 else 'partial'

        return SignalAggregationService._upsert_snapshot(
            user, date, 'health_biometrics',
            score=score,
            confidence=confidence_for_state(state),
            signal_class='verified_measurement',
            source_signals=source_data,
            expected=is_expected,
            state=state,
        )

    @staticmethod
    def _compute_medication_adherence(user, date, expected_map):
        """
        Medication compliance.
        Sources: MedicineLog vs MedicineSchedule.
        Normalization: taken_count / scheduled_count.
        """
        from apps.health.models import MedicineLog, MedicineSchedule

        is_expected = expected_map.get('medication', False)

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
            return None  # Zero-fill will handle

        # Count taken logs
        logs = MedicineLog.objects.filter(
            user=user,
            scheduled_date=date,
        )
        taken = logs.filter(log_status='taken').count()
        late = logs.filter(log_status='late').count()
        skipped = logs.filter(log_status='skipped').count()

        # Late doses count at 80% credit
        effective_taken = taken + (late * 0.8)
        score = min(1.0, effective_taken / scheduled_count)

        # Determine state — skipped beats missed when ALL doses are skipped
        if score >= 1.0:
            state = 'completed'
        elif score > 0:
            state = 'partial'
        elif skipped > 0 and (taken + late) == 0:
            # All doses explicitly skipped, none taken
            state = 'skipped'
        elif skipped > 0:
            # Some skipped, some not taken — partial at best
            state = 'partial'
        else:
            state = 'missed'

        return SignalAggregationService._upsert_snapshot(
            user, date, 'medication_adherence',
            score=score,
            confidence=confidence_for_state(state),
            signal_class='verified_action',
            source_signals={
                'scheduled': scheduled_count,
                'taken': taken,
                'late': late,
                'skipped': skipped,
                'score': round(score, 2),
            },
            expected=is_expected,
            state=state,
        )

    @staticmethod
    def _compute_faith_practice(user, date, expected_map):
        """
        Spiritual discipline engagement.
        Sources: UserReadingProgress, faith HabitEntries.
        """
        from apps.faith.models import UserReadingProgress
        from apps.purpose.models import HabitEntry

        is_expected = expected_map.get('faith', False)
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
            return None  # Zero-fill will handle

        score = sum(sub_scores) / len(sub_scores)

        if score >= 1.0:
            state = 'completed'
        elif score > 0:
            state = 'partial'
        else:
            state = 'missed'

        return SignalAggregationService._upsert_snapshot(
            user, date, 'faith_practice',
            score=score,
            confidence=confidence_for_state(state),
            signal_class='verified_action',
            source_signals=source_data,
            expected=is_expected,
            state=state,
        )

    @staticmethod
    def _compute_mental_reflection(user, date, expected_map):
        """
        Introspective activity.
        Sources: JournalEntry.
        """
        from apps.journal.models import JournalEntry

        is_expected = expected_map.get('journal', False)

        entries = JournalEntry.objects.filter(
            user=user,
            entry_date=date,
        )

        if not entries.exists():
            return None  # Zero-fill will handle

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
        state = 'completed' if best_score >= 0.7 else 'partial'

        return SignalAggregationService._upsert_snapshot(
            user, date, 'mental_reflection',
            score=best_score,
            confidence=confidence_for_state(state),
            signal_class='verified_action',
            source_signals=source_data,
            expected=is_expected,
            state=state,
        )

    @staticmethod
    def _compute_cognitive_fitness(user, date, expected_map):
        """
        Brain training engagement.
        Sources: GameSession.
        """
        from apps.brain_training.models import GameSession

        is_expected = expected_map.get('brain_training', False)

        sessions = GameSession.objects.filter(
            user=user,
            completed_at__date=date,
            status='completed',
        )

        count = sessions.count()
        if count == 0:
            return None  # Zero-fill will handle

        # 1 session = 0.5, 2+ = 1.0
        if count >= 2:
            score = 1.0
            state = 'completed'
        else:
            score = 0.5
            state = 'partial'

        return SignalAggregationService._upsert_snapshot(
            user, date, 'cognitive_fitness',
            score=score,
            confidence=confidence_for_state(state),
            signal_class='verified_action',
            source_signals={'sessions_completed': count},
            expected=is_expected,
            state=state,
        )

    @staticmethod
    def _compute_productivity_progress(user, date, expected_map):
        """
        Task and project execution.
        Sources: Task completions vs due tasks.
        """
        from apps.life.models import Task

        is_expected = expected_map.get('tasks', False)

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

        # Count explicitly skipped tasks due today
        skipped_today = due_today.filter(completion_status='skipped').count()
        completed_due = due_today.filter(completion_status='completed').count()

        if due_count == 0 and completed_today == 0:
            return None  # Zero-fill will handle

        if due_count == 0:
            # Nothing was due but something was completed — proactive work
            score = 0.8
            state = 'completed'
        elif completed_today >= due_count:
            score = 1.0
            state = 'completed'
        elif completed_today > 0 or completed_due > 0:
            score = max(completed_today, completed_due) / due_count
            state = 'partial'
        elif skipped_today > 0 and completed_due == 0:
            # All due tasks skipped, none completed
            score = 0.0
            state = 'skipped'
        else:
            score = 0.0
            state = 'missed'

        return SignalAggregationService._upsert_snapshot(
            user, date, 'productivity_progress',
            score=score,
            confidence=confidence_for_state(state),
            signal_class='verified_action',
            source_signals={
                'due_today': due_count,
                'completed_today': completed_today,
                'skipped_today': skipped_today,
            },
            expected=is_expected,
            state=state,
        )

    # ──────────────────────────────────────────────────────────
    # Phase 4 Signal Computers — Nutrition, Relationships, Finance
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _compute_nutrition_compliance(user, date, expected_map):
        """
        Dietary adherence and tracking compliance.
        Sources: FoodEntry, WaterEntry, FastingWindow.
        Normalization: average of available sub-scores.
        """
        from apps.health.models import FoodEntry, WaterEntry, FastingWindow

        is_expected = expected_map.get('nutrition', False)
        sub_scores = []
        source_data = {}

        # Food logging sub-score — did the user log any food today?
        food_entries = FoodEntry.objects.filter(
            user=user, logged_date=date,
        )
        food_count = food_entries.count()
        if food_count > 0:
            # 1+ meals logged = base score; 3+ meals = full credit
            if food_count >= 3:
                sub_scores.append(1.0)
            elif food_count >= 2:
                sub_scores.append(0.7)
            else:
                sub_scores.append(0.5)
            source_data['food_entries'] = food_count

        # Water intake sub-score
        water_entries = WaterEntry.objects.filter(
            user=user, logged_date=date,
        )
        if water_entries.exists():
            # Sum all entries, convert to oz for scoring
            total_oz = 0
            for entry in water_entries:
                amount = float(entry.amount)
                unit = entry.unit
                if unit == 'oz':
                    total_oz += amount
                elif unit == 'ml':
                    total_oz += amount / 29.5735
                elif unit == 'cups':
                    total_oz += amount * 8
                elif unit == 'liters':
                    total_oz += amount * 33.814
                else:
                    total_oz += amount  # Assume oz as fallback

            if total_oz >= 64:
                sub_scores.append(1.0)
            elif total_oz >= 32:
                sub_scores.append(0.5)
            elif total_oz >= 16:
                sub_scores.append(0.25)
            else:
                sub_scores.append(0.1)
            source_data['water_oz'] = round(total_oz, 1)

        # Fasting compliance sub-score
        fasting_windows = FastingWindow.objects.filter(
            user=user, started_at__date=date,
        )
        if fasting_windows.exists():
            # Check if any fasting window met its target
            completed = [
                fw for fw in fasting_windows
                if fw.ended_at and fw.target_hours
                and fw.duration_hours and fw.duration_hours >= fw.target_hours
            ]
            if completed:
                sub_scores.append(1.0)
                source_data['fasting_met_target'] = True
            else:
                # Started but didn't complete — partial credit
                sub_scores.append(0.5)
                source_data['fasting_met_target'] = False

        if not sub_scores:
            return None  # Zero-fill will handle

        score = sum(sub_scores) / len(sub_scores)
        state = 'completed' if score >= 0.7 else 'partial'

        return SignalAggregationService._upsert_snapshot(
            user, date, 'nutrition_compliance',
            score=score,
            confidence=confidence_for_state(state),
            signal_class='verified_action',
            source_signals=source_data,
            expected=is_expected,
            state=state,
        )

    @staticmethod
    def _compute_relational_engagement(user, date, expected_map):
        """
        Social and relationship activity.
        Sources: RelationshipInteraction.
        Normalization: count of distinct person interactions.
        """
        try:
            from apps.relationships.models import RelationshipInteraction
        except ImportError:
            return None  # Relationships app not available

        is_expected = expected_map.get('relationships', False)

        interactions = RelationshipInteraction.objects.filter(
            user=user,
            interaction_date=date,
        )
        interaction_count = interactions.count()
        if interaction_count == 0:
            return None  # Zero-fill will handle

        # Distinct people interacted with
        distinct_people = interactions.values('person').distinct().count()

        # Normalize: 1 interaction = 0.5, 2+ distinct people = 1.0
        if distinct_people >= 2:
            score = 1.0
            state = 'completed'
        elif interaction_count >= 2:
            score = 0.7
            state = 'partial'
        else:
            score = 0.5
            state = 'partial'

        return SignalAggregationService._upsert_snapshot(
            user, date, 'relational_engagement',
            score=score,
            confidence=confidence_for_state(state),
            signal_class='verified_action',
            source_signals={
                'interaction_count': interaction_count,
                'distinct_people': distinct_people,
            },
            expected=is_expected,
            state=state,
        )

    @staticmethod
    def _compute_financial_health(user, date, expected_map):
        """
        Financial behavior signals — STUB.

        Finance module is coming_soon. This computer returns None until
        deterministic financial data sources exist.
        """
        return None

    # ──────────────────────────────────────────────────────────
    # Phase 7: Journal Signal Blending
    # ──────────────────────────────────────────────────────────

    # Confidence discount for journal-inferred signals (reduced trust)
    JOURNAL_CONFIDENCE_DISCOUNT = 0.7

    @staticmethod
    def _blend_journal_signals(user, date, existing_results):
        """
        Blend journal-extracted inferred_behavior signals into signal snapshots.

        For signal types that already have a verified snapshot, journal signals
        are noted in source_signals but don't override the verified score.

        For signal types with NO verified snapshot, a new inferred_behavior
        snapshot is created from journal signals (with confidence discount).

        Modifies existing_results in-place (appends new snapshots).
        """
        try:
            from apps.journal.models import JournalSignal
        except ImportError:
            return  # Journal app not available

        # Get journal signals for this user/date via the entry's date
        journal_signals = JournalSignal.objects.filter(
            entry__user=user,
            entry__entry_date=date,
            confidence__gte=0.5,
        ).select_related('entry')

        if not journal_signals.exists():
            return

        # Group by signal_type
        by_type = {}
        for js in journal_signals:
            by_type.setdefault(js.signal_type, []).append(js)

        # Check which signal types already have verified snapshots
        existing_types = {s.signal_type for s in existing_results}

        for signal_type, signals in by_type.items():
            if signal_type in existing_types:
                # Already have verified data — just annotate the existing snapshot
                for snapshot in existing_results:
                    if snapshot.signal_type == signal_type:
                        source = snapshot.source_signals or {}
                        source['journal_inferred'] = [
                            {
                                'text': js.extracted_text[:100],
                                'confidence': js.confidence,
                            }
                            for js in signals
                        ]
                        snapshot.source_signals = source
                        snapshot.save(update_fields=['source_signals'])
                        break
            else:
                # No verified data — create inferred_behavior snapshot
                best_signal = max(signals, key=lambda s: s.confidence)
                discounted_confidence = (
                    best_signal.confidence
                    * SignalAggregationService.JOURNAL_CONFIDENCE_DISCOUNT
                )

                domain = SIGNAL_TYPE_DOMAIN.get(signal_type, 'life')
                snapshot = SignalAggregationService._upsert_snapshot(
                    user, date, signal_type,
                    score=discounted_confidence,  # Use discounted confidence as score
                    confidence=discounted_confidence,
                    signal_class='inferred_behavior',
                    source_signals={
                        'source': 'journal_nlp',
                        'extractions': [
                            {
                                'text': js.extracted_text[:100],
                                'confidence': js.confidence,
                            }
                            for js in signals
                        ],
                    },
                    expected=True,
                    state='completed',
                )  # Journal-inferred: confidence already discounted via JOURNAL_CONFIDENCE_DISCOUNT
                existing_results.append(snapshot)

    # ──────────────────────────────────────────────────────────
    # Phase 5.5: Capture/Document Extraction Signal Blending
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _blend_extraction_signals(user, date, existing_results):
        """
        Blend capture and document extraction signals during nightly aggregation.

        Delegates to the TargetedSignalRecomputeService blend functions.
        This ensures that extraction signals created between nightly runs
        are picked up even if the targeted recompute didn't fire.
        """
        from apps.core.ai_eae.targeted_recompute import (
            _blend_capture_signals,
            _blend_document_signals,
        )

        # Blend capture signals
        try:
            from apps.capture.models import CaptureSignal
            capture_signals = CaptureSignal.objects.filter(
                entry__user=user,
                entry__created_at__date=date,
                confidence__gte=0.6,
            ).select_related('entry')
            if capture_signals.exists():
                _blend_capture_signals(user, date, list(capture_signals))
        except ImportError:
            pass

        # Blend document signals
        try:
            from apps.life.models import DocumentSignal
            document_signals = DocumentSignal.objects.filter(
                document__user=user,
                document__created_at__date=date,
                confidence__gte=0.4,
            ).select_related('document')
            if document_signals.exists():
                _blend_document_signals(user, date, list(document_signals))
        except ImportError:
            pass
