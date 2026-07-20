"""
Platform capability support: DOMAIN SEMANTICS (plain-language capability metadata).

The ONE authoritative, human-language description of what each truth domain and each
of its entities MEANS — so the conversational model routes by MEANING, not by matching
a domain NAME. The capability index (`_capabilities`) exposes this to Current Context,
and the Model Interface tool descriptions consume it; no surface maintains its own
parallel prose.

WHY: two domains can both legitimately contain an English concept — e.g. `nutrition`
(a meal you ATE) vs `meals` (a meal you PLAN/COOK), or `calendar.event` (scheduled
time) vs `events.event` (a significant life event), or `relationships.person` vs
`legacy.person`. Domain names alone cannot disambiguate these; the model needs the
semantic purpose + entity descriptions + explicit boundary notes.

CONTRACT (enforced by apps/core/truth/tests/test_capability_semantics.py):
  * every domain advertising ≥1 entity/history/analysis has a non-empty `purpose`;
  * every advertised entity_type has a description;
  * `nutrition.meal` reads as an EATEN/logged meal; the `meals` domain reads as
    recipe/supply/planning/preparation;
  * this registry stays catalog-driven (keys ⊆ registered domains; advertised
    domains ⊆ this registry).

Shape: {domain: {"purpose": str,
                 "entities": {entity_type: str, ...},
                 "boundary": str (optional — the distinction to a sibling domain),
                 "cues": [str, ...] (optional — natural phrasings that route here)}}.
"""

