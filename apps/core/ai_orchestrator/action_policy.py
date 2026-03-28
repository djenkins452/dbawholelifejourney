"""
Action Policy Registry — Centralized governance for all AI-initiated actions.

Single source of truth for risk levels, categories, confirmation requirements,
authority boundaries, and rate limits for every registered intent.

Replaces the scattered PASSTHROUGH_INTENTS frozenset with a structured,
inspectable policy model. All governance decisions (confirm? block? rate-limit?)
flow through get_policy().

Pipeline position:
    Intent Recognition → Action Policy → CRUD Gate → Safety Engine → Execution
"""

import logging
import time as _time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple

from django.core.cache import cache

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────


class ActionCategory(str, Enum):
    """What kind of operation this action performs."""
    READ = 'read'               # Fetch data, no side effects
    NAVIGATE = 'navigate'       # UI navigation, no data change
    LOG = 'log'                 # Record a metric/event (append-only)
    CREATE = 'create'           # Create a new entity
    MUTATE = 'mutate'           # Update an existing entity
    DESTRUCTIVE = 'destructive' # Delete / bulk-modify
    CONTROL = 'control'         # System state (learning mode, calibration)
    SYSTEM = 'system'           # Undo, edit-last, meta-operations


class RiskLevel(str, Enum):
    """How risky this action is if executed incorrectly."""
    NONE = 'none'           # No risk (reads, navigation)
    LOW = 'low'             # Low risk (append-only logs)
    MEDIUM = 'medium'       # Medium risk (creates — reversible but noisy)
    HIGH = 'high'           # High risk (mutations — changes existing data)
    CRITICAL = 'critical'   # Critical (deletes, bulk ops — hard to undo)


class AuthorityLevel(str, Enum):
    """Whether Beth can execute this automatically."""
    AUTO = 'auto'           # Execute without asking (reads, navigation, control)
    CONFIRM = 'confirm'     # Requires user confirmation before execution
    BLOCKED = 'blocked'     # Never auto-execute (reserved for admin-only ops)


# ── Policy Dataclass ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ActionPolicy:
    """Governance policy for a single intent type."""
    intent_type: str
    category: ActionCategory
    risk_level: RiskLevel
    authority: AuthorityLevel
    label: str = ''
    max_per_message: int = 5
    max_per_minute: int = 10
    requires_explicit_verb: bool = False  # Destructive: user must say delete/remove

    def __repr__(self):
        return (
            f"ActionPolicy({self.intent_type!r}, "
            f"cat={self.category.value}, risk={self.risk_level.value}, "
            f"auth={self.authority.value})"
        )


# ── Policy Registry ───────────────────────────────────────────────────
# Every registered intent gets an entry. Unknown intents get a safe default.

ACTION_POLICY: Dict[str, ActionPolicy] = {}


def _r(intent, cat, risk, auth, label='', **kw):
    """Shorthand to register a policy entry."""
    ACTION_POLICY[intent] = ActionPolicy(
        intent_type=intent,
        category=cat,
        risk_level=risk,
        authority=auth,
        label=label,
        **kw,
    )


# ── Read-only (auto-execute, no confirmation) ─────────────────────────

_r('read_task', ActionCategory.READ, RiskLevel.NONE, AuthorityLevel.AUTO,
   label='Look up tasks')
_r('read_calendar_events', ActionCategory.READ, RiskLevel.NONE, AuthorityLevel.AUTO,
   label='Look up calendar events')
_r('query_event_history', ActionCategory.READ, RiskLevel.NONE, AuthorityLevel.AUTO,
   label='Query event history')
_r('check_budget', ActionCategory.READ, RiskLevel.NONE, AuthorityLevel.AUTO,
   label='Check budget')

# ── Control plane (auto-execute) ──────────────────────────────────────

_r('enter_learning_mode', ActionCategory.CONTROL, RiskLevel.NONE, AuthorityLevel.AUTO,
   label='Enter Learning Mode')
_r('exit_learning_mode', ActionCategory.CONTROL, RiskLevel.NONE, AuthorityLevel.AUTO,
   label='Exit Learning Mode')
_r('pause_calibration', ActionCategory.CONTROL, RiskLevel.NONE, AuthorityLevel.AUTO,
   label='Pause calibration')
_r('complete_calibration', ActionCategory.CONTROL, RiskLevel.NONE, AuthorityLevel.AUTO,
   label='Complete calibration')
