# Beth Gold-Standard Acceptance

> **The quality bar.** Routing + differentiation are necessary but NOT sufficient.
> An answer can be technically correct and still fail the user. This document
> defines, per high-frequency question, what *unacceptable*, *acceptable*, and
> *gold-standard Chief-of-Staff* answers look like — the target Beth's deterministic
> fallbacks (and LLM-phrased answers) must clear. Enforced by
> `apps/ai/tests/test_beth_gold_standard.py`.
> **Date:** 2026-06-26 · No new architecture — quality only.

## The five quality gates (every answer must clear all five)

1. **Evidence** — cites specifics (a goal/milestone name, a number, a momentum word, a named driver), never pure generality.
2. **Synthesis** — combines ≥2 evidence dimensions into a read, not a single bare fact.
3. **Actionable** — ends with a concrete next step the user can do, not a placeholder.
4. **Non-templated** — no banned generic coaching phrases; references the *specific* subject.
5. **Distinct** — materially different from every sibling intent's answer.

**Banned generic phrases** (a response containing any of these FAILS): "take the
(next/concrete next) step", "make progress", "work on your goal", "advance your
goal", "take one step", "take your first action", "maintain/keep/lock-in
consistency", "maintain/keep momentum", "stay consistent", "stay on track" (as the
*entire* advice), "keep it up", "do your best", "stay focused".

---

## GOALS

### "How is my goal progressing?" → `goals_progress`
- **Unacceptable:** "You're making progress. Keep it up."
- **Acceptable:** "Your France 2027 mission is progressing steadily."
- **Gold:** "France 2027 is in its weight-loss foundation phase and progressing steadily — your weight is trending down and your workouts are on schedule. The next milestone is returning to a running base. Today's lever: complete today's scheduled workout and hit your protein target."
- **Required:** goal name · phase/milestone · a momentum read · a next step.
- **Forbidden:** bare "making progress"; portfolio-only ("you have N goals").
- **Tone:** observant, specific, forward-looking.

### "Am I still on track?" → `goal_on_track`
- **Unacceptable:** "Yes, you're doing fine."
- **Acceptable:** "Yes — France 2027 is on track."
- **Gold:** "Yes — you're on track for France 2027. The evidence: weight trending down and workouts on schedule, with steady momentum. The one thing watching: workout frequency is light, so the next move is to complete today's scheduled workout and hit your protein target."
- **Required:** a yes/roughly/no verdict · evidence · a next move.
- **Forbidden:** vague reassurance with no evidence.
- **Distinct from progress:** leads with a verdict, not a status tour.

### "Why is this goal important?" → `goal_why_priority`
- **Unacceptable:** "Because it's your top goal." / any portfolio metric.
- **Gold:** "France 2027 is your priority because of what it means to you: running the 18K in France with your family and being healthy enough to keep up with your kids for decades. Success looks like crossing that finish line together in 2027."
- **Required:** the user's why_it_matters / success definition (meaning, family, health, values).
- **Forbidden:** active goal count, deadlines, completion %, momentum scores, portfolio.
- **Tone:** reflective, values-anchored — speaks to meaning, not metrics.

### "What could cause this goal to fail?" → `goal_failure_modes`
- **Unacceptable:** "It might not work out." / a progress summary.
- **Gold:** "The most likely ways France 2027 fails: light workout frequency slipping further, missed scheduled sessions, nutrition drifting off plan, momentum fading if the routine lapses, and abandoning the daily habits that drive it. The single best guard today: complete today's scheduled workout and hit your protein target."
- **Required:** a ranked list of specific failure modes · a guard action.
- **Forbidden:** a progress narration; "you have N active goals".
- **Distinct:** a risk-of-failure list, not a status read.

### "How confident are you I'll succeed?" → `goal_confidence`
- **Unacceptable:** "I'm sure you'll do great!"
- **Gold:** "My confidence in France 2027 is solid right now. Strengths: weight trending down and workouts on schedule. The risk: workout frequency is light. What would raise it: complete today's scheduled workout and hit your protein target consistently this week."
- **Required:** a confidence level · strengths · risks · what would raise it.
- **Forbidden:** empty cheerleading; progress narration.

