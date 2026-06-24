# Document 4 — Holistic Diagnostic Framework

**Purpose:** Define how ChatGPT answers the hardest CoS questions — *Why? What's causing this? What changed? What's getting in the way?* — across the user's entire life, without ever overstating causality. Opens by fixing the **minimal always-loaded context** the whole loop depends on.

---

## 0. Minimal Always-Loaded Context (Final Determination)

The standing package present on **every** turn — maximum awareness, minimum tokens. Each item is already computed by WLJ today (provider proven in the Readiness Audit); the package is essentially the output of `build_cos_context` / `build_executive_context`.

| # | Standing item | Provider | Why always-on |
|---|---------------|----------|---------------|
| 1 | Identity · assistant name · feature flags · key preferences | `UserPreferences`, `get_cos_name()`, context_processors | Scopes every answer; sets which domains exist for this user |
| 2 | Time anchor · active block · day phase | `get_active_block`, today services | Nearly every judgment is time-relative |
| 3 | Execution truth (done/overdue/recoverable · next action · biggest risk · fix priority) | `get_execution_truth`, `build_execution_state`, selectors | The most-used CoS function |
| 4 | Executive summary (strategic state · risk flags · momentum · recommended focus) | `build_executive_context`, `build_cos_intelligence` | The holistic 30,000-ft view |
| 5 | Top signals (prioritized, deduped) | unified feed + signal renderer | What's notable now without raw queries |
| 6 | Foundational health vitals (weight+trend · glucose · sleep · recovery) | `build_health_state` | Foundational domain; contextualizes most reasoning |
| 7 | Situation verdict (day mode: normal/recovery/etc.) | `compute_situation_for_user`, `compute_right_now_focus` | Sets the posture before the CoS speaks |
| 8 | Trust framing (which context is canonical vs advisory) | narration-contract tiers | Stops rollups from becoming per-item claims (Law 16) |

**Determination:** these 8 items, and only these, are always-loaded. Everything domain-specific (faith, journal, goals, relationships, meals, history, captures, documents, screen) is **on-demand** — pulled by the retrieval framework (Doc 3) when the intent requires it. This keeps the standing footprint small while guaranteeing the CoS always knows *who, when, what's due, the big picture, what's notable, core health, the day's posture, and what it's allowed to treat as truth.*

---

## 1. What a Diagnostic Answer Must Contain

Every "why/what's-causing/what-changed" answer is composed of four separable parts, and the architecture forbids blending them:

1. **The observation** (provider fact) — *that* the thing changed. Always deterministic. ("Your weight-loss rate flattened over 3 weeks.")
2. **The evidence** (provider facts) — the deterministic states that co-occur. Always provider-sourced, each individually true.
3. **The hypothesis** (ChatGPT synthesis) — the *connection* between evidence and observation. This is wisdom, explicitly labeled, never system truth.
4. **The confidence** (Doc 6) — how strongly the evidence supports the hypothesis.

The seam between (2) and (3) is the single most important line in the whole architecture. WLJ certifies facts; ChatGPT proposes the story connecting them — and says so.

---

## 2. Evidence Ranking (within a diagnosis)

Once evidence is gathered (Doc 3), ChatGPT ranks each piece by **causal weight**, highest first:

| Tier | Evidence type | Causal weight | Example |
|------|---------------|---------------|---------|
| **A — System-certified linkage** | A deterministic composer/correlation already encodes this domain as causally linked to the focal domain | Strongest | Weight composer naming sleep/nutrition (`deterministic_router.py:6204`) |
| **B — Co-occurring foundational signal** | A foundational-tier signal degraded in the same window | Strong | glucose variability rising alongside weight plateau |
| **C — Co-occurring non-foundational state** | A supporting-domain metric moved in the same window | Moderate | routine adherence down, calendar density up |
| **D — Distal/stranded correlation** | A computed-but-unlinked domain moved similarly | Weak (correlation only) | journal stress up, faith streak broken |
| **E — Temporal coincidence only** | Something happened around the same time, no metric linkage | Lowest — context, not cause | a trip occurred |

