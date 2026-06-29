# Conversation Object Matrix

> Every deterministic fact Beth answers should be a complete **Conversation Object**:
> primary fact + supporting facts + the natural follow-ups it can answer **from memory**
> (no extra retrieval, query, or LLM). Registry: `apps/ai/chatgpt_cos/conversation_object.py`.
> Generic follow-up handlers live in `conversation_memory.py` and fire when the fact
> carries the needed field. **A fact is not complete until its natural follow-ups answer.**

## Generic follow-up handlers (reusable across ALL domains)

| Handler | Answers | Needs (on the fact / object) |
|---|---|---|
| `compose_when` | "At what time?" | a timestamp (`recorded_at`/`as_of`/`for_date`) |
| `compose_is_current` | "Is that current?" | timestamp + `freshness` |
| `compose_concern` | "Should I be concerned? / Is that good?" | `interpretation` (safety) |
| `compose_meaning` | "Why is that important?" | `interpretation.meaning` |
| `compose_comparison` | "Compared to yesterday / my average?" | a `prior`/`average` **supporting** fact |
| `compose_supporting` | "What did I eat?" (the items behind a total) | a domain **supporting** fact (e.g. `meals`) |
| `compose_why` | "Why do you say that?" | always available (the basis) |

## Matrix (deterministic facts)

| Domain · Primary | Supporting (gathered with the answer) | Natural follow-ups answerable | Missing (Future Backlog) |
|---|---|---|---|
| **Glucose** · `last_glucose_reading` | average (7d), timestamp, interpretation, freshness, confidence | at what time · is that good · should I be concerned · why important · is that current · compared to my average · why | per-reading trend; device source-delay characteristics |
| **Glucose (yesterday)** · `glucose_yesterday` | timestamp, interpretation, freshness | at what time · concern · meaning · current · why | comparison vs day-before |
| **Calories** · `calories_today` | **meals**, **protein**, prior (yesterday), target | what did I eat · how much protein · compared to yesterday · why | remaining-calories · biggest meal |
| **Calories (yesterday)** · `calories_yesterday` | **meals** | what did I eat · why | comparison |
| **Steps** · `steps_today` | prior (yesterday), freshness | compared to yesterday · why | goal/target · weekly trend |
| **Sleep** · `sleep_last_night` | average (7d), timestamp | at what time · compared to my average · why | quality/HRV detail · streak |
| **Weight** · `current_weight` / `weight_yesterday` | timestamp | at what time · why | compared to yesterday/last week · goal/remaining · trend |
| **Protein** · `protein_today` | — | why | compared to yesterday · target/remaining |
| **Blood pressure** · `last_blood_pressure_reading` | timestamp | at what time · current · why | interpretation (band) · comparison |
| **Medications** · `current_medications` / `meds_today` | — | did I take them (meds_today) · why | which/when · adherence trend |
| **Journal** · `journal_today` / `last_journal` | — | when did I last (last_journal) · why | what did I write about · streak |
| **Workout** · `workout_today` / `workout_yesterday` | — | why | what/how long · this-week count |
| **Calendar** · `appointments_today` / `next_appointment` | — | (lists items) · why | with whom · where · history |
| **Goals** · `top_goal` / `active_goal_count` / `goals_overdue` / `next_goal_deadline` | — | why | progress/pace · which goals · deadline detail |
| **Faith / Relationships / Finance / Purpose** (registered domains) | — | why | full Conversation Objects (Layer 2+ rollout) |

## Ranked missing capabilities (highest leverage first)

1. **Comparison / trend** (`compared to yesterday / my average`) — multi-domain (steps,
   calories, weight, sleep, glucose). ✅ **IMPLEMENTED** as a generic handler driven by a
   `prior`/`average` supporting fact; wired for calories/steps/sleep/glucose.
2. **Supporting items** (`what did I eat / which goals / what did I write`) — generic
   `compose_supporting`; ✅ wired for calories→meals (extensible to goals, journal).
3. **Target / remaining** ("what's left today?") — calories/protein/steps vs goal.
4. **Per-domain comparison data for weight** (yesterday/last-week/goal supporting facts).
5. **Interpretation bands for BP** (reuse the clinical-interpretation pattern).

These are added by extending the registry — one row per fact — not by patching
individual questions.

## Future rule (enforced)

When a deterministic fact is added, its Conversation Object spec is **mandatory**: its
declared `follows` must each resolve. Enforced by
`apps/ai/tests/test_conversation_object.py::ConversationObjectCompletenessTests`.
