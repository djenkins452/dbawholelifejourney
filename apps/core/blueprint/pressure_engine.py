"""
Phase 4 — Deterministic Pressure Engine.

Computes forward-looking pressure components and the Composite Pressure
Index (CPI). All functions are deterministic — no randomness, no LLM calls.

Components:
    A) Calendar density (scheduled_minutes / available_minutes)
    B) Workload compression (flexible blocks vs free time)
    C) Habit breach probability (Tier 1 override history + density)
    D) Goal trajectory erosion (required_rate vs actual_rate)
    E) Deadline collision detection (72h window clustering)
    F) Composite Pressure Index (weighted sum, 0–100)

Horizon sensitivity:
    0–7 days: full precision
    8–14 days: moderate (×0.6)
    15–30 days: early warning only (×0.3)

Project: Whole Life Journey
Path: apps/core/blueprint/pressure_engine.py
"""

import datetime as dt
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

# Available window for scheduling (7:00 – 22:00 = 15 hours = 900 minutes)
DAY_START_HOUR = 7
DAY_END_HOUR = 22
AVAILABLE_MINUTES_PER_DAY = (DAY_END_HOUR - DAY_START_HOUR) * 60  # 900

# Horizon attenuation factors
HORIZON_FULL = 7       # days 0-7: full precision (×1.0)
HORIZON_MODERATE = 14  # days 8-14: moderate (×0.6)
HORIZON_EARLY = 30     # days 15-30: early warning (×0.3)

ATTENUATION_FULL = 1.0
ATTENUATION_MODERATE = 0.6
ATTENUATION_EARLY = 0.3

# Thresholds
OVERLOADED_DAY_THRESHOLD = 0.8  # >80% density = overloaded day
COMPRESSION_RATIO = 1.2         # flexible > free × 1.2 = compressed


def _horizon_attenuation(horizon_days):
    """Return attenuation factor based on forecast horizon."""
    if horizon_days <= HORIZON_FULL:
        return ATTENUATION_FULL
    elif horizon_days <= HORIZON_MODERATE:
        return ATTENUATION_MODERATE
    else:
        return ATTENUATION_EARLY


# =========================================================================
# A) Calendar Density
# =========================================================================

def compute_calendar_density(user, horizon_days=7):
    """
    Compute calendar density over the forecast horizon.

    Density = scheduled_minutes / available_minutes for each day.
    Clamped to 0–1. Days with >0.8 are flagged as overloaded.

    Args:
        user: User instance.
        horizon_days: Number of days to look ahead (default: 7).

    Returns:
        float — Density score (0.0–1.0).
    """
    from .models import ArchitecturePlan

    today = timezone.localdate()
    total_scheduled = 0
    total_available = 0
    overloaded_days = 0

    for offset in range(horizon_days):
        target_date = today + dt.timedelta(days=offset)
        plan = ArchitecturePlan.get_active_for_date(user, target_date)

        day_minutes = 0
        if plan:
            for block in plan.blocks.all():
                if block.start_time and block.end_time:
                    start_dt = dt.datetime.combine(target_date, block.start_time)
                    end_dt = dt.datetime.combine(target_date, block.end_time)
                    delta = (end_dt - start_dt).total_seconds() / 60
                    if delta > 0:
                        day_minutes += delta

        day_density = min(1.0, day_minutes / AVAILABLE_MINUTES_PER_DAY)
        if day_density > OVERLOADED_DAY_THRESHOLD:
            overloaded_days += 1

        total_scheduled += day_minutes
        total_available += AVAILABLE_MINUTES_PER_DAY

    if total_available == 0:
        return 0.0

    raw_density = total_scheduled / total_available
    attenuation = _horizon_attenuation(horizon_days)
    return min(1.0, raw_density * attenuation)


# =========================================================================
# B) Workload Compression
# =========================================================================

