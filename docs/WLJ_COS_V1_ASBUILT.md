# WLJ Chief of Staff — v1.0 As-Built Architecture (Rollback Reference)

> **Purpose.** This document is the complete as-built record of how the Chief of Staff (CoS)
> works today, immediately before the v2.0 "intent-first" evolution. It is the **rollback
> reference**: the code state it describes is tagged **`cos-v1.0-checkpoint`** (commit
> `4bacbcc3`, pushed to remote). Nothing in v1.0 is to be lost. Every claim below is anchored
> to a file and line so it can be verified or restored.
>
> **Scope.** The **model-interface runtime** (`preferences.use_model_interface=True`) — the
> path Danny is actually on and the only one relevant to v2.0. The two other coexisting
> runtimes are documented in §2 for completeness.
>
> *Last updated: 2026-08-06. Reflects Blockers #3–#12, intent-and-domain horizons, and #13A.*

---

## 0. One-paragraph summary

WLJ owns the **deterministic truth** of a person's life; a provider-agnostic conversational
model owns **reasoning, conversation, and communication**. On each turn the model-interface
runtime assembles a large system prompt = a fixed **Constitution** (identity + doctrine) +
several **salient leads** (facts raised to prominence) + a **structured-context JSON** of
owned truth interfaces, and drives the model through a **bounded agentic tool loop** in which
the model calls read-only **truth tools** (and, when enabled, **write/action tools** behind a
deterministic confirmation gate). WLJ answers every tool call deterministically through a
**canonical truth envelope**, audits it, and returns it. The model narrates. Today the model
decides *what to retrieve* mostly from the **domain** implied by the question — a correct
Q&A engine. v2.0 inserts an **intent/help-type understanding step before retrieval is
chosen** (see the separate v2.0 design).

---

## 1. Current architecture (the boundary)

```
                 ┌─────────────────────────── WLJ (deterministic) ───────────────────────────┐
  User ⇄ Chat →  │  Truth domains · envelope · registry · execution/decision authority ·      │
                 │  personal truth · current context · conversation state · confirmation ·     │
                 │  audit · intelligence engines (SAME/ISE, background only)                    │
                 └───────────────▲───────────────────────────────────────────────┬────────────┘
                                 │ truth tools (read)          write/action tools  │
                                 │ + composed briefings         (confirm-gated)    ▼
                 ┌───────────────┴──────────── Conversational model (provider-agnostic) ────────┐
                 │  meaning · prioritization · synthesis · recommendation · conversation         │
                 └──────────────────────────────────────────────────────────────────────────────┘
```

**Invariants (v1.0, preserved in v2.0):**
- WLJ never invents a fact; the model may reason but never fabricate (`constitution.py:44-48`).
- A value about the user may be stated only when a truth tool returned it for the scope being
  answered (`constitution.py:50-59`).
- Heavy analytics never run on the request path — read pre-computed cache/snapshot only
  (`get_module_state(..., allow_rebuild=False)`, `state_engine.py:74`; `docs/WLJ_REQUEST_PATH_SAFETY.md`).
- The provider is config behind one seam; no vendor/assistant name is a system identity.

---

## 2. Conversation flow (entry → runtime → response)

**HTTP entry points** (`apps/ai/urls.py`):
- `api/chat/` → `AssistantChatView` (`apps/ai/views.py:963`, `post` at `:981`) — **non-streaming**.
- `api/chat/stream/` → `AssistantChatStreamView` (`views.py:1283`, `post` at `:1304`) — **SSE**; the
  view is only a relay (`_chat_relay_stream`, `views.py:1179`), it does not generate.
- `api/chat/stream/resume/<job_id>/` → `AssistantChatResumeView` (`views.py:1402`) — reconnect by job id.

Both call **one gateway**: `CoSGateway.respond(...)` (`apps/ai/cos_gateway/gateway.py:108`), which rejects
non-migrated surfaces (`MIGRATED_SURFACES={chat, chat_stream}`, `cos_gateway/envelope.py:34`) and
resolves the runtime once.

