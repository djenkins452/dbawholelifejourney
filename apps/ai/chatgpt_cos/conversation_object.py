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


def spec(fact_key):
    return CONVERSATION_OBJECTS.get(fact_key, {})


def supporting_for(fact_key):
    return spec(fact_key).get("supporting", ())


def follows_for(fact_key):
    return spec(fact_key).get("follows", (WHY,))
