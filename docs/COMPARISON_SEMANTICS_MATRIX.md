# Comparison Semantics Matrix

> Knowing *how* to compare is a different capability from knowing *what* to compare. Each
> metric declares its Comparison Semantics; the comparison engine never guesses — it asks
> the domain and executes the contract. Registry: `conversation_object.py ::
> COMPARISON_SEMANTICS`. Engine: `referential.py :: _compare`.

| Metric | Strategy | Confidence | Why this comparison | Customer sees |
|---|---|---|---|---|
| **Glucose** | `average` | high | a single reading swings through the day and rarely reflects control | latest vs recent average, **with the reason** |
| **Steps** | `running_total` | high | steps accumulate through the day | today's total vs yesterday's total |
| **Calories** | `running_total` | high | calories accumulate through the day | today's total vs yesterday's total |
| **Protein** | `running_total` | high | protein accumulates through the day | today's total vs yesterday's / target |
| **Weight** | `latest` | medium | weight is the most recent weigh-in | last weigh-in vs prior weigh-in |
| **Sleep** | `nightly` | medium | one value per night | last night vs the prior night |
| **Blood pressure** | `latest` | medium | compared the most recent readings | latest vs prior reading |

## Why it matters (the headline fix)

**Glucose was comparing point-vs-point** — today's latest reading vs yesterday's latest
reading. Two noisy snapshots; the customer can't make a decision from that. Now glucose
declares `strategy: average`, so the engine compares the latest reading against the recent
average **and explains why**:

> *"That's up 18 mg/dL from your recent average (142 → 160). I compared against your recent
> average because individual glucose readings swing a lot through the day, so a single
> reading rarely reflects your overall control."*

## Acceptance guarantees (regression)

- Glucose **never** defaults to point-vs-point.
- Weight **never** defaults to averages (latest weigh-in).
- Steps / Calories compare **running totals**, not averages.
- Sleep compares **nightly** values.
- Every numeric topic has **declared** semantics (no silent default).

## Confidence

Confidence travels with the comparison (`result["comparison_confidence"]`). `average` /
`running_total` are high-confidence; single-`latest` / single-`nightly` are medium. Beth
prefers the highest-confidence comparison that still fulfills the request.

## Named next

- Per-day **glucose averages** (today's avg vs yesterday's avg) — needs the per-day
  average fact (new retrieval; out of scope this sprint).
- **Finance** windows (daily/weekly/monthly depending on the question).
- **Heart rate** (resting average vs current).
