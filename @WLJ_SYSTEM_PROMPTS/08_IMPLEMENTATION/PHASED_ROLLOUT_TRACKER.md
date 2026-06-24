# ChatGPT CoS — Phased Rollout Tracker

**Branch:** `feat/chatgpt-cos-transition` · **Baseline:** `a2e94d2b` (main)
**Status legend:** ⬜ Not started · 🟦 In progress · ✅ Done · ⏸️ Blocked

| Phase | Title | Status | Code? | Usable outcome | Commit(s) |
|-------|-------|--------|-------|----------------|-----------|
| **0** | Preserve Architecture Baseline | ✅ Done | No | Baseline committed; branch + trackers created | `a2e94d2b` (main), this branch |
| **1** | Standing Context Foundation | ✅ Done (on branch) | Yes (read-only) | Aware CoS — "how am I doing" from standing context | `d1dcd9b0` |
| **2** | Generic Domain Access | ✅ Done (on branch) | Yes (read-only) | Holistic read CoS — any domain via `get_domain_state` | `f8cc390d` |
| **3** | ChatGPT Integration Layer | ✅ Done (on branch, flag OFF) | Yes (flag-gated) | Natural conversation with dynamic evidence retrieval | `786204bd` |
| **4** | Decision Surface Reuse | ✅ Done (on branch, flag OFF) | Yes (reuse) | Execution/Risk/Fix answers via existing modes | `9f5b86bf` |
| **5** | Historical Intelligence | ✅ Done (on branch, flag OFF) | Yes (reuse) | "Have I been here before" — keyword history search | `5b7b44a4` |
| **6** | Action Execution | ✅ Done (on branch, flag OFF) | Yes (reuse) | CoS that acts — tasks/journal/goals/events via UAIO | `e68be088` |
| **7** | Persistent Conversation Infra | ⬜ Not started | Yes (reuse) | Server-owned execution; survives nav/refresh/disconnect; multi-tab reattach | — |
| **8** | Chat UI Transition | ⬜ Not started | Yes | ChatGPT path behind a flag; legacy live; rollback ready | — |
| **9** | Legacy Beth Retirement | ⬜ Not started | Yes (removal) | Legacy conversational orchestration retired | — |

> **Connection topology (DECIDED): HYBRID.** Conversation orchestration stays inside WLJ; OpenAI is the reasoning engine; tools are internal Python services (StandingContextService, DomainStateService, DecisionService, HistorySearchService, ActionExecutionService) reusing existing providers, designed to be wrapped by authenticated HTTP endpoints later with no logic change. No OAuth/public APIs during initial build.
>
> **Phase 7 reuse target:** the persistent/background-conversation requirement is largely already built — `apps/ai/chat_stream_bus.py` + `run_chat_generation` (Celery) + the resume-by-job_id endpoint (commit `50fb57e5`) already make Beth generation survive navigation. Phase 7 reuses this, it does not rebuild it.

---

## Consolidated status (branch / commit / main-readiness)

| Phase | Status | Branch | Commit | Ready for Main |
|-------|--------|--------|--------|----------------|
| Architecture Docs | Complete | main | `a2e94d2b` | Yes (merged) |
| Phase 0 Tracking | Complete | feat/chatgpt-cos-transition | `a1e9325b` | Yes |
| Phase 1 Standing Context | Complete | feat/chatgpt-cos-transition | `d1dcd9b0` | Yes (dormant/unwired) |
| Phase 2 Domain Access | Complete | feat/chatgpt-cos-transition | `f8cc390d` | Yes (merged `f7eea159`) |
| Phase 3 ChatGPT Integration | Complete | feat/chatgpt-cos-transition | `786204bd` | NO — pending real-model live validation |
| Phase 4 Decision Surface | Complete | feat/chatgpt-cos-transition | `9f5b86bf` | NO — pending real-model live validation |
| Phase 5 Historical Intelligence | Complete | feat/chatgpt-cos-transition | `5b7b44a4` | NO — rides the 3+4 live-validation gate |
| Phase 6 Action Execution | Complete | feat/chatgpt-cos-transition | `e68be088` | NO — rides the 3-6 live-validation gate |

> **Live validation status (Phase 3+4 merge gate):** the deterministic half is PROVEN against real (non-mocked) services — `dispatch_tool_call` → `get_decision`/`get_domain_state`/`get_standing_context` returns real deterministic truth (e.g. `get_decision('risk')` → "No risks right now." via the real `build_execution_state`+selectors; `purpose`→`goals` SAE alias confirmed). The real-MODEL tool-selection link is NOT yet validated — this environment has no `OPENAI_API_KEY`. Run the harness in a key-bearing safe env to complete the gate:
> `python manage.py validate_cos_tools --email <you@example.com>`
> Until that passes, Phase 3 + 4 stay on the branch (per the "mocked is no longer sufficient" policy).
| Phase 7 Persistent Conversations | Pending | — | — | — |
| Phase 8 UI Cutover | Pending | — | — | — |
| Phase 9 Legacy Retirement | Pending | — | — | — |

> Phases 1–2 are "ready for main" in the sense that they are additive, read-only, fully tested, and have NO caller in any request path yet (dormant until Phase 3 wires them). They remain branch-isolated per the transition plan.

---

## Phase 0 — completion record (this phase)

| Task | Status | Evidence |
|------|--------|----------|
| 1. Commit all architecture documents | ✅ | `a2e94d2b` on `main` (29 docs + changelog), pushed |
| 2. Create dedicated branch | ✅ | `feat/chatgpt-cos-transition` |
| 3. Implementation tracking documentation | ✅ | `IMPLEMENTATION_BACKLOG.md`, this tracker |
| 4. Migration checklist | ✅ | `MIGRATION_CHECKLIST.md` |
| Code changes | ✅ None (Phase 0 is no-code) | — |

---

## Critical-path milestones (from Day-1 rollout sequence, Doc 07/06)
- **Usable holistic read-only CoS** → end of **Phase 2**.
- **CoS that acts / feels real** → end of **Phase 6**.
- **Full conversational cutover** → **Phase 8**, with legacy retained.
- **Legacy retirement** → **Phase 9**, only after validated parity + rollback.

## Update protocol
After each phase: set status, record commit hash(es) + deployment status, and append a short report (Current state / Changes / Blast radius / Verification / Next phase) to `PHASE_REPORTS.md` (created when Phase 1 begins).
