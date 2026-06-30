# Layer 2 Certification Snapshot — Executive Reasoning

**Status:** CERTIFIED · FROZEN · under change control
**Certified:** 2026-06-30
**Tag:** `layer2-executive-reasoning-v1`
**Manifest:** `apps/core/truth/certification.py :: LAYER_2`

## Acceptance results

| Tier | Result | Evidence |
|---|---|---|
| Smoke | GREEN | manifest consistent, modules import, gate includes L1+L2, L1 still frozen |
| Full | GREEN | each reasoning engine behaves (confidence, risk, semantics, goal) |
| Deep | GREEN | reasoning does not mutate Layer 1 truth; intent fulfilment is a comparison |
| **Conversation** (mandatory) | GREEN | this week's production conversations succeed end-to-end |

Gate: `apps/ai/tests/test_layer2_certification.py` + the conversation-capability regressions
(`test_reasoning`, `test_conversation_object`, `test_conversation_goal`,
`test_referential_resolution`, `test_comparison_semantics`, `test_intent_fulfillment`,
`test_active_subject`, `test_trust_capabilities`, `test_supporting_facts`,
`test_presentation`). Enforced in CI by `certify_layers` (re-runs Layer 1 + Layer 2).

## Capabilities certified

Conversation Object · Conversation Goal · Active Subject · Referential Resolution ·
Comparison Semantics · Intent Fulfillment · Reasoning Confidence · Risk Reasoning ·
Priority Reasoning · Reason Explanation & Transparency · Natural Follow-up.

## Production conversations now permanently protected (this week's backlog)

| Conversation | Was | Now | Regression |
|---|---|---|---|
| "What did I eat?" after a calorie total | answered meal *timestamps* | the meals | `test_supporting_facts` |
| "Compared to today" on meals | two lists | the comparison itself | `test_intent_fulfillment` |
| "What about yesterday?" / "compared to today" | failed / drifted to coaching | resolves on the topic | `test_referential_resolution` |
| "Is that an average?" | asked for clarification | answered from the object | `test_trust_capabilities` |
| Glucose "compared to yesterday" | point-vs-point (noisy) | average + honored target | `test_comparison_semantics` |
| "Compared to my average" after yesterday | anchored on yesterday | anchored on current reading | `test_active_subject` |
| `glucose_yesterday` rendering | "Glucose yesterday: 105" | "Yesterday your glucose was 105 mg/dL" | `test_comparison_semantics` |

## Layer integrity

Layer 1 remains CERTIFIED and FROZEN; `highest_certified_layer() == 2`. Layer 2 consumes
Layer 1 read-only and modifies nothing. See `docs/LAYER2_CONSTITUTION.md` and
`docs/LAYER2_INVENTORY.md`.
