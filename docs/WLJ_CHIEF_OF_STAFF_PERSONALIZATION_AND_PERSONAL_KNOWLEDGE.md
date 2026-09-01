# WLJ Chief of Staff Personalization & Personal Knowledge — Target-State Design

**Status:** ✅ **APPROVED / FROZEN FOR IMPLEMENTATION PLANNING** — R2 applied.
**Date:** 2026-08-17 (R2)
**No code changed. No migrations. No provider configuration changed. Implementation not authorized.**
Companion evidence: the runtime investigation in this session.
**M0 contracts (frozen 2026-08-18):** `docs/WLJ_PERSONALIZATION_PERSONAL_KNOWLEDGE_CONTRACTS.md` — this document governs *what we are building and why*; the contracts document governs *what every term must mean*. Read this first, then the contracts, then the milestone.

> **Frozen means:** the conceptual architecture, canonical authorities, boundaries, learning policy, privacy model and milestone sequence in this document are settled and are the contract M0 writes against. Changing anything marked *settled* (§34a) requires a deliberate revision entry, not a decision made mid-implementation. Everything marked *implementation detail* (§34b) is deliberately left to its milestone.

---

## Revision Record

### R2 — 2026-08-17 (final decisions; design frozen)

| # | Decision | Sections revised |
|---|---|---|
| 1 | Existing-user knowledge review **ships with M3**, so About Me is truthful on day one | §28, §30, §35 |
| 2 | Progressive relationship-building default = **Occasionally** | §12a |
| 3 | Third-party knowledge: ordinary relationship context allowed; **sensitive third-party facts are deliberate-teaching only** in v1 | §14 |
| 4 | **ZDR is investigated, never depended on** — architecture correct with or without it | §16 |
| 5 | Final milestone map (M0–M7) | §35 |
| 6 | Design **frozen**; decisions classified settled / implementation detail / deferred | §34a–c, §38 |

### R1 — 2026-08-17 (Danny's review decisions)

