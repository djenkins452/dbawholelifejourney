# WLJ CoS Audit Scoring System

**Version:** 1.0
**Created:** 2026-03-11
**Last updated:** 2026-03-11

---

## Scoring Overview

Each audit domain receives a numeric score (0-100) and corresponding letter grade.

### Grade Scale

| Grade | Score Range | Meaning |
|-------|-----------|---------|
| **A** | 90-100 | Excellent — meets or exceeds architectural vision |
| **B** | 80-89 | Good — solid architecture with minor improvements needed |
| **C** | 70-79 | Acceptable — functional but has meaningful gaps |
| **D** | 60-69 | Below expectations — significant issues need addressing |
| **F** | <60 | Critical — architectural violations or major risks |

### Overall System Score

The overall system score is the weighted average of all seven domain scores:

| Domain | Weight | Rationale |
|--------|--------|-----------|
| CoS Conversation & Action Architecture | 20% | Core mutation pathway — highest risk |
| Engine Architecture | 15% | Foundation for intelligence quality |
| Hard Coding & Configuration Discipline | 10% | Maintainability and flexibility |
| Observability & System Health | 15% | Production reliability |
| Proactive Coaching System | 10% | User engagement quality |
| AI Decision Quality | 20% | Trust and safety — highest user impact |
| User Experience Consistency | 10% | Perceived quality and trustworthiness |

---

## Scoring Rubrics

### Domain 1: CoS Conversation & Action Architecture (20%)

| Score Range | Criteria |
|-------------|----------|
| 90-100 | `execute_action()` is sole mutation gateway; zero bypass paths; routing fully centralized; domain logic cleanly separated from conversation layer |
| 80-89 | `execute_action()` handles >95% of mutations; ≤2 minor bypass paths; routing mostly centralized |
| 70-79 | `execute_action()` handles >85% of mutations; some routing scattered; minor domain logic in conversation layer |
| 60-69 | Multiple mutation paths; routing partially centralized; domain logic embedded in conversation layer |
| <60 | No centralized mutation gateway; scattered routing; heavy domain logic in conversation layer |

### Domain 2: Engine Architecture (15%)

| Score Range | Criteria |
|-------------|----------|
| 90-100 | All engines produce signals only; zero direct state mutations; no inter-engine coupling; clear separation of concerns |
| 80-89 | >90% signal-only engines; ≤2 engines with minor state mutations; minimal coupling |
| 70-79 | Most engines signal-only; some engines mutate state; moderate coupling exists |
| 60-69 | Multiple engines mutate state; significant inter-engine coupling; some orchestration in engines |
| <60 | Engines routinely mutate state; heavy coupling; engines contain orchestration logic |

### Domain 3: Hard Coding & Configuration Discipline (10%)

| Score Range | Criteria |
|-------------|----------|
| 90-100 | Safety invariants hard-coded; all tunable parameters configurable; prompts centrally managed |
| 80-89 | Mostly good separation; ≤5 parameters that should be configurable; prompts mostly managed |
| 70-79 | Moderate hard-coding; 5-15 parameters that should be configurable; prompts partially scattered |
| 60-69 | Significant hard-coding; many parameters embedded in code; prompts scattered |
| <60 | Widespread hard-coding; business logic embedded as constants; no prompt management |

### Domain 4: Observability & System Health (15%)

| Score Range | Criteria |
|-------------|----------|
| 90-100 | Full telemetry coverage; all failure modes tracked; proactive anomaly detection; operational dashboards complete |
| 80-89 | >90% coverage; most failure modes tracked; anomaly detection present; dashboards functional |
| 70-79 | Moderate coverage; major failure modes tracked; some monitoring gaps; basic dashboards |
| 60-69 | Partial coverage; significant monitoring gaps; limited anomaly detection |
| <60 | Minimal coverage; most failures untracked; no anomaly detection; blind spots |

### Domain 5: Proactive Coaching System (10%)

| Score Range | Criteria |
|-------------|----------|
| 90-100 | Centralized orchestration; effective fatigue protection; coordinated messages; evidence-based prioritization |
| 80-89 | Mostly centralized; good fatigue protection; minor coordination gaps |
| 70-79 | Partially centralized; basic fatigue protection; some message conflicts possible |
| 60-69 | Fragmented orchestration; weak fatigue protection; limited coordination |
| <60 | No centralized orchestration; no fatigue protection; uncoordinated messages |

### Domain 6: AI Decision Quality (20%)

| Score Range | Criteria |
|-------------|----------|
| 90-100 | Reliable intent classification; unambiguous entity resolution; comprehensive safety protections; confirmation logic robust |
| 80-89 | Good classification accuracy; minor ambiguity risks; strong safety protections |
| 70-79 | Acceptable classification; moderate ambiguity risks; safety protections present but gaps exist |
| 60-69 | Classification issues documented; ambiguity risks significant; safety gaps concerning |
| <60 | Unreliable classification; frequent misresolution; safety protections insufficient |

### Domain 7: User Experience Consistency (10%)

| Score Range | Criteria |
|-------------|----------|
| 90-100 | Consistent voice across all domains; clear action narration; excellent conversation continuity; human-like CoS personality |
| 80-89 | Mostly consistent voice; good narration; minor continuity gaps; strong personality |
| 70-79 | Generally consistent; some domain-specific tone shifts; basic conversation tracking |
| 60-69 | Inconsistent voice in places; narration unclear at times; limited conversation context |
| <60 | Fragmented personality; poor narration; no conversation continuity |

---

## Scoring Process

1. **Evidence-based:** Each score must cite specific code references, file paths, or documented behaviors.
2. **Justified:** Each score includes a written justification explaining why the score was assigned.
3. **Compared to vision:** Scores reflect distance from the architectural vision, not just functional correctness.
4. **Trend-aware:** When previous audits exist, note trend (improving, stable, declining).

---

## Complexity Drift Score (Supplementary)

In addition to the seven domains, a supplementary Complexity Drift score is assigned:

| Score Range | Meaning |
|-------------|---------|
| 90-100 | System complexity is well-managed; clear abstractions; minimal redundancy |
| 80-89 | Complexity is manageable; some areas could be simplified |
| 70-79 | Complexity is growing; some redundant patterns; maintenance burden increasing |
| 60-69 | Complexity is concerning; significant redundancy; refactoring needed |
| <60 | Complexity is unmanageable; heavy duplication; architectural debt is compounding |

---

*Maintained by the WLJ Architecture Governance process.*
