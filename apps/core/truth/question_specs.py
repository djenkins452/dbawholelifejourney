"""
Question Specification — the reusable, data-driven certification unit (Owner-1 home).

A `QuestionSpec` is DATA, not a framework or a registry: it pairs a natural-language
question (reusable by Owner-2 / Customer Truth) with a DETERMINISTIC retrieval
descriptor + expected semantics (checkable by Owner-1 with NO OpenAI). The same spec
therefore serves both certification owners without duplicating question definitions.

Certification is organised around CAPABILITIES (not domains): every domain simply
declares which capabilities it supports. `capability_matrix()` renders that as the
planning artifact across all registered domains.
"""
from dataclasses import dataclass, field

# -- The eight retrieval capabilities ------------------------------------------------
CURRENT_FACT = "current_fact"
HISTORICAL = "historical"
LATEST = "latest"
TIMELINE = "timeline"
LIST = "list"
COUNT = "count"
EXISTENCE = "existence"
COMPARISON = "comparison"

CAPABILITIES = (CURRENT_FACT, HISTORICAL, LATEST, TIMELINE, LIST, COUNT,
                EXISTENCE, COMPARISON)


@dataclass(frozen=True)
class QuestionSpec:
    id: str                     # stable question id
    domain: str                 # canonical truth domain
    capability: str             # one of CAPABILITIES
    question: str               # natural-language question (Owner-2)
    surface: str                # deterministic retrieval: current|history|entity|entity_one
    args: dict                  # kwargs for the surface (values may be "@anchor" refs)
    expect: dict                # deterministic expectation (see run_spec)
    fixture: str                # certification_fixtures.FIXTURES key
    provider: str = ""          # expected canonical provider (domain)
    applicability: str = "applicable"
    criticality: str = "normal"