def compute_compression(user, horizon_days=7):
    """
    Detect workload compression.

    If flexible block time exceeds remaining free time × 1.2, the schedule
    is compressed. Score 0–1 based on severity.

    Args:
        user: User instance.
        horizon_days: Number of days to look ahead.

    Returns:
        float — Compression score (0.0–1.0).
    """
    from .models import ArchitecturePlan

    today = timezone.localdate()
    total_flexible_minutes = 0
    total_free_minutes = 0

    for offset in range(horizon_days):
        target_date = today + dt.timedelta(days=offset)
        plan = ArchitecturePlan.get_active_for_date(user, target_date)

        day_scheduled = 0
        day_flexible = 0

        if plan:
            for block in plan.blocks.all():
                if block.start_time and block.end_time:
                    start_dt = dt.datetime.combine(target_date, block.start_time)
                    end_dt = dt.datetime.combine(target_date, block.end_time)
                    delta = (end_dt - start_dt).total_seconds() / 60
                    if delta > 0:
                        day_scheduled += delta
                        # Tier 3 and 4 blocks are considered flexible
                        if block.tier >= 3:
                            day_flexible += delta

        day_free = max(0, AVAILABLE_MINUTES_PER_DAY - day_scheduled)
        total_flexible_minutes += day_flexible
        total_free_minutes += day_free

    # If no flexible blocks, no compression
    if total_flexible_minutes == 0:
        return 0.0

    # Compression threshold: flexible > free × 1.2
    threshold = total_free_minutes * COMPRESSION_RATIO
    if total_flexible_minutes <= threshold:
        return 0.0

    # Score scales from 0 at threshold to 1.0 at 2× threshold
    overshoot = total_flexible_minutes - threshold
    max_overshoot = threshold if threshold > 0 else total_flexible_minutes
    raw_score = min(1.0, overshoot / max(max_overshoot, 1))

    attenuation = _horizon_attenuation(horizon_days)
    return raw_score * attenuation


# =========================================================================
# C) Habit Breach Probability (Deterministic)
# =========================================================================

def compute_breach_probability(user, horizon_days=7):
    """
    Compute deterministic habit breach probability.

    Based on:
    - Historical Tier 1 override frequency (14-day lookback)
    - Calendar density around protected blocks
    - Recent drift events on Tier 1 behaviors

    Args:
        user: User instance.
        horizon_days: Forecast horizon.

    Returns:
        float — Breach probability (0.0–1.0).
    """
    from .models import ArchitecturePlan, DriftEvent, Tier1OverrideEvent

    now = timezone.now()
    lookback_14d = now - dt.timedelta(days=14)
    lookback_7d = now - dt.timedelta(days=7)

    # Factor 1: Tier 1 override frequency (0–1)
    override_count = Tier1OverrideEvent.objects.filter(
        user=user,
        created_at__gte=lookback_14d,
    ).count()
    # 4+ overrides in 14 days → max score
    override_factor = min(1.0, override_count / 4.0)

    # Factor 2: Density around protected blocks in horizon
    today = timezone.localdate()
    protected_density_score = 0.0
    protected_days_checked = 0

    for offset in range(min(horizon_days, HORIZON_FULL)):
        target_date = today + dt.timedelta(days=offset)
        plan = ArchitecturePlan.get_active_for_date(user, target_date)
        if not plan:
            continue

        blocks = list(plan.blocks.all())
        tier1_blocks = [b for b in blocks if b.tier == 1]
        if not tier1_blocks:
            continue

        protected_days_checked += 1

        # Total scheduled minutes for this day
        day_minutes = 0
        for b in blocks:
            if b.start_time and b.end_time:
                start_dt = dt.datetime.combine(target_date, b.start_time)
                end_dt = dt.datetime.combine(target_date, b.end_time)
                delta = (end_dt - start_dt).total_seconds() / 60
                if delta > 0:
                    day_minutes += delta

        day_density = min(1.0, day_minutes / AVAILABLE_MINUTES_PER_DAY)
        if day_density > 0.7:  # High density around protected blocks
            protected_density_score += day_density

    if protected_days_checked > 0:
        density_factor = min(1.0, protected_density_score / protected_days_checked)
    else:
        density_factor = 0.0

    # Factor 3: Recent Tier 1 drift events (7-day lookback)
    tier1_drifts = DriftEvent.objects.filter(
        user=user,
        tier=1,
        date__gte=lookback_7d.date(),
    ).count()
    # 3+ Tier 1 drifts in 7 days → max score
    drift_factor = min(1.0, tier1_drifts / 3.0)

    # Weighted combination: overrides 0.4, density 0.3, drift 0.3
    raw_score = (
        override_factor * 0.4
        + density_factor * 0.3
        + drift_factor * 0.3
    )

    attenuation = _horizon_attenuation(horizon_days)
    return min(1.0, raw_score * attenuation)


# =========================================================================
# D) Goal Trajectory Erosion
# =========================================================================

