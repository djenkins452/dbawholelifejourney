"""
Conversation Object registry.

A deterministic fact is not complete until the conversation that naturally follows it
can be answered WITHOUT another retrieval, query, or LLM reconstruction. So each PRIMARY
fact declares a Conversation Object: the SUPPORTING facts a follow-up needs (gathered
once with the primary answer) and the follow-up capabilities it offers.

Generalized and domain-agnostic. Adding a fact's full conversation = adding a row here;
the generic handlers (when/concern/meaning/is_current/comparison/supporting/why) and the
supporting-fact gatherer both read this registry. This is the structure that stops us
fixing one follow-up at a time.

`supporting`: tuple of (label, source, provider_key) — source ∈ {"execution","health"}.
`follows`:    follow-up capabilities the object supports (documentation + completeness).
"""

# Follow-up capability labels (handlers live in conversation_memory).
WHEN = "when"            # "at what time?" — needs a timestamp
CONCERN = "concern"      # "should I be concerned? / is that good?" — needs interpretation
MEANING = "meaning"      # "why is that important?" — needs interpretation.meaning
CURRENT = "current"      # "is that current?" — needs timestamp + freshness
COMPARISON = "comparison"  # "compared to yesterday / my average?" — needs a 'prior'/'average' supporting fact
SUPPORTING_MEALS = "supporting_meals"  # "what did I eat?" — needs a 'meals' supporting fact
WHY = "why"              # "why do you say that?" — always available

CONVERSATION_OBJECTS = {
    # ---- Nutrition ----------------------------------------------------------
    "calories_today": {
        "supporting": (("meals", "execution", "meals_today"),
                       ("protein", "health", "protein_today"),
                       ("prior", "health", "calories_yesterday")),
        "follows": (SUPPORTING_MEALS, COMPARISON, WHY),
    },
    "calories_yesterday": {
        "supporting": (("meals", "execution", "meals_yesterday"),),
        "follows": (SUPPORTING_MEALS, WHY),
    },
    # ---- Activity -----------------------------------------------------------
    "steps_today": {
        "supporting": (("prior", "health", "steps_yesterday"),),
        "follows": (COMPARISON, WHY),
    },
    "steps_yesterday": {"supporting": (), "follows": (WHY,)},
    # ---- Sleep --------------------------------------------------------------
    "sleep_last_night": {
        "supporting": (("average", "health", "average_sleep_7d"),),
        "follows": (WHEN, COMPARISON, WHY),
    },
    # ---- Glucose (clinical) -------------------------------------------------
    "last_glucose_reading": {
        "supporting": (("average", "health", "average_glucose_yesterday"),),
        "follows": (WHEN, CONCERN, MEANING, CURRENT, COMPARISON, WHY),
    },
    "glucose_yesterday": {
        "supporting": (),
        "follows": (WHEN, CONCERN, MEANING, CURRENT, WHY),
    },
    # ---- Weight -------------------------------------------------------------
    "weight_yesterday": {"supporting": (), "follows": (WHEN, WHY)},
    "current_weight": {"supporting": (), "follows": (WHEN, WHY)},
}


# ---------------------------------------------------------------------------
# Conversational frame: a TOPIC is the timeframe-independent subject of a fact.
# (topic, timeframe) <-> fact_key lets a bare reference ("what about yesterday?")
# re-point the SAME topic to a new timeframe — no restated subject, no topic drift.
# ---------------------------------------------------------------------------
TOPICS = {
    "meals_today": ("meals", "today"),
    "meals_yesterday": ("meals", "yesterday"),
    "calories_today": ("calories", "today"),
    "calories_yesterday": ("calories", "yesterday"),
    "protein_today": ("protein", "today"),
    "steps_today": ("steps", "today"),
    "steps_yesterday": ("steps", "yesterday"),
    "last_glucose_reading": ("glucose", "today"),
    "glucose_yesterday": ("glucose", "yesterday"),
    "current_weight": ("weight", "today"),
    "weight_yesterday": ("weight", "yesterday"),
    "sleep_last_night": ("sleep", "today"),
    "journal_today": ("journal", "today"),
    "workout_today": ("workout", "today"),
    "workout_yesterday": ("workout", "yesterday"),
    "appointments_today": ("calendar", "today"),
}
_FACT_BY_TOPIC = {(topic, tf): k for k, (topic, tf) in TOPICS.items()}


