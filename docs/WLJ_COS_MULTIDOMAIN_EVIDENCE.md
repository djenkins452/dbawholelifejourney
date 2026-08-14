# WLJ Chief of Staff — Multi-Domain Evidence Representation & Synthesis Handoff

**Type:** Investigation + controlled A/B/C experiment. No production behavior change shipped; no aggregator, bundle, second model call, or summarizer built. STOP-and-report per the milestone.
**Date:** 2026-08-13
**Governing question:** *Are we asking OpenAI to synthesize evidence, or handing it several reports and then wondering why it writes another report?*

---

## 1. What the multi-domain tool payload actually looks like (traced, `get_analysis('overall')`)

Each domain's `get_analysis('overall')` returns a **self-contained per-domain envelope** (`domain_analysis.py::_domain_overview` / `_envelope`):

- **Deterministic facts only** — the `note` states "WLJ has made NO judgment here — no ranking, no verdict, no status, no advice." Verified: **no heuristic verdicts, recommendations, or interpretive prose** in the payload. (The legacy verdicts live in `deterministic_understanding`, not here.) The health branch already *removed* the old 115-key scorecard/narrative/verdict in favor of concept-organized facts.
- **But it is report-shaped and bloated:**
  - a labeled `concepts` tree (health) — "Body composition", "Glucose / metabolic" … each with labeled members (value/unit/change) — reads like section headers;
  - a `subjects` dict of **per-facet trend analyses** (health: **12**), each an 8-field `change` block (first/last/delta/pct_change/slope_per_point/direction/points_compared);
  - a `state` snapshot; `concepts` and `subjects` **overlap** (same facets, two views);
  - repeated per-call metadata: a **~150-token `scope` prose instruction repeated in every result**, plus `note`, `schema_version`, `generated_at`, `granularity`, `evidence:'rich'`, `subjects_covered`, `subjects_with_data`, `has_state`.

**Token size:** ~800–2,000 tokens/domain; a 4-domain whole-life turn ships **~6,200 tokens of evidence** (measured), much of it duplication (concepts vs subjects) and repeated instructional boilerplate (`scope`/`note`) that belongs in the system prompt once.

## 2. Controlled experiment (real model, worker `a229b308`/`d680e372`; production untouched)

Same model, same system prompt (CONSTITUTION), same question ("How am I doing overall in my life?"), same domains (health, nutrition, relationships, goals) — **only the tool-result representation varied**, delivered as tool messages:

- **A** — current production envelopes, verbatim.
- **B** — same deterministic facts, report scaffolding removed (no `scope`/`note`/metadata, concepts+subjects merged to one value+change per facet). N domain-partitioned results.
- **C** — the same cleaned facts **pooled into ONE combined block** (single tool result), not N domain-partitioned results.

| arm | evidence tokens | prompt tokens | output shape (across runs) |
|---|---|---|---|
| A | ~6,196 | 18,800 | domain tour (Health/Nutrition/Relationships/Goals) every run |
| **B** | **~690 (9× smaller)** | 12,624 (−6,176) | **still a domain tour** every run — grounding preserved |
| C | ~790 | 12,674 | **inconsistent**: one run a sharp prioritized judgment ("My read is you're progressing in health/fitness, but nutrition needs attention"), other runs a generic "several areas" multi-section answer |

## 3. Answers to the milestone's questions

1. **Facts or mini-reports?** Facts — but wrapped in a per-domain **report skeleton** (labeled concept groups + 12 nested subjects + metadata).
2. **Does each domain summarize itself?** Not in prose, but **structurally yes** — each arrives as a self-contained labeled sub-report.
3. **Facts mixed with heuristic interpretation?** **No** — the payload is verdict-free (the `note` guarantees it; verified).
4. **Does repeated domain structure encourage sequential summarization?** **Yes, but the driver is the PARTITIONING, not the per-result content** — see 6.
5. **Evidence buried under metadata/redundant prose?** Yes — ~9× bloat: repeated `scope` prose, concepts/subjects duplication, verbose change internals.
6. **Can the same model synthesize better with cleaner evidence?** **Cleaning per-result content (B) did NOT help** — B still toured. **Pooling into one block (C) helped only inconsistently.** So the sectioning is driven by evidence arriving as **N domain-partitioned tool results** (the model mirrors the partition), plus the model's default for the "how am I doing overall" framing — not by the per-result scaffolding.
7. **Fixable generically at the tool-result contract?** The **bloat** is (a 9× token reduction is available generically). The **sectioning** is not reliably fixable by a per-result representation change.
8. **Would it affect narrow questions?** A per-result cleanup would touch every `get_analysis('overall')`; narrow paths (`get_entity`/`get_domain_state`/single-subject) are separate. Not shipped, so moot.
9. **Is a second synthesis pass necessary?** Not *proven* necessary (C's best run shows one model can synthesize pooled evidence). But **no ALLOWED representation change reliably fixes the sectioning**, and the one that helped (pooled evidence) is a cross-domain aggregator — which this milestone forbids.

## 4. Decision — STOP and report (no production change)

- The milestone's implementation gate is "a small tool-result representation change that **materially and reliably improves synthesis** while preserving grounding." The experiment **does not prove that**: B (allowed) cuts 9× tokens and preserves grounding but does **not** improve synthesis; C (pooled) improves it only inconsistently **and requires a forbidden cross-domain aggregator**.
- Reliably guaranteeing judgment-led synthesis over multi-domain evidence therefore needs one of the mechanisms this milestone excludes (a pooled cross-domain evidence representation / aggregator, or a second synthesis pass). Per the stop condition, that is **reported, not built**.
- **Separately worth noting (not shipped):** the payload is ~9× token-bloated (repeated `scope` prose, concepts/subjects duplication, verbose change internals). A generic slimming of the `get_analysis('overall')` result — moving the repeated instructional `scope`/`note` to the system prompt and de-duplicating concepts/subjects — is a real efficiency/hygiene win (~6k fewer prompt tokens per whole-life turn) that **preserves grounding**, but it does **not** fix the sectioning and so is offered as a separate optional decision, not this milestone's fix.

**Bottom line:** we are handing OpenAI several domain-partitioned payloads (bloated, but verdict-free) and it mirrors the partition as sections. Cleaning the payloads removes the bloat but not the report; pooling the evidence breaks the mirror only sometimes and is the forbidden aggregator. The reliable fix is architectural (pooled evidence or a second pass) — a scoped decision for Danny, proven here before anything is added.