**Ranking rules:**
- A and B can support an "I know / strong I-suspect" conclusion.
- C, D, E may **contribute** to a hypothesis but cannot, alone, be asserted as *the* cause.
- More low-tier evidence does **not** sum to high-tier certainty. Five weak correlations are still a suspicion, not a proof.

---

## 3. Causal Confidence Rules

ChatGPT must never overstate causality. The binding rules:

1. **Correlation is labeled correlation.** Any tier C/D/E contribution is phrased as "moved together with," "coincided with," "may be contributing" — never "caused."
2. **System-certified causality may be stated as the leading cause**, but still attributed to evidence ("your data shows sleep dropped, which the system links to slower loss").
3. **A single high-tier cause is preferred to a sprawl of weak ones.** If A/B explains the observation, the CoS leads with it and lists others as secondary — it does not present a flat list of 10 equal "causes."
4. **Causal direction is not assumed.** Stress up + weight flat could run either way; the CoS notes the co-movement without asserting which drives which, unless a provider encodes direction (e.g., CDCE's time-lagged sleep→mood).
5. **Absence of evidence is not evidence.** If a domain couldn't be checked (STRANDED/UNWIRED), the CoS does not infer it's *fine* — it names it as unchecked.

---

## 4. Conflicting Evidence Handling

Holistic diagnosis routinely surfaces deterministic facts that point different directions. The architecture's rule: **present, weight, and explain — never average or suppress.**

| Conflict pattern | Behavior |
|------------------|----------|
| Two facts suggest opposite conclusions (nutrition compliant ✓ but sleep degraded ✗) | Present both; weight by tier (A/B over C/D); explain why one likely dominates |
| A deterministic value contradicts the user's belief | Surface the provider value plainly; flag the gap; do not capitulate to the assertion (Law 16) |
| Two providers disagree on the same fact | Defer to the higher-precedence source (signal source precedence; canonical over rollup, Law 16); note the discrepancy |
| Evidence is mixed with no dominant tier | State honestly that the picture is mixed; give the leading hypothesis at reduced confidence; name what would disambiguate |

Averaging conflicting evidence into a bland middle is explicitly forbidden — it destroys the truth the providers worked to compute.

---

## 5. Missing Evidence Handling

| Situation | Behavior |
|-----------|----------|
| A high-causal-value domain is unreachable (STRANDED/UNWIRED) | Name it as the key gap; give the conclusion *conditional* on it ("if your routine held, then sleep is the likely driver") |
| The focal domain itself lacks a needed field (e.g., "recent changes" delta absent) | Use what exists (trend strings), flag the missing aggregate |
| WLJ doesn't compute the data at all (ABSENT) | "I can't determine this from your data" — full stop |
| Enough is reachable for a partial answer | Answer the reachable part with confidence; bound the rest explicitly |

The governing principle: **a holistic CoS is allowed to be incomplete, but never allowed to be invented.** Disclosed gaps build trust; hidden gaps destroy it.

---

## 6. Uncertainty Communication

The diagnostic answer's *shape* encodes its confidence (full vocabulary in Doc 6):

```
[Observation — provider fact, stated plainly]
[Leading cause — tier A/B evidence, "high confidence, your data shows…"]
[Contributing factors — tier C/D, "these moved with it; correlation, not proof"]
[Gaps — "I couldn't check X / your data doesn't track Y"]
[What would sharpen this — the specific evidence that would raise confidence]
```

This structure makes the certainty *legible*: the user can see exactly which parts are certified truth, which are the CoS's read, and which are unknown — which is precisely what a trustworthy Chief of Staff owes.

---

## 7. The Diagnostic Contract (one line)

> **State what changed from truth. Lead with the strongest-linked cause. Mark every weaker factor as correlation. Disclose every gap. Never let synthesis impersonate a fact.**

---

*Document 4 of 6. Historical pattern-matching and the coaching synthesis that builds on this framework are in Document 5; the confidence vocabulary is formalized in Document 6.*
