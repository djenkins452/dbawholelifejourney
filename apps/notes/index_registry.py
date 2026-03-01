"""
Rename trigger registry for Notes search index.

Defines which attachable models trigger note reindexing when their
display fields change. Used by signals.py to dynamically register
pre_save/post_save handlers for rename detection.

Adding a new attachable model to the Notes system only requires
adding an entry here — no signal code changes needed.
"""

# Map of "app_label.ModelName" -> config dict.
# display_fields: list of field names that, when changed, trigger a reindex
# of any notes attached to the entity.
NOTE_INDEX_REGISTRY = {
    "life.Task": {
        "display_fields": ["title"],
    },
    "life.Project": {
        "display_fields": ["title"],
    },
    "purpose.LifeGoal": {
        "display_fields": ["title"],
    },
    "purpose.HabitGoal": {
        "display_fields": ["name"],
    },
    "journal.JournalEntry": {
        "display_fields": ["title"],
    },
}