# ===================================================================================
# First vertical slice — Weight · Medication · Nutrition (SUPPORTED capabilities only;
# known gaps are declared in CAPABILITY_GAPS, never as passing specs).
# ===================================================================================
SLICE_SPECS = [
    # ---- WEIGHT (health) ----------------------------------------------------------
    QuestionSpec("weight.current", "health", CURRENT_FACT, "What do I weigh?",
                 "current", {"metric": "weight_yesterday"}, {"kind": "present"},
                 "weight", provider="health", criticality="critical"),
    QuestionSpec("weight.latest", "health", LATEST, "What is my latest recorded weight?",
                 "current", {"metric": "weight_yesterday"}, {"kind": "present"},
                 "weight", provider="health"),
    QuestionSpec("weight.historical", "health", HISTORICAL,
                 "What did I weigh on that date?", "history",
                 {"metric": "weight", "period": "custom",
                  "start": "@specific_date", "end": "@specific_date"},
                 {"kind": "series_point_value", "value": "@specific_weight"},
                 "weight", provider="health"),
    QuestionSpec("weight.timeline", "health", TIMELINE,
                 "What weights were recorded over this period?", "history",
                 {"metric": "weight", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_min_points", "n": 3}, "weight", provider="health"),
    QuestionSpec("weight.comparison", "health", COMPARISON,
                 "Is my latest weight lower than the previous one?", "history",
                 {"metric": "weight", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_latest_lt_prev"}, "weight", provider="health"),

    # ---- MEDICATION (medicine) ----------------------------------------------------
    QuestionSpec("med.list", "medicine", LIST, "What medications am I taking?",
                 "current", {"metric": "current_medications"},
                 {"kind": "list_contains_all", "value": "@med_names"},
                 "medication", provider="medicine", criticality="critical"),
    QuestionSpec("med.current", "medicine", CURRENT_FACT,
                 "What is my latest medication state today?", "current",
                 {"metric": "medication_execution_today"}, {"kind": "present"},
                 "medication", provider="medicine"),
    QuestionSpec("med.existence_pos", "medicine", EXISTENCE, "Am I taking Metformin?",
                 "entity_one", {"name": "Metformin"}, {"kind": "entity_found"},
                 "medication", provider="medicine"),
    QuestionSpec("med.existence_neg", "medicine", EXISTENCE, "Am I taking Aspirin?",
                 "entity_one", {"name": "Aspirin"}, {"kind": "entity_absent"},
                 "medication", provider="medicine"),
    QuestionSpec("med.history", "medicine", HISTORICAL,
                 "What medication adherence history is available?", "history",
                 {"metric": "adherence", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_min_points", "n": 1}, "medication", provider="medicine"),
    QuestionSpec("med.last_taken", "medicine", LATEST, "When did I last take Metformin?",
                 "entity_one", {"name": "Metformin"},
                 {"kind": "entity_field", "path": "performance.last_taken",
                  "value": "@last_taken_date"}, "medication", provider="medicine"),

    # ---- NUTRITION (nutrition) ----------------------------------------------------
    QuestionSpec("nutrition.list", "nutrition", LIST, "What have I eaten?",
                 "entity", {"entity_type": "food"}, {"kind": "entities_min", "n": 3},
                 "nutrition", provider="nutrition"),
    QuestionSpec("nutrition.latest", "nutrition", LATEST, "What was my latest meal?",
                 "entity", {"entity_type": "food"}, {"kind": "entities_min", "n": 1},
                 "nutrition", provider="nutrition"),
    QuestionSpec("nutrition.existence_pos", "nutrition", EXISTENCE,
                 "Have I eaten pizza?", "entity_one", {"name": "pizza"},
                 {"kind": "entity_found"}, "nutrition", provider="nutrition"),
    QuestionSpec("nutrition.existence_neg", "nutrition", EXISTENCE,
                 "Have I eaten sushi?", "entity_one", {"name": "sushi"},
                 {"kind": "entity_absent"}, "nutrition", provider="nutrition"),
    # Date-scoped totals + windowed averages via the new nutrition history() surface
    # (get_history). Closes the measured HISTORICAL/TIMELINE gap (2026-07-18).
    QuestionSpec("nutrition.calories_yesterday", "nutrition", HISTORICAL,
                 "How many calories did I eat yesterday?", "history",
                 {"metric": "calories", "period": "yesterday"},
                 {"kind": "series_point_value", "value": "@calories_yesterday"},
                 "nutrition", provider="nutrition", criticality="critical"),
    QuestionSpec("nutrition.timeline", "nutrition", TIMELINE,
                 "What did my calories look like this week?", "history",
                 {"metric": "calories", "period": "custom",
                  "start": "@week_start", "end": "@week_end"},
                 {"kind": "series_min_points", "n": 3}, "nutrition", provider="nutrition"),
    QuestionSpec("nutrition.calories_week_avg", "nutrition", TIMELINE,
                 "What are my average calories this week?", "history",
                 {"metric": "calories", "period": "custom",
                  "start": "@week_start", "end": "@week_end"},
                 {"kind": "series_average_equals", "value": "@avg_calories_week"},
                 "nutrition", provider="nutrition"),
    QuestionSpec("nutrition.protein_week_avg", "nutrition", TIMELINE,
                 "What is my average protein this week?", "history",
                 {"metric": "protein", "period": "custom",
                  "start": "@week_start", "end": "@week_end"},
                 {"kind": "series_average_equals", "value": "@avg_protein_week"},
                 "nutrition", provider="nutrition"),
    QuestionSpec("nutrition.carbs_week_avg", "nutrition", TIMELINE,
                 "What are my average carbs this week?", "history",
                 {"metric": "carbs", "period": "custom",
                  "start": "@week_start", "end": "@week_end"},
                 {"kind": "series_average_equals", "value": "@avg_carbs_week"},
                 "nutrition", provider="nutrition"),
    QuestionSpec("nutrition.fat_week_avg", "nutrition", TIMELINE,
                 "What is my average fat this week?", "history",
                 {"metric": "fat", "period": "custom",
                  "start": "@week_start", "end": "@week_end"},
                 {"kind": "series_average_equals", "value": "@avg_fat_week"},
                 "nutrition", provider="nutrition"),

    # ---- HEALTH VITALS TRENDS — glucose + blood pressure (health) ------------------
    # Closes the measured glucose/BP TREND gap (2026-07-18): current facts passed but
    # history_metrics excluded glucose & BP. Now answerable via get_history.
    QuestionSpec("health.glucose_timeline", "health", TIMELINE,
                 "What was my glucose trend this week?", "history",
                 {"metric": "glucose", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_min_points", "n": 3}, "vitals", provider="health"),
    QuestionSpec("health.glucose_week_avg", "health", TIMELINE,
                 "What is my average glucose this week?", "history",
                 {"metric": "glucose", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_average_equals", "value": "@glucose_week_avg"},
                 "vitals", provider="health"),
    QuestionSpec("health.bp_systolic_timeline", "health", TIMELINE,
                 "How has my blood pressure changed this month?", "history",
                 {"metric": "bp_systolic", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_min_points", "n": 3}, "vitals", provider="health"),
    QuestionSpec("health.bp_diastolic_avg", "health", TIMELINE,
                 "What is my average diastolic pressure this month?", "history",
                 {"metric": "bp_diastolic", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_average_equals", "value": "@bp_diastolic_week_avg"},
                 "vitals", provider="health"),
    QuestionSpec("health.bp_change", "health", COMPARISON,
                 "Is my latest blood pressure lower than before?", "history",
                 {"metric": "bp_systolic", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_latest_lt_prev"}, "vitals", provider="health"),

    # ---- BODY MEASUREMENTS — waist / body composition (health) ---------------------
    # Closes the measured Body-Measurements gap (2026-07-18): BodyCompositionEntry data
    # existed with NO point-in-time/series accessor. ("Latest measurements" already
    # reach the model via get_domain_state('health') SAE; trend is the true gap.)
    QuestionSpec("health.waist_timeline", "health", TIMELINE,
                 "How has my waist changed over time?", "history",
                 {"metric": "waist", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_min_points", "n": 3}, "body", provider="health"),
    QuestionSpec("health.waist_avg", "health", TIMELINE,
                 "What is my average waist measurement this month?", "history",
                 {"metric": "waist", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_average_equals", "value": "@waist_avg"},
                 "body", provider="health"),
    QuestionSpec("health.waist_change", "health", COMPARISON,
                 "Is my waist smaller than it was before?", "history",
                 {"metric": "waist", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_latest_lt_prev"}, "body", provider="health"),

    # ---- JOURNAL ------------------------------------------------------------------
    QuestionSpec("journal.entries", "journal", LIST,
                 "What have I written about this week?", "entity",
                 {"entity_type": "entry"}, {"kind": "entities_min", "n": 3},
                 "journal", provider="journal"),
    QuestionSpec("journal.entry_by_date", "journal", EXISTENCE,
                 "What did I journal yesterday?", "entity_one",
                 {"name": "@yesterday"}, {"kind": "entity_found"},
                 "journal", provider="journal"),
    QuestionSpec("journal.mood_history", "journal", TIMELINE,
                 "How has my mood changed recently?", "history",
                 {"metric": "mood", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_min_points", "n": 2}, "journal", provider="journal"),

    # ---- FAITH --------------------------------------------------------------------
    QuestionSpec("faith.prayers", "faith", LIST,
                 "What have I been praying about recently?", "entity",
                 {"entity_type": "prayer"}, {"kind": "entities_min", "n": 2},
                 "faith", provider="faith"),
    QuestionSpec("faith.prayer_lookup", "faith", EXISTENCE,
                 "Am I praying about healing?", "entity_one",
                 {"name": "@prayer_name"}, {"kind": "entity_found"},
                 "faith", provider="faith"),

    # ---- PEOPLE / RELATIONSHIPS ---------------------------------------------------
    QuestionSpec("rel.people", "relationships", LIST,
                 "Who are the people in my life?", "entity",
                 {"entity_type": "person"}, {"kind": "entities_min", "n": 2},
                 "relationships", provider="relationships"),
    QuestionSpec("rel.tell_about", "relationships", EXISTENCE,
                 "Tell me about Heather.", "entity_one",
                 {"name": "@heather"}, {"kind": "entity_found"},
                 "relationships", provider="relationships"),
    QuestionSpec("rel.last_contact", "relationships", CURRENT_FACT,
                 "When did I last spend time with Heather?", "entity_one",
                 {"name": "@heather"},
                 {"kind": "entity_field", "path": "definition.last_contact",
                  "value": "@heather_last"}, "relationships", provider="relationships"),

    # ---- CALENDAR -----------------------------------------------------------------
    QuestionSpec("cal.tomorrow", "calendar", CURRENT_FACT,
                 "What do I have tomorrow?", "current",
                 {"metric": "tomorrow_event_count"}, {"kind": "present"},
                 "calendar", provider="calendar"),
    QuestionSpec("cal.upcoming", "calendar", CURRENT_FACT,
                 "What meetings are coming up?", "current",
                 {"metric": "upcoming_count"}, {"kind": "present"},
                 "calendar", provider="calendar"),
    QuestionSpec("cal.events", "calendar", LIST,
                 "What appointments have I recently completed / do I have?", "entity",
                 {"entity_type": "event"}, {"kind": "entities_min", "n": 2},
                 "calendar", provider="calendar"),
    QuestionSpec("cal.event_history", "calendar", TIMELINE,
                 "How many events did I have over this period?", "history",
                 {"metric": "events", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_min_points", "n": 1}, "calendar", provider="calendar"),

    # ---- TASKS --------------------------------------------------------------------
    QuestionSpec("tasks.completed_history", "tasks", TIMELINE,
                 "What have I accomplished this week?", "history",
                 {"metric": "completed", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_min_points", "n": 2}, "tasks", provider="tasks"),
    QuestionSpec("tasks.list", "tasks", LIST,
                 "What is overdue / what did I complete?", "entity",
                 {"entity_type": "task"}, {"kind": "entities_min", "n": 3},
                 "tasks", provider="tasks"),
    QuestionSpec("tasks.lookup", "tasks", EXISTENCE,
                 "What's the status of my taxes task?", "entity_one",
                 {"name": "@task_name"}, {"kind": "entity_found"},
                 "tasks", provider="tasks"),

    # ---- GOALS / MISSIONS ---------------------------------------------------------
    QuestionSpec("goals.active", "goals", CURRENT_FACT,
                 "What are my active goals?", "current",
                 {"metric": "active_goals"}, {"kind": "present"},
                 "goals", provider="goals", criticality="critical"),
    QuestionSpec("goals.primary_mission", "goals", CURRENT_FACT,
                 "What is my primary mission?", "current",
                 {"metric": "primary_mission"}, {"kind": "present"},
                 "goals", provider="goals"),
    QuestionSpec("goals.completion_rate", "goals", CURRENT_FACT,
                 "How much progress have I made?", "current",
                 {"metric": "completion_rate"}, {"kind": "present"},
                 "goals", provider="goals"),
    QuestionSpec("goals.milestones_overdue", "goals", CURRENT_FACT,
                 "Which milestones are overdue?", "current",
                 {"metric": "milestones_overdue"}, {"kind": "present"},
                 "goals", provider="goals"),
    QuestionSpec("goals.list", "goals", LIST,
                 "List my goals and milestones.", "entity",
                 {"entity_type": "goal"}, {"kind": "entities_min", "n": 1},
                 "goals", provider="goals"),
    QuestionSpec("goals.mission_lookup", "goals", EXISTENCE,
                 "How am I progressing toward my France 2027 mission?", "entity_one",
                 {"name": "@mission"}, {"kind": "entity_found"},
                 "goals", provider="goals"),
    QuestionSpec("goals.progress_history", "goals", TIMELINE,
                 "How has my mission progress trended?", "history",
                 {"metric": "progress", "period": "custom",
                  "start": "@range_start", "end": "@range_end"},
                 {"kind": "series_min_points", "n": 3}, "goals", provider="goals"),

    # ---- LEGACY -------------------------------------------------------------------
    QuestionSpec("legacy.people", "legacy", LIST,
                 "Tell me about my family history.", "entity",
                 {"entity_type": "person"}, {"kind": "entities_min", "n": 2},
                 "legacy", provider="legacy"),
    QuestionSpec("legacy.person_lookup", "legacy", EXISTENCE,
                 "Tell me about Harold Keck.", "entity_one",
                 {"name": "@person"}, {"kind": "entity_found"},
                 "legacy", provider="legacy"),
    QuestionSpec("legacy.places", "legacy", LIST,
                 "What places have special meaning to me?", "entity",
                 {"entity_type": "place"}, {"kind": "entities_min", "n": 1},
                 "legacy", provider="legacy"),

    # ---- NUTRITION — scoped retrieval (deterministic, not model inference) ---------
    QuestionSpec("nutrition.lunch_this_week", "nutrition", LIST,
                 "Show every lunch this week.", "entity",
                 {"entity_type": "food",
                  "filters": {"meal": "lunch", "period": "custom",
                              "start": "@week_start", "end": "@week_end"}},
                 {"kind": "entities_min", "n": 2}, "nutrition_scoped", provider="nutrition"),
    QuestionSpec("nutrition.breakfast_this_week", "nutrition", LIST,
                 "Show every breakfast this week.", "entity",
                 {"entity_type": "food",
                  "filters": {"meal": "breakfast", "period": "custom",
                              "start": "@week_start", "end": "@week_end"}},
                 {"kind": "entities_min", "n": 3}, "nutrition_scoped", provider="nutrition"),
    QuestionSpec("nutrition.dinner_this_week", "nutrition", LIST,
                 "Show every dinner this month.", "entity",
                 {"entity_type": "food",
                  "filters": {"meal": "dinner", "period": "custom",
                              "start": "@week_start", "end": "@week_end"}},
                 {"kind": "entities_min", "n": 2}, "nutrition_scoped", provider="nutrition"),
    QuestionSpec("nutrition.fast_food_count", "nutrition", COUNT,
                 "How often have I eaten fast food?", "entity",
                 {"entity_type": "food",
                  "filters": {"contains": "@fast_food", "period": "custom",
                              "start": "@week_start", "end": "@week_end"}},
                 {"kind": "entities_count_equals", "n": 2}, "nutrition_scoped",
                 provider="nutrition"),
    QuestionSpec("nutrition.last_lasagna", "nutrition", EXISTENCE,
                 "When did I last eat lasagna?", "entity_one",
                 {"name": "@pizza_or_last"}, {"kind": "entity_found"},
                 "nutrition_scoped", provider="nutrition"),

    # ---- PEOPLE — most important + upcoming birthday ------------------------------
    QuestionSpec("rel.most_connected", "relationships", LIST,
                 "Who are the most important people in my life?", "current",
                 {"metric": "most_connected"}, {"kind": "present"},
                 "relationships", provider="relationships"),
    QuestionSpec("rel.upcoming_birthday", "relationships", CURRENT_FACT,
                 "Whose birthday is coming up?", "current",
                 {"metric": "upcoming_birthdays"}, {"kind": "present"},
                 "relationships", provider="relationships"),

    # ---- JOURNAL — scoped + themes -----------------------------------------------
    QuestionSpec("journal.this_week", "journal", LIST,
                 "What have I written this week?", "entity",
                 {"entity_type": "entry",
                  "filters": {"period": "custom", "start": "@week_start",
                              "end": "@week_end"}},
                 {"kind": "entities_min", "n": 3}, "journal", provider="journal"),
    QuestionSpec("journal.themes", "journal", CURRENT_FACT,
                 "What concerns have I repeated / topics this month?", "current",
                 {"metric": "themes"}, {"kind": "present"}, "journal", provider="journal"),

    # ---- GOALS — milestones completed --------------------------------------------
    QuestionSpec("goals.milestones_completed", "goals", CURRENT_FACT,
                 "Which milestones have I completed?", "current",
                 {"metric": "milestones_completed"}, {"kind": "present"},
                 "goals", provider="goals"),

    # ---- LEGACY — memories scoped by person / era --------------------------------
    QuestionSpec("legacy.memories_involving", "legacy", LIST,
                 "Show memories involving Harold.", "entity",
                 {"entity_type": "memory", "filters": {"involves": "@involves"}},
                 {"kind": "entities_min", "n": 2}, "legacy", provider="legacy"),
    QuestionSpec("legacy.childhood", "legacy", LIST,
                 "Show childhood memories.", "entity",
                 {"entity_type": "memory", "filters": {"occurred_to": 1940}},
                 {"kind": "entities_min", "n": 2}, "legacy", provider="legacy"),

    # ---- CALENDAR — specific past day --------------------------------------------
    QuestionSpec("cal.last_tuesday", "calendar", LIST,
                 "What did I have last Tuesday?", "entity",
                 {"entity_type": "event", "filters": {"on_date": "@past_date"}},
                 {"kind": "entities_min", "n": 1}, "calendar", provider="calendar"),

    # ---- PEOPLE — cross-WLJ composition about one person -------------------------
    QuestionSpec("rel.everything", "relationships", EXISTENCE,
                 "Tell me everything you know about Heather.", "entity_one",
                 {"name": "@heather"}, {"kind": "entity_found"},
                 "relationships", provider="relationships"),
    QuestionSpec("rel.working_on", "relationships", EXISTENCE,
                 "What have Heather and I been working on?", "entity_one",
                 {"name": "@heather"},
                 {"kind": "entity_field_present", "path": "extensions.interactions_by_context"},
                 "relationships", provider="relationships"),
    QuestionSpec("rel.journal_mentions", "relationships", EXISTENCE,
                 "What journal entries mention Heather?", "entity_one",
                 {"name": "@heather"},
                 {"kind": "entity_field_present", "path": "extensions.journal_entries"},
                 "relationships", provider="relationships"),
    QuestionSpec("rel.memories_involving", "relationships", EXISTENCE,
                 "What memories involve Heather?", "entity_one",
                 {"name": "@heather"},
                 {"kind": "entity_field_present", "path": "extensions.memories"},
                 "relationships", provider="relationships"),
    QuestionSpec("rel.goals_involving", "relationships", EXISTENCE,
                 "What goals involve Heather?", "entity_one",
                 {"name": "@heather"},
                 {"kind": "entity_field_present", "path": "extensions.goals"},
                 "relationships", provider="relationships"),
    QuestionSpec("rel.trips", "relationships", EXISTENCE,
                 "What trips have Heather and I taken?", "entity_one",
                 {"name": "@heather"},
                 {"kind": "entity_field_present", "path": "extensions.shared_places"},
                 "relationships", provider="relationships"),

    # ---- LEGACY — signature retrieval --------------------------------------------
    QuestionSpec("legacy.grandfather", "legacy", EXISTENCE,
                 "Tell me about my grandfather.", "entity_one",
                 {"name": "@grandfather"}, {"kind": "entity_found"},
                 "legacy", provider="legacy"),
    QuestionSpec("legacy.parents", "legacy", LIST,
                 "Tell me about my parents.", "entity",
                 {"entity_type": "person", "filters": {"relationship": "father"}},
                 {"kind": "entities_min", "n": 1}, "legacy", provider="legacy"),
    QuestionSpec("legacy.life_events", "legacy", LIST,
                 "What important life events have I captured?", "entity",
                 {"entity_type": "memory", "filters": {"entry_type": "event"}},
                 {"kind": "entities_min", "n": 1}, "legacy", provider="legacy"),
    QuestionSpec("legacy.recent", "legacy", LIST,
                 "What memories have I recorded recently?", "entity",
                 {"entity_type": "memory"}, {"kind": "entities_min", "n": 3},
                 "legacy", provider="legacy"),
]


# Known, honest gaps — capabilities a slice domain does NOT yet support deterministically
# (data may exist, but the DomainTruth SURFACE the CoS uses cannot answer it). These are
# the additive follow-ons; they are NEVER written as passing specs.
CAPABILITY_GAPS = {
    "nutrition": {
        # HISTORICAL + TIMELINE closed 2026-07-18 by NutritionDomainTruth.history()
        # (per-day macro totals → get_history date-scoped totals + windowed averages).
        CURRENT_FACT: "no generic current-fact tool for nutrition; today's running "
                      "totals reach the model via get_domain_state('nutrition')",
        COMPARISON: "no comparison surface",
    },
    "health": {
        COUNT: "no arbitrary windowed count surface (e.g. 'how many weigh-ins this month')",
    },
    "medicine": {
        COMPARISON: "no adherence comparison surface",
        COUNT: "no windowed count surface",
    },
}


# ===================================================================================
# Deterministic evaluator — Owner-1 checks a spec with NO model.
# ===================================================================================
def _resolve(v, anchors):
    if isinstance(v, str) and v.startswith("@"):
        return anchors[v[1:]]
    if isinstance(v, dict):          # resolve nested anchors (e.g. inside `filters`)
        return {k: _resolve(x, anchors) for k, x in v.items()}
    return v


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def run_spec(user, spec, anchors):
    """Execute a spec's deterministic retrieval + expectation against `user`.
    Returns (passed: bool, detail: dict). No OpenAI."""
    from apps.core.truth.domain import get_domain_truth
    truth = get_domain_truth(user, spec.domain)
    args = {k: _resolve(v, anchors) for k, v in spec.args.items()}
    exp = spec.expect
    kind = exp["kind"]

    if spec.surface == "current":
        ct = truth.current(args["metric"])
        if kind == "present":
            return bool(ct.present), {"value": ct.value}
        if kind == "value_equals":
            want = _resolve(exp["value"], anchors)
            a, b = _num(ct.value), _num(want)
            ok = (a is not None and b is not None and abs(a - b) < 0.05) or ct.value == want
            return bool(ct.present and ok), {"value": ct.value, "want": want}
        if kind == "list_contains_all":
            want = _resolve(exp["value"], anchors)
            val = ct.value or []
            return bool(ct.present and all(w in val for w in want)), {"value": val}

    elif spec.surface == "history":
        hs = truth.history(args["metric"], args.get("period", "last_7_days"),
                           **{k: v for k, v in args.items() if k in ("start", "end")})
        pts = list(getattr(hs, "points", []))
        if kind == "series_min_points":
            return len(pts) >= exp["n"], {"points": len(pts)}
        if kind == "series_latest_lt_prev":
            return (len(pts) >= 2 and _num(pts[-1].value) < _num(pts[-2].value)), \
                   {"points": len(pts)}
        if kind == "series_point_value":
            want = _num(_resolve(exp["value"], anchors))
            vals = [_num(p.value) for p in pts]
            return (any(v is not None and abs(v - want) < 0.05 for v in vals)), {"vals": vals}
        if kind == "series_average_equals":
            want = _num(_resolve(exp["value"], anchors))
            avg = _num(hs.average()) if hs is not None else None
            return (avg is not None and want is not None and abs(avg - want) < 0.5), \
                   {"average": avg, "want": want}

    elif spec.surface == "entity":
        _f = args.get("filters")
        ents = (truth.describe(args.get("entity_type", "food"), filters=_f) if _f
                else truth.describe(args.get("entity_type", "food"))) or []
        if kind == "entities_min":
            return len(ents) >= exp["n"], {"count": len(ents)}
        if kind == "entities_count_equals":
            return len(ents) == exp["n"], {"count": len(ents)}
        if kind == "entities_contain":
            sub = str(_resolve(exp["value"], anchors)).lower()
            return (any(sub in (getattr(e, "identity", "") or "").lower() for e in ents)), \
                   {"count": len(ents)}

    elif spec.surface == "entity_one":
        ent = truth.describe_one(args["name"])
        if kind == "entity_found":
            return ent is not None, {"found": ent is not None}
        if kind == "entity_absent":
            return ent is None, {"found": ent is not None}
        if kind in ("entity_field", "entity_field_present"):
            if ent is None:
                return False, {"found": False}
            cur = ent
            for part in exp["path"].split("."):
                cur = (cur.get(part) if isinstance(cur, dict)
                       else getattr(cur, part, None))
                if cur is None:
                    break
            if kind == "entity_field_present":
                return bool(cur), {"got": str(cur)[:80]}
            want = _resolve(exp["value"], anchors)
            return str(cur) == str(want), {"got": str(cur), "want": str(want)}

    return False, {"error": f"unhandled surface/kind {spec.surface}/{kind}"}


# ===================================================================================
# Capability matrix — the primary planning artifact across all registered domains.
# ===================================================================================
def _assessed_caps(supports):
    """Capabilities IMPLIED by a provider's declared supports() (breadth, not proof)."""
    caps = set()
    if supports.get("current"):
        caps |= {CURRENT_FACT, LATEST}
    if supports.get("history"):
        caps |= {HISTORICAL, TIMELINE}
    if supports.get("entities"):
        caps |= {LIST, EXISTENCE, LATEST}
    return caps


def capability_matrix():
    """{domain: {capability: status}} where status ∈
    'certified' (a passing deterministic spec exists) | 'gap' (declared missing) |
    'assessed' (provider supports() implies it, no deterministic spec yet) | 'na'."""
    from apps.core.truth.domain import get_domain_truth, registered_domains
    spec_caps = {}
    for s in SLICE_SPECS:
        spec_caps.setdefault(s.domain, set()).add(s.capability)

    matrix = {}
    for domain in registered_domains():
        try:
            sup = get_domain_truth(None, domain).supports()
        except Exception:
            sup = {}
        certified, assessed = spec_caps.get(domain, set()), _assessed_caps(sup)
        gaps = CAPABILITY_GAPS.get(domain, {})
        row = {}
        for cap in CAPABILITIES:
            if cap in certified:
                row[cap] = "certified"
            elif cap in gaps:
                row[cap] = "gap"
            elif cap in assessed:
                row[cap] = "assessed"
            else:
                row[cap] = "na"
        matrix[domain] = row
    return matrix


def matrix_summary():
    """Counts for the operational view: certified / assessed / gap across all domains."""
    m = capability_matrix()
    tally = {"certified": 0, "assessed": 0, "gap": 0, "na": 0}
    for row in m.values():
        for status in row.values():
            tally[status] = tally.get(status, 0) + 1
    return {"domains": len(m), "capabilities": len(CAPABILITIES), **tally,
            "slice_domains": sorted({s.domain for s in SLICE_SPECS}),
            "slice_specs": len(SLICE_SPECS)}
