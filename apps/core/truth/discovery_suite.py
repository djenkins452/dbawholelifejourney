"""Truth Discovery Validation Suite — the permanent OBJECT-level Owner-2 suite.

Each entry is a natural "tell me everything about <object>" prompt (exactly as a user
would ask — NO field names) paired with `must_surface`: the deterministic truths the
Chief of Staff's answer MUST contain for that single object. This validates that every
meaningful deterministic truth attached to an object is reachable through normal
conversation. If the CoS omits a `must_surface` item that WLJ stores for that object,
that is a Truth Layer bug (not a reasoning miss).

This is DATA, not a harness: it is the canonical script an operator runs through the
Acceptance Center (Owner-2). `anchor` documents how the object resolves deterministically;
`surface` names the provider entity/current the answer should be composed from (traceability
only — never shown to the model). `must_surface` is plain language on purpose.
"""

DISCOVERY_PROMPTS = [
    # ================= UPLOADS =================
    {"id": "artifacts.latest_upload", "domain": "artifacts",
     "object": "most recent uploaded artifact",
     "prompt": "Tell me everything you know about the last thing I uploaded.",
     "anchor": "most recent Artifact",
     "surface": "artifacts.entity(artifact)",
     "must_surface": ["what kind of file it is", "when it arrived", "its title or name",
                      "what WLJ perceived in it", "what it was filed against",
                      "confidence", "any note"]},

    # ================= BODY & VITALS =================
    {"id": "body.weigh_in", "domain": "health", "object": "latest weigh-in",
     "prompt": "Tell me everything you know about my latest weigh-in.",
     "anchor": "most recent WeightEntry",
     "surface": "health.entity(weight)",
     "must_surface": ["weight value", "unit", "date", "data source",
                      "body fat %", "lean mass", "any note", "recent weight trend"]},

    {"id": "body.blood_pressure", "domain": "health", "object": "most recent BP reading",
     "prompt": "Tell me everything you know about my most recent blood pressure reading.",
     "anchor": "most recent BloodPressureEntry",
     "surface": "health.entity(blood_pressure)",
     "must_surface": ["systolic/diastolic", "pulse", "date/time", "context (resting…)",
                      "which arm", "body position", "any note", "data source",
                      "recent BP trend"]},

    {"id": "body.glucose", "domain": "health", "object": "most recent glucose reading",
     "prompt": "Tell me everything you know about my most recent glucose reading.",
     "anchor": "most recent GlucoseEntry",
     "surface": "health.entity(glucose)",
     "must_surface": ["value with its correct unit (mg/dL or mmol/L — never mislabeled)",
                      "date/time", "context (fasting…)", "trend direction/rate",
                      "device/source", "any note", "recent glucose trend"]},

    {"id": "body.body_measurement", "domain": "health", "object": "recent measurement session",
     "prompt": "Tell me everything you know about my most recent body measurement session.",
     "anchor": "most recent BodyMeasurementSession",
     "surface": "health.entity(body_measurement)",
     "must_surface": ["session date", "title", "source",
                      "every metric captured (waist, body fat %, lean mass, …) with units",
                      "any per-measurement notes", "how each metric is trending"]},

    {"id": "body.sleep", "domain": "health", "object": "most recent sleep",
     "prompt": "Tell me everything you know about how I slept last night.",
     "anchor": "most recent SleepEntry (authoritative per night)",
     "surface": "health.entity(sleep)",
     "must_surface": ["date", "bedtime & wake time", "time asleep / in bed",
                      "sleep stages (deep/REM/light/awake)", "sleep efficiency",
                      "quality", "heart rate (avg/min/max)", "HRV", "respiratory rate",
                      "interruptions", "caffeine / mindful minutes if recorded",
                      "any note", "contributing factors", "source"]},

    {"id": "body.steps", "domain": "health", "object": "recent activity/steps",
     "prompt": "Tell me everything you know about my activity yesterday.",
     "anchor": "most recent StepsEntry",
     "surface": "health.entity(steps)",
     "must_surface": ["step count", "goal", "distance", "calories burned",
                      "resting calories", "flights climbed", "exercise minutes",
                      "stand hours", "any note", "source"]},

    # ================= NUTRITION & MEALS =================
    {"id": "nutrition.recent_meal", "domain": "nutrition", "object": "most recent food logged",
     "prompt": "Tell me everything you know about the last thing I ate.",
     "anchor": "most recent FoodEntry",
     "surface": "nutrition.entity(food)",
     "must_surface": ["food name & brand", "meal", "date/time", "serving info",
                      "full macros (calories/protein/carbs/fat/fiber/sugar)",
                      "micros (sodium/cholesterol/potassium/saturated fat)",
                      "where the data came from", "how it was logged",
                      "whether it's a favorite", "location/pace/hunger/fullness/mood if set",
                      "any note"]},

    {"id": "nutrition.yesterday", "domain": "nutrition", "object": "yesterday's nutrition",
     "prompt": "Tell me everything you know about my nutrition yesterday.",
     "anchor": "FoodEntries for yesterday + daily totals",
     "surface": "nutrition.history(calories/protein/carbs/fat) + entity(food)",
     "must_surface": ["total calories", "total protein/carbs/fat", "each meal & its foods",
                      "how it compares to my dietary targets"]},

    {"id": "nutrition.last_pizza", "domain": "nutrition", "object": "last time I ate pizza",
     "prompt": "When did I last eat pizza, and what do you know about it?",
     "anchor": "most recent FoodEntry matching 'pizza'",
     "surface": "nutrition.entity_one('pizza')",
     "must_surface": ["the pizza item + brand", "the date", "meal", "its macros",
                      "serving info"]},

    {"id": "nutrition.dietary_profile", "domain": "meals", "object": "dietary profile",
     "prompt": "Tell me everything you know about my current dietary profile.",
     "anchor": "the user's DietaryProfile",
     "surface": "meals.current(dietary_profile) / entity(dietary_profile)",
     "must_surface": ["daily carb limit", "protein target", "calorie target",
                      "fat limit", "dietary flags", "diabetes sensitivity"]},

    # ================= FITNESS =================
    {"id": "fitness.recent_workout", "domain": "health", "object": "most recent workout",
     "prompt": "Tell me everything you know about my most recent workout.",
     "anchor": "most recent WorkoutSession",
     "surface": "health.entity(workout)",
     "must_surface": ["date & start time", "workout type / mode", "duration",
                      "calories / distance / avg heart rate / intensity",
                      "every exercise with its sets, reps, and weights", "any PRs",
                      "any note", "source"]},

    {"id": "fitness.last_named", "domain": "health", "object": "last named session",
     "prompt": "Tell me everything you know about my last squat session.",
     "anchor": "most recent WorkoutSession matching 'squat'",
     "surface": "health.entity_one('squat')",
     "must_surface": ["the session date", "squat sets/reps/weights (load, not bodyweight)",
                      "any PR", "volume", "any note"]},

    # ================= MEDICATIONS =================
    {"id": "meds.named", "domain": "medicine", "object": "a named medication",
     "prompt": "Tell me everything you know about my Metformin.",
     "anchor": "the Intake named 'Metformin'",
     "surface": "medicine.entity_one('Metformin')",
     "must_surface": ["dose & unit", "purpose", "category", "frequency",
                      "the full schedule — times AND which days", "instructions (with food…)",
                      "start/end dates", "monitoring requirements",
                      "adherence (7/30/90 day)", "when I last took it",
                      "refill status (supply, needs refill, requested)",
                      "paused status if paused", "prescriber", "pharmacy", "Rx number",
                      "any note"]},

    # ================= GOALS / MISSIONS =================
    {"id": "goals.mission", "domain": "goals", "object": "the primary mission / a named goal",
     "prompt": "Tell me everything you know about my France 2027 mission.",
     "anchor": "LifeGoal matching 'France 2027' (or the primary mission)",
     "surface": "goals.entity_one('France 2027')",
     "must_surface": ["title & status", "why it matters", "what success looks like",
                      "target date & time remaining", "milestones (done/overdue/next)",
                      "progress %", "momentum + what's improved / still needs work",
                      "reflection & motivation note", "commitment level & timeframe",
                      "the annual direction it ladders to", "victory milestones",
                      "linked habits", "any motivation links", "hero image if set"]},

    {"id": "goals.completed_milestone", "domain": "goals", "object": "latest completed milestone",
     "prompt": "Tell me everything you know about my most recently completed milestone.",
     "anchor": "most recent completed GoalMilestone",
     "surface": "goals.current(milestones_completed) / entity(milestone)",
     "must_surface": ["milestone title", "which goal it belongs to", "completion date",
                      "any objective/target it measured"]},

    {"id": "goals.annual_direction", "domain": "goals", "object": "word/theme of the year",
     "prompt": "Tell me everything you know about my word and theme for this year.",
     "anchor": "current AnnualDirection",
     "surface": "goals.entity(annual_direction)",
     "must_surface": ["the year", "word of the year", "why that word",
                      "the theme & its description", "the anchor scripture/quote & source",
                      "whether it's the current year"]},

    # ================= HABITS =================
    {"id": "habits.overview", "domain": "habits", "object": "a habit",
     "prompt": "Tell me everything you know about my reading habit.",
     "anchor": "HabitGoal matching 'read'",
     "surface": "habits.entity_one('read')",
     "must_surface": ["purpose & success criteria", "how it's measured & how often",
                      "target", "current streak & longest streak", "at-risk status",
                      "completion rate", "recent entries (with notes/duration/count)",
                      "linked goals", "the annual direction it supports"]},

    # ================= JOURNAL (journal-only — no contamination) =================
    {"id": "journal.yesterday", "domain": "journal", "object": "yesterday's journal entry",
     "prompt": "Tell me everything you know about what I journaled yesterday.",
     "anchor": "JournalEntry for yesterday",
     "surface": "journal.entity_one(yesterday)",
     "must_surface": ["the entry's content", "title", "my mood", "emotions", "tags",
                      "categories", "the prompt that inspired it if any",
                      "any extracted themes/signals"],
     "must_not_surface": ["audio exposure", "mobility/walking speed", "health telemetry",
                          "any non-journal record"]},

    {"id": "journal.themes", "domain": "journal", "object": "recurring journal themes",
     "prompt": "What have I been writing about lately, and what keeps coming up?",
     "anchor": "journal theme aggregation over the month",
     "surface": "journal.current(themes)",
     "must_surface": ["most frequent topics/tags", "repeated emotions/concerns"],
     "must_not_surface": ["non-journal records"]},

    # ================= PEOPLE / RELATIONSHIPS =================
    {"id": "people.named", "domain": "relationships", "object": "a person",
     "prompt": "Tell me everything you know about Heather.",
     "anchor": "relationships.Person matching 'Heather'",
     "surface": "relationships.entity_one('Heather')",
     "must_surface": ["relationship type", "contact info (email/phone)", "household",
                      "groups she's in", "when I last connected & how long it's been",
                      "how often we interact", "my notes about her",
                      "recent interactions (what we did)", "journal entries mentioning her",
                      "memories involving her", "goals involving her",
                      "trips/places we've shared", "events involving her",
                      "her upcoming birthday"]},

    {"id": "people.most_important", "domain": "relationships", "object": "most important people",
     "prompt": "Who are the most important people in my life right now?",
     "anchor": "relationships ranked by interaction",
     "surface": "relationships.current(most_connected)",
     "must_surface": ["the top people", "how often I interact with each",
                      "when I last connected with each"]},

    {"id": "people.upcoming_birthday", "domain": "relationships", "object": "upcoming birthday",
     "prompt": "Whose birthday is coming up?",
     "anchor": "SignificantEvent birthdays in the next window",
     "surface": "relationships.current(upcoming_birthdays)",
     "must_surface": ["whose birthday", "the date", "how many days away"]},

    # ================= LEGACY =================
    {"id": "legacy.person", "domain": "legacy", "object": "an ancestor / family member",
     "prompt": "Tell me everything you know about my grandfather.",
     "anchor": "legacy.Person by relationship/name",
     "surface": "legacy.entity_one('grandfather')",
     "must_surface": ["name & also-known-as", "relationship", "birth & death",
                      "their biography", "significance", "memories they appear in",
                      "the family relationships (who they're related to, with any notes)",
                      "preserved facts (career/faith/military, with subject)",
                      "a portrait if stored"]},

    {"id": "legacy.childhood", "domain": "legacy", "object": "childhood memories",
     "prompt": "Tell me everything you know about my childhood.",
     "anchor": "Memories in the childhood era range",
     "surface": "legacy.entity(memory, occurred era)",
     "must_surface": ["the childhood-era memories", "when each occurred",
                      "people & places in them"]},

    {"id": "legacy.recent_memory", "domain": "legacy", "object": "most recent memory",
     "prompt": "Tell me everything you know about the last memory I recorded.",
     "anchor": "most recently created Memory",
     "surface": "legacy.entity(memory)",
     "must_surface": ["the story/narrative itself", "type of memory", "when it occurred",
                      "people (and their roles)", "places", "life milestones it belongs to",
                      "attached media (photos with captions & dates, audio)",
                      "significance", "who contributed/attributed it"]},

    {"id": "legacy.places", "domain": "legacy", "object": "meaningful places",
     "prompt": "What places have special meaning to me?",
     "anchor": "legacy Places by significance",
     "surface": "legacy.entity(place)",
     "must_surface": ["each place name & location", "its description",
                      "coordinates / map link", "a photo if stored", "significance",
                      "memories tied to it"]},

    # ================= FAITH =================
    {"id": "faith.reading_plan", "domain": "faith", "object": "current Bible study",
     "prompt": "Tell me everything you know about my current Bible study.",
     "anchor": "active UserReadingPlan",
     "surface": "faith.entity(reading_plan)",
     # "current Bible study" == the ACTIVE plan (plan_status='active'), NOT the most
     # recently STARTED plan. Resolve by the app's active marker, never describe()[0].
     "selection": {"rule": "active", "status": "active"},
     "bind_template": "Tell me everything you know about my Bible reading plan \"{identity}\".",
     "must_surface": ["the plan title & category", "duration", "what day I'm on",
                      "my progress", "today's reading", "reminder time",
                      "my per-day reflection notes"]},

    {"id": "faith.prayer", "domain": "faith", "object": "most recent prayer request",
     "prompt": "Tell me everything you know about my most recent prayer request.",
     "anchor": "most recent PrayerRequest",
     "surface": "faith.entity(prayer)",
     "selection": {"rule": "latest"},   # prayers are composed newest-first (-created_at)
     "bind_template": "Tell me everything you know about my prayer request \"{identity}\".",
     "must_surface": ["what I'm praying about", "priority", "who/what it's for",
                      "when I recorded it", "answered/unanswered status",
                      "answer notes if answered", "whether it reminds daily"]},

    {"id": "faith.reading_consistency", "domain": "faith", "object": "reading consistency",
     "prompt": "How consistent has my Bible reading been?",
     "anchor": "faith reading completion history",
     "surface": "faith.history(reading)",
     "must_surface": ["days read over the window", "streak / days since"]},

    # ================= CALENDAR =================
    {"id": "calendar.today", "domain": "calendar", "object": "today's schedule",
     "prompt": "Tell me everything you know about my schedule today.",
     "anchor": "CalendarEvents for today",
     "surface": "calendar.entity(event, on_date=today) / current",
     "must_surface": ["each event's title", "start & end times", "all-day or not",
                      "which life domain", "commitment level", "status",
                      "whether it's protected", "description",
                      "recurrence details (incl. its timezone) if recurring"]},

    {"id": "calendar.next", "domain": "calendar", "object": "next meeting",
     "prompt": "Tell me everything you know about my next meeting.",
     "anchor": "next upcoming CalendarEvent",
     "surface": "calendar.current(next_event) / entity(event)",
     "must_surface": ["title", "when it starts & ends", "duration", "domain",
                      "commitment level", "description", "recurrence if any"]},

    # ================= TASKS =================
    {"id": "tasks.next", "domain": "tasks", "object": "what to do next",
     "prompt": "What should I work on next, and what do you know about it?",
     "anchor": "decision_authority.current_action",
     "surface": "get_decision + tasks.entity",
     "must_surface": ["the recommended next action", "why it's next",
                      "its due date/priority/context"]},

    {"id": "tasks.overdue", "domain": "tasks", "object": "oldest overdue task",
     "prompt": "Tell me everything you know about my oldest overdue task.",
     "anchor": "oldest overdue Task",
     "surface": "tasks.entity(task)",
     "must_surface": ["the task", "how overdue", "due date", "priority & commitment",
                      "the project it belongs to", "module", "effort", "progress",
                      "scheduling/recurrence", "any dependency it's waiting on",
                      "partial-progress notes", "any note"]},

    # ================= PROJECTS =================
    {"id": "projects.active", "domain": "projects", "object": "most active project",
     "prompt": "Tell me everything you know about my most active project.",
     "anchor": "an active Project",
     "surface": "projects.entity(project)",
     "must_surface": ["title", "description & purpose", "priority", "category & tags",
                      "target/start dates", "overdue status", "task counts & progress",
                      "cover image if set", "any reflection"]},

    # ================= EVENTS =================
    {"id": "events.upcoming", "domain": "events", "object": "upcoming significant events",
     "prompt": "Tell me everything about my upcoming anniversaries and important dates.",
     "anchor": "SignificantEvents of every type",
     "surface": "events.current(upcoming_events) / entity(event)",
     "must_surface": ["events of every type (anniversary/memorial/milestone/…), not just "
                      "birthdays", "title", "the date & how many days away", "the year it "
                      "began", "linked person", "description & any custom message"]},

    # ================= CAPTURE =================
    {"id": "capture.recent", "domain": "capture", "object": "most recent capture",
     "prompt": "Tell me everything you know about my most recent capture.",
     "anchor": "most recent CaptureEntry",
     "surface": "capture.entity(capture)",
     "must_surface": ["title", "category/subcategory", "when captured", "duration",
                      "processing status", "the transcript", "the summary",
                      "any extracted signals"]},

    # ================= NOTES =================
    {"id": "notes.recent", "domain": "notes", "object": "most recent note",
     "prompt": "Tell me everything you know about my most recent note.",
     "anchor": "most recent Note",
     "surface": "notes.entity(note)",
     "must_surface": ["title", "the note content", "tags", "color", "whether it's pinned",
                      "what it's attached to", "when created/updated"]},

    # ================= BRAIN TRAINING =================
    {"id": "brain.recent", "domain": "brain_training", "object": "most recent game session",
     "prompt": "Tell me everything you know about my most recent brain training session.",
     "anchor": "most recent GameSession",
     "surface": "brain_training.entity(game_session)",
     "must_surface": ["which game & category", "difficulty", "when I played",
                      "time spent", "score", "mistakes", "hints used", "status"]},

    # ================= MEDICAL / LABS =================
    {"id": "medical.recent_lab", "domain": "medical", "object": "most recent lab result",
     "prompt": "Tell me everything you know about my most recent lab results.",
     "anchor": "latest LabResults (per test)",
     "surface": "medical.entity(lab_result) / current(latest_labs)",
     "must_surface": ["each test name & value with unit", "reference range",
                      "normal/abnormal flag", "result status", "when collected/reported",
                      "the test category / what it measures", "how the value has trended",
                      "the ordering provider", "which panel & source document",
                      "any note"]},

    {"id": "medical.panel", "domain": "medical", "object": "a lab panel",
     "prompt": "Tell me everything you know about my last blood panel.",
     "anchor": "most recent LabPanel",
     "surface": "medical.entity(lab_panel)",
     "must_surface": ["panel name & type", "when collected", "ordering provider",
                      "every result in it (value, unit, flag)", "how many were abnormal"]},
]


def prompts_by_domain():
    out = {}
    for p in DISCOVERY_PROMPTS:
        out.setdefault(p["domain"], []).append(p)
    return out
