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

Per the architecture baseline (@WLJ_SYSTEM_PROMPTS/07_DAY1_TOOL_CATALOG) and the
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

from apps.ai.cos_services.domain_state import (
    DOMAIN_REGISTRY,
    DOMAIN_STATE_SCHEMA_VERSION,
    get_domain_state,
    supported_domains,
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
    # Phase 3
    "get_tool_schemas",
    "enabled_tool_names",
    "evidence_tools_enabled",
    "dispatch_tool_call",
]