DOMAIN_SEMANTICS = {
    # ── Consumption vs supply: the nutrition/meals boundary ──────────────────
    "nutrition": {
        "purpose": ("What the person ACTUALLY ATE — their logged foods and meals, "
                    "calories and nutrients, and consumption history (breakfast, "
                    "lunch, dinner, snacks)."),
        "entities": {
            "food": "One food item the person logged eating, with its macros.",
            "meal": ("A meal the person ATE — the foods logged for a breakfast / "
                     "lunch / dinner / snack on a given day, with per-meal totals."),
            "frequent_food": ("The person's most-logged foods, ranked by how OFTEN "
                              "they were eaten (with counts and a time window)."),
        },
        "boundary": ("Consumption truth — what was EATEN. For recipes, pantry/supply, "
                     "meal plans, leftovers, or what the person COULD cook, use the "
                     "'meals' domain."),
        "cues": ["what did I eat", "my last meal", "calories today",
                 "everything I ate last Tuesday", "what do I eat most",
                 "how much protein today", "summarize my nutrition"],
    },
    "meals": {
        "purpose": ("Recipes, food SUPPLY, and meal PLANNING — what the person can "
                    "make or plans to eat: recipes, pantry/inventory, meal plans, "
                    "leftovers, dietary profile, and preparation."),
        "entities": {
            "recipe": "A recipe the person owns (ingredients, steps, nutrition, cost).",
            "pantry_item": "An item currently in the person's pantry / food supply.",
            "meal_plan": "A PLANNED meal (intended, not necessarily eaten).",
            "leftover": "Leftovers currently available to eat.",
            "consumption": ("A record that the person ate servings of a prepared "
                            "RECIPE (recipe-attributed — distinct from a logged meal)."),
            "dietary_profile": "The person's dietary preferences/restrictions for planning.",
        },
        "boundary": ("Supply / planning / recipes — NOT what was actually eaten. For "
                     "eaten foods and meals, calories, and consumption history, use "
                     "the 'nutrition' domain."),
        "cues": ["what can I cook", "what's in my pantry", "my meal plan",
                 "recipe for", "do I have leftovers", "what should I make"],
    },

    # ── Health & body ────────────────────────────────────────────────────────
    "health": {
        "purpose": ("Body vitals and fitness measured over time: weight, sleep, "
                    "steps, glucose, blood pressure, body measurements, and workouts."),
        "entities": {
            "workout": "A completed workout with its exercises, sets, reps, and weights.",
            "sleep": "A night's sleep record.",
            "body_measurement": "A body measurement (body fat, waist, etc.).",
            "steps": "A day's step record.",
            "glucose": "A glucose reading.",
            "blood_pressure": "A blood-pressure reading.",
            "weight": "A weight reading.",
        },
        "cues": ["how's my weight", "did I work out", "my blood pressure",
                 "how did I sleep", "steps today"],
    },
    "medicine": {
        "purpose": ("Medications, supplements, OTC and wellness products the person "
                    "takes, and adherence to them."),
        "entities": {
            "medication": "A prescribed medication and its schedule/adherence.",
            "supplement": "A supplement the person takes.",
            "otc": "An over-the-counter product the person takes.",
            "wellness": "A wellness product the person takes.",
        },
        "cues": ["my medications", "did I take my meds", "am I on"],
    },
    "medical": {
        "purpose": "Lab results, lab panels, and uploaded medical documents.",
        "entities": {
            "lab_result": "A single lab value/result.",
            "lab_panel": "A panel of related lab results.",
            "document": "An uploaded medical document.",
        },
        "cues": ["my lab results", "my cholesterol", "my last blood work"],
    },

    # ── Purpose / execution ──────────────────────────────────────────────────
    "goals": {
        "purpose": "The person's life goals, milestones, and annual directions, with progress.",
        "entities": {
            "goal": "A life goal the person is pursuing.",
            "milestone": "A milestone within a goal.",
            "annual_direction": "A yearly direction/theme.",
        },
        "cues": ["my goals", "am I on track", "goal progress"],
    },
    "habits": {
        "purpose": "The person's habits and how consistently they keep them.",
        "entities": {"habit": "A habit the person is building, with its consistency."},
        "cues": ["my habits", "my streak", "how consistent have I been"],
    },
    "tasks": {
        "purpose": "The person's to-dos and their completion.",
        "entities": {"task": "A task/to-do, with due date and completion state."},
        "cues": ["my tasks", "what's due", "what did I finish"],
    },
    "projects": {
        "purpose": "The person's projects and their status.",
        "entities": {"project": "A project the person is working on."},
        "cues": ["my projects"],
    },

    # ── Time: calendar vs significant events ─────────────────────────────────
    "calendar": {
        "purpose": "SCHEDULED time — the person's calendar events and appointments.",
        "entities": {"event": "A scheduled calendar event/appointment at a time."},
        "boundary": ("Scheduled time on the calendar. For significant life events "
                     "(birthdays, anniversaries, milestones), use the 'events' domain."),
        "cues": ["what's on my calendar", "my schedule", "meetings today",
                 "what do I have last Tuesday"],
    },
    "events": {
        "purpose": ("Significant LIFE events — birthdays, anniversaries, and personal "
                    "milestones (not calendar appointments)."),
        "entities": {"event": "A significant life event (birthday, anniversary, milestone)."},
        "boundary": ("Life milestones, not scheduled appointments. For the daily "
                     "schedule, use the 'calendar' domain."),
        "cues": ["upcoming birthdays", "anniversaries", "important dates"],
    },

    # ── Writing / spiritual ──────────────────────────────────────────────────
    "journal": {
        "purpose": "The person's written journal entries and mood over time.",
        "entities": {"entry": "A journal entry (its text and mood)."},
        "cues": ["my journal", "what did I write", "my mood lately"],
    },
    "faith": {
        "purpose": ("The person's prayers, Scripture reading plans and progress, saved "
                    "verses, faith milestones, and Bible study notes/highlights/bookmarks."),
        "entities": {
            "prayer": "A prayer the person recorded.",
            "reading_plan": "A Bible reading plan and its progress.",
            "milestone": ("A significant moment in the person's faith journey — salvation, "
                          "baptism, rededication, an answered prayer, or a spiritual insight."),
            "saved_verse": ("A Scripture verse the person saved to their collection "
                            "(flagged as a memory verse when they are memorizing it)."),
            "study_note": "A Bible study note the person wrote on a specific passage.",
            "highlight": "A Bible passage the person highlighted while reading.",
            "bookmark": "A place in the Bible the person bookmarked to return to.",
        },
        "cues": ["my prayers", "my reading plan", "my Bible reading", "my memory verses",
                 "my faith milestones", "my baptism", "my study notes"],
    },

    # ── People: relationships vs legacy ──────────────────────────────────────
    "relationships": {
        "purpose": "People in the person's life and their interactions with them.",
        "entities": {"person": "A person the user knows, with interaction history."},
        "boundary": ("Living relationships and interactions. For preserved family "
                     "history / ancestry, use the 'legacy' domain."),
        "cues": ["who did I talk to", "my relationships", "people I contact most"],
    },
    "legacy": {
        "purpose": "Preserved memories, people, and places — the person's life story / legacy.",
        "entities": {
            "memory": "A preserved memory / story.",
            "person": "A person in the family/legacy record (may be ancestral).",
            "place": "A meaningful place in the person's legacy.",
        },
        "boundary": ("Preserved life story / family history. For current living "
                     "contacts and interactions, use the 'relationships' domain."),
        "cues": ["my family history", "memories of", "my ancestry"],
    },

    # ── Capture / notes / brain training / finance ───────────────────────────
    "capture": {
        "purpose": "Items the person quickly captured/saved (photos, uploads) for later.",
        "entities": {"capture": "A captured item awaiting triage/use."},
        "cues": ["what did I capture", "my saved items"],
    },
    "artifacts": {
        "purpose": ("Files the person has UPLOADED — documents (PDFs), images/photos, "
                    "audio recordings/voice notes, and video — kept as durable, "
                    "retrievable truth with the deterministically extracted text/"
                    "transcript. Use to FIND or READ something the user uploaded (a "
                    "receipt, an MRI/lab report, an insurance card, bloodwork, a "
                    "policy, a recording), INCLUDING from a past turn: pass `name` "
                    "with words the file is about (e.g. 'MRI', 'receipt') to search "
                    "its content/filename, or `entity_type` to list one class."),
        "entities": {
            "artifact": "Any uploaded file (document/image/audio/video) with its extracted content.",
            "document": "An uploaded document (PDF, …) with its extracted page text.",
            "image": "An uploaded image / photo.",
            "audio": "An uploaded audio recording / voice note, with its transcript.",
            "video": "An uploaded video.",
        },
        "boundary": ("The user's own UPLOADED files as retrievable truth + their "
                     "extracted content. For a domain's canonical record (a logged "
                     "lab RESULT, a medication), use that domain; use 'artifacts' to "
                     "retrieve the uploaded FILE itself and what it says."),
        "cues": ["show me the receipt I uploaded", "what did my MRI say",
                 "find my insurance card", "the PDF I uploaded",
                 "the recording from tuesday", "when did I last upload bloodwork",
                 "documents I uploaded about", "read the file I sent",
                 "summarize the document I uploaded"],
    },
    "notes": {
        "purpose": "The person's saved notes.",
        "entities": {"note": "A saved note."},
        "cues": ["my notes"],
    },
    "brain_training": {
        "purpose": "Brain-training game sessions and scores over time.",
        "entities": {"game_session": "A completed brain-training game session and score."},
        "cues": ["my brain training", "my game scores"],
    },
    "finance": {
        "purpose": "The person's finances (accounts, transactions, budgets).",
        "entities": {},
    },
}


def domain_semantics(domain=None):
    """Return semantics for one domain (or the whole registry). Read-only, no I/O."""
    if domain is not None:
        return DOMAIN_SEMANTICS.get(domain, {})
    return {k: dict(v) for k, v in DOMAIN_SEMANTICS.items()}
