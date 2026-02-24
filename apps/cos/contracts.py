"""
CoS v2 Action Contract — Abstract base class for module integrations.

Every CRUD-capable module that wants CoS support implements a subclass
of CosActionContract and registers it via the CosActionRegistry.

The contract standardises:
- create / update / delete / retrieve / summarise
- duplicate detection (semantic + domain-specific)
- conflict / overlap detection
- post-activity reflection capture hooks

Consumers (UAIO action router, proactive prompt service, etc.) call
through the registry so they never import module-specific code directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────
# Result dataclasses
# ──────────────────────────────────────────────────────────


@dataclass
class ActionResult:
    """Standard result from any CoS action."""

    success: bool
    entity: Optional[Any] = None
    entity_id: Optional[int] = None
    reused: bool = False
    error: Optional[str] = None
    requires_decision: bool = False
    decision_options: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DuplicateCheck:
    """Result of a duplicate check."""

    is_duplicate: bool
    existing_entity: Optional[Any] = None
    existing_entity_id: Optional[int] = None
    match_type: Optional[str] = None  # "exact", "semantic", "recurrence"
    message: Optional[str] = None


@dataclass
class ConflictCheck:
    """Result of a conflict / overlap check."""

    has_conflict: bool
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    suggested_resolutions: List[Dict[str, Any]] = field(default_factory=list)
    message: Optional[str] = None


# ──────────────────────────────────────────────────────────
# Abstract contract
# ──────────────────────────────────────────────────────────


class CosActionContract(ABC):
    """
    Abstract interface that every CoS-integrated module must implement.

    Lifecycle:
        check_duplicate → check_conflicts → create / update / delete
        → (post-action) capture_reflection_hook

    Subclasses MUST implement: module_name, create, retrieve, summarise.
    Subclasses SHOULD override: update, delete, check_duplicate,
    check_conflicts, capture_reflection_hook.
    """

    def __init__(self, user):
        self.user = user

    # ── Identity ──────────────────────────────────────────

    @property
    @abstractmethod
    def module_name(self) -> str:
        """Return the unique module identifier (e.g. 'calendar', 'journal')."""

    # ── CRUD ──────────────────────────────────────────────

    @abstractmethod
    def create(self, **kwargs) -> ActionResult:
        """Create a new entity.  Must handle dedup internally."""

    def update(self, entity_id: int, **kwargs) -> ActionResult:
        """Update an existing entity.  Default: not supported."""
        return ActionResult(
            success=False,
            error=f"{self.module_name} does not support update via CoS.",
        )

    def delete(self, entity_id: int, **kwargs) -> ActionResult:
        """Soft-delete an entity.  Default: not supported."""
        return ActionResult(
            success=False,
            error=f"{self.module_name} does not support delete via CoS.",
        )

    @abstractmethod
    def retrieve(self, entity_id: int) -> ActionResult:
        """Retrieve a single entity by ID."""

    @abstractmethod
    def summarise(self, **kwargs) -> ActionResult:
        """
        Return a summary of entities (e.g. today's events, recent entries).
        kwargs may contain date ranges, filters, limits, etc.
        """

    # ── Safety checks ─────────────────────────────────────

    def check_duplicate(self, **kwargs) -> DuplicateCheck:
        """
        Check whether creating with these params would be a duplicate.
        Default: no duplicate (module has no dedup logic).
        """
        return DuplicateCheck(is_duplicate=False)

    def check_conflicts(self, **kwargs) -> ConflictCheck:
        """
        Check for scheduling conflicts / overlaps.
        Default: no conflicts (module has no time-based constraints).
        """
        return ConflictCheck(has_conflict=False)

    # ── Post-action hooks ─────────────────────────────────

    def capture_reflection_hook(
        self,
        entity_id: int,
        reflection_text: str,
        **kwargs,
    ) -> bool:
        """
        Store a reflection note against a specific entity occurrence.
        Returns True if stored successfully.
        Default: no-op (returns False).
        """
        return False

    def supports_reflections(self) -> bool:
        """Whether this module supports post-activity reflections."""
        return False

    def supports_proactive_prompts(self) -> bool:
        """Whether this module supports pre/post event prompts."""
        return False