| # | Decision | Sections revised |
|---|---|---|
| 1 | Knowledge map reports counts, never qualitative coverage | §5 |
| 2 | Coverage authority guides; it never becomes a questionnaire | §7, §8 |
| 3 | Natural learning is **candidate-only** in v1 — *trust before magic* | §13, §35 |
| 4 | **Interaction Guidance is a distinct third truth**, not Personal Knowledge | §11, §21–27 |
| 5 | **Build the canonical PK authority; migrate `PersonalFact` into it** *(reverses R0's lean)* | §9, §21–27, §34 |
| 6 | **No content-hash tombstones.** Forget is guaranteed by the v1 learning gate + a visible boundary list | §15 |
| 7 | Privacy contract moves into the foundation; disclosure ships before the interview | §16, §35 |
| 8 | New: **progressive relationship-building** (invitations to learn more) | §12a, §35 |
| 9 | Milestone sequence revised to Danny's ordering | §35 |

Three of these interact and should be read together: **(3) + (6)** — because v1 commits nothing without the user's consent, the "silently relearned" class closes without retaining any artifact of deleted content. **(5)** was reversed by reading `PersonalFact`'s actual schema rather than its reputation.

---

## 0. The one-paragraph version

WLJ has three generations of personalization and three half-built memory stores, and **none of them reach the certified `model_interface` runtime**. Rather than reconnect them, this proposal collapses all of it into **three composable dimensions** delivered through the **one envelope seam that already works**:

> **Persona** — how my Chief of Staff feels and speaks.
> **Operational Preferences** — how it works with me. *(configured settings + a small, stated-only tier of **Interaction Guidance**)*
> **Personal Knowledge** — what it knows about me.

Personal Knowledge becomes a single first-class truth authority with a first-class **About Me** workspace and a resumable, persona-voiced **Getting to Know You** interview. The net effect is *less* architecture, not more: five stores and two settings pages collapse into two authorities and one settings home.

**R1 posture:** deliberate teaching persists; ordinary conversation only ever proposes. *Trust before magic.*

---

## 1. Product vision and design principles

### Vision

A new user meets a Chief of Staff with a name and a personality they chose and enjoy. They teach it about their life at whatever depth they want, in conversation, not in a form. They can see everything it knows, correct it, and delete it. Years later it still knows their daughter's name, how they like to be pushed, and that they've always wanted to see Alaska — and they understand exactly where that lives and who processes it.

### Principles

1. **One Chief of Staff, three composable dimensions.** Persona ≠ Preferences ≠ Knowledge. Choosing Texas Rancher must not silently override "Low Question Frequency."
2. **Structure is for retrieval and control, not interpretation.** WLJ stores and indexes personal facts. It never computes what they mean. (Constitution I.4.)
3. **The default experience is a name and a persona.** Depth is available, never required. No cockpit.
4. **One acquisition spine.** Interview and ordinary conversation converge on the same authority through the same candidate → confirm → audit path.
5. **Never a second copy of domain truth.** Personal Knowledge *references* canonical entities; it does not shadow them.
6. **Deletion must be believable.** If a user says "forget that," it must not come back next week.
7. **Honest privacy.** We do not claim the model isn't involved when the model is conducting the conversation.
8. **Coverage is about stored knowledge, never a judgment about the person.**
9. **Personas are a feature, not a legacy.** Fun is a product requirement (settled).

---

## 2. Evidence: what exists today

Verified by runtime trace, not inference. Full file:line evidence in §36.

### Personalization — three generations, none delivered

| Generation | Where | Reaches certified CoS? |
|---|---|---|
| `CoachingStyle` DB rows with `prompt_instructions` (14 personas) | `apps/ai/models.py`, `apps/ai/fixtures/coaching_styles.json`, migration `0015` | **No** — read only by the retired `personal_assistant.py` |
| PIL persona templates (greeting/warning/closing frames) | `apps/core/ai_persona/*` | **No** — used only by briefings, weekly reports, interventions |
| `ai_relationship` projection | `apps/ai/cos_services/ai_relationship.py` | **Yes** — but carries only the persona *slug*, never its voice |

**Consequence:** selecting *Army Drill Sergeant* today changes nothing about how the Chief of Staff talks to you in chat. The model receives the bare string `"drill_sergeant"` with no instructions attached.

### Memory — three stores, none delivered

| Store | Written by | Read by certified CoS? |
|---|---|---|
| `UserPreferences._ai_personal_context` (the 203-line encrypted blob) | conversation-clear extraction only | **No** (Dashboard insight only) |
| `PersonalFact` (`apps/core/ai_memory/`) | `post_response_intelligence` — which `model_interface` never invokes | **No** |
| `BehaviorDirective` / reflection learning | same dormant path | **No** (read only by `chatgpt_cos`) |
| `LearnedCommunicationPreference` | **nothing, ever — zero writers in the codebase** | Projected as permanently `[]` |

### Settings scattered across two pages plus nowhere

- **Preferences page:** AI Profile, Learned Context, coaching style, response detail, PA enable/consent.
- **CoS Settings page:** display name, accountability, question frequency, sensitivity topics, event reflections, relationship suggestions, Learning Mode.
- **No UI at all** (fields exist, are projected, unreachable): `default_relationship`, `personality_overlay`, `preference_learning_enabled`, `assistant_confirm_actions`.

### What genuinely works (and is the seam to build on)

`personal_truth` → `personal_truth_for_context()` → standing context → `json.dumps` into the system prompt, with the same composer also backing the `get_user_truth` tool. **This two-tier pattern is certified and proven.** Personal Knowledge should plug into it rather than invent a delivery path.

---

## 3. Proposed Preferences information architecture

I'm challenging the proposed five-section split in one place: **Identity and Relationship & Personality are the same act.** Naming your Chief of Staff and choosing who it is belongs on one screen, and it should be the most enjoyable screen in the product.

```
Preferences → Chief of Staff
  ① Your Chief of Staff        name + persona gallery          ← the fun screen
  ② How We Work Together        depth · accountability · proactivity ·
                                question frequency · follow-through ·
                                confirmations · event reflections ·
                                relationship suggestions
  ③ Boundaries                  sensitive topics · what not to raise unprompted
  ④ Privacy & Learning          AI processing consent · what may be learned ·
                                provider transparency · export · delete

About Me                        ← TOP-LEVEL destination, not a Preferences accordion
  Getting to Know You · Knowledge Map · Manage what's known · Privacy summary
```

**Why four, not five:** "Communication" and "Guidance & Accountability" both answer *how does it work with me* and split awkwardly (is "directness" communication or accountability?). One operational section with clear grouping is simpler and matches the mental model.

**Why About Me is top-level:** it is a workspace the user visits to *do* something, not a settings panel. Burying it under Preferences is what produced today's textarea. Agreeing with the original instinct here.

**Retire the separate CoS Settings page.** Two settings homes for one assistant is the confusion that let `sensitivity_tags` drift out of the runtime unnoticed.

---

## 4. Persona architecture (settled requirement — preserve and improve)

### The product model

**Persona = voice.** The user picks a named character from a gallery. That is the whole interaction. No sliders on the primary path.

**Operational Preferences = behavior.** Orthogonal, separately chosen, and they **win**.

### Deterministic precedence — the rule that makes composition work

```
explicit user setting  >  persona default  >  system default
```

Each resolved value carries a provenance tag (`user` / `persona` / `default`) — reusing the `_sources` pattern already in `ai_relationship`. This is what lets *Texas Rancher + Deep Dive + Firm Accountability + Low Question Frequency* work without the persona stomping the operational choices. A persona may *suggest* "high question frequency"; an explicit user choice always overrides it, and the UI says so ("Texas Rancher usually asks a lot — you've set this to Low, which wins").

### Persona internals (maintainable, not user-facing)

A persona is a named bundle of reusable behavioral attributes, so fourteen personas don't mean fourteen hand-written prompt essays:

- **Voice attributes** — register, warmth, directness, humor, formality, verbosity bias, signature expressions, regionalisms
- **Operational defaults** — the starting values it suggests for §3②
- **Rendered instruction block** — composed from the attributes, cached, delivered to the model

`CoachingStyle` already has the right shape (admin-editable, no deploy needed to add a persona — real product value). It becomes the **single persona registry**, extended with structured attributes and operational defaults.

### The highest-value persona fix

**The persona's voice must reach the envelope.** Today only the slug does. The `ai_relationship` projection must carry the composed instruction block. This is a small change with a large, immediately felt product effect — fourteen personas that currently do nothing in chat start working.

### Personas apply everywhere, including the interview

The Getting to Know You interview is conducted **in the user's persona voice**. Southern Belle asks about your family differently than the Marine Gunnery Sergeant does.

**Invariant (testable):** *the knowledge gathered is persona-invariant; only the wording differs.* Same coverage map, same extracted facts, same storage. This is what keeps personas fun without making them a truth risk.

---

## 5. About Me workspace

```
┌─────────────────────────────────────────────────────────┐
│  About Me                                                │
│  What your Chief of Staff knows about you.               │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Getting to Know You                    [Continue] │  │
│  │  We've talked about family and work.               │  │
│  │  Picking up where we left off.                     │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  What I know about you                                   │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Family & Important People      14 things I know  → │  │
│  │ Work & Career                   8 things I know  → │  │
│  │ Interests                       3 things I know  → │  │
│  │ Goals & Dreams          nothing yet · Tell me →    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Manage everything  ·  What I've been told  ·  Privacy   │
└─────────────────────────────────────────────────────────┘
```

**Presentation law (R1 — not styling, a product rule):** the map **reports stored knowledge as a count and nothing else.** It never evaluates how complete the user's life information is.

**Forbidden:** "Rich" / "Some" / "Not yet" as quality labels · percentages · completeness scores · progress bars · comparisons · "incomplete" / "missing" / "needs attention" · any colour that encodes sufficiency.

**Permitted:** a factual count (*"14 things I know"*), a plain empty state (*"nothing yet"*), and an action (*"Tell me more about this"*). An empty topic is a **neutral fact about WLJ's storage**, never a gap in the person. A user with no interest in discussing faith must see nothing that reads as a deficiency — this is the Visual Truth Contract instinct applied to knowledge: *only actual completion may look like completion*, and here **nothing is ever "complete," because a life is not a form.**

**Inside a topic:** the individual facts, each with provenance ("You told me this on 12 March" / "From your Getting to Know You conversation" / "You imported this"), and per-fact actions: **Edit · Delete · Pin · Mark sensitive**. Plus one button: **"Tell my Chief of Staff more about this"** — which resumes the interview scoped to that topic.

**Recently learned** is the trust surface: a quiet weekly digest of what natural conversation added, reviewable and reversible. Not an interruption; a receipt.

---

## 6. Getting to Know You — the experience

**Opening** (in persona voice):

> I'm your Chief of Staff. The more I understand about you, the better I can help.
> I'd like to get to know you — your family, work, what matters to you.
> You're in control: skip anything, tell me that's enough, go deeper, or stop and come back later.

**User control vocabulary — recognized natural language, not buttons:**

| The user says | What happens |
|---|---|
| "skip" / "next" | current question abandoned, topic stays open |
| "that's enough about family" | topic marked *satisfied by user*, never re-raised unprompted |
| "ask me more" / "go deeper" | depth increases within the topic |
| "just the basics" | depth capped for the session |
| "let's come back to this later" | topic parked, resumable |
| "I don't want to discuss that" | topic marked **declined** — permanently off-limits until the user reopens it |
| "don't remember that" | current turn marked no-learn |
| "forget what I just said" | retroactive tombstone (§13) |
| "stop for now" | session suspended, fully resumable |

The distinction between **satisfied**, **parked**, and **declined** is deterministic state WLJ owns — that is what makes "don't ask me about that again" actually stick across years.

**Depth is user-driven.** "I'm married to Heather and we have one daughter, Haley, who's married to Parker" may naturally open Heather, Haley, Parker, and family dynamics — but only as far as the user leads.

---

## 7. Interview intelligence — the architecture question

### Options considered

| Design | Product quality | Privacy story | Resumability | Verdict |
|---|---|---|---|---|
| **Fully deterministic** (WLJ scripts questions) | Poor — a 75-field form wearing a chat costume | Cleanest ("nothing sent") | Trivial | Rejected — fails the product test |
| **Fully model-driven** (model owns everything) | Excellent | Same as chat | Fragile — coverage lives only in the transcript | Rejected — no deterministic authority over what's been covered or declined |
| **Hybrid — WLJ owns coverage, model owns conversation** | Excellent | Same as chat, honestly stated | Deterministic | **Recommended** |

### Recommended: hybrid

**WLJ owns (deterministic) — what is *known*, not what to *ask*:**
- What has been discussed, and what is stored from it
- What is **available to explore** (the ontology, as an inventory — not an agenda)
- What the user **parked** or **declined**, and when
- Session state, resumability, "where we left off"
- The candidate → confirm → commit → audit spine for every fact
- The persona voice instruction

**The model owns (reasoning) — what is *worth* asking:**
- What to ask next, and whether to ask at all right now
- Which thread in what the user just said deserves following
- How to phrase it in persona voice
- When a follow-up is natural vs intrusive
- Recognizing "that's enough about family" as intent
- Extracting candidate facts from what was said

### The ontology guides coverage and retrieval. It does not dictate a sequence. (R1)

This is the line that keeps the interview from decaying into a questionnaire wearing a chat costume.

| WLJ must NOT | WLJ must |
|---|---|
| Order the topics, or hand the model a "next topic" | Report topic states as **facts** the model reasons over |
| Score, weight, or prioritize what to ask | Enforce boundaries: declined topics are **never** offered |
| Treat an empty topic as a task to be completed | Treat an empty topic as a neutral fact |
| Mark the interview "finished" | Hold state so it can always resume |

**Concretely:** WLJ hands the model *"family: 6 facts, last discussed 3 turns ago · work: 0 facts · faith: declined 12 March · goals: parked"* — an inventory, unordered. The model decides that after "my daughter Haley married Parker," the interesting thread is Parker, **not** the next empty category.

### The ontology must be able to learn (R1)

If the model discovers an area the predefined map never anticipated — a user's decades-long involvement in a volunteer fire department, say — that knowledge must not be forced into "Other" and forgotten.

- A committed fact whose subject fits no existing topic is stored with an **emergent topic label** proposed at commit time.
- Emergent labels are first-class for retrieval immediately (the fact is findable, editable, deletable from day one).
- They surface in an operator review so the ontology can **grow deliberately** — an evolving inventory, never a hardcoded enum that requires a deploy to accommodate a human life.

This directly avoids repeating `PersonalFact`'s central flaw: eight fixed `fact_type` choices, hardcoded in Python (§9).

This is exactly the certified pattern already in production: WLJ supplies deterministic state in the envelope, the model drives the turn, writes route through `request_action`. **It reuses the existing CoS runtime rather than building a second conversational engine** — no new orchestration, no interview state machine invented from scratch, no second reasoning path. Constitution I.2 and IV.4 both point here.

### The privacy mental model this permits

Because the model conducts the interview, we **cannot** say "nothing you say here is sent to the AI provider." The honest, simple, and actually reassuring framing:

> **This is a conversation with your Chief of Staff — so it works exactly like every other conversation you have with it.**
> Your Chief of Staff is powered by an AI provider, so what you say is processed by that provider to generate its reply.
> **What makes this different is what happens afterward: WLJ stores what you teach it in your account, so it's still there tomorrow.**
> **WLJ remembers. The provider processes.**

No special exemption, no asterisk, nothing that collapses under scrutiny.

---

## 8. Resumable interview state

One deterministic record per user (the coverage authority), holding:

- Per-topic status, depth preference, last-touched, count of facts gathered
- Session pointer: active / suspended / last question asked
- Declined topics, with the date declined (so the UI can offer "you told me this was off-limits — reopen?")

**Not** a transcript. The conversation itself lives in the normal conversation store; the coverage authority holds only the deterministic state. This keeps long-term memory out of Conversation State (constraint honored) and makes "continue where we left off" a deterministic read, not a re-derivation from chat history.

**R1 clarification — this record is an inventory, not an agenda.** It answers *"what do we know, and what did the user rule out?"* It must never acquire a `next_topic`, a completion percentage, or an ordering. The moment it does, the interview becomes a questionnaire and the model stops reasoning.

---

## 9. Personal Knowledge data model

### The core insight

The three example facts are genuinely different kinds of thing:

| Example | Kind |
|---|---|
| "Heather is Danny's wife" | relationship edge to a person |
| "They have been married since 1997" | attribute with a temporal anchor |
| "Heather tends to be more laid-back than Danny" | durable qualitative context |

**Trying to schematize the third is the trap.** It is comparative, subjective, and unbounded. Any schema that captures it becomes a personality-modeling engine — and WLJ interpreting "laid-back" is exactly the reasoning engine the Constitution forbids.

### The resolution: statement-primary, structure-secondary

Every unit of Personal Knowledge is **one fact record** whose payload is the natural-language statement. Structure exists **only to retrieve it and let the user control it**.

```
PersonalKnowledgeFact
  ├─ statement           the fact in natural language  ← THE PAYLOAD (encrypted)
  ├─ topic               family · work · goals · values · interests ·
  │                      communication · health_context · faith · history …
  ├─ subject_ref         → canonical Person / entity, when one applies (nullable)
  ├─ subject_label       free text when no canonical entity exists
  ├─ attributes          {} — sparse, only where unambiguous
  │                      (relation: "spouse", since: 1997, name: "Heather")
  ├─ provenance          interview · conversation · explicit · imported · legacy
  ├─ source_conversation → for "forget everything from that chat"
  ├─ confidence          extraction confidence (explicit statements = 1.0)
  ├─ sensitivity         normal · sensitive  → controls retrieval tier
  ├─ status              active · superseded · tombstoned
  ├─ superseded_by       → lineage for corrections
  ├─ pinned              user forced it into the standing tier
  └─ space/user          ownership boundary
```

- Fact 1 → `subject_ref`=Person(Heather), `attributes={relation: spouse}`
- Fact 2 → same subject, `attributes={since: 1997}`
- Fact 3 → same subject, **no attributes** — the statement is the whole fact

**The model reads the statement and reasons. WLJ never parses "laid-back."** The Truth/Reasoning boundary holds because WLJ's job stops at *store, index, retrieve, let the user control.*

### R1 — Build the canonical authority. Migrate `PersonalFact` into it. Retire it.

**This reverses R0's lean toward evolving `PersonalFact`.** I formed that view from its reputation as "the closest existing shape." Reading its actual schema (`apps/core/ai_memory/models.py:15–109`) changes the answer decisively.

| Target requirement | `PersonalFact` today | Gap |
|---|---|---|
| Topic / category | `fact_type` — **8 hardcoded choices** in Python | Structural — a new area needs a deploy; kills §7's emergent ontology |
| Canonical entity reference | `subject_name` — **a free string** | Structural — this *is* the shadow-person problem, in string form |
| Provenance | `conversation` / `manual` only | No interview, explicit, imported, or legacy |
| Source conversation | — | Absent; "forget that whole chat" is impossible |
| Sensitivity | — | Absent; sensitive facts cannot be excluded from the standing tier |
| Supersession lineage | `is_active` boolean | Correction **destroys** history rather than superseding |
| Pinning | — | Absent |
| Deduplication key | — | Absent (dedup is done by an LLM prompt today) |
| Space / ownership | plain `user` FK | Not in the shape the ratified PDP expects |
| Forget semantics | — | Absent |
| Structured attributes | — | Absent |
| Audit linkage | — | Absent |
| Encryption at rest | **`fact_text` is plaintext** | Adopting it as-is is a **privacy regression** — today's blob *is* encrypted |
| Natural-language payload | ✅ `fact_text` | The one genuine match |
| User editing | ✅ `is_active` | Partial |
| Retrieval | indexes built for the old access pattern | Rebuild |
| Extensibility | enum-bound | Structural |

**Roughly thirteen of seventeen requirements are missing, and five of those are structural** — entity references, lineage, space scoping, extensible topics, and encryption cannot be bolted on without changing what the model *means*. Evolving it would mean renaming its semantics, adding ~10 fields, encrypting an existing plaintext column in place, rebuilding its indexes, and inheriting a docstring that describes the exact behaviour we are retiring ("biographical life facts learned from conversations" — R1 §13 makes deliberate teaching the primary path, not extraction).

**And the migration it saves is nearly free anyway.** `PersonalFact` has been unwritten on the production streaming path since 2026-07-09 (`f98fd021`), so the row count is small and mostly stale. We would be inheriting years of conceptual debt to avoid a migration measured in hundreds of rows.

**Recommendation (decisive):** build `PersonalKnowledgeFact` to the §9 model, migrate `PersonalFact` rows into it as `provenance=legacy_extraction`, and **retire `PersonalFact` and the `ai_memory` fact stack**. Optimize for the authority WLJ should still want in 2031.

---

## 10. Person and relationship modeling

**Personal Knowledge must not create a second person table.** WLJ already has canonical people (relationships domain, Legacy people, and the in-flight person-consolidation program).

- Facts about a person carry `subject_ref` → the **canonical** Person.
- If the interview surfaces someone WLJ doesn't have (Parker), it **creates a canonical Person through the existing deterministic action path** — validated, confirmed, audited — not a shadow record.
- The relationship *edge* ("Heather is my wife", "Parker is married to Haley") is canonical relationship truth and belongs to the relationships domain.
- The *colour* ("Heather tends to be more laid-back") is Personal Knowledge attached to that person.

**Boundary rule:** if the relationships domain owns it, PK references it. PK owns only what no domain owns.

---

## 11. The boundaries (five concepts, three dimensions)

| Concept | Owns | Lifetime | Authority | Example |
|---|---|---|---|---|
| **Configured Preference** | how the CoS behaves, by explicit choice | until changed | Persona + Operational projection | "Deep Dive", "Texas Rancher" |
| **Interaction Guidance** *(R1)* | how the CoS should work with me, stated in words | until changed | Operational dimension, learned tier | "When I'm overwhelmed, give me one recommendation, not five choices" |
| **Personal Knowledge** | durable personal context | years, user-controlled | PK authority (new, singular) | "Heather is my wife", "always wanted to see Alaska" |
| **Canonical Domain Truth** | records, metrics, history | domain-owned | existing domain authorities | weight, goals, tasks, calendar |
| **Conversation State** | what we're doing right now | this conversation | `conversation_state.py` | active subject, pending confirmation |

**Enforcement rules:**
1. PK never duplicates domain truth. "My weight goal is 180" is a **Goal**, not a PK fact. If the CoS needs it, it calls the goals tool.
2. PK may *reference* domain entities but never caches their values.
3. Conversation State is never long-term memory. Nothing in PK is written from or read into it.
4. A configured preference is never inferred into PK, and a PK fact never silently changes a configured preference. "I like short answers" said in chat becomes a **candidate preference change the CoS offers**, never a silent setting flip.

Rule 4 is the one that prevents the class of "why did my Chief of Staff change how it talks to me?"

### R1 — Interaction Guidance is a third truth, not Personal Knowledge

R0 proposed merging `BehaviorDirective` into PK. That collapses two semantically different things to save a table. Danny is right to push back, and **`BehaviorDirective`'s own docstring names the distinction better than R0 did**:

> *"Unlike PersonalFact/ExtractedFact (which RECORD facts), a directive CHANGES behavior downstream."* — `apps/core/ai_memory/models.py:271`

**The separating test — one question:**

> **Does it describe the user's life, or instruct the Chief of Staff's behaviour?**

| Statement | Describes / Instructs | Home |
|---|---|---|
| "Danny's wife is Heather" | describes | **Personal Knowledge** |
| "Danny prefers direct answers" | instructs — *and a setting already exists* | **Configured Preference** (offered as a settings change) |
| "When Danny is overwhelmed, don't give him five choices" | instructs — *conditional, no setting exists* | **Interaction Guidance** |

### The rule that stops this becoming another uncontrolled store

**If a configured preference already covers it, it is a proposed preference change — never a learned directive.**

"I prefer direct answers" maps to the existing directness/persona controls, so the CoS *offers to change the setting*. Only guidance with **no settable equivalent** — conditional, situational, idiosyncratic — becomes Interaction Guidance. This keeps the store small by construction and prevents it drifting into a shadow settings system that silently overrides the user's explicit choices.

**Ownership:** Interaction Guidance belongs to the **Operational Preferences dimension** (how my CoS works with me) as its *learned tier* — not to Personal Knowledge, and not to Persona. It is projected alongside the configured preferences, and configured settings still win on any conflict (§4 precedence).

**v1 gate — stated only.** Only guidance the user **said in words** ("always give me one recommendation, not options") is stored. `BehaviorDirective`'s `observed` and `derived` sources — auto-created at 0.5–0.55 confidence from the model's own inference — are **not** carried forward in v1. That is the uncontrolled-learning risk, and it is exactly what R1 §13 rules out for PK too.

**Two things must be dropped from `BehaviorDirective` when it is rebuilt:**
- The **`meaning`** field ("why it matters") — that is WLJ storing an interpretation, which Constitution I.4 gives to the model.
- **`explain()`**, which composes prose. WLJ exposes the facts; the model does the explaining.

**User control is identical to PK:** every guidance item is visible, editable, and deletable in the same surface, with the same provenance display. Nothing about how the CoS treats you is hidden from you.

**Fate revision:** `BehaviorDirective` is **EVOLVE → rebuild as Interaction Guidance under Operational Preferences**, *not* MERGE into PK. Reflection keeps its observing role and may **propose** guidance; it never commits it.

---

## 12. Intentional discovery (the interview)

The interview is the *deliberate* acquisition path. Everything the user says flows through:

```
user statement → model extracts candidate → WLJ validates → commit → audit → About Me
```

Interview-sourced facts get `provenance=interview` and the highest default trust, because the user was deliberately teaching. They still appear in About Me and are still fully deletable.

---

## 12a. Progressive relationship-building (R1)

The relationship should deepen over years without the interview ever becoming homework. The Chief of Staff may **occasionally offer** to learn more:

> *"We've talked a lot about work, but I don't know much about what you enjoy outside it. Want me to ask you a couple of questions sometime?"*
> *"You've mentioned your brother a few times — I don't know much about him. Want to tell me about him?"*

**The division holds:** the model reasons that learning more would help; **WLJ deterministically owns what is actually known and every boundary the user has set.**

**Two deterministic signals WLJ can supply — both facts, never judgments:**
- *topic has no stored facts* (an inventory reading, not a deficiency)
- *an entity is referenced repeatedly in conversation with no PK facts attached* — this is what makes the brother example possible, and it is a **count**, not an inference

**User preference: "Help my Chief of Staff get to know me over time"**

| Setting | Behaviour |
|---|---|
| **Never** | No invitations, ever. Deterministic and absolute. |
| **Occasionally** *(default — R2)* | Rate-limited invitations, well spaced |
| **Naturally** | The model may offer whenever the conversation genuinely opens the door |

**R2 — the default is Occasionally, not Naturally.** A well-timed invitation to share more is one of the most personal moments the product can create; a badly-timed one is intrusive in a way that is hard to recover from. We have no production evidence yet about which we produce. **Trust calibration follows the same logic as §13:** start conservative, let real experience earn the change. *Naturally* remains available on day one for users who want a more actively developing relationship.

**The deterministic guardrails below apply at every setting, including *Naturally*.** They are WLJ-owned boundaries, not model judgment, and the preference never relaxes them.

**Guardrails — deterministic, WLJ-owned, non-negotiable:**
- A **declined** topic is never the subject of an invitation. Ever.
- Rate limit is enforced by WLJ, not by the model's judgment — the model cannot talk itself into asking again.
- "Not now" **parks** the topic; the same invitation is not repeated.
- Never in the same turn as the user raising something difficult.
- **Never phrased as a deficiency.** *"I don't know much about your brother"* is a fact about WLJ's storage and is fine. *"Your profile is incomplete"* is a judgment about the person and is forbidden — the §5 presentation law applies to the CoS's words as well as the UI.

An invitation is an offer between two parties who know each other, not a prompt to complete a form.

---

## 13. Natural conversational learning — conservative in v1 (R1)

**Product principle: trust before magic.**

R0 proposed auto-committing high-confidence facts with a receipt. R1 rejects that for initial release. Extraction accuracy, sensitivity classification, deduplication and correction have **no production evidence yet** — the pipeline has been dormant since 2026-07-09. Auto-committing into the store whose entire value is trust, before we know the extractor is trustworthy, spends the trust we are trying to build.

### Two learning intents, sharply separated

| Path | Intent | v1 behaviour |
|---|---|---|
| **Deliberate** — Getting to Know You; "Remember this…" | The user is **teaching** | **Persists** validated PK directly |
| **Ordinary conversation** | The user is **talking** | **Candidate only** — never auto-committed |

### The low-friction mechanism (this is the design question)

Candidates must surface **without turning conversation into a confirmation workflow.** Rejected: confirming inline every turn (destroys the conversation), and a notification per candidate (nagging).

**Recommended: a passive, batched, user-initiated review.**

1. Candidates are stored as **candidates** — a separate, quarantined state. They **never enter the envelope**, are never retrieved, and never influence a single response until accepted.
2. They surface in **About Me → "What I've been told"** as a quiet, unbadged list: *"I noticed these in our conversations. Keep any?"* — with **Keep all · Keep · Discard** per item. Reviewing is optional and never blocks anything.
3. **Optionally**, when the conversation is *already on that subject*, the CoS may ask once, naturally — *"You've mentioned Alaska a few times. Want me to remember that?"* — governed by the same §12a frequency preference, so a user who set **Never** is never asked.
4. **Unreviewed candidates expire** (≈30 days) and are purged. Quarantine is not a shadow store that accumulates forever.

The user gets the benefit of natural discovery with **zero conversational friction and zero surprise**, because nothing the CoS says is ever shaped by something the user did not accept.

### Requirements that carry forward from R0 unchanged

1. **It must actually run on the certified runtime** — enqueued from the `model_interface` generation task, off the request path, `safe_enqueue`, fire-and-forget.
2. **Learn only from the user's own statements.** Today's extractor feeds the assistant's response into the extraction prompt as "context" — a fabrication vector where the model's own guess becomes a stored fact. Remove it.
3. **Default-deny for sensitive classes** (§14) — never a candidate, let alone a commit.
4. **Batched, not per-turn** (§19).

### The path to permissiveness

Auto-commit becomes a **later, evidence-gated** decision (M6+), not a v1 default. The evidence required: measured extraction precision, sensitivity-classifier accuracy, deduplication behaviour on real data, and observed user accept/discard rates from the review surface. **The review surface is the instrument that produces that evidence** — accept/discard rates tell us exactly how good extraction is, from real users, at zero risk. That is a genuine reason to ship the conservative version first rather than merely a cautious one.

---

## 14. Sensitive information handling

**Never auto-learned. Explicit "remember this" only:**
sexual orientation · immigration status · criminal history · financial account details · credentials · precise location of others · third-party health information · religious belief *(unless the user has faith features enabled and volunteers it in a faith context)*.

**Sensitivity controls retrieval, not just storage.** A fact marked sensitive is **excluded from the standing tier** — it is never in every prompt. It is retrievable only via the truth tool when the conversation is already on that subject. This means a sensitive fact isn't sitting in the context of an unrelated conversation about lunch.

### Third-party knowledge — the settled policy (R2)

A Personal Knowledge system that cannot hold *"Heather is my wife"* is not a Personal Knowledge system. **Ordinary third-party relationship context is core to the product and is stored as part of the user's own Personal Knowledge.**

**Allowed — ordinary relationship context:**

> Heather is my wife · Haley is my daughter · Parker is married to Haley · Mike and Jarah are close friends · My brother and I aren't very close · Brian is my boss

These are facts about **the user's life and relationships**. They are the user's own context, held in the user's own space, the same as a diary. Prohibiting them would make the product impossible.

**Materially stronger handling — sensitive information about another person:**

another person's health or medical conditions · sexual orientation or sex life · financial accounts or detailed financial information · criminal history · credentials or secrets · precise private location · similarly sensitive protected or private information.

**The v1 rule — one sentence:**

> **Sensitive facts about another person are never learned from ordinary conversational candidate discovery. They require deliberate, explicit teaching, and even then they are marked sensitive and kept out of standing context.**

| | Ordinary relationship context | Sensitive third-party information |
|---|---|---|
| Deliberate teaching (interview, "remember this") | ✅ stored | ✅ stored **where policy permits**, marked sensitive |
| Ordinary conversation (candidate discovery) | candidate, per §13 | ❌ **never a candidate** — discarded, not quarantined |
| Standing context (every turn) | eligible | ❌ **never** — retrieval-tier only, on-subject |

Being mentioned in passing must never be sufficient for a sensitive fact about a third party to become routine standing-context material.

### Deliberately not a legal taxonomy

**The Personal Knowledge engine must not contain a comprehensive classification scheme for protected information.** That would be a reasoning engine wearing a compliance costume — unmaintainable, jurisdiction-bound, and forever wrong at the edges.

Instead:
- The sensitive **categories above are a bounded, enumerated policy list**, versioned in the M0 contract and changeable as a policy decision — not an inferred taxonomy.
- Classification is **default-deny**: anything the classifier is unsure about is treated as sensitive for candidate purposes, which fails toward *not learning* rather than toward learning.
- The **user's own explicit teaching is always authoritative** over the classifier. If they choose to tell their Chief of Staff about their mother's diagnosis, that is their call — WLJ stores it, marks it sensitive, and keeps it out of every unrelated conversation.
- **The consequence of the classifier being wrong is bounded by §13:** in v1 nothing from ordinary conversation commits without the user's acceptance, so a misclassification costs at most a discarded candidate — never a stored surprise.

The existing opt-out phrase detection (`personal_context.py`) is genuinely good design and its vocabulary should be carried forward into the new gate — it is one of the few pieces worth preserving verbatim.

---

## 15. User-control model — remember / forget / correct

| Verb | User says | Deterministic behavior |
|---|---|---|
| **Remember** | "remember that…" | explicit commit, `provenance=explicit`, never auto-expires |
| **Don't remember** (pre-emptive) | "don't save that", "off the record" | turn marked no-learn; nothing from it becomes a candidate |
| **Forget** (retroactive) | "forget what I just said" | **tombstone** — see below |
| **Correct** | "actually it's 1997" | old fact `superseded`, new fact `active`, lineage retained and visible |
| **Forget a conversation** | "forget that whole chat" | every fact with that `source_conversation` tombstoned |

### Guaranteeing "forgotten stays forgotten" — R1 revises the mechanism

**The requirement stands and is first-class:**

> *If I tell WLJ to forget learned conversational knowledge, it must not quietly relearn the same knowledge later.*

Naive deletion has a fatal failure mode: the user says "forget that," the fact is deleted, and later the same fact is re-extracted from a similar remark. The user concludes deletion doesn't work and never trusts the feature again.

**R0 proposed a content-hash tombstone. R1 rejects it on privacy grounds.**

Two genuine problems, not theoretical:

1. **A hash of a short statement is not anonymous.** Personal facts are short and drawn from a small plausible space. `sha256("Danny has depression")` falls to a dictionary attack in seconds. Retaining hashes of deleted personal statements retains **recoverable** deleted content — the exact opposite of what the user asked for.
2. **It contradicts the user's expectation.** "Forget that" means *gone*. Silently keeping a derived artifact of it — however well-intentioned — is the kind of thing that reads as a betrayal when discovered, and it would be discovered.

### The safest mechanism — and R1 §13 makes it nearly free

**The v1 learning gate already closes the class.** Because ordinary conversation **commits nothing without the user's explicit acceptance** (§13), a re-extracted fact cannot silently return — it can only appear as a **candidate**, which the user who just said "forget that" will discard. **There is no silent relearning path to defend against.** The two decisions were made independently and happen to compose: the conservative learning posture is also the strongest privacy posture.

**What v1 stores instead: a visible boundary, not hidden content.**

When the user forgets something, WLJ records a **"Don't remember" entry at subject/topic granularity** — *"Don't store things about my brother's health"* — which is:

- **User-authored in substance** — a boundary they set, not content they deleted
- **Visible** in About Me, listed plainly, with the date
- **Editable and removable** by the user at any time
- **Free of the deleted statement** — no text, no hash, no derivative

It suppresses future **candidates** in that area, and because the user can see and remove it, nothing is retained deceptively. This is a boundary the user is aware of, which is categorically different from a hidden hash of their deleted sentence.

**If auto-commit is ever enabled (M6+),** revisit whether finer-than-subject suppression is needed. If it is, the requirements are: **per-user salted**, non-reversible, **visible to the user as an entry they can delete**, and disclosed. Never a bare content hash, and never invisible.

**Net:** the class is eliminated, and nothing deleted is retained in any form.

**Also required:** export everything, delete everything, pause learning entirely, and a visible provenance trail on every fact.

---

## 16. Provider and privacy transparency

### Verified against current OpenAI API terms

WLJ calls `/v1/chat/completions` (`apps/ai/services.py:811`, reached by `model_interface` via `_call_api_with_tools`). Per OpenAI's current API data-controls documentation:

- **API data is not used to train OpenAI models by default** — "data sent to the OpenAI API is not used to train or improve OpenAI models (unless you explicitly opt in to share data with us)" (effective 1 March 2023).
- **Abuse-monitoring logs are retained up to 30 days** by default, "unless longer retention is required by law, or is reasonably necessary to protect our services."
- **Zero Data Retention (ZDR)** is available for `/v1/chat/completions` — WLJ's endpoint — but **requires prior approval by OpenAI**.

**Today's privacy page overstates and understates simultaneously.** `templates/core/privacy.html:177` says "We do not allow OpenAI to use your data for training their models" — directionally true but phrased as an active control WLJ exerts rather than the API default. And the 30-day abuse-monitoring retention is not disclosed at all.

**Do not ship any wording until WLJ's actual OpenAI org configuration is checked** (training-sharing opt-in status; ZDR approval status). The claim must match the account, not the documentation.

### The mental model to teach

> **WLJ remembers. The AI provider processes.**
>
> WLJ stores what you teach your Chief of Staff in **your WLJ account** — that's why it's still there tomorrow.
> To answer you, WLJ sends the relevant parts to our AI provider, which generates the reply and then doesn't keep it as your Chief of Staff's memory.
> The provider isn't where your Chief of Staff's memory lives. WLJ is.

No LLM architecture knowledge required to understand it.

### Layered disclosure — recommended

1. **Onboarding** — one sentence at AI consent, plain language.
2. **Preferences → Privacy & Learning** — a short panel: what's remembered, what's processed, what you control, link to full page.
3. **About Me** — one line plus a link, in context, where it matters most.
4. **"How AI & Your Data Work"** — the full page, in plain English, with the verified provider specifics.

All four link to (4). One source of truth for the wording, four entry points — the same "one authority" discipline applied to disclosure.

### R1 — Privacy is foundation, not a late milestone

R0 scheduled the privacy work at M6. That was wrong: **a user cannot meaningfully consent to being learned about after they have already been learned about.**

Split into two deliverables, both moved forward:

**The learning contract — M0, alongside the other contracts.**
The written, settled policy: what may be learned, by which path, what is default-deny, what sensitivity means, what forget guarantees, and what the provider does and does not retain. Every later milestone is built against it rather than discovering it.

**The user-facing explanation — ships with the surface it describes, never after.**
- The learning/privacy panel ships **with M2** (the moment anything is stored).
- The full "How AI & Your Data Work" page and the About Me disclosure ship **with M3** (the moment the user can see what's stored).
- **Both must be live before M4.** Getting to Know You is the single largest act of disclosure a user will make to WLJ; it cannot be the thing that ships ahead of the explanation.

**Provider-specific claims are release-gated.** No wording ships until WLJ's actual OpenAI organisation configuration is verified — training-sharing opt-in status and ZDR approval status. The claim must match the account, not the documentation. This is a release gate on M2, not a task in M6.

### R2 — Zero Data Retention: investigate, never depend on

**The architecture must be correct and honestly describable whether or not WLJ ever receives ZDR.** ZDR is a *provider retention configuration layered beneath* the architecture — it is never a prerequisite for Personal Knowledge, and no design decision in this document may assume it.

The invariant holds either way:

> **WLJ remembers. The configured AI provider processes.**

ZDR changes only *how long the provider holds the transient copy it processed* — it does not change who owns the memory. That is precisely why the architecture can be settled now and the provider question answered later.

**Investigation required before the M2 disclosure gate** (against current official OpenAI documentation **and** WLJ's actual organisation/account configuration):

1. Is WLJ **eligible** for ZDR?
2. Is ZDR **currently enabled** on the account?
3. What are the **approval requirements** and lead time?
4. Is **every endpoint and capability WLJ currently uses** ZDR-compatible?
5. **Tool/function-call implications** — WLJ's CoS turns are tool-heavy; confirm ZDR behaviour across a multi-tool turn.
6. Any **endpoint-specific exceptions**.
7. **Abuse-monitoring implications** — what protection is given up.
8. **Operational and debugging implications** — what diagnostic capability is lost when provider-side logs no longer exist.
9. Would enabling ZDR **affect current WLJ functionality**?
10. **What exact privacy claims become supportable with ZDR, and what exact claims are supportable without it.**

**Both wordings must be drafted, and the honest one shipped.** Neither is a weak position — "not used for training, retained up to 30 days for abuse monitoring" is a clear, ordinary, defensible statement. Overclaiming is the only failure mode here.

**Not part of this design revision:** no provider configuration is changed, and no claim is written, until (10) is answered against the real account.

---

## 17. How Personal Knowledge reaches `model_interface`

**Reuse the certified seam — invent nothing.**

`personal_truth.py` is already the one composer feeding **both** the standing context and the `get_user_truth` tool. Personal Knowledge becomes a **section in that same composer**, delivered through `build_standing_context()` exactly as nutrition and health facts are today.

```
PK authority ──► personal_truth composer ──┬─► personal_truth_for_context()
                 (one composer)            │      └─► standing context ─► system prompt
                                           └─► get_personal_knowledge tool (on demand)
```

Zero new delivery paths. Zero new envelope fields beyond one section. The persona/operational projection extends `ai_relationship` the same way.

---

## 18. Turn-level selection — not dumping a life into every prompt

Two tiers, mirroring the proven pattern:

**Standing tier — always on, hard-bounded (~20–25 facts, ~400 tokens).**
Selected by **deterministic policy**, not by relevance-to-question (that would be reasoning):
- pinned facts first
- then topic weight (identity anchors: household, immediate family, work) × recency × provenance strength
- sensitive facts **excluded**
- hard cap enforced; overflow is reachable only by tool

**Retrieval tier — on demand.**
`get_personal_knowledge(topic=…, subject=…)` — the model calls it when it needs depth, exactly as it calls `get_user_truth` today. The model decides *when* it needs to know more about Haley; WLJ decides *what it's allowed to see*.

**Explicitly not recommended for v1: embedding/semantic retrieval.** Topic + subject filtering is deterministic, debuggable, and almost certainly sufficient at personal-knowledge scale (hundreds, not millions, of facts). Adding a vector store would be new architecture solving a problem we have no evidence of. Revisit only if topic filtering demonstrably fails.

---

## 19. Cost implications

Measured baseline (from the cost audit): a broad CoS turn is 3–9 billable provider requests against a ~60k-token prompt, **input-dominated**, at roughly $0.15–$0.19/turn.

| Addition | Impact |
|---|---|
| PK standing tier (~400 tokens) | **<1%** of an existing prompt — negligible |
| Persona instruction block (~200–300 tokens) | negligible |
| `get_personal_knowledge` tool calls | on demand, same as any truth tool |
| Interview turns | conversation-priced; **user-bounded** (they choose the length) |
| **Natural learning extraction** | **the real cost driver** — one extra call per qualifying turn |

**Cost controls, designed in from the start:**
- Keep the existing **regex pre-screen** — most turns never trigger extraction.
- **Batch extraction** per conversation-close or per N turns, not per turn.
- Use a **cheaper model tier** for extraction (it's structured extraction, not reasoning).
- Route every call through `record_llm_event` with a distinct `traffic_class` so it is visible in `/owner/finance/` from day one — this class of cost surge has bitten before.

**Prompt-cache note (the biggest lever):** the standing block is stable across turns and therefore cacheable. The PK standing tier must sit in the **stable prefix region** of the prompt, not interleaved with per-turn content, or it will break cache hits and cost more than it saves.

---

## 20. Security implications

- **Space-scoped from day one.** Per the ratified Security & Authorization Framework, `user_id` is the physical stand-in for a Personal Space. PK must carry the ownership boundary in the shape the future PDP expects, so it never needs a re-scoping migration.
- **Field-level encryption on statement text**, matching today's `encrypt_personal_data` treatment of the blob.
- **Complete export and deletion**, including tombstones and lineage.
- **New surface: prompt injection.** PK statements are user-authored text that enters the system prompt. A malicious or imported entry could attempt to issue instructions. Mitigations: deliver PK strictly as **data inside the structured-context JSON block** (already the pattern), and add an explicit constitutional clause that context fields are data and never instructions. Worth naming because it is a genuinely new attack surface that today's flat blob also has but nobody has articulated.
- **Third-party data** — facts about others are stored under the user's ownership and must be included in that user's export/delete.

---

## 21–27. Fate of every existing system

**Legend:** KEEP · EVOLVE · MERGE · MIGRATE · RETIRE

### Memory stores

| System | Fate | Why |
|---|---|---|
| `ai_profile` (2,000-char manual biography) | **MIGRATE → RETIRE** | A user should never maintain a biography by hand while WLJ separately keeps learned facts. Becomes **seed input**: "I read what you wrote — let's build on it." Extracted into PK, then the field retires. Its real value was always as an *introduction*, which is exactly what the interview opening is. |
| `_ai_personal_context` (the 203-line blob) | **MIGRATE → RETIRE** | Parse each line into a PK fact with `provenance=legacy_extraction`, presented to the user for review (§28). Then drop the field and delete `apps/ai/personal_context.py` entirely. |
| `PersonalFact` (`ai_memory`) | **MIGRATE → RETIRE** *(R1 — reversed)* | Thirteen of seventeen target requirements missing, five structurally (§9). Adopting its plaintext `fact_text` would be a privacy regression. Migrate its rows into the new canonical authority as `provenance=legacy_extraction`, then retire it and the `ai_memory` fact stack. |
| `LearnedCommunicationPreference` | **RETIRE — delete the table** | **Zero writers have ever existed.** Its role is served by Interaction Guidance / configured preferences. |
| `BehaviorDirective` | **EVOLVE → Interaction Guidance** *(R1 — no longer MERGE)* | A directive *instructs behaviour*; a PK fact *describes a life*. Semantically distinct — see §11. Rebuilt under the Operational Preferences dimension, **stated-source only** in v1, with `meaning` and `explain()` dropped (WLJ must not store interpretation or compose prose). |
| Reflection read-back (`approved_correction_context_block`) | **EVOLVE** | Must reach `model_interface` (today only `chatgpt_cos`) — delivered through the PK/preference projection, **not** a second context block. |
| `post_response_intelligence` | **EVOLVE + reconnect** | Becomes the natural-discovery candidate pipeline, enqueued from `model_interface` (§13). |
| Executive Reflection engine | **KEEP** (narrowed) | Keeps its observation/EIO/scorecard role. Stops owning a private preference store. |

### Personalization

| System | Fate | Why |
|---|---|---|
| `CoachingStyle` + 14 personas | **KEEP + EVOLVE** | Becomes the single persona registry. Add behavioral attributes + operational defaults. **Must reach `model_interface`.** Admin-editable without deploy is real product value — preserve it. |
| `apps/core/ai_persona` (PIL templates) | **KEEP (contained) → RETIRE (phased)** | Still live on deterministic-render surfaces (briefings, weekly reports, interventions). Retires when those surfaces move to model rendering. Do not touch now. |
| `ai_coaching_style` field | **EVOLVE → `persona_key`** | It is a persona, not a coaching style. The name has caused the conceptual confusion. |
| `personality_overlay` | **RETIRE** | Redundant with persona. Never had UI. Delete the field. |
| `default_relationship` | **EVOLVE** | Finally gets UI as part of persona/relationship selection. |
| `cos_display_name` | **KEEP** | Works, reaches the model, users like it. |
| `cos_response_style` | **KEEP** | Operational depth. Works today. |
| `assistant_confirm_actions` | **KEEP → expose** | Reaches the model; has no UI. Surface it in §3②. |
| Blueprint `accountability_style`, `question_frequency` | **KEEP → MOVE** | Correct concepts, wrong home. Move into the one CoS settings surface. |
| `sensitivity_tags` | **KEEP → EVOLVE** | Correct concept; **does not reach `model_interface`** today. Must be projected. Home: §3③ Boundaries. |
| `relationship_suggestions_enabled`, `event_reflections_enabled` | **KEEP → EVOLVE** | Proactivity controls; must reach the runtime. Home: §3②. |
| `preference_learning_enabled` | **EVOLVE** | Becomes the master learning control in §3④. Finally gets UI. |
| Learning Mode (`cos_learning_mode_active`) | **KEEP** | Genuinely enforced on the write path (`intent_service.py:1418`). A distinct concept from preference learning — keep the distinction explicit in the UI so they are never conflated. |

### Enablement, consent, and settings surfaces

| System | Fate | Why |
|---|---|---|
| `personal_assistant_enabled` | **RENAMED (2026-09-02)** | Correct that the CoS *is* the product, so it is no longer a switch for the product. Renamed `proactive_assistance_enabled` (`users.0096`): it now controls interruption only — check-ins, briefings, suggestions, the expanded panel. Access is governed by `personal_assistant_consent`. |
| `personal_assistant_consent` | **MERGE** | **Do not lose the consent** — merge into one AI data-processing consent. |
| `ai_enabled` + `ai_data_consent` | **KEEP → CONSOLIDATE** | Today four gates guard the CoS. Collapse to **two**: *AI enabled* and *AI data processing consent*, plus a new *Learning enabled*. Fewer gates, same governance, far less confusion. |
| Separate CoS Settings page | **MERGE → RETIRE the page** | One assistant, one settings home. This split is what let `sensitivity_tags` drift out of the runtime unnoticed. |
| Preferences "What I Know About You" accordion | **RETIRE** | Replaced by the About Me workspace. |
| `personal_truth` composer / Standing Context / ECE | **KEEP + EXTEND** | The seam that works. Extend, never fork. |
| Conversation State | **KEEP — unchanged** | Explicitly out of scope for memory. |

### What can be deleted

`apps/ai/personal_context.py` · `LearnedCommunicationPreference` model + table · `_ai_personal_context` field · `ai_profile` field + nudge fields · `personality_overlay` field · CoS Settings view + template + URLs · PA enable/consent fields + the two gate checks · the Preferences learned-context accordion and its JS.

**And the largest deletion available:** once `model_interface` is universal, the legacy `personal_assistant.py` and `chatgpt_cos` runtimes retire — and with them `prompt_builder.py`'s personalization assembly, `dashboard_ai.py`'s context reader, and the entire reason three parallel personalization systems exist. **That single retirement removes more architecture than everything else in this document combined.**

---

## 28. Migration considerations (not the plan)

- **The 203 facts are unverified.** They were extracted by an LLM from transcripts, never reviewed, possibly stale, possibly wrong, possibly duplicated. Migrating them silently into a trusted store would import unknown errors into a feature whose entire value is trust.
- **R2 — the review experience ships with M3, not later.** An existing user must never open About Me and see an empty workspace while WLJ still holds their legacy Learned Context, AI Profile and `PersonalFact` rows. That would be the product telling a visible lie on the exact surface built to prove it remembers.

### R2 — The existing-user product moment

Conceptually (wording to be written at M3, not fixed here):

> *"I've learned some things about you from our previous conversations. Let's go through them together — keep what's right, correct what's changed, and remove anything you'd rather I didn't remember."*

**Design requirements:**

| Requirement | Why |
|---|---|
| Legacy knowledge is **reconciled far enough that About Me truthfully represents what WLJ previously knew** | The workspace must be honest on day one |
| Imported facts carry **`provenance=legacy_extraction`** and are **visibly marked as unreviewed** | Never silently elevate 203 old LLM-extracted lines into unquestioned truth |
| Unreviewed legacy facts are **eligible for retrieval but not for the standing tier** until reviewed | Bounds the blast radius of an inherited error — a wrong fact can be found and corrected, but never quietly shapes every conversation |
| **Keep · Correct · Remove**, per fact, at the user's pace | Review is an invitation, never a gate on using the product |
| **Reviewing is optional and resumable** | Same posture as the interview |
| **Legacy source stores are not deleted at M3** | Deletion waits for M7, after adoption is proven |

**This is a trust moment, not a data-plumbing task.** Handled well, the first thing an existing user does in About Me is watch their Chief of Staff be corrected by them and accept it — which teaches the control model better than any explanatory copy could.
- **`ai_profile`** extracts cleanly into PK facts and is a natural interview seed.
- **`PersonalFact` rows** (if it becomes the authority) migrate structurally, not semantically.
- **Persona keys** map 1:1; no user loses their chosen persona.
- **Consent consolidation must be conservative** — a user who consented under the old four-gate model must not be silently upgraded to broader consent. Where ambiguous, ask.
- Sequencing, backfill, and rollback belong to the implementation milestone, not here.

---

## 29. New-user onboarding integration

Today's wizard has an "AI Coaching" step (step 5 of 7). Target:

1. **Meet your Chief of Staff** — name it, pick a persona from the gallery. Delightful, 30 seconds, and it immediately changes the voice of everything after.
2. **AI consent + the privacy sentence** — one screen, plain language.
3. **"Want to tell me about yourself?"** — start Getting to Know You, or skip. **Skipping must be completely graceful** — the CoS works fine without it and can offer later.

The interview must never be a gate on reaching the product.

---

## 30. Returning-user experience

- Existing users keep their persona and see it start actually working in chat (a visible improvement, worth a release note).
- About Me appears with their migrated knowledge and an invitation to review it.
- The interview is offered, never forced.
- "Recently learned" gives an ongoing, low-noise sense that the relationship is developing.
- Over years: the knowledge map fills in, the CoS references things naturally, and the user can always see why it knows something.

---

## 31. Mobile and web

- The interview is **conversational**, so it works natively in the existing chat surfaces on both — no separate mobile interview UI needed. This is a significant argument for the conversational design over a form.
- About Me's knowledge map: cards stack to a single column at ≤480px; per-fact actions must be ≥44×44px touch targets.
- Persona gallery is inherently card-based and mobile-friendly.
- Long fact lists need pagination or lazy loading on mobile.
- Standard WLJ responsive rules apply (375px verification).

---

## 32. Accessibility

- The knowledge map must not encode coverage in **colour alone** — "Rich / Some / Not yet" as text, always.
- The interview is text-first and screen-reader-native by construction.
- Every persona card needs a text description, not just an emoji.
- Destructive actions (delete a fact, clear all) need clear confirmation and an accessible name that says *what* is being deleted.
- Coverage states must be announced as stored-knowledge levels, never as progress toward a required goal.

---

## 33. Degraded behavior when the provider is unavailable

This is where WLJ-owned storage genuinely wins, and the design should lean into it:

| Surface | Behavior with provider down |
|---|---|
| About Me — view, edit, delete, add facts manually | **Fully functional** — it's WLJ data |
| Knowledge map | **Fully functional** |
| Persona / preference configuration | **Fully functional** |
| Interview | Unavailable, cleanly stated ("your Chief of Staff can't talk right now"), **state preserved, resumes exactly where it stopped** |
| Natural learning | Queued or skipped; never blocks a response; never silently corrupts state |
| Export / delete | **Fully functional** |

Nothing is lost, because nothing that matters lives at the provider. That is the architecture's promise, made visible.

---

## 34. Open product decisions requiring Danny's judgment

### 34a. Settled product decisions (frozen — change only by revision entry)

| Decision | Settled as |
|---|---|
| User-facing dimensions | **Persona · Operational Preferences · Personal Knowledge** |
| Personas | First-class, fun, prominent; named gallery, not sliders; reach the certified CoS |
| Precedence | **explicit setting > persona default > system default**, with provenance |
| Interaction Guidance | Semantically distinct from PK; lives in Operational Preferences; **stated-source only** in v1; suppressed where a configured preference already exists |
| PK authority | **Build the correct canonical authority; migrate `PersonalFact` into it.** `PersonalFact` is *not* the future authority |
| Encryption | Statement text encrypted at rest — **no plaintext regression** |
| Knowledge map | Factual counts only; no richness/completeness judgments (§5 presentation law) |
| Interview | Hybrid, persona-voiced, adaptive, resumable; ontology **guides**, never sequences; emergent topics allowed |
| Ownership split | Model owns *what is worth asking*; WLJ owns *what is known*, boundaries, resumability |
| Deliberate teaching | **Persists** |
| Ordinary conversation (v1) | **Candidate-only. No silent commits.** *Trust before magic* |
| Forget semantics | **No content-hash tombstones.** Believable without retaining recoverable deleted content |
| Third-party knowledge | Ordinary relationship context allowed; **sensitive third-party facts = deliberate teaching only**, never standing context (§14) |
| Sensitivity policy | Bounded enumerated list, default-deny, user's explicit teaching authoritative; **not a legal taxonomy in the engine** |
| Progressive relationship-building | Preference Never / **Occasionally (default)** / Naturally; guardrails apply at every setting |
| Privacy | Foundational; contract at M0, disclosure ships **before** Getting to Know You |
| ZDR | **Investigated, never depended on.** Architecture correct with or without it |
| About Me | First-class workspace; legacy review ships **with M3** |
| Seam | Reuse the certified Personal Truth / Standing Context / Model Interface path |
| Boundaries | Domain Truth never duplicated into PK; Conversation State never long-term memory |
| Retirement | Legacy removed **only after adoption is proven** (M7) |

### 34b. Implementation details intentionally left to milestones

Not decided here, and not blocking: exact field names, table structure and indexes (M0/M2) · the standing-tier ranking weights and cap (M2) · topic vocabulary v1 and the emergent-topic review flow (M0/M4) · exact user-facing copy everywhere, including the legacy-review wording (M3) · About Me's navigation placement (M3) · interview pacing and length (M4) · rate-limit numbers for invitations (M4) · candidate expiry window (M6) · extraction model tier and batching cadence (M6) · migration mechanics and backfill order (M3/M5).

### 34c. Genuinely deferred future product decisions

1. **Graduating natural learning to auto-commit** — requires production evidence from M6 and an explicit product decision. Deliberately deferred.
2. **User-created custom personas** — real product upside, real moderation cost. Revisit after M1 shows how personas land.
3. **Whether a free-form "anything else you'd like me to know" field survives** alongside structured PK. Decidable at M3/M4 once the interview exists.
4. **Whether the default for progressive relationship-building moves to *Naturally*** — an M5 evidence question by design.
5. **Whether ZDR is pursued and enabled** — investigation before M2; the answer changes the privacy *wording*, never the architecture.
6. **Timing of legacy runtime retirement** (M7) — unlocks the single largest architectural deletion, but only when `model_interface` adoption is proven.

**None of these blocks M0.** Each is either downstream evidence-gated or a copy/config decision that the frozen architecture already accommodates in both directions.

---

## 35. Recommended implementation milestones (descriptions only)

**FINAL (R2).** Verified against the repository for dependency problems — none found. Names and intent preserved as specified.

| | Milestone | Delivers |
|---|---|---|
| **M0** | **Personalization & Personal Knowledge Contracts** *(no code)* | Freeze canonical ownership, schemas/contracts, learning policy, Interaction Guidance boundary, sensitivity & third-party policy, persona composition/precedence, privacy/provider contract, domain-truth boundary, retrieval policy, user-control semantics |
| **M1** | **Personas + Unified CoS Preferences** | Persona voice reaches the certified CoS; two persona systems consolidate behind one registry; precedence with provenance; **one** settings home (CoS Settings merged); consent gates consolidated; orphaned fields exposed; `sensitivity_tags` + proactivity controls projected into the runtime |
| **M2** | **Personal Knowledge Foundation** | Canonical PK authority, deterministic retrieval, `personal_truth` integration, standing tier, provenance, sensitivity, security/space scoping, user-control semantics. **Privacy/provider disclosure foundation ships here**; provider-specific wording is release-gated on verified account configuration (§16) |
| **M3** | **About Me + Existing Knowledge Review** | The workspace — inspect, manage, correct, delete, add, provenance, knowledge counts, privacy transparency — **plus the legacy knowledge review experience (§28)** so the workspace is truthful on day one. **Legacy source stores are not deleted here** |
| **M4** | **Getting to Know You** | Persona-voiced hybrid interview; deterministic resumability and boundaries; model-driven conversational exploration; emergent topics; deliberate PK teaching |
| **M5** | **Production Validation / Relationship Refinement** | Real deliberate-learning experience validates PK quality, interview behaviour, boundaries, retrieval and progressive relationship-building. Absorbs migration hardening |
| **M6** | **Conservative Natural Conversational Learning** | Candidate-only discovery, quarantined state, passive review, optional contextual asks, expiry, instrumentation, evidence gathering. **Auto-commit requires later production evidence and an explicit product decision** |
| **M7** | **Legacy Retirement** | Superseded stores, fields, settings pages, duplicate personalization paths, and ultimately the obsolete runtimes — **only after adoption is proven** |

### Why this ordering is safe

- **Contract before construction (M0).** Every later milestone builds against a written policy instead of discovering one — which is how the current three-generation sprawl happened.
- **M1 is independent and immediately felt.** Fourteen personas that do nothing today start working. Highest delight-per-unit-of-risk in the programme, and it needs nothing from M2.
- **Nothing is stored before there is a way to see and control it** (M2 → M3, one step apart, with the privacy panel at M2).
- **Nothing is learned automatically before deliberate learning has production evidence** (M4/M5 → M6).
- **Nothing is deleted before adoption is proven** (M7 last, and M3 explicitly does not delete legacy sources).

Each of those is a one-way door held shut until the evidence to open it exists.

---

## 36. Runtime evidence

**Personalization delivery**
- `apps/ai/cos_gateway/runtime.py:37–64` — three coexisting runtimes; `use_model_interface` wins
- `apps/ai/model_interface/service.py:155–235` — the complete standing context; no personal facts
- `apps/ai/model_interface/service.py:628–644` — standing context JSON-dumped into the system prompt
- `apps/ai/cos_services/ai_relationship.py:120–221` — the working projection; carries the persona **slug only**
- `apps/ai/cos_services/personal_truth.py:290–330` — five sections; no learned knowledge
- `apps/ai/model_interface/constitution.py:181–184` — "Honor the user's AI Relationship" — with no voice instructions supplied

**Persona systems**
- `apps/ai/fixtures/coaching_styles.json` + migration `0015` — 14 personas
- `apps/ai/models.py` `CoachingStyle.prompt_instructions` — read only by `apps/ai/personal_assistant.py`
- `apps/core/ai_persona/persona_profiles.py`, `persona_registry.py` — second, template-based system; consumed by briefings/weekly reports/interventions only

**Memory stores**
- `apps/users/models.py:647–670` — encrypted blob; `apps/users/views.py:296` — "203" = non-empty line count
- `apps/ai/personal_context.py:264–307` — the only blob writer; `apps/ai/views.py:1688–1768` — fires on conversation clear only
- `apps/core/ai_memory/life_fact_extractor.py:69` → `PersonalFact`; invoked only by `post_response_intelligence`
- `apps/ai/chatgpt_cos/tasks.py:172–181` — previous runtime enqueued post-response intelligence
- `apps/ai/model_interface/tasks.py` — successor runtime does **not**; `git log -S` confirms it never did (`f98fd021`, 2026-07-09)
- `apps/ai/models.py:2001` `LearnedCommunicationPreference` — no writer anywhere in the codebase

**Settings and consent**
- `templates/users/preferences.html:945–1017` — the learned-context accordion and its claims
- `apps/ai/views.py:2469–2503` — CoS Settings save (blueprint + display name)
- `apps/ai/views.py:223–250` — the four-gate consent stack
- `apps/users/views.py:91–121` — onboarding steps; "AI Coaching" is step 5 of 7

**Provider**
- `apps/ai/services.py:811` — `/v1/chat/completions`, reached by `model_interface` via `_call_api_with_tools`
- `templates/core/privacy.html:173–180` — current claims; overstated in one place, silent on 30-day retention

**Sources for provider terms:**
[OpenAI — Data controls in the OpenAI platform](https://developers.openai.com/api/docs/guides/your-data) ·
[OpenAI Data Retention Policy 2026 (Meetily)](https://meetily.ai/llm-privacy/openai)

---

## 37. The final product test

> *Can a new user meet their Chief of Staff, teach it who they are at whatever depth they choose, understand and control what WLJ remembers, configure how it treats them, understand when an AI provider processes their information, and build a trusted relationship that becomes more useful over years?*

| Requirement | How this design satisfies it |
|---|---|
| Meet their Chief of Staff | Name + persona gallery in onboarding — the first delightful moment |
| Teach it at any depth | Conversational interview, user-controlled, resumable, never a form |
| Understand what's remembered | About Me knowledge map with per-fact provenance |
| Control it | Edit · delete · pin · pause · tombstoned forget · export |
| Configure how it treats them | Persona + orthogonal operational preferences, explicit precedence |
| Understand provider processing | "WLJ remembers, the provider processes" — layered, verified, honest |
| Becomes more useful over years | One authority, two acquisition paths, never "finished" |

**Constitutional check:** WLJ owns deterministic truth and preferences (I.1) · the model reasons and drives the interview (I.2) · WLJ emits facts, never verdicts about the person (I.4) · one authority per truth, replacing three (III.1) · provider stays behind the Model Interface seam (I.8) · truth exposed, not invented (IV.4) · **the architecture gets smaller** (IV.2).

**No Constitutional Review is required for this design.** It creates no reasoning engine, no second authority, and no provider dependency — it consolidates three broken half-systems into one that conforms.

---

## 38. Design freeze

### Final conceptual architecture

```
                    ONE CHIEF OF STAFF
   ┌──────────────┬──────────────────────┬─────────────────────┐
   │   PERSONA    │     OPERATIONAL      │       PERSONAL      │
   │              │     PREFERENCES      │      KNOWLEDGE      │
   │ how it feels │  how it works with   │  what it knows      │
   │ and speaks   │  me                  │  about me           │
   ├──────────────┼──────────────────────┼─────────────────────┤
   │ named        │ configured settings  │ facts + durable     │
   │ personas     │        +             │ context, statement- │
   │ over shared  │ Interaction Guidance │ primary, entity-    │
   │ attributes   │ (stated-only, v1)    │ referencing         │
   └──────────────┴──────────────────────┴─────────────────────┘
              ↓ all three compose; settings beat persona ↓
        AI Relationship projection  +  Personal Truth composer
                            ↓  ONE existing seam  ↓
              Standing Context → Executive Context Envelope
                            ↓
                   Model Interface (provider-agnostic)

   Separate and never merged:
     Canonical Domain Truth — via tools, never copied into PK
     Conversation State     — this turn only, never memory
```

**Two acquisition paths, one authority:** deliberate teaching (interview, "remember this") **persists**; ordinary conversation **proposes only** in v1.

### Final canonical authorities

| Truth | Authority | Status |
|---|---|---|
| Persona definitions | `CoachingStyle` registry, extended | KEEP + EVOLVE |
| Configured preferences | `UserPreferences` + Blueprint, projected via `ai_relationship` | KEEP + EVOLVE |
| Interaction Guidance | rebuilt under Operational Preferences | EVOLVE from `BehaviorDirective` |
| **Personal Knowledge** | **new canonical authority** — `PersonalFact` migrated in, then retired | **BUILD** |
| Interview coverage & boundaries | new deterministic coverage record | BUILD |
| Delivery to the model | `personal_truth` composer → Standing Context | **REUSE — do not fork** |
| Domain truth | existing domain authorities | UNCHANGED |
| Conversation state | `conversation_state.py` | UNCHANGED |

### Is M0 blocked?

**No. Nothing blocks M0.**

Every §34c item is either evidence-gated downstream (auto-commit graduation, invitation default, runtime retirement), or a wording/configuration choice the frozen architecture already accommodates in both directions (ZDR, custom personas, free-form field). The ZDR investigation is scheduled **before M2** and is explicitly not a prerequisite — the privacy model is honest and complete either way.

**No issue prevents freezing this design.**

M0 is a contract-writing milestone with no code, no migrations, and no provider changes — and everything it must settle is decided in §34a or explicitly scoped to it.

**Implementation is not authorized. Awaiting separate authorization.**
