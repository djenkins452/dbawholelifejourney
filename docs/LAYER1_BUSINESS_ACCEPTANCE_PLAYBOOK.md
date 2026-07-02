# Layer 1 Business Acceptance Playbook

**Status:** Permanent WLJ architecture. Part of the
[Layer 1 Domain Framework](LAYER1_DOMAIN_FRAMEWORK.md).

> This is **not a list of test cases.** It is the **way of thinking** a developer must adopt
> when validating a Layer 1 domain. Test cases live in the acceptance suite and grow forever;
> this teaches the mindset that generates them and knows when to stop.

---

## The core stance: you are not testing code. You are trying to disappoint a customer.

Engineering acceptance asks "does the code do what I built it to do?" Business acceptance asks
"**will a real person trust this?**" Those are different questions, and the second is the one
that matters. A domain can be green on every unit test and still fail the customer — because
the unit tests assert what you *thought* to build, and the customer asks what you *didn't*.

So the acceptance mindset is adversarial toward your own work: **your job is to find the
question that embarrasses the domain**, and keep finding them until you honestly can't.

---

## The five lenses

Run every domain through all five. They surface different failures.

### 1. Think like a customer

Ask the questions a paying customer would ask, **in their words**, not yours. Not
`current_medications` — "what am I taking?" Not `adherence_7d` — "am I actually taking my
meds?" The customer doesn't know your fact keys, your intents, or your schema. They know their
life. If a natural phrasing of a real need returns the wrong thing or nothing, that is a defect
even if every internal name is spelled correctly.

The customer also asks the **specific** form, not just the general one. "What am I taking?" and
"What's my Metformin dose?" are both natural. A domain that answers the first but not the
second is incomplete — Medication's biggest maturity jump was discovering that single-entity
retrieval was missing behind complete entities.

### 2. Think like Danny

Danny is the demanding customer who knows the product should be excellent and will not accept
"technically correct." Thinking like Danny means:

- **Correct-but-useless fails.** "Your sleep is trending down. A good next step: an earlier
  wind-down." is true and read like a shrug — no evidence, no concrete action, no *why*. That
  failed acceptance (Run #62) *because* Danny wouldn't accept it, even though the fact was
  right.
- **Symmetry is expected.** If prescriptions get adherence, supplements should too. Danny will
  ask "what's my supplement adherence?" and a list of supplements is a wrong answer.
- **The follow-up is part of the answer.** Danny asks "what about yesterday?" then "compared to
  my average?" A domain that drops the thread has failed even if each isolated answer is right.

### 3. Attempt to break the capability

Before declaring a domain done, **become the customer and run a large natural-question set with
the intent to break it.** This is not optional garnish — it is the step that finds the real
gaps. Medication was declared "complete" (four entities, dose-level execution) and the break
attempt immediately exposed four missing capabilities: single-entity retrieval, symmetric
categories, the combined "what am I taking?" view, and "what's left today?". The entities were
complete; the *retrieval surface around them* was not — the same root cause behind every prior
report.

Break-attempt techniques:

- **Mis-tag the data.** Tag a supplement as a prescription and confirm the vocabulary still
  holds (the classifier is the final authority, not the DB row).
- **Ask the adjacent question.** If you built "what's my dose", ask "when did my dose *change*"
  — a different intent that the "dose" cue must not swallow.
- **Ask the negative / empty case.** "Am I taking X" for something you're not; a day with
  nothing logged (a real `0`, never "unknown").
- **Disable the snapshot.** Patch the SAE to raise and confirm the domain still answers.
- **Repeat the identical question.** Same question, unchanged data → identical answer (Law 5).

### 4. Test natural business questions

Validate against the questions the *business* has, phrased naturally, spanning the entity's
whole life:

- **Inventory** — what do I have? (each category, and combined)
- **Execution** — did I do it today? what's left?
- **Performance** — how's it going over time? (and for a single entity, not just overall)
- **Definition** — what's the dose / target / cadence?
- **History** — when did it start / change / stop?
- **Mapping** — which of these are for \<condition / goal / purpose>?

If your question list only covers "inventory + overall performance," you have tested a fraction
of the domain. The entity has six dimensions; the questions must span them.

### 5. Follow conversational threads

Customers converse; they don't issue isolated queries. Validate the **thread**, not just the
turn:

- The anchor must not drift ("what's my BG?" → "yesterday?" → "compared to today" must
  re-center on the current reading, not stay on yesterday).
- A comparison goal must *produce a comparison*, not two lists.
- "Why?" / "what changed?" / "anything else?" must resolve from the conversation object, not
  cascade to a generic fallback.

A domain that answers every single question perfectly but loses the second turn of every
conversation has failed business acceptance.

---

## When do you stop?

> **Continue until you struggle to find another reasonable business question.**

Not until the tests pass. Not until you're tired. Until you, sitting there as the customer,
genuinely cannot think of another natural thing to ask about this domain. That struggle is the
signal — it means the question space is covered, not that your patience ran out. If you can
still think of questions, you are not done, regardless of the green suite.

When you reach that point, the *last* few questions you had to strain to invent are usually the
edge of the domain's real scope — record them, and if they're legitimately out of scope, say so
explicitly (a phased deferral with a trigger, never "maybe someday").

---

## The rules that keep acceptance honest

- **Acceptance validates the product, not the code.** Assert against the *rendered answer a
  customer reads*, and against the real evaluator (the acceptance `gates` / `is_actionable` /
  banned-phrase rules) — not a hand-rolled substring you'll drift from.
- **Every production defect becomes a permanent regression.** The moment a real conversation
  fails, the exact case is frozen in the suite forever. This is how the suite grows to match
  reality and how a fixed bug can never silently return.
- **A green test that asserts wrong behavior is worse than no test.** When you fix behavior,
  fix the tests that encoded the old behavior — don't preserve a lie because it's green.
- **Production is the final authority.** Repository evidence forms the hypothesis; the live
  conversation is the verdict. "It should work" is not "it works."
- **Infrastructure honesty.** Distinguish a content defect on a healthy path from an infra
  outage. A failing acceptance run reports empty-responses, OpenAI-failures, and whether it is
  trustworthy — fix the thing that actually broke.
- **Root cause, not wording.** When a question fails, find *why* (truth? retrieval? routing?
  response shape? vocabulary?) and fix the class of defect, not the one phrasing. Run #62 was
  a fallback-*shape* defect, not a sleep-question wording patch — the fix improved every
  health-risk answer, not one sentence.

---

## The acceptance debrief (end every domain sprint with this)

Answer these out loud before you call a domain done. They shape the recommendation; they are
not busywork:

1. Which of the five lenses did I actually run — or did I only "think like a customer" and skip
   the break attempt?
2. What was the last question I had to strain to invent? (If it was easy, I stopped too early.)
3. Does every dimension of the entity have at least one natural question in the suite?
4. Did I test the second and third conversational turn, or only isolated questions?
5. Is every production defect for this domain frozen as a regression?
6. Did I assert the rendered answer against the real evaluator, or a substring I made up?
7. Would *Danny* accept this — or is it merely correct?

If any answer is uncomfortable, the domain is not ready.

---

*Origin: the Medication acceptance journey — the "become Danny and try to break it" maturity
gate, Run #62 (correct-but-not-actionable), the supplement mis-tag trust failure, and the
conversation-thread capabilities (Conversation Object, Goal, Active Subject).*