def compute_goal_erosion(user, horizon_days=7):
    """
    Detect goal trajectory erosion.

    For each active goal with a target_date:
    - required_rate = remaining_work / days_remaining
    - actual_rate = work_done / days_elapsed
    - Stage 1 (Momentum slowing): actual_rate declining but still on track
    - Stage 2 (Off-track): actual_rate < required_rate

    Output: normalized score 0–1.

    Args:
        user: User instance.
        horizon_days: Forecast horizon.

    Returns:
        float — Erosion score (0.0–1.0).
    """
    try:
        from apps.purpose.models import LifeGoal
    except ImportError:
        return 0.0

    today = timezone.localdate()
    goals = LifeGoal.objects.filter(
        user=user,
        status='active',
        target_date__isnull=False,
    )

    if not goals.exists():
        return 0.0

    erosion_scores = []

    for goal in goals:
        target_date = goal.target_date
        days_remaining = (target_date - today).days

        # Skip goals with no time pressure in horizon
        if days_remaining > horizon_days * 2:
            continue

        # Skip goals already past due (handled by deadline engine)
        if days_remaining <= 0:
            erosion_scores.append(1.0)
            continue

        # Progress-based erosion
        progress = goal.milestone_progress_percent  # 0-100
        total_days = max(1, (target_date - goal.created_at.date()).days)
        days_elapsed = max(1, total_days - days_remaining)

        # Required rate = remaining progress / remaining days
        remaining_progress = 100 - progress
        required_rate = remaining_progress / max(1, days_remaining)

        # Actual rate = progress / days elapsed
        actual_rate = progress / days_elapsed

        if actual_rate >= required_rate:
            # On track — check for momentum slowing (Stage 1)
            # Compare required_rate vs actual_rate ratio
            ratio = actual_rate / max(required_rate, 0.01)
            if ratio < 1.5:
                # Momentum slowing but still on track
                erosion_scores.append(0.3)
            else:
                erosion_scores.append(0.0)
        else:
            # Off-track (Stage 2)
            # How far behind: ratio of actual/required (inverted)
            if required_rate > 0:
                behind_ratio = 1.0 - min(1.0, actual_rate / required_rate)
            else:
                behind_ratio = 0.0
            # Scale: 0.5 (slightly behind) to 1.0 (severely behind)
            erosion_scores.append(0.5 + behind_ratio * 0.5)

    if not erosion_scores:
        return 0.0

    # Average erosion across all tracked goals
    raw_score = sum(erosion_scores) / len(erosion_scores)
    attenuation = _horizon_attenuation(horizon_days)
    return min(1.0, raw_score * attenuation)


# =========================================================================
# E) Deadline Collision Detection
# =========================================================================

def compute_deadline_collisions(user, horizon_days=7):
    """
    Detect deadline collisions in the forecast window.

    Scans deadlines in the horizon for:
    - <2h gap between hard deadlines
    - >3 hard deadlines on the same day

    Normalizes to 0–1.

    Args:
        user: User instance.
        horizon_days: Forecast horizon.

    Returns:
        float — Collision score (0.0–1.0).
    """
    from .models import Commitment, DeadlineSnapshot

    # Use the latest deadline snapshot if available and fresh
    snapshot = DeadlineSnapshot.latest_for_user(user)
    if snapshot and not snapshot.is_stale():
        collision_flags = snapshot.collision_flags or []
        if not collision_flags:
            return 0.0

        pair_collisions = sum(
            1 for f in collision_flags if f.get('type') == 'pair_collision'
        )
        daily_overloads = sum(
            1 for f in collision_flags if f.get('type') == 'daily_overload'
        )

        # Each pair collision = 0.2, each daily overload = 0.3
        raw_score = min(1.0, pair_collisions * 0.2 + daily_overloads * 0.3)
        attenuation = _horizon_attenuation(horizon_days)
        return raw_score * attenuation

    # Fallback: compute directly from commitments + goals
    now = timezone.now()
    horizon_end = now + dt.timedelta(days=min(horizon_days, HORIZON_FULL))
    all_deadlines = []

    # Pending commitments
    pending = Commitment.pending_for_user(user)
    for c in pending:
        if c.time_boundary and now <= c.time_boundary <= horizon_end:
            all_deadlines.append(c.time_boundary)

    # Goal deadlines
    try:
        from apps.purpose.models import LifeGoal
        goals = LifeGoal.objects.filter(
            user=user,
            status='active',
            target_date__isnull=False,
        )
        for g in goals:
            goal_dt = dt.datetime.combine(
                g.target_date, dt.time(23, 59),
                tzinfo=timezone.get_current_timezone(),
            )
            if now <= goal_dt <= horizon_end:
                all_deadlines.append(goal_dt)
    except ImportError:
        pass

    if len(all_deadlines) < 2:
        return 0.0

    # Sort and detect collisions
    sorted_deadlines = sorted(all_deadlines)
    pair_collisions = 0
    for i in range(len(sorted_deadlines) - 1):
        gap_hours = (
            sorted_deadlines[i + 1] - sorted_deadlines[i]
        ).total_seconds() / 3600
        if gap_hours < 2:
            pair_collisions += 1

    # Daily overload detection
    from collections import Counter
    day_counts = Counter(d.date() for d in sorted_deadlines)
    daily_overloads = sum(1 for count in day_counts.values() if count > 3)

    raw_score = min(1.0, pair_collisions * 0.2 + daily_overloads * 0.3)
    attenuation = _horizon_attenuation(horizon_days)
    return raw_score * attenuation


