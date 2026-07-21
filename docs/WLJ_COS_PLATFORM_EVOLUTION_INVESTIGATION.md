# WLJ — Chief of Staff Platform Evolution: Architectural Investigation

**Status:** Investigation only. No code written. Produced in response to the ratified direction *"One Chief of Staff, many workspaces"* (`01 §6`, `02` Constitution Article II, bootloader `00 §PRIMARY FOCUS`).
**Method:** Four parallel runtime traces (reuse map · Current Context flow · Journal separability · navigation), every claim carrying `file:line`.
**Governing question:** How do we *evolve* — not redesign — the existing system so the Chief of Staff sits above every domain, preserving everything that already works?

**One-line finding:** The platform is already ~85–90% "one CoS, many workspaces." The work is overwhelmingly **recognition, consolidation, and elimination** — not construction. There is exactly **one net-new capability** (CoS-decided navigation on the keeper runtime), exactly **one shape to generalize** (the durable draft session), and several **architectures to delete**.

---

## 0. The single most important discovery — two runtimes, not one

The two independent traces landed on **two different chat runtimes**, and reconciling them *is* the migration:

| | **Keeper runtime** (`model_interface`) | **Legacy runtime** (`PersonalAssistant` / orchestrator) |
|---|---|---|
| Entry | `ModelInterfaceService.generate()` — `apps/ai/model_interface/service.py:627`, via `CoSGateway.respond()` — `apps/ai/cos_gateway/gateway.py:108` | `PersonalAssistant.send_message` — `apps/ai/personal_assistant.py`; `apps/core/ai_orchestrator/orchestrator.py` |
| Current Context | Carried as an Executive Context Envelope field + `_focus_lead` — `service.py:135-138, 211-250` | `current_context_preamble()` prepend — `apps/core/current_context.py:41-65` (only when `endpoint=="cos_chat"`) |
| Conversation State | First-class envelope field — `service.py:149-155` | — |
| **Navigation directive** | **ABSENT** — `generate` returns answer-text only (`service.py:671-672`) | **PRESENT** — `navigation` key `apps/ai/views.py:1140-1141`, produced by `_get_navigation_hint()` `personal_assistant.py:2857`, hardcoded `NAVIGATION_HINTS` `:2749` |
| Client render of nav | not emitted | `renderNavigation()` — `templates/components/chat_widget.html:2132`, consumed `:2985` |

**Implication.** "Navigation already exists" (Agent D) and "no navigation field is returned" (Agent B) are *both true* — they describe different runtimes. The keeper runtime is where Current Context, Conversation State, and the whole Executive Context Envelope live; it is the future. The legacy runtime is where a navigation channel already exists but is driven by a stale hardcoded map. **The migration is: bring navigation onto the keeper runtime by reusing the deterministic pieces the legacy path proved out, then retire the legacy path — not build navigation twice.**

---

## 1. Q1 — Which CoS components are already generic & reusable?

**Answer: 6 of 7 core systems are domain-agnostic today, by deliberate design.** The codebase repeatedly self-describes as catalog/registry-driven ("assembler owns nothing," "catalog-driven — no per-domain plumbing").

| System | Entrypoint | Verdict | Evidence |
|---|---|---|---|
| Model Interface seam | `ModelInterfaceService.generate()` | **GENERIC** on domain; **provider-coupled** | `service.py:627`; performs no reasoning (`service.py:22-24`); tools built from catalog (`constitution.py:457-512`). OpenAI hard-bound at `apps/ai/services.py:790` |
| CoSGateway | `respond(surface=…)` | **GENERIC** | `gateway.py:108`; `surface` is a transport channel not a domain (`envelope.py:34`); returns standardized `CoSResponse` (`envelope.py:61`) |
| Executive Context Envelope | `build_standing_context()` | **GENERIC** | `service.py:120`; Current Context **and** Conversation State are both peer fields (`service.py:135-155`); "assembler owns nothing" (`service.py:119-139`) |
| Conversation State | `conversation_state.record_turn()/read()` | **GENERIC** | `conversation_state.py:159/116`; subject from concrete signals, never language (`:28-32`) |
| Confirmation pipeline | `resolve_pending_action()` | **GENERIC** | `action_interface.py:112`; card is a generic `{action, params, summary, options}` (`confirmation.py:20-22`); JS has no domain names (`wlj-confirmation.js`) |
| Action + Audit pipeline | `request_action → execute_action → execute_intent` | **GENERIC** | `action_interface.py:60` → `action_execution.py:130` → `intent_service.py:1405`; "NO new write path" (`action_execution.py:28`); audit `ToolCallLog` domain-agnostic (`audit.py:45`) |
| Truth surfaces registry | `@register_domain_truth` / `get_domain_entity()` | **GENERIC** | `domain.py:45/53`; "catalog-driven — every domain that registers participates automatically" (`domain_entity.py:31-34`) |

**The only real coupling is the provider:** `AIService` binds OpenAI directly (`services.py:790`, client factory `:169`) rather than sitting behind the injectable `ai_service` seam that already exists on the constructor (`service.py:104-109`). Two systems also carry small **cross-domain config lists** (not domain locks): the action allowlist `DAY1_ACTION_ALLOWLIST` (`action_execution.py:53-70`, spans tasks/goals/journal/faith/health) and the lazy provider-module tuple `_KNOWN_PROVIDER_MODULES` (`domain.py:25-40`).

---

## 2. Q2 — Which components are truly Journal-specific?

**Answer: Very little.** The Journal app is a reference implementation where a *generic* "durable draft + conversation → composed artifact" machine is welded to journal-only nouns via a thin, identifiable seam. Even the base system prompt already opens *"You are the user's Chief of Staff"* (`journal_conversation.py:44`) — the generalization was anticipated.

**What genuinely stays Journal-only:**
- The terminal binding **Save → `JournalEntry`** and `resulting_entry` FK — `apps/journal/models.py:357-363`, `views.py:499-508`.
- **Prompt *strings* / Playbook copy** — `_CONVO_SYSTEM`, `_GEN_SYSTEM`, etc. (`journal_conversation.py:44-157`) are tuned journaling *content* (the composition *framework* around them is generic).
- **Voice-sample fidelity source** — `_voice_samples_block` reads past `JournalEntry` prose to write in the user's voice (`journal_conversation.py:384-393`).
- Vocabulary: **Journal is *Saved*; Legacy is *Published*** (fixed this session).

**What is already generic / already core (nothing to lift):**
- **Truth Discovery** lives in `apps/core/truth/discovery_suite.py`; Journal is one registered domain (`discovery_suite.py:167-183`) resolving through the generic `get_domain_entity` seam.
- **Publish-to-Legacy** is Legacy's *polymorphic import engine* — `journal` is one `SourceType` among ChatGPT/Claude/Word/PDF/memoir/GEDCOM (`apps/legacy/models.py:855-865`). There is **no journal-specific publish code**.

---

## 3. Q3 — Which Journal features should become platform CoS capabilities?

**Answer: The durable-draft machine — and only that — should be lifted; everything else either is already platform-level or is thin journal copy that stays.**

| Journal piece | Verdict | Disposition |
|---|---|---|
| `JournalConversation` + `written_body` (`models.py:317-399`) | **HYBRID** | **LIFT** → generic `WorkspaceDraftSession(transcript, written_body, generated_draft, state, resulting_object)`; only `resulting_entry` + naming are journal-bound |
| Draft lifecycle (active→reviewing→completed, resume, explicit disposal) (`journal_conversation.py:160-297`, `views.py:673-798`) | **HYBRID** | **LIFT** the state machine; terminal Save→JournalEntry stays journal |
| Autosave (`views.py:775-797`) | **GENERALIZABLE** | **LIFT** — a request-path-safe single-row write; only the target field is journal (note: it is a **DB write, not a cache key** — corrects a stale note in memory) |
| Three modes: Just Write / Write Together / Talk It Through (`views.py:605-610, 673-693`) | **GENERALIZABLE** | **LIFT** — these are *draft-channel/modality* concepts (typed channel · text conversation · voice over the same transcript), not journal concepts; only the feature-flag namespace is journal |
| `generate_entry` / `respond()` (`journal_conversation.py:227-297`) | **HYBRID** | **LIFT** the two-channel composer; voice-fidelity source + "entry" framing stay journal |
| Prompts / Playbook / Memory Model (`journal_conversation.py:44-157`) | **HYBRID** | Framework already CoS-level (reuses `build_personal_truth`, `journal_conversation.py:349-353`); **prompt strings stay** as a per-workspace injectable |
| Truth Discovery (`apps/core/truth/discovery_suite.py`) | **ALREADY CORE** | Confirm the seam only |
| Publish→Legacy (`apps/legacy/models.py:845-940`) | **ALREADY CORE** | Confirm the seam only |

**The generalization seam is small and explicit:** swap `resulting_entry→journal.JournalEntry` for a generic target object, and inject two per-workspace values — (a) the system-prompt/Playbook string, (b) the voice/fidelity source. Those two injectables are exactly what stays journal-specific.

---

## 4. Q4 — How Current Context flows today (traced end-to-end)

The keeper path, each hop with evidence:

