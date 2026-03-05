"""
Body Composition Intelligence Service — deterministic analysis of scan history.

Computes fat loss quality, recomposition detection, plateau classification,
fat loss speed monitoring, and muscle loss risk scoring from historical
BodyCompositionEntry scans.

Architecture rule:
    ALL calculations occur at daily rollup time (via DailyHealthSummaryBuilder).
    CoS reads ONLY from DailyHealthSummary — never calls this service directly.

Usage (from daily_summary_builder.py only):
    from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence
    result = BodyCompositionIntelligence.compute_daily_intelligence(user, target_date)
"""

import logging
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Avg, StdDev

logger = logging.getLogger(__name__)


class BodyCompositionIntelligence:
    """Deterministic body composition analysis from scan history."""

    # ------------------------------------------------------------------
    # Core helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def compute_fat_mass(weight, body_fat_pct):
        """
        Compute fat mass from weight and body fat percentage.

        fat_mass = weight × (body_fat_pct / 100)

        Returns Decimal (lbs) or None if inputs invalid.
        """
        if weight is None or body_fat_pct is None:
            return None
        w = float(weight)
        bf = float(body_fat_pct)
        if w <= 0 or bf < 0 or bf >= 100:
            return None
        fm = w * (bf / 100)
        return Decimal(str(round(fm, 2)))

    @staticmethod
    def compute_lean_mass(weight, fat_mass):
        """
        Compute lean mass from weight and fat mass.

        lean_mass = weight - fat_mass

        Returns Decimal (lbs) or None if inputs invalid.
        """
        if weight is None or fat_mass is None:
            return None
        w = float(weight)
        fm = float(fat_mass)
        if w <= 0 or fm < 0 or fm >= w:
            return None
        lm = w - fm
        return Decimal(str(round(lm, 2)))

    # ------------------------------------------------------------------
    # Scan retrieval
    # ------------------------------------------------------------------

    @staticmethod
    def get_latest_scan(user, as_of_date):
        """
        Pull latest body composition values at or before as_of_date.

        Priority:
            1. BodyCompositionEntry (InBody, DEXA, etc.)
            2. WeightEntry (HealthKit + manual)
            3. DailyHealthSummary (rollup)

        Returns dict with:
            weight, body_fat_pct, fat_mass, lean_mass,
            skeletal_muscle_mass, scan_date, source
        All fields may be None if no data exists.
        """
        from apps.health.models import BodyCompositionEntry, WeightEntry, DailyHealthSummary

        result = {
            'weight': None,
            'body_fat_pct': None,
            'fat_mass': None,
            'lean_mass': None,
            'skeletal_muscle_mass': None,
            'scan_date': None,
            'source': None,
        }

        # 1. BodyCompositionEntry — flexible metric-per-row
        bce_qs = (
            BodyCompositionEntry.objects
            .filter(user=user, measurement_date__lte=as_of_date)
            .order_by('-measurement_date', '-created_at')
        )

        metrics_needed = {
            'body_fat_pct': ('body_fat_pct', 'body_fat_percentage'),
            'lean_mass': ('lean_mass', 'lean_body_mass'),
            'skeletal_muscle_mass': ('skeletal_muscle_mass', 'muscle_mass'),
            'fat_mass': ('fat_mass',),
        }

        for field, metric_names in metrics_needed.items():
            entry = bce_qs.filter(metric_name__in=metric_names).first()
            if entry:
                result[field] = entry.value
                # Use the most recent scan date we find
                if result['scan_date'] is None or entry.measurement_date > result['scan_date']:
                    result['scan_date'] = entry.measurement_date
                    result['source'] = entry.source

        # Weight from BodyCompositionEntry
        weight_entry = bce_qs.filter(metric_name='weight').first()
        if weight_entry:
            result['weight'] = weight_entry.value

        # 2. WeightEntry fallback for weight + body_fat + lean_mass
        if result['weight'] is None:
            we = (
                WeightEntry.objects
                .filter(user=user, recorded_at__date__lte=as_of_date)
                .order_by('-recorded_at')
                .first()
            )
            if we:
                # Convert to lbs if needed
                if we.unit == 'kg':
                    result['weight'] = Decimal(str(round(float(we.value) * 2.20462, 2)))
                else:
                    result['weight'] = we.value
                if we.body_fat_percentage and result['body_fat_pct'] is None:
                    result['body_fat_pct'] = we.body_fat_percentage
                if we.lean_body_mass and result['lean_mass'] is None:
                    result['lean_mass'] = we.lean_body_mass
                if result['scan_date'] is None:
                    result['scan_date'] = we.recorded_at.date()
                    result['source'] = we.source if hasattr(we, 'source') else 'weight_entry'

        # 3. DailyHealthSummary fallback
        if result['weight'] is None or result['body_fat_pct'] is None:
            dhs = (
                DailyHealthSummary.objects
                .filter(user=user, summary_date__lte=as_of_date)
                .exclude(weight__isnull=True)
                .order_by('-summary_date')
                .first()
            )
            if dhs:
                if result['weight'] is None and dhs.weight:
                    result['weight'] = dhs.weight
                if result['body_fat_pct'] is None and dhs.body_fat_pct:
                    result['body_fat_pct'] = dhs.body_fat_pct
                if result['lean_mass'] is None and dhs.lean_mass:
                    result['lean_mass'] = dhs.lean_mass
                if result['skeletal_muscle_mass'] is None and dhs.skeletal_muscle_mass:
                    result['skeletal_muscle_mass'] = dhs.skeletal_muscle_mass
                if result['scan_date'] is None:
                    result['scan_date'] = dhs.summary_date
                    result['source'] = 'daily_summary'

        # Compute fat_mass if we have weight + body_fat_pct but no explicit fat_mass
        if result['fat_mass'] is None and result['weight'] and result['body_fat_pct']:
            result['fat_mass'] = BodyCompositionIntelligence.compute_fat_mass(
                result['weight'], result['body_fat_pct']
            )

        # Compute lean_mass if we have weight + fat_mass but no explicit lean_mass
        if result['lean_mass'] is None and result['weight'] and result['fat_mass']:
            result['lean_mass'] = BodyCompositionIntelligence.compute_lean_mass(
                result['weight'], result['fat_mass']
            )

        return result

    # ------------------------------------------------------------------
    # Window metrics (14d / 21d comparisons)
    # ------------------------------------------------------------------

    @staticmethod
    def get_window_metrics(user, end_date, window_days=14):
        """
        Compare two scan snapshots across a time window.

        For 14-day analysis: accepts start scan within ±5 days of target.
        For 21-day analysis: accepts start scan within ±7 days of target.
        Requires actual window between 10–20 days (14d) or 14–28 days (21d).

        Returns:
            {current, start, deltas, window_actual_days, sufficient_data}
        """
        BCI = BodyCompositionIntelligence

        # Current snapshot
        current = BCI.get_latest_scan(user, end_date)
        if current['weight'] is None or current['body_fat_pct'] is None:
            return {
                'current': current,
                'start': None,
                'deltas': None,
                'window_actual_days': 0,
                'sufficient_data': False,
            }

        # Tolerance for start scan
        if window_days <= 14:
            tolerance = 5
            min_days, max_days = 10, 20
        else:
            tolerance = 7
            min_days, max_days = 14, 28

        target_start = end_date - timedelta(days=window_days)
        search_start = target_start - timedelta(days=tolerance)
        search_end = target_start + timedelta(days=tolerance)

        # Find start snapshot — nearest scan within tolerance window
        start = BCI.get_latest_scan(user, search_end)

        # Verify the start scan date falls within our tolerance
        if (
            start['weight'] is None
            or start['body_fat_pct'] is None
            or start['scan_date'] is None
            or start['scan_date'] < search_start
            or start['scan_date'] > search_end
        ):
            return {
                'current': current,
                'start': None,
                'deltas': None,
                'window_actual_days': 0,
                'sufficient_data': False,
            }

        # Check actual window span
        window_actual_days = (current['scan_date'] - start['scan_date']).days if (
            current['scan_date'] and start['scan_date']
        ) else 0

        if window_actual_days < min_days or window_actual_days > max_days:
            return {
                'current': current,
                'start': start,
                'deltas': None,
                'window_actual_days': window_actual_days,
                'sufficient_data': False,
            }

        # Ensure fat_mass computed for both
        c_fat = current['fat_mass'] or BCI.compute_fat_mass(current['weight'], current['body_fat_pct'])
        s_fat = start['fat_mass'] or BCI.compute_fat_mass(start['weight'], start['body_fat_pct'])
        c_lean = current['lean_mass'] or BCI.compute_lean_mass(current['weight'], c_fat)
        s_lean = start['lean_mass'] or BCI.compute_lean_mass(start['weight'], s_fat)

        if c_fat is None or s_fat is None or c_lean is None or s_lean is None:
            return {
                'current': current,
                'start': start,
                'deltas': None,
                'window_actual_days': window_actual_days,
                'sufficient_data': False,
            }

        deltas = {
            'weight_delta': float(current['weight']) - float(start['weight']),
            'fat_mass_delta': float(c_fat) - float(s_fat),
            'lean_mass_delta': float(c_lean) - float(s_lean),
            'body_fat_pct_delta': float(current['body_fat_pct']) - float(start['body_fat_pct']),
        }

        return {
            'current': current,
            'start': start,
            'deltas': deltas,
            'window_actual_days': window_actual_days,
            'sufficient_data': True,
        }

    # ------------------------------------------------------------------
    # Fat loss quality
    # ------------------------------------------------------------------

    @staticmethod
    def compute_fat_loss_quality(deltas, window_actual_days):
        """
        Classify fat loss quality from window deltas.

        Noise guard: if abs(weight_delta) < 1.5 lbs → INSUFFICIENT_DATA.

        Labels:
            EXCELLENT — ratio ≥ 0.80, lean stable (≥ -0.3 lbs/week)
            GOOD — ratio 0.60–0.80
            MIXED — ratio 0.40–0.60
            MUSCLE_LOSS_RISK — ratio < 0.40 or lean dropping > 0.5 lbs/week
            INSUFFICIENT_DATA — not enough weight change to classify
        """
        if deltas is None:
            return {
                'label': 'INSUFFICIENT_DATA',
                'fat_loss_ratio': None,
                'fat_contributed_lbs': None,
                'lean_contributed_lbs': None,
                'explanation': 'Not enough scan data to evaluate fat loss quality.',
            }

        weight_delta = deltas['weight_delta']
        fat_mass_delta = deltas['fat_mass_delta']
        lean_mass_delta = deltas['lean_mass_delta']

        # Noise guard
        if abs(weight_delta) < 1.5:
            return {
                'label': 'INSUFFICIENT_DATA',
                'fat_loss_ratio': None,
                'fat_contributed_lbs': round(fat_mass_delta, 1),
                'lean_contributed_lbs': round(lean_mass_delta, 1),
                'explanation': (
                    f'Weight change of {weight_delta:+.1f} lbs is too small to evaluate '
                    f'fat loss quality (need ≥1.5 lbs).'
                ),
            }

        # Compute ratio — clamped 0 to 1.2
        raw_ratio = abs(fat_mass_delta) / abs(weight_delta)
        fat_loss_ratio = max(0.0, min(1.2, raw_ratio))

        # Lean mass change rate (lbs per week)
        weeks = window_actual_days / 7.0
        lean_rate_per_week = lean_mass_delta / weeks if weeks > 0 else 0

        # Classification
        if fat_loss_ratio < 0.40 or lean_rate_per_week < -0.5:
            label = 'MUSCLE_LOSS_RISK'
            explanation = (
                f'Only {fat_loss_ratio:.0%} of weight loss came from fat. '
                f'Lean mass changing at {lean_rate_per_week:+.1f} lbs/week — risk of muscle loss.'
            )
        elif fat_loss_ratio < 0.60:
            label = 'MIXED'
            explanation = (
                f'{fat_loss_ratio:.0%} of weight loss came from fat. '
                f'Some lean mass contribution — consider increasing protein or adjusting deficit.'
            )
        elif fat_loss_ratio < 0.80:
            label = 'GOOD'
            explanation = (
                f'{fat_loss_ratio:.0%} of weight loss came from fat. '
                f'Lean mass relatively preserved.'
            )
        else:
            # ratio >= 0.80
            if lean_rate_per_week >= -0.3:
                label = 'EXCELLENT'
                explanation = (
                    f'{fat_loss_ratio:.0%} of weight loss came from fat. '
                    f'Lean mass stable — excellent fat loss quality.'
                )
            else:
                label = 'GOOD'
                explanation = (
                    f'{fat_loss_ratio:.0%} of weight loss came from fat, '
                    f'but lean mass declining at {lean_rate_per_week:+.1f} lbs/week.'
                )

        return {
            'label': label,
            'fat_loss_ratio': round(fat_loss_ratio, 3),
            'fat_contributed_lbs': round(fat_mass_delta, 1),
            'lean_contributed_lbs': round(lean_mass_delta, 1),
            'explanation': explanation,
        }

    # ------------------------------------------------------------------
    # Recomposition detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_recomposition(deltas):
        """
        Detect body recomposition: fat down, muscle up, weight flat.

        Criteria:
            weight_delta between -1.0 and +1.0 lbs
            fat_mass_delta ≤ -1.0 lbs
            lean_mass_delta ≥ +0.5 lbs
        """
        if deltas is None:
            return {'detected': False, 'details': 'Insufficient data for recomposition detection.'}

        weight_flat = -1.0 <= deltas['weight_delta'] <= 1.0
        fat_down = deltas['fat_mass_delta'] <= -1.0
        lean_up = deltas['lean_mass_delta'] >= 0.5

        detected = weight_flat and fat_down and lean_up

        if detected:
            details = (
                f"Recomposition detected: weight {deltas['weight_delta']:+.1f} lbs (flat), "
                f"fat mass {deltas['fat_mass_delta']:+.1f} lbs, "
                f"lean mass {deltas['lean_mass_delta']:+.1f} lbs."
            )
        else:
            reasons = []
            if not weight_flat:
                reasons.append(f"weight change {deltas['weight_delta']:+.1f} lbs (not flat)")
            if not fat_down:
                reasons.append(f"fat mass {deltas['fat_mass_delta']:+.1f} lbs (not decreasing enough)")
            if not lean_up:
                reasons.append(f"lean mass {deltas['lean_mass_delta']:+.1f} lbs (not increasing enough)")
            details = f"No recomposition: {'; '.join(reasons)}."

        return {'detected': detected, 'details': details}

    # ------------------------------------------------------------------
    # Plateau detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_plateau(user, end_date, window_days=21):
        """
        Classify plateau status over a 21-day window.

        Labels:
            TRUE_PLATEAU — weight flat AND fat flat AND no recomp
            RECOMP — weight flat but fat down + lean up
            WATER — high weight variance but fat stable (10+ weight entries)
            INSUFFICIENT_DATA — not enough scans
        """
        from apps.health.models import DailyHealthSummary

        BCI = BodyCompositionIntelligence

        metrics = BCI.get_window_metrics(user, end_date, window_days=window_days)

        if not metrics['sufficient_data']:
            return {
                'status': 'INSUFFICIENT_DATA',
                'explanation': 'Not enough scan data for plateau analysis.',
                'weight_range_lbs': None,
                'fat_mass_range_lbs': None,
            }

        deltas = metrics['deltas']
        weight_flat = abs(deltas['weight_delta']) <= 1.0
        fat_flat = abs(deltas['fat_mass_delta']) <= 0.5

        # Check for recomposition
        recomp = BCI.detect_recomposition(deltas)

        if weight_flat and recomp['detected']:
            return {
                'status': 'RECOMP',
                'explanation': (
                    'Weight is stable but body composition is improving — '
                    'fat decreasing and lean mass increasing.'
                ),
                'weight_range_lbs': round(abs(deltas['weight_delta']), 1),
                'fat_mass_range_lbs': round(abs(deltas['fat_mass_delta']), 1),
            }

        if weight_flat and fat_flat:
            return {
                'status': 'TRUE_PLATEAU',
                'explanation': (
                    f"Weight and fat mass both stable over {metrics['window_actual_days']} days. "
                    f"Consider adjusting caloric intake or training stimulus."
                ),
                'weight_range_lbs': round(abs(deltas['weight_delta']), 1),
                'fat_mass_range_lbs': round(abs(deltas['fat_mass_delta']), 1),
            }

        # Water fluctuation check: high weight variance but fat stable
        if not weight_flat and fat_flat:
            # Check if we have enough weight entries for variance analysis
            window_start = end_date - timedelta(days=window_days)
            weight_entries = (
                DailyHealthSummary.objects
                .filter(
                    user=user,
                    summary_date__gte=window_start,
                    summary_date__lte=end_date,
                    weight__isnull=False,
                )
                .count()
            )
            if weight_entries >= 10:
                return {
                    'status': 'WATER',
                    'explanation': (
                        'Weight is fluctuating but fat mass is stable — '
                        'likely water retention or carb/sodium variance.'
                    ),
                    'weight_range_lbs': round(abs(deltas['weight_delta']), 1),
                    'fat_mass_range_lbs': round(abs(deltas['fat_mass_delta']), 1),
                }

        return {
            'status': 'INSUFFICIENT_DATA',
            'explanation': 'Weight and fat mass both changing — no plateau pattern detected.',
            'weight_range_lbs': round(abs(deltas['weight_delta']), 1),
            'fat_mass_range_lbs': round(abs(deltas['fat_mass_delta']), 1),
        }

    # ------------------------------------------------------------------
    # Fat loss speed
    # ------------------------------------------------------------------

    @staticmethod
    def compute_fat_loss_speed(deltas, start_weight, window_actual_days):
        """
        Classify fat loss speed as % of body weight per week.

        Labels:
            SAFE — 0.5%–1.0% per week
            FAST — 1.0%–1.5%
            TOO_FAST — >1.5%
            SLOW — <0.5%
            GAINING — weight increasing
        """
        if deltas is None or start_weight is None or window_actual_days is None:
            return {
                'rate_pct_per_week': None,
                'label': 'INSUFFICIENT_DATA',
                'message': 'Not enough data to compute fat loss speed.',
            }

        sw = float(start_weight)
        wd = float(window_actual_days)

        if sw <= 0 or wd <= 0:
            return {
                'rate_pct_per_week': None,
                'label': 'INSUFFICIENT_DATA',
                'message': 'Invalid weight or window data.',
            }

        weight_delta = deltas['weight_delta']

        if weight_delta > 0:
            return {
                'rate_pct_per_week': None,
                'label': 'GAINING',
                'message': f'Weight increased by {weight_delta:+.1f} lbs over {wd:.0f} days.',
            }

        rate = (abs(weight_delta) / sw * 100) / (wd / 7.0)
        rate = round(rate, 2)

        if rate >= 1.5:
            label = 'TOO_FAST'
            message = (
                f'Losing {rate:.1f}%/week — exceeds safe rate. '
                f'Risk of muscle loss. Consider increasing calories slightly.'
            )
        elif rate >= 1.0:
            label = 'FAST'
            message = f'Losing {rate:.1f}%/week — aggressive but manageable with adequate protein.'
        elif rate >= 0.5:
            label = 'SAFE'
            message = f'Losing {rate:.1f}%/week — optimal range for preserving lean mass.'
        else:
            label = 'SLOW'
            message = f'Losing {rate:.1f}%/week — very gradual pace.'

        return {
            'rate_pct_per_week': rate,
            'label': label,
            'message': message,
        }

    # ------------------------------------------------------------------
    # Muscle loss risk scoring
    # ------------------------------------------------------------------

    @staticmethod
    def compute_muscle_loss_risk(user, end_date):
        """
        Composite muscle loss risk score (0–100).

        Components:
            lean_mass_drop: 0–40 (from 14d lean_mass_delta)
            protein_low: 0–25 (from ProteinService weekly consistency)
            recovery_low: 0–20 (from 7d avg recovery_score)
            training_high: 0–15 (training load vs 28d baseline)

        Risk levels: LOW (0–29), MED (30–59), HIGH (60–100)
        """
        from apps.health.models import DailyHealthSummary

        BCI = BodyCompositionIntelligence
        drivers = []

        # --- Component 1: Lean mass drop (0–40) ---
        lean_score = 0
        metrics_14d = BCI.get_window_metrics(user, end_date, window_days=14)
        if metrics_14d['sufficient_data'] and metrics_14d['deltas']:
            lean_delta = metrics_14d['deltas']['lean_mass_delta']
            window_weeks = metrics_14d['window_actual_days'] / 7.0
            lean_rate = lean_delta / window_weeks if window_weeks > 0 else 0

            if lean_rate < -1.0:
                lean_score = 40
            elif lean_rate < -0.5:
                lean_score = 30
            elif lean_rate < -0.3:
                lean_score = 20
            elif lean_rate < 0:
                lean_score = 10
            # else: stable or gaining = 0

            drivers.append({
                'component': 'lean_mass_drop',
                'score': lean_score,
                'detail': f'Lean mass {lean_rate:+.2f} lbs/week',
            })
        else:
            drivers.append({
                'component': 'lean_mass_drop',
                'score': 0,
                'detail': 'Insufficient scan data',
            })

        # --- Component 2: Protein low (0–25) ---
        protein_score = 0
        try:
            from apps.health.services.protein_service import ProteinService
            weekly = ProteinService.get_weekly_summary(user, end_date)
            if weekly and weekly.get('status') == 'ok':
                consistency = weekly.get('consistency_pct', 100)
                if consistency < 50:
                    protein_score = 25
                elif consistency < 60:
                    protein_score = 20
                elif consistency < 70:
                    protein_score = 15
                elif consistency < 80:
                    protein_score = 10
                elif consistency < 90:
                    protein_score = 5
                drivers.append({
                    'component': 'protein_low',
                    'score': protein_score,
                    'detail': f'Protein consistency {consistency:.0f}%',
                })
            else:
                drivers.append({
                    'component': 'protein_low',
                    'score': 0,
                    'detail': 'No protein data',
                })
        except Exception:
            logger.error("Failed to get protein data for muscle loss risk", exc_info=True)
            drivers.append({
                'component': 'protein_low',
                'score': 0,
                'detail': 'Protein data unavailable',
            })

        # --- Component 3: Recovery low (0–20) ---
        recovery_score_comp = 0
        start_7d = end_date - timedelta(days=7)
        recovery_avg = (
            DailyHealthSummary.objects
            .filter(
                user=user,
                summary_date__gte=start_7d,
                summary_date__lte=end_date,
                recovery_score__isnull=False,
            )
            .aggregate(avg=Avg('recovery_score'))
            .get('avg')
        )
        if recovery_avg is not None:
            if recovery_avg < 40:
                recovery_score_comp = 20
            elif recovery_avg < 50:
                recovery_score_comp = 15
            elif recovery_avg < 60:
                recovery_score_comp = 10
            elif recovery_avg < 70:
                recovery_score_comp = 5
            drivers.append({
                'component': 'recovery_low',
                'score': recovery_score_comp,
                'detail': f'7d avg recovery {recovery_avg:.0f}/100',
            })
        else:
            drivers.append({
                'component': 'recovery_low',
                'score': 0,
                'detail': 'No recovery data',
            })

        # --- Component 4: Training high (0–15) ---
        training_score = 0
        start_28d = end_date - timedelta(days=28)
        training_28d = (
            DailyHealthSummary.objects
            .filter(
                user=user,
                summary_date__gte=start_28d,
                summary_date__lte=end_date,
                training_load__isnull=False,
            )
            .aggregate(avg=Avg('training_load'))
            .get('avg')
        )
        training_7d = (
            DailyHealthSummary.objects
            .filter(
                user=user,
                summary_date__gte=start_7d,
                summary_date__lte=end_date,
                training_load__isnull=False,
            )
            .aggregate(avg=Avg('training_load'))
            .get('avg')
        )
        if training_28d and training_7d and float(training_28d) > 0:
            ratio = float(training_7d) / float(training_28d)
            if ratio > 1.5:
                training_score = 15
            elif ratio > 1.3:
                training_score = 10
            elif ratio > 1.1:
                training_score = 5
            drivers.append({
                'component': 'training_high',
                'score': training_score,
                'detail': f'7d/28d training ratio {ratio:.2f}',
            })
        else:
            drivers.append({
                'component': 'training_high',
                'score': 0,
                'detail': 'No training data',
            })

        # --- Composite ---
        total = lean_score + protein_score + recovery_score_comp + training_score

        if total >= 60:
            level = 'HIGH'
        elif total >= 30:
            level = 'MED'
        else:
            level = 'LOW'

        return {
            'risk_score': total,
            'risk_level': level,
            'drivers': drivers,
        }

    # ------------------------------------------------------------------
    # Single-call convenience for builder
    # ------------------------------------------------------------------

    @staticmethod
    def compute_daily_intelligence(user, target_date):
        """
        Compute all body composition intelligence for a single day.

        Called ONLY by DailyHealthSummaryBuilder.

        Returns dict matching DailyHealthSummary field names,
        or empty dict if insufficient data.
        """
        from apps.health.models import DailyHealthSummary

        BCI = BodyCompositionIntelligence
        result = {}

        # Get today's scan data
        scan = BCI.get_latest_scan(user, target_date)
        if scan['weight'] is None or scan['body_fat_pct'] is None:
            return result

        # Compute fat_mass for today
        fat_mass = BCI.compute_fat_mass(scan['weight'], scan['body_fat_pct'])
        if fat_mass is not None:
            result['fat_mass'] = fat_mass

        # 14-day window analysis
        metrics_14d = BCI.get_window_metrics(user, target_date, window_days=14)

        drivers = {}

        if metrics_14d['sufficient_data']:
            deltas = metrics_14d['deltas']
            window_days = metrics_14d['window_actual_days']

            # Fat loss quality
            quality = BCI.compute_fat_loss_quality(deltas, window_days)
            result['fat_loss_quality_label'] = quality['label']
            if quality['fat_loss_ratio'] is not None:
                result['fat_loss_ratio_14d'] = Decimal(str(quality['fat_loss_ratio']))
            drivers['fat_loss_quality'] = quality['explanation']

            # Recomposition
            recomp = BCI.detect_recomposition(deltas)
            result['recomposition_flag_14d'] = recomp['detected']
            if recomp['detected']:
                drivers['recomposition'] = recomp['details']

            # Fat loss speed
            start_weight = metrics_14d['start']['weight']
            speed = BCI.compute_fat_loss_speed(deltas, start_weight, window_days)
            result['fat_loss_speed_label'] = speed['label']
            if speed['rate_pct_per_week'] is not None:
                result['fat_loss_speed_pct_per_week'] = Decimal(str(speed['rate_pct_per_week']))
            drivers['fat_loss_speed'] = speed['message']

        # Plateau detection (21-day window)
        try:
            plateau = BCI.detect_plateau(user, target_date, window_days=21)
            result['plateau_status'] = plateau['status']
            if plateau['status'] not in ('INSUFFICIENT_DATA', ''):
                drivers['plateau'] = plateau['explanation']
        except Exception:
            logger.error("Failed to compute plateau status", exc_info=True)

        # Muscle loss risk
        try:
            risk = BCI.compute_muscle_loss_risk(user, target_date)
            result['muscle_loss_risk_score'] = risk['risk_score']
            result['muscle_loss_risk_level'] = risk['risk_level']
            drivers['muscle_loss_risk'] = {
                'score': risk['risk_score'],
                'level': risk['risk_level'],
                'components': risk['drivers'],
            }
        except Exception:
            logger.error("Failed to compute muscle loss risk", exc_info=True)

        result['body_comp_drivers'] = drivers

        return result