# ---------------------------------------------------------------------------
# Conversation GOAL: what the user is trying to accomplish (independent of topic).
# The topic stays stable; the goal evolves naturally — review → compare → trend →
# investigate — so Beth participates in a discussion instead of answering isolated
# prompts. Generalized across every topic.
# ---------------------------------------------------------------------------
GOAL_REVIEW = "review"          # show the fact
GOAL_COMPARE = "compare"        # A vs B across timeframes
GOAL_TREND = "trend"            # direction over time / vs average
GOAL_INVESTIGATE = "investigate"  # why / what changed / what caused it


def evolve_goal(prev, new_topic, new_timeframe, explicit=None):
    """Deterministic goal evolution. `prev` is the previously stored frame (or None).
    An explicit hint (set by the resolver for an obvious objective) always wins; else
    a same-topic move to a new timeframe is the moment a COMPARISON intent emerges."""
    if explicit:
        return explicit
    if not prev or not new_topic or prev.get("topic") != new_topic:
        return GOAL_REVIEW                       # new topic / fresh start
    if new_timeframe and prev.get("timeframe") != new_timeframe:
        return GOAL_COMPARE                       # same topic, another day → comparing
    return prev.get("goal") or GOAL_REVIEW        # unchanged → keep the standing goal


def topic_of(fact_key):
    """(topic, timeframe) for a fact_key, or None."""
    return TOPICS.get(fact_key)


def fact_for_topic(topic, timeframe):
    """The fact_key for a (topic, timeframe), or None if that timeframe isn't tracked."""
    return _FACT_BY_TOPIC.get((topic, timeframe))


# ---------------------------------------------------------------------------
# Comparison Semantics: each metric declares HOW it should be compared, so the
# comparison engine never guesses — it asks the domain. Knowing how to compare is a
# different capability from knowing WHAT to compare.
#   strategy:    "running_total" (accumulates through the day — compare the totals)
#                "latest"        (a point-in-time reading — compare the readings)
#                "nightly"       (one value per night — compare the nights)
#                "average"       (point readings are noisy — compare against the average)
#   confidence:  how trustworthy this comparison is for a real decision
#   explanation: why this is the right comparison (surfaced to the customer)
# ---------------------------------------------------------------------------
_DEFAULT_SEMANTICS = {"strategy": "latest", "confidence": "medium", "explanation": ""}

COMPARISON_SEMANTICS = {
    "glucose": {
        "strategy": "average", "confidence": "high",
        "explanation": ("individual glucose readings swing a lot through the day, so a "
                        "single reading rarely reflects your overall control"),
    },
    "steps": {"strategy": "running_total", "confidence": "high",
              "explanation": "steps accumulate through the day, so I compared running totals"},
    "calories": {"strategy": "running_total", "confidence": "high",
                 "explanation": "calories accumulate through the day, so I compared running totals"},
    "protein": {"strategy": "running_total", "confidence": "high",
                "explanation": "protein accumulates through the day"},
    "weight": {"strategy": "latest", "confidence": "medium",
               "explanation": "weight is your most recent weigh-in"},
    "sleep": {"strategy": "nightly", "confidence": "medium",
              "explanation": "I compared the two nights"},
    "blood_pressure": {"strategy": "latest", "confidence": "medium",
                       "explanation": "I compared your most recent readings"},
}


def comparison_semantics(topic):
    """The declared Comparison Semantics for a topic (never guesses — defaults to a
    medium-confidence 'latest' when a topic hasn't declared its own)."""
    return COMPARISON_SEMANTICS.get(topic, _DEFAULT_SEMANTICS)


def spec(fact_key):
    return CONVERSATION_OBJECTS.get(fact_key, {})


def supporting_for(fact_key):
    return spec(fact_key).get("supporting", ())


def follows_for(fact_key):
    return spec(fact_key).get("follows", (WHY,))