1. **Server → HTML meta.** Two emit patterns in `templates/base.html:14-21`: overview pages emit `summary:<key>` via `PageSummaryMixin` (`apps/core/current_context.py:271-305`); any Narratable DetailView auto-emits `app.model:pk` via `object.context_ref` (`current_context.py:146-160, 247-268`) — **zero per-view code**.
2. **Page-summary providers.** Registry + decorator `register_page_summary(key)` (`current_context.py:82-96`); resolved by `_resolve_page_summary` (`:114-134`). Providers self-register at app-ready and return facts-only `{title, content, kind}` (e.g. `apps/health/page_summaries.py:24-53` reading the *same* `build_weight_summary` the page renders — single source).
3. **Transport.** Browser reads `meta[name="wlj-context"]` → `page_context.focus_ref` (`assistant_panel.html:1005-1025`) and POSTs it.
4. **Baseline resolution.** `get_current_context_baseline()` (`apps/ai/cos_services/current_context.py:368-415`) → `resolve_current_context(user, ref)` (`apps/core/current_context.py:196-244`): a `summary:` ref → provider dict; an `app.model:pk` ref → ContentType → user-scoped object → `get_context_summary()`. **Ownership enforced** at `:224-232`. Uniform output `{title, content, kind, ref}`.
5. **Into the envelope.** Attached as Pillar-4 field `current_context` (`apps/ai/model_interface/service.py:135-138`), peer to `conversation_state`, `missions`, `personal_truth`.
6. **Into OpenAI.** Raised to high salience by `_focus_lead` ("ON SCREEN RIGHT NOW", `service.py:211-250`); also inside the JSON envelope; the Constitution tells the model to answer deictic questions from focus and **not** retrieve when focus suffices (`constitution.py:96-146`). Provider call at `services.py:733, 790`.
7. **Response.** `generate` returns `{answer, tools_called, standing_context, turn_id}` (`service.py:671-672`) — **no structured navigation field** (the gap in §0).

**Generic vs. hardcoded:** the resolver, both mixins, transport, baseline, envelope field, `_focus_lead`, and Constitution are all fully generic — a new page becomes conversational with one mixin line. Domain knowledge is isolated in each `@register_page_summary` provider (lives with the module, never in the CoS). **Legacy DOM scrapers** in `assistant_panel.html:871-985` still feed the old `page_content` scrape — superseded by `focus_ref`, and a deletion candidate.

---

## 5. Q5 — How navigation becomes a deterministic CoS action, inside existing architecture

**Every piece already exists; the net-new code is glue, not architecture.**

- **Concept → URL registry:** `TeachingDestination` (`apps/help/models.py:529`) — **190 active rows** in `apps/help/fixtures/teaching_destinations.json`, each a concept→route map (`/health/weight/`, `/journal/`, `/calendar/availability/`…). Adding a destination is a fixture row.
- **Resolver:** `resolve_route(text, subject, module)` (`apps/core/action_router.py:252`) already scores free text against `TeachingDestination.get_all_active()` and returns an `OPEN_WORKFLOW` `ActionRoute` with `destination_url` + `destination_label` (`:50-73`). Crash-safe, never raises (`:300`).
- **Response channel:** the `navigation` `{url, label, action_type}` directive already exists on the legacy API (`apps/ai/views.py:1140-1141`) and is declared first-class on the orchestrator envelope (`orchestrator.py:74`).
- **Client:** `renderNavigation()` already turns that dict into a clickable link (`chat_widget.html:2132`, consumed `:2985`).

**What's missing (all keeper-runtime glue):**
1. A first-class **`navigate_to_workspace`** tool/intent that fires on a *pure* navigation request ("show me my weight history", "I'd like to journal") — today navigation only fires *after a successful mutation* via the hardcoded `NAVIGATION_HINTS` (`personal_assistant.py:2749, 2866-2870`).
2. Wiring that tool into the **keeper** runtime: add a `navigate` field to `generate`'s return (`service.py:671-672`) and register the tool in the model's toolset (`all_tools()`, `service.py:647`).
3. Have it call `resolve_route()` (the 190-row registry) **instead of** the stale 26-entry `NAVIGATION_HINTS` map.

**Constitutional fit:** navigation is an **action** (Article I.7 — safe, deterministic, audited path) whose target is deterministic truth (Current Context `location.url` + `TeachingDestination`). Current Context is already Article II authority. **No Constitutional Review required** — this is ordinary in-Articles work, matching the bootloader's framing. The CoS must **answer-in-place when the current workspace suffices** (Article II.4 — Current Context enriches, never traps) and navigate only when another workspace's surface *is* the better answer.

---

## 6. Q6 — Which services already support this model

Nearly all of them. The invariant loop **One CoS → Current Context → workspace → truth → tools → conversation continues** is already assembled from existing parts:

- **One CoS / one conversation:** `CoSGateway.respond()` (`gateway.py:108`) + `ModelInterfaceService` (`service.py:627`) — surface-agnostic, single conversation record.
- **Current Context:** fully generic pipeline (§4).
- **Conversation State:** deterministic working-state, envelope field (`conversation_state.py`).
- **Truth per workspace:** `@register_domain_truth` catalog (`domain.py:45`).
- **Tools per workspace:** built from the catalog dynamically (`constitution.py:457-512`).
- **Navigation targets:** `TeachingDestination` (190 rows) + `resolve_route()` (`action_router.py:252`).
- **Actions + audit:** one write path + `ToolCallLog` (`action_execution.py:130`, `audit.py:45`).

---

## 7. Q7 — What can be generalized without breaking Journal

- **Lift `JournalConversation` → `WorkspaceDraftSession`** with Journal as a thin subclass/target — Journal keeps its `resulting_entry`, prompt strings, and voice source. Existing Journal behavior is preserved because the journal bindings become the *first* configured workspace of the generic primitive, not a rewrite.
- **Autosave, the three modes, and the two-channel composer** generalize with only the target field / flag namespace / prompt+voice injectables changing.
- **Navigation** is added on the keeper runtime as new glue; no existing Journal path changes.
- **Everything already core** (Truth Discovery, Legacy import, Current Context, Conversation State, confirmation, action/audit) needs *nothing* — only doc-level recognition as CoS platform capabilities.

---

## 8. Opportunities to ELIMINATE architecture (not add it)

The strongest outcome of this investigation: the reframe lets us *delete*, not build.

1. **Delete the legacy DOM scrapers** — `assistant_panel.html:871-985` per-page `querySelector` blocks are fully superseded by server-side `focus_ref`/Current Context. Removes a whole class of "scraped DOM disagrees with truth."
2. **Collapse two navigation sources into one** — retire the hardcoded `NAVIGATION_HINTS` (26 entries, `personal_assistant.py:2749`) in favor of the single `TeachingDestination` registry (190 rows) via `resolve_route()`. One deterministic source of navigation truth (Article III.1 spirit).
3. **Retire the duplicate conversation runtimes** — legacy Beth + ChatGPT-CoS collapse into `model_interface` as users converge (already an audit-only track in the bootloader). This deletes the `current_context_preamble` legacy injection (`current_context.py:41-65`) and the `NARRATIVE_SURFACES` migration scaffold (`envelope.py:53`).
4. **Prevent future duplication before it happens** — generalizing the draft session *eliminates* the per-workspace draft models that would otherwise be forked. The Travel architecture doc *already plans* to "reuse the Journal draft lifecycle" — give it a real primitive to reuse instead of a copy to make.
5. **(Longer-term) close the provider seam** — move OpenAI behind the already-present injectable `ai_service` seam so `services.py:790` is not the one hard binding. Not urgent; the single genuine coupling.

Net: the platform gets **simpler** as it becomes more capable — exactly the Article IV.2 test.

---

## 9. Recommended migration strategy (phased, no big-bang, reuse-first)

**Phase 0 — Recognition (docs only, no code).** Ratify the 6 generic systems (§1) as named **CoS platform capabilities** and the durable-draft machine as the reference workspace pattern. Zero risk; unblocks every future workspace to compose rather than fork.

**Phase 1 — Navigation on the keeper runtime (the one net-new capability).** Add a `navigate_to_workspace` tool to `model_interface`, resolving targets via the existing `resolve_route()`/`TeachingDestination`; emit a `navigation` field from `generate`; reuse the existing `renderNavigation()` client. Fire on pure nav intents (answer-in-place when Current Context suffices — Article II.4). **Then delete** `NAVIGATION_HINTS`. Certification: the existing 5-point intent-registration gate + a natural-conversation test ("I'd like to journal" → opens Journal; "what meds am I on?" → answers or opens Medications appropriately).

**Phase 2 — Generalize the durable draft.** Extract `WorkspaceDraftSession` from `JournalConversation` (transcript + written_body + generated_draft + state + generic `resulting_object`), with Journal as the first configured workspace (its `JournalEntry` target, prompt strings, and voice source injected). Migrate behind a flag; the Journal certification suite is the regression gate. This is the primitive Travel and every later workspace compose.

**Phase 3 — Eliminate the duplicates (§8).** Delete DOM scrapers; converge conversation runtimes onto `model_interface`; remove the superseded legacy injections. Gated on the runtime-consolidation track already in flight.

**Guardrails honored throughout:** no redesign of Journal or the CoS; no second assistant; no duplicate conversation system; no domain-specific AI engine; no new architecture where composition suffices; no Constitutional Review triggered. Reuse first, compose over duplicate, reduce architecture wherever possible.

