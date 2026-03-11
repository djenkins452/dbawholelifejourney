"""
EAE — Constants & Thresholds.

All scoring weights, budget caps, escalation thresholds, and timing constants
for the Executive Arbitration Engine. Centralized here for tuning and audit.

CONFIGURATION:
    Tunable thresholds (confidence, capacity, budget, fatigue) are sourced
    from AIThresholdConfig via get_threshold(). This allows runtime tuning
    through the admin panel without code deployment. The hard-coded defaults
    below serve as safe fallbacks if the DB record is missing.

INTENSITY MULTIPLIER:
    A central scalar (default 1.0) that deterministically adjusts sensitivity
    across scoring, escalation, budget compression, and tone transitions.
    At 1.0, all behavior is baseline. Values > 1.0 increase sensitivity
    (escalate sooner, tighter budgets, firmer tone). Values < 1.0 soften.
    Future-proofed for per-user configuration via Blueprint, but not
    user-facing in Phase 8 rollout.
"""

from apps.core.ai_config import get_threshold

# =============================================================================
# INTENSITY MULTIPLIER (central tuning scalar)
# =============================================================================

# Default intensity: 1.0 = baseline behavior (no change)
# > 1.0 = more aggressive (escalate faster, tighter budgets, firmer tone)
# < 1.0 = more lenient (slower escalation, wider budgets, gentler tone)
# Clamped to [0.5, 2.0] at runtime to prevent extreme behavior
DEFAULT_INTENSITY_MULTIPLIER = 1.0
INTENSITY_MIN = 0.5
INTENSITY_MAX = 2.0


def get_intensity(user=None):
    """
    Return the intensity multiplier for a user.

    Phase 8: Always returns DEFAULT_INTENSITY_MULTIPLIER.
    Future: Will read from PersonalOperatingBlueprint or EAEState per-user.
    """
    # Future hook: read from user's Blueprint or EAEState
    # if user:
    #     try:
    #         bp = user.operating_blueprint
    #         return max(INTENSITY_MIN, min(INTENSITY_MAX, bp.eae_intensity))
    #     except Exception:
    #         pass
    return DEFAULT_INTENSITY_MULTIPLIER


def apply_intensity(value, intensity=None, inverse=False):
    """
    Apply intensity multiplier to a threshold or score.

    Args:
        value: The base value to adjust.
        intensity: Multiplier (default: DEFAULT_INTENSITY_MULTIPLIER).
        inverse: If True, divides instead of multiplies. Use for thresholds
                 where lower = more sensitive (e.g., confidence minimums,
                 de-escalation requirements). Higher intensity should LOWER
                 these thresholds, making them easier to trigger.

    Returns:
        Adjusted value. At intensity=1.0, returns value unchanged.
    """
    if intensity is None:
        intensity = DEFAULT_INTENSITY_MULTIPLIER
    intensity = max(INTENSITY_MIN, min(INTENSITY_MAX, intensity))
    if intensity == 1.0:
        return value
    if inverse:
        return value / intensity
    return value * intensity


# =============================================================================
# SCORING & NORMALIZATION WEIGHTS (§4.2 of design spec)
# =============================================================================

# Global normalization formula weights (must sum to 1.0)
WEIGHT_LOCAL_SCORE = 0.35
WEIGHT_DRIFT_ANCHOR = 0.30
WEIGHT_GOVERNANCE = 0.20
WEIGHT_RECENCY = 0.15

# Governance importance weight defaults
GOVERNANCE_NON_NEGOTIABLE = 2.0
GOVERNANCE_IMPORTANT = 1.0
GOVERNANCE_FLEXIBLE = 0.3
GOVERNANCE_UNCATEGORIZED = 0.5

# Recency decay: linear over this many hours (168h = 7 days)
RECENCY_DECAY_HOURS = 168

# Severity weights for PIE insights (maps severity -> base score)
SEVERITY_WEIGHTS = {
    'info': 10,
    'positive': 25,
    'warning': 60,
    'critical': 100,
}

# Priority weights for PGE guidance (maps priority int -> base score)
PRIORITY_WEIGHTS = {
    1: 100,  # Critical
    2: 80,   # High
    3: 50,   # Medium
    4: 25,   # Low
    5: 10,   # Info
}