### "What should I do today?" → `goals_focus_today`
- **Unacceptable:** "Work on your goals." / "Make progress today."
- **Gold:** "Today, focus on France 2027. The single highest-leverage move: complete today's scheduled workout and hit your protein target."
- **Required:** ONE concrete, completable-today action tied to the goal.
- **Forbidden:** any banned generic phrase; multiple competing goals.

---

## HEALTH

### "What's my biggest health risk?" → `biggest_health_risk`
- **Gold:** "The one thing worth your attention right now: your blood sugar has been running high lately. A short walk after meals and steadier carb timing is the highest-leverage move."
- **Required:** ONE named risk · why it matters · a concrete action.
- **Forbidden:** a list; bare "watch your health".

### "How am I doing overall?" / "Am I making progress?" → `overall_progress`
- **Gold:** "Your weight is 248 lb and trending down, about 8 from your goal. Glucose is around 165 (a little high), and sleep is averaging 6.2 hours (a bit short). The main thing to nudge next: your blood sugar."
- **Required:** ≥2 metrics with reads · a next focus. **Distinct:** multi-metric summary, not a single risk.

### "What should I focus on today?" → `health_focus_today`
- **Gold:** "Today, focus on your blood sugar. Acting on it keeps it from compounding. One concrete step: take a 15–20 minute walk after your biggest meal."
- **Required:** ONE focus · why today · a concrete 24h action.

### "What are my concerns?" → `health_concerns`
- **Gold:** a ranked list (≥2) of named concerns, each with a what-to-do. **Distinct:** a survey, not a single headline.

---

## RHYTHM

### "What should I do next?" → next_rhythm
- **Gold:** names the actual next scheduled item with its time; never a goal lecture.

### "Check in." (and the daily agenda) → clarification → daily agenda
- **Gold (daytime):** "Coming up today you have your 7am workout and 12pm lunch. Your highest priority is the workout. Your best next step is to begin it."
- **Gold (evening, 8pm+):** "It's getting late, so let's wrap up well. The best use of tonight is to wind down — journal a few lines, prepare for tomorrow, and protect your sleep. Tomorrow's first priority looks like your workout — rest up for it."
- **Required (evening):** wind-down / sleep / journal / tomorrow. **Forbidden (evening):** "begin <morning activity>", "Next up: Workout".

### "Full whole-life check-in." → daily agenda / executive read
- **Gold:** a synthesized read across schedule + the top goal + the top risk, ending with one next step — not a single-domain answer.

---

## EXECUTIVE (cross-domain — answered today via the Goals strategic layer)

> Executive cross-domain composition is a deferred roadmap item; until then these
> route to the Goals strategic intents (per `BETH_DOMAIN_DEPENDENCY_GRAPH.md`:
> prioritization & overall progress are owned by Goals).

- **"How am I doing overall in life?"** → `goals_progress` (overall): a synthesized read of the headline goal + momentum + the one thing to nudge.
- **"What should I prioritize?"** → `goals_focus_today`: the single highest-leverage action.
- **"What am I neglecting?"** → `goal_concerns`: the goals actually slipping (drifting/stalled/failing) — honest "nothing slipping" when all healthy.
- **"What concerns you most?"** → `biggest_goal_risk`: the single biggest real risk (or "no significant risks" + watch item when healthy).
- **Required across all:** evidence + synthesis + one concrete next step. **Forbidden:** generic life-coach platitudes.

---

## How the suite enforces this

`test_beth_gold_standard.py` runs each question's deterministic answer and asserts:
the five gates (evidence/synthesis/actionable/non-templated/distinct), the
per-question required concepts present, the forbidden concepts absent, and pairwise
material distinctness across sibling intents. A response that "sounds templated,
repeats generic coaching phrases, lacks synthesis, lacks evidence, lacks actionable
guidance, or is indistinguishable from another intent" FAILS the build.