---

## Appendix — evidence index (primary file:line anchors)

- Keeper runtime: `apps/ai/model_interface/service.py:120, 135-155, 211-250, 421-434, 627, 646-650, 671-672`; `apps/ai/cos_gateway/gateway.py:108`; `apps/ai/cos_gateway/envelope.py:34-61`
- Current Context: `templates/base.html:14-21`; `apps/core/current_context.py:41-65, 82-134, 146-160, 196-244, 247-305`; `apps/ai/cos_services/current_context.py:197-415`; `apps/health/page_summaries.py:24-53`
- Conversation State: `apps/ai/model_interface/conversation_state.py:28-32, 58, 90-101, 116, 159`
- Confirmation / action / audit: `apps/ai/model_interface/confirmation.py:20-98`; `apps/ai/cos_services/action_interface.py:60-197`; `apps/ai/cos_services/action_execution.py:16-105, 130-189`; `apps/ai/intent_service.py:1405`; `apps/ai/cos_services/audit.py:45-77`; `static/js/wlj-confirmation.js`
- Truth surfaces: `apps/core/truth/domain.py:25-65`; `apps/ai/cos_services/domain_entity.py:31-34, 185`; `apps/core/truth/discovery_suite.py:17-183`
- Journal: `apps/journal/models.py:317-399`; `apps/journal/services/journal_conversation.py:16-157, 160-313, 349-393`; `apps/journal/views.py:467-521, 605-693, 775-797`
- Navigation: `apps/help/models.py:529-611`; `apps/help/fixtures/teaching_destinations.json`; `apps/core/action_router.py:50-73, 181-306`; `apps/ai/views.py:1140-1153`; `apps/ai/personal_assistant.py:2546, 2749, 2857-2870`; `templates/components/chat_widget.html:2112-2140, 2983-2986`
- Provider seam: `apps/ai/services.py:169, 199, 733, 790`
- Legacy import: `apps/legacy/models.py:845-940`

---
---

# PART II — Is "navigation" the right abstraction? (follow-up investigation)

**Question posed:** Is *navigation* the thing the CoS should decide, or is it merely one implementation detail of a higher-level deterministic action — *"open/reveal this target"* — where WLJ decides whether to navigate, which page/tab/anchor, or that the target is already visible?

**Verdict: navigation is an implementation detail. The correct deterministic action is "reveal a target," where the target is a *semantic reference* (an object, a workspace, or a capability) that the CoS already holds — and WLJ owns the presentation resolution. This abstraction is not hypothetical: it already exists in three partial forms in the runtime. The work is to *unify and complete* it, which also lets us delete four duplicate maps and collapse three routers.** This supersedes Part II→Phase 1's "add a `navigate_to_workspace` tool": we should not build a navigation action at all — we should complete the reveal-a-target resolver, of which navigation is one output.

## 10. The three abstraction fragments that already exist

WLJ already separates *semantic target* from *presentation* in three places — but no single resolver unifies them, and each collapses to a bare URL too early.

1. **`capability` — the semantic action target (the most intent-centric layer).** `apps/core/execution/action_routing.py` — docstring `:1-34`: *"routing originates from the ACTION's identity, never displayed wording."* It derives a `capability` (`CAP_LOG_WEIGHT`, `CAP_OPEN_BIBLE_READING`, `:66-78`) metadata-first via `derive_capability` (`:216-262`), then `_CAPABILITY_URL[capability]` (`:83-97`) maps it to a page. The CoS's deterministic action `primary_action` is already a canonical-metadata dict (`source_type`, `source_id`, `activity_type`, `title`), passed through un-mutated by selectors (`apps/core/execution/selectors.py:20-28`). **But `resolve_action_destination(item)` (`action_routing.py:279-299`) returns only a bare URL string and discards the capability** — the separation terminates in a string.

2. **`ModuleDefinition` — the workspace as a first-class entity.** `apps/users/models.py:1720-1812`, self-described as *"THE single source of truth for all WLJ modules."* Carries `slug` (canonical key), `route_name` (home URL name, resolvable via `reverse()` — `:1799-1802`), `url_namespace`, and **`mapped_domain_keys`** (JSON bridge module→domain keys, e.g. `["health","medical"]` — `:1792-1796`). Fixture `apps/users/fixtures/module_definitions.json` populates it (`health→health:landing`, `journal→journal:home`…). "Open the Health workspace" = `ModuleDefinition(slug="health").route_name` → `reverse()`, **no URL literal**.

3. **Current Context `current_screen` — the presentation-state authority.** Every turn the envelope carries `current_screen = {location, focus}`: `location.{url, module, title}` from the real client `window.location.pathname` (`apps/ai/cos_services/current_context.py:186-194, 322-365`), and `focus.{ref, kind, title, content}` (`:218-226`). So *"is the target already on screen?"* is computable from truth that already exists. The one precedent that does URL-diff reasoning is the **navigation guard** (`current_context.py:254-260`): honor a remembered focus only when `remembered_url == cur_url`.

## 11. Answers to the seven questions

**Q1 — Is "workspace transition" the real deterministic action?** *Partly — it's one case of a broader action.* The real deterministic action is **"reveal a target,"** where a target is a semantic reference at one of three granularities: an **object** (`app.model:pk`), a **workspace** (`ModuleDefinition.slug`), or a **capability** (`CAP_*`). "Workspace transition" covers the workspace case ("I'd like to journal"); "show me today's weight point" is an object/capability case; "is my glucose ok — I'm looking at it" is a *no-op* case. So the abstraction is **target revelation**; workspace transition is one mode of its output.

**Q2 — Should the CoS choose a workspace, an object, a destination, or something else?** The CoS should choose a **target reference** — and it *already holds these*: object refs from `get_entity` (`ref = app.model:pk`, `apps/core/current_context.py:243`), workspace/domain keys (`DomainCapability.name`, `ModuleDefinition.slug`), and capabilities (`derive_capability`). The CoS should **never** choose a URL, tab, anchor, or "navigate vs stay." Those are presentation, which WLJ owns.

**Q3 — Can `TeachingDestination` already represent this?** *Partially, and it's the wrong home for the abstraction.* Its 190 rows are a good concept→leaf-page catalog (a valid *resolver input*), but it is URL-string-centric and keyed by a free-text `module` CharField (`apps/help/models.py:559-574`). The canonical identity of a workspace lives in **`ModuleDefinition`**, and of an object in its **ref**. Use `TeachingDestination` as one input to the resolver, not as the abstraction.

**Q4 — Can Current Context already support this?** *Yes — fully, on the current-state side.* `current_screen.location.url/module` + `current_screen.focus.ref` are deterministic every turn (§3). The "already-visible → no navigation" decision is computable **today** from existing truth; the guard at `current_context.py:254-260` proves the URL comparison is trivial. The gap is entirely on the *target → presentation* side.

