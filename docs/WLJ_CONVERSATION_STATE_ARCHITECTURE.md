# WLJ Chief-of-Staff — Conversation State Management (Governing Architecture)

**Status:** Phase 1A review COMPLETE → **constitutionally compliant, no Constitutional Review required** → Phase 1B implemented → **Architectural refinement review COMPLETE (2026-07-20): Q1 — Conversation State is carried INSIDE the Executive Context Envelope, not an independent Truth Surface (framing corrected; architecture already correct); Q2 — lifecycle reframed EVENT-DRIVEN PRIMARY with turn/time as genuine last-resort fallbacks (turn backstop 4→12).** → **Deterministic-Writers governance COMPLETE (2026-07-20): §4a documents the ONE writer authority + the reasoning-based mechanisms that may NEVER write it, runtime-proven and enforced by `test_conversation_state_writer_contract.py`.** → **Active-Artifact Continuity COMPLETE (2026-07-20): §4b — an active image/video is now RE-PERCEIVED (not just referenced) on follow-ups, with a bytes cache for the durable-storage-pending window (prod "the image isn't available" defect).** → **Permitted-Data + Expansion-Test governance COMPLETE (2026-07-20): §5a/§5b — runtime-verified every field is deterministic (no runtime changes needed); schema allow-list contract + Engineering Guide §3f. Artifact separation of concerns (§4b.1) + generic-support coverage (§4b.2) documented.** **The capability is ARCHITECTURALLY FROZEN** — it evolves only when production experience reveals a genuine need and the Expansion Test (§5b) passes. AWAITING production validation.
**Date:** 2026-07-20
**Runtime scope:** Danny's production runtime is `use_model_interface=True` → `CoSGateway.respond` → `ModelInterfaceService` (proven). All design and tests target that runtime.

---

## 0. The capability, in one line

**Current Context** answers *"what page is the user on?"* **Conversation State** answers *"what are we
currently talking about, doing, or waiting on?"* These are different deterministic truths. WLJ owns
the deterministic conversation working-state; the conversational model reasons over it. WLJ does **not**
perform semantic reasoning and does **not** become a conversation conductor.

**Architectural position (refined 2026-07-20, Q1 review): Conversation State is NOT an independent
Truth Surface — it is deterministic conversational truth CARRIED INSIDE the Executive Context Envelope.**
It is a peer *field* to `current_context` within the one envelope (`ModelInterfaceService.build_standing_context`),
assembled by the same one path each turn. The four Truth Surfaces are the *tools* the model calls
(`get_entity` / `get_history` / `get_analysis` / `search_history`); **Conversation State is not one of them
— there is no `get_conversation_state` tool and the model never fetches it.** This preserves all four design
goals with the *simpler* architecture: one authority (`conversation_state.py`), one read (metadata — no
duplicated retrieval), one precedence list (the operating prompt — no competing chains), no parallel context
system. Current Context remains authoritative for page questions (Article II); Conversation State never
overrides it — it is a *sibling field* the model reads for follow-ups and pending resolutions.

---

## 1. Existing capability inventory (proven by code + runtime trace)

