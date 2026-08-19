# WLJ Personalization & Personal Knowledge — M0 Contracts

**Status:** ✅ **M0 COMPLETE — CONTRACTS FROZEN.** No feature implementation. No migrations. No provider configuration changed.
**Date:** 2026-08-18
**Governing product design:** `docs/WLJ_CHIEF_OF_STAFF_PERSONALIZATION_AND_PERSONAL_KNOWLEDGE.md` (APPROVED / FROZEN, R2)
**Constitution:** `@WLJ_SYSTEM_PROMPTS/00_WLJ_CHIEF_OF_STAFF_STARTUP/02_WLJ_CONSTITUTION.md`

> **What this document is.** The frozen target-state design says *what we are building and why*. This document says *what every future milestone must mean by each term*, so M1–M7 cannot independently invent semantics. Where the two ever disagree, the target-state design governs the product decision and this document governs the contract.
>
> **What this document is not.** It is not a schema, not an implementation plan, and not a migration. Field names, table structure, ranking weights, copy and pacing remain scoped to their milestones (target-state §34b).

**Reading order for any future session:** target-state design → this document → the milestone.

---

## 0. Contract index

| # | Contract | Freezes |
|---|---|---|
| 1 | Persona | identity, voice attributes, composition, precedence, delivery |
| 2 | Operational Preferences | the canonical vocabulary and its owners |
| 3 | Interaction Guidance | the boundary, the writer, the v1 gate |
| 4 | Personal Knowledge | the canonical record semantics |
| 5 | Domain Truth boundary | reference-vs-copy rules |
| 6 | Retrieval | standing tier + on-demand tier |
| 7 | Learning | deliberate vs candidate |
| 8 | Interview coverage | what WLJ may and may not own |
| 9 | User control | ten verbs, precisely |
| 10 | Sensitivity & third-party | policy, not taxonomy |
| 11 | Presentation truth | counts, never judgments |
| 12 | Progressive relationship-building | signals, boundaries, default |
| 13 | Privacy & provider | provider-agnostic separation |
| 14 | Legacy adoption | how M3 treats each legacy store |
| 15 | Cost & observability | which activities may call a provider |
| 16 | Contract enforcement | the regression tests M1–M7 must add |

---

## 1. Persona contract

**Definition.** Persona = *how my Chief of Staff feels and speaks.* It is a voice, never a behaviour policy and never a source of truth.

### 1.1 Canonical identity

- Every persona has a stable **persona key** (slug). The key is immutable once any user has selected it; a persona is deactivated, never deleted or re-keyed.
- A persona carries a **user-facing name, description and icon** for the gallery.
- The persona registry is the **single** persona authority. Two persona systems exist today (`CoachingStyle` rows; `apps/core/ai_persona/*` templates) — M1 consolidates definition into one registry (target-state §21–27).

### 1.2 Voice attributes (reusable, internal)

A persona is composed from reusable **voice attributes** — register, warmth, directness, humor, formality, verbosity bias, signature expressions, regionalisms — so that N personas do not require N hand-written prompt essays and a new persona is a data change, not a deploy.

**Voice attributes are internal.** They exist for maintainability and are never presented to the customer as a bank of sliders (target-state §4, settled).

### 1.3 Instruction composition

- The registry composes a **persona instruction block** from the attributes.
- The block is **voice only.** It may not contain truth claims, behaviour policy that duplicates an Operational Preference, or any instruction that would override a deterministic rule.
- Composition is deterministic and cacheable.

### 1.4 Operational defaults and the precedence invariant

A persona may declare **suggested defaults** for Operational Preferences (Contract 2).

**LOCKED INVARIANT:**

```
explicit user setting  >  persona default  >  system default
```

- A persona default applies only where the user has expressed no explicit setting.
- Selecting a persona **never rewrites** an explicit user setting.
- Every resolved preference value carries a **provenance tag** — `user` / `persona` / `default` — extending the existing `_sources` pattern in `apps/ai/cos_services/ai_relationship.py`.
- Provenance is user-visible so the UI can explain a conflict honestly ("Texas Rancher usually asks a lot — you've set this to Low, which wins").

### 1.5 Extension / admin model

