# CoS Persistent Learning Upgrade — Master Control Document

**Status:** COMPLETE
**Started:** 2026-02-28
**Author:** Claude Code (Opus 4.6)
**Approved by:** Danny Jenkins

---

## Executive Summary

Transform the Companion of Self (CoS) from a recall-only assistant into an adaptive learning system that improves continuously based on user behavior, feedback, corrections, and patterns.

**Current state:** CoS has conversation memory (RAG), learned profile extraction (regex), and a feedback field (`was_helpful`) that is never read back.

**Target state:** CoS that weights memories by helpfulness, persists corrections, evolves its learned profile, detects behavioral patterns, optimizes response style, and proactively surfaces detected patterns to the user.

---

## Phase 1: System Audit — Confirmed Gaps

| Component | Status | Gap |
|-----------|--------|-----|
| `memory_service.py` | Working | Flat retrieval — no weighting by helpfulness, recency, or corrections |
| `learning_extractor.py` | Working | Additive-only — no decay, frequency tracking, or conflict resolution |
| `ConversationMemory` model | Working | Missing: helpfulness_score, retrieval_count, was_corrected |
| `UserLearnedProfile` model | Working | Items are plain strings — no confidence, frequency, timestamps |
| `AssistantMessage.was_helpful` | Working (write) | **Dead-end** — stored but never queried to influence behavior |
| Correction handling | In-session only | No persistent correction records |
| Behavioral patterns | Not implemented | No cross-domain pattern detection |
| Response optimization | Not implemented | No per-user response preference learning |
| COS-CX (CX1-CX6) | Working | Not touched by this upgrade |
| PIE/PRIE | Working | Outputs not injected into CoS prompts (future enhancement) |

---

## Phase 2: Architecture Design

### Mechanism 1 — Feedback-Weighted Memory
- Add `helpfulness_score`, `retrieval_count`, `was_corrected` to ConversationMemory
- Modify retrieval scoring: `similarity * 0.5 + recency * 0.2 + helpfulness * 0.2 + frequency * 0.1`
- Propagate `was_helpful` from AssistantMessage to ConversationMemory

### Mechanism 2 — Correction Persistence
- New model: `CorrectionRecord`
- Detect correction language in user messages
- Store structured corrections with embeddings
- Inject as high-priority context in system prompt

### Mechanism 3 — Profile Evolution
- Migrate profile items from `list[str]` to `list[dict]` with confidence, frequency, timestamps
- Add decay logic (items not mentioned in 60+ days lose confidence)
- Add conflict resolution (new contradictory info marks old as resolved)
- Frequency tracking on re-extraction

### Mechanism 4 — Behavioral Pattern Learning
- New model: `BehavioralPattern`
- Cross-domain pattern detection (journal, health, tasks, faith)
- Statistical detection (>70% consistency over 4+ weeks)
- Inject active patterns into CoS system prompt

### Mechanism 5 — Adaptive Response Optimization
- New model: `ResponsePreference`
- Track response characteristics that get positive/negative feedback
- Inject learned preferences into system prompt

### Mechanism 6 — Pattern Awareness Reporting
- Surface newly detected patterns conversationally
- User confirmation boosts confidence
- User denial drops confidence

---

## Phase 3: Implementation Tracking

| Task | Status | Files |
|------|--------|-------|
| New models (ConversationMemory fields, CorrectionRecord, BehavioralPattern, ResponsePreference) | DONE | `apps/ai/models.py`, migration |
| Migration | DONE | `apps/ai/migrations/0024_persistent_learning_models.py` |
| Profile evolution (backward-compatible dict format) | DONE | `apps/core/ai_learning/learning_extractor.py`, `models.py` |
| Feedback-weighted memory | DONE | `apps/ai/memory_service.py` |
| Feedback propagation | DONE | `apps/ai/views.py` |
| Correction service | DONE | `apps/ai/correction_service.py` (new) |
| Pattern detector | DONE | `apps/ai/pattern_detector.py` (new) |
| Response optimizer | DONE | `apps/ai/response_optimizer.py` (new) |
| Prompt integration | DONE | `apps/ai/personal_assistant.py` |
| Tests | DONE | 517 passed, 0 failures |

---

## Phase 4: Verification Checklist

- [x] Memory retrieval still works with existing data (backward compatible)
- [x] COS-CX (CX1-CX6) not affected (not touched)
- [x] Prompt construction stays within token budget (strict block size limits)
- [x] Existing tests pass (517/517)
- [x] New mechanisms activate without breaking chat flow (all wrapped in try/except)
- [x] `python manage.py check` clean
- [x] Migrations apply cleanly

---

## Phase 5: Completion

- [x] All tests pass
- [x] Changelog updated
- [x] Control document updated with final status
- [x] Committed, merged to main, pushed

---

## Risks

1. **Token budget** — Adding corrections, patterns, and response prefs to system prompt could exceed limits. Mitigation: strict block size limits per injection.
2. **Profile migration** — Converting `list[str]` to `list[dict]` needs careful data migration. Mitigation: migration handles both formats gracefully.
3. **API cost** — Correction embeddings add OpenAI calls. Mitigation: corrections are rare events, minimal cost.

---

*Last updated: 2026-02-28*
