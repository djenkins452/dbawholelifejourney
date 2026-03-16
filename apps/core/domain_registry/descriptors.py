# ==============================================================================
# File: apps/core/domain_registry/descriptors.py
# Description: DomainCapability dataclass — schema for domain registration
# ==============================================================================
"""
Domain Capability Descriptor

Each WLJ domain registers a DomainCapability instance declaring its
capabilities, models, context builders, proactive signals, and relationships.
"""

from dataclasses import dataclass, field
from typing import Optional


class DomainClass:
    """
    Domain classification constants.

    Controls how the domain participates in CoS, signal routing,
    and module governance.
    """
    BEHAVIORAL = 'behavioral'     # First-class user life domain (Health, Faith, etc.)
    INFLUENCE = 'influence'       # Cross-domain ingestion/influence system (Capture)
    KNOWLEDGE = 'knowledge'       # Structured knowledge store (Documents)
    CONTEXT = 'context'           # Contextual enrichment (Travel, future)
    SYSTEM = 'system'             # Internal infrastructure (observability, etc.)

    ALL = {BEHAVIORAL, INFLUENCE, KNOWLEDGE, CONTEXT, SYSTEM}

    # Domains that represent a user's life area
    USER_LIFE_DOMAINS = {BEHAVIORAL}

    # Domains that can be a cross-domain signal source
    CROSS_DOMAIN_SOURCES = {INFLUENCE}

    # Domains that participate in CoS context assembly
    COS_PARTICIPATING = {BEHAVIORAL, INFLUENCE, KNOWLEDGE}


@dataclass
class DomainCapability:
    """
    Descriptor for a WLJ domain's capabilities.

    Every domain app must create one of these in its capabilities.py
    and call registry.register(capability) during app startup.
    """
    # Identity
    name: str                                   # e.g., "health"
    display_name: str                           # e.g., "Health & Vitals"
    description: str                            # Human-readable purpose

    # ── Phase 3: Domain governance metadata ──
    domain_class: str = DomainClass.BEHAVIORAL  # Classification (behavioral, influence, etc.)

    # What actions can be performed via CoS
    intent_types: list = field(default_factory=list)  # e.g., ["log_weight", "log_heart_rate"]

    # What data models this domain manages
    primary_models: list = field(default_factory=list)  # e.g., ["WeightEntry", "HeartRateEntry"]

    # What context this domain contributes to CoS
    context_builders: list = field(default_factory=list)  # e.g., ["_build_health_and_vitals"]

    # What signals this domain can generate proactively
    proactive_signals: list = field(default_factory=list)  # e.g., ["medication_gap", "missed_workout"]

    # Phase 4: Signal taxonomy types this domain is expected to produce
    # Maps to SIGNAL_TYPE_DOMAIN keys in signal_aggregation.py
    # Metadata only — used for audit, diagnostics, and coverage validation.
    # Does NOT drive runtime signal routing.
    expected_signal_types: list = field(default_factory=list)  # e.g., ["health_activity", "health_biometrics"]

    # Related domains for cross-domain reasoning
    related_domains: list = field(default_factory=list)  # e.g., ["fitness", "meals", "goals"]

    # Feature flag controlling this domain (None = always enabled)
    feature_flag: Optional[str] = None  # e.g., "features.health.enabled"

    # URL namespace for navigation
    url_namespace: Optional[str] = None  # e.g., "health"

    # App label (auto-set during registration)
    app_label: Optional[str] = None

    @property
    def is_user_life_domain(self) -> bool:
        """Whether this domain represents a user's life area."""
        return self.domain_class in DomainClass.USER_LIFE_DOMAINS

    @property
    def is_cross_domain_source(self) -> bool:
        """Whether this domain is a cross-domain ingestion/influence system."""
        return self.domain_class in DomainClass.CROSS_DOMAIN_SOURCES

    @property
    def participates_in_cos(self) -> bool:
        """Whether this domain participates in CoS context assembly."""
        return self.domain_class in DomainClass.COS_PARTICIPATING

    def coverage_score(self) -> float:
        """
        Compute a 0-100 coverage score based on registration completeness.

        Scoring:
        - Has intents: 25 points
        - Has context builders: 20 points
        - Has proactive signals: 20 points
        - Has expected signal types: 10 points (Phase 4)
        - Has related domains: 10 points
        - Has primary models: 15 points
        """
        score = 0.0
        if self.intent_types:
            score += 25.0
        if self.context_builders:
            score += 20.0
        if self.proactive_signals:
            score += 20.0
        if self.expected_signal_types:
            score += 10.0
        if self.related_domains:
            score += 10.0
        if self.primary_models:
            score += 15.0
        return score
