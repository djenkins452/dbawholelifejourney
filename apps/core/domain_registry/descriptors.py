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

    # What actions can be performed via CoS
    intent_types: list = field(default_factory=list)  # e.g., ["log_weight", "log_heart_rate"]

    # What data models this domain manages
    primary_models: list = field(default_factory=list)  # e.g., ["WeightEntry", "HeartRateEntry"]

    # What context this domain contributes to CoS
    context_builders: list = field(default_factory=list)  # e.g., ["_build_health_and_vitals"]

    # What signals this domain can generate proactively
    proactive_signals: list = field(default_factory=list)  # e.g., ["medication_gap", "missed_workout"]

    # Related domains for cross-domain reasoning
    related_domains: list = field(default_factory=list)  # e.g., ["fitness", "meals", "goals"]

    # Feature flag controlling this domain (None = always enabled)
    feature_flag: Optional[str] = None  # e.g., "features.health.enabled"

    # URL namespace for navigation
    url_namespace: Optional[str] = None  # e.g., "health"

    # App label (auto-set during registration)
    app_label: Optional[str] = None

    def coverage_score(self) -> float:
        """
        Compute a 0-100 coverage score based on registration completeness.

        Scoring:
        - Has intents: 30 points
        - Has context builders: 20 points
        - Has proactive signals: 25 points
        - Has related domains: 10 points
        - Has primary models: 15 points
        """
        score = 0.0
        if self.intent_types:
            score += 30.0
        if self.context_builders:
            score += 20.0
        if self.proactive_signals:
            score += 25.0
        if self.related_domains:
            score += 10.0
        if self.primary_models:
            score += 15.0
        return score
