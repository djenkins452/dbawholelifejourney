"""
Place context helpers for the Discovery pipeline (intentionally tiny).

Place *identification* is done by the SAME OpenAI call Discovery already makes —
there is NO external lookup service, no OpenStreetMap/Nominatim/Google, and no
second network request. This module only supplies two pieces of local context:

- `home_location(user)` — the author's configured home (existing Preferences),
  handed to the Discovery prompt so it can resolve public places near home.
- `is_personal_place(name)` — a cheap heuristic kept as a SAFETY NET behind the
  model's own personal/public judgment, so obvious private places ("Grandma's
  house") are never treated as public even if the model slips.
"""

import re

# Relational possessors and generic private nouns signal a PERSONAL place.
# NB: possessive alone is not private ("Marie Callender's" is public) — the
# signal is a family/relational possessor or a generic private location.
_RELATIONAL = (
    r"grandma|grandmas|grandmother|grandpa|grandpas|grandfather|granny|nana|"
    r"papa|mama|mom|mommy|mother|dad|daddy|father|aunt|auntie|uncle|cousin|"
    r"our|my|nana's|the family"
)
_GENERIC_PRIVATE = (
    r"barn|treehouse|tree house|fishing hole|swimming hole|homestead|outhouse|"
    r"smokehouse|the shop|the field|the woods|the creek|the yard|the garden|"
    r"the cabin|our cabin|the cottage|the farmhouse|the porch|back porch|"
    r"the property|the homeplace|the home place|the lake house|the treehouse"
)


def is_personal_place(name):
    """True when a place name looks private/personal and should NOT be identified."""
    n = " " + (name or "").strip().lower() + " "
    if not n.strip():
        return False
    if re.search(r"\b(" + _RELATIONAL + r")\b", n):
        return True
    if re.search(r"\b(" + _GENERIC_PRIVATE + r")\b", n):
        return True
    if re.search(r"\bthe old \w+", n):     # "the old barn", "the old house"
        return True
    return False


def home_location(user):
    """The user's configured home (existing Preferences — no new settings).
    Returns {text, source} or None. Given to the Discovery prompt as context."""
    prefs = getattr(user, "preferences", None)
    city = (getattr(prefs, "location_city", "") or "").strip() if prefs else ""
    if not city:
        return None
    country = (getattr(prefs, "location_country", "") or "").strip() if prefs else ""
    text = city
    if country and country.lower() not in ("united states", "usa", "us", "u.s.") \
            and "," not in city:
        text = "%s, %s" % (city, country)
    return {"text": text, "source": "home"}