Personas remain **admin-editable without a deploy** (today's genuine product value). Adding a persona is: a key, gallery copy, voice attributes, optional operational defaults.

### 1.6 Delivery

- Persona reaches the model **only** through the `ai_relationship` projection into Standing Context (target-state §17).
- The projection MUST carry the composed instruction block, not merely the persona key. *(Today it carries the key alone — the live defect M1 fixes.)*
- Delivery is **provider-agnostic**: the block is data inside the Executive Context Envelope, passed through the Model Interface seam. No persona artifact may reference a provider, an endpoint, or a model name (Constitution I.8).

### 1.7 Persona invariant for the interview

The interview is conducted in persona voice. **The knowledge gathered is persona-invariant** — same coverage, same extracted facts, same storage; only wording differs. This is a testable contract (Contract 16).

---

## 2. Operational Preferences contract

**Definition.** Operational Preferences = *how my Chief of Staff works with me.* Deterministic, user-configurable, explicitly chosen.

### 2.1 Canonical vocabulary

Every preference below has exactly one canonical meaning across the product.

| Preference | Semantics | Current authority | M0 disposition |
|---|---|---|---|
| **Response depth** | How much detail a routine answer carries | `UserPreferences.cos_response_style` | **CANONICAL — keep** |
| **Accountability** | How firmly the CoS holds the user to stated intent | `PersonalOperatingBlueprint.accountability_style` | **CANONICAL — keep**; surfaced in the unified settings home (M1) |
| **Proactivity** | Whether the CoS raises things unprompted | *(no single field today)* | **DEFINE at M1** from existing controls; do not invent a new engine |
| **Question / check-in frequency** | How often the CoS asks vs states | `PersonalOperatingBlueprint.question_frequency` | **CANONICAL — keep** |
| **Progressive "get to know me" invitations** | Frequency of invitations to share more | *(new)* | **NEW at M4** — Contract 12 |
| **Follow-through** | Whether the CoS re-raises commitments it recorded | `ConversationFollowUp` behaviour | **CANONICAL — keep**, exposed as a preference |
| **Event reflections** | Post-event reflection prompts | `PersonalOperatingBlueprint.event_reflections_enabled` | **CANONICAL — keep**; must reach the runtime (M1) |
| **Relationship suggestions** | Suggestions about people | `PersonalOperatingBlueprint.relationship_suggestions_enabled` | **CANONICAL — keep**; must reach the runtime (M1) |
| **Action confirmations** | Whether writes require confirmation | `UserPreferences.assistant_confirm_actions` | **CANONICAL — keep**; expose in UI (M1) |
| **Sensitivity / boundaries** | Topics to treat gently or avoid raising | `PersonalOperatingBlueprint.sensitivity_tags` | **CANONICAL — keep**; must reach the runtime (M1) |
| **Learning enablement** | Whether WLJ may learn at all | `UserPreferences.preference_learning_enabled` | **CANONICAL — keep**; expose in UI (M1) |
| **Assistant display name** | What the CoS is called | `UserPreferences.cos_display_name` | **CANONICAL — keep** |
| **Persona selection** | Which persona | `UserPreferences.ai_coaching_style` | **CANONICAL — keep**; semantics renamed to *persona* at M1 |

### 2.2 Fields that do NOT become canonical

- `personality_overlay` — redundant with Persona. **Retire (M7).** No milestone may build on it.
- `personal_assistant_enabled` — the CoS is the product. **Retire (M7).**
- `default_relationship` — folded into persona/relationship selection at M1.

### 2.3 Consent is not a preference

`ai_enabled` + `ai_data_consent` (+ today's `personal_assistant_consent`) are **governance gates**, not operational preferences. They consolidate at M1 into: **AI enabled** · **AI data-processing consent** · **Learning enabled**. Consolidation must be conservative — a user consenting under the old four-gate model is never silently upgraded to broader consent.

### 2.4 Learning Mode is distinct

`PersonalOperatingBlueprint.cos_learning_mode_active` (action suppression, enforced at `apps/ai/intent_service.py:1418`) is **not** preference learning and **not** Personal Knowledge learning. The three must never be conflated in code, UI, or copy.

### 2.5 Delivery

All Operational Preferences reach the model through the **same** `ai_relationship` projection as Persona. No preference gets a private delivery path.

---

## 3. Interaction Guidance contract

**Definition.** Interaction Guidance = *durable, user-stated behavioural guidance that does not already map to an explicit configured preference.*

### 3.1 The boundary test (frozen)

> **Does this describe the user's life, or instruct the Chief of Staff's behaviour?**

| Statement | Classification |
|---|---|
| "Heather is my wife" | describes → **Personal Knowledge** |
| "I prefer direct answers" | instructs, **and a setting exists** → **propose a Configured Preference change** |
| "When I'm overwhelmed, don't give me five choices" | instructs, **conditional, no setting exists** → **Interaction Guidance** |

### 3.2 The suppression rule (this is what keeps the store small)

**If an explicit configured preference already represents the request, the CoS proposes changing that setting. It MUST NOT create Interaction Guidance.**

Consequence: Interaction Guidance can never become a shadow settings system that silently overrides explicit user choices. Only conditional, situational or idiosyncratic guidance with **no settable equivalent** may persist.

### 3.3 v1 gate — stated source only

- Only guidance the user **stated in words** may persist.
- **Model-derived behavioural interpretation is never persisted as truth.** Today's `BehaviorDirective` auto-creates `observed` (0.55) and `derived` (0.50) rows; these sources are **not carried forward**.
- Reflection (`apps/ai/reflection/`) may **propose**; it never commits.

### 3.4 Forbidden fields (WLJ must not author interpretation or prose)

Two fields on today's `BehaviorDirective` are **forbidden** in the rebuilt authority:

- **`meaning`** ("why it matters") — WLJ storing an interpretation. Constitution I.4 gives interpretation to the model.
- **`explain()`** — WLJ composing prose. WLJ exposes facts; the model explains.

Any milestone reintroducing either requires a Constitutional Review.

### 3.5 Ownership, lifecycle, control, delivery

- **Owner:** the Operational Preferences dimension, as its *learned tier*. Not Personal Knowledge. Not Persona.
- **Writer:** one deterministic writer, reached only through the explicit-statement path (deliberate teaching or a user correction the user confirmed). No background writer.
- **Lifecycle:** active → superseded (by a newer stated guidance) → removed. No confidence decay, no reinforcement counters in v1.
- **Control:** visible, editable, deletable in the same surface and with the same provenance display as Personal Knowledge. Nothing about how the CoS treats the user is hidden from the user.
- **Delivery:** through the `ai_relationship` projection, alongside configured preferences. **Configured settings win on any conflict** (Contract 1.4).

---

## 4. Personal Knowledge contract

**Definition.** Personal Knowledge (PK) = *durable facts and context the Chief of Staff knows about the user's life.*

**Design principle (frozen):** the natural-language **statement is the payload**; structure exists **only for retrieval and user control**, never for interpretation. WLJ stores, indexes, retrieves and lets the user control. WLJ never computes what a PK statement means.

### 4.1 Required record semantics

| Element | Contract |
|---|---|
| **Statement** | The fact/context in natural language, in the user's framing. **Encrypted at rest** (no plaintext regression against today's encrypted blob). It is factual/contextual payload — **never a WLJ-authored interpretation, verdict, or summary.** |
| **Topic** | The knowledge area, used for retrieval and the Knowledge Map. **Extensible without a deploy** — must support emergent topics (Contract 8.4). Not a hardcoded enum. |
| **Canonical entity reference** | Optional reference to the canonical entity the fact is about (Contract 5). Nullable. |
| **Subject label** | Optional free-text subject when no canonical entity exists. **Never a substitute identity record** — it does not become a person. |
| **Attributes** | Sparse, structured, **only where unambiguous** (relation, year, name). Absent by default. A fact needing no attributes stores none. |
| **Provenance** | How it was acquired: `interview` · `explicit` · `about_me_entry` · `conversation_candidate_accepted` · `imported` · `legacy_extraction`. |
| **Source conversation / interview** | Where applicable — required to make "forget everything from that conversation" possible. |
| **Sensitivity** | `normal` · `sensitive`. Governs **retrieval tier eligibility**, not just storage (Contract 6, 10). |
| **Review / trust state** | `unreviewed` · `reviewed` · `user_authored`. Legacy imports enter `unreviewed` and are **standing-context-ineligible until reviewed** (Contract 14). |
| **Correction / supersession lineage** | Correction **supersedes**; it never destroys history. Old record marked superseded, new record active, lineage retained and user-visible. *(Today's `is_active` boolean destroys it — explicitly rejected.)* |
| **Deletion semantics** | Contract 9. Deletion removes the statement content. **No recoverable representation of deleted content is retained.** |
| **Pinning / standing eligibility** | Explicit user pin forces standing-tier inclusion, subject to the hard cap and the sensitivity exclusion. |
| **Ownership / Space** | User-owned, carrying the ownership boundary in the shape the ratified PDP expects (`docs/WLJ_SECURITY_AUTHORIZATION_FRAMEWORK.md`) so no re-scoping migration is later required. |
| **Audit** | Every create / correct / delete / accept is audited through the existing deterministic action-audit path. |
| **Retrieval** | Deterministic by topic / subject / entity (Contract 6). |
| **Timestamps** | Created, updated, and — where the fact is time-anchored — an as-of the user supplied. WLJ never infers a precision the user did not give (`timestamp_precision` principle). |
| **User control** | Every field above is inspectable; statement, topic, sensitivity and pin are user-editable; the record is deletable (Contract 9). |

### 4.2 What PK is NOT

- Not a copy of domain truth (Contract 5).
- Not conversation state.
- Not a judgment, score, verdict, or ranking of the person.
- Not a place for WLJ-authored inference about the user.

### 4.3 `PersonalFact` is not the future authority

Frozen decision (target-state §9). `PersonalFact` is a **migration source** only. No milestone may extend it.

---

## 5. Domain Truth boundary contract

### 5.1 The locked rule

> **If a canonical WLJ domain owns the truth, Personal Knowledge REFERENCES that authority rather than copying its value.**

PK may record *that a relationship exists* and *durable context about it*; it may never cache a value a domain computes.

### 5.2 Decision procedure (deterministic)

1. **Does a canonical WLJ domain own this truth?** → the domain owns it; PK references it, or stores nothing.
2. **Is it a durable fact/context about the user's life that no domain owns?** → PK.
3. **Does it instruct CoS behaviour?** → Contract 3.
4. **Is it only about this conversation?** → Conversation State.
5. **Unsure?** → do not store in PK. Record the ambiguity for the milestone; never create a shadow authority.

### 5.3 Worked classifications

| Example | Home | Note |
|---|---|---|
| "Heather is my wife" | **Canonical Person + relationship** (referenced by PK) | The identity/edge is domain truth |
| "Heather tends to be more laid-back than me" | **PK** | Qualitative context no domain owns |
| "We've been married since 1997" | **PK attribute** on the referenced person, or the relationship domain if it owns marriage dates | Resolve at M2 against the domain's actual ownership |
| "My weight goal is 180" | **Goals domain** | PK never copies the number |
| "I've lost 40 lbs and I'm proud of it" | **PK** (the durable meaning) + Health domain (the numbers) | Never duplicate the measurement |
| "I have three tasks due Friday" | **Tasks/Calendar** | Never PK — it is not durable |
| "I read the Bible most mornings" | **PK** (a routine); Faith domain owns readings | PK never stores reading history |
| "Brian is my boss" | **Canonical Person + relationship**, referenced by PK | |
| "I've been at my company 12 years" | **PK** | No domain owns career tenure today |
| "I enjoy motorcycles" | **PK** (interest) | |
| "I've always wanted to visit Alaska" | **PK** (aspiration) — *not* a Goal unless the user creates one | Aspiration ≠ tracked goal |
| "I prefer short answers" | **Configured Preference** (Contract 3.2) | |
| "When I'm overwhelmed, give me one recommendation" | **Interaction Guidance** | |

**Aspiration vs Goal is a boundary M4 must respect:** the CoS may *offer* to create a Goal; it must never silently promote a wish into a tracked domain record.

### 5.4 Documented dependency — canonical Person

Repository evidence shows **four** `Person` models: `apps/people/models.py:43`, `apps/relationships/models.py:36`, `apps/legacy/models.py:90`, `apps/core/ai_relationships/models.py:32`.

This is **not** ambiguity to resolve here. `docs/WLJ_PERSON_CONSOLIDATION_AND_RECOGNITION.md` is **APPROVED** and already settles it: `apps.people.Person` is *"the canonical identity record… a foundational Layer-1 Core truth domain"*, with **Phase 0b implemented and verified; consumer migration (0c+) not started.**

**Contract:**
- PK's canonical entity reference targets **`apps.people.Person`**.
- PK **must not** select a different Person table, and **must not** create its own person record under any circumstance.
- Where a consumer is still un-migrated, resolution goes through the **Person Consolidation program**, not through a PK workaround.
- **M2 dependency (recorded, not invented):** PK entity references require whatever level of Person consolidation exists at M2. If consolidation has not progressed, M2 ships PK with entity references **nullable and unused**, relying on `subject_label`, and adopts references when consolidation permits. PK never forces the consolidation program's hand and never forks it.

---

## 6. Knowledge retrieval contract

Two tiers. Same composer. This is the certified `personal_truth` / `get_user_truth` pattern reused, not a new mechanism (target-state §17–18).

### 6.1 Standing tier — always on

**Selection is deterministic policy, never relevance-to-question.** Ranking by relevance to the user's message would be reasoning, and belongs to the model.

Selection principles (weights deliberately not tuned here — M2):

1. **Explicit pins first.**
2. **Identity and relationship anchors** — household, immediate family, work — the facts a person who knows you would never need to look up.
3. **Provenance and review eligibility** — `unreviewed` legacy facts are **excluded** (Contract 14).
4. **Sensitivity exclusion — absolute.** A `sensitive` fact is **never** in the standing tier, at any weight, for any user, ever.
5. **Deterministic hard cap** on both fact count and serialized size. The cap is enforced in code, not by convention; overflow is reachable only through the retrieval tier.
6. **Stable-prefix placement.** The standing block must sit in the prompt's stable prefix region so it remains prompt-cacheable. Interleaving it with per-turn content breaks cache hits and costs more than the block saves (Contract 15).

### 6.2 Retrieval tier — on demand

- A truth tool retrieving PK by **topic / subject / canonical entity**.
- **The model decides when it needs more knowledge. WLJ deterministically decides what it is authorized and appropriate to return** — applying sensitivity, review state, ownership and caps.
- Returns facts. Never a summary, never a verdict, never a ranking of the person.

### 6.3 No vector retrieval

**Embedding/semantic retrieval is NOT introduced.** Topic + subject + entity filtering is deterministic, debuggable and sufficient at personal-knowledge scale. Adding a vector store requires **production evidence that deterministic filtering fails** — and an explicit product decision.

---

## 7. Learning contract

### 7.1 Deliberate learning — persists

**Paths:** Getting to Know You · explicit "remember this" · direct About Me entry.

All three carry **clear user intent to teach**.

- **Validation:** the statement is well-formed, non-empty, attributable to the user, and not a domain-truth duplicate (Contract 5).
- **Persistence:** committed as active PK through the deterministic action path — validate → (confirm where required) → execute → audit.
- **Provenance:** `interview` / `explicit` / `about_me_entry`.
- **Review state:** `user_authored` or `reviewed` — deliberate teaching is not `unreviewed`.
- **Sensitivity:** classified on commit; first-party sensitive facts may be stored on explicit intent and are marked sensitive. Sensitive **third-party** facts follow Contract 10.

### 7.2 Ordinary conversational discovery — candidate only (v1)

**Frozen: no silent commits.** *Trust before magic.*

A candidate:

- **is NOT Personal Knowledge**;
- **is NEVER delivered to the CoS as truth**;
- **cannot influence any future answer until accepted**;
- **is quarantined from standing context and from the retrieval tier**;
- is surfaced only through **passive review** or a **tightly bounded contextual invitation** (Contract 12 frequency preference governs the latter);
- **expires** unreviewed, per a policy set at M6.

### 7.3 The candidate → PK contract

| | Candidate | Accepted PK |
|---|---|---|
| Visible to the model | ❌ never | ✅ per Contract 6 |
| Influences answers | ❌ never | ✅ |
| Standing tier | ❌ never | ✅ if eligible |
| User action required | **yes — explicit acceptance** | — |
| Provenance on acceptance | — | `conversation_candidate_accepted` |
| Sensitive third-party | ❌ never generated (Contract 10) | only by deliberate teaching |
| Expiry | yes | no |

**Acceptance is the only transition.** There is no automatic promotion path in v1, and no milestone may add one without the graduation decision below.

### 7.4 Additional v1 requirements

- **Learn only from the user's own statements.** The assistant's response must not be fed to extraction as source material — that is a fabrication vector where the model's own guess becomes a stored fact. *(Today's extractor does this; it is not carried forward.)*
- Extraction runs **off the request path**, enqueued from the certified runtime via `safe_enqueue`, fire-and-forget.
- **Batched, not per-turn** (Contract 15).

### 7.5 Graduation is NOT decided here

Auto-commit remains **evidence-gated** and requires an explicit product decision informed by M6 data: extraction precision, sensitivity-classifier accuracy, deduplication behaviour, and observed accept/discard rates.

---

## 8. Interview coverage and resumability contract

### 8.1 WLJ MAY own (deterministic)

- Areas discussed, and the count of facts stored from each
- Declined topics, with the date declined
- Parked topics
- User-selected depth and boundaries
- Active / suspended interview state
- A deterministic **resume pointer**

### 8.2 WLJ MUST NOT

- Score the person
- Score topic completeness
- Prescribe a fixed next topic
- Determine what is conversationally interesting
- Mark the person or the interview "complete"
- Order, weight, or prioritize topics
- Turn coverage into a questionnaire

**The model owns what is worth asking next.** WLJ hands it an **unordered inventory** of facts, and the model reasons.

### 8.3 Boundary enforcement is deterministic

**Declined topics are never offered.** This is enforced by WLJ, not by model judgment — the model cannot reason its way past a boundary the user set.

### 8.4 Emergent topics

A committed fact whose subject fits no existing topic is stored with an **emergent topic label** proposed at commit time.

- Emergent labels are **first-class for retrieval immediately** — findable, editable, deletable from day one.
- They surface in an operator review so the topic vocabulary can grow deliberately.
- **No deployment may be required to accommodate a meaningful aspect of a human life.**

### 8.5 State record shape

One deterministic record per user holding §8.1 only. **Not a transcript** — the conversation lives in the normal conversation store. It must never acquire a `next_topic`, a completion percentage, or an ordering.

---

## 9. User-control semantics contract

| Verb | Trigger | Deterministic behaviour |
|---|---|---|
| **Remember this** | explicit request | Commit as active PK, `provenance=explicit`, `review_state=user_authored`. Never auto-expires. |
| **Don't remember this** | pre-emptive, in-turn ("off the record") | Mark the turn **no-learn**. Nothing from it becomes a candidate. Existing PK unaffected. |
| **Forget what I just said** | retroactive, current turn | Delete PK committed from that turn; discard candidates from that turn. |
| **Forget learned knowledge about X** | scoped | Delete matching PK for subject/topic X. Offer to record a **visible user-set boundary** (§9.2). |
| **Correct this** | correction | **Supersede** — old record superseded, new active, lineage retained and visible. Never destructive. |
| **Delete this** | single record | Remove the statement content. Lineage entries referencing it are also purged. |
| **Clear learned Personal Knowledge** | global | Remove all PK. Requires explicit confirmation naming what will be removed. |
| **Pause learning** | preference | No new PK or candidates from any path. Existing PK still retrieved. Distinct from deleting. |
| **Review legacy knowledge** | M3 | Keep · Correct · Remove per fact, resumable, optional (Contract 14). |
| **Review natural-learning candidates** | M6 | Keep · Discard per candidate, passive, optional (Contract 7). |

### 9.1 Deletion must be believable

**No recoverable representation of deleted content may be retained** — no content hash, no fingerprint, no derivative. A hash of a short personal statement is dictionary-recoverable and would mean retaining deleted content while claiming deletion.

### 9.2 How "forgotten stays forgotten" is guaranteed in v1

The **conservative learning gate (Contract 7.2)** closes the class structurally: because ordinary conversation commits nothing without explicit acceptance, re-extracted knowledge can only reappear as a **candidate**, which the user declines. There is no silent relearning path to defend against.

Where a user wants a standing boundary, WLJ records a **visible, user-authored, user-deletable "don't remember" entry** at subject/topic granularity. It contains **no deleted content** — it is a boundary the user set and can see, categorically different from a hidden artifact of a deleted sentence.

**If auto-commit is ever enabled**, any finer-grained suppression must be per-user salted, non-reversible, **visible to the user as a deletable entry**, and disclosed. Never a bare content hash. Never invisible.

### 9.3 PK deletion ≠ domain record deletion

**Deleting Personal Knowledge never deletes a canonical domain record**, and vice versa.

- "Forget that Heather is my wife" removes PK context; it does **not** delete the canonical Person or the relationship record.
- Deleting a Goal does **not** delete PK context about the user's ambitions.
- Any control that could be misread as deleting domain data must state plainly what it removes.

---

## 10. Sensitivity and third-party knowledge contract

### 10.1 Not a legal taxonomy

The PK authority **must not contain a comprehensive classification scheme for protected information.** That would be a reasoning engine wearing a compliance costume — unmaintainable, jurisdiction-bound, wrong at the edges.

Instead: a **bounded, enumerated, versioned policy list**, changeable as a policy decision.

### 10.2 Sensitive categories (v1 policy list)

health/medical conditions · sexual orientation or sex life · financial accounts or detailed financial information · criminal history · credentials or secrets · precise private location · immigration status · religious belief *(first-party, where volunteered outside an enabled faith context)* · similarly sensitive protected or private information.

**Versioned.** Changing the list is a recorded policy decision, not a code refactor.

### 10.3 Third-party knowledge

**Ordinary relationship context MAY be stored** as part of the user's own life: *"Heather is my wife" · "Haley is my daughter" · "Parker is married to Haley" · "Mike and Jarah are close friends" · "My brother and I aren't very close" · "Brian is my boss."* Prohibiting this would make Personal Knowledge impossible.

**Sensitive information about another person:**

| | Ordinary third-party context | Sensitive third-party information |
|---|---|---|
| Deliberate teaching | ✅ stored | ✅ **where policy permits**, marked sensitive |
| Natural-learning candidate | candidate per Contract 7 | ❌ **never generated** — discarded, not quarantined |
| Standing context | eligible | ❌ **never** — retrieval tier only, on-subject |

**Being mentioned in passing is never sufficient** for sensitive third-party information to become routine standing-context material.

### 10.4 No hidden dossiers

WLJ does not accumulate profiles of people who are not its users. Third-party PK exists **only** as context for the user's own relationships, is owned by that user, appears in that user's export and deletion, and is visible to them in About Me.

### 10.5 First-party sensitivity and explicit intent

- **Uncertainty defaults safely** — anything the classifier is unsure about is treated as sensitive for candidate purposes, failing toward *not learning*.
- **The user's explicit teaching is authoritative over the classifier.** If a user chooses to teach a sensitive fact about themselves, WLJ stores it, marks it sensitive, and keeps it out of unrelated conversations.
- Sensitivity governs **retrieval**, not merely storage — the difference between "we hold it" and "it is in the context of every conversation about lunch."
- **The blast radius of a misclassification is bounded by Contract 7.2:** in v1, nothing from ordinary conversation commits without acceptance, so an error costs at most a discarded candidate — never a stored surprise.

---

## 11. Presentation truth contract (Knowledge Map / About Me)

**The Knowledge Map reports deterministic stored knowledge only. It never evaluates how complete a person's life information is.**

**Required form:**

```
Family & Important People — 14 things I know
Work & Career — 8 things I know
Goals & Dreams — nothing yet · Tell me more →
```

**Forbidden:** Rich / Some / Not yet as quality labels · percentages · completeness scores · progress bars · sufficiency judgments · deficiency language ("incomplete", "missing", "needs attention") · any colour encoding sufficiency · any comparison between topics or users.

**An empty topic is a neutral fact about WLJ's storage, never a gap in the person.**

### 11.1 The rule applies to the CoS's language

Invitations to share more must **never** imply the user is deficient or owes WLJ information.

- ✅ *"I don't know much about your brother"* — a fact about WLJ's storage.
- ❌ *"Your profile is incomplete"* / *"You still haven't told me about…"* — a judgment about the person.

---

## 12. Progressive relationship-building contract

**Preference:** *Help my Chief of Staff get to know me over time* — **Never · Occasionally · Naturally**.

**Initial default: Occasionally** (trust calibration — target-state §12a).

### 12.1 WLJ deterministically enforces (at EVERY setting, including Naturally)

- **Rate limits** — enforced by WLJ, never by model judgment. The model cannot talk itself into asking again.
- **Declined-topic suppression** — absolute; a declined topic is never the subject of an invitation.
- **Parked-topic handling** — "not now" parks it; the same invitation is not repeated.
- **All other explicit user boundaries**, including sensitivity settings.
- **Never** — means never. No invitations, deterministically.

### 12.2 Deterministic signals WLJ MAY expose

- **No stored PK for a topic** — an inventory reading.
- **Repeated reference to a known entity with little or no attached PK** — a **count**, not an inference.

### 12.3 The invariant

> **Absence of knowledge is not a judgment and not an obligation to ask.**

WLJ exposes the signal; **the model decides whether an invitation is conversationally appropriate**, and may decline to ask at all.

---

## 13. Privacy and provider-processing contract

### 13.1 The invariant

> **WLJ remembers. The configured AI provider processes.**

Provider-agnostic and true regardless of provider, endpoint, or retention configuration.

### 13.2 Separated concerns (never conflated in code, UI, or copy)

| Concern | Meaning |
|---|---|
| **WLJ persistent storage** | Personal Knowledge, preferences, guidance — in the user's WLJ account. The canonical memory. |
| **Provider processing** | Context sent through the Model Interface so the model can reason and reply. Transient. |
| **Provider retention** | How long the provider holds what it processed. A provider configuration fact. |
| **Model training / data sharing** | Whether provider data trains models. A provider account policy fact. |
| **User consent** | Permission for AI processing at all. |
| **PK learning controls** | What WLJ may remember, by which path — independent of all provider facts. |

### 13.3 No provider specifics in the authority

**The Personal Knowledge authority must contain no OpenAI-specific behaviour** — no endpoint, model name, retention assumption, or ZDR conditional. Provider facts live in the privacy/disclosure layer, behind the Model Interface seam (Constitution I.8).

### 13.4 Facts to verify before M2 user-facing wording is released

Release gate on M2. Verify against **current official OpenAI documentation AND WLJ's actual organisation/account configuration**:

1. ZDR **eligibility** for WLJ's account
2. ZDR **currently enabled?**
3. **Approval requirements** and lead time
4. Are **all endpoints/capabilities WLJ uses** ZDR-compatible? *(WLJ uses `/v1/chat/completions` — `apps/ai/services.py:811`)*
5. **Tool/function-call implications** across a multi-tool CoS turn
6. **Endpoint-specific exceptions**
7. **Abuse-monitoring implications** — what protection is surrendered
8. **Operational/debugging implications** — diagnostic capability lost when provider-side logs do not exist
9. Would enabling ZDR **affect current WLJ functionality**?
10. **Exact claims supportable WITH ZDR, and exact claims supportable WITHOUT it**

**Both wordings are drafted; the honest one ships.** Neither is weak — "not used for training; retained up to 30 days for abuse monitoring" is clear and defensible. **Overclaiming is the only failure mode.**

### 13.5 ZDR is optional infrastructure

**ZDR is never an architectural dependency.** No contract in this document assumes it. Personalization and Personal Knowledge are correct, transparent and shippable with or without it. **Provider configuration is not changed by M0.**

### 13.6 Baseline correction owed

`templates/core/privacy.html:177` currently states *"We do not allow OpenAI to use your data for training their models"* — phrased as an active control WLJ exerts rather than the API default — and does not disclose the abuse-monitoring retention window. M2 corrects both against verified facts.

---

## 14. Legacy-data adoption contract

### 14.1 Per-store treatment at M3

| Store | M3 treatment |
|---|---|
| `UserPreferences._ai_personal_context` (the 203-line blob) | Parsed into PK as `provenance=legacy_extraction`, `review_state=unreviewed`. **Source field NOT deleted.** |
| `UserPreferences.ai_profile` | Extracted into PK as `provenance=legacy_extraction` **and** retained as an interview seed. **Field NOT deleted.** |
| `PersonalFact` | Migrated into PK as `provenance=legacy_extraction`. Structural migration only — **no semantic re-interpretation.** **Table NOT deleted.** |
| `BehaviorDirective` | Only **stated-source** rows (`told` / `confirmed` / `corrected`) are eligible, as Interaction Guidance. `observed` / `derived` rows are **NOT adopted** (Contract 3.3). `meaning` is **NOT carried forward** (Contract 3.4). |
| Persona / preferences | Mapped 1:1. **No user loses their chosen persona.** Consent consolidation is conservative (Contract 2.3). |

### 14.2 Rules for legacy extracted facts

- **Provenance preserved** — `legacy_extraction` is permanent, not overwritten on review.
- **Appear for user review** — Keep · Correct · Remove, resumable, optional, never a gate on using the product.
- **Excluded from routine standing context until reviewed/accepted.** This bounds the blast radius of an inherited error: a wrong legacy fact can be found and corrected, but never quietly shapes every conversation.
- Retrievable on demand before review (so About Me is truthful), but never standing.
- Fully correctable and deletable.
- **Source stores are NOT deleted during M3.**

### 14.3 Retirement is M7

Final deletion of legacy stores, fields, settings surfaces and duplicate personalization paths belongs to **M7, after adoption is proven**. No earlier milestone may delete a legacy source.

---

## 15. Cost and observability contract

### 15.1 Activities that MAY generate provider calls

| Activity | Provider call? | Classification |
|---|---|---|
| Normal CoS conversation | yes (existing) | `source` = conversational surface; `traffic_class=production` |
| Getting to Know You interview | yes — **it is a conversation** | distinct `source` (e.g. interview) so its cost is separable; `traffic_class=production` |
| Deliberate PK extraction (structuring what the user taught) | yes, bounded | distinct `source`; `traffic_class=background` where off the request path |
| Natural-learning candidate extraction | yes, **batched** | distinct `source`; `traffic_class=background` |
| Candidate review surface | **no** — deterministic rendering | — |
| Knowledge Map / About Me | **no** | — |
| Standing-tier selection | **no** — deterministic | — |
| Retrieval-tier PK lookup | **no** — deterministic (the model's tool call is already counted in its turn) | — |

### 15.2 Requirements

- **Every** new provider call routes through the existing seam `apps/ai/llm_accounting.py :: record_llm_event`, with a **distinct `source`** so each activity is separable in `/owner/finance/` **from day one**. Cost surges have happened before precisely because a new caller was indistinguishable from conversation.
- **Do not add provider calls merely because historical learning code did so.** Every call in the legacy learning stack must justify itself against Constitution IV.2 before being reintroduced.
- **Keep the regex pre-screen** — most turns must never trigger extraction.
- **Batch** candidate extraction; do not call per turn.
- Extraction is structured work, not reasoning — a **cheaper model tier** is appropriate.
- **Standing-tier placement must preserve prompt caching** (Contract 6.1.6). The standing block is stable across turns; interleaving it with per-turn content is a cost regression.

### 15.3 Testing cost discipline preserved

The existing tiers (CLAUDE.md; `03_ENGINEERING_OPERATING_GUIDE §10a`) apply unchanged. **Tier 1 deterministic tests are the default** for every contract in this document — all sixteen are deterministically testable. **Tier 2** = one real-model smoke after a model-affecting deploy. Tier 3/4 remain reserved. **No milestone in this programme may adopt repeated real-model runs as its default verification strategy.**

---

## 16. Contract enforcement — tests future milestones must add

**Purpose: make it structurally impossible for another runtime migration to silently disconnect personalization or learning while the UI keeps promising it.** That is exactly what happened between 2026-07-09 and 2026-08-17, and it was invisible because no test asserted end-to-end delivery.

These follow the established repository pattern (`apps/core/tests/test_*_contract.py`).

| # | Contract test | Asserts | Milestone |
|---|---|---|---|
| **T1** | **Persona delivery** | For a user with a persona selected, the composed **instruction block** (not just the key) is present in the certified runtime's system prompt | M1 |
| **T2** | **Precedence** | Explicit setting beats persona default beats system default; provenance tags are correct | M1 |
| **T3** | **Operational preference delivery** | **Every** preference in Contract 2.1 appears in the envelope. Adding a preference without delivery **fails CI** — the specific gap that hid `sensitivity_tags` | M1 |
| **T4** | **UI ↔ runtime parity** | Every user-editable personalization control has a runtime consumer. **A control the runtime ignores fails CI** — the class that produced this entire investigation | M1 |
| **T5** | **PK delivery** | Eligible PK reaches the envelope; the `get_personal_knowledge` tool returns for topic/subject/entity | M2 |
| **T6** | **Standing-tier bounds** | Hard cap enforced; **sensitive facts never present**; `unreviewed` legacy facts never present | M2 |
| **T7** | **Domain-truth non-duplication** | PK contains no copy of a value a domain owns; boundary decision procedure holds on the §5.3 examples | M2 |
| **T8** | **No plaintext** | PK statements are encrypted at rest | M2 |
| **T9** | **Correction lineage** | Correction supersedes and preserves lineage; never destroys history | M2 |
| **T10** | **Deletion completeness** | Deletion leaves **no recoverable representation** — asserts absence of content hashes/fingerprints of deleted statements | M2 |
| **T11** | **PK ≠ domain deletion** | Deleting PK never deletes a canonical domain record, and vice versa | M2 |
| **T12** | **Presentation truth** | No forbidden vocabulary, percentage, or progress indicator in Knowledge Map surfaces (pattern of `test_visual_truth_contract.py`) | M3 |
| **T13** | **Legacy review gating** | `unreviewed` legacy facts are retrievable but **never standing**; source stores still exist post-M3 | M3 |
| **T14** | **Coverage is not a questionnaire** | The interview-state record exposes **no** `next_topic`, ordering, score, or completion field | M4 |
| **T15** | **Declined topics** | A declined topic is never offered, at any preference setting | M4 |
| **T16** | **Persona invariance** | The same taught content yields the same stored knowledge across personas | M4 |
| **T17** | **Invitation limits** | Rate limits and `Never` are deterministically enforced regardless of model behaviour | M4 |
| **T18** | **Candidate quarantine** | A candidate **never** appears in the envelope, standing tier, or retrieval results before acceptance | M6 |
| **T19** | **No sensitive third-party candidates** | Sensitive third-party information is never generated as a candidate | M6 |
| **T20** | **Learning gates** | `Pause learning`, no-learn turns and consent gates suppress **all** write paths | M6 |
| **T21** | **Cost classification** | Every new provider call records a distinct `source` through `record_llm_event` | M4/M6 |
| **T22** | **Interpretation prohibition** | No WLJ-authored `meaning`/prose field is reintroduced on Interaction Guidance | M1/M2 |

**T3 and T4 are the load-bearing ones.** Everything else protects a feature; those two protect the *promise*.

---

## 16a. M2 as-built — provider/privacy verification status (2026-08-19)

M2 creates the first persistent Personal Knowledge store, so Contract 13's verification
list is now **live and outstanding**. Recorded here rather than in the frozen design,
because it is operational state, not architecture.

**Established from the repository (no operator action needed):**

| Fact | Evidence |
|---|---|
| Endpoint in use | `/v1/chat/completions` (`apps/ai/services.py`) — ZDR-eligible per OpenAI docs |
| PK payload encrypted at rest | `encrypt_personal_data` / `decrypt_personal_data_safe`, the SAME utility as the legacy `_ai_personal_context` blob — no plaintext regression |
| Dev fallback behaviour | without a key the utility prefixes `UNENCRYPTED:`; identical to the legacy blob, and asserted by test so the column can never hold an unmarked plaintext statement |
| PK never reaches the provider except as context | PK is delivered only inside the structured-context block of the system prompt; no separate provider call exists |
| No PK in logs/telemetry | `__str__` omits the statement; service logging carries ids/topics only — both asserted by test |

**Requires Danny/operator verification before ANY user-facing privacy wording ships (M3):**

1. Is the OpenAI organisation opted **out** of data sharing for training? (API default is out; the account setting is what must be confirmed.)
2. Is **Zero Data Retention** enabled, or eligible-but-unenabled, for this organisation?
3. Is `PERSONAL_DATA_ENCRYPTION_KEY` configured in the production environment? **Until it is, Personal Knowledge statements are stored with the `UNENCRYPTED:` prefix rather than Fernet-encrypted** — the same exposure the legacy blob already has, but M2 materially increases the volume of durable personal text, so this should be confirmed before M3 invites users to teach WLJ about their lives.

Item 3 is the one with real user-visible consequence and is the single highest-value
check of the three. Nothing in the architecture depends on ZDR (Contract 13.5).

## 17. M0 definition-of-done audit

| # | Criterion | Status |
|---|---|---|
| 1 | Every future authority has a precise responsibility | ✅ Contracts 1–4, 8 |
| 2 | Every boundary is explicit | ✅ Contracts 3, 5, 7; target-state §11 |
| 3 | Personal Knowledge record semantics frozen | ✅ Contract 4 |
| 4 | Learning semantics frozen | ✅ Contract 7 |
| 5 | User-control semantics frozen | ✅ Contract 9 |
| 6 | Sensitivity / third-party policy frozen | ✅ Contract 10 |
| 7 | Provider/privacy contract frozen, provider-agnostic | ✅ Contract 13 |
| 8 | Legacy adoption rules frozen | ✅ Contract 14 |
| 9 | Future contract tests identified | ✅ Contract 16 (T1–T22) |
| 10 | No feature implementation begun | ✅ documentation only |
| 11 | No feature migration begun | ✅ none created |
| 12 | No provider configuration changed | ✅ none touched |
| 13 | No real-model testing occurred | ✅ none run |
| 14 | Documentation committed under normal discipline | ✅ changelog + index updated |

### Contradictions discovered against the frozen design

**None.** One dependency was **recorded rather than invented**: canonical Person ownership (Contract 5.4), which the already-approved Person Consolidation design settles. Two live defects were re-confirmed and are already assigned (persona instructions never reaching the runtime → M1; `sensitivity_tags` never reaching the runtime → M1).

### Prerequisite for M1

**None.** M1 (Personas + Unified Chief of Staff Preferences) depends only on Contracts 1, 2, 3 and tests T1–T4, T22 — all frozen above. It requires nothing from Personal Knowledge, the interview, or the provider investigation.

**M1 is UNBLOCKED.**