**Runtime selection** — `CoSGateway.resolve_runtime` (`gateway.py:48-63`), precedence:
1. `preferences.use_model_interface` → **`ModelInterfaceRuntime`** ← *Danny's active path.*
2. else `evidence_tools_enabled(user)` → `ChatGPTCoSRuntime`.
3. else → `LegacyBethRuntime` (**default** fall-through).

The three classes live in `apps/ai/cos_gateway/runtime.py` (`ChatGPTCoSRuntime:48`,
`ModelInterfaceRuntime:133`, `LegacyBethRuntime:356`); legacy imports are confined to the legacy class.

**`ModelInterfaceRuntime.respond`** (`runtime.py:142`), in order:
1. **Typed-confirmation short-circuit** (`:157-167`) — only when there's a message and no new
   uploads. `resolve_typed_confirmation(user, conv.id, message)` (§7) can resolve a pending
   yes/cancel **without a model call** (`_deliver_confirmation_result`, `:291`).
2. **Multimodal ingest** (`:172-219`) — store uploads as hashed artifacts, sample video frames,
   link artifacts to the conversation, re-perceive an already-active artifact when no new upload.
3. **Streaming branch** (`:222-238`) — mint `job_id`, seed the bus, enqueue
   `run_model_interface_generation.delay(...)`; return `stream_job_id`. (The task persists messages.)
4. **Non-streaming branch** (`:240-289`) — `load_conversation_history` **before** persisting
   (`:247`); create the user `AssistantMessage`; call `ModelInterfaceService.generate(...)` (`:259`);
   `confirmation.bind_conversation(...)` (`:271`); persist the assistant message with any
   confirmation card + `metadata{cos_path:"model_interface", tools_called}` (`:272`).

**Where it runs:** non-streaming generation runs **synchronously in the web/gunicorn request**;
streaming generation runs in the **Celery worker** (`run_model_interface_generation`,
`apps/ai/model_interface/tasks.py:40`, `soft_time_limit=95`), with the web process relaying the
`chat_stream_bus` snapshot as SSE (single-writer = the task; `apps/ai/chat_stream_bus.py`).
Task→queue routing: `run_model_interface_generation` is **not** in `CELERY_TASK_ROUTES`
(`config/settings.py:1240`), so it lands on the default `celery` queue. *Exact prod worker fleet
is defined in the Railway dashboard, not the Procfile* (see the deploy-topology memory).

---

## 3. Prompt & environment construction

**Two files own it:** `apps/ai/model_interface/constitution.py` (fixed doctrine + tool schemas)
and `apps/ai/model_interface/service.py` (`ModelInterfaceService` — per-turn assembly).

### 3.1 The Constitution (`constitution.py:18-537`)
One concatenated string; provider-agnostic; 24 doctrine sections in file order:

1. **WHO YOU ARE — YOUR IDENTITY** (`:19-38`) — "You are the user's Chief of Staff… A chief of
   staff does NOT report data or read out sections; they think, decide what actually matters, and
   tell the person the one thing they most need to hear and do." Frames all below as *guardrails*.
2. Personal-assistant / WLJ ownership split (`:40-42`).
3. **TRUTH / no-fabrication** (`:44-48`).
4. **ANSWER GROUNDING** (governing) (`:50-59`).
5. **TRUTH ENVELOPE — read it before you speak** (`:61-68`).
6. **SELF-CONSISTENCY** (`:70-75`).
7. **MEDICAL INFORMATION POLICY** — 3 levels (`:77-123`): L1 WLJ truth (answer directly), L2
   general medical knowledge (attribute to ADA/CDC/NIH/…), L3 personal interpretation (no
   personalized medical advice, referral said once), out-of-range = calm & factual.
