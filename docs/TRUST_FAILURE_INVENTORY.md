# Trust Failure Inventory — Sprint #1

> Classified by **what made the customer lose confidence**, not by code. Clustered so we
> fix *capabilities*, not symptoms.

## The five production trust failures → three capabilities

| # | Trust failure | Customer reaction | Capability (root) |
|---|---|---|---|
| TF1 | Referential timeline (today→yesterday→day-before→last week→last month) | "I shouldn't have to restate the topic." | **Frame Resolution** (timeline depth) |
| TF4 | Topic awareness ("Is that an average?" → Beth asks for clarification) | "Why did she answer that?" | **Frame Resolution** (meta-questions) |
| TF5 | Human conversation ("what changed?", "anything else?", "go deeper", "should I worry?") | "I shouldn't have to spell it out." | **Frame Resolution** (conversational patterns) |
| TF2 | Conversation-object completeness (glucose lacks average/yesterday/trend on hand) | "That doesn't seem complete." | **Supporting-Fact Completeness** |
| TF3 | Presentation consistency (raw structures / internal names / dense reporting) | "That doesn't read like a person." | **Presentation Enforcement** |

**Key insight:** TF1, TF4, TF5 are the *same capability* — resolving a natural utterance
against the active Conversation Object's frame. They are not three fixes; they are one
capability with three reference types (timeframe, meta, pattern).

## What this sprint implements

1. **Topic-Aware Meta Resolution** (TF4) — "Is that an average? / a single reading?"
   answered from the active fact's nature, and the recent average offered alongside.
   Never a clarifying question.
2. **Conversational Pattern Resolution** (TF5) — "what changed? / what caused that?" →
   the deterministic comparison; "anything else? / go deeper" → the remaining supporting
   facts. Reusable across every topic, not isolated fixes.
3. **Presentation Consistency guard** (TF3) — a regression asserting no deterministic
   answer leaks an internal field name or a raw structure.

## Deferred to the next Trust Sprint (named, with trigger)

- **TF1 deep timeline** ("day before yesterday", "last month") — needs date-parameterized
  historical retrieval per domain (Layer 1 `history.py`/`periods.py`). This sprint stops
  the *drift* (deep-timeline references stay on-topic and answer honestly instead of
  switching subjects), but real N-day-ago / N-month-ago answers are the next sprint.
  **Trigger:** wire `answer_metric_for_date(user, topic, date)` over DailyHealthQueries.
