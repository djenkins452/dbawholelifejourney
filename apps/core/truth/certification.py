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
    # CERTIFIED 2026-06-29 — production Smoke/Full/Deep GREEN + real-conversation
    # validation. FROZEN: permanent infrastructure, change only via formal control.
    "status": "certified",
    "certified_on": "2026-06-29",
    "frozen": True,
    "certification_commit": "d6c187f734be0e020d56e42e2eacc91285b5db05",
    "certification_tag": "layer1-canonical-truth-v1",
    "acceptance_results": {"smoke": "GREEN", "full": "GREEN", "deep": "GREEN"},
    "production_validated": True,
    # APPROVED Layer 1 scope. The roadmap — not implementation — defines this list.
    # Origin: original inventory backlog · approved Domain Truth checkpoint ·
    # Confidence/Stability RATIFIED 2026-06-28 as the trust properties of Canonical
    # Truth (a truth value is not trustworthy without value+freshness+confidence+stability).
    "capabilities": [
        "Per-Day Truth",                  # original inventory
        "Freshness",                      # original inventory (Law 1)
        "Confidence",                     # ratified 2026-06-28 (Law 2)
        "Stability",                      # ratified 2026-06-28 (Law 5)
        "Current Truth Objects",          # original inventory
        "Point-in-Time History",          # original inventory
        "Domain Truth Objects",           # approved architectural checkpoint
        "Deterministic Provider Registry",  # original inventory
    ],
    "emerged_pending_ratification": [],   # cleared — Confidence + Stability ratified above
    "future_backlog": [
        # No grounding in any approved governance doc → FUTURE BACKLOG (not Layer 1):
        "Truth Catalog",  # introspection tooling; serves the registry/Beth, not canonical truth
        # Acceptance Center evolution (approved for backlog 2026-06-28): a synthetic
        # acceptance user + per-question health-data setup + time mocking, driven by
        # `freshness_expect`, so the LIVE Deep suite can exercise the 5-state freshness
        # matrix end-to-end. Until then the matrix is validated deterministically
        # (test_daily_health_freshness) and the live suite runs coherent honesty checks.
        "Freshness state-simulation harness",
    ],
    "platform_modules": [
        "apps.core.truth.freshness",
        "apps.core.truth.confidence",
        "apps.core.truth.stability",
        "apps.core.truth.current",
        "apps.core.truth.periods",
        "apps.core.truth.history",
        "apps.core.truth.domain",
        "apps.core.truth.catalog",
        "apps.ai.chatgpt_cos.fact_registry",
    ],
    "test_modules": [
        # platform capabilities
        "apps.core.tests.test_truth_freshness",
        "apps.core.tests.test_truth_confidence",
        "apps.core.tests.test_truth_stability",
        "apps.core.tests.test_current_truth",
        "apps.core.tests.test_truth_history",
        "apps.core.tests.test_domain_truth",
        "apps.core.tests.test_truth_catalog",
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

LAYER_2 = {
    "number": 2,
    "name": "Executive Reasoning",
    # CERTIFIED 2026-06-30 — reasons OVER Layer 1 truth, never creates truth. Built and
    # validated against this week's production conversations. FROZEN under change control.
    "status": "certified",
    "certified_on": "2026-06-30",
    "frozen": True,
    "certification_tag": "layer2-executive-reasoning-v1",
    "acceptance_results": {"smoke": "GREEN", "full": "GREEN", "deep": "GREEN",
                           "conversation": "GREEN"},
    "production_validated": True,
    # Reusable reasoning capabilities (classified by capability, not feature).
    "capabilities": [
        "Conversation Object",            # the active conversational frame
        "Conversation Goal",              # review → compare → trend → investigate
        "Active Subject",                 # the anchor; moves only on explicit refocus
        "Referential Resolution",         # bare references resolve against the frame
        "Comparison Semantics",           # how each metric should be compared
        "Intent Fulfillment",             # accomplish the objective, not the literal prompt
        "Reasoning Confidence",           # weakest-link trustworthiness of a conclusion
        "Risk Reasoning",                 # read risk from Layer 1 interpretation (never invent)
        "Priority Reasoning",             # rank by significance
        "Reason Explanation & Transparency",  # why she said it / what it means
        "Natural Follow-up",              # what changed / anything else / is that an average
    ],
    "future_backlog": [
        # Layer 3 (named, not built): action selection/execution, cross-domain conflict
        # resolution, recommendation ranking across domains, deep-timeline retrieval.
        "Action Selection (Layer 3)",
        "Cross-Domain Conflict Resolution (Layer 3)",
        "Deep-Timeline Retrieval (Layer 1 change-control item)",
    ],
    "platform_modules": [
        "apps.ai.chatgpt_cos.conversation_object",
        "apps.ai.chatgpt_cos.conversation_memory",
        "apps.ai.chatgpt_cos.referential",
        "apps.ai.chatgpt_cos.fulfillment",
        "apps.ai.chatgpt_cos.reasoning.engines",
        "apps.ai.chatgpt_cos.supporting_facts",
        "apps.core.truth.present",   # Presentation reasoning (Layer 2 consumes Layer 1)
    ],
    "test_modules": [
        # reusable reasoning engines + the manifest gate
        "apps.ai.tests.test_reasoning",
        "apps.ai.tests.test_layer2_certification",
        # conversation reasoning capabilities (production-conversation regressions)
        "apps.ai.tests.test_conversation_object",
        "apps.ai.tests.test_supporting_facts",
        "apps.ai.tests.test_conversation_goal",
        "apps.ai.tests.test_referential_resolution",
        "apps.ai.tests.test_comparison_semantics",
        "apps.ai.tests.test_intent_fulfillment",
        "apps.ai.tests.test_active_subject",
        "apps.ai.tests.test_trust_capabilities",
        "apps.core.tests.test_presentation",
    ],
}

# Registry of all WLJ layers (extended as higher layers are built/certified).
LAYERS = {
    1: LAYER_1,
    2: LAYER_2,
    # 3: Action/Execution, 4: Domain Intelligence, 5: Cross-Domain Intelligence,
    # 6: Chief of Staff Briefing, 7: Beth, 8: Customer Experience — added as each is built.
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


def highest_layer():
    """Highest layer PRESENT (built), regardless of certification status — the
    deterministic release gate runs these even before live-Deep certification."""
    return max(LAYERS) if LAYERS else 0
