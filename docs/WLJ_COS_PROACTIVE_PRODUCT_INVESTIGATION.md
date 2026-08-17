# WLJ Chief of Staff — Post-Certification Product Investigation
## From "Knows My Life" → "Helps Me Run My Life"

**Type:** product/runtime investigation + roadmap decision (NO implementation).
**Date:** 2026-08-14. **Baseline:** the CoS Certification Program is **ACTIONABLE COMPLETE**
(139/140 questions, zero actionable gaps, one deferred; cross-domain Executive Synthesis
grounded; missing-data awareness works on-request — `WLJ_COS_CERTIFICATION_LEDGER.md`).
The core WLJ↔OpenAI architecture is CLOSED. This doc decides the next PRODUCT milestone.

---

## 1. Certification baseline (what "knows my life" now means)
The CoS can be asked anything actionable about any life domain and answers from grounded,
current, deterministic truth; it reasons across domains, prioritizes, distinguishes
strengths from problems, substantiates on challenge, and — when asked — names the boundaries
of its own evidence. That is **necessary but insufficient**: today the CoS is overwhelmingly
a *question-answer endpoint* — excellent when engaged, mostly silent otherwise.

## 2. As-built operating loop (runtime-traced)
Live CoS = `CoSGateway.respond()` → `ModelInterfaceService.generate()` (the certified
runtime). Change → `fire_intelligence()` (fire-and-forget) → SAE state + stored
`Insight`/`Prediction`/`GuidanceItem` (backend only; **not injected into the certified CoS
standing context**). Separately, a **scheduled proactive layer** runs under Celery Beat →
ISE: the **Proactive Guidance Scheduler (PGS, every 15 min)** authors ~25 check-in types and
delivers them by seeding a real `is_proactive` assistant chat message **+** lighting the
in-app bell (default-on); the **Daily Briefing Engine (DBE, daily)** writes a dashboard card;
the **DNE (every 10 min)** fans out critical/warning insights/guidance/briefings to channels
(in-app on; email/SMS/push opt-in, default off); an **app-open chat briefing** exists. **So
WLJ already reaches Danny proactively in-app** — but that proactive voice runs largely on the
**legacy `PersonalAssistant`/`proactive_checkins` pipeline, not the certified
`model_interface` CoS**, and does not share its grounding, its standing context, or its
whole-life executive synthesis.

## 3–7. Capability maturity

| Capability | Maturity | Evidence |
|---|---|---|
| **Awareness** (knows relevant facts) | **MATURE** | SAE state, insights, `current_action`, per-value freshness, whole-life truth certified |
| **Judgment** (OpenAI decides it matters) | **MATURE** | Certified cross-domain Executive Synthesis: prioritizes, distinguishes strengths/problems, grounded |
| **Initiative** (brings it forward unasked) | **PARTIAL — WIRED but DISCONNECTED** | PGS/DBE/DNE deliver in-app proactively (default-on), but on the LEGACY pipeline; the certified CoS's grounded judgment is NOT the proactive voice; stored insights not in CoS standing context; session-start CoS presence **suppressed/stubbed** for CoS users |
| **Follow-through** (remembers a thread, returns to it) | **WEAK / MISSING** | Conversation State carries only the active subject, one session, 30-min TTL; **no promised follow-up** ("check back tonight" `snooze_until` is NOT persisted/consumed — cosmetic); no cross-session "you told me this morning"; routine-recovery escalation is the only real deterministic follow-up |
| **Missing-data awareness** | **ON-REQUEST ONLY** | Per-value freshness reaches the model; "what am I missing" answered well; **no proactive "your data is stale, advice limited" surface** in standing context |
| **Time-based initiative** | **BUILT** | PGS (15 min, time-windowed, quiet 22–07 hard-coded), DBE (daily), nightly reminder crons, CoS Event Engine (3h). No user-set brief time; no general quiet-hours field |
| **Event-based initiative** | **PARTIAL** | Post-write fires SAE+insights (backend); only critical/warning promoted via DNE; significant-event (milestone) reflex delivers a win. Info/positive/weak = retrieval-only |

## 8–10. Action completeness
CoS model writes (only when `use_model_interface_writes`, **default OFF**): `mutate_task`,
`create_task`, `complete_task`, `log_weight`, `log_body_measurements`,
`import_journal_entries` + `resolve_pending_action`, `complete_execution_item` (retroactive,
multi-domain), `next_review_item`. **A large action surface EXISTS but is NOT exposed to the
CoS**: `log_food`, `log_workout`/`log_exercise_set`, `take_medication`, `log_glucose/BP/HR/
sleep/water/steps`, `create_event`/calendar edits, `log_transaction`, `create_note`,
real-time `create_journal_entry`, `create_goal`/`update_goal_progress`, `start/end_fast`, etc.
→ **many common requests end advice-only.** Confirmation/audit path is mature.