# =========================================================================
# F) Composite Pressure Index
# =========================================================================

def compute_pressure_index(user, horizon_days=7):
    """
    Compute the Composite Pressure Index (0–100).

    Fetches active weight config and computes weighted sum of all
    component scores.

    Args:
        user: User instance.
        horizon_days: Forecast horizon.

    Returns:
        dict — {
            'pressure_index': int (0–100),
            'density_score': float,
            'compression_score': float,
            'breach_risk_score': float,
            'erosion_score': float,
            'collision_score': float,
        }
    """
    from .pressure_models import PressureWeightConfig

    # Compute all components
    density = compute_calendar_density(user, horizon_days)
    compression = compute_compression(user, horizon_days)
    breach = compute_breach_probability(user, horizon_days)
    erosion = compute_goal_erosion(user, horizon_days)
    collision = compute_deadline_collisions(user, horizon_days)

    # Fetch active weights
    config = PressureWeightConfig.get_active()

    # Weighted sum: each component is 0–1, weight is 0–100
    # Formula: sum(component × weight) → 0–100
    index = (
        density * config.density_weight
        + compression * config.compression_weight
        + breach * config.breach_weight
        + erosion * config.erosion_weight
        + collision * config.collision_weight
    )

    # Clamp to 0–100 integer
    pressure_index = max(0, min(100, round(index)))

    return {
        'pressure_index': pressure_index,
        'density_score': round(density, 4),
        'compression_score': round(compression, 4),
        'breach_risk_score': round(breach, 4),
        'erosion_score': round(erosion, 4),
        'collision_score': round(collision, 4),
    }


# =========================================================================
# Snapshot Persistence (Step 3)
# =========================================================================

def update_pressure_snapshot(user, horizon_days=7):
    """
    Compute all pressure components and persist a new PressureSnapshot.

    Does NOT overwrite previous snapshots — always creates a new record.
    Stores baseline variance in metadata for future adaptive use.

    Non-blocking on failure: logs errors but does not raise.

    Args:
        user: User instance.
        horizon_days: Forecast horizon (default: 7).

    Returns:
        PressureSnapshot instance, or None on failure.
    """
    from .pressure_models import PressureSnapshot

    try:
        result = compute_pressure_index(user, horizon_days)

        # Compute baseline variance (for future adaptive thresholds)
        baseline_variance = _compute_baseline_variance(user, result)

        snapshot = PressureSnapshot.objects.create(
            user=user,
            pressure_index=result['pressure_index'],
            density_score=result['density_score'],
            compression_score=result['compression_score'],
            breach_risk_score=result['breach_risk_score'],
            erosion_score=result['erosion_score'],
            collision_score=result['collision_score'],
            horizon_days=horizon_days,
            computed_at=timezone.now(),
            metadata={
                'baseline_variance': baseline_variance,
                'component_details': {
                    'density': result['density_score'],
                    'compression': result['compression_score'],
                    'breach': result['breach_risk_score'],
                    'erosion': result['erosion_score'],
                    'collision': result['collision_score'],
                },
            },
        )

        logger.info(
            "Phase 4: PressureSnapshot created for user %s — "
            "index=%d, horizon=%dd",
            user.pk, result['pressure_index'], horizon_days,
        )
        return snapshot

    except Exception as e:
        logger.warning(
            "Phase 4: Failed to create PressureSnapshot for user %s: %s",
            user.pk, e,
        )
        return None


def _compute_baseline_variance(user, current_result):
    """
    Compute variance from recent snapshots for future adaptive thresholds.

    Compares current pressure_index against the last 7 snapshots.
    Stored in metadata for Phase 5+ adaptive behavior.

    Returns:
        dict — variance metrics.
    """
    from .pressure_models import PressureSnapshot

    recent = list(
        PressureSnapshot.objects.filter(user=user)
        .order_by('-computed_at')[:7]
        .values_list('pressure_index', flat=True)
    )

    if len(recent) < 2:
        return {'sample_size': len(recent), 'mean': 0, 'std_dev': 0}

    mean = sum(recent) / len(recent)
    variance = sum((x - mean) ** 2 for x in recent) / len(recent)
    std_dev = variance ** 0.5

    return {
        'sample_size': len(recent),
        'mean': round(mean, 2),
        'std_dev': round(std_dev, 2),
        'current_delta': round(current_result['pressure_index'] - mean, 2),
    }
