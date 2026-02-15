"""
SUE -- Entity Resolver.

Resolves extracted entities and contextual references to concrete
database objects. Uses a priority chain:

1. Current page context (highest priority)
2. SLCME learned mappings
3. SAE state (e.g., "my weight" → latest weight from state)
4. Database fallback (direct query)

The resolver NEVER executes actions. It returns resolved entity
identifiers for the UAIO orchestrator to use.
"""

import logging

logger = logging.getLogger(__name__)


class ResolvedEntity:
    """A resolved entity with its source and confidence."""

    __slots__ = (
        "entity_type",
        "entity_id",
        "display_value",
        "source",
        "confidence",
    )

    def __init__(self, entity_type, entity_id, display_value="", source="", confidence=0.0):
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.display_value = display_value
        self.source = source  # "context", "slcme", "sae", "database"
        self.confidence = confidence

    def to_dict(self):
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "display_value": self.display_value,
            "source": self.source,
            "confidence": self.confidence,
        }


class EntityResolutionResult:
    """Complete entity resolution result."""

    __slots__ = (
        "resolved_entities",
        "unresolved_references",
        "used_slcme",
        "used_sae",
        "used_context",
    )

    def __init__(self):
        self.resolved_entities = []       # List[ResolvedEntity]
        self.unresolved_references = []   # List[str]
        self.used_slcme = False
        self.used_sae = False
        self.used_context = False

    def to_dict(self):
        return {
            "resolved": [e.to_dict() for e in self.resolved_entities],
            "unresolved": self.unresolved_references,
            "sources": {
                "slcme": self.used_slcme,
                "sae": self.used_sae,
                "context": self.used_context,
            },
        }


def resolve_entities(user, contextual_references, domain_hint="", context=None):
    """
    Resolve contextual references to concrete entities.

    Priority chain:
    1. Current page context
    2. SLCME learned mappings
    3. SAE state
    4. Database fallback

    Args:
        user: Django user instance.
        contextual_references: List of reference strings (e.g., ["that goal", "my weight"]).
        domain_hint: Best guess domain from parser (e.g., "health").
        context: Optional dict with page context info.

    Returns:
        EntityResolutionResult with resolved and unresolved entities.
    """
    result = EntityResolutionResult()

    if not contextual_references:
        return result

    for ref in contextual_references:
        entity = _resolve_single_reference(user, ref, domain_hint, context, result)
        if entity:
            result.resolved_entities.append(entity)
        else:
            result.unresolved_references.append(ref)

    return result


def _resolve_single_reference(user, reference, domain_hint, context, result):
    """
    Attempt to resolve a single contextual reference.

    Returns ResolvedEntity or None.
    """
    ref_lower = reference.lower().strip()

    # Priority 1: Page context
    entity = _resolve_from_context(ref_lower, context)
    if entity:
        result.used_context = True
        return entity

    # Priority 2: SLCME
    entity = _resolve_from_slcme(user, ref_lower, domain_hint)
    if entity:
        result.used_slcme = True
        return entity

    # Priority 3: SAE state
    entity = _resolve_from_sae(user, ref_lower, domain_hint)
    if entity:
        result.used_sae = True
        return entity

    # Priority 4: Database fallback (lightweight only)
    entity = _resolve_from_database(user, ref_lower, domain_hint)
    if entity:
        return entity

    return None


