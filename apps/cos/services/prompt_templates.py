"""
CoS v2 Prompt Templates — Activity-type-specific prompt text.

Each activity type has pre-event and post-event templates.
Templates are plain strings with {placeholders} for personalization.

Placeholder variables:
- {title}: event/activity title
- {time}: formatted time string
- {duration}: duration in minutes
- {activity_type}: human-readable activity type
"""

# ──────────────────────────────────────────────────────────
# Pre-event templates
# ──────────────────────────────────────────────────────────

PRE_EVENT_TEMPLATES = {
    "meeting": (
        "Your meeting \"{title}\" starts in {lead_minutes} minutes. "
        "Any prep or goals you want to keep in mind?"
    ),
    "workout": (
        "Your workout \"{title}\" starts in {lead_minutes} minutes. "
        "Ready to go?"
    ),
    "bible_study": (
        "Your Bible study \"{title}\" starts in {lead_minutes} minutes. "
        "Take a moment to prepare your heart."
    ),
    "prayer": (
        "Your prayer time \"{title}\" starts in {lead_minutes} minutes."
    ),
    "devotional": (
        "Your devotional \"{title}\" starts in {lead_minutes} minutes."
    ),
    "journaling": (
        "Your journaling time \"{title}\" starts in {lead_minutes} minutes. "
        "What's on your mind today?"
    ),
    "meditation": (
        "Your meditation \"{title}\" starts in {lead_minutes} minutes. "
        "Find a quiet space and settle in."
    ),
    "fasting": (
        "Your fasting period \"{title}\" starts in {lead_minutes} minutes."
    ),
    "appointment": (
        "Your appointment \"{title}\" starts in {lead_minutes} minutes. "
        "Don't forget to prepare anything you need."
    ),
    "task": (
        "Your scheduled task \"{title}\" starts in {lead_minutes} minutes."
    ),
    "default": (
        "Your activity \"{title}\" starts in {lead_minutes} minutes."
    ),
}

# ──────────────────────────────────────────────────────────
# Post-event templates
# ──────────────────────────────────────────────────────────

POST_EVENT_TEMPLATES = {
    "meeting": (
        "Your meeting \"{title}\" just ended. "
        "Did it go well? Any follow-ups?"
    ),
    "workout": (
        "Did you complete your workout \"{title}\"? "
        "How did it go?"
    ),
    "bible_study": (
        "How was your Bible study \"{title}\"? "
        "Anything stand out to you?"
    ),
    "prayer": (
        "How was your prayer time \"{title}\"?"
    ),
    "devotional": (
        "How was your devotional \"{title}\"? "
        "Any reflections?"
    ),
    "journaling": (
        "How was your journaling session \"{title}\"?"
    ),
    "meditation": (
        "How was your meditation \"{title}\"? "
        "Feel centered?"
    ),
    "fasting": (
        "How is your fasting \"{title}\" going? "
        "Any reflections?"
    ),
    "appointment": (
        "Your appointment \"{title}\" should be done. "
        "How did it go? Any follow-ups?"
    ),
    "task": (
        "Did you complete \"{title}\"?"
    ),
    "default": (
        "Your activity \"{title}\" should be done. "
        "How did it go?"
    ),
}

# ──────────────────────────────────────────────────────────
# Default lead/delay times per activity type (in minutes)
# ──────────────────────────────────────────────────────────

DEFAULT_LEAD_MINUTES = {
    "meeting": 10,
    "workout": 15,
    "bible_study": 10,
    "prayer": 5,
    "devotional": 5,
    "journaling": 5,
    "meditation": 5,
    "fasting": 10,
    "appointment": 15,
    "task": 10,
    "default": 15,
}

DEFAULT_POST_DELAY_MINUTES = {
    "meeting": 5,
    "workout": 10,
    "bible_study": 5,
    "prayer": 5,
    "devotional": 5,
    "journaling": 5,
    "meditation": 5,
    "fasting": 5,
    "appointment": 10,
    "task": 5,
    "default": 5,
}

# ──────────────────────────────────────────────────────────
# Activity type detection from event titles
# ──────────────────────────────────────────────────────────

ACTIVITY_TYPE_PATTERNS = {
    "workout": [
        "workout", "exercise", "gym", "training", "run", "jog",
        "swim", "yoga", "pilates", "hiit", "crossfit", "lift",
    ],
    "bible_study": [
        "bible study", "bible reading", "scripture",
    ],
    "prayer": [
        "prayer", "prayer time", "quiet time",
    ],
    "devotional": [
        "devotional", "devo",
    ],
    "journaling": [
        "journaling", "journal", "reflection",
    ],
    "meeting": [
        "meeting", "standup", "sync", "1:1", "one-on-one",
        "call", "conference", "interview",
    ],
    "meditation": [
        "meditation", "meditate", "mindfulness", "breathwork",
        "breathing exercise", "centering",
    ],
    "fasting": [
        "fasting", "fast day", "intermittent fast",
    ],
    "appointment": [
        "appointment", "doctor", "dentist", "therapy",
        "medical", "checkup", "check-up",
    ],
}


def detect_activity_type(title: str) -> str:
    """Detect activity type from event title. Returns 'default' if no match."""
    title_lower = title.strip().lower()
    for activity_type, patterns in ACTIVITY_TYPE_PATTERNS.items():
        for pattern in patterns:
            if pattern in title_lower:
                return activity_type
    return "default"


def get_pre_event_template(activity_type: str) -> str:
    """Get pre-event prompt template for activity type."""
    return PRE_EVENT_TEMPLATES.get(
        activity_type, PRE_EVENT_TEMPLATES["default"]
    )


def get_post_event_template(activity_type: str) -> str:
    """Get post-event prompt template for activity type."""
    return POST_EVENT_TEMPLATES.get(
        activity_type, POST_EVENT_TEMPLATES["default"]
    )


def get_lead_minutes(activity_type: str) -> int:
    """Get default lead time in minutes for pre-event prompts."""
    return DEFAULT_LEAD_MINUTES.get(
        activity_type, DEFAULT_LEAD_MINUTES["default"]
    )


def get_post_delay_minutes(activity_type: str) -> int:
    """Get default delay in minutes for post-event prompts."""
    return DEFAULT_POST_DELAY_MINUTES.get(
        activity_type, DEFAULT_POST_DELAY_MINUTES["default"]
    )


def render_template(template: str, **kwargs) -> str:
    """Render a prompt template with variables. Missing vars left as-is."""
    try:
        return template.format(**kwargs)
    except KeyError:
        # Graceful fallback for missing variables
        result = template
        for key, value in kwargs.items():
            result = result.replace("{" + key + "}", str(value))
        return result
