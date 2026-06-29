# Intent Fulfillment Matrix

> Conversation Goal says *what the customer wants*. Intent Fulfillment decides whether
> the response *accomplishes* it. Never optimize for literal prompt completion — optimize
> for objective completion. The engineering contract: each goal has a **minimum
> successful response** that fulfills the intent, not merely answers the words.

| Goal | Minimum successful response | Common customer expectation | Current implementation | Gap |
|---|---|---|---|---|
| **Review** | The fact + what's next (remaining/target) | "Tell me where I am." | `format_fact_sentence` + `present_remaining` | ✅ fulfilled |
| **Compare** (numeric) | The **delta** — direction + magnitude | "Is it up or down, and by how much?" | `compose_comparison` → "down 3,923 (8,123 → 4,200)" | ✅ fulfilled |
| **Compare** (structured, e.g. meals) | The **differences & overlaps** — not two lists | "What's different between the days?" | ~~two side-by-side lists~~ → **insight composer** | ✅ **closed this sprint** |
| **Trend** | Direction over time vs a baseline | "Which way is this heading?" | `compose_comparison(average)` → vs recent average | ✅ mostly (single baseline) |
| **Investigate** | The change + its comparison | "What changed / what caused it?" | `compose_what_changed` → the delta | ◑ partial (delta, not root cause) |
| **Summarize** | The highlights, ranked | "Give me the rundown." | — | ✗ not yet built |
| **Explain** | The basis / why she said it | "Why do you say that?" | `compose_why` | ✅ fulfilled |
| **Clarify** | A direct meta-answer | "Is that an average?" | `compose_is_average` | ✅ fulfilled |
| **Navigate** | The figure for the named period | "What about the day before?" | honest on-topic decline | ✗ deep-timeline retrieval (TF1) |

## This sprint closes the Compare gap for structured topics

**Goal:** Compare meals across days.
**Poor fulfillment (literal):** Yesterday […]. Today […].
**Good fulfillment (objective):** *"Yesterday included lunch, but today doesn't yet. Pizza
appears on both days. Yesterday was heavier (4 items vs 2) — today is lighter so far."*

The comparison **is** the answer. Implemented in `apps/ai/chatgpt_cos/fulfillment.py`
(`fulfill_meal_comparison`), called from the referential comparison path. Numeric topics
already fulfilled via the delta; this generalizes fulfillment to structured topics.

## Named next (own sprints)

- **Summarize** — a ranked-highlights composer (needs a salience model).
- **Investigate** — root-cause beyond the delta (needs causal supporting facts).
- **Navigate** — deep-timeline retrieval (TF1) so Compare/Trend can reach older periods.