| Mechanism | Owns | Storage | Lifecycle | Prod-active (model_interface) | Sufficient? |
|---|---|---|---|---|---|
| `model_interface/confirmation.py` (Store #1) | Bound pending confirmations `{id,action,params,summary,status}` | per-**USER** cache `wlj:mi:confirm:{uid}`, TTL 300s, max 5 | single-use; consumed on resolve | **YES** (the only prod pending store) | Partial — per-user not per-conversation; **surfaced non-saliently** (proven at 97% of a 65k prompt); no active-subject notion |
| `current_context.attachments` | This-turn uploads | per-request only | one turn | YES | No — gone on a text-only follow-up |
| `current_context.conversation_artifacts` (`MultimodalArtifact.source_conversation_id`) | Passive list of earlier uploads | DB (durable link) + rebuilt per turn | durable | YES | Partial — a passive metadata stub; **no "active" designation**; no frames/preview for a silent video |
| `perceive_images_for_artifacts` | Re-delivers pixels/frames on `get_entity(artifacts)` | on-demand | model-initiated only | YES | Only if the model *chooses* to retrieve |
| `current_focus_store` (`wlj:cc:last_focus:{cid}`) | Last on-screen PAGE focus ref | cache, TTL 3600s | cross-turn, same-page-gated | YES | Page focus only — **chat uploads never enter it** |
| `AssistantConversation.metadata` JSON (line 549, "e.g. pending confirmations") | Free-form conversation bag | DB, durable, atomic with `conversation.save` | durable | Present but **unused by model_interface** | The correct durable, conversation-scoped home |
| `chatgpt_cos` `conversation_memory` + `conductor` (`metadata.last_answer` / `conductor_state`) | The richest active-subject model (`active_subject`, topic, fact, basis) | DB metadata | durable | **NO — chatgpt_cos runtime only** | Not on Danny's path; keyed on health `fact_key`, **no artifact concept** |
| Legacy stores #2–#6 (`pending_intent_*`, `pending_crud_*`+`PendingAction`, disambiguate, clarification, `metadata.pending_clarification`) | Various pending states | mixed cache/DB | 300s / none | **NO** (legacy Beth / chatgpt_cos) | Fragmented; not Danny's runtime |

**Net:** pending confirmations exist on prod (Store #1) but are per-user + buried non-saliently; artifact
continuity is passive-only; there is **no deterministic active-subject/active-artifact pointer** and **no
conversation-scoped working-state authority** on the production runtime. The rich active-subject model
exists but only in a non-production runtime and cannot represent an artifact.

## 2. Relationship to existing foundational capabilities

- **Current Context (Article II):** a *peer axis*, not a replacement. Current Context = the page's
  server-resolved truth (authoritative for "what am I looking at"). Conversation State = the interaction's
  working truth (authoritative for "what are we discussing / waiting on"). Conversation State **never
  overrides** Current Context for an explicit page question; it takes precedence only for follow-ups and
  short responses that belong to the ongoing interaction. Both are provided; the model reasons which the
  user means.
- **Standing Context / Executive Context Envelope:** Conversation State is a new *owned interface* inside
  `build_standing_context` (peer to `current_context`, `personal_truth`, `deterministic_understanding`),
  surfaced with a salient lead like `_focus_lead`/`_profile_lead`.
- **Personal Truth / Truth Surfaces:** unchanged. Conversation State references entities/artifacts by id;
  the model retrieves full content through the existing truth tools (`get_entity`).
- **Artifacts / Artifacts-as-Truth:** Conversation State points at `MultimodalArtifact` ids; retrieval +
  re-perception stay in the existing spine. It does not copy artifact bytes.
- **Rich Confirmation / deterministic actions / pending confirmations:** the existing `confirmation.py`
  bound-confirmation store stays the action authority (I.7). Conversation State **surfaces** open
  confirmations saliently (fixing the "yes" loss) — it does not fork the action path.
- **Conversation history:** history is the last-12 raw text turns; Conversation State is the compact
  *deterministic working-state* (refs, ids, turn counters) — not a transcript replay, not model prose.
- **Long-term memory:** out of scope. Conversation State is ephemeral working-state with expiry.

## 3. Deterministic vs. reasoning boundary

**WLJ (deterministic):** which confirmation/workflow is pending (id, summary, allowed responses); which
artifacts were introduced and remain active; the active subject *derived from concrete signals* (this
turn's attachment, or a `get_entity` the model just called); ids, timestamps, turn counters, source turn;
expiration; explicit completion/cancellation.

**Model (reasoning):** whether a follow-up ("for a leak?", "is that dangerous?") semantically refers to the
active subject; whether a short "yes" answers the pending confirmation; when the user has changed topic;
how to phrase the answer. WLJ supplies candidate referents + active-state facts; **the model decides.**
WLJ never classifies the language.

## 4. Authority & ownership

**ONE conversation-scoped deterministic authority:** `apps/ai/model_interface/conversation_state.py`,
persisted in `AssistantConversation.metadata["conversation_state"]` (durable, atomic with the turn, no
migration, correct grain). It **generalizes** — it does not fork — existing state: it reuses the
`confirmation.py` pending store (read-through) and `MultimodalArtifact` provenance; it adds only the
missing active-subject/active-artifact/last-answer pointers. No new per-domain or per-modality store.

## 4a. Deterministic Writers (governance — who may modify Conversation State)

**Conversation State is a closed, deterministic object. It is never an open-ended shared bag
that arbitrary systems modify.** There is ONE writer authority — `conversation_state.py` — and
it is invoked from exactly ONE runtime entry point (`ModelInterfaceService.generate`), from
**concrete deterministic signals only**. Runtime-proven (writer instrumentation + source scan):
the only callers of `record_turn`/`clear`/`_save` are within `apps/ai/model_interface/`, and no
other module writes `metadata["conversation_state"]`. Enforced by
`apps/ai/tests/test_conversation_state_writer_contract.py`.

### Allowed writers (deterministic events the implementation actually supports)

| Writer | Trigger (concrete signal) | Effect | Determinism |
|--------|---------------------------|--------|-------------|
| `ModelInterfaceService.generate` → `conversation_state.record_turn` | an **uploaded artifact** this turn (`attachments`, WLJ upload-ingest) | ACTIVATE/SUPERSEDE the active subject + active_artifacts | WLJ ingested the file; the model did not supply it |
| ″ | an **artifact/entity retrieval** — the model called `get_entity`; the subject is derived by WLJ (`_subject_from_entity_result`) from the tool **RESULT** (retrieved identity / artifact id) | ACTIVATE/SUPERSEDE (or UPDATE) | derived from a WLJ-produced result, not model prose |
| ″ | **no new signal** | PRESERVE (subject persists) / advance turn counter | pure bookkeeping |
| `confirmation.py` `create` / `consume` | a **pending confirmation** created by the deterministic action path, or resolved/declined/cancelled via `resolve_pending_action` (**deterministic action execution / workflow transition / explicit completion / explicit cancellation**) | pending appears / is single-use consumed (read-through into the lead) | WLJ safe action path (Art I.7) |
| `AssistantConversation.clear_messages()` (`metadata = {}`) | **conversation initialization / reset** | clears the whole working-state | deterministic reset |
| `conversation_state.clear()` | an explicit deterministic reset hook (available; unwired today) | clears the working-state | deterministic |

Every writer input is a **concrete runtime fact** — an uploaded artifact, a tool result, an
action/confirmation event, or a conversation reset. The model's contribution is only *which tool
it called*; WLJ extracts the state from the **result**, deterministically.

### What may NEVER write Conversation State

Conversation State is **never** created or mutated by any reasoning-based mechanism:

- OpenAI (or any provider) reasoning or its free-text answer
- transcript summarization / conversation summaries / `context_summary`
- semantic guesses, inferred topics, or heuristic/keyword classifiers
- reflection, AI-memory generation, or any learned/inferred store
- LLM interpretation of what the conversation is "about"

**The conversational model REASONS OVER Conversation State; it never writes it.** Proven at
runtime: a turn whose answer names a topic in prose ("my weight goal matters") produced **no**
active subject — only an upload or a `get_entity` result changes state. If a future feature needs
the model to influence Conversation State, it must do so by performing a **deterministic action**
(upload, retrieval, or a confirmed action) whose *result* WLJ records — never by writing the state
from model output. This keeps Conversation State exactly as trustworthy as Current Context.

## 4b. Active Artifact Re-Delivery (perceivability, not just reference)

Preserving the active artifact's *reference* is necessary but not sufficient: an active
**image or video** must stay **perceivable** across follow-ups — the model cannot answer "how
many ounces is it?" from a reference it cannot see. (Production defect 2026-07-20: the artifact
reference survived, but the model had only "image you uploaded" and answered "the image isn't
available.") The completion (deterministic, general — image/video, not image-special-cased):

- **Re-delivery:** on a turn with **no new upload**, the runtime reads `conversation_state
  .active_artifact_ids(conversation)` and re-delivers that artifact's perceivable pixels/frames
  (`perceive_images_for_artifacts`) into the turn's perception payload — so the active image/video
  is **re-perceived**, exactly as on the upload turn. Bounded to the ACTIVE SUBJECT artifact;
  ends the moment Conversation State supersedes or expires (§6/§8). (`cos_gateway/runtime.py`.)
- **Pending-window bytes:** image re-perception previously required durable object storage, which
  is written **asynchronously** — so an image uploaded *this* turn was not yet retrievable on the
  *next* turn. Fix: at ingest the upload bytes are cached short-term (`_cache_artifact_bytes`,
  TTL = Conversation State's), and `perceive_images_for_artifacts` falls back to that cache when
  `is_durably_stored` is still false. Video frames already live on the artifact record (no gap).
- **Documents** (PDF/receipt): their deterministically-extracted **text** is delivered via the
  existing `conversation_artifacts` surface + `get_entity(domain='artifacts')`; the active-artifact
  reference above keeps them addressable ("what does page 4 say?").

This is exposure/completion of the existing capability — it adds no new writer (re-delivery is a
READ of Conversation State) and no new store. `apps/ai/tests/test_conversation_state_artifact_continuity.py`.

### 4b.1 Architectural separation of concerns (Conversation State is NOT an artifact engine)

| Layer | Responsibility | Owns |
|-------|----------------|------|
| **Conversation State** | **WHICH** artifact is active (a reference + lifecycle) | `active_artifacts` / `active_subject.ref` |
| **Artifact Adapters** (`perceive_images_for_artifacts`, `attachments_from_ids`, bytes cache) | **HOW** that artifact becomes perceivable again (bytes/frames/text reconstruction) | per-kind perception |
| **Executive Context** (`build_standing_context`) | ASSEMBLES the active reference + the reconstructed perception into the turn | the envelope |
| **Model Perception** | REASONS over the reconstructed artifact | — |

Conversation State stores only the **identifier + lifecycle**; it never decodes bytes, renders pages,
extracts text, or samples frames — that is the adapters' job. **Conversation State never becomes an
artifact-processing engine.** Adding a new artifact type is an *adapter* change; Conversation State is
untouched.

### 4b.2 Generic artifact support (coverage — preserved from the 2026-07-20 analysis)

Conversation State provides **universal artifact references** (any `kind` can be the active subject).
Perception continuity is provided by the **adapters**, which today cover:

| Type | Continuity | Status |
|------|-----------|--------|
| image · screenshot · receipt-photo (`kind=image`) | visual re-delivery (bytes + cache) | ✅ adapter |
| video (`kind=video`) | frame re-delivery | ✅ adapter |
| PDF · Word · text · receipt-PDF (`kind=document`) | text surface (`extracted_text` via `conversation_artifacts` + `get_entity`) | ⚠️ text only |
| audio (`kind=audio`) | transcript via the text surface | ⚠️ text only |

Future adapters — **PDF page rendering, DOCX embedded content, OCR for scanned documents** — extend
*perception* for `document`/`audio` **without changing Conversation State itself** (its universal
reference already holds; only the per-kind adapter is added).

## 5. State model (minimal, durable, reference-based — never model prose)

```
AssistantConversation.metadata["conversation_state"] = {
  "turn": int,                       # monotonically increasing turn counter
  "updated_ts": iso,
  "active_subject": {                # what "it/that/this/the video" points at
     "kind": "artifact"|"entity", "ref": <id>, "label": str,
     "source_turn": int, "first_ts": iso } | null,
  "active_artifacts": [ {"artifact_id": id, "kind": str, "filename": str, "ts": iso}, ... ],
  "last_answer_turn": int,           # the turn a follow-up is responding to (ref, not prose)
}
# Pending confirmations/workflows are NOT copied here — they are read through from the
# confirmation authority (confirmation.list_open) so there is ONE pending-action source.
```
Facts and references only; no free-form conversation summary.

## 5a. Permitted Data (governance — what Conversation State MAY and may NEVER contain)

Conversation State is a **compact deterministic index into the current interaction** — nothing more.
**Runtime-verified 2026-07-20:** every stored field is a deterministic scalar / reference / timestamp;
no field violates this — no runtime changes were required.

**MAY contain (deterministic references + deterministic state ONLY):**
- active-subject / artifact / entity / workflow / confirmation **identifiers** (`ref`, `artifact_id`)
- deterministic **lifecycle state** (`turn`, `source_turn`, `last_answer_turn`, a `kind` label, an
  `artifact` flag, `schema_version`)
- **timestamps** (`updated_ts`, `first_ts`, `ts`) and **provenance** (`source_turn`)
- deterministic **references to durable truth** (an artifact id, an entity identity from a tool result)
- a `label` — a **deterministic display name only** (a filename, or the retrieved entity's `identity`
  from the tool RESULT, or a fixed fallback like "image you uploaded"). It is **never** model-authored
  and is length-bounded; it exists solely so the salient lead reads naturally.

**MUST NEVER contain:** conversation summaries · transcript summaries · AI-generated prose · semantic
interpretations · inferred intent · generated explanations · heuristic classifications · reflection
output · LLM-authored memory · model-generated free text · conversation analysis.

Conversation State is **NOT** another transcript, another memory system, or another reasoning engine.
The conversational model **reasons OVER** Conversation State; it **never writes it** (§4a). Enforced by
`apps/ai/tests/test_conversation_state_schema_contract.py` (allow-list schema; forbids free-text/summary
keys) and `test_conversation_state_writer_contract.py` (single writer authority).

## 5b. Expansion Test (governance — when Conversation State is allowed to grow)

Conversation State is a **system eliminator, not another system.** Before extending it, answer:

1. Does this **replace an existing deterministic system**?
2. Does it **eliminate duplicate logic**?
3. Does it **reduce architecture** (net fewer systems)?
4. Does it preserve the **deterministic / reasoning boundary** (deterministic in; model reasons over)?
5. Does it preserve the **writer contract** (one authority; concrete signals only)?

**If #1 and #2 are both NO, the proposal is presumed architectural scope creep and must not be added.**
Any proposal to place *generated text* inside Conversation State is scope creep unless it *demonstrably
replaces* an existing deterministic system. Durable records (`JournalConversation`, `*Session`,
`ConversationMemory`) and long-term memory are out of scope by definition — Conversation State may hold a
*reference* to them, never their contents.

## 6. Deterministic lifecycle — EVENT-DRIVEN PRIMARY (refined 2026-07-20, Q2 review)

State transitions are driven by **deterministic events** WLJ can actually observe. Turn/time
(§8) are **last-resort fallbacks**, never the primary clear. The semantic transitions WLJ
*cannot* observe ("never mind", an implicit topic change) are the **model's** job (Article I.2):
the model simply stops referring to the subject, and — absent a new event — the fallback bounds it.

| Verb | Deterministic event (WLJ-observable) | Effect |
|------|--------------------------------------|--------|
| **ACTIVATE** | an upload arrives; the model retrieves an entity/artifact (`get_entity`); a confirmation is created (`confirmation.create`) | subject/artifact/pending becomes active |
| **UPDATE** | the SAME subject is re-surfaced (re-retrieved) | `source_turn` resets → reinforced (backstop clock restarts) |
| **SUPERSEDE** | a NEW upload; a retrieval of a DIFFERENT subject | the new subject **replaces** the old (the primary way a subject changes) |
| **CLEAR (event)** | explicit reset (`clear()` / `clear_messages()`); a pending confirmation resolved/declined/cancelled | working-state / that pending is dropped (single-use `consume` for pendings) |
| **PRESERVE** | an ambiguous follow-up with no new subject signal | the subject **persists** unchanged |
| **CLEAR (fallback)** | *no event above fired* → §8 | inactivity TTL / generous turn backstop bound state the model silently abandoned |

Interruption / return-later is durable in metadata; §8 governs whether it is still active.

## 7. Precedence (as surfaced to the model; the model reasons, WLJ never overrides Article II)

1. Explicit current-turn instruction.
2. A **pending confirmation / workflow** awaiting resolution (a short yes/no/cancel resolves THAT).
3. The **active conversational subject / artifact** (a follow-up or "it/that" refers to THIS).
4. Prior conversation turns (history).
5. **Current Context** (the page) — authoritative for explicit page questions ("what am I looking at").
6. Other truth retrieval.
7. General reasoning.

This prevents *unrelated* page Current Context from displacing an active conversation, while **preserving
Article II**: an explicit page reference still answers from Current Context. WLJ presents both; the model
disambiguates.

## 8. Expiration & recovery — FALLBACKS ONLY (events in §6 are primary)

The clears below fire **only when no §6 event has already superseded or cleared the state**. They
exist because WLJ cannot deterministically detect *semantic* abandonment ("never mind", a silent new
task) — that is language (Article I.2). They are safety nets, not the primary lifecycle.

- **Inactivity (primary fallback):** the whole state expires after `TTL_SECONDS` (30 min) of inactivity.
- **Turn backstop (secondary fallback):** an unreinforced, never-superseded subject ages out after a
  **generous** `MAX_SUBJECT_TURNS` (12). Raised from 4 in the Q2 refinement so turn-count is a genuine
  last resort — not an eager primary clear that drops a subject the user is still discussing. A
  re-retrieval (UPDATE event) resets this clock.
- **Superseded/completed:** handled as EVENTS in §6 (not here) — a new subject replaces the old; a
  resolved confirmation is consumed.
- **Refresh/reconnect:** durable in the DB row → survives browser refresh and worker reconnect (same
  conversation). A *new* conversation (`get_or_create_active`) starts clean — expired state never
  contaminates a later conversation.
- **Explicit clear (event):** `clear()` / `clear_messages()` resets the state.

## 9. Multiple simultaneous workflows

Pending confirmations already support up to 5 concurrent bound transactions, each id-bound. When >1 is
open, the salient lead **lists them** and instructs the model to resolve the specific id — and, on an
ambiguous bare "yes", to **ask which one** rather than execute an arbitrary action. **Fail closed for
actions.**

## 10. Constitutional review — RESULT: COMPLIANT (no Review required)

- **Article I.1 (WLJ owns deterministic truth):** conversation working-state (which artifact, which pending
  action, which subject) is deterministic truth WLJ can own. ✅ Strengthens truth delivery.
- **Article I.2 (model owns reasoning):** WLJ provides candidate referents + facts; the model decides
  whether "for a leak?" refers to the video. No reasoning/conductor engine in WLJ. ✅
- **Article II (Current Context Authority):** *Considered carefully.* Conversation State is a **peer axis**,
  not a substitute. It does not use scraped DOM and does not override Current Context for page questions;
  the salient lead explicitly defers to Current Context for explicit page references (II.1/II.4 intact). It
  is additive, not an inversion. ✅
- **Article III.1 (single authority):** ONE conversation-scoped authority; reuses the existing confirmation
  and artifact authorities (read-through), no parallel pending store. ✅
- **Article IV (reuse/expose before invent):** reuses `AssistantConversation.metadata`, `confirmation.py`,
  `MultimodalArtifact`, the salience-lead pattern. ✅

Compliant framing (matches the mandate): *WLJ owns deterministic conversation state; the model reasons over
it; WLJ does not perform semantic reasoning or become a conductor.* **No Article is changed, weakened, or
inverted → no Constitutional Review; proceed to Phase 1B.**

---

## Implementation Status (Phase 1B)

See changelog `2026-07-20`. `apps/ai/model_interface/conversation_state.py` (authority) +
`ModelInterfaceService` integration (read in `build_standing_context`, write after `generate`, salient
`_conversation_state_lead`) + precedence guidance in the constitution prompt. Tests:
`apps/ai/tests/test_conversation_state.py`. **AWAITING production validation.**