8. RELATIONSHIP (honor chosen name / default relationship / style) (`:125-127`).
9. DETERMINISTIC UNDERSTANDING (reason from it, don't recompute) (`:129-142`).
10. CURRENT CONTEXT (clock, current_screen, capabilities) (`:144-159`).
11. CONVERSATION STATE (what we're doing / waiting on) (`:161-169`).
12. **RETRIEVAL PRECEDENCE** — source list 0–5 (`:171-194`): (0) active conversation state, (1)
    current context, (2) this conversation, (3) truth already in context
    (`deterministic_understanding`, `personal_truth`, `execution_state`, `missions`,
    `current_action`), (4) a truth tool, (5) own general reasoning.
13. INTENT — retrieve vs reason (`:196-211`).
14. **EXECUTIVE ASSESSMENT** — broad "how am I doing" answered as one synthesized judgment, not a
    dashboard (`:213-258`).
15. **INVESTIGATE BEFORE CONCLUDING** — investigator, not query engine; first move
    `get_analysis(domain, subject)` (`:260-296`).
16. **CONSIDER ALL, PRESENT THE VITAL FEW** — consider every relevant fact, say only what matters
    (`:298-313`).
17. **REASON ACROSS COMPETING HYPOTHESES** — investigate change over time, multiple hypotheses,
    rank, don't force a winner; **NO GENERIC FALLBACK** filler ban (`:315-370`).
18. **EVIDENCE-BASED RECOMMENDATIONS** (`:372-397`) — *the doctrine Blocker #13A extended*: now
    also fires on improvement-intent statements ("I need to plan my nutrition better…"), asking
    "do I already know enough to answer specifically? retrieve FIRST"; generic advice is fallback
    only when WLJ lacks the truth.
19. **PRINCIPLES, NOT PRESCRIPTIONS** (`:399-425`) — advisor, not clinician; investigate → explain →
    reference established guidance; sub-blocks CAUSATION + GOAL-AWARE.
20. ACTIONS (call the named tool; on `confirmation_required` → `resolve_pending_action`) (`:427-434`).
21. ATTACHMENTS (multimodal; batch import; earlier/past uploads; provenance) (`:436-492`).
22. **RESULTS, NOT INTENTIONS** — narrate only what already happened (`:494-503`).
23. **EXECUTIVE BRIEFING VOICE & FORMATTING** — no ChatGPT markdown; `•` bullets only (`:505-516`).
24. **COMPLETION** — response ends when the objective is satisfied; follow-up optional/gated (`:518-536`).

`RESPONSE_COMPLETION_REMINDER` (`:545-582`) is a separate compact restatement appended **last**
(highest salience).

### 3.2 `build_standing_context()` (`service.py:146-226`) — the owned truth interfaces
The assembler **owns nothing**; each field is pulled from its owner at its own freshness:

| Field | Source (owner) | Freshness |
|---|---|---|
| `ai_relationship` | `get_ai_relationship(user)` | slow (projection) |
| `deterministic_understanding` | `model_interface.understanding.read(user)` (warm-on-pending) | medium, cache-first |
| `current_context` | `get_current_context_baseline(...)` | fast (clock/screen/capabilities) |
| `conversation_state` | `conversation_state.read(conversation)` | per-turn, owned field (no tool) |
| `personal_truth` | `personal_truth_for_context(build_personal_truth(user))` | durable, cache-first |
| `missions` | `mission_link.get_mission_map(user)["missions"]` | cached 1h |
| `execution_state` | `decision_authority.execution_facts(user, state)` | per-turn, built once |
| `current_action` | `decision_authority.current_action(user, state)` (+`enrich_action`) | per-turn |
| `pending_confirmations` | `confirmation.list_open(user)` | **only when writes enabled** |

### 3.3 The six salient leads (`service.py`) — raise a fact to prominence, no new retrieval
- `_attachment_lead` (`:457`) — files attached this turn ("do NOT ask to upload again").
- `_conversation_state_lead` (`:354`) — pending confirmation → `resolve_pending_action`; active
  subject (metric → re-retrieve for new date; "it/that/why" follow-ups also refer to it — #12).
- `_executive_lead` (`:526`) — **`current_action`**; LEAD with it on EXECUTION/check-in vs
  completeness ("what's left" → enumerate) vs "walk me through my day" (tasks + calendar). A broad
  EXECUTIVE ASSESSMENT / investigation question ("how am I doing", "where should I focus", "what am
  I neglecting") is NOT collapsed onto `current_action` — it investigates across domains and
  synthesizes (the model owns the verdict, I.4). *(Grown across #3, #6, #7, #9; Executive
  Over-Steer Correction 2026-08-12 — `docs/WLJ_COS_MODEL_ON_TRUTH_ASSESSMENT.md`.)*
- `_focus_lead` (`:237`) — on-screen object (inlines content; "answer from THIS, do not retrieve").
- `_profile_lead` (`:278`) — nutrition targets / conditions / allergies as HARD CONSTRAINTS.
- `_grounding_lead` (`:428`) — unconditional; restates GROUND-IT / READ-ENVELOPE / OWN-A-CONTRADICTION.

### 3.4 `_system_prompt()` concatenation order (`service.py:560-577`)
`CONSTITUTION` → attachment → conversation_state → **executive** → focus → profile →
`"=== STRUCTURED CONTEXT …"` + `json.dumps(standing_context)` → grounding → `RESPONSE_COMPLETION_REMINDER` (last).

### 3.5 The model call
`generate()` (`service.py:922`) → `AIService._call_api_with_tools(system_prompt, message,
tools=all_tools(writes_enabled), dispatch, conversation_history, images)` (`services.py:685`): a
**bounded agentic loop** (`resolve_tool_loop_budgets(endpoint)`), `tool_choice="auto"` each round,
**tools dropped on the final round** so the model must answer in prose. Images become a multimodal
content array. `load_conversation_history(conversation, limit=12)` (`service.py:62`) loads **all**
user/assistant turns (the `message_type` filter was removed — Blocker #3).

---

## 4. Retrieval & truth flow (the tools)

Model tool call → `dispatch` (`service.py:895`) → `_do` branch (`:690`) →
`cos_services.get_domain_*` → `_wrap_truth` (`:96`) maps the branch status into the **canonical
envelope** → audited `kind="truth"` → returned to the model. The retrieved subject is captured as
`conversation_state.active_subject` for follow-up continuity (`_SUBJECT_BEARING_TOOLS`, `:584`).

**Read tools** (schemas dynamically enum'd from the catalog, `constitution.py:590-704`):

| Tool | Returns | Impl (`apps/ai/cos_services/`) |
|---|---|---|
| `get_domain_state` | current composed SAE snapshot for a domain | `domain_state.py:121` |
| `get_history` | per-period aggregates + within-window `change`/trend | `domain_history.py:144` |
| `get_readings` | intra-day timestamped samples + window stats/excursions | `domain_readings.py:184` |
| `get_event_frequency` | how often an event occurs across recurring windows over time | `domain_event_frequency.py:149` |
| `get_comparison` | period-A vs period-B delta/pct/direction | `domain_comparison.py:110` |
| `get_adherence` | actual vs registered target (variance/% / counts) | `domain_adherence.py:81` |
| `get_entity` | record-level detail (CompleteEntity); re-perceives artifacts | `domain_entity.py:185` |
| `get_analysis` | **one composed investigation bundle**; `subject="overall"` = whole-domain roll-up | `domain_analysis.py:494` |
| `get_user_truth` | durable stored profile (targets, conditions, meds, goals, priorities) | `personal_truth.py:360` |
| `get_foundational_health_facts` | date-independent scalars (meds, latest weight, 7-day avgs) | `health_facts.py:642` |
| `search_history` | keyword CONTENT search (legacy SearchService adapters) | `history_search.py:176` |

**Canonical envelope** (`apps/core/truth/envelope.py`): `value, freshness(current|stale|pending|
partial|missing), confidence(high|med|low|none), source, as_of, status`. Status vocabulary
`ok/pending/empty/insufficient_evidence/missing/error` (`:38-43`). Honest-absence constructors
(`pending/missing/insufficient_evidence/empty/error`). Blocker #5: `_wrap_truth` for
`unsupported*` preserves the customer-safe `reason` + assessable areas, never re-emits the raw
status token (`service.py:108-122`).

**Domain registry** (`apps/core/truth/domain.py`): `DomainTruth` facade per domain
(`current/history/readings/event_frequency/state/describe`), `registered_domains()`,
`WHOLE_DOMAIN_SUBJECT="overall"`. A domain earns the synthetic `"overall"` subject when it has ≥2
analysis subjects / history metrics / current metrics (`:231-235`). `catalog.py::truth_catalog()`
is the single source the tool enums read.

**Meaning-based routing** (`apps/core/truth/semantics.py`): `DOMAIN_SEMANTICS` distinguishes sibling
concepts (nutrition = meal EATEN vs meals = meal PLANNED; calendar.event vs events.event), exposed
as `capabilities.domain_semantics`.

**Date resolution** (`apps/core/truth/periods.py`): `resolve_date_expression(phrase, today)` is THE
shared resolver — named periods, aliases, **relative-night phrases** (#11), "last/past N units",
ISO dates, weekdays, "N days/weeks/… ago". The model passes the natural phrase; WLJ resolves it.

**`get_domain_analysis` composition** (`domain_analysis.py`): single-subject path reuses history
(trailing windows + all-time coherent `change`) + entity detail, with `holds_data`/`evidence`.
Whole-domain `overall` → `_domain_overview` = **STATE** (`get_domain_state`) + **TRENDS**
(`get_domain_history` per facet over ONE window). Window: explicit period honored exactly; else
**domain-natural default** (`_DOMAIN_DEFAULT_DAYS`: finance/health 30, relationships/medical 90,
nutrition 14, legacy 365) then **auto-widen** (90→365→3650) to the most-recent window with activity
(#horizons). `_state_is_present` ignores a disabled `{enabled:False}` marker (#8). Health replaces
the flat state with a concept-organized fact view, WLJ verdicts stripped.

---

## 5. Reasoning flow (how the model decides — the v2.0 target)

Per turn: (1) the model reads the Constitution + leads + structured JSON + history; (2) it
**decides whether and what to retrieve**; (3) it runs the bounded tool loop; (4) it narrates under
the completion/formatting doctrine. Retrieval selection is governed by **doctrine text the model
interprets** (§3.1) — there is **no deterministic intent/help-type classifier**, by design (meaning
belongs to the model, not WLJ).

**v2.0 change (shipping, model-side only — not a new step/layer/classifier).** The model's **first
internal question** was reframed at the top of the identity (`constitution.py`, the
`HOW A CHIEF OF STAFF BEGINS — YOUR FIRST INTERNAL QUESTION` block): from *"what did they ask / which
domain?"* to **"what kind of help is this person actually asking me for?"** — and, when WLJ already
holds the truth, *review what they've actually been doing before answering*. WLJ still only supplies
truth; it never classifies the ask. This generalizes Blocker #13A (which only extended one deep
doctrine and missed the relationship/commitment cases). It is proving itself in production
conversation-by-conversation via the standard blocker loop — not on paper.

---

## 6. Executive assessments & intelligence

- **Single decision authority** — `decision_authority.current_action(user)` (`apps/core/execution/
  decision_authority.py:37`) is the ONE producer of "what to do now"
  (`{mode, primary_action, reason, follow_on, message}`), over `build_execution_state`
  (`execution_state.py:48`) and `selectors.get_next_action`; a second selector is CI-rejected.
  `execution_facts` gives the day as facts; `compute_execution_phase` is the deterministic day-phase.
- **Mission link** — `mission_link.get_mission_map` / `enrich_action` join an action → signal_type →
  ranked goals (references only; prose lives once in `missions`).
- **Executive assessment** — whole-domain STATE+TRENDS via `_domain_overview` (§4); broad "how am I
  doing" answered as one synthesized judgment (Constitution §14) leading with `current_action`
  (`_executive_lead`).
- **CoS intelligence (the "one brain")** — `cos_intelligence.build_cos_intelligence(user)` and
  `compose_executive_read(user)` → `chatgpt_cos.executive_interpretation.interpret(user)`; standing
  reads composed in `cos_context.py` and projected read-only by `standing_context.py`
  (`executive_read` placed first). `active_intelligence` reads pre-computed Insight/Prediction/
  Guidance records — never recomputed on the request path.
- **SAE state** — `get_module_state(user, module, allow_rebuild=False)` on the request path (read
  cache/snapshot only); builders in `ai_state/state_builder.py` run in the background.
- **Engines (Celery Beat, background)** — SAME (60s anomaly monitoring), ISE (300s scheduler
  dispatching DBE/GLOE/PGE/WIRE/DNE…), CoS keepalive (30s cache warm), nightly signals.
- **Proactive check-ins** — `proactive_checkins.py` (throttled/deduped, writes
  `AssistantMessage(is_proactive=True)`); `checkin_author.author_checkin` uses the **same**
  `build_standing_context` envelope and degrades to `current_action_directive`.

---

## 7. Write path & confirmation

**Exposure:** `ALLOWED_WRITE_INTENTS = (mutate_task, create_task, complete_task, log_weight,
log_body_measurements, import_journal_entries)` (`constitution.py:1140`), appended to the tool set
**only when `writes_enabled`** (`preferences.use_model_interface_writes`, fail-safe False,
`service.py:137`). Plus `resolve_pending_action`.

**Dispatch:** write intent → `action_interface.request_action` (`service.py:882`);
`resolve_pending_action` → `action_interface.resolve_pending_action` (`:886`).

**`action_interface.py`:** `request_action` runs `execute_action`; on `confirmation_required` it
`build_view(...)` + `_confirm.create(...)` a **bound confirmation** and returns the client payload.
`resolve_pending_action` executes a **specific** confirmation by id (`params["confirmed"]=True`,
single-use consume). `resolve_typed_confirmation` deterministically resolves a typed yes/cancel via
`match_typed` **before the model** (the model is never load-bearing for confirm/cancel).

**`action_execution.execute_action`:** allowlist gate (`DAY1_ACTION_ALLOWLIST`) → confirmation gate
(`_confirmation_required` via `ACTION_POLICY`; `mutate_task` = HIGH/CONFIRM) → forward `confirmed`
only for `_DATA_CONFIRM_INTENTS` (`multimodal.py:792` = log_weight/log_body_measurements/
import_journal_entries) → `IntentService.execute_intent` → handler.

**Rich Confirmation:** `model_interface/confirmation.py` (per-user cache store, TTL 300, bind/
list/open/consume) + `confirmation_contract.py` (`CONFIRM_ALIASES`/`CANCEL_ALIASES`, `build_view`,
`match_typed`). **Audit:** `cos_services/audit.py::record_tool_call` → `ToolCallLog`
(`apps/ai/models.py:2122`; `kind ∈ truth/action/preference/response`).

**KNOWN DEFECT — `mutate_task` delete confirmation loop** (write-path Blocker #13, root cause
independently confirmed): two compounding mismatches — (a) the resolver forwards `params['confirmed']
=True`, but `handle_mutate_task` delete only honors `kwargs['delete_confirmed']`, and `mutate_task`
is excluded from `_DATA_CONFIRM_INTENTS` so `confirmed` is stripped before reaching the handler;
(b) the handler returns `error='delete_confirmation_required'`, which `execute_action`'s re-mint
check (`err=='confirmation_required'`) does not match. Net: a typed/button "yes" consumes the
one-shot confirmation and returns an error while the task is never deleted. **Contained fix known**
(align the flag + error code; add `mutate_task` to the confirmed-forward set). Deferred, not lost.

---

## 8. Read path & current context (page awareness)

- **Detail page** → focused object `app.model:pk` via `<meta name="wlj-context">`, resolved by
  `resolve_current_context(user, ref)` (`apps/core/current_context.py:217`) →
  `NarratableMixin.get_context_summary`.
- **Overview page** → `summary:<key>` via `@register_page_summary` + `PageSummaryMixin`
  (user-scoped, request-path-safe, facts-only providers).
- Enters the envelope as `current_context` (`cos_services/current_context.py::
  get_current_context_baseline`), salience raised by `_focus_lead` (inlines on-screen content).

**Conversation continuity** — `conversation_state.py`: `record_turn` anchors the active subject from
attachments or a `retrieved_subject` (with `domain`/`metric` pointers so a date-shift follow-up
re-retrieves — #10/#11); `read` returns the non-expired working state (TTL 1800s, subject backstop
12 turns). `load_conversation_history` loads all user/assistant turns (#3).

**Personal truth** — `personal_truth.py::build_personal_truth` is the ONE composer for both the
standing-context `personal_truth` field and the `get_user_truth` tool; detects nutrition-target
contradictions; facts carry provenance/authority/sensitivity.

---

## 9. Known strengths (preserve these)

1. **Clean truth/reasoning boundary** — WLJ owns deterministic truth; the model reasons. One seam,
   provider-agnostic. This is the foundation and must survive v2.0 untouched.
2. **Canonical envelope + honest absence** — every fact carries freshness/confidence/source; empty vs
   insufficient vs error are distinct; no fabrication.
3. **Single decision authority** — exactly one producer of "what to do now"; consumers never
   re-prioritize.
4. **Request-path safety** — heavy analytics are background-only; the request path reads
   cache/snapshots; CI enforces it.
5. **The salient-lead mechanism** — a proven, low-risk way to raise a specific truth to prominence
   near the user's turn (the vehicle for most Blocker fixes #3–#12).
6. **Deterministic confirmation & audit** — typed yes/cancel resolves without the model; every
   tool/action is audited to `ToolCallLog`.
7. **Composed assessments** — whole-domain STATE+TRENDS with domain-natural, auto-widening horizons;
   grounded, specific answers where data exists (health/finance/relationships verified in prod).
8. **Continuity** — active-subject anchoring + full history + shared date resolver make date-shift
   and pronoun follow-ups work.

## 10. Known weaknesses (why v2.0 exists — and the backlog)

1. **PRIMARY: Q&A engine, not yet a Chief of Staff.** Retrieval is chosen from the *domain* implied
   by the question, governed by doctrine text the model interprets — there is **no deterministic
   step that first asks "what kind of help is being requested?"** This produced Blocker #13A
   (generic advice when personal truth existed). *This is the v2.0 target.*
2. **13B — the CoS cannot explain its own behavior.** "Why didn't you do that to start with?" is met
   with a clarification request, not an explanation. Open; own trace/fix pending.
3. **Write-path #13 — delete confirmation loop** (§7). Contained fix known; deferred.
4. **Observability gap** — write/resolve tool calls are audited as `kind='response'`/empty tool_name
   in the transcript view, making the write path hard to see in `ToolCallLog` traces.
5. **Cross-domain causal reasoning is a boundary, not a capability** — "what's affecting my sleep?"
   is answered within-domain; WLJ computes no correlations (deliberate — avoids ungrounded causation).
6. **Two other coexisting runtimes** (ChatGPT CoS, Legacy Beth) add branching; only model-interface
   is Danny's path. Not a defect, but complexity to be aware of.
7. **Operational** — worker redeploys cause a brief window where enqueues are dropped
   (`redis: circuit_open`); acceptance runs must wait for the worker to warm.

---

## 11. Rollback

- **Tag:** `cos-v1.0-checkpoint` (annotated) at commit `4bacbcc3`, pushed to
  `git@ssh.github.com:djenkins452/dbawholelifejourney.git`.
- **To roll back:** `git checkout cos-v1.0-checkpoint` (or reset a branch to it) and redeploy. Every
  subsystem above is anchored to file:line at that commit.
- **Do not lose:** the invariants in §1, the single decision authority (§6), the envelope contract
  (§4), request-path safety, and the salient-lead mechanism (§3.3) — v2.0 builds *on* these, never
  replaces them.
