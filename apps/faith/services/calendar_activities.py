"""
Faith → Calendar activity descriptor.

Faith may contain several reading systems at once — legacy UserReadingPlans
("Journey Through John", "Building a Godly Marriage", …) and the canonical
Journey ("Walking With God Through Scripture"). From the user's perspective
there is ONE activity: 📖 Bible Reading.

Faith owns that canonical name and the canonical experience it opens. The
Calendar collapses every faith reading contributor into this one activity and
never exposes the underlying system names — those live inside Faith.

See apps/health/services/calendar_activities.py for the descriptor contract.
"""

# The canonical reading experience — "the same experience the user should
# naturally use today" (Journey resolves to the user's current day, and gracefully
# handles not-yet-started). Owned by Faith, not the Calendar.
_READING_URL = "/faith/journey/today/"

READING_ACTIVITY = {
    "key": "bible_reading",   # every faith reading source collapses to one activity
    "label": "Bible Reading",
    "icon": "📖",
    "unit": "",               # one activity, never a count
    "url": _READING_URL,
    "point": True,            # a reading happens at a point in time — a compact entry
}
