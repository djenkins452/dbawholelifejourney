# ==============================================================================
# File: apps/core/truth/cos_question_catalogs.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Chief-of-Staff Question Catalogs for the remaining Layer-1 truth domains
#              (Medications, Goals, Habits, Calendar, Tasks, People, Legacy, Medical,
#              Brain Training, Projects, Notes, Capture). ONE data module driving the
#              data-driven Question Certification framework (apps.core.truth
#              .question_catalog). Certification is COMPUTED against the live capability
#              registries — never asserted. Each question declares the truth it REQUIRES;
#              questions reflect what the product actually supports (from each DomainTruth's
#              supports()), reuse the platform capabilities, and never encode a verdict.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""CoS remaining-domain Question Catalogs. Extend by ADDING a Question; the framework
computes `certified` from the live registries. WLJ exposes facts; OpenAI judges."""
from apps.core.truth.question_catalog import Question, Requirement as R, register_question


def _q(qid, domain, topic, category, examples, requires, note=""):
    register_question(Question(id=qid, domain=domain, topic=topic, category=category,
                               examples=tuple(examples), requires=tuple(requires),
                               note=note))


# ── MEDICATIONS (domain 'medicine') — facts only; medication truth ≠ medical advice ──
_q("medicine.current", "medicine", "medications", "current",
   ["what medications am I taking", "what am I currently prescribed"],
   [R("current", "medicine", "current_medications")])
_q("medicine.supplements", "medicine", "medications", "current",
   ["what supplements do I take"], [R("current", "medicine", "current_supplements")])
_q("medicine.adherence_history", "medicine", "medications", "history",
   ["my medication adherence this month", "how adherent have I been"],
   [R("history", "medicine", "adherence")])
_q("medicine.adherence_trend", "medicine", "medications", "trend",
   ["is my medication adherence improving", "am I taking my meds more consistently"],
   [R("trend", "medicine", "adherence")])
_q("medicine.adherence_comparison", "medicine", "medications", "comparison",
   ["was my adherence better this month than last"],
   [R("comparison", "medicine", "adherence")])
_q("medicine.analysis", "medicine", "medications", "analysis",
   ["how am I doing with my medications", "analyze my medication adherence"],
   [R("analysis", "medicine", "overall")])

# ── GOALS (domain 'goals') — progress FACTS only; NO momentum/pace verdicts ──────────
_q("goals.active", "goals", "goals", "current",
   ["what are my active goals", "what am I working toward"],
   [R("current", "goals", "active_goals")])
_q("goals.primary_mission", "goals", "goals", "current",
   ["what's my primary mission"], [R("current", "goals", "primary_mission")])
_q("goals.completion_rate", "goals", "goals", "current",
   ["what's my goal completion rate", "how many milestones have I completed"],
   [R("current", "goals", "completion_rate")])
_q("goals.progress_history", "goals", "goals", "history",
   ["how has my goal progress been", "my milestone progress over time"],
   [R("history", "goals", "progress")])
_q("goals.progress_trend", "goals", "goals", "trend",
   ["is my goal progress trending up", "am I making progress on my goals"],
   [R("trend", "goals", "progress")])
_q("goals.analysis", "goals", "goals", "analysis",
   ["how am I doing on my goals", "analyze my missions"],
   [R("analysis", "goals", "overall")])

# ── HABITS (domain 'habits') — occurrence-scoped completion; behavioral consistency ──
_q("habits.active", "habits", "habits", "current",
   ["what habits am I tracking", "what are my current habits"],
   [R("current", "habits", "active_habits")])
_q("habits.consistency_history", "habits", "habits", "history",
   ["how consistent have my habits been", "my habit consistency this month"],
   [R("history", "habits", "consistency")])
_q("habits.consistency_trend", "habits", "habits", "trend",
   ["are my habits getting more consistent", "is my habit consistency improving"],
   [R("trend", "habits", "consistency")])
_q("habits.analysis", "habits", "habits", "analysis",
   ["how am I doing with my habits", "analyze my habit consistency"],
   [R("analysis", "habits", "habits")])

# ── CALENDAR (domain 'calendar') — deterministic time truth ─────────────────────────
_q("calendar.today", "calendar", "calendar", "current",
   ["what's on my calendar today", "how many events today"],
   [R("current", "calendar", "today_event_count")])
_q("calendar.next", "calendar", "calendar", "current",
   ["what's my next event", "what's coming up next"],
   [R("current", "calendar", "next_event")])
_q("calendar.upcoming", "calendar", "calendar", "current",
   ["what's coming up", "what's on my schedule this week"],
   [R("current", "calendar", "upcoming_count")])
_q("calendar.history", "calendar", "calendar", "history",
   ["how many events did I have last week", "my calendar activity over time"],
   [R("history", "calendar", "events")])
_q("calendar.analysis", "calendar", "calendar", "analysis",
   ["how busy have I been", "analyze my calendar"],
   [R("analysis", "calendar", "overall")])

# ── TASKS (domain 'tasks') — Execution truth (Decision Authority owns 'what now') ────
_q("tasks.overdue", "tasks", "tasks", "current",
   ["what tasks are overdue", "how many overdue tasks do I have"],
   [R("current", "tasks", "overdue_count")])
_q("tasks.due_today", "tasks", "tasks", "current",
   ["what's due today", "what tasks do I have today"],
   [R("current", "tasks", "tasks_due_today")])
_q("tasks.completed_history", "tasks", "tasks", "history",
   ["how many tasks have I completed lately", "my task completion over time"],
   [R("history", "tasks", "completed")])
_q("tasks.completed_trend", "tasks", "tasks", "trend",
   ["am I completing more tasks", "is my task completion trending up"],
   [R("trend", "tasks", "completed")])
_q("tasks.analysis", "tasks", "tasks", "analysis",
   ["how am I doing with my tasks", "analyze my task completion"],
   [R("analysis", "tasks", "overall")])

# ── PEOPLE / RELATIONSHIPS (domain 'relationships') — facts, not relationship verdicts ─
_q("relationships.neglected", "relationships", "people", "current",
   ["who have I not connected with lately", "which relationships am I neglecting"],
   [R("current", "relationships", "neglected_count")])
_q("relationships.birthdays", "relationships", "people", "current",
   ["whose birthday is coming up", "any birthdays this week"],
   [R("current", "relationships", "upcoming_birthdays")])
_q("relationships.most_connected", "relationships", "people", "current",
   ["who do I interact with most"], [R("current", "relationships", "most_connected")])
_q("relationships.interactions_history", "relationships", "people", "history",
   ["how often have I been connecting with people", "my interactions over time"],
   [R("history", "relationships", "interactions")])
_q("relationships.interactions_trend", "relationships", "people", "trend",
   ["am I connecting with people more or less"],
   [R("trend", "relationships", "interactions")])
_q("relationships.analysis", "relationships", "people", "analysis",
   ["how am I doing with my relationships", "analyze my connections"],
   [R("analysis", "relationships", "overall")])

# ── LEGACY (domain 'legacy') — Published preservation truth (Journal is Saved) ──────
_q("legacy.memories", "legacy", "legacy", "current",
   ["how many memories have I saved", "how much of my legacy have I captured"],
   [R("current", "legacy", "total_memories")])
_q("legacy.people", "legacy", "legacy", "current",
   ["how many people are in my legacy"], [R("current", "legacy", "total_people")])
_q("legacy.analysis", "legacy", "legacy", "analysis",
   ["how am I doing with my legacy", "analyze my preserved memories"],
   [R("analysis", "legacy", "overall")])

# ── MEDICAL (domain 'medical') — lab/records FACTS; NO clinical interpretation ──────
_q("medical.tracked_labs", "medical", "medical", "current",
   ["what lab tests am I tracking", "what labs do you have for me"],
   [R("current", "medical", "tracked_lab_tests")])
_q("medical.abnormal", "medical", "medical", "current",
   ["are any of my lab results abnormal", "which labs are out of range"],
   [R("current", "medical", "abnormal_results")])
_q("medical.latest", "medical", "medical", "current",
   ["what are my latest lab results"], [R("current", "medical", "latest_labs")])
_q("medical.lab_history", "medical", "medical", "history",
   ["how has my lab value trended", "my lab results over time"],
   [R("history", "medical", "lab_value")])
_q("medical.lab_trend", "medical", "medical", "trend",
   ["is my lab value improving"], [R("trend", "medical", "lab_value")])
_q("medical.analysis", "medical", "medical", "analysis",
   ["analyze my lab results", "how are my labs looking"],
   [R("analysis", "medical", "overall")])

# ── BRAIN TRAINING (domain 'brain_training') — cognitive measurements, not verdicts ─
_q("brain_training.recent", "brain_training", "brain_training", "current",
   ["how many brain games have I played", "what's my brain training streak"],
   [R("current", "brain_training", "games_played_7d")])
_q("brain_training.streak", "brain_training", "brain_training", "current",
   ["what's my current brain training streak"],
   [R("current", "brain_training", "current_streak")])
_q("brain_training.history", "brain_training", "brain_training", "history",
   ["how have my brain game scores been", "my best scores over time"],
   [R("history", "brain_training", "daily_best_score")])
_q("brain_training.trend", "brain_training", "brain_training", "trend",
   ["are my brain game scores improving", "is my cognitive performance trending up"],
   [R("trend", "brain_training", "daily_best_score")])
_q("brain_training.analysis", "brain_training", "brain_training", "analysis",
   ["how am I doing with brain training", "analyze my cognitive performance"],
   [R("analysis", "brain_training", "overall")])

# ── PROJECTS (domain 'projects') — thin surface: current facts only ─────────────────
_q("projects.active", "projects", "projects", "current",
   ["what projects am I working on", "what are my active projects"],
   [R("current", "projects", "active_projects")])

# ── NOTES (domain 'notes') — thin surface: current facts only (distinct from Journal) ─
_q("notes.count", "notes", "notes", "current",
   ["how many notes do I have"], [R("current", "notes", "note_count")])

# ── CAPTURE (domain 'capture') — inbox facts only (finalized truth lives elsewhere) ──
_q("capture.unprocessed", "capture", "capture", "current",
   ["how many captures do I have to process", "what's in my capture inbox"],
   [R("current", "capture", "unprocessed_count")])
