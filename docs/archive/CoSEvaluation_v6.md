# CoS Behavioral Evaluation Report — v6

**Date:** 2026-03-07
**Evaluator:** Claude (System Evaluation Agent)
**Status:** EVALUATION PENDING — OpenAI API quota exhausted from v5 eval run. Code changes deployed; full 28-question eval to be run once quota resets.

---

## Executive Summary

v6 implemented three categories of changes:

### A. Pipeline Fix (Part 1): Reflection Misclassification
`_is_personal_reflection()` was too broad — matched strategic questions via substring hits on words like "improved" (matching "improvement"), "my life", "lately". Now tightened:
- **Added strategic exclusions** — any message containing `?`, "should I", "improve", "focus on", "what would", etc. is immediately excluded from reflection classification
- **Changed to phrase-level matching** — requires full phrases like "I feel ", "I'm struggling", "feeling overwhelmed" instead of individual words
- **Removed false-positive triggers** — "improved", "my life", "better", "since", "lately", "recently" no longer trigger alone

### B. Prompt Engineering (Parts 2-6): Consolidated CoS Operational Rules
Replaced the v5 multi-block prompt rules with a unified `CHIEF OF STAFF OPERATIONAL RULES (v6)` block containing 6 rules:

1. **RULE 1: No Generic Productivity Advice** — Eisenhower Matrix, Pomodoro, "time block your day" explicitly forbidden; must use actual user data instead
2. **RULE 2: Chief of Staff Voice** — strategic advisor tone, banned 9 specific generic assistant phrases
3. **RULE 3: Missing Data Framing** — "not logged yet" pattern with actionable links, never "unable to access"
4. **RULE 4: Decision Mode** — when user asks "should I...", response must follow Situation→Assessment→Recommendation→Next Step structure; mirroring without recommendation is forbidden
5. **RULE 5: Operational Briefing Format** — Goals→Goal-supporting actions→Tasks due→Overdue→Maintenance→Recommendation priority order; today-focused, concise, no clutter
6. **RULE 6: Knowledge Response Grounding** — acknowledge missing data→provide knowledge→explain what enables personalization

### C. Mandatory Context Evaluation (v6 upgrade)
Expanded from 4 steps to 6 steps — now explicitly requires checking:
- Tasks due today and overdue tasks
- Outstanding commitments (workout, routines)
- Missing data domains
Added stronger anti-template test: "does it reference the user's actual task count, workout status, goal state, or time context? If not, rewrite."

### D. Prohibited Behavior Updates
Added to SECTION 8:
- "Eisenhower Matrix", "Pomodoro Technique", "review your priorities", "set daily objectives" explicitly named
- Mirroring decision questions without recommendation — forbidden
- Empathy templates for strategic questions — forbidden

---

## Code Changes

| File | Change | Lines |
|------|--------|-------|
| `apps/ai/personal_assistant.py` | Tightened `_is_personal_reflection()` — strategic exclusions + phrase-level matching | ~50 lines changed |
| `apps/ai/personal_assistant.py` | SECTION 8 — added 5 more prohibited behaviors | +5 lines |
| `apps/core/ai_orchestrator/cos_context.py` | Mandatory context eval v6 — 6 steps + stronger anti-template | ~30 lines changed |
| `apps/core/ai_orchestrator/cos_context.py` | Consolidated v6 operational rules — 6 rules in single block | ~120 lines (replaced ~90 lines of v5 rules) |

---

## v5 Run 1 Baseline (for comparison when v6 eval runs)

From the v5 evaluation run 1 (valid API responses, before quota exhaustion):

