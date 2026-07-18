# WLJ Deterministic Truth Layer — Operator Acceptance Guide

**Purpose:** the permanent manual certification instrument for the deterministic Truth Layer.
This is the final human sign-off before the Truth Layer is approved and the Chief-of-Staff
CRUD milestone is authorized.

**How to use it**
1. Ask the Chief of Staff the **Discovery Prompt** exactly as written.
2. Read the response and compare it, item by item, against the **Expected Information** checklist.
3. Mark each item:
   - **✓ Present** — the information appears naturally in the answer and is correct.
   - **✗ Missing** — WLJ stores this for the object, but the answer left it out → **Truth Layer bug.**
   - **⚠ Incorrect** — it appears but the value/label is wrong → **Truth Layer bug.**
   - **N/A** — the object legitimately has no value for this item (e.g. a weigh-in with no note).
4. Check the **Should NEVER appear** guards. Anything listed there showing up is a **Truth Layer bug.**
5. Record every ✗ / ⚠ as a bug against the object's provider/composer (not as a reasoning issue).

> An item is only **N/A** when the object *genuinely has no such data*. If WLJ stores it and it is
> absent, it is **Missing**, not N/A. When unsure, treat it as Missing and file the bug.

The machine-checkable source of these prompts + expected truths lives at
`apps/core/truth/discovery_suite.py` (kept in sync with this guide by `test_discovery_suite.py`).

---

