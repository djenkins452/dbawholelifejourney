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

---

## Evidence for the migration: present is not relevant (2026-09-03)

The attachment incident had two halves, and the second is the one that matters to this
migration.

**First half — WLJ's fault, fixed.** Prior uploads were delivered inside `current_context`,
which means what is true right now. Stale data presented as current. WLJ must deliver
context accurately, and it was not.

**Second half — not WLJ's to fix.** Even with an image attached to the *current* turn,
"Mark Charge Watch complete" should not draw an image disclaimer. The image is present; it
is not relevant. That is an ordinary relevance judgment, and it belongs to the model.

### The invariant

> **EXPLICIT CURRENT USER INTENT > unrelated available context.**
> Context may be present without being relevant.

### What this rules out

No image-specific suppression rule. No deterministic task-versus-image router. No procedural
instruction telling the model when a file matters. Building any of those would be WLJ
growing a mind — the exact thing this migration exists to reverse — and it would make the
prompt longer to compensate for reasoning the model already does well.

The division of labour:

| | Responsibility |
|---|---|
| **WLJ** | Deliver context accurately, and say honestly what each piece IS — this turn's upload, a file from eleven days ago, an unresolved question |
| **OpenAI** | Decide what, of everything present, bears on what was actually asked |
| **Neither** | A rule that decides relevance in advance |

### The one thing WLJ owed here, and paid

A rule that *compels* commentary about context, keyed on that context existing, is WLJ
overriding the model's relevance judgment procedurally. One instance existed and has been
removed:

* `_attachment_lead` rendered a processing attachment as *"still being read — **tell the
  user** it's being read and to ask again in a moment"*. That is a script, triggered by a
  file's state, regardless of whether the user's request had anything to do with the file.
  It now reads *"still being read — contents not available yet"*: state, not speech.
* The Constitution's equivalent clauses are now scoped — *"WHEN THE USER'S REQUEST DEPENDS
  ON THAT ATTACHMENT, tell them it is still being read"*, and for an unreadable or truncated
  file, *"WHEN YOU ARE ANSWERING FROM IT, say what you can and note the limit"*. The
  protection is intact (never guess unread contents); only the compulsion is gone.

`PresentIsNotRelevantTests` in `apps/core/tests/test_attachment_lifecycle_contract.py`
certifies the absence of that coercion — asserting on a file's own state line, since the
block legitimately *forbids* one wrong statement ("never tell the user to upload a document
that is listed here") and a prohibition is not a compulsion.

### Carried into Stage 2

This is direct evidence for the migration's thesis and for the ranking of its candidates:
when the assistant answers badly with accurate context in front of it, the first question is
whether WLJ mislabelled the context — not which procedural rule to add. Every rule that
tells the model *when* something matters is a Stage-2 candidate on exactly these grounds.

---

## Stage 2, experiment 1 — the Phase-1 verdict boundary (COMPLETE 2026-09-04)

**Chosen over block 22 on production evidence**, not on size. The mechanism already existed
and was already trusted; this applies it symmetrically rather than inventing anything.

**Removed from Phase 1** (the existing `_VERDICT_KEYS`, unchanged): `momentum`,
`strategic_summary`, `momentum_score`, `momentum_7d_avg`, `momentum_summary`,
`momentum_trend`, `recommended_action`.

**Retained**: primary challenge, challenge reason, biggest risk, workload + summary,
cognitive load, health read, recovery/intervention flags, executive & clinical priority,
patterns, wins, opportunity, predictions, confidence, goal pace, material changes,
`milestone_percent`, `progress_score`, and every canonical execution bucket.

**Block 17**: 1,122 → 824 chars. Only the deference clauses went, because only they existed
because a conclusion was supplied.

**Prompt**: constitution 69,067 → 68,769; structured context 52,934 → 49,182; system prompt
131,386 → 127,461; with tool schemas 199,358.

**The lesson that generalises.** The narrow fix — strip one section — was wrong inside ten
minutes: the same verdict arrived from `missions[*].progress`. A boundary drawn per-section
requires every future section to opt in from memory; a boundary drawn at the envelope cannot
be forgotten. Both phases now share one list, one function, one boundary.

**Still deliberately unchanged**: Phase-2 eligibility, Phase 2 itself, every other
constitution block, every tool.
