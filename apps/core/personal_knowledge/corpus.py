# ==============================================================================
# File: apps/core/personal_knowledge/corpus.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic characterization of a Personal Knowledge corpus
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-20
# ==============================================================================
"""Read-only, deterministic shape-analysis of a user's Personal Knowledge.

**Why this exists.** M3's review experience was safe but assumed a small corpus. A mature
user turned out to have 200+ unreviewed legacy facts, turning review into hundreds of
clerical decisions. To make review practical we first have to know what is actually in
there — how much is duplication, how much is one-line fact, how much is long synthesized
prose that must NOT be silently promoted to trusted knowledge.

**It classifies by STRUCTURE, never by meaning.** Length, sentence count, list-shape and
literal text overlap are things a computer can know. Whether a sentence is "interpretive"
is a judgement, so the labels here say what a record *looks like* (`long_prose`,
`compound`) and leave the reading to the human. Nothing here calls a provider, and nothing
here mutates a fact.
"""

import re
from collections import Counter, defaultdict

from .models import FactStatus, PersonalKnowledgeFact, ReviewState
from .service import _normalize_for_identity

# Structural thresholds. Deliberately generous — a record only needs to be *flagged for
# human eyes*, and over-flagging is safer than quietly waving something through.
SHORT_MAX_CHARS = 18          # below this a record is unlikely to carry a durable fact
LONG_PROSE_MIN_CHARS = 180    # long enough that it is almost certainly a summary
COMPOUND_MIN_SENTENCES = 2
COMPOUND_MIN_LIST_ITEMS = 4   # "a, b, c, and d" — a bundled claim, not one fact
NEAR_DUP_MIN_OVERLAP = 0.80   # literal token overlap; NEVER used to auto-merge

_SENTENCE_SPLIT = re.compile(r"[.!?]+(?:\s|$)")
_STOPWORDS = {
    "the", "a", "an", "is", "was", "are", "were", "be", "been", "am", "i", "my", "me",
    "and", "or", "but", "to", "of", "in", "for", "on", "with", "that", "this", "it",
    "as", "at", "by", "from", "we", "our", "us", "you", "your",
}


def _tokens(text):
    return {t for t in re.findall(r"[a-z0-9']+", (text or "").lower())
            if t not in _STOPWORDS and len(t) > 2}


def _sentence_count(text):
    return len([p for p in _SENTENCE_SPLIT.split(text or "") if p.strip()])


def _list_item_count(text):
    """Commas + trailing 'and'/'or' — the shape of a bundled, multi-claim statement."""
    return (text or "").count(",") + len(re.findall(r"\b(?:and|or)\b", (text or "").lower()))


def classify_shape(statement):
    """What does this record LOOK like? Structure only — never a claim about meaning.

    Returns one of:
      ``noise``       — too short to carry a durable fact
      ``long_prose``  — long enough to be a synthesized summary; needs human eyes
      ``compound``    — several sentences or a bundled list of claims
      ``atomic``      — a single short statement, the shape review is cheap for
    """
    text = (statement or "").strip()
    if len(text) < SHORT_MAX_CHARS:
        return "noise"
    if len(text) >= LONG_PROSE_MIN_CHARS:
        return "long_prose"
    if (_sentence_count(text) >= COMPOUND_MIN_SENTENCES
            or _list_item_count(text) >= COMPOUND_MIN_LIST_ITEMS):
        return "compound"
    return "atomic"


def _near_duplicate_groups(records):
    """Group records whose statements literally overlap above the threshold.

    Deterministic set overlap on words — NOT semantic similarity. Two records land in the
    same group only when they share most of their actual words, and even then the caller
    must treat it as a *review-ordering hint*: statements that differ in meaning while
    sharing vocabulary ("I like running" / "I don't like running") would group here, which
    is exactly why this never merges anything by itself.
    """
    groups, used = [], set()
    for i, (pk_i, text_i) in enumerate(records):
        if pk_i in used:
            continue
        ti = _tokens(text_i)
        if not ti:
            continue
        group = [pk_i]
        for pk_j, text_j in records[i + 1:]:
            if pk_j in used:
                continue
            tj = _tokens(text_j)
            if not tj:
                continue
            overlap = len(ti & tj) / min(len(ti), len(tj))
            if overlap >= NEAR_DUP_MIN_OVERLAP:
                group.append(pk_j)
                used.add(pk_j)
        if len(group) > 1:
            used.add(pk_i)
            groups.append(group)
    return groups


def characterize(user, *, unreviewed_only=True):
    """Describe a user's PK corpus. READ-ONLY — never writes, never calls a provider.

    Returns counts and structural classifications ONLY. No statement text leaves this
    function, so it is safe to expose through an operator surface.
    """
    qs = PersonalKnowledgeFact.objects.filter(
        user=user, fact_status=FactStatus.ACTIVE)
    if unreviewed_only:
        qs = qs.filter(review_state=ReviewState.UNREVIEWED)

    by_topic, by_provenance, by_shape = Counter(), Counter(), Counter()
    by_sensitivity, by_legacy_source = Counter(), Counter()
    exact = defaultdict(list)
    records, lengths = [], []

    for fact in qs:
        text = fact.statement or ""
        by_topic[fact.topic] += 1
        by_provenance[fact.provenance] += 1
        by_sensitivity[fact.sensitivity] += 1
        by_legacy_source[(fact.attributes or {}).get("legacy_source") or "(none)"] += 1
        by_shape[classify_shape(text)] += 1
        exact[_normalize_for_identity(text)].append(fact.id)
        records.append((fact.id, text))
        lengths.append(len(text))

    exact_groups = [ids for ids in exact.values() if len(ids) > 1]
    exact_redundant = sum(len(ids) - 1 for ids in exact_groups)
    near_groups = _near_duplicate_groups(records)
    near_redundant = sum(len(g) - 1 for g in near_groups)

    total = len(records)
    return {
        "total": total,
        "by_topic": dict(by_topic.most_common()),
        "by_provenance": dict(by_provenance.most_common()),
        "by_sensitivity": dict(by_sensitivity.most_common()),
        # WHICH legacy store each record came from — the line-delimited blob and the
        # profile paragraphs carry no topic, which is why an all-"other" corpus happens.
        "by_legacy_source": dict(by_legacy_source.most_common()),
        "by_shape": dict(by_shape.most_common()),
        "exact_duplicate_groups": len(exact_groups),
        "exact_redundant_records": exact_redundant,
        "near_duplicate_groups": len(near_groups),
        "near_duplicate_group_sizes": sorted((len(g) for g in near_groups), reverse=True),
        "near_redundant_records": near_redundant,
        "length_chars": {
            "min": min(lengths) if lengths else 0,
            "max": max(lengths) if lengths else 0,
            "mean": round(sum(lengths) / total) if total else 0,
        },
        # How much of the pile is genuinely distinct, one-decision-each knowledge?
        "distinct_estimate": total - exact_redundant,
        "needs_human_eyes": by_shape.get("long_prose", 0) + by_shape.get("compound", 0),
        "cheap_to_review": by_shape.get("atomic", 0),
    }