# ECC commitment tier weights
ECC_TIER_WEIGHTS = {
    1: 100,
    2: 70,
    3: 40,
}

# PRIE horizon urgency multipliers
HORIZON_URGENCY = {
    7: 1.0,    # <= 7 days: full urgency
    30: 0.7,   # <= 30 days: moderate
    90: 0.4,   # <= 90 days: low
}

# =============================================================================
# CONFIDENCE THRESHOLDS (§4.3)
# =============================================================================

# Minimum confidence to surface a signal (sourced from AIThresholdConfig)
CONFIDENCE_MIN_CHAT = get_threshold("confidence_min_chat", 0.40)
CONFIDENCE_MIN_PUSH = get_threshold("confidence_min_push", 0.60)
CONFIDENCE_MIN_BRIEFING = get_threshold("confidence_min_briefing", 0.30)

# Scoring modifiers based on confidence (thresholds from AIThresholdConfig)
CONFIDENCE_HIGH_BOOST = 10      # Added to normalized score when confidence >= high threshold
CONFIDENCE_HIGH_THRESHOLD = get_threshold("confidence_high_threshold", 0.85)
CONFIDENCE_LOW_PENALTY = -15    # Added to normalized score when confidence <= low threshold
CONFIDENCE_LOW_THRESHOLD = get_threshold("confidence_low_threshold", 0.50)

# =============================================================================
# NOISE BUDGET (§5.2)
# =============================================================================

# Per-channel cognitive unit caps (chat/push from AIThresholdConfig)
BUDGET_CHAT = get_threshold("budget_chat", 3)
BUDGET_PUSH = get_threshold("budget_push", 1)
BUDGET_SMS = 1
BUDGET_EMAIL = 5
BUDGET_BRIEFING = 5
BUDGET_WEEKLY_REPORT = 7
BUDGET_COMMAND_CENTER = 999  # Unlimited for admin visibility

# Hard maximums (capacity bonus can push up to these)
BUDGET_CHAT_MAX = 5
BUDGET_PUSH_MAX = 2
BUDGET_SMS_MAX = 1
BUDGET_EMAIL_MAX = 7
BUDGET_BRIEFING_MAX = 7
BUDGET_WEEKLY_REPORT_MAX = 10

# Global daily budget across all channels (from AIThresholdConfig)
BUDGET_GLOBAL_DAILY = get_threshold("budget_global_daily", 8)

# Capacity adjustments to budget
CAPACITY_CRITICAL_ADJUSTMENT = -2   # capacity_score < 0.2
CAPACITY_LOW_ADJUSTMENT = -1        # capacity_score 0.2-0.4
CAPACITY_NORMAL_ADJUSTMENT = 0      # capacity_score 0.4-0.7
CAPACITY_HIGH_ADJUSTMENT = 1        # capacity_score > 0.7

CAPACITY_CRITICAL_THRESHOLD = 0.2
CAPACITY_LOW_THRESHOLD = get_threshold("capacity_low_threshold", 0.4)
CAPACITY_HIGH_THRESHOLD = get_threshold("capacity_high_threshold", 0.7)

# Floor: always surface at least this many items
BUDGET_FLOOR = 1

# =============================================================================
# BUNDLING (§5.3)
# =============================================================================

BUNDLE_MIN_ITEMS = 2
BUNDLE_MAX_ITEMS = 5
BUNDLE_SCORE_BONUS = 5  # Added to max(member_scores) for coherence

# =============================================================================
# CROSS-CHANNEL DEDUP (§5.4)
# =============================================================================

# Hours within which a pushed item suppresses from chat
CROSS_CHANNEL_DEDUP_HOURS = 4

# =============================================================================
# DRIFT RISK BANDS (§6.1)
# =============================================================================

DRIFT_BAND_GREEN = (0, 39)       # On Track
DRIFT_BAND_YELLOW = (40, 59)     # Attention Needed
DRIFT_BAND_ORANGE = (60, 69)     # Active Drift
DRIFT_BAND_RED = (70, 84)        # Significant Drift
DRIFT_BAND_CRITICAL = (85, 100)  # Crisis

