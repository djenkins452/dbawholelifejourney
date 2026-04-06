"""
Action Contracts — Structured response metadata for CoS actions.

Defines the ActionContract dataclass that enriches action results with:
- Navigation URLs (where to see the result)
- Follow-up actions (suggested next steps)
- Display hints (icons, formatting)

Project: Whole Life Journey
Path: apps/core/ai_orchestrator/action_contracts.py
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from apps.core.ai_orchestrator.url_resolver import (
    build_action_url_metadata,
    resolve_intent_url,
    resolve_module_url,
)

logger = logging.getLogger(__name__)


@dataclass
class ActionLink:
    """A clickable link/button to include in the response."""
    url: str
    label: str
    style: str = "link"  # "link", "button", "button_primary"
    icon: str = ""       # Optional icon hint (e.g., "chart", "list", "calendar")

    def to_dict(self) -> dict:
        result = {"url": self.url, "label": self.label, "style": self.style}
        if self.icon:
            result["icon"] = self.icon
        return result


@dataclass
class ActionContract:
    """
    Enriched metadata for an action result.

    Attached to action responses to give the frontend structured
    navigation and follow-up information.
    """
    intent_type: str
    success: bool
    message: str
    # Navigation
    view_url: Optional[str] = None       # URL to view the result
    view_label: Optional[str] = None     # Label for the view link
    detail_url: Optional[str] = None     # URL to specific entity
    # Follow-ups
    follow_up_links: List[ActionLink] = field(default_factory=list)
    # Display
    icon: str = ""                       # Icon hint for the action type

    def to_dict(self) -> dict:
        result = {
            "intent_type": self.intent_type,
            "success": self.success,
            "message": self.message,
        }
        if self.view_url:
            result["view_url"] = self.view_url
            result["view_label"] = self.view_label or "View"
        if self.detail_url:
            result["detail_url"] = self.detail_url
        if self.follow_up_links:
            result["follow_up_links"] = [link.to_dict() for link in self.follow_up_links]
        if self.icon:
            result["icon"] = self.icon
        return result


# ---------------------------------------------------------------------------
# Intent → Icon Mapping
# ---------------------------------------------------------------------------

INTENT_ICONS: Dict[str, str] = {
    "log_weight": "scale",
    "log_heart_rate": "heart",
    "log_blood_pressure": "heart",
    "log_glucose": "droplet",
    "log_food": "utensils",
    "log_sleep": "moon",
    "log_water": "droplet",
    "log_steps": "footprints",
    "log_workout": "dumbbell",
    "log_exercise_set": "dumbbell",
    "log_cardio": "running",
    "create_journal_entry": "book",
    "add_gratitude": "star",
    "log_prayer": "hands-praying",
    "create_goal": "target",
    "log_habit": "check-circle",
    "create_task": "list-check",
    "create_event": "calendar",
    "start_fast": "timer",
    "end_fast": "timer",
    "log_transaction": "wallet",
    "take_medication": "pill",
}


# ---------------------------------------------------------------------------
# Follow-Up Suggestions
# ---------------------------------------------------------------------------
# After certain actions, suggest relevant follow-ups.

FOLLOW_UP_MAP: Dict[str, List[dict]] = {
    "log_weight": [
        {"url": "/health/weight/", "label": "View trends", "icon": "chart"},
    ],
    "log_food": [
        {"url": "/health/nutrition/", "label": "View daily totals", "icon": "chart"},
    ],
    "log_workout": [
        {"url": "/health/fitness/", "label": "View workout history", "icon": "list"},
    ],
    "create_journal_entry": [
        {"url": "/journal/", "label": "View journal", "icon": "book"},
    ],
    "create_goal": [
        {"url": "/purpose/goals/", "label": "View all goals", "icon": "target"},
    ],
    "create_event": [
        {"url": "/calendar/", "label": "View calendar", "icon": "calendar"},
    ],
    "create_task": [
        {"url": "/life/tasks/", "label": "View tasks", "icon": "list-check"},
    ],
    "log_prayer": [
        {"url": "/faith/prayer/", "label": "View prayer journal", "icon": "book"},
    ],
    "start_fast": [
        {"url": "/health/fasting/", "label": "View fasting tracker", "icon": "timer"},
    ],
    "log_transaction": [
        {"url": "/finance/", "label": "View finances", "icon": "chart"},
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_action_contract(
    intent_type: str,
    success: bool,
    message: str,
    created_object: dict = None,
) -> ActionContract:
    """
    Build an ActionContract for an action result.

    Resolves URLs, attaches follow-up links, and adds display metadata.

    Args:
        intent_type: The intent that was executed.
        success: Whether the action succeeded.
        message: The user-facing response message.
        created_object: Dict with created object details.

    Returns:
        ActionContract with navigation and follow-up metadata.
    """
    contract = ActionContract(
        intent_type=intent_type,
        success=success,
        message=message,
        icon=INTENT_ICONS.get(intent_type, ""),
    )

    if not success:
        return contract

    # Resolve navigation URL
    url_meta = build_action_url_metadata(intent_type, created_object)
    if url_meta:
        contract.view_url = url_meta.get("url")
        contract.view_label = url_meta.get("label")
        contract.detail_url = url_meta.get("detail_url")

    # Add follow-up links
    follow_ups = FOLLOW_UP_MAP.get(intent_type, [])
    for fu in follow_ups:
        # Don't add duplicate of the main view URL
        if fu["url"] != contract.view_url:
            contract.follow_up_links.append(
                ActionLink(
                    url=fu["url"],
                    label=fu["label"],
                    icon=fu.get("icon", ""),
                )
            )

    return contract


def enrich_response_with_contracts(
    action_results: list,
    enriched_actions: list = None,
) -> List[dict]:
    """
    Build ActionContracts for a list of action results.

    Args:
        action_results: List of ActionResult objects from execution_engine.
        enriched_actions: List of EnrichedAction objects (parallel to action_results).

    Returns:
        List of ActionContract dicts ready for JSON serialization.
    """
    contracts = []

    for i, result in enumerate(action_results):
        intent_type = getattr(result, "action_type", None) or ""
        if not intent_type and enriched_actions and i < len(enriched_actions):
            intent_type = enriched_actions[i].intent_type

        created = getattr(result, "created_object", None)

        contract = build_action_contract(
            intent_type=intent_type,
            success=result.success,
            message=result.message,
            created_object=created,
        )
        contracts.append(contract.to_dict())

    return contracts
