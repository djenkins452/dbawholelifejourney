"""
WLJ Layer Certification manifest.

A layer is COMPLETE only when CERTIFIED: implementation done, its acceptance +
regression GREEN, frozen as permanent infrastructure. Once certified a layer must
never regress — every future layer's release gate re-runs all certified layers and
fails if any regresses (`certify_layers` management command / CI).

This manifest is the source of truth for what each layer certifies and which
deterministic test modules constitute its gate. The LIVE Deep Acceptance Center
(needs the production OpenAI stack) is the complementary runtime gate; this manifest
covers the deterministic foundation that can be enforced in CI on every commit.
"""

LAYER_1 = {
    "number": 1,
    "name": "Canonical Truth",
    "status": "certified",            # flip to "certified" only when the gate is GREEN
    "certified_on": "2026-06-28",
    "frozen": True,
    "capabilities": [
        "Per-Day Truth",
        "Freshness",
        "Current Truth Objects",
        "Point-in-Time History",
        "Domain Truth Objects",
        "Deterministic Provider Registry",
    ],
    "platform_modules": [
        "apps.core.truth.freshness",
        "apps.core.truth.current",
        "apps.core.truth.periods",
        "apps.core.truth.history",
        "apps.core.truth.domain",
        "apps.ai.chatgpt_cos.fact_registry",
    ],
    "test_modules": [
        # platform capabilities
        "apps.core.tests.test_truth_freshness",
        "apps.core.tests.test_current_truth",
        "apps.core.tests.test_truth_history",
        "apps.core.tests.test_domain_truth",
        "apps.core.tests.test_fact_registry",
        "apps.core.tests.test_layer1_certification",
        # domain consumers (Health first, deterministic fast path)
        "apps.health.tests.test_daily_health_queries",
        "apps.health.tests.test_daily_health_freshness",
        "apps.ai.tests.test_execution_facts",
        "apps.ai.tests.test_foundation_validation",
        "apps.ai.tests.test_foundational_steps",
    ],
}

# Registry of all WLJ layers (extended as higher layers are built/certified).
LAYERS = {
    1: LAYER_1,
    # 2: Current Truth, 3: Historical Retrieval, 4: Domain Intelligence,
    # 5: Cross-Domain Intelligence, 6: Chief of Staff Briefing, 7: Beth,
    # 8: Customer Experience — added as each is built.
}


def layers_up_to(n):
    """Certified-or-present layers 1..n, in order (the release gate set)."""
    return [LAYERS[i] for i in sorted(LAYERS) if i <= n]


def certification_modules(up_to_layer):
    """Union (de-duplicated, order-preserved) of test modules for layers 1..N — the
    deterministic regression gate that must stay GREEN for layer N to certify."""
    seen, mods = set(), []
    for layer in layers_up_to(up_to_layer):
        for m in layer["test_modules"]:
            if m not in seen:
                seen.add(m)
                mods.append(m)
    return mods


def certified_layers():
    return [l for l in LAYERS.values() if l.get("status") == "certified"]


def highest_certified_layer():
    nums = [l["number"] for l in certified_layers()]
    return max(nums) if nums else 0