## 11. Current Context → Reveal Target readiness
Per `WLJ_COS_PLATFORM_EVOLUTION_INVESTIGATION.md`: navigation is ~85–90% built; the net-new
is ONE `navigate_to_workspace` tool + wiring a `navigate` field into `generate()` on the
keeper runtime. Its gates (Current Context cert, Retrieval Platform cert, Executive Truth
cert, whole-life domain cert) are **now satisfied** → gate-ready. But it is **presentation**,
not initiative — lower priority for "helps me run my life."

## 12–13. Proactive surfaces + scenario results (as-built)
Surfaces: CoS chat (proactive seed), in-app bell, dashboard briefing card, app-open briefing;
push/SMS/email dormant. Scenarios:
- **A Morning** — DBE card + app-open briefing exist, but on the legacy path; the *certified*
  CoS does not proactively open the day. Session-start CoS = stub.
- **B Missed workout** — awareness YES (completion is derived, never inferred from a plan);
  proactive follow-up only via generic PGS workout check-in, not tied to a specific
  conversation.
- **C Work crisis** — active subject persists within the session; **no durable thread** to
  help across the rest of the day or return tomorrow. GAP.
- **D Missing nutrition** — CoS knows on-request ("what am I missing"); does **not**
  proactively flag that advice is degraded. GAP.
- **E Relationship drift** — PASS: OpenAI flags neglected people from facts (days-since-
  contact) with NO WLJ "neglected" verdict.
- **F Medication miss** — overdue medication truth exists; PGS medicine check-in can fire.
  Partial.
- **G Evening reconciliation** — `complete_execution_item` + guided review support retroactive
  multi-domain completion. Reasonable.
- **H Workspace reveal** — navigation only after a mutation (hardcoded hints); pure "show me
  my weight" reveal needs the gate-ready `navigate_to_workspace` tool.

## 14. Gap matrix (by category — do not solve one with another's machinery)
| Gap | Category | Note |
|---|---|---|
| Proactive voice is the LEGACY pipeline, not the certified CoS | **Initiative** | Delivery is wired; the certified grounded judgment isn't behind it |
| Certified CoS doesn't proactively open the day (session-start stubbed) | **Initiative** | DBE/app-open briefing exist but not the certified CoS |
| Stored insights not injected into CoS standing context | **Context** | The CoS can't proactively reference its own generated intelligence |
| Promised follow-up not persisted; no cross-session thread | **Follow-through** | `snooze_until` unconsumed; Conversation State one-session only |
| No proactive "data stale → advice limited" surface | **Initiative + Context** | Freshness exists per-value; not surfaced unasked |
| Large action surface unexposed to CoS | **Action** | Many requests end advice-only |
| `navigate_to_workspace` not built | **Presentation** | Gate-ready per the evolution doc |
| Push/SMS/email dormant | **User-control / operator** | Needs registered device + env creds (operator), then opt-in |
| No user brief-time / general quiet-hours / priority-domain prefs | **User-control** | PGS hard-codes windows |

## 15. Ranked next product milestones (by daily customer value × trust × frequency × reuse × low risk)
1. **Proactive Daily Executive Brief — in the CERTIFIED CoS's voice.** Once-daily (app-open /
   morning) the CoS opens the day with a grounded, prioritized read: *what matters today,
   what changed, what's slipping, and what I'm missing* — the SAME whole-life executive
   synthesis just certified, delivered through the already-wired proactive surface. Turns the
   entire certification into a daily felt experience.
2. **Conversational follow-through / durable promised follow-up.** The CoS can create a
   deterministic follow-up record ("check back tonight about the workout") that the existing
   PGS re-fires with context. Makes it *stay with* Danny across the day.
3. **Proactive missing-data ask.** When stale/absent truth materially limits advice, say so
   and ask for it — the CoS already knows what it's missing; surface it unasked.
4. **Action completeness (curated expansion).** Expose the safe, high-frequency actions
   behind the mature confirmation path so common requests end in *doing*, not advice.
5. **Reveal Target / `navigate_to_workspace`** (gate-ready; presentation) — after the above.

