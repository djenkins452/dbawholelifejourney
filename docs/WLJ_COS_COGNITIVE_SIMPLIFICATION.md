# CoS Cognitive Simplification — Migration Ledger

**Status:** Stages 0 and 1 COMPLETE (2026-09-03). Stage 2 not started.
**Direction (settled — do not re-debate):** OpenAI owns reasoning. WLJ owns canonical
truth, memory, deterministic calculations and safe consequences.

---

## Why

The certified runtime works, but it grew by accretion: every production trust failure was
answered with more prompt. The result is a system prompt the model reads before every
answer that is larger than most of the documents it reasons about, in which a rule that
protects the user's money sits in the same undifferentiated wall of text as advice about
how to phrase a follow-up question.

The architecture review recommended shortening it. It also recommended **not starting
there** — three confident hypotheses about this runtime had already been overturned by
measurement, and a 60% prompt reduction guided by intuition is exactly the change that
breaks something subtle and slow to detect.

So the migration starts by measuring, then by drawing a line, and only then by cutting.

---

## Stage 0 — Instrumentation (COMPLETE)

`apps/ai/model_interface/telemetry.py`, recorded on the `response` audit row each turn
already writes.

**Recorded:** prompt characters by section; the constitution's invariant/guidance split;
tools exposed, combined schema size, largest by name, and which were actually called;
tool-loop rounds and whether the cap was hit; history trimming by the token governor;
Phase-2 eligibility, whether it ran, and whether it materially changed the answer;
Phase-1 → Phase-2 context coverage and any silently-lost keys; duplicated-instruction
counts per section.

**Never recorded:** conversation text, the user's message, the answer, Personal Knowledge
statements, health or finance values, raw prompts, or evidence payloads. The Phase-2
comparison builds its word sets in memory and keeps only the ratio.

Certified by `apps/core/tests/test_cos_telemetry_contract.py`, which feeds every prompt
section a unique marker and proves no marker reaches the record — an assertion on the
DATA, so a future field that quietly carries text fails it.

Read it with:

```bash
python manage.py cos_prompt_baseline            # static composition
python manage.py cos_prompt_baseline --turns 50 # what real turns actually did
```

### Baseline (measured 2026-09-03)

| Section | Chars |
|---|---|
| Constitution | 68,946 |
| Structured context | 52,966 |
| Current situation | 4,773 |
| Completion reminder | 2,966 |
| Grounding | 1,771 |
| **System prompt** | **131,422** |
| Tool schemas (40 tools) | 71,897 |
| **Total per turn** | **203,319** |

Duplicated instruction mentions: **229** across the prompt — `retrieve/never-invent` 75,
`persona/voice` 81, `confirmation` 30, `grounding` 21, `active-subject` 13,
`current-truth` 9. (Measured against a real standing context on the development database;
production values will differ in the structured-context row.)

Largest tool schemas: `remember_about_user` 5,279 · `complete_execution_item` 4,622 ·
`get_analysis` 4,082 · `log_workout` 3,406 · `mutate_task` 3,202 · `get_entity` 3,011.

---

## Stage 1 — Constitution separation (COMPLETE)

`apps/ai/model_interface/constitution_map.py` classifies all 34 constitution paragraphs as
**INVARIANT** (protecting canonical truth, grounding, authorization, confirmation,
exact-target integrity, privacy/sensitivity, Personal Knowledge authority, or
write/postcondition integrity) or **GUIDANCE** (interpretation, judgment, prioritisation,
conversational behaviour, reasoning style, historical patches).

**Not one character moved.** Prompt position is semantics in this runtime — a rule read
after the model has already decided it needs no tools cannot change whether it needs tools.
Physically reordering the constitution into two sections would be a behavioural change
wearing the costume of a refactor. The split is therefore a classification OVER the text,
and `test_constitution_structure_contract.py` proves the classified blocks re-join into the
constitution byte for byte.

| | Blocks | Chars | Share |
|---|---|---|---|
| Invariant | 15 | 24,246 | 35.2% |
| Guidance | 19 | 44,634 | 64.7% |
| — of which historical patches | 4 | 13,596 | 19.7% |
| Mixed (both kinds in one paragraph) | 3 | — | — |

### The completeness guarantee

Blocks are addressed by a stable text anchor, never an index. Consequently:

* a constitution paragraph added without a classification → **test fails** (policy added
  unreviewed);
* a paragraph deleted → its classification entry is orphaned → **test fails** (policy lost);
* any rewording → byte-exact reconstruction fails → **test fails**.

An invariant must name the boundary it protects; guidance may not claim one; and only
guidance may be marked as a historical patch — safety boundaries do not retire.

### Historical patches (Stage-2 candidates — NOT removed)

| Block | Compensated for | Responsibility that now exists |
|---|---|---|
| HOW A CHIEF OF STAFF BEGINS (5,208) | A user-supplied figure asserted as retrieved fact (the $2,300 payment that did not exist) | `apps.ai.finance_claim_guard`, enforced at the dispatch boundary — a boundary, not a rule to remember |
| EXECUTIVE ASSESSMENT (6,920) | Broad life questions answered from standing context without gathering current evidence | Two-phase execution with measured orientation coverage |
| CONVERSATION STATE (1,018) | Completed actions re-proposed; clarification answers landing on a stale subject | `record_completed_action` / `set_pending_clarification`, rendered in the ordered CURRENT SITUATION block |
| SELF-CONSISTENCY (450) | Answers contradicting earlier turns after Phase-2 context loss | `render_conversation_context` + completed-action state |

### Findings worth acting on later

* The word **"(governing)"** in the prose is not the same as an invariant. `COMPLETION`
  says "governing" but governs response shape, not the user's data.
* The **medical policy block is 9,096 characters** — the largest in the constitution — and
  is a genuine authority boundary wrapped around a large amount of answering guidance. It
  is the strongest candidate for a later invariant/guidance separation.
* **No constitution text defends the audit/cost boundary.** That boundary lives entirely
  in code (`llm_admission`, `ToolCallLog`), which is the right place for it — noted so
  nobody later "fixes" the gap by adding prose.
* `REASON ACROSS COMPETING HYPOTHESES` (4,565) is the clearest case of instructing a
  frontier model in how to think.

---

## Deliberately NOT done in Stages 0–1

Phase 2 remains. No tool was pruned or consolidated. No constitution guidance was removed.
Legacy runtimes remain. `deterministic_understanding` is untouched. No Action Safety
boundary was weakened, and none will be by this migration.
