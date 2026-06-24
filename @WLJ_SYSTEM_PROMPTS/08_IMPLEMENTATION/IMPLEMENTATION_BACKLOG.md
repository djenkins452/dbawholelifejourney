# ChatGPT CoS — Implementation Backlog

**Branch:** `feat/chatgpt-cos-transition`
**Baseline commit (main):** `a2e94d2b` — architecture baseline (04–07)
**Governing principle:** WLJ owns truth · ChatGPT owns understanding.
**Philosophy:** Expose · Serialize · Reuse · Launch · Iterate later. **Not** Redesign · Rebuild · Refactor · Perfect.

**The prime directive for every item below:** before writing anything, *prove the capability already exists*, then prefer serialization/reuse over invention. No new engines, no parallel pipelines, no Beth rebuild. Challenge any task that drifts toward rebuilding intelligence rather than exposing it.

---

## Backlog (by phase)

Each item lists: the new surface, what it **reuses** (existing deterministic provider — the work is exposure, not logic), and the acceptance signal.

### Phase 1 — Standing Context Foundation
| ID | Item | Reuses (existing) | Acceptance |
|----|------|-------------------|------------|
| P1-1 | `get_standing_context()` serializer | `build_cos_context` (`cos_context.py:3555`), `build_executive_context` (`:9079`) | Returns one JSON object with the 9 standing fields (Doc 07/02) |
| P1-2 | Read-only endpoint/service exposing it | existing CoS cache cadence | GET returns cached object; "pending" on miss (no live compute) |
| P1-3 | Tests | — | Serializer shape + freshness-guard + no-live-compute test |
| P1-4 | Telemetry | existing observability | Emit fetch/latency/cache-hit metrics |

**Done when:** ChatGPT can answer *"How am I doing? / What should I focus on? / What's my biggest risk?"* from standing context with **no extra tool calls.**

### Phase 2 — Generic Domain Access
| ID | Item | Reuses | Acceptance |
|----|------|--------|------------|
| P2-1 | `get_domain_state(domain)` accessor | `get_module_state` (`state_engine.py:74`) over `MODULE_BUILDERS` (`state_builder.py:5576`) | One parameterized tool covers all domains — **no per-domain tools** |
| P2-2 | Serialization layer (JSON-safe) | existing builders | Each domain returns its canonical state dict unchanged (no re-aggregation, Law 9) |
| P2-3 | Tests + observability | — | Domain allowlist + shape tests; per-domain fetch telemetry |

**Done when:** ChatGPT can answer *"What's my weight? / How is my faith life? / What goals are stalled?"*

### Phase 3 — ChatGPT Integration Layer
| ID | Item | Reuses | Acceptance |
|----|------|--------|------------|
| P3-1 | ChatGPT orchestration service | existing chat request lifecycle (as reference, not copy) | ChatGPT receives standing context + can call tools |
| P3-2 | Tool registry + dispatcher | tool roles from Doc 07/01 | Registered tools: standing, domain, decision, history, action |
| P3-3 | Telemetry + observability | existing chat snapshot infra | Per-turn tool-call trace |

**Done when:** a user converses naturally while ChatGPT dynamically retrieves deterministic evidence.

### Phase 4 — Decision Surface Reuse
| ID | Item | Reuses | Acceptance |
|----|------|--------|------------|
| P4-1 | `get_decision(mode)` tool | `CosDecisionView` / `cos_mode_router` (`/assistant/api/cos/decision/`) + selectors | **No new decision logic** — wraps the live endpoint |

**Done when:** ChatGPT answers *"What should I do next? / biggest risk? / what should I fix?"* via the existing deterministic modes.

### Phase 5 — Historical Intelligence
| ID | Item | Reuses | Acceptance |
|----|------|--------|------------|
| P5-1 | `search_history()` (time-based) | `query_event_history` / `EventResolver` (`action_handlers.py:6626`) | Time/date lookups across health/journal/faith |
| P5-2 | Wire existing keyword search (incremental) | `SearchService` (`search_service.py:30`), `search_notes_cos` (`notes/services.py:419`) — **currently dead code, just unwired** | Notes/capture/journal keyword search reachable |

**Done when:** ChatGPT answers *"Have I struggled with this before? / What worked previously? / How have I changed this year?"* without fabrication.

### Phase 6 — Action Execution
| ID | Item | Reuses | Acceptance |
|----|------|--------|------------|
| P6-1 | `execute_action(action, params)` dispatch | `execute_intent` → `action_handlers` (54 handlers) via UAIO | **No new write paths**; routes through Phase-2 write authority |
| P6-2 | Day-1 allowlist | the handlers below | create/update/complete_task, create_goal, create_note, create_journal_entry, log_prayer, save_verse, create_event, log_habit, log_workout |
| P6-3 | Safety-gate preservation tests | existing Learning Mode / validators | Gates fire regardless of front-end |

**Done when:** ChatGPT can add tasks, log journals, create goals, schedule events, log faith activity — through existing deterministic handlers.

### Phase 7 — Chat UI Transition
| ID | Item | Reuses | Acceptance |
|----|------|--------|------------|
| P7-1 | Feature flag for ChatGPT path | existing flag infra | Per-user toggle; legacy Beth path stays live |
| P7-2 | Side-by-side validation + telemetry comparison | existing chat snapshot/telemetry | Parity dashboard (legacy vs ChatGPT) |
| P7-3 | Rollback strategy | flag flip | One-flag revert to Beth |

**Done when:** conversational experience runs on ChatGPT behind a flag, with legacy still operational and instant rollback.

### Phase 8 — Legacy Beth Conversational Retirement
| ID | Item | Reuses | Acceptance |
|----|------|--------|------------|
| P8-1 | Retire legacy conversation/prompt orchestration ONLY | — | Remove conversational glue; **keep all deterministic infrastructure** |

**Done when:** validated parity/improvement + trust + rollback path → legacy conversational orchestration removed; deterministic truth untouched.

---

## Standing guardrails (apply to every item)
1. Prove existing capability before building.
2. Serialize over invent · reuse over new infrastructure.
3. Preserve Architecture Laws — LLM Last, Single Source of Truth, Deterministic Decisioning, State-First Reads, Narration Contract.
4. Read-only before write; writes only through UAIO.
5. No live compute on the request path (read cache/snapshot; "pending" on miss).
6. Observable at every step.
7. Move fast; avoid overengineering.

## Anti-pattern watchlist (challenge on sight)
- A new "engine," "service brain," or "intelligence" module → STOP, reuse SAE/signals/composers.
- A second copy of state aggregation → STOP, call `get_module_state`.
- Per-domain `get_X_context` tools → STOP, use `get_domain_state(domain)`.
- A new write path bypassing UAIO → STOP, route through `execute_intent`.
- "Let's perfect this before launch" → STOP, ship the reuse path, iterate later.
