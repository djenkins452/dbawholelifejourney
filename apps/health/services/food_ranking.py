# ==============================================================================
# File: food_ranking.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The one relevance ordering for food discovery — deterministic, pure
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-06
# ==============================================================================
"""Which of these candidates best answers what the person typed?

Nothing answered that question before. `_search_local` returned the user's saved foods
ordered by `-updated_at` and the catalog ordered **alphabetically by name**, and the caller
concatenated the two and sliced. The "top result" was therefore an artifact of recency and
the alphabet — which is the entire reason `4 Egg Ham and Cheese Sandwich` led the results
for "ham and cheese sandwich": its name begins with a digit, and digits sort before letters.

This module is discovery ONLY. It orders approximate candidates so a person can pick.
It never decides what a written record is called — that stays at the write boundary
(`_exact_food_match`), where nothing but an exact identity may take over the user's words.

    SEARCH may return approximate candidates.
    WRITE identity may never silently substitute one.

Pure, deterministic, and free of any knowledge about particular foods, brands or
categories: it compares token sets and strings.
"""

import difflib
import re

# Function words carry no food identity. This is grammar, not a food list — nothing here
# names an ingredient, a brand or a category, and adding a food to it would be a bug.
_FUNCTION_WORDS = frozenset({
    "a", "an", "and", "the", "of", "with", "in", "on", "for", "plus", "or", "w",
})

# Tiers, best first. The gap between them is what stops a more specific product from
# winning on shared words alone.
TIER_EXACT = 0            # the same food, by name
TIER_SAME_CONCEPTS = 1    # every meaningful word, and no extra ones
TIER_SUPERSET = 2         # every meaningful word, plus extra concepts the user did not say
TIER_PARTIAL = 3          # some of the words
TIER_FUZZY = 4            # neither — held together only by string similarity

# Where a candidate came from, as a tie-break only. A person's own saved food wins a tie
# against a catalog row; it never wins across tiers, which is what let a saved product
# outrank the generic food someone actually asked for.
_SOURCE_ORDER = {"custom": 0, "local": 1, "fatsecret": 2, "openfoodfacts": 3, "ai": 4}

_FUZZY_FLOOR = 0.60       # below this, string similarity is not evidence of anything


def normalize(name):
    """Fold case, punctuation and spacing so the same food compares equal."""
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def _singular(word):
    """Fold a regular English plural so one banana matches "Bananas, raw".

    Added when the USDA catalog was seeded (2026-09-06) and immediately proved
    undiscoverable: USDA names generics in the plural with a comma qualifier, so
    "banana" shared NO token with "Bananas, raw" and a saved branded product outranked
    the actual fruit. This is morphology, not ranking — the tiers and their order are
    untouched; it only decides when two words are the same word.
    """
    if len(word) > 4 and word.endswith("es") and word[:-2].endswith(
            ("s", "x", "z", "ch", "sh")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokens(name):
    """Meaningful words, function words removed, regular plurals folded."""
    return {_singular(t) for t in normalize(name).split()
            if t and t not in _FUNCTION_WORDS}


def score(candidate_name, query, *, source=""):
    """(tier, extra_concepts, -overlap, source_rank, length) — lower sorts better.

    Every component is a plain fact about two strings: which tier the match falls in, how
    many concepts the candidate ADDS that the person did not ask for, how much of what
    they did ask for is present, where it came from, and how long the name is.
    """
    q_norm, c_norm = normalize(query), normalize(candidate_name)
    q_tokens, c_tokens = tokens(query), tokens(candidate_name)
    source_rank = _SOURCE_ORDER.get(source, 9)
    length = len(c_norm)

    if q_norm and q_norm == c_norm:
        return (TIER_EXACT, 0, 0, source_rank, length)

    if q_tokens and q_tokens <= c_tokens:
        extra = len(c_tokens - q_tokens)
        tier = TIER_SAME_CONCEPTS if extra == 0 else TIER_SUPERSET
        return (tier, extra, -len(q_tokens), source_rank, length)

    overlap = len(q_tokens & c_tokens)
    if overlap:
        return (TIER_PARTIAL, len(c_tokens - q_tokens), -overlap, source_rank, length)

    ratio = difflib.SequenceMatcher(None, q_norm, c_norm).ratio()
    if ratio >= _FUZZY_FLOOR:
        return (TIER_FUZZY, 0, -round(ratio * 100), source_rank, length)
    return (TIER_FUZZY + 1, 0, 0, source_rank, length)


def rank(results, query):
    """Order search results best-first. Stable, so equal candidates keep their order."""
    return sorted(
        results or [],
        key=lambda r: score(getattr(r, "name", ""), query,
                            source=getattr(r, "source", "")),
    )


def has_strong_match(results, query):
    """Is one of these candidates good enough that looking further would add nothing?

    Used to decide whether to consult an external source. Previously that decision was
    "do we have at least three rows?", so three irrelevant substring hits were enough to
    stop the search — quantity standing in for quality.
    """
    for result in results or []:
        if score(getattr(result, "name", ""), query,
                 source=getattr(result, "source", ""))[0] <= TIER_SAME_CONCEPTS:
            return True
    return False
