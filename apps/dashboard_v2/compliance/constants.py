"""
Compliance Audit System — canonical status definitions and reason codes.

These are the product-level semantics for the compliance event layer.
Every compliance event row uses these statuses to explain what happened and why.
"""

# ── Scoring Buckets ──────────────────────────────────────────────
# Each bucket maps to a V2 compliance card.

BUCKET_MEDICATION = "medication_doses"
BUCKET_WORKOUT = "workouts"
BUCKET_ROUTINE = "routine_items"
BUCKET_TASK = "tasks"
BUCKET_JOURNAL = "journal"
BUCKET_FAITH = "faith"

SCORING_BUCKET_CHOICES = [
    (BUCKET_MEDICATION, "Medication Doses"),
    (BUCKET_WORKOUT, "Workouts"),
    (BUCKET_ROUTINE, "Routine Items"),
    (BUCKET_TASK, "Tasks"),
    (BUCKET_JOURNAL, "Journal"),
    (BUCKET_FAITH, "Faith"),
]

SCORING_BUCKETS = [b[0] for b in SCORING_BUCKET_CHOICES]

# ── Domains ──────────────────────────────────────────────────────
# Source system domains — finer-grained than scoring buckets.

DOMAIN_MEDICATION = "medication"
DOMAIN_WORKOUT = "workout"
DOMAIN_ROUTINE = "routine"
DOMAIN_TASK = "task"
DOMAIN_JOURNAL = "journal"
DOMAIN_FAITH = "faith"

DOMAIN_CHOICES = [
    (DOMAIN_MEDICATION, "Medication"),
    (DOMAIN_WORKOUT, "Workout"),
    (DOMAIN_ROUTINE, "Routine"),
    (DOMAIN_TASK, "Task"),
    (DOMAIN_JOURNAL, "Journal"),
    (DOMAIN_FAITH, "Faith"),
]

# ── Actual Status ────────────────────────────────────────────────
# What actually happened with this item.

ACTUAL_NONE = "none"
ACTUAL_COMPLETED = "completed"
ACTUAL_COMPLETED_LATE = "completed_late"
ACTUAL_SKIPPED = "skipped"
ACTUAL_RESCHEDULED = "rescheduled"
ACTUAL_OPEN = "open"

ACTUAL_STATUS_CHOICES = [
    (ACTUAL_NONE, "No action taken"),
    (ACTUAL_COMPLETED, "Completed"),
    (ACTUAL_COMPLETED_LATE, "Completed Late"),
    (ACTUAL_SKIPPED, "Skipped"),
    (ACTUAL_RESCHEDULED, "Rescheduled"),
    (ACTUAL_OPEN, "Open / In Progress"),
]

# ── Final Status ─────────────────────────────────────────────────
# The scoring status after applying rules. This is what rollups use.

FINAL_COMPLETED = "completed"
FINAL_COMPLETED_LATE = "completed_late"
FINAL_SKIPPED = "skipped"
FINAL_MISSED = "missed"
FINAL_OVERDUE = "overdue"
FINAL_RESCHEDULED = "rescheduled"
FINAL_NOT_EXPECTED = "not_expected"

FINAL_STATUS_CHOICES = [
    (FINAL_COMPLETED, "Completed"),
    (FINAL_COMPLETED_LATE, "Completed Late"),
    (FINAL_SKIPPED, "Skipped"),
    (FINAL_MISSED, "Missed"),
    (FINAL_OVERDUE, "Overdue"),
    (FINAL_RESCHEDULED, "Rescheduled"),
    (FINAL_NOT_EXPECTED, "Not Expected"),
]

# Statuses that count as "good" in rollup numerator
FINAL_POSITIVE = {FINAL_COMPLETED, FINAL_COMPLETED_LATE}

# Statuses that count as "bad" (appear in missed list)
FINAL_NEGATIVE = {FINAL_MISSED, FINAL_OVERDUE}

# Statuses excluded from rollup denominator entirely
FINAL_EXCLUDED_FROM_DENOMINATOR = {FINAL_NOT_EXPECTED}

# ── Reason Codes ─────────────────────────────────────────────────
# Why an item received its final_status. Answers "why was this counted this way?"

REASON_ON_TIME = "on_time"
REASON_AFTER_GRACE = "after_grace"
REASON_NO_LOG = "no_log"
REASON_EXPLICIT_SKIP = "explicit_skip"
REASON_EXPLICIT_MISSED = "explicit_missed"
REASON_OVERDUE_DUE_DATE = "overdue_due_date"
REASON_NOT_DUE_TODAY = "not_due_today"
REASON_INACTIVE_SCHEDULE = "inactive_schedule"
REASON_REST_DAY = "rest_day"
REASON_RESCHEDULED = "rescheduled"
REASON_SATISFIED_BY_LINKED = "satisfied_by_linked"
REASON_NO_DUE_DATE = "no_due_date"
REASON_COMPLETED_TODAY = "completed_today"
REASON_PLAN_ACTIVE = "plan_active"
REASON_NO_PLAN = "no_plan"
REASON_ENTRY_EXISTS = "entry_exists"
REASON_NO_ENTRY = "no_entry"
REASON_ASSERTED_ON_TIME = "asserted_on_time"
REASON_COMPLETED_VIA_SESSION = "completed_via_session"
REASON_COMPLETED_VIA_JOURNAL = "completed_via_journal"
REASON_NOT_COMPLETED = "not_completed"