# =============================================================================
# ESCALATION LADDER (§6.2)
# =============================================================================

ESCALATION_NOMINAL = 0
ESCALATION_ELEVATED = 1
ESCALATION_ACTIVE = 2
ESCALATION_CRITICAL = 3
ESCALATION_OVERRIDE = 4

ESCALATION_CHOICES = [
    (ESCALATION_NOMINAL, 'Nominal'),
    (ESCALATION_ELEVATED, 'Elevated'),
    (ESCALATION_ACTIVE, 'Active'),
    (ESCALATION_CRITICAL, 'Critical'),
    (ESCALATION_OVERRIDE, 'Override'),
]

# Drift thresholds for escalation level triggers
ESCALATION_DRIFT_THRESHOLDS = {
    ESCALATION_NOMINAL: 40,      # Drift < 40 → level 0
    ESCALATION_ELEVATED: 60,     # Drift 40-59 → level 1
    ESCALATION_ACTIVE: 70,       # Drift 60-69 → level 2
    ESCALATION_CRITICAL: 85,     # Drift 70-84 → level 3
    ESCALATION_OVERRIDE: 101,    # Drift 85+ → level 4
}

# Consecutive non-negotiable misses for escalation
ESCALATION_NN_MISS_ELEVATED = 2   # 2+ consecutive missed NNs → level 1
ESCALATION_NN_MISS_ACTIVE = 3     # 3+ consecutive decline days → level 2

# De-escalation requirements
DEESCALATION_DRIFT_DROP = 10      # Drift must decrease by >= 10 from peak
DEESCALATION_MIN_HOURS = 48       # Minimum hours at current level
DEESCALATION_NN_MISS_WINDOW = 48  # No new NN misses in this many hours
DEESCALATION_MIN_COMPLIANCE = 1   # At least N positive events required

# Sustained level 3 before auto-escalation to 4
ESCALATION_SUSTAINED_DAYS = 5

# =============================================================================
# PRIMARY FOCUS (§6.4)
# =============================================================================

PRIMARY_FOCUS_MAX_CHANGES = 2         # Max changes per day
PRIMARY_FOCUS_DRIFT_THRESHOLD = 15    # Drift increase needed for midday correction

# =============================================================================
# OVERRIDE STATE MACHINE (§6.5)
# =============================================================================

OVERRIDE_STRIKE_MAX = 3

# Override types
OVERRIDE_PERMANENT = 'permanent'
OVERRIDE_TEMPORARY = 'temporary'

# Cooldown durations (hours)
COOLDOWN_TEMPORARY_HOURS = 24
COOLDOWN_AMBIGUOUS_HOURS = 12

# Auto-escalation: N temporaries in M days → permanent
OVERRIDE_AUTO_ESCALATE_COUNT = 3
OVERRIDE_AUTO_ESCALATE_WINDOW_DAYS = 14

# =============================================================================
# TONE BANDS (§3.4)
# =============================================================================

TONE_REFLECTIVE_GENTLE = 'reflective_gentle'
TONE_REFLECTIVE_FIRM = 'reflective_firm'
TONE_DIRECT_CLEAR = 'direct_clear'
TONE_DIRECT_URGENT = 'direct_urgent'
TONE_EXECUTIVE_OVERRIDE = 'executive_override'

TONE_CHOICES = [
    (TONE_REFLECTIVE_GENTLE, 'Reflective Gentle'),
    (TONE_REFLECTIVE_FIRM, 'Reflective Firm'),
    (TONE_DIRECT_CLEAR, 'Direct Clear'),
    (TONE_DIRECT_URGENT, 'Direct Urgent'),
    (TONE_EXECUTIVE_OVERRIDE, 'Executive Override'),
]

# Escalation level → tone band mapping
ESCALATION_TONE_MAP = {
    ESCALATION_NOMINAL: TONE_REFLECTIVE_GENTLE,
    ESCALATION_ELEVATED: TONE_REFLECTIVE_FIRM,
    ESCALATION_ACTIVE: TONE_DIRECT_CLEAR,
    ESCALATION_CRITICAL: TONE_DIRECT_URGENT,
    ESCALATION_OVERRIDE: TONE_EXECUTIVE_OVERRIDE,
}