def _resolve_from_context(reference, context):
    """
    Resolve from page context.

    If the user says "that one" or "it" while on a specific page,
    the page context tells us what they mean.
    """
    if not context:
        return None

    # Generic references resolve to current page object
    generic_refs = {"it", "that one", "that", "this"}
    module = context.get("module", "")
    page_id = context.get("object_id", "")

    if reference in generic_refs and page_id:
        return ResolvedEntity(
            entity_type=_module_to_entity_type(module),
            entity_id=str(page_id),
            display_value=context.get("page_title", ""),
            source="context",
            confidence=0.95,
        )

    # Domain-specific references
    if "goal" in reference and module == "purpose" and page_id:
        return ResolvedEntity(
            entity_type="goal",
            entity_id=str(page_id),
            display_value=context.get("page_title", ""),
            source="context",
            confidence=0.90,
        )

    if "prayer" in reference and module == "faith" and page_id:
        return ResolvedEntity(
            entity_type="prayer",
            entity_id=str(page_id),
            display_value=context.get("page_title", ""),
            source="context",
            confidence=0.90,
        )

    if "task" in reference and module == "life" and page_id:
        return ResolvedEntity(
            entity_type="task",
            entity_id=str(page_id),
            display_value=context.get("page_title", ""),
            source="context",
            confidence=0.90,
        )

    return None


def _resolve_from_slcme(user, reference, domain_hint):
    """Resolve from SLCME learned mappings."""
    try:
        from apps.core.ai_memory.memory_engine import resolve_context

        # Map domain hint to SLCME context type
        context_type_hint = _domain_to_context_type(domain_hint)
        resolution = resolve_context(user, reference, context_type_hint=context_type_hint)

        if resolution.resolved:
            return ResolvedEntity(
                entity_type=resolution.meaning_type or "unknown",
                entity_id=resolution.meaning_identifier or "",
                display_value=resolution.meaning_identifier or "",
                source="slcme",
                confidence=0.85 if resolution.confidence == "high" else 0.60,
            )
    except Exception as e:
        logger.debug(f"SLCME resolution failed for '{reference}': {e}")

    return None


def _resolve_from_sae(user, reference, domain_hint):
    """
    Resolve from SAE state.

    "my weight" → latest weight value from SAE health state
    "my goal" → active goal info from SAE goals state
    """
    try:
        from apps.core.ai_state.state_engine import get_module_state

        # "my weight", "my latest weight", "the current weight"
        if any(kw in reference for kw in ("weight", "weigh")):
            state = get_module_state(user, "health")
            if state and state.get("weight_current"):
                return ResolvedEntity(
                    entity_type="weight_entry",
                    entity_id="latest",
                    display_value=f"{state['weight_current']} lb",
                    source="sae",
                    confidence=0.80,
                )

        # "my habit", "that habit"
        if "habit" in reference:
            state = get_module_state(user, "habits")
            if state and state.get("active_habit_count", 0) == 1:
                # Only one active habit -- unambiguous
                return ResolvedEntity(
                    entity_type="habit",
                    entity_id="single_active",
                    display_value="active habit",
                    source="sae",
                    confidence=0.75,
                )

        # "my goal", "that goal"
        if "goal" in reference:
            state = get_module_state(user, "goals")
            if state and state.get("active_goal_count", 0) == 1:
                return ResolvedEntity(
                    entity_type="goal",
                    entity_id="single_active",
                    display_value="active goal",
                    source="sae",
                    confidence=0.75,
                )

    except Exception as e:
        logger.debug(f"SAE resolution failed for '{reference}': {e}")

    return None


def _resolve_from_database(user, reference, domain_hint):
    """
    Lightweight database fallback for entity resolution.

    Only used for simple lookups. Complex queries should be
    deferred to UAIO execution phase.
    """
    # Currently returns None -- database fallback is handled
    # by the UAIO action handlers during execution.
    # SUE should not do heavy database queries.
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _module_to_entity_type(module):
    """Map module name to entity type."""
    mapping = {
        "health": "health_entry",
        "faith": "prayer",
        "purpose": "goal",
        "life": "task",
        "journal": "journal_entry",
        "medical": "medical_record",
    }
    return mapping.get(module, module)


def _domain_to_context_type(domain):
    """Map domain hint to SLCME context type hint."""
    mapping = {
        "health": "health_entry",
        "faith": "scripture_page",
        "purpose": "goal",
        "life": "task",
        "journal": "journal_entry",
    }
    return mapping.get(domain)
