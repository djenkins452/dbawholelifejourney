"""
Canonical Person domain registration.

People is a foundational, always-on Layer 1 truth domain — the single identity
authority every other module consumes. It has NO feature flag (identity never
disappears when a feature is disabled) and is classified SYSTEM: it is the identity
substrate, not a behavioral life-area that produces cross-domain signals.
"""

from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability, DomainClass

registry.register(DomainCapability(
    name="people",
    display_name="People (Canonical Person)",
    description="The single canonical Person identity authority: identity, "
                "recognition phrases, membership, resolution, merge, provenance.",
    domain_class=DomainClass.SYSTEM,
    intent_types=[],
    primary_models=[
        "Person", "PersonMembership", "RecognitionPhrase",
        "PersonPhoto", "PersonEvent", "PersonSourceLink",
    ],
    context_builders=[],
    proactive_signals=[],
    expected_signal_types=[],
    related_domains=["relationships", "legacy"],
    feature_flag=None,
    url_namespace="people",
))