# =============================================================================
# CHANNEL IDENTIFIERS
# =============================================================================

CHANNEL_CHAT = 'chat'
CHANNEL_PUSH = 'push'
CHANNEL_SMS = 'sms'
CHANNEL_EMAIL = 'email'
CHANNEL_BRIEFING = 'briefing'
CHANNEL_WEEKLY_REPORT = 'weekly_report'
CHANNEL_COMMAND_CENTER = 'command_center'

CHANNEL_CHOICES = [
    (CHANNEL_CHAT, 'Chat'),
    (CHANNEL_PUSH, 'Push Notification'),
    (CHANNEL_SMS, 'SMS'),
    (CHANNEL_EMAIL, 'Email'),
    (CHANNEL_BRIEFING, 'Daily Briefing'),
    (CHANNEL_WEEKLY_REPORT, 'Weekly Report'),
    (CHANNEL_COMMAND_CENTER, 'Command Center'),
]

# Channel → default budget mapping
CHANNEL_BUDGET_MAP = {
    CHANNEL_CHAT: BUDGET_CHAT,
    CHANNEL_PUSH: BUDGET_PUSH,
    CHANNEL_SMS: BUDGET_SMS,
    CHANNEL_EMAIL: BUDGET_EMAIL,
    CHANNEL_BRIEFING: BUDGET_BRIEFING,
    CHANNEL_WEEKLY_REPORT: BUDGET_WEEKLY_REPORT,
    CHANNEL_COMMAND_CENTER: BUDGET_COMMAND_CENTER,
}

# Channel → hard max mapping
CHANNEL_BUDGET_MAX_MAP = {
    CHANNEL_CHAT: BUDGET_CHAT_MAX,
    CHANNEL_PUSH: BUDGET_PUSH_MAX,
    CHANNEL_SMS: BUDGET_SMS_MAX,
    CHANNEL_EMAIL: BUDGET_EMAIL_MAX,
    CHANNEL_BRIEFING: BUDGET_BRIEFING_MAX,
    CHANNEL_WEEKLY_REPORT: BUDGET_WEEKLY_REPORT_MAX,
    CHANNEL_COMMAND_CENTER: BUDGET_COMMAND_CENTER,
}

# Channel → minimum confidence mapping
CHANNEL_CONFIDENCE_MAP = {
    CHANNEL_CHAT: CONFIDENCE_MIN_CHAT,
    CHANNEL_PUSH: CONFIDENCE_MIN_PUSH,
    CHANNEL_SMS: CONFIDENCE_MIN_PUSH,  # Same as push
    CHANNEL_EMAIL: CONFIDENCE_MIN_CHAT,
    CHANNEL_BRIEFING: CONFIDENCE_MIN_BRIEFING,
    CHANNEL_WEEKLY_REPORT: CONFIDENCE_MIN_BRIEFING,
    CHANNEL_COMMAND_CENTER: 0.0,  # No minimum for admin
}

# =============================================================================
# DEDUP RULES (§4.4)
# =============================================================================

# Same-module, same-type signals within this window are deduped
DEDUP_SAME_DAY = True

# Overlapping prediction horizon tolerance (days)
DEDUP_PREDICTION_HORIZON_DAYS = 7

# =============================================================================
# EXPIRY RULES (§4.5)
# =============================================================================

EXPIRY_INSIGHT_INFO_HOURS = 48
EXPIRY_INSIGHT_WARNING_DAYS = 7
EXPIRY_PREDICTION_BUFFER_DAYS = 1       # predicted_date + 1 day
EXPIRY_GUIDANCE_DEFAULT_DAYS = 14
EXPIRY_CORRELATION_DAYS = 30
EXPIRY_PROTECTIVE_ALERT_HOURS = 12

# =============================================================================
# HEARTBEAT & AUDIT (§7.2)
# =============================================================================

# Maximum time between arbitrations before health degrades
HEARTBEAT_MAX_IDLE_MINUTES = 15

# Decision log retention before archival
AUDIT_RETENTION_DAYS = 90

# Override cleanup window
OVERRIDE_CLEANUP_CHECK_HOURS = 24
