"""
Canonical "where does this action happen?" resolver — CAPABILITY-first.

Single source of truth for deep-linking a Focus / Do-This-Now / rhythm action to
the WLJ page where the user actually performs it. Routing originates from the
ACTION being represented — never from the displayed wording and never from the
fact that the item happens to be a routine.

    item  ──▶  derive_capability(item)  ──▶  _CAPABILITY_URL[capability]  ──▶ URL

Capability derivation is METADATA-FIRST (rename-safe), title-LAST:
    1. source_type            — meds/supplements are authoritative → log_intake
    2. RoutineSchedule.activity_type (on the item, else queried)
                              — workout / journal / bible / faith
    3. Task.module / item.domain — faith / journal / nutrition / fitness / …
    4. title keyword bridge   — ONLY to disambiguate sub-domains the current
                                metadata can't express (nutrition / weight /
                                measurements / prayer have no activity_type yet).
                                Documented last resort; mirrors
                                auto_complete_routine_schedules' name-fallback.
    5. fallback capability    — a ROUTINE with no signal is a genuine household
                                routine → open_routines; a task → its domain
                                home → open_life.

Renames are safe for anything carrying metadata: "Bible Reading" → "Morning
Scripture" still routes to the reading workflow via activity_type='bible'.

REGRESSION THIS FIXES (2026-07-05): rhythm items hardcoded detail_url to the
Routines page, so "Journal" and "Log Nutrition" navigated to /life/routines/
instead of their workflow. detail_url now flows through this resolver.

All URLs resolve via reverse() with a literal-path fallback, so a route rename
never produces a dead link.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _dest(url_name: str, literal: str) -> str:
    """Resolve a named route, falling back to a literal path. Never dead."""
    try:
        from django.urls import reverse
        return reverse(url_name)
    except Exception:
        return literal


# ── Capabilities ──────────────────────────────────────────────────────────
# A capability is the deterministic ACTION an item represents. The presentation
# text can change freely; the capability (and therefore the destination) does
# not. Each maps to the SPECIFIC workflow the user performs it in.
CAP_LOG_NUTRITION = "log_nutrition"
CAP_CREATE_JOURNAL_ENTRY = "create_journal_entry"
CAP_OPEN_BIBLE_READING = "open_bible_reading"
CAP_OPEN_PRAYER = "open_prayer"
CAP_OPEN_FAITH = "open_faith"
CAP_LOG_MEASUREMENTS = "log_measurements"
CAP_LOG_WORKOUT = "log_workout"
CAP_LOG_WEIGHT = "log_weight"
CAP_LOG_INTAKE = "log_intake"
CAP_OPEN_FITNESS = "open_fitness"
CAP_OPEN_ROUTINES = "open_routines"
CAP_OPEN_LIFE = "open_life"
CAP_OPEN_HEALTH = "open_health"


# capability → (url_name, literal fallback). SPECIFIC entry pages where they
# exist, so "Log Weight" opens the weight ENTRY form, not just the domain home.
_CAPABILITY_URL: dict[str, tuple[str, str]] = {
    CAP_LOG_NUTRITION:        ("health:nutrition_home",         "/health/physical/nutrition/"),
    CAP_CREATE_JOURNAL_ENTRY: ("journal:entry_create",          "/journal/new/"),
    CAP_OPEN_BIBLE_READING:   ("faith:reading_plans",           "/faith/reading-plans/"),
    CAP_OPEN_PRAYER:          ("faith:prayer_list",             "/faith/prayers/"),
    CAP_OPEN_FAITH:           ("faith:home",                    "/faith/"),
    CAP_LOG_MEASUREMENTS:     ("health:body_composition_create", "/health/physical/body-composition/log/"),
    CAP_LOG_WORKOUT:          ("health:workout_create",         "/health/physical/fitness/workout/new/"),
    CAP_LOG_WEIGHT:           ("health:weight_create",          "/health/physical/weight/log/"),
    CAP_LOG_INTAKE:           ("health:intake_home",            "/health/physical/intake/"),
    CAP_OPEN_FITNESS:         ("health:fitness_home",           "/health/physical/fitness/"),
    CAP_OPEN_ROUTINES:        ("life:routine_list",             "/life/routines/"),
    CAP_OPEN_LIFE:            ("life:home",                     "/life/"),
    CAP_OPEN_HEALTH:          ("health:home",                   "/health/physical/"),
}


def capability_to_url(capability: str | None) -> str | None:
    spec = _CAPABILITY_URL.get(capability or "")
    return _dest(*spec) if spec else None


# ── Metadata → capability ───────────────────────────────────────────────────
def _activity_to_capability(activity: str | None) -> str | None:
    a = (activity or "").lower()
    if a == "workout":
        return CAP_LOG_WORKOUT
    if a == "journal":
        return CAP_CREATE_JOURNAL_ENTRY
    if a == "bible":
        return CAP_OPEN_BIBLE_READING
    if a == "faith":
        return CAP_OPEN_FAITH
    return None


def _module_to_capability(module: str | None) -> str | None:
    m = (module or "").lower()
    if m in ("prayer",):
        return CAP_OPEN_PRAYER
    # A module of "faith" is the DOMAIN, not a specific workflow — land on faith
    # home. Bible-reading specificity comes from activity_type='bible' or a
    # bible keyword, not from the generic module.
    if m in ("faith", "bible", "scripture", "bible_reading", "faith_engaged"):
        return CAP_OPEN_FAITH
    if m == "journal":
        return CAP_CREATE_JOURNAL_ENTRY
    if m in ("nutrition", "meals"):
        return CAP_LOG_NUTRITION
    if m in ("fitness", "workout"):
        return CAP_LOG_WORKOUT
    if m in ("medicine", "intake", "supplements"):
        return CAP_LOG_INTAKE
    return None


# ── Title keyword bridge (LAST RESORT, documented) ──────────────────────────
# Ordered; first hit wins. Only consulted when metadata can't classify the item
# (nutrition / weight / measurements / prayer have no activity_type). Retire a
# row once the corresponding metadata exists.
_KEYWORD_BRIDGE: list[tuple[tuple[str, ...], str]] = [
    (("supplement", "medication", "medicine", "amino", "creatine", "fish oil",
      "metformin", "mounjaro", "lantus", "insulin", "vitamin", "magnesium",
      "take meds", "take medication"), CAP_LOG_INTAKE),
    (("measurement", "measurements", "body composition", "body-composition",
      "body fat", "waist", "tape measure", "circumference"), CAP_LOG_MEASUREMENTS),
    (("weigh", "weight", "scale", "step on the scale"), CAP_LOG_WEIGHT),
    (("nutrition", "meal", "macro", "macros", "calorie", "protein", "log food",
      "log nutrition", "eat"), CAP_LOG_NUTRITION),
    (("workout", "pickleball", "bike", "ride", "run", "running", "exercise",
      "gym", "cardio", "yoga", "stretch", "lift", "train"), CAP_LOG_WORKOUT),
    (("bible", "scripture", "devotional", "reading plan", "psalm", "gospel",
      "read the word"), CAP_OPEN_BIBLE_READING),
    (("prayer", "pray", "quiet time", "worship"), CAP_OPEN_PRAYER),
    (("journal", "journaling", "reflect", "gratitude"), CAP_CREATE_JOURNAL_ENTRY),
    (("dishwasher", "shower", "watch", "laundry", "chore", "trash", "garbage",
      "tidy", "clean", "make bed", "bed", "dishes", "vacuum"), CAP_OPEN_ROUTINES),
]


def _keyword_capability(title: str | None) -> str | None:
    t = (title or "").lower()
    if not t:
        return None
    for keywords, cap in _KEYWORD_BRIDGE:
        if any(kw in t for kw in keywords):
            return cap
    return None


def _routine_activity_type(item: dict) -> str | None:
    # Prefer the activity_type already on the item (no query); else look it up.
    at = item.get("activity_type")
    if at:
        return at
    source_id = item.get("source_id")
    if not source_id:
        return None
    try:
        from apps.life.models import RoutineSchedule
        sched = (RoutineSchedule.objects.filter(pk=source_id)
                 .only("activity_type").first())
        return sched.activity_type if sched else None
    except Exception:
        return None


def _task_module(source_id) -> str | None:
    if not source_id:
        return None
    try:
        from apps.life.models import Task
        task = Task.objects.filter(pk=source_id).only("module").first()
        return getattr(task, "module", None) if task else None
    except Exception:
        return None


def derive_capability(item: dict) -> str | None:
    """The deterministic capability an item represents (metadata-first)."""
    source_type = item.get("source_type")
    title = item.get("title") or ""

    # 1. Meds / supplements — source_type is authoritative.
    if source_type in ("medication_dose", "supplement_dose"):
        return CAP_LOG_INTAKE

    # 2. Routine items — canonical activity_type, then keyword, then household.
    if source_type == "routine_item":
        activity_cap = _activity_to_capability(_routine_activity_type(item))
        kw_cap = _keyword_capability(title)
        # Specific activity types (workout / journal / bible) are authoritative.
        if activity_cap and activity_cap != CAP_OPEN_FAITH:
            return activity_cap
        # Generic 'faith' activity → let the title pick the SPECIFIC faith
        # workflow (prayer vs bible vs journal) WITHIN the faith domain; if it
        # can't, land on faith home. (Metadata narrows the domain; the title
        # only disambiguates inside it.)
        if activity_cap == CAP_OPEN_FAITH:
            if kw_cap in (CAP_OPEN_PRAYER, CAP_OPEN_BIBLE_READING,
                          CAP_CREATE_JOURNAL_ENTRY):
                return kw_cap
            return CAP_OPEN_FAITH
        # No activity type → keyword bridge, else a genuine household routine.
        return kw_cap or CAP_OPEN_ROUTINES

    # 3. Tasks — canonical module / domain, then keyword.
    if source_type == "task":
        cap = _module_to_capability(_task_module(item.get("source_id")) or item.get("domain"))
        if cap:
            return cap
        cap = _keyword_capability(title)
        if cap:
            return cap
        if (item.get("domain") or "").lower() == "health":
            return CAP_OPEN_HEALTH
        return CAP_OPEN_LIFE

    # 4. Binary domain summaries (faith/workout/journal), if a focus surfaces one.
    cap = _module_to_capability(item.get("domain"))
    if cap:
        return cap

    # 5. Documented keyword bridge, then safe fallback.
    return _keyword_capability(title) or CAP_OPEN_LIFE


def resolve_action_destination(item: dict) -> str:
    """Resolve the canonical WLJ destination URL for an execution item/action,
    from its deterministic CAPABILITY (never its displayed wording).

    Returns a real, verified URL string. Never a dead link.
    """
    try:
        url = capability_to_url(derive_capability(item))
        return url or _dest("life:home", "/life/")
    except Exception:
        logger.debug("resolve_action_destination failed for %r", item, exc_info=True)
        return _dest("life:home", "/life/")