## 16–19. RECOMMENDED NEXT MILESTONE (ONE)
**#1 — Proactive Daily Executive Brief on the certified CoS.**
- **Why first:** highest FREQUENCY (every morning/app-open), highest TRUST (it is the
  certified voice, not the legacy pipeline), maximal REUSE (the certified cross-domain
  Executive Synthesis + the already-wired PGS/DBE/app-open delivery + existing prefs), LOWEST
  new-architecture cost (connect proven pieces; un-stub session-start onto `CoSGateway`), and
  it is the single change that most makes Danny FEEL the CoS is running his day rather than
  waiting to be asked. It directly answers Scenario A and sets up follow-through (#2).
- **Reuses:** `ModelInterfaceService.generate()` + certified executive synthesis; PGS/DBE
  delivery + `_create_proactive_message`; standing context (`current_action`, missions,
  freshness); user prefs (`assistant_proactive_checkins`, `notification_reminder_time`, quiet
  windows). Adds a `daily_brief` intent that runs the certified whole-life read once/day and
  seeds it as the day's opening `is_proactive` message.
- **MUST NOT build:** a new scheduler (PGS/ISE exist), a new notification channel, a second
  briefing engine (DBE exists — consume/replace it, don't fork), a deterministic "importance
  brain" (OpenAI owns "does this matter"), generated-prose memory in Conversation State, a
  nagging engine (respect existing caps/quiet hours), push-to-device plumbing (operator-gated),
  or Reveal Target (later milestone). Keep it once-daily and user-controlled.

## 20. Operator / deferred items (not code milestones)
- **Push-to-device**: register a native `MobileDevice` + set APNs env creds + opt-in
  `intelligence_push_enabled` — **operator/infra**, then off-device reach lights up (code is
  complete).
- **Deferred (honest):** `health.body_temperature.current_context`; per-domain
  `current_context` without a page summary; per-exercise strength progression; workout-plan
  adherence.

---

## 21. MILESTONE 1 — SHIPPED (2026-08-14, commit `30d2499c`)
**Proactive Daily Executive Brief, authored by the CERTIFIED CoS.** Delivered exactly as
recommended — connect proven pieces, no new architecture.

- **Where:** `generate_daily_executive_brief_for_user(user)` in `apps/ai/proactive_checkins.py`,
  called FIRST in the existing PGS morning window (`WINDOW_MORNING = range(7, 10)`).
- **Reasoning:** the SAME certified runtime Danny gets on a broad question —
  `ModelInterfaceService.generate(conversation, DAILY_BRIEF_DIRECTIVE)` → model-directed
  CURRENT-truth retrieval + bounded Executive Synthesis. **No second reasoning system;** the
  legacy `PersonalAssistant`/proactive generators are untouched.
- **Delivery:** the existing `_create_proactive_message` → real `is_proactive` assistant turn
  in the active conversation + DNE/bell. A real turn Danny can reply to ("why?/I disagree").
- **Idempotency:** at most one per **user-local day** by DETERMINISTIC DB identity
  (`metadata.brief_date`), never model-prose equality; atomic `cache.add` lock guards
  concurrent workers. Safe against repeated 15-min cycles, retries, and multiple app opens.
- **Fail-safe:** empty/error answer → NO brief written, NO legacy reasoning substituted, never
  raises; normal interactive CoS unaffected. Respects the proactive-disabled preference.
- **Request-path safe:** runs only in the PGS worker cycle; never on a page load (contract 4/4).

**Natural product certification (deployed worker, Danny's real data):**
- **A — daily generation:** grounded (retrieved health/goals/relationships/finance live), one
  high-impact focus (body-composition drift: weight −5.1 lb but lean mass −2.2 lb / fat +4.0 lb,
  low protein), executive judgment + one action. No domain-tour/metric-dump/five-list. PASS.
- **B — evidence challenge:** substantiated with real numbers (protein 33g vs 180g target =
  18.3% compliance, tied to the lean-mass loss). PASS.
- **C — disagreement + data-quality doubt:** genuinely RECONSIDERED — acknowledged inconsistent
  logging (34 entries/wk, last Aug 16), recognized the low-intake signal could be a data
  artifact, and reframed the priority to "verify logging first." Did not dig in or capitulate.
  PASS (also demonstrates **D — missing-data awareness** firing when it materially limits
  judgment).
- **E — duplicate protection:** deterministic DB identity + atomic lock; unit-proven
  (`test_daily_executive_brief.py`, one-per-local-day + next-day-regenerates). PASS.
- **F — normal-chat regression:** a plain "how's my weight trending?" returns the usual focused
  answer; the brief is fully isolated to the morning window. PASS.
- **Multiple runs:** 3 independent brief openings, consistent single-focus executive quality
  with honest variance in which facet of the same whole-life story leads.

**Legacy proactive migration — remaining (NOT this milestone):** the morning window's other
generators (medicine / birthday / faith check-ins) and the DBE dashboard card still run on the
legacy pipeline — but **none is a whole-life executive chat brief**, so there is NO content
duplication with the new brief and nothing was suppressed. The broader migration of the ~25
PGS check-in types and the DBE card onto the certified CoS is deferred to a later milestone
(each is a domain-specific nudge, lower value than the day-opener). Milestone 2 (durable
promised follow-up) and push-to-device (operator-gated) remain per §15/§20.

## 22. PROACTIVE PRODUCT PHASE 2 — COMPLETE (2026-08-17)
All three milestones shipped, prod-deployed (web+worker), and validated on Danny's real data.
Cost telemetry + testing-cost guardrails from the governance milestone were preserved throughout
(every new proactive turn is ledgered under `traffic_class=proactive`; validation used bounded
Tier-2/Tier-4 real-model runs per `03 §10a`, never batches).

- **M2 — Durable Conversational Follow-Through** (`cabea74b`…`22d45741`). `ConversationFollowUp`
  is the single deterministic owner; created only by the native `schedule_follow_up` tool (model
  computes the time, WLJ validates+stores); fired by the existing PGS cycle, authored FRESH from
  current truth by the certified CoS, delivered via `_create_proactive_message`; duplicate-safe
  (atomic claim), fail-safe (no fabricated follow-up), proactive-pref-gated. Fixed the dead
  `handle_remind_later` `snooze_until` lie. Prod smoke: `scheduled` end-to-end. **Prod bug the
  Tier-2 smoke caught:** `django.utils.timezone.utc` (removed in Django 5.x) → fixed to
  `datetime.timezone.utc` (env drift a unit test couldn't see — the reason the smoke exists).
- **M3 — Proactive Missing-Data Intervention** (`019146f1`). Core capability already existed
  (model reasons over freshness/`holds_data`/briefing STALE tier; proven M1 Test D) — not rebuilt.
  Closed the one real TRUTH gap: on-demand facts-only `get_data_health` tool over the single
  existing `health_sync_status` authority, so the CoS tells "not synced" from "not done." OpenAI
  decides materiality; no importance brain. Prod smoke: listed quiet sources w/ days-since.
- **M4 — Action Completeness** (`415b6038`…`13941f24`). Exposed the remaining DAY1-safe
  high-leverage actions (create_event, add_reminder, log_workout, log_habit, create_goal,
  update_goal_progress, log_prayer, save_verse, create_journal_entry, add_gratitude) through the
  existing validate→confirm→execute→audit pipeline; safety ratchet test locks the invariant.
  Prod-verified `create_event status=ok`. **Fixed an action-audit observability gap** (named-write
  rows were unlinked from the conversation) that briefly masqueraded as write-fabrication but was
  a stale-snapshot read + missing `conversation_id`.

**Integrated day-long certification (one scripted conversation, Danny's data):** executive read
("Prayer Time is the one thing — overdue") → plan + `schedule_follow_up` ("I'll check back at 6 PM
about your Prayer Time") → `get_data_health` (quiet sources named) → `create_event(ok)` — with
continuity threading the subject across all four turns. **It reads as one Chief of Staff running the
day with Danny, not disconnected features.**

**Residuals (proven, minor — not blockers):** (1) follow-up *firing* is time-delayed (PGS), shown
via unit tests + a real 6 PM follow-up scheduled during cert, not synchronously; (2)
`resolve_pending_action` shares the audit-linkage gap now fixed for `request_action`; (3) a read
immediately after a write can reflect a stale SAE snapshot (pre-existing Layer-1 read-freshness,
affects all writes, not M4-specific). **Phase 2 can be declared COMPLETE** pending Danny's app-level
validation and cleanup of the cert test artifacts (a few events/tasks/follow-ups on his account).

## CLOSURE ANSWER
**Smallest next capability that makes Danny noticeably feel his Chief of Staff HELPS RUN his
life:** the **Proactive Daily Executive Brief in the certified CoS's own voice** — his CoS has
already thought about his day when he opens the app and leads with the one thing that matters,
what changed, what's slipping, and what it needs from him, grounded in the whole-life truth we
just certified. Not another score, layer, or dashboard — a daily, felt shift from *"answers my
questions"* to *"runs my day with me."* **Recommendation only — do not implement until Danny
reviews.**