**Q5 — Can the existing Action framework execute this?** *Yes.* A reveal is a read-only presentation directive travelling the same audited path as any tool result. The directive channel + client renderer already exist on the legacy runtime (`apps/ai/views.py:1140-1141`; `chat_widget.html:2132`); they need porting to the keeper runtime as a **presentation directive** (a peer field on `generate`'s return, `service.py:671-672`), not a bare `navigation` URL.

**Q6 — Would this reduce architecture rather than add it?** *Yes, substantially* (see §12). It collapses **four** duplicate home-URL maps and **three** routers' URL logic and one hardcoded hint map into **one** presentation resolver — while cleanly separating CoS intent from WLJ presentation.

**Q7 — Does this allow UI redesigns without changing CoS behavior?** *Yes — this is the decisive payoff.* Because the CoS emits **target references** (capability / object ref / workspace key) and never URLs/tabs/anchors, the entire UI — routes, tabs, page structure, which graph lives where — can be redesigned and only the WLJ presentation resolver (`ModuleDefinition.route_name`, `_CAPABILITY_URL`, ref→URL) updates. **CoS behavior is invariant under UI change.** This is exactly the principle "the CoS reasons about intent; WLJ reasons about presentation."

## 12. What's missing — the smallest deterministic abstraction to complete it

Only three small, concentrated pieces are unbuilt; every input already exists:

1. **One `PresentationResolver`** (the single new deterministic authority): `resolve(target_ref, current_screen) → PresentationDirective`. Inputs already deterministic. Output: `{mode: navigate | reveal_in_place | already_visible, url?, anchor?, tab?, ref?, label?}`. `already_visible` and `reveal_in_place` are the modes entirely absent today (no action router has any "already here" concept — only the *inbound* guard does).
2. **Uniform target → URL derivation**, feeding the resolver: workspace target → `ModuleDefinition.route_name` (exists); capability target → make `resolve_action_destination` return a struct instead of a string (`action_routing.py:279` — the capability is computed at `:295` and thrown away); object target → a contract-level ref→URL (today `get_absolute_url` is ad-hoc on ~15 models and absent from `NarratableMixin`); **summary-key → URL** reverse map (missing entirely — `_PAGE_SUMMARY_PROVIDERS` is key→fn only).
3. **One `domain_key → workspace home` hop** over `ModuleDefinition.mapped_domain_keys` (no such helper exists; the CoS's semantic keys like `nutrition` fold into module `health` only via this bridge).

## 13. Architecture ELIMINATED by this abstraction (net negative code)

- **Four duplicate module-home maps collapse to one** (`ModuleDefinition`): `apps/core/ai_orchestrator/url_resolver.py:86-101` `MODULE_URL_MAP`, `apps/core/action_router.py:147-153` `_MODULE_HOME`, `apps/core/context_processors.py:543-552` `CORRECT_ROUTES`. Drift already bit (migration `0058_fix_health_route_to_landing` reconciles `health:home` vs `health:landing`) — Article III.1 ("one deterministic authority") *argues for* this consolidation.
- **`NAVIGATION_HINTS`** (flat `action_type→path`, `personal_assistant.py:2749`) is deleted — subsumed by capability→presentation.
- **Three routers' URL logic converges on one resolver.** `core/action_router.py` (URL+label), the render-time `resolve_action_destination`, and `NAVIGATION_HINTS` all emit whole-page URLs independently; the resolver becomes the single producer of "where/how to reveal X."
- Confirms the Part I plan: **do not build a `navigate_to_workspace` tool.** Build the reveal resolver; navigation is one of its outputs.

## 14. Constitutional fit

Clean, and it *improves* compliance:
- **CoS emits intent (I.2 reasoning); WLJ resolves presentation deterministically (I.1/I.3).** The division the Constitution already mandates, now extended to presentation.
- **Article III.1 (one deterministic authority per domain)** is *strengthened* — four home maps become one.
- Reveal is a **deterministic, audited action (I.7)**; targets are deterministic references, not model-invented URLs.
- **No new architecture, no Constitutional Review** — this is consolidation of existing systems (`ModuleDefinition`, `capability`, Current Context) behind one resolver.

## 15. Recommended architecture (naming + shape)

- **The CoS deterministic action = `reveal` (open/reveal a target).** The model chooses a **target reference** only: `{object: "app.model:pk"}` | `{workspace: "<slug>"}` | `{capability: "CAP_*"}`. It never names a page, tab, route, or anchor.
- **WLJ owns a single `PresentationResolver`** that diffs the target against `current_screen` and returns a **PresentationDirective** (`navigate` / `reveal_in_place` / `already_visible`, with url/anchor/tab). It is request-path-safe (reads catalogs + current context; no heavy compute) and audited like any tool.
- **Existing systems it composes (build almost nothing new):** `ModuleDefinition` (workspace home + domain bridge), `capability`/`action_routing.py` (semantic action targets), Current Context `current_screen` (presentation state + the already-visible diff), `TeachingDestination` (named-destination input), the existing directive channel + `renderNavigation` client (ported to the keeper runtime).

**Revised phase order (replaces Part I §9 Phase 1):**
- **Phase 1a — Consolidate presentation truth:** one `domain_key → ModuleDefinition → route_name` resolver; retire the four duplicate home maps. Pure elimination, no behavior change.
- **Phase 1b — `PresentationResolver` + `reveal` action on the keeper runtime:** capability/workspace/object target → directive; `already_visible`/`reveal_in_place` modes; port the directive channel; delete `NAVIGATION_HINTS`. Certification: natural conversation ("I'd like to journal" → reveal Journal workspace; "is my glucose ok" *while on the glucose page* → `already_visible`, answer in place).
- **Phase 1c (optional):** widen `_CAPABILITY_URL` to `(url, anchor)` and add the `summary-key → URL` reverse map so a target can reveal a specific graph, not just a whole page.

## Appendix II — evidence anchors (Part II)

- Intent-centric router / capability: `apps/core/execution/action_routing.py:1-34, 66-97, 216-299`; `apps/core/execution/selectors.py:20-28`; `apps/ai/cos_services/tool_registry.py:107-124`; `apps/ai/chatgpt_cos/reasoning/stages.py:124-138`
- Workspace entity: `apps/users/models.py:1720-1812`; `apps/users/fixtures/module_definitions.json`; `apps/core/domain_registry/descriptors.py:50-91`; `apps/core/truth/semantics.py:1-242`
- Current Context presentation-state: `apps/ai/cos_services/current_context.py:186-194, 218-226, 254-260, 322-365, 388`; `apps/ai/model_interface/service.py:135-136, 212-250`; `templates/components/chat_widget.html:1178-1239`
- Duplicate home maps (to eliminate): `apps/core/ai_orchestrator/url_resolver.py:86-101`; `apps/core/action_router.py:53-82, 147-153, 216-303`; `apps/core/context_processors.py:543-552`
- Hint map + directive channel: `apps/ai/personal_assistant.py:2749-2877`; `apps/ai/views.py:1140-1141`; `templates/components/chat_widget.html:2132-2140`

---
---

# PART III — The presentation abstraction & the complete elimination audit

**Question posed:** Is *"Presentation Resolver"* the right abstraction, or is there an even simpler architectural model hiding underneath it? Produce the complete presentation dependency graph, every duplicate, every elimination opportunity, the smallest deterministic model, authority boundaries, constitutional basis, risks, and migration.

**The headline answer — there IS something simpler, and it is a concept *reduction*, not a new subsystem:**

> **There is no "Presentation" subsystem to add. There is the Current Context authority (Article II) — completed in the outbound direction. And the presentation *verb* does not belong to WLJ at all; it belongs to the client.**

"Presentation Resolver" is directionally right but it smuggles in two mistakes: (1) it names a *new authority* when the correct move adds a *direction* to an authority that already exists; (2) it implies WLJ chooses the presentation verb (navigate/scroll/modal), which would break every screenless or non-web client. The simpler model splits cleanly into three parts, each landing on an existing layer:

| Part | What it is | Universal? | Owner | Layer |
|---|---|---|---|---|
| **Target** | a *desired Current Context*, in the existing ref grammar `{object, summary}` (+ alias namespaces) | yes | the model **chooses** it | Reasoning (I.2) |
| **Relation** | `normalized_target_ref` vs `current_ref` → `same` (already-visible) / `different` / `child` | yes | **WLJ** computes it | Truth (I.1/I.3) — *Current Context, outbound* |
| **Verb** | navigate · scroll · select_tab · highlight · open_modal · speak · glance · spatial-window | **no — client-specific** | the **client adapter** chooses it | Experience (V.3) |

The only genuinely-new deterministic code is **Part 2** — and it is tiny: normalize a target to a ref (over catalogs that already exist) and compare it to the current context ref. That is **Current Context made bidirectional**: it adds *zero new architectural concepts* (the reference grammar, ownership model, freshness envelope, and request-path-safety rules already defined for Current Context apply unchanged), while it lets us *delete* three competing resolvers, four duplicate home maps, and the "navigation" concept itself. This is why it beats "Presentation Resolver": that phrase adds a noun; *bidirectional Current Context + client verb* removes several.

`already_visible` is the one mode WLJ legitimately owns — because it is a **relation** (a truth comparison `target==current`), not a verb. Every other mode in the original sketch (navigate/scroll/tab/modal) is a **verb** and belongs to the client. That is the exact cut line.

## 16. The complete presentation dependency graph (audited)

**34 presentation-decision sites across 12 files; ~22 duplicative; 3 competing central resolvers + 1 ad-hoc path, none aware of each other.** Condensed graph (full inventory in Appendix III):

```
INPUT CATALOGS (keep as data; everything normalizes through these)
  TeachingDestination (DB, 190 rows)            apps/help/models.py:529        [named-destination alias]
  _CAPABILITY_URL (CAP_* → url)                 apps/core/execution/action_routing.py:83   [capability alias]
  ModuleDefinition.route_name (module → home)   apps/users/models.py:1799      [workspace identity — AUTHORITATIVE]
  get_absolute_url (~25 models, object → detail) [object leaf — AUTHORITATIVE, per-model]
  Current Context grammar {object, summary}     apps/core/current_context.py:68,81  [the terminal ref space]

THREE COMPETING CENTRAL RESOLVERS (collapse to one)
  A  core/action_router.resolve_route            → Executive Briefing render (executive_summary.py:710,1247)
  B  core/execution/action_routing.resolve_action_destination → Today/Focus dashboard render (today_execution.py:328)
  C  core/ai_orchestrator/url_resolver → action_contracts.build_action_contract → orchestrator.navigation  → CoS reply render
  +  ad-hoc: personal_assistant.NAVIGATION_HINTS → _get_navigation_hint → chat reply render

CLIENT (collapse 4 copy-pasted branch blocks × 2 divergent surfaces → one applyPresentation adapter)
  chat_widget.html / assistant_panel.html: renderNavigation(link) · renderOptions · renderConfirmation
  bespoke verbs: scroll=?beth_msg param · select_tab=simulated .click() · highlight=inline style · modal=showFrictionGate
  inbound (keep): base.html <meta wlj-context> → focus_ref  (the symmetric report channel)
```

## 17. All duplicate systems (equivalence classes)

| Class | What it maps | Duplicate copies | Canonical survivor |
|---|---|---|---|
| **1** | module → home URL | `MODULE_URL_MAP` · `_MODULE_HOME` · `CORRECT_ROUTES` · `MODULE_URLS` · `ModuleDefinition.route_name` (**5×, live drift**: `/health/` vs `health:landing` vs `health:home→/health/physical/`) | **`ModuleDefinition.route_name`** |
| **2** | intent/action_type → workflow URL | `INTENT_URL_MAP` · `FOLLOW_UP_MAP` · `NAVIGATION_HINTS` · `_SUBJECT_FALLBACK` (**4×, live drift**: `/health/vitals/` vs `/health/heart-rate/`) | **`TeachingDestination`** (+ `_CAPABILITY_URL`) |
| **3** | keyword/NL → destination scorer | `_best_destination` · `TeachingToolService._score_destination` (**2× identical**) | **one scorer on `TeachingDestination`** |
| **4** | text → subject/capability keyword bridge | `_SUBJECT_RULES` · `_KEYWORD_BRIDGE` | **one keyword taxonomy** |
| **5** | "the task I made" → `/life/tasks/` | 3 hardcoded literals (`personal_assistant`, `action_handlers`) | **`Task.get_absolute_url()`** |
| **6** | domain binary action → URL | `_binary_map` ×2 | folds into **`_CAPABILITY_URL`** |
| **Resolvers** | "where does this go?" | resolvers A, B, C + NAVIGATION_HINTS (**4 front doors**) | **one outbound-context resolver** |
| **Client** | assistant directive → DOM | 4 copy-pasted branch blocks × 2 surfaces | **one `applyPresentation()`** |

**Live drift is already documented in the tree** (migration `0058_fix_health_route_to_landing`) — the duplication is not theoretical; it has already produced wrong URLs.

## 18. What happens to each system under one bidirectional Current Context

- **DISAPPEAR (deleted):** `NAVIGATION_HINTS` + `_get_navigation_hint`; four of five home maps (`MODULE_URL_MAP`, `_MODULE_HOME`, `CORRECT_ROUTES`, `MODULE_URLS`); `_best_destination` (dup scorer); the 3 hardcoded `task_url` literals; `_binary_map`×2; `INTENT_URL_MAP`/`FOLLOW_UP_MAP`/`_SUBJECT_FALLBACK` (fold into the registry). The **word "navigation" leaves the CoS vocabulary entirely.**
- **SHRINK / MERGE:** resolvers A + B + C collapse into **one** outbound-context resolver; `_SUBJECT_RULES` + `_KEYWORD_BRIDGE` → one keyword taxonomy; `executive_summary` route-attach consumes the one resolver.
- **BECOME ADAPTERS / INPUT CATALOGS:** `TeachingDestination` (named-destination alias), `_CAPABILITY_URL` (capability alias) → inputs the resolver normalizes through, not resolvers themselves. Client `renderNavigation`/`renderOptions`/`renderConfirmation` + bespoke scroll/tab/highlight/modal → one shared `applyPresentation(directive)` adapter per client.
- **REMAIN AUTHORITATIVE (the leaves the resolver delegates to):** `ModuleDefinition.route_name` (workspace home), `get_absolute_url` (object→detail, per-model), Current Context inbound (`<meta wlj-context>`→`focus_ref`) as the report half of the now-bidirectional authority, the toggle/complete POST endpoints (they are *actions*, not presentation — `complete_url` stays a separate field), and `safe_url`/`url_or` (template reverse-safety primitive).

**Concept count: three resolver concepts + "navigation hints" + "module URL maps" (≈5 architectural nouns) → one direction added to one existing authority (Current Context) + one existing client-adapter pattern gaining modes. Net new nouns: ~0. Net deleted nouns: ~4.**

## 19. The smallest deterministic presentation model

- **CoS emits a Target only** — a reference in the existing grammar: `object:app.model:pk` | `summary:<key>` | (alias) `workspace:<slug>` | `capability:<CAP>`. Never a URL, tab, anchor, or verb.
- **WLJ (Current Context, outbound) returns a Context Target Directive** — pure truth: `{ ref (normalized to object|summary), workspace, url, anchor?, relation: same|different|child }`. `relation==same` ⇒ `already_visible`. Request-path-safe (reads catalogs + current context), audited like any tool.
- **The client adapter chooses the verb** — `applyPresentation(directive)` maps `{ref, relation, url}` + its own capabilities → navigate / scroll / select_tab / highlight / no-op (web); speak / glance / spatial-window (future clients).
- **Terminal taxonomy = 2** (`object`, `summary`). Workspace, capability, and named-destination are **alias namespaces** that normalize into those two. No third terminal type exists or is needed.
- **Explicit boundaries (prevent scope creep):** *actions* that change state (log weight, play devotional audio) are the **Action pipeline**, not presentation — a capability may *resolve to* a surface to reveal, but "do the thing" stays on the audited action path. Pure client gestures with no semantic target ("go back") are **verb-only, client-owned** — they never enter the target grammar.

## 20. Authority boundaries

- **Model (Reasoning, I.2):** chooses the *target* (intent). Never a route/tab/verb.
- **WLJ / Current Context (Truth, I.1/I.3; Authority, Article II — now bidirectional):** owns the *reference grammar*, normalizes aliases → ref, owns the *current* screen (inbound) and the *target↔current relation* (outbound). One deterministic producer (III.1).
- **WLJ / Action (I.7):** `reveal` is an audited action; state-changing actions stay on the existing safe path.
- **Client adapter (Experience, V.3):** owns the *verb*. One `applyPresentation()` per client; shared across the two web surfaces to end their drift.
- **Input catalogs (data):** `ModuleDefinition`, `TeachingDestination`, `_CAPABILITY_URL`, `get_absolute_url` — authoritative *leaves*, consulted by the one resolver, never competing resolvers.

## 21. Why this is constitutionally correct

- **Article II (Current Context Authority) — extended, not bypassed.** The outbound direction reuses the exact `{object, summary}` grammar (II.2/II.3); targets are **server-normalized, never client/model-invented URLs** (II.1). Strengthened.
- **Article III.1 (one deterministic authority per domain) — this is the biggest win.** Today "where does this go?" has *four* producers with proven drift — a latent III.1 violation. Collapsing to one resolver is precisely what III.1 demands.
- **Article I — clean division.** Model reasons the target (I.2); WLJ owns deterministic target/relation truth (I.1, I.3); reveal is audited (I.7); no reasoning engine added (I.2, IV.2); catalogs are *exposed* behind one resolver, not a new bespoke capability (IV.4).
- **Article V.3 (layered) — honored exactly:** target=Reasoning, relation=Truth, verb=Experience.
- **Verdict:** **no Constitutional Review required** — it forbids nothing the Constitution allows and consolidates toward the Articles. It is ordinary (large) in-Articles work.

## 22. Risks

1. **Coverage dependency (the main one).** Reveal precision is bounded by *Current Context declaration coverage*. Today capability/log/form pages, both dashboards, workspace homes (e.g. `JournalHomeView`), and even `journal.EntryDetailView` declare **no** context (evidence: Part II §11 / Appendix). Until a surface declares a ref, a fine target degrades to the workspace home and `already_visible` can't fire. *Mitigation:* reveal degrades gracefully; ride the existing Current Context rollout backlog; land the **dashboard day-summary** provider first (highest-value, currently missing entirely).
2. **`get_absolute_url` is non-uniform** (~25 ad-hoc, absent from `NarratableMixin`). Object targets need a contract-level ref→URL. *Mitigation:* add it to the Narratable contract; until then, object reveal falls back to workspace home.
3. **Load-bearing nav consolidation.** The home maps feed *every page's* nav chrome (`context_processors`). *Mitigation:* Phase A is report-only/parity-tested; where drift exists (the `0058` class), the parity test must **deliberately choose the correct URL**, not codify a bug.
4. **The verb-in-WLJ anti-pattern.** Implementing the original literal sketch (WLJ returns navigate/scroll/modal) would break Voice/Watch/VisionOS. *Mitigation:* enforce the target+relation / verb split — only `already_visible` (a relation) is WLJ's.
5. **Two divergent client surfaces already drift** (retrofitted once for parity). *Mitigation:* one *shared* `applyPresentation()` module + a contract test, or they re-drift.
6. **New cross-client directive schema** to version (web/iOS/watch). Small, but a real contract surface.
7. **Blast radius (V.2).** 22 sites is large — never big-bang. Sequence pure-elimination → new direction → coverage; log any residual duplicate that can't be safely removed.

## 23. Future-client analysis (does it get stronger or weaker?)

**Stronger — decisively — *because* the verb is not in WLJ.** Evidence: no native bridge exists today (client audit), so every future client is a clean adapter consuming the same `{target, relation, url}`; and the web verbs are *already* bespoke and client-specific (navigate=link, scroll=`?beth_msg`, tab=simulated `.click()`), proving the verb was never universal.

- **Voice-only (no screen):** target+relation with `url` ignored → adapter *speaks* the answer; "reveal weight history" becomes "here's your weight history…". Reveal degrades to describe — because the CoS never said "navigate."
- **Apple Watch / glance:** adapter shows a complication or "open on iPhone." CoS unchanged.
- **VisionOS / Desktop:** adapter opens a spatial window / side panel instead of navigating. CoS unchanged.
- **Where it breaks:** only if the verb is baked into WLJ (Risk 4). Avoid that and the CoS operates *identically* while each client chooses its own presentation — which is exactly the stated goal ("the CoS reasons about intent; WLJ reasons about presentation" — refined to: *WLJ reasons about the target/relation truth; the client renders the verb*).

## 24. Migration strategy (phased; pure-elimination first)

- **Phase A — Consolidate the maps (pure elimination; NO product-behavior change; NO CoS change).** Collapse Classes 1–6 behind the canonical leaves (`ModuleDefinition`, `TeachingDestination`, `_CAPABILITY_URL`, `get_absolute_url`); merge resolvers A/B/C into one internal resolver; delete `NAVIGATION_HINTS` and the four duplicate home maps. Parity tests resolve the existing drift deliberately. *Removes ~22 sites and 3-of-4 resolver front doors; huge concept reduction, zero UX change.*
- **Phase B — Make Current Context bidirectional (the one new deterministic bit).** Add outbound normalization (target → ref+url+anchor) + relation computation (→ `already_visible`); expose as the `reveal` action's resolution on the keeper runtime. Audited, request-path-safe. Server emits `{target, relation, url}`; no client change yet.
- **Phase C — One client adapter.** Replace the 4 copy-pasted branch blocks + bespoke scroll/tab/highlight/modal with one shared `applyPresentation(directive)` used by both web surfaces (ends their drift). Web verbs: navigate/scroll/select_tab/highlight/`already_visible`=no-op.
- **Phase D — Coverage.** Declare Current Context on the highest-value blind surfaces, in order: dashboard day-summary → journal entry detail → medication detail → workspace homes → log/form pages. Each declaration upgrades a coarse workspace reveal into a precise object/summary reveal and enables `already_visible`.
- **Phase E — New clients.** iOS/native/watch/visionOS each implement their own `applyPresentation` adapter against the *same* `{target, relation, url}` contract. CoS and WLJ unchanged.

**Supersedes** Part II's Phase 1a/1b framing: the deterministic action is not `navigate_to_workspace` and not even a standalone "Presentation Resolver" — it is **`reveal(target)` resolved by a bidirectional Current Context**, with the verb at the client.

## Appendix III — full server inventory (34 sites)

Canonical leaves: `ModuleDefinition.route_name` (`apps/users/models.py:1799`); `TeachingDestination` (`apps/help/models.py:529`, fixture 190 rows); `_CAPABILITY_URL` (`apps/core/execution/action_routing.py:83`); `get_absolute_url` (~25 models: `finance:207,560,853,1254,1855`; `journal:206`; `life:143,400,771,858,970,1043,1355,1808`; `meals:307,1494`; `medical:290,361,419,662`; `notes:179`; `purpose:174,363,845,911,1181`); Current Context grammar (`apps/core/current_context.py:68,81`).
Duplicate/competing resolvers: `apps/core/ai_orchestrator/url_resolver.py:27,86,109,184,214`; `apps/core/ai_orchestrator/action_contracts.py:114,152`; `apps/core/action_router.py:90,130,147,181,216,252,306`; `apps/core/execution/action_routing.py:106-262,265,279`; `apps/ai/personal_assistant.py:2749,2857,3138,3260`; `apps/ai/action_handlers.py:3777,3807`; `apps/core/context_processors.py:543,484`; `apps/core/views.py:421`; `apps/core/decision_engine/action_prioritizer.py:493,1015`; `apps/core/execution/today_execution.py:220,321,437`; `apps/core/cos_briefing/executive_summary.py:710,802,849,1247`; `apps/help/services.py:608,640,725`.
NOT presentation (excluded despite names): `apps/core/ai_orchestrator/action_router.py` (`route_action` = parameter/tone enrichment, no URL); `apps/ai/deterministic_router.py` (`_DATA_ROUTES` = message→handler); `apps/health/services/current_health.py` (`_ROUTES` = metric→query).
Client: `templates/components/chat_widget.html:2041-2160, 2980-2986, 3079-3086, 3234-3237, 3340-3348`; `templates/components/assistant_panel.html:443-456, 1190-1192, 1924-1926, 1937-1955`; `static/js/wlj-confirmation.js`; `templates/base.html:14-22` (inbound `<meta wlj-context>`).

---
---

# PART IV — Phase A implementation results (increment 1)

**Scope guard:** Phase A is **pure elimination** — no `reveal(target)`, no outbound/bidirectional Current Context, no client presentation adapter, no new CoS behavior, no schema change. This increment corrects the one **proven** module-home drift and locks the canonical authority; the broader multi-file resolver merge is sequenced behind operator production validation (below).

## Pre-write verification against the current tree (2026-07-21)

The Part III inventory was **re-verified against the live tree, not trusted blindly** — and it had already moved under concurrent sessions:
- **Confirmed:** `action_router._MODULE_HOME`, `url_resolver.MODULE_URL_MAP`, `ModuleDefinition.route_name`, `context_processors.CORRECT_ROUTES`, `core/views.MODULE_URLS`, the three central resolvers.
- **Drifted from the audit (caught):** the second hardcoded `/life/tasks/` literal at `action_handlers.py:3807` **no longer exists** (a concurrent session removed it); only `:3777` remains.
- **Corrected finding:** `MODULE_URL_MAP` is **not** a pure duplicate of `ModuleDefinition` — it carries extra keys (`fitness`, `medical`, `calendar`, `dashboard`, `assistant`, `settings`, `billing`, `transformation`) that are sub-modules/system pages. It is a **distinct-responsibility adapter**, retained, not deleted. (`meals` is absent from it — a pre-existing coverage gap, logged, not drift.)

## The Health inconsistency — deliberately resolved (not naming preference)

Traced to real routes: `health:landing` → `HealthLandingView` at `""` = **`/health/`** (workspace home); `health:home` → `HealthHomeView` at `"physical/"` = **`/health/physical/`** (a sub-page). Canonical workspace home = **`health:landing` (`/health/`)**, corroborated by four independent authorities: `ModuleDefinition.route_name='health:landing'` (fixture), `CORRECT_ROUTES['health']='health:landing'` (with the standing comment *"Landing page at /health/, not /health/physical/"*), `MODULE_URL_MAP['health']='/health/'`, and migration `0058_fix_health_route_to_landing`. **Parity proven locally:** `reverse()` of every `ModuleDefinition.route_name` equals its `MODULE_URL_MAP` URL for all shared modules. The sole outlier was `action_router._MODULE_HOME['health']='health:home'` — accidental drift.

## Changed this increment

1. **`apps/core/action_router.py`** — `_MODULE_HOME['health']`: `health:home` → **`health:landing`** (drift correction toward the canonical authority; commented in place).
2. **`apps/core/tests/test_action_router.py`** — `test_module_home_fallback_when_subject_unknown` asserted the drifted `/health/physical/`; **deliberately corrected** to `/health/` with rationale (the test had codified the bug — "not silent cleanup").
3. **`apps/core/tests/test_module_home_authority.py`** (new) — contract locking the canonical authority: Health home = `/health/`; no module-home resolves to the `/health/physical/` sub-page; every module-home route reverses; and the two CoS-facing home maps (`_MODULE_HOME` ↔ `MODULE_URL_MAP`) may never silently diverge.

## Verification (results, not intentions)

- `apps.core.tests.test_module_home_authority` — **5/5 OK**.
- `apps.core.tests.test_action_router` + `apps.core.ai_orchestrator.tests.test_url_resolver` + module-home authority — **50/50 OK**.
- `apps.core.tests.test_constitution_contract` + `apps.core.tests.test_request_path_safety_contract` — **13/13 OK**.
- `makemigrations --check --dry-run` — **No changes detected**. `manage.py check` — clean.
- **Runtime path validated** via Django shell: `resolve_module_url` → `/health/`, `/journal/`, `/faith/`, `/finance/` (legacy `action_contracts` consumer preserved); module-home fallback → `/health/`; health-weight subject → `/health/physical/weight/`; legacy `life:task_list` task subject → `/life/tasks/`; invariant `_MODULE_HOME['health']==health:landing` holds.

## Explicitly RETAINED (distinct responsibility or defensive adapter — documented, not "missed")

- `MODULE_URL_MAP` (super-set of module + sub-module + system pages) — CoS-awareness adapter.
- `CORRECT_ROUTES` / `MODULE_URLS` — defensive bad-DB fallbacks that already use `ModuleDefinition.route_name` as primary (MoreView's comment: *"avoids any DB/route_name issues"*). Retained as clearly-scoped adapters per the desired-shape rule.
- `TeachingDestination`, `_CAPABILITY_URL`, capability metadata — semantic input catalogs; kept (they own distinct truth and feed the future target model).
- `NAVIGATION_HINTS` and the legacy `PersonalAssistant` navigation path — **not touched**: they run on the legacy runtime whose retirement is a separate gated track; deleting them needs keeper/legacy consolidation + production validation.

## DEFERRED to a later increment (with reason)

The **three-central-resolver merge** (`action_router` + `execution/action_routing` + `ai_orchestrator/url_resolver` → one internal resolver), **`NAVIGATION_HINTS` removal**, and the **duplicate-scorer/keyword-bridge dedup** are behavior-touching across user-facing CoS/executive/nav surfaces. Per the milestone's own completion gate ("runtime validation proves behavior preservation"), those require **production behavior validation that only the operator (Danny) can perform** — WLJ sessions have no prod access — and a clean concurrency window. They are sequenced next, each as its own parity-tested increment. This is a bounded, honest first cut (V.2 blast-radius discipline), not the whole of Phase A.

---
---

# PART V — Phase A.5: Current Context Certification (increment 1)

**Why this milestone:** the Part III/IV work proved the real blocker to bidirectional Current Context is **Current Context coverage** — many workspaces don't declare deterministic context, so a future `reveal(target)` would have nothing precise to target and `already_visible` could rarely fire. This milestone **strengthens the deterministic foundation only** — no `reveal`, no outbound/Desired Context, no client adapter, no CoS/routing/nav/presentation change (Article II only).

## The correcting structural finding

`UserOwnedModel(NarratableMixin,…)` (`apps/core/models.py:183`) makes **every `UserOwnedModel` Narratable**, and `base.html:18-21` **auto-emits `object.context_ref` for any `DetailView` of one** — zero per-view code. So **object-detail pages are largely auto-certified already** (an earlier trace's claim that journal entries "aren't targets" was wrong — `EntryDetailView` is a `DetailView` of a `UserOwnedModel` and auto-declares). The real gaps concentrate in **(a) overview/summary pages** (need a `@register_page_summary` provider) and **(b) object pages built as `TemplateView`/`View`** (no `object` in context → need `CurrentContextMixin`).

## Certification matrix (as-built inventory; full per-page tables in the session investigation)

| Class | Meaning | Count (approx.) | Examples |
|---|---|---|---|
| **CERTIFIED** | declares correct CC | large | All `DetailView`-of-`UserOwnedModel` object pages (journal entry, goals, projects, habits, reflections, recipes, finance accounts/txns/goals, faith prayer/milestone/study-note, legacy person/place/milestone/media, note, people person); registered summaries `health.weight/nutrition/body_intelligence`, `faith.home/prayers/reading_plans`, `meals.leftovers`, `artifacts.library/detail`; `WorkoutDetailView` (`CurrentContextMixin`), Purpose home/goal-list (`CurrentContextMixin`) |
| **PARTIAL** | auto object identity but thin/unexposed numeric truth | small | Medical `ResultDetailView`/`PanelDetailView` (auto identity, but lab value/range/flag not in `get_context_summary`); `RecipeIntelligenceDetailView`, `UserReadingPlan` (thin) |
| **MISSING — overview** | overview page, no `page_summary_key` | **many (the real gap)** | **all dashboards** (`dashboard_v2`=`/dashboard/`, `v3`), health landing/home + sleep/hydration/steps/glucose/BP/heart-rate/fasting/fitness/medications overviews, meals dashboard/pantry/plan, **journal home** ✅(now), legacy hearth/library, finance dashboard, life home/tasks/calendar, purpose reflections/habits lists, capture inbox, notes list, relationships lists, sports/brain hubs |
| **MISSING — object (non-DetailView)** | object page as `TemplateView`/`View` | small | **medication `IntakeDetailView`** ✅(now), **legacy story `EditorView`** ✅(now), relationships `PersonDetailView` (non-`UserOwnedModel`), capture `CaptureDetailView`, medical `TestTrendView` |
| **NO CC (correct)** | transient action / reference data | large | all create/update/delete/toggle/log/OAuth/import/status endpoints; WriteTogether/Talk-It-Through conversational surfaces; Bible-API proxies; reference catalogs |
| **N/A** | app not registered | — | **Travel** (no `apps/travel/`, not in `INSTALLED_APPS`) |

## Implemented this increment (highest-value, request-path-safe, zero CoS-behavior change)

1. **`journal.home` OVERVIEW summary** — new shared source `apps/journal/services/journal_home_summary.py :: build_journal_home_summary` (cheap counts + streak; facts only); provider `apps/journal/page_summaries.py` (`@register_page_summary("journal.home")`); self-registered via `JournalConfig.ready`; `JournalHomeView` set to `PageSummaryMixin` + `page_summary_key="journal.home"` and its `stats` now read the **same** builder (one source feeds both — no page-vs-assistant drift).
2. **`health.IntakeDetailView`** (medication detail) — added `CurrentContextMixin` + memoized `_get_intake()` + `get_current_context_object()` (mirrors the certified `WorkoutDetailView`). `Intake` is a `UserOwnedModel`; the page now declares `health.intake:pk`.
3. **`legacy.EditorView`** (story editor) — added `CurrentContextMixin` + memoized `_get_memory()` + `get_current_context_object()`; declares `legacy.memory:pk`, and emits **no** context for a brand-new story (no pk) — the `None` case is guarded by the mixin.

**Chosen for safety:** all three are pure exposure of already-fetched truth. The medication/story pages add **zero request-path compute** (the object is already fetched; CoS resolution is a single cheap object read). The `journal.home` provider is request-path-safe (indexed counts, no heavy builder, no LLM).

## Runtime evidence (results, not intentions)

New contract `apps/core/tests/test_current_context_certification.py` — **5/5 OK**, proving each declaration resolves on the actual CoS path:
- `build_journal_home_summary` returns `total=2`; the registered `journal.home` provider composes `"Total entries: 2"` from the same source; empty-state deterministic.
- `IntakeDetailView.get_current_context_object()` returns the `Intake`, and `resolve_current_context(user, intake.context_ref())` resolves it (the assistant-side path).
- `EditorView.get_current_context_object()` returns the `Memory` and resolves; a new story (no pk) returns `None` (no context emitted).

Regression + contracts: **journal suite 190/190 OK**; `test_request_path_safety_contract` + `test_constitution_contract` **13/13 OK**; `makemigrations --check` **No changes**; `manage.py check` clean; `journal.home` confirmed self-registered at app-ready (10 providers total).

## Remaining gaps (deferred, prioritized) and readiness

**Next-highest value (documented for the follow-on increment):**
- **`summary:dashboard.day`** — the #1 overview gap, BUT `current_action()` falls through to `build_execution_state()` (heavy) when no state is passed; a provider would run heavy compute on the **chat request path** — a request-path-safety violation. **Prerequisite: a cached/snapshot execution state** (read with `allow_rebuild=False`) before this can ship. Deliberately deferred, not skipped.
- **Overview summaries with existing cheap-ish truth**: health landing/home (`DailyHealthSummaryBuilder`), finance dashboard (`CurrentFinance`/`FinanceDomainTruth`), meals dashboard, legacy hearth/library, capture inbox — each needs a `build_*_summary` extraction + request-path-safety verification per page.
- **Object (non-DetailView)**: relationships `PersonDetailView` (route through the already-built canonical `people.Person` mirror — has creation side-effects, needs care), capture `CaptureDetailView` (`CaptureEntry` is not `UserOwnedModel`), medical `Result/Panel` `CONTEXT_FIELDS` enrichment.
- **Bulk win**: health metric dashboards share `HealthMetricDashboardMixin` — one `get_page_summary_key` hook could certify ~10 pages at once.

**Readiness for bidirectional Current Context:** **Not yet.** This increment proves the pattern and closes three high-value gaps, but the dashboard day-summary (the single most-used surface) and the domain overview summaries remain. Bidirectional Current Context should begin only after the overview coverage — dashboard day-summary first (gated on a cached execution state) — is in place, so `reveal(target)` and `already_visible` have precise deterministic context to operate on across the workspaces a user actually sits in.

---
---

# PART VI — Dashboard Day Summary Certification (Truth milestone)

**Why:** the Part V blocker. The Dashboard is the single most-used workspace but had **no** Current Context, and the naive source (`current_action`→`build_execution_state`) is too heavy for request-path Current Context resolution. This milestone certifies a deterministic, **request-path-safe** Dashboard Day Summary — a Truth milestone, not a CoS one.

## 1. Investigation findings (the 7 questions)

1. **What should it contain?** Facts-only projection of today's execution: counts (total / completed / remaining / overdue / still-to-come), completed-tasks, a by-type breakdown, and the next *scheduled* (not prioritized) item. No verdicts, no prose.
2. **Which already exists as deterministic truth?** All of it — the execution contract (`build_today_execution` → `{items, summaries}`) already carries per-item `completed_today`, `time_status`/`status`, `scheduled_time`, `source_type`, and `summaries.tasks_completed_today`.
3. **Which producer owns it?** `apps/core/execution/today_execution.py :: build_today_execution` — the single execution-contract authority (III.1/III.2). The heavy `build_execution_state` (prioritization/phase) sits *on top of* it.
4. **Which is already cached?** The execution contract **is** an SAE module: `MODULE_BUILDERS["execution"] = _build_execution_state` → `build_today_execution` (`apps/core/ai_state/state_builder.py:6058-6103`), read via `get_module_state(user, "execution", allow_rebuild=False)` (`state_engine.py:74`).
5. **Which requires heavy compute?** `build_execution_state` (prioritized buckets, timing, `execution_phase`, at-risk, blocked-dependents) — uncached; the envelope calls it live *in the worker*. Excluded from this summary.
6. **Which can run on the request path?** The **cached SAE read** (`allow_rebuild=False`) — a single dict read, no queries on miss. Nothing else.
7. **Which must first become cached?** **Nothing new** — the SAE `execution` snapshot already provides the substrate. `execution_phase`/prioritized "do-now" are intentionally *out of scope* (they'd require the heavy builder); they can be added later only if cached.

## 2. Dashboard Summary Contract (facts only)

`{ status: "ready"|"pending", total, completed, remaining, overdue, upcoming, tasks_completed_today, by_type:{source_type:count}, next_item:{title,time}|None }`. `next_item` is the *earliest not-completed scheduled* item — explicitly **not** a prioritized "what to do now" (that stays with the single execution decision authority). WLJ exposes numbers/titles; the model interprets.

## 3. Shared builder design

`apps/core/execution/dashboard_day_summary.py :: build_dashboard_day_summary(user)` — the ONE source. Reads only the SAE snapshot; projects the cached contract into the contract above; never raises. Consumers (all read this one builder — no parallel implementation):
- `dashboard.day` page-summary provider (`apps/dashboard_v2/page_summaries.py`, `@register_page_summary`, self-registered via `DashboardV2Config.ready`).
- `DashboardV2View` **and** `DashboardV3View` — `PageSummaryMixin` + `page_summary_key="dashboard.day"`, and `context["day_summary"] = build_dashboard_day_summary(user)` (reads the **cached** builder, matching the provider exactly — so the page's summary and the assistant's summary are identical, not the page's live contract).

## 4. Cache architecture (reused, not invented)

No new cache. Reuses the SAE `execution` snapshot: **ownership** = SAE (`UserState.state_data["execution"]`); **producer** = `build_today_execution`; **refresh** = SAE background cycle + incremental `state_updater`; **invalidation** = task/routine writes drop `wlj:user_state:<id>:execution` (e.g. `apps/life/services/routine_helpers.py:973`); **dependencies** = execution domains; **runtime cost** = one cached dict read. **Pending** contract: on a cold snapshot the builder returns `status="pending"` and the provider says *"being prepared"* — it **never** rebuilds on the request path (the CLAUDE.md rule verbatim).

## 5. Runtime validation (same truth at every step)

Injected a known cached contract (3 items: 1 completed, 1 overdue, 1 upcoming med) into `UserState.state_data["execution"]`, then observed the identical numbers across the chain:
`build_dashboard_day_summary` → `{total:3, completed:1, remaining:2, overdue:1, upcoming:1, next_item:Vit D@08:00}` → provider content `"Commitments today: 3 … Completed: 1"` → `resolve_current_context(user, "summary:dashboard.day")` (the CoS path) returns the same content → both dashboard views expose the same builder (identity-checked). Cold user → `status="pending"` at every step. **No drift.**

## 6. Certification evidence

| Property | Evidence |
|---|---|
| deterministic | pure projection of the cached contract; fixed inputs → fixed facts (test) |
| authoritative | reads the single execution-contract authority via SAE; no re-derivation |
| request-path safe | only `get_module_state(..., allow_rebuild=False)`; grep proves no `build_execution_state`/`build_today_execution` call; `test_request_path_safety_contract` 4/4 |
| shared | provider + both views import the *same* `build_dashboard_day_summary` (identity-asserted) |
| reusable | plain `(user)→facts` builder; any surface (page, CoS, future card, watch) can read it |
| suitable for Current Context | registered `summary:dashboard.day`; resolves via `resolve_current_context` |
| suitable for bidirectional CC | `summary:dashboard.day` is a terminal ref in the existing grammar — a future `reveal(target)` can target it and `already_visible` can compare it |
| suitable for Reveal Target | the Dashboard workspace now has a canonical context ref to reveal to |

## 7. Remaining gaps

- **`execution_phase` + prioritized "do-now"** are intentionally excluded (need the heavy builder). A future increment could add a *cached phase* to the SAE execution snapshot and extend the summary — deferred, documented.
- Other domain overview summaries (health home, finance, meals, legacy, capture) still pending (Part V).
- **Pre-existing dashboard_v3 test failures (7)** exist in the base from the concurrent Journal-Workspace/Dashboard redesign (`eb7392ed`) — confirmed **not** caused by this milestone (they fail with these edits shelved). Flagged for a separate fix; out of this milestone's scope.

## 8. Test results

`apps/core/tests/test_dashboard_day_summary.py` — **5/5 OK** (facts projection; pending-when-cold; honest pending message; full-chain one-source; views declare + share builder). `test_request_path_safety_contract` **4/4**; `test_constitution_contract` **9/9**; `makemigrations --check` **No changes**; `manage.py check` clean; `dashboard.day` self-registered at app-ready. Dashboard regression: **0 new failures** from this change (the 7 failures are pre-existing, proven by shelving the edits).

## 9. Readiness for bidirectional Current Context

**Closer, but finish the overview tier first.** The Dashboard — the highest-value surface — is now certified with a request-path-safe deterministic summary, which was *the* blocker named in Part V. Recommended before starting bidirectional CC: certify the remaining high-traffic domain overviews (health home, finance, meals) with the same shared-builder + SAE-cached pattern. Once those land, `reveal(target)` and `already_visible` will have precise deterministic context across the workspaces users actually sit in, and bidirectional Current Context can begin on a fully certified foundation.

---
---

# PART VII — Health / Finance / Meals Home Certification (Truth milestone)

**Why:** the Part VI §9 recommendation — the remaining three high-traffic domain overviews. Each was an overview page with **no** Current Context. Certified here with the **exact Dashboard Day Summary pattern**: one shared, facts-only, request-path-safe builder that reads the domain's **already-cached SAE snapshot** (`allow_rebuild=False`), returns `status="pending"` on a cold snapshot, and feeds BOTH the page render and the Current Context provider. No new authority, no new cache, no new calculation — pure exposure of existing cached truth.

## 1. Reused truth (no new authority)

| Workspace | Page (view) | SAE module | Producer (single authority) | Builder (new, shared) | Provider (`summary:<key>`) |
|---|---|---|---|---|---|
| **Health Home** | `HealthHomeView` (`health:home`, `/health/physical/`) | `health` | `build_health_state` | `apps/health/services/health_home_summary.py :: build_health_home_summary` | `health.home` (`apps/health/page_summaries.py`) |
| **Finance** | `FinanceDashboardView` (`finance:dashboard`, `/finance/`) | `finance` | `build_finance_state` (`_contract.summary/upcoming/alerts`) | `apps/finance/services/finance_home_summary.py :: build_finance_home_summary` | `finance.dashboard` (`apps/finance/page_summaries.py`, new file) |
| **Meals** | `MealsDashboardView` (`meals:dashboard`, `/meals/`) | `meals` | `build_meals_state` | `apps/meals/services/meals_home_summary.py :: build_meals_home_summary` | `meals.dashboard` (`apps/meals/page_summaries.py`) |

Each SAE module is registered in `MODULE_BUILDERS` (`state_builder.py:6058-6103`) → populated by the SAE cycle → read request-path-safe via `get_module_state(user, "<module>", allow_rebuild=False)`. Health Home reads the SAME `health` snapshot the page renders from (`hs`); Finance's `finance` snapshot is the same `_contract` `CurrentFinance` reads; Meals' `meals` snapshot is thinner than the full live dashboard (pantry / expiring / dinner-plan / grocery-cycle / dietary-targets facts) — the certified summary exposes those snapshot facts.

## 2. Facts-only contracts (no verdicts)

- **`health.home`** — weight (current + 30d change), 7-day sleep/steps/heart-rate, latest+7-day glucose, latest BP, water today vs goal, medication status (a SAE-resolved fact, not a WLJ verdict).
- **`finance.dashboard`** — net worth (+ assets/liabilities), account count, month spending/income, cash-pressure level (SAE fact), active-goal / overdue-bill / over-budget / recurring-due-14d counts. `enabled=False` and empty-`_contract` are distinct honest states.
- **`meals.dashboard`** — pantry item count, expiring-within-3-days count + names, tonight's dinner plan, grocery cycle days, daily protein/carb targets. No-household is a READY (not pending) honest state.

## 3. Certification evidence

Per workspace, mirroring the Dashboard 5-point certification (identical structure in each test file): (1) builder projects the cached snapshot deterministically; (2) `status="pending"` when the snapshot is cold; (3) the provider's pending message is honest ("being prepared"); (4) full chain reads ONE source — builder → provider → `resolve_current_context(user, "summary:<key>")` (the actual CoS path) agree; (5) the view declares `page_summary_key` AND imports the SAME builder by identity (no parallel impl). Meals adds a 6th (no-household is READY, not pending).

## 4. Test results

`apps/finance/tests/test_finance_home_summary.py` (5), `apps/meals/tests/test_meals_home_summary.py` (6), `apps/health/tests/test_health_home_summary.py` (5) — **16/16 OK**. `test_request_path_safety_contract` **4/4**; `test_constitution_contract` **9/9**; `makemigrations --check` **No changes**; `manage.py check` clean; all three providers (`health.home`, `finance.dashboard`, `meals.dashboard`) self-register at app-ready (14 providers total). No model changes; no new cache; no new authority.

## 5. Overview tier — certified

The three highest-traffic domain overviews (Health Home, Finance, Meals) now carry request-path-safe deterministic Current Context, alongside the Dashboard (Part VI) and Weight/Nutrition/Body-Intelligence (reference impls). The overview tier the Part VI §9 readiness note gated bidirectional Current Context on is complete for the primary workspaces users sit in. Remaining overview summaries (glucose, calendar, goals, tasks, reports, analytics, legacy hearth/library, capture) follow the identical pattern when their turn comes.
