# ==============================================================================
# File: apps/ai/cos_services/__init__.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: ChatGPT CoS internal service layer (HYBRID architecture, Phase 1+)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
ChatGPT Chief of Staff — Internal Service Layer
================================================

Per the architecture baseline (@WLJ_SYSTEM_PROMPTS/07_COS_TOOLS_REFERENCE) and the
HYBRID connection decision, these services expose WLJ's EXISTING deterministic
truth to the ChatGPT reasoning layer. They:

* reuse existing providers (build_cos_context, get_module_state, CosDecisionView
  providers, SearchService, execute_intent) — NO new intelligence, NO new engines;
* are read-cache-first and NEVER live-compute on the request path;
* are designed to be wrapped by authenticated HTTP endpoints LATER without any
  business-logic change (business logic lives here, not in endpoints).

WLJ owns truth. ChatGPT owns understanding.

Phase 1 — StandingContextService: get_standing_context()
Phase 2 — DomainStateService:     get_domain_state()
"""

from apps.ai.cos_services.action_execution import (
    DAY1_ACTION_ALLOWLIST,
    allowed_actions,
    execute_action,
)
from apps.ai.cos_services.ai_relationship import (
    AI_RELATIONSHIP_SCHEMA_VERSION,
    get_ai_relationship,
)
from apps.ai.cos_services.action_interface import (
    request_action,
    resolve_pending_action,
)
from apps.ai.cos_services.audit import record_tool_call
from apps.ai.cos_services.current_context import (
    CURRENT_CONTEXT_SCHEMA_VERSION,
    get_current_context_baseline,
)
from apps.ai.cos_services.domain_history import (
    DOMAIN_HISTORY_SCHEMA_VERSION,
    get_domain_history,
    history_capability_index,
    history_capable_domains,
)
from apps.ai.cos_services.domain_analysis import (
    DOMAIN_ANALYSIS_SCHEMA_VERSION,
    analysis_capability_index,
    analysis_capable_domains,
    get_domain_analysis,
)
from apps.ai.cos_services.domain_readings import (
    DOMAIN_READINGS_SCHEMA_VERSION,
    get_domain_readings,
    readings_capability_index,
    readings_capable_domains,
)
from apps.ai.cos_services.domain_comparison import (
    DOMAIN_COMPARISON_SCHEMA_VERSION,
    comparison_capability_index,
    comparison_capable_domains,
    get_domain_comparison,
)
from apps.ai.cos_services.domain_adherence import (
    DOMAIN_ADHERENCE_SCHEMA_VERSION,
    adherence_capability_index,
    adherence_capable_domains,
    get_domain_adherence,
)
from apps.ai.cos_services.personal_truth import (
    PERSONAL_TRUTH_SCHEMA_VERSION,
    build_personal_truth,
    get_user_truth,
    personal_truth_for_context,
)
from apps.ai.cos_services.domain_entity import (
    DOMAIN_ENTITY_SCHEMA_VERSION,
    get_domain_entity,
    entity_capability_index,
    entity_capable_domains,
)
from apps.ai.cos_services.domain_state import (
    DOMAIN_REGISTRY,
    DOMAIN_STATE_SCHEMA_VERSION,
    get_domain_state,
    supported_domains,
)
from apps.ai.cos_services.health_facts import (
    SUPPORTED_FACTS,
    get_foundational_health_facts,
)
from apps.ai.cos_services.history_search import (
    SUPPORTED_HISTORY_DOMAINS,
    search_history,
)
from apps.ai.cos_services.standing_context import (
    STANDING_CONTEXT_SCHEMA_VERSION,
    get_standing_context,
)
from apps.ai.cos_services.tool_dispatcher import dispatch_tool_call
from apps.ai.cos_services.tool_registry import (
    enabled_tool_names,
    evidence_tools_enabled,
    get_tool_schemas,
)

__all__ = [
    # Phase 1
    "get_standing_context",
    "STANDING_CONTEXT_SCHEMA_VERSION",
    # Phase 2
    "get_domain_state",
    "supported_domains",
    "DOMAIN_REGISTRY",
    "DOMAIN_STATE_SCHEMA_VERSION",
    # Pillar 1 — history branch (Truth Resolution Layer, DomainTruth.history)
    "get_domain_history",
    "get_domain_analysis",
    "analysis_capability_index",
    "analysis_capable_domains",
    "get_user_truth",
    "build_personal_truth",
    "personal_truth_for_context",
    "history_capability_index",
    "history_capable_domains",
    "DOMAIN_HISTORY_SCHEMA_VERSION",
    # Pillar 1 — readings branch (Truth Resolution Layer, DomainTruth.readings; intra-day)
    "get_domain_readings",
    "readings_capability_index",
    "readings_capable_domains",
    "DOMAIN_READINGS_SCHEMA_VERSION",
    # Pillar 1 — comparison branch (period A vs period B; reuses history)
    "get_domain_comparison",
    "comparison_capability_index",
    "comparison_capable_domains",
    "DOMAIN_COMPARISON_SCHEMA_VERSION",
    # Pillar 1 — adherence branch (actual vs target; reuses history + target registry)
    "get_domain_adherence",
    "adherence_capability_index",
    "adherence_capable_domains",
    "DOMAIN_ADHERENCE_SCHEMA_VERSION",
    # Pillar 1 — entity branch (Truth Resolution Layer, DomainTruth.describe)
    "get_domain_entity",
    "entity_capability_index",
    "entity_capable_domains",
    "DOMAIN_ENTITY_SCHEMA_VERSION",
    # Phase 3
    "get_tool_schemas",
    "enabled_tool_names",
    "evidence_tools_enabled",
    "dispatch_tool_call",
    # Foundational health facts (focused, scalar)
    "get_foundational_health_facts",
    "SUPPORTED_FACTS",
    # Phase 5
    "search_history",
    "SUPPORTED_HISTORY_DOMAINS",
    # Phase 6
    "execute_action",
    "allowed_actions",
    "DAY1_ACTION_ALLOWLIST",
    # Interface Pillar 3 — AI Relationship (projection)
    "get_ai_relationship",
    "AI_RELATIONSHIP_SCHEMA_VERSION",
    # Interface — Audit
    "record_tool_call",
    # Interface Pillar 4 — Current Context baseline
    "get_current_context_baseline",
    "CURRENT_CONTEXT_SCHEMA_VERSION",
    # Interface Pillar 2 — Action interface (stateful confirmation)
    "request_action",
    "resolve_pending_action",
]
