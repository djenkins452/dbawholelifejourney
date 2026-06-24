# ChatGPT CoS — Migration Checklist (Beth → ChatGPT)

The cutover checklist for transitioning the **conversational layer** from legacy Beth to ChatGPT while WLJ continues to own truth. This governs what must be true before each gate is crossed. It is a safety instrument: nothing is removed until its replacement is proven.

**Non-negotiable invariant:** every item preserves WLJ's deterministic core. Domains, engines, signals, state, execution, storage, dashboards, telemetry, integrations, and the Architecture Laws are **out of scope for change** at every step.

---

## Gate A — Before exposing any surface (Phases 1–2)
- [ ] Capability proven to already exist (provider named with `file:line`) before any serializer is written.
- [ ] Serializer reuses the existing builder; performs **no re-aggregation** (Law 9).
- [ ] Read path reads cache/snapshot only; returns "pending" on miss — **no live compute** on request path.
- [ ] Output is deterministic and observable (telemetry emitted).
- [ ] Tests cover shape + freshness + no-live-compute.

## Gate B — Before connecting ChatGPT (Phase 3)
- [ ] Standing context (Phase 1) and `get_domain_state` (Phase 2) live and tested.
- [ ] Tool registry contains only reuse-backed tools (no tool fronts a non-existent provider).
- [ ] Auth/identity scoping enforced on every tool call (correct user, entitlements).
- [ ] Per-turn tool-call tracing in place.
- [ ] ChatGPT cannot originate facts — every factual field traces to a provider (LLM Last).

## Gate C — Before enabling decisions & history (Phases 4–5)
- [ ] `get_decision(mode)` wraps the existing `/api/cos/decision/` — **no new decision logic** added.
- [ ] Decision answers match the deterministic modes exactly (Execution/Risk/Fix; Law 14).
- [ ] `search_history` returns deterministic records only; no fabricated history.
- [ ] Any keyword search wired from existing `SearchService`/`search_notes_cos` (not reinvented).

## Gate D — Before enabling actions (Phase 6)
- [ ] `execute_action` routes through `execute_intent` → UAIO — **no new write path** (Law 8).
- [ ] Day-1 allowlist enforced; non-allowlisted actions rejected.
- [ ] Existing safety gates (Learning Mode, validators) verified firing regardless of front-end.
- [ ] Destructive/ambiguous actions require confirmation; `ActionResult` narrated truthfully.
- [ ] Writes are auditable (existing audit trail intact).

## Gate E — Before UI cutover (Phase 7)
- [ ] Feature flag gates the ChatGPT path per user; **legacy Beth path remains fully operational**.
- [ ] Side-by-side validation run; telemetry comparison shows parity or improvement.
- [ ] Chat history preserved/accessible across both paths.
- [ ] Observability + auditability preserved on the ChatGPT path.
- [ ] One-flag rollback to Beth verified.

## Gate F — Before legacy retirement (Phase 8)
- [ ] ChatGPT CoS production-validated over a sustained window.
- [ ] Trust established (no fabrication incidents; confidence framework honored).
- [ ] Telemetry confirms parity or improvement vs legacy.
- [ ] Rollback path still exists at the moment of retirement.
- [ ] Retirement scope limited to **conversational orchestration / prompt glue only**.
- [ ] Deterministic infrastructure (engines, state, signals, execution, decision modes, action handlers) **untouched**.

---

## Rollback posture (all phases)
- Phases 1–6 are **additive, read-or-reuse** surfaces — disabling a tool is a no-op for legacy Beth.
- Phase 7 cutover is **flag-gated** — rollback = flip the flag.
- Phase 8 is the only destructive step and is gated on Gate F in full.

## What this migration explicitly does NOT touch
domains · engines · signals · deterministic truth · execution architecture · storage · dashboards · telemetry · integrations · state architecture · Architecture Laws · the 54 action handlers · the decision modes · SAE/PIE/PRIE/PGE/CDCE and all Phase-1/2/3 engines.
