# Document 3 — Dynamic Evidence Retrieval Framework

**Purpose:** Define how ChatGPT decides *what additional deterministic truth to retrieve* — the engine behind Stages 4–6 of the reasoning loop. This is the difference between a shallow single-domain answer and a genuinely holistic one, without degenerating into "fetch everything every time."

**Three questions the framework answers, on every Deliberate turn:**
> What do I already know? · What else do I need? · Where does that truth live — and is it reachable?

---

## 1. The Retrieval Decision Procedure

```
SCOPE (from Doc 2 matrix: what evidence types does this intent need?)
  │
  ▼
INSPECT KNOWN  ── standing context already covers it? ──▶ yes → use it (no fetch)   [State-First Reads]
  │ no
  ▼
RANK CANDIDATES by  expected causal value  ÷  retrieval cost
  │
  ▼
RETRIEVE the top candidate  (a BACKED tool first; Doc 2 catalog)
  │
  ▼
UPDATE BELIEF  ── did it explain / resolve the question at target confidence? 
  │                         │
  │ yes → STOP             │ no
  ▼                         ▼
ANSWER             SUFFICIENCY GATE  ── any candidate left  AND  budget remaining
                            AND  marginal value still high? 
                                  │ yes → loop back to RETRIEVE
                                  │ no  → STOP and answer with explicit gaps
```

The loop is **belief-driven**: each retrieval updates what ChatGPT believes the answer is, and the next choice is the evidence most likely to *change* that belief.

---

## 2. Evidence Ranking — Causal Value ÷ Cost

ChatGPT orders candidate evidence by a qualitative ratio, not a fixed sequence.

**Causal value (higher = fetch sooner):**
1. **Focal-domain state** — the domain the question is *about* (weight question → health). Always first.
2. **Domains with a known deterministic linkage** to the focal domain — e.g., for weight, the BACKED composer already encodes sleep/nutrition/workouts/glucose/medication as linked (`deterministic_router.py:6308`). Fetch these next; they have *system-acknowledged* causal relevance.
3. **Domains flagged in standing signals** — if the top-signals package already shows "sleep degraded" or "execution overload," that domain jumps the queue (the system has already pre-surfaced it as notable).
4. **Distal domains** (stress/journal, travel, routine, relationship, calendar, faith) — fetched only when 1–3 don't explain the change. These are the *stranded* factors: deterministically computed but not pre-linked, so they carry lower prior causal value and must be synthesized carefully.

