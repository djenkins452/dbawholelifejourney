"""
Message Orchestrator — Centralized proactive message coordination.

Project: Whole Life Journey
Path: apps/core/cos/message_orchestrator.py
Purpose: Prevents message flooding and ensures coordinated delivery of
         proactive messages from multiple engines (PGE, DNE, TRIGGERS, etc.).

Problem solved:
    Multiple engines can independently decide to send proactive messages
    to the user. Without coordination, the user can receive:
    - Conflicting advice from different engines
    - Too many messages in a short period (fatigue)
    - Messages about the same topic from different sources

    This orchestrator acts as a single coordination point.

Usage:
    from apps.core.cos.message_orchestrator import MessageOrchestrator

    orchestrator = MessageOrchestrator(user)

    # Check if a message should be sent
    if orchestrator.should_deliver(message_type="check_in", source="PGE"):
        deliver_message(...)
        orchestrator.record_delivery(message_type="check_in", source="PGE")

    # Get delivery budget remaining
    budget = orchestrator.get_remaining_budget()

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from django.utils import timezone

logger = logging.getLogger(__name__)


# =========================================================================
# Configuration — Delivery Limits
# =========================================================================

# Maximum proactive messages per channel per time window
DELIVERY_LIMITS = {
    "push": {"per_hour": 2, "per_day": 6},
    "chat": {"per_hour": 3, "per_day": 10},
    "sms": {"per_hour": 1, "per_day": 3},
    "email": {"per_hour": 1, "per_day": 2},
    "briefing": {"per_hour": 1, "per_day": 2},
}

# Minimum spacing between messages of the same type (minutes)
MESSAGE_TYPE_COOLDOWNS = {
    "check_in": 60,          # 1 hour between check-ins
    "drift_alert": 120,       # 2 hours between drift alerts
    "protective_alert": 30,   # 30 min between protective alerts
    "guidance": 60,            # 1 hour between guidance messages
    "reflection_prompt": 180,  # 3 hours between reflection prompts
    "weekly_report": 10080,    # 7 days between weekly reports
    "briefing": 720,           # 12 hours between briefings
}

# Priority ordering for message types (higher = more important)
MESSAGE_PRIORITY = {
    "protective_alert": 100,   # Safety/deadline critical
    "drift_alert": 80,         # Behavioral drift
    "check_in": 60,            # Status check-in
    "guidance": 50,            # Proactive guidance
    "reflection_prompt": 40,   # Reflection prompts
    "briefing": 30,            # Daily briefing
    "weekly_report": 20,       # Weekly report
}


class MessageOrchestrator:
    """
    Coordinates proactive message delivery for a single user.

    Responsibilities:
    - Enforces per-channel delivery limits
    - Enforces per-type cooldown periods
    - Prioritizes competing messages
    - Tracks delivery history for fatigue protection
    - Provides delivery budget visibility
    """

    def __init__(self, user):
        self.user = user
        self._delivery_history = self._load_recent_deliveries()

    def _load_recent_deliveries(self) -> List[Dict]:
        """Load recent delivery records from the database."""
        try:
            from apps.core.ai_delivery.models import DeliveryRecord
            cutoff = timezone.now() - timedelta(hours=24)
            records = DeliveryRecord.objects.filter(
                user=self.user,
                delivered_at__gte=cutoff,
            ).values("channel", "message_type", "source_engine", "delivered_at")
            return list(records)
        except Exception:
            # Graceful degradation if model doesn't exist yet
            logger.debug(
                "MessageOrchestrator: DeliveryRecord not available, "
                "using empty history"
            )
            return []

    def should_deliver(
        self,
        message_type: str,
        channel: str = "chat",
        source: str = "",
    ) -> Tuple[bool, str]:
        """
        Check if a message should be delivered right now.

        Args:
            message_type: Type of message (e.g., "check_in", "drift_alert")
            channel: Delivery channel (e.g., "chat", "push", "sms")
            source: Source engine code (e.g., "PGE", "DNE")

        Returns:
            Tuple of (should_deliver: bool, reason: str)
        """
        now = timezone.now()

        # Check 1: Channel delivery limits
        channel_limits = DELIVERY_LIMITS.get(channel, {"per_hour": 2, "per_day": 8})

        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(hours=24)

        channel_last_hour = sum(
            1 for d in self._delivery_history
            if d.get("channel") == channel and d.get("delivered_at", day_ago) >= hour_ago
        )
        channel_last_day = sum(
            1 for d in self._delivery_history
            if d.get("channel") == channel and d.get("delivered_at", day_ago) >= day_ago
        )

        if channel_last_hour >= channel_limits["per_hour"]:
            return False, f"Channel '{channel}' hourly limit reached ({channel_last_hour}/{channel_limits['per_hour']})"

        if channel_last_day >= channel_limits["per_day"]:
            return False, f"Channel '{channel}' daily limit reached ({channel_last_day}/{channel_limits['per_day']})"

        # Check 2: Message type cooldown
        cooldown_minutes = MESSAGE_TYPE_COOLDOWNS.get(message_type, 30)
        cooldown_cutoff = now - timedelta(minutes=cooldown_minutes)

        same_type_recent = [
            d for d in self._delivery_history
            if d.get("message_type") == message_type
            and d.get("delivered_at", day_ago) >= cooldown_cutoff
        ]

        if same_type_recent:
            last_delivery = max(d.get("delivered_at", day_ago) for d in same_type_recent)
            minutes_ago = (now - last_delivery).total_seconds() / 60
            return False, (
                f"Message type '{message_type}' cooldown active "
                f"(last sent {minutes_ago:.0f}m ago, cooldown: {cooldown_minutes}m)"
            )

        return True, "OK"

    def record_delivery(
        self,
        message_type: str,
        channel: str = "chat",
        source: str = "",
        metadata: Optional[Dict] = None,
    ):
        """
        Record a message delivery for tracking.

        Args:
            message_type: Type of message delivered
            channel: Channel used
            source: Source engine code
            metadata: Optional delivery metadata
        """
        delivery = {
            "channel": channel,
            "message_type": message_type,
            "source_engine": source,
            "delivered_at": timezone.now(),
        }
        self._delivery_history.append(delivery)

        # Persist to database if available
        try:
            from apps.core.ai_delivery.models import DeliveryRecord
            DeliveryRecord.objects.create(
                user=self.user,
                channel=channel,
                message_type=message_type,
                source_engine=source,
                metadata=metadata or {},
            )
        except Exception:
            # Model may not exist yet — just track in-memory
            logger.debug(
                "MessageOrchestrator: DeliveryRecord save skipped (model not available)"
            )

        logger.info(
            "Message delivered: user=%s type=%s channel=%s source=%s",
            self.user.id if hasattr(self.user, 'id') else 'unknown',
            message_type, channel, source,
        )

    def get_remaining_budget(self) -> Dict[str, Dict[str, int]]:
        """
        Get remaining delivery budget per channel.

        Returns:
            Dict of channel -> {"per_hour": remaining, "per_day": remaining}
        """
        now = timezone.now()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(hours=24)

        budget = {}
        for channel, limits in DELIVERY_LIMITS.items():
            sent_hour = sum(
                1 for d in self._delivery_history
                if d.get("channel") == channel
                and d.get("delivered_at", day_ago) >= hour_ago
            )
            sent_day = sum(
                1 for d in self._delivery_history
                if d.get("channel") == channel
                and d.get("delivered_at", day_ago) >= day_ago
            )
            budget[channel] = {
                "per_hour": max(0, limits["per_hour"] - sent_hour),
                "per_day": max(0, limits["per_day"] - sent_day),
            }
        return budget

    def prioritize_messages(
        self, messages: List[Dict]
    ) -> List[Dict]:
        """
        Sort competing messages by priority.

        Each message dict should have at least:
            - "message_type": str
            - "content": str
            - "source": str (engine code)

        Returns messages sorted by priority (highest first),
        with duplicates by type removed (keeps highest priority source).
        """
        # Sort by priority (higher = more important)
        sorted_msgs = sorted(
            messages,
            key=lambda m: MESSAGE_PRIORITY.get(m.get("message_type", ""), 0),
            reverse=True,
        )

        # Deduplicate by message type (keep first = highest priority)
        seen_types = set()
        deduplicated = []
        for msg in sorted_msgs:
            msg_type = msg.get("message_type", "unknown")
            if msg_type not in seen_types:
                seen_types.add(msg_type)
                deduplicated.append(msg)

        return deduplicated

    def get_orchestration_summary(self) -> Dict:
        """Get summary for observability/debugging."""
        return {
            "user_id": self.user.id if hasattr(self.user, 'id') else None,
            "deliveries_last_24h": len(self._delivery_history),
            "budget_remaining": self.get_remaining_budget(),
            "delivery_limits": DELIVERY_LIMITS,
            "message_cooldowns": MESSAGE_TYPE_COOLDOWNS,
        }