REASON_CODE_CHOICES = [
    (REASON_ON_TIME, "Completed within grace period"),
    (REASON_AFTER_GRACE, "Completed after grace period expired"),
    (REASON_NO_LOG, "No completion log found"),
    (REASON_EXPLICIT_SKIP, "Explicitly skipped by user"),
    (REASON_EXPLICIT_MISSED, "Explicitly marked as missed"),
    (REASON_OVERDUE_DUE_DATE, "Past due date and still incomplete"),
    (REASON_NOT_DUE_TODAY, "Not due/scheduled for this date"),
    (REASON_INACTIVE_SCHEDULE, "Schedule is inactive or paused"),
    (REASON_REST_DAY, "Scheduled rest day"),
    (REASON_RESCHEDULED, "Rescheduled to a different time"),
    (REASON_SATISFIED_BY_LINKED, "Satisfied by linked event"),
    (REASON_NO_DUE_DATE, "No due date assigned"),
    (REASON_COMPLETED_TODAY, "Task completed on this date"),
    (REASON_PLAN_ACTIVE, "Active reading plan for this date"),
    (REASON_NO_PLAN, "No active reading plan"),
    (REASON_ENTRY_EXISTS, "Entry logged for this date"),
    (REASON_NO_ENTRY, "No entry found for this date"),
    (REASON_ASSERTED_ON_TIME, "User asserted on-time completion"),
    (REASON_COMPLETED_VIA_SESSION, "Completed via workout"),
    (REASON_COMPLETED_VIA_JOURNAL, "Completed via journal entry"),
    (REASON_NOT_COMPLETED, "Not completed"),
]

REASON_SATISFIED_BY_LINKED = "satisfied_by_linked"
REASON_SATISFIED_BY_WORKOUT = "satisfied_by_linked_workout"
REASON_SATISFIED_BY_JOURNAL = "satisfied_by_linked_journal"
REASON_SATISFIED_BY_FAITH = "satisfied_by_linked_faith"
REASON_DUPLICATE_OBLIGATION = "duplicate_obligation"

REASON_CODE_CHOICES += [
    (REASON_SATISFIED_BY_LINKED, "Satisfied by linked activity"),
    (REASON_SATISFIED_BY_WORKOUT, "Satisfied by linked workout completion"),
    (REASON_SATISFIED_BY_JOURNAL, "Satisfied by linked journal entry"),
    (REASON_SATISFIED_BY_FAITH, "Satisfied by linked faith activity"),
    (REASON_DUPLICATE_OBLIGATION, "Duplicate obligation — not counted separately"),
]

REASON_LABELS = dict(REASON_CODE_CHOICES)

# ── Score Suppression Reasons ────────────────────────────────────

SUPPRESSED_BY_LINKED = "satisfied_by_linked"
SUPPRESSED_BY_LINKED_WORKOUT = "satisfied_by_linked_workout"
SUPPRESSED_BY_LINKED_JOURNAL = "satisfied_by_linked_journal"
SUPPRESSED_BY_LINKED_FAITH = "satisfied_by_linked_faith"
SUPPRESSED_DUPLICATE = "duplicate_obligation"

SUPPRESSION_REASON_CHOICES = [
    (SUPPRESSED_BY_LINKED, "Satisfied by linked activity"),
    (SUPPRESSED_BY_LINKED_WORKOUT, "Satisfied by linked workout completion"),
    (SUPPRESSED_BY_LINKED_JOURNAL, "Satisfied by linked journal entry"),
    (SUPPRESSED_BY_LINKED_FAITH, "Satisfied by linked faith activity"),
    (SUPPRESSED_DUPLICATE, "Duplicate obligation — not counted separately"),
]

SUPPRESSION_LABELS = dict(SUPPRESSION_REASON_CHOICES)

# ── Obligation Types ─────────────────────────────────────────────

OBLIGATION_WORKOUT = "workout"
OBLIGATION_JOURNAL = "journal"
OBLIGATION_FAITH_PRAYER = "faith_prayer"
OBLIGATION_FAITH_BIBLE = "faith_bible"
OBLIGATION_MEDICATION = "medication"
OBLIGATION_TASK = "task"
OBLIGATION_ROUTINE = "routine"

# Map obligation_type → suppression reason for linked-activity suppression
OBLIGATION_SUPPRESSION_MAP = {
    OBLIGATION_WORKOUT: SUPPRESSED_BY_LINKED_WORKOUT,
    OBLIGATION_JOURNAL: SUPPRESSED_BY_LINKED_JOURNAL,
    OBLIGATION_FAITH_PRAYER: SUPPRESSED_BY_LINKED_FAITH,
    OBLIGATION_FAITH_BIBLE: SUPPRESSED_BY_LINKED_FAITH,
}

# ── Human-readable Final Status Labels ───────────────────────────

FINAL_STATUS_LABELS = {
    FINAL_COMPLETED: "Completed",
    FINAL_COMPLETED_LATE: "Late",
    FINAL_SKIPPED: "Skipped",
    FINAL_MISSED: "Missed",
    FINAL_OVERDUE: "Overdue",
    FINAL_RESCHEDULED: "Rescheduled",
    FINAL_NOT_EXPECTED: "Not Expected",
}

# ── Source Systems ───────────────────────────────────────────────

SOURCE_MEDICINE_LOG = "medicine_log"
SOURCE_MEDICINE_SCHEDULE = "medicine_schedule"
SOURCE_WORKOUT_SESSION = "workout_session"
SOURCE_WORKOUT_SCHEDULE_LOG = "workout_schedule_log"
SOURCE_WORKOUT_SCHEDULE = "workout_schedule"
SOURCE_ROUTINE_LOG = "routine_log"
SOURCE_ROUTINE_SCHEDULE = "routine_schedule"
SOURCE_TASK = "task"
SOURCE_JOURNAL_ENTRY = "journal_entry"
SOURCE_READING_PROGRESS = "reading_progress"
SOURCE_READING_PLAN = "reading_plan"
SOURCE_PRAYER_TASK = "prayer_task"