| Question | v5 Score | Key Issue | v6 Fix Applied |
|----------|----------|-----------|----------------|
| Q1 | 2 | "unable to access" via web search bypass | Web search exclusions (v5 fix) |
| Q2 | 8 | ✅ | — |
| Q3 | 7 | ✅ | — |
| Q4 | 2 | Generic formula via web search bypass | Web search exclusions (v5 fix) |
| Q5 | 8 | ✅ | — |
| Q6 | 7 | ✅ | — |
| Q7 | 7 | ✅ | — |
| Q8 | 8 | ✅ CoS voice | — |
| Q9 | 7 | ✅ | — |
| Q10 | 5 | Generic sleep/stress advice | v6 RULE 1 + anti-template |
| Q11 | 6 | Somewhat generic | v6 RULE 5 briefing format |
| Q12 | 2 | Eisenhower Matrix via web search bypass | Web search exclusions (v5 fix) + v6 RULE 1 |
| Q13 | 1 | "I'm here to assist you" via web search bypass | Web search exclusions (v5 fix) + v6 RULE 2 |
| Q14 | 2† | Conversation contamination hallucination | Per-question isolation (eval fix) |
| Q15 | 2† | Conversation contamination hallucination | Per-question isolation (eval fix) |
| Q16 | 7 | ✅ | — |
| Q17 | 7 | ✅ | — |
| Q18 | 1§ | API rate limit fallback | Quota issue |
| Q19 | 8 | ✅ Knowledge grounding | — |
| Q20 | 2 | Eisenhower Matrix via web search bypass | Web search exclusions (v5 fix) + v6 RULE 5 |
| Q21 | 1§ | API rate limit fallback | Quota issue |
| Q22 | 7 | ✅ | — |
| Q23 | 1 | Reflection misclassification | v6 Part 1 reflection fix |
| Q24 | 8 | ✅ CoS briefing | — |

† Conversation contamination — fixed by per-question isolation
§ API rate limit — not a code issue

### Projected v6 Improvements (when eval runs)

Based on the fixes applied:

| Category | v5 Score | Projected v6 | Reason |
|----------|----------|-------------|---------|
| Q1 (weight query) | 2 | 7-8 | Web search exclusion routes to CoS pipeline |
| Q4 (lean body mass) | 2 | 7-8 | Web search exclusion + RULE 6 knowledge grounding |
| Q10 (tiredness) | 5 | 7 | RULE 1 anti-generic + RULE 5 briefing format |
| Q12 (structure day) | 2 | 7-8 | Web search exclusion + RULE 5 briefing format |
| Q13 (greeting) | 1 | 6-7 | Web search exclusion + RULE 2 CoS voice |
| Q14 (encourage) | 2 | 7-8 | Per-question isolation eliminates contamination |
| Q15 (goals matter) | 2 | 7-8 | Per-question isolation + RULE 5 briefing |
| Q20 (focus today) | 2 | 7-8 | Web search exclusion + RULE 5 briefing format |
| Q23 (biggest improvement) | 1 | 7-8 | Reflection fix routes to CoS instead of template |
| Q25-Q28 (new decision Qs) | — | 7-8 | RULE 4 decision mode |

**Projected overall: ~7.0-7.5/10** (up from v5 measured 5.6)

---

## New Evaluation Questions (v6)

### Q25: "I feel tired and worn out. Should I still do my workout today?"
**Expected behavior:** Decision mode — Situation (tiredness + workout outstanding) → Assessment (workout is non-negotiable discipline, but intensity can be adjusted) → Recommendation (do reduced intensity) → A/B/C options

### Q26: "I haven't worked out yet and I'm trying to decide if I should push through or take a break. What do you recommend?"
**Expected behavior:** Decision mode — clear recommendation to push through (workout is non-negotiable), with intensity adjustment option. Must NOT end with "How does that sound?" without a recommendation.

### Q27: "How should I think about my workout versus my bike ride today?"
**Expected behavior:** Distinguish workout (non-negotiable core discipline) from bike ride (optional/bonus). Protect the core habit first.

### Q28: "If I open CoS in the middle of the day, what should the briefing look like?"
**Expected behavior:** Operational briefing — Goals → Goal-supporting actions → Tasks due → Overdue → Maintenance → Recommendation. Today-focused, concise.

---

## Hallucination Protection Status

All v4/v5 protections confirmed intact:
- ✅ `_is_functional_query` calibration suppression — unchanged
- ✅ `AUTHORITATIVE DATA STATE` snapshot — unchanged
- ✅ `ABSOLUTE GROUNDING RULES` — unchanged
- ✅ Web search `PERSONAL_DATA_EXCLUSIONS` — expanded (v5 fix preserved)
- ✅ Personal data query guard in `_generate_response()` — unchanged

---

## Next Steps

1. **Re-run evaluation** once OpenAI API quota resets
2. **Review reflection fix** with actual API responses to confirm Q23 now routes correctly
3. **Assess decision quality** (Q25-Q28) to validate RULE 4 effectiveness
4. **Consider proactive briefing phase** — if v6 eval confirms strong briefing quality, CoS is ready for proactive daily briefing features

---

*Generated by CoS Evaluation Pipeline v6 — 2026-03-07*
*Full 28-question evaluation pending API quota reset*