## Global rules — should NEVER appear in ANY answer
These apply to every object below (in addition to each object's own guards):
- Database field names, model names, or internal identifiers (UUIDs, primary keys, sync ids).
- Internal hashes, fingerprints, embeddings, or search-index data.
- Signed / expiring storage URLs or secret links.
- Cache state, processing/queue state, or migration/bookkeeping fields.
- Any value labeled with the wrong unit.

---

# BODY & VITALS

## Weight
**Prompt:** *"Tell me everything you know about my latest weigh-in."*
**Expected Information**
- □ Current weight
- □ Units (lb / kg)
- □ Date recorded
- □ Time recorded
- □ How it was entered (Apple Health, manual, InBody, scale, etc.)
- □ Body fat percentage
- □ Lean body mass
- □ Any notes
- □ Recent weight trend

## Blood Pressure
**Prompt:** *"Tell me everything you know about my most recent blood pressure reading."*
**Expected Information**
- □ Systolic and diastolic
- □ Pulse
- □ Date and time
- □ Context (resting, after exercise, etc.)
- □ Which arm
- □ Body position (seated, lying down)
- □ Any notes
- □ How it was entered (device / manual)
- □ Recent blood-pressure trend

## Glucose
**Prompt:** *"Tell me everything you know about my most recent glucose reading."*
**Expected Information**
- □ The value **with its correct unit** (mg/dL or mmol/L)
- □ Date and time
- □ Context (fasting, after a meal, etc.)
- □ Trend direction and rate
- □ Device / source (Dexcom, manual, Apple Health)
- □ Any notes
- □ Recent glucose trend
**Should NEVER appear**
- A value shown in the wrong unit, or a trend that mixes mg/dL and mmol/L readings together.

## Body Measurements
**Prompt:** *"Tell me everything you know about my most recent body measurement session."*
**Expected Information**
- □ The date of the check-in
- □ A title for the session (if given)
- □ How it was recorded (source)
- □ Every measurement captured (waist, body fat %, lean mass, chest, hips, etc.) with units
- □ Any notes on individual measurements
- □ How each measurement is trending over time

## Sleep
**Prompt:** *"Tell me everything you know about how I slept last night."*
**Expected Information**
- □ The date
- □ Bedtime and wake time
- □ Time asleep and time in bed
- □ Sleep stages (deep, REM, light, awake)
- □ Sleep efficiency
- □ Sleep quality
- □ Heart rate (average, min, max)
- □ Heart rate variability (HRV)
- □ Respiratory rate
- □ Interruptions / time awake
- □ Caffeine and mindful minutes (if recorded)
- □ Any notes
- □ Contributing factors (if recorded)
- □ Source (Apple Health, etc.)

## Steps / Activity
**Prompt:** *"Tell me everything you know about my activity yesterday."*
**Expected Information**
- □ Step count
- □ Step goal
- □ Distance
- □ Calories burned
- □ Resting calories
- □ Flights climbed
- □ Exercise minutes
- □ Stand hours
- □ Any notes
- □ Source

---

# NUTRITION & MEALS

## Meals (most recent food)
**Prompt:** *"Tell me everything you know about the last thing I ate."*
**Expected Information**
- □ The food name and brand
- □ Which meal (breakfast / lunch / dinner / snack)
- □ Date and time
- □ Serving size and quantity
- □ Calories and macros (protein, carbs, fat, fiber, sugar)
- □ Micronutrients (sodium, cholesterol, potassium, saturated fat)
- □ Where the nutrition data came from
- □ How it was logged
- □ Whether it's a favorite
- □ Context (location, eating pace, hunger/fullness, mood) if recorded
- □ Any notes

## Yesterday's Nutrition
**Prompt:** *"Tell me everything you know about my nutrition yesterday."*
**Expected Information**
- □ Total calories
- □ Total protein, carbs, and fat
- □ Each meal and the foods in it
- □ How it compares to my dietary targets

## Last time I ate a food
**Prompt:** *"When did I last eat pizza, and what do you know about it?"*
**Expected Information**
- □ The specific item (and brand)
- □ The date
- □ Which meal
- □ Its calories and macros
- □ Serving info

## Dietary Profile
**Prompt:** *"Tell me everything you know about my current dietary profile."*
**Expected Information**
- □ Daily carb limit
- □ Daily protein target
- □ Daily calorie target
- □ Daily fat limit
- □ Dietary flags / preferences
- □ Whether I'm diabetes-sensitive

---

# FITNESS

## Workouts
**Prompt:** *"Tell me everything you know about my most recent workout."*
**Expected Information**
- □ The date and start time
- □ Workout type / mode
- □ Duration
- □ Calories, distance, average heart rate, intensity (as applicable)
- □ Every exercise, with its sets, reps, and weights
- □ Any personal records
- □ Any notes
- □ Source

## Named session
**Prompt:** *"Tell me everything you know about my last squat session."*
**Expected Information**
- □ The date
- □ Squat sets, reps, and the actual load used (not bodyweight)
- □ Any personal record
- □ Total volume
- □ Any notes

---

# MEDICATIONS

## Medications
**Prompt:** *"Tell me everything you know about my Metformin."*
**Expected Information**
- □ Dose and unit
- □ What it's for
- □ Category (prescription, supplement, etc.)
- □ Frequency
- □ The full schedule — the times **and which days**
- □ Instructions (e.g. take with food)
- □ Start and end dates
- □ Monitoring requirements
- □ Adherence over the last 7 / 30 / 90 days
- □ When I last took it
- □ Refill status (supply, whether it needs a refill, whether one was requested)
- □ Paused status and reason (if paused)
- □ Prescriber
- □ Pharmacy
- □ Prescription number
- □ Any notes

---

# GOALS, MISSIONS, MILESTONES & HABITS

## Goals / Missions
**Prompt:** *"Tell me everything you know about my France 2027 mission."*
**Expected Information**
- □ Title and status
- □ Why it matters
- □ What success looks like
- □ Target date and time remaining
- □ Milestones — completed, overdue, and what's next
- □ Overall progress
- □ Momentum, and what's improved vs. still needs work
- □ My reflection and motivation note
- □ Commitment level and timeframe
- □ The annual direction it ladders up to
- □ Victory milestones
- □ Linked habits
- □ Any motivation links
- □ A hero image (if set)

## Milestones
**Prompt:** *"Tell me everything you know about my most recently completed milestone."*
**Expected Information**
- □ The milestone
- □ Which goal it belongs to
- □ When it was completed
- □ Any target it was measuring

## Annual Direction
**Prompt:** *"Tell me everything you know about my word and theme for this year."*
**Expected Information**
- □ The year
- □ My word of the year
- □ Why I chose that word
- □ The theme and its description
- □ The anchor scripture / quote and its source
- □ Whether it's the current year

## Habits
**Prompt:** *"Tell me everything you know about my reading habit."*
**Expected Information**
- □ Its purpose and success criteria
- □ How it's measured and how often
- □ The target
- □ Current streak and longest streak
- □ Whether it's at risk
- □ Completion rate
- □ Recent entries (with notes, duration, or count)
- □ Linked goals
- □ The annual direction it supports

---

# JOURNAL

## Journal Entries
**Prompt:** *"Tell me everything you know about what I journaled yesterday."*
**Expected Information**
- □ The entry's content
- □ Its title
- □ My mood
- □ Emotions
- □ Tags
- □ Categories
- □ The prompt that inspired it (if any)
- □ Any recurring themes or extracted insights
**Should NEVER appear**
- Audio exposure, mobility / walking speed, or any other health-sensor telemetry.
- Any record that is not a journal entry (meals, workouts, tasks, etc.).

## Journal Themes
**Prompt:** *"What have I been writing about lately, and what keeps coming up?"*
**Expected Information**
- □ My most frequent topics / tags
- □ Repeated emotions or concerns
**Should NEVER appear**
- Any non-journal record or sensor data.

---

# PEOPLE & RELATIONSHIPS

## People
**Prompt:** *"Tell me everything you know about Heather."*
**Expected Information**
- □ Our relationship
- □ Contact info (email, phone)
- □ Household
- □ Groups she belongs to
- □ When I last connected and how long it's been
- □ How often we interact
- □ My notes about her
- □ Recent interactions (what we did)
- □ Journal entries that mention her
- □ Memories involving her
- □ Goals involving her
- □ Trips or places we've shared
- □ Events involving her
- □ Her upcoming birthday
**Should NEVER appear**
- Internal identifiers, database keys, or embeddings for the person.

## Most Important People
**Prompt:** *"Who are the most important people in my life right now?"*
**Expected Information**
- □ The top people
- □ How often I interact with each
- □ When I last connected with each

## Upcoming Birthday
**Prompt:** *"Whose birthday is coming up?"*
**Expected Information**
- □ Whose birthday
- □ The date
- □ How many days away

---

# LEGACY

## Legacy People / Family
**Prompt:** *"Tell me everything you know about my grandfather."*
**Expected Information**
- □ Name and also-known-as
- □ Relationship to me
- □ Birth and death
- □ Their biography
- □ Their significance
- □ Memories they appear in
- □ The family relationships — who they're connected to (with any notes)
- □ Preserved facts (career, faith, military, etc.)
- □ A portrait (if stored)

## Childhood Memories
**Prompt:** *"Tell me everything you know about my childhood."*
**Expected Information**
- □ The childhood-era memories
- □ When each occurred
- □ People and places in them

## Legacy Memories (most recent)
**Prompt:** *"Tell me everything you know about the last memory I recorded."*
**Expected Information**
- □ The story / narrative itself
- □ The type of memory
- □ When it occurred
- □ People in it (and their roles)
- □ Places
- □ Life milestones it belongs to
- □ Attached media (photos with captions and dates, audio)
- □ Its significance
- □ Who contributed or is attributed

## Places
**Prompt:** *"What places have special meaning to me?"*
**Expected Information**
- □ Each place's name and location
- □ Its description
- □ Coordinates or a map link
- □ A photo (if stored)
- □ Its significance
- □ Memories tied to it

---

# FAITH

## Reading Plans
**Prompt:** *"Tell me everything you know about my current Bible study."*
**Expected Information**
- □ The plan title and category
- □ Its duration
- □ What day I'm on
- □ My progress
- □ Today's reading
- □ The reminder time
- □ My per-day reflection notes

## Prayer Requests
**Prompt:** *"Tell me everything you know about my most recent prayer request."*
**Expected Information**
- □ What I'm praying about
- □ Its priority
- □ Who or what it's for
- □ When I recorded it
- □ Whether it's answered
- □ Answer notes (if answered)
- □ Whether it reminds me daily

## Reading Consistency
**Prompt:** *"How consistent has my Bible reading been?"*
**Expected Information**
- □ Days read over the period
- □ My streak / days since last reading

---

# CALENDAR

## Today's Schedule
**Prompt:** *"Tell me everything you know about my schedule today."*
**Expected Information**
- □ Each event's title
- □ Start and end times
- □ Whether it's all-day
- □ Which life domain it belongs to
- □ Commitment level
- □ Status
- □ Whether it's protected
- □ Description
- □ Recurrence details (including its timezone) if it repeats

## Next Meeting
**Prompt:** *"Tell me everything you know about my next meeting."*
**Expected Information**
- □ Title
- □ When it starts and ends
- □ Duration
- □ Which life domain
- □ Commitment level
- □ Description
- □ Recurrence (if any)

---

# TASKS

## Next Task
**Prompt:** *"What should I work on next, and what do you know about it?"*
**Expected Information**
- □ The recommended next action
- □ Why it's next
- □ Its due date, priority, and context

## Oldest Overdue Task
**Prompt:** *"Tell me everything you know about my oldest overdue task."*
**Expected Information**
- □ The task
- □ How overdue it is
- □ Its due date
- □ Priority and commitment level
- □ The project it belongs to
- □ Its module / area
- □ Effort
- □ Progress
- □ Scheduling / recurrence
- □ Any dependency it's waiting on
- □ Partial-progress notes
- □ Any notes

---

# PROJECTS

## Projects
**Prompt:** *"Tell me everything you know about my most active project."*
**Expected Information**
- □ Title
- □ Description and purpose
- □ Priority
- □ Category and tags
- □ Target and start dates
- □ Whether it's overdue
- □ Task counts and progress
- □ A cover image (if set)
- □ Any reflection

---

# SIGNIFICANT EVENTS

## Significant Events
**Prompt:** *"Tell me everything about my upcoming anniversaries and important dates."*
**Expected Information**
- □ Events of **every type** — anniversaries, memorials, milestones, holidays, and others (not just birthdays)
- □ Each event's title
- □ Its date and how many days away
- □ The year it began
- □ The person it's linked to
- □ Its description and any custom message

---

# CAPTURE

## Captures
**Prompt:** *"Tell me everything you know about my most recent capture."*
**Expected Information**
- □ Its title
- □ Category / subcategory
- □ When it was captured
- □ Its duration
- □ Its processing status
- □ The transcript
- □ The summary
- □ Any extracted signals
**Should NEVER appear**
- Signed or expiring audio URLs / secret storage links.

---

# NOTES

## Notes
**Prompt:** *"Tell me everything you know about my most recent note."*
**Expected Information**
- □ Its title
- □ The note content
- □ Tags
- □ Color
- □ Whether it's pinned
- □ What it's attached to
- □ When it was created and last updated

---

# BRAIN TRAINING

## Brain Training Sessions
**Prompt:** *"Tell me everything you know about my most recent brain training session."*
**Expected Information**
- □ Which game and category
- □ Difficulty
- □ When I played
- □ Time spent
- □ Score
- □ Mistakes
- □ Hints used
- □ Status
**Should NEVER appear**
- The puzzle's solution or answer key.

---

# MEDICAL / LABS

## Lab Results
**Prompt:** *"Tell me everything you know about my most recent lab results."*
**Expected Information**
- □ Each test name and its value with units
- □ The reference range
- □ Whether it's normal or abnormal (and how)
- □ The result status (final, preliminary)
- □ When it was collected and reported
- □ The test category / what it measures
- □ How the value has trended over time
- □ The ordering provider
- □ Which panel it belongs to and the source document
- □ Any notes
**Should NEVER appear**
- Internal file hashes, raw OCR/extracted text, or internal document identifiers.

## Lab Panels
**Prompt:** *"Tell me everything you know about my last blood panel."*
**Expected Information**
- □ The panel name and type
- □ When it was collected
- □ The ordering provider
- □ Every result in it (value, unit, normal/abnormal)
- □ How many were abnormal

---

## Certification sign-off

| | |
|---|---|
| Tester | ___________________ |
| Date | ___________________ |
| Objects passing with zero bugs | ____ / 40 |
| Truth Layer bugs filed | ___________________ |
| **Truth Layer approved for CRUD milestone?** | ☐ Yes ☐ No |

*Approve only when every object passes with zero **Missing** and zero **Incorrect** items, and
no **Should NEVER appear** guard is violated.*