_r('no_action', ActionCategory.CONTROL, RiskLevel.NONE, AuthorityLevel.AUTO,
   label='No action')

# ── Log operations (low risk, confirm) ────────────────────────────────

_r('log_weight', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log weight')
_r('log_blood_pressure', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log blood pressure')
_r('log_heart_rate', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log heart rate')
_r('log_glucose', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log blood sugar')
_r('log_blood_oxygen', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log blood oxygen')
_r('log_body_measurement', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log body measurement')
_r('log_food', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log food')
_r('log_sleep', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log sleep')
_r('log_water', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log water intake')
_r('log_steps', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log steps')
_r('take_medicine', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Mark medicine taken')
_r('take_medicines_by_time', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Mark medicines taken')
_r('start_fast', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Start fast')
_r('end_fast', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='End fast')
_r('log_prayer', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log prayer')
_r('log_habit', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log habit')
_r('log_workout', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log workout')
_r('log_exercise_set', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log exercise set')
_r('log_cardio', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log cardio session')
_r('log_transaction', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log transaction')
_r('log_transformation_protocol', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Log transformation')
_r('log_shopping_item', ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Add shopping item')

# ── Create operations (medium risk, confirm) ──────────────────────────

_r('create_task', ActionCategory.CREATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Create task')
_r('create_routine_task', ActionCategory.CREATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Create routine task')
_r('create_event', ActionCategory.CREATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Create calendar event')
_r('create_goal', ActionCategory.CREATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Create goal')
_r('set_intention', ActionCategory.CREATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Set intention')
_r('add_reminder', ActionCategory.CREATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Add reminder')
_r('create_journal_entry', ActionCategory.CREATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Create journal entry')
_r('add_gratitude', ActionCategory.CREATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Log gratitude')
_r('add_faith_milestone', ActionCategory.CREATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Add faith milestone')
_r('save_verse', ActionCategory.CREATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Save verse')

# ── Mutate operations (high risk, confirm) ────────────────────────────

_r('mutate_task', ActionCategory.MUTATE, RiskLevel.HIGH, AuthorityLevel.CONFIRM,
   label='Update task')
_r('mutate_calendar_event', ActionCategory.MUTATE, RiskLevel.HIGH, AuthorityLevel.CONFIRM,
   label='Update calendar event')
_r('complete_task', ActionCategory.MUTATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Complete task')
_r('skip_task', ActionCategory.MUTATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Skip task')
_r('mark_prayer_answered', ActionCategory.MUTATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Mark prayer answered')
_r('update_goal_progress', ActionCategory.MUTATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Update goal progress')
_r('complete_shopping_item', ActionCategory.MUTATE, RiskLevel.LOW, AuthorityLevel.CONFIRM,
   label='Mark shopping item purchased')
_r('reschedule_routine_item', ActionCategory.MUTATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Reschedule routine item')

# ── Settings (medium risk, confirm) ───────────────────────────────────

_r('set_cos_name', ActionCategory.MUTATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Change assistant name')
_r('email_medicine_list', ActionCategory.MUTATE, RiskLevel.MEDIUM, AuthorityLevel.CONFIRM,
   label='Email medicine list')

# ── System (high risk, confirm) ───────────────────────────────────────

_r('undo_last_action', ActionCategory.SYSTEM, RiskLevel.HIGH, AuthorityLevel.CONFIRM,
   label='Undo last action')
_r('edit_last_entry', ActionCategory.SYSTEM, RiskLevel.HIGH, AuthorityLevel.CONFIRM,
   label='Edit last entry')

# Clean up helper
del _r


# ── Backward Compatibility ────────────────────────────────────────────
# Computed frozenset matching the old PASSTHROUGH_INTENTS shape so any
# code that imports it directly continues to work.

PASSTHROUGH_INTENTS = frozenset(
    k for k, v in ACTION_POLICY.items()
    if v.authority == AuthorityLevel.AUTO
)


# ── Policy Lookup Functions ───────────────────────────────────────────

# Safe default for unknown intents: treat as high-risk mutation requiring confirmation.
_DEFAULT_POLICY = ActionPolicy(
    intent_type='_unknown',
    category=ActionCategory.MUTATE,
    risk_level=RiskLevel.HIGH,
    authority=AuthorityLevel.CONFIRM,
    label='Unknown action',
)


def get_policy(intent_type: str) -> ActionPolicy:
    """
    Get the governance policy for an intent.

    Unknown intents get a safe default (HIGH risk, CONFIRM required).
    """
    return ACTION_POLICY.get(intent_type, _DEFAULT_POLICY)


def requires_confirmation(intent_type: str) -> bool:
    """
    Drop-in replacement for crud_confirmation.requires_confirmation().

    Returns True if user must confirm before execution.
    """
    return get_policy(intent_type).authority != AuthorityLevel.AUTO


def is_destructive(intent_type: str, parameters: Optional[dict] = None) -> bool:
    """
    Check if a specific action invocation is destructive.

    Static check via policy category PLUS dynamic check for
    mutate_task/mutate_calendar_event with action=delete.
    """
    policy = get_policy(intent_type)
    if policy.category == ActionCategory.DESTRUCTIVE:
        return True
    # Dynamic: mutate with delete action is destructive
    if intent_type in ('mutate_task', 'mutate_calendar_event'):
        if parameters and parameters.get('action') == 'delete':
            return True
    return False


def get_risk_level(intent_type: str, parameters: Optional[dict] = None) -> RiskLevel:
    """
    Get effective risk level, accounting for dynamic escalation.

    Mutate intents with delete action escalate to CRITICAL.
    """
    policy = get_policy(intent_type)
    if is_destructive(intent_type, parameters):
        return RiskLevel.CRITICAL
    return policy.risk_level


# ── Rate Limiter ──────────────────────────────────────────────────────


class ActionRateLimiter:
    """
    Per-user action rate limiting using Django cache.

    Prevents accidental or runaway multiple actions:
    - max 2 destructive actions per minute
    - max 10 general actions per minute
    - max 5 actions per single message (enforced by caller)
    """

    # Defaults (runtime values from AIThresholdConfig)
    MAX_DESTRUCTIVE_PER_MINUTE = 2
    MAX_GENERAL_PER_MINUTE = 10
    MAX_ACTIONS_PER_MESSAGE = 5

    @classmethod
    def _get_limits(cls):
        """Load rate limits from AIThresholdConfig at runtime."""
        from apps.core.ai_config import get_threshold

        return (
            get_threshold("max_destructive_per_minute", cls.MAX_DESTRUCTIVE_PER_MINUTE),
            get_threshold("max_general_per_minute", cls.MAX_GENERAL_PER_MINUTE),
            get_threshold("max_actions_per_message", cls.MAX_ACTIONS_PER_MESSAGE),
        )

    @staticmethod
    def _minute_key() -> str:
        """Current minute bucket for rate limiting."""
        return str(int(_time.time()) // 60)

    @classmethod
    def check_rate_limit(
        cls,
        user,
        intent_type: str,
        parameters: Optional[dict] = None,
    ) -> Tuple[bool, str]:
        """
        Check if the action is within rate limits.

        Returns:
            (allowed, reason_if_blocked)
        """
        minute = cls._minute_key()
        max_destructive, max_general, _ = cls._get_limits()

        # Destructive rate limit
        if is_destructive(intent_type, parameters):
            key = f"action_rate:destructive:{user.id}:{minute}"
            count = cache.get(key, 0)
            if count >= max_destructive:
                logger.warning(
                    "[RATE_LIMIT] Destructive limit hit: user=%s intent=%s count=%d",
                    user.id, intent_type, count,
                )
                return False, (
                    "You've made several changes quickly. "
                    "Take a moment, then try again."
                )
            cache.set(key, count + 1, 120)

        # General rate limit
        key = f"action_rate:general:{user.id}:{minute}"
        count = cache.get(key, 0)
        if count >= max_general:
            logger.warning(
                "[RATE_LIMIT] General limit hit: user=%s intent=%s count=%d",
                user.id, intent_type, count,
            )
            return False, (
                "That's a lot of actions in a short time. "
                "Please wait a moment."
            )
        cache.set(key, count + 1, 120)

        return True, ''

    @classmethod
    def check_message_limit(cls, action_count: int) -> Tuple[bool, str]:
        """
        Check per-message action count limit.

        Called by the orchestrator before processing each action in a batch.
        """
        _, _, max_per_msg = cls._get_limits()
        if action_count >= max_per_msg:
            return False, (
                f"That's a lot of actions at once (max {max_per_msg}). "
                "Try breaking it into smaller requests."
            )
        return True, ''