**Cost (higher = fetch later / only if needed):**
- Cheap: standing context (free), single SAE metric, a BACKED composer call.
- Moderate: a full `get_module_state` for an additional domain.
- Expensive / unreliable: UNWIRED search tools (capture/notes) and time-series history — these also carry a *reach risk* (may return nothing because they're not wired), so they sit last and their absence must not be read as "no cause here."

**Rule:** never fetch a distal/expensive candidate before exhausting the cheap, high-value, BACKED ones. This keeps the common diagnostic cheap and the rare deep one thorough.

---

## 3. The Widening Ladder (Diagnostic Retrieval)

For "Why has X changed?" the CoS climbs a ladder, stopping at the first rung that explains the change at target confidence:

| Rung | Evidence | Backing | Behavior on a hit |
|------|----------|---------|-------------------|
| 0 | Standing context + top signals | BACKED | If a signal already names the cause → answer (high confidence) |
| 1 | Focal-domain full state | BACKED | If focal state shows the mechanism → answer |
| 2 | System-linked domains (focal's known correlates) | BACKED | Use the existing composer if the focal domain has one (weight) |
| 3 | Adjacent domains surfaced by signals/situation | BACKED | Add as contributing evidence |
| 4 | Distal/stranded domains (stress, travel, routine, exec-overload, relationship, calendar, faith) | STRANDED | Retrieve each domain's state; synthesize correlation → label "I suspect" |
| 5 | History (analogs, prior interventions) | BACKED(time)/UNWIRED(keyword) | Corroborate or temper the hypothesis |

Most physical-health diagnostics resolve by rung 2–3. Genuinely holistic "why am I off" questions climb to rung 4–5 — which is exactly where the audited coverage gaps live, so the answer's confidence is bounded there.

---

## 4. Stopping Criteria

The loop terminates when **any** of these is true:

1. **Confidence target met** — the working hypothesis reaches "I know" or a strong "I suspect" (Doc 6) and further evidence is unlikely to overturn it.
2. **Marginal value collapse** — the next-best candidate's expected belief-change is low (the remaining evidence is weakly linked or redundant).
3. **Reach exhaustion** — all *reachable* (BACKED) candidates are consumed; only STRANDED/UNWIRED candidates remain. The CoS stops and answers with an explicit "what I couldn't check" note — it does **not** invent the missing piece.
4. **Budget bound** — a turn-level retrieval ceiling (breadth cap) is hit. The CoS answers with current evidence and flags incompleteness.

**Anti-patterns the criteria prevent:**
- *Premature stop* — answering "it's your sleep" after rung 1 without checking linked domains.
- *Infinite widening* — retrieving every domain for every question.
- *Silent truncation* — stopping at reach exhaustion but presenting the partial answer as complete (forbidden; criterion 3 forces disclosure).

---

## 5. Escalation Rules

When evidence is insufficient or conflicting, ChatGPT escalates rather than guessing:

| Situation | Escalation behavior |
|-----------|---------------------|
| Reachable evidence exhausted, cause still unclear | State the leading hypothesis + the specific evidence that *would* resolve it ("I can't see your routine adherence here — that's the gap") |
| Conflicting deterministic evidence (e.g., nutrition compliant, sleep degraded) | Present both, weight by causal linkage, do not average (Doc 4 §conflict) |
| A needed tool is STRANDED/UNWIRED | Name the limitation explicitly; downgrade to "I suspect"; offer what *is* known |
| Question requires data WLJ doesn't compute (ABSENT) | "I cannot determine this from your data" — never fabricate |
| User asserts a fact contradicting provider truth | Surface the deterministic value; flag the contradiction (Law 16 contradiction handling) |

---

## 6. Confidence Thresholds Driving Retrieval

Retrieval depth is governed by *target confidence for the category*:

- **Scalar/Status/Execution/Risk/Fix** → target = canonical; one BACKED read suffices; no widening.
- **Diagnostic** → target = "strong suspicion with named evidence"; widen until rung 2–4 supports a leading cause or reach exhausts.
- **Predictive** → target = "model says, with stated confidence"; one prediction read + one analog.
- **Coaching** → target = "whole-self informed"; breadth over depth — a light read across many domains beats a deep dive into one.

The threshold is *lower for breadth-first coaching* (you need enough of the person to be wise, not exhaustive proof) and *higher for diagnostic causality* (you must not assert a cause you haven't evidenced).

---

## 7. Worked Trace — "Why has my weight loss slowed?"

```
SCOPE      → diagnostic; focal = weight; linked = sleep/nutrition/workouts/glucose/medication; distal = stress/travel/routine/exec/relationship/calendar/faith
INSPECT    → standing vitals show weight trend flat; top signals show nothing conclusive
RUNG 1     → get_health_context → weight/glucose normal, sleep slightly down       (belief: maybe sleep)
RUNG 2     → get_root_cause_assessment(weight)  [BACKED] → names sleep + nutrition within its 5-domain aperture (belief firms: sleep + nutrition adherence)
SUFFICIENCY→ leading cause supported, but holistic scope not yet covered; marginal value of distal still moderate
RUNG 4     → get_module_state(routine), (journal/stress), (calendar)  [STRANDED] → routine adherence down, stress_score up, calendar dense
RECONCILE  → physical (sleep/nutrition) = primary, system-certified; life factors (routine/stress/calendar) = contributing, correlation-only
STOP       → reach of BACKED + key STRANDED consumed; remaining (travel/relationship/faith) low marginal value
ANSWER     → "Primary driver looks like reduced sleep + slipping nutrition adherence (high confidence — your data shows it). Contributing, but I'm less certain: your routine adherence dropped and journal stress rose the same weeks, with a heavier calendar — these correlate but I can't prove causation. I couldn't check travel/relationships here."
```

This trace is the framework's intent in miniature: **start canonical, widen deliberately, stop honestly, and label the seam between certified cause and synthesized suspicion.**

---

*Document 3 of 6. The reconciliation and causal-confidence rules referenced above are specified in Document 4.*
