# WLJ CoS Audit Process

**Version:** 1.0
**Created:** 2026-03-11
**Last updated:** 2026-03-11

---

## How to Run an Audit

To execute a full system audit, say:

> "Run the WLJ Full System Audit."

This triggers the following process.

---

## Audit Execution Steps

### Phase 1: Preparation (5-10 min)

1. **Read governance docs:**
   - `architecture_governance/COS_AUDIT_FRAMEWORK.md` — Audit domains and key questions
   - `architecture_governance/COS_AUDIT_SCORING.md` — Scoring rubrics
   - `architecture_governance/COS_AUDIT_PROCESS.md` — This process document

2. **Read reference docs:**
   - `docs/ENGINE_COS_REFERENCE.md` — Current engine inventory and known bugs
   - `docs/INTELLIGENCE_ARCHITECTURE.md` — Authoritative engine definitions

3. **Load previous audit** (if any):
   - Read the most recent file in `architecture_governance/system_audits/`
   - Note previous scores for trend analysis

### Phase 2: Deep Exploration (20-30 min)

Launch parallel exploration agents for each audit domain:

| Agent | Target |
|-------|--------|
| CoS Action Architecture | Chat pipeline, intent routing, action execution, mutation paths |
| Engine Architecture | All engines, dependencies, state mutations, signal patterns |
| Observability & Health | Telemetry, error tracking, monitoring, dashboards |
| Proactive Coaching | Check-in generation, throttling, fatigue protection, coordination |
| Configuration Analysis | Hard-coded values, prompts, thresholds, feature flags |
| UX Consistency | System prompts, voice, personality, conversation management |

### Phase 3: Analysis & Scoring (15-20 min)

For each of the 7 audit domains:

1. **Collect evidence** — File paths, line numbers, code patterns
2. **Identify strengths** — What works well architecturally
3. **Identify weaknesses** — What deviates from the vision
4. **Identify risks** — What could cause problems at scale
5. **Formulate recommendations** — Specific, actionable improvements
6. **Assign score** — Using the rubric in `COS_AUDIT_SCORING.md`
7. **Write justification** — Explain the score with evidence

### Phase 4: Cross-Cutting Analysis (10 min)

1. **Complexity drift analysis** — Count engines, dependencies, layers, duplicated logic
2. **Phase boundary compliance** — Verify three-phase pipeline integrity
3. **Key system risks** — Identify top 5 systemic risks
4. **Strategic improvements** — Prioritize top 5 improvements by impact

### Phase 5: Report Generation (10 min)

Create the audit report at:
```
architecture_governance/system_audits/cos_system_audit_YYYY_MM_DD.md
```

Each audit creates a NEW report file. Never overwrite previous audits.

### Phase 6: Framework Update (5 min)

Review `COS_AUDIT_FRAMEWORK.md` for gaps:
- Are there new engines not in the framework?
- Are there new architectural patterns?
- Have key file paths changed?

Update the framework if needed.

---

## Report Template

```markdown
# WLJ CoS System Audit — YYYY-MM-DD

## Executive Summary
[2-3 paragraph overview of system health, key findings, overall score]

## Architecture Map
[Current system architecture diagram showing key components and data flows]

## Section 1: CoS Conversation & Action Architecture
**Score:** XX/100 (Grade: X)
### Strengths
### Weaknesses
### Risks
### Recommendations

## Section 2: Engine Architecture
**Score:** XX/100 (Grade: X)
### Strengths
### Weaknesses
### Risks
### Recommendations

## Section 3: Hard Coding & Configuration Discipline
**Score:** XX/100 (Grade: X)
### Strengths
### Weaknesses
### Risks
### Recommendations

## Section 4: Observability & System Health
**Score:** XX/100 (Grade: X)
### Strengths
### Weaknesses
### Risks
### Recommendations

## Section 5: Proactive Coaching System
**Score:** XX/100 (Grade: X)
### Strengths
### Weaknesses
### Risks
### Recommendations

## Section 6: AI Decision Quality
**Score:** XX/100 (Grade: X)
### Strengths
### Weaknesses
### Risks
### Recommendations

## Section 7: User Experience Consistency
**Score:** XX/100 (Grade: X)
### Strengths
### Weaknesses
### Risks
### Recommendations

## Complexity Drift Analysis
**Score:** XX/100 (Grade: X)
[Findings about system complexity trends]

## Key System Risks
1. [Risk with severity and impact assessment]
2. ...

## Top Strategic Improvements
1. [Improvement with priority, effort estimate, and expected impact]
2. ...

## Overall System Score
| Domain | Weight | Score | Grade | Trend |
|--------|--------|-------|-------|-------|
| CoS Conversation & Action | 20% | XX | X | — |
| Engine Architecture | 15% | XX | X | — |
| Hard Coding & Configuration | 10% | XX | X | — |
| Observability & System Health | 15% | XX | X | — |
| Proactive Coaching | 10% | XX | X | — |
| AI Decision Quality | 20% | XX | X | — |
| UX Consistency | 10% | XX | X | — |
| **Overall** | **100%** | **XX** | **X** | **—** |

Complexity Drift (supplementary): XX/100 (Grade: X)
```

---

## Audit Cadence

| Frequency | Type | Scope |
|-----------|------|-------|
| Monthly | Full audit | All 7 domains + complexity drift |
| After major features | Focused audit | Affected domains only |
| After incidents | Incident review | Root cause domain + observability |

---

## Artifacts

| Artifact | Location | Purpose |
|----------|----------|---------|
| Audit Framework | `architecture_governance/COS_AUDIT_FRAMEWORK.md` | Defines what to audit |
| Scoring System | `architecture_governance/COS_AUDIT_SCORING.md` | Defines how to score |
| Audit Process | `architecture_governance/COS_AUDIT_PROCESS.md` | Defines how to run |
| Audit Reports | `architecture_governance/system_audits/` | Historical records |

---

*Maintained by the WLJ Architecture Governance process.*
