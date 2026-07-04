"""
Import classification — the orchestrator's first act.

Before any Discovery extraction, the importer asks of every unit it segments from
a document: "What is this?" A story? A bare fact? A person? A place? A milestone?
A quote? A relationship alias like "Dad"? Classification decides ROUTING — only
narrative units become story Memories; facts and entities are held in their own
review queues and never silently become stories.

Self-contained inside the Legacy domain: one direct OpenAI JSON call, no CoS /
Beth. Fails safe — if the model is unavailable or errors, every unit defaults to
STORY, exactly reproducing the pre-classification behaviour, so imports never break.
"""

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Keep in sync with ImportChunk.Kind — the model is the source of truth, but the
# prompt enumerates the vocabulary so the model returns valid values.
_KINDS = [
    "story", "journal_entry", "letter", "fact", "person", "relationship_alias",
    "place", "milestone", "timeline_event", "quote", "artifact", "media_ref",
    "biography", "description", "gedcom_person", "gedcom_family", "unknown",
]

SYSTEM_PROMPT = """You triage a personal document being imported into a life-\
preservation app. The document is a mixture of many kinds of information. For EACH \
numbered unit, decide WHAT IT IS — do not summarize or rewrite it, only classify it.

Classify each unit as exactly one of:
- story: a narrative lived experience ("My dad took me fishing and we...").
- journal_entry: a dated diary-style personal entry.
- letter: a letter written to or by the author.
- fact: a concise factual statement, NOT a narrative ("I married Heather on June 7, 1997." / "My first dog was Sarge, a black lab."). Facts must NEVER be classified as stories.
- person: a description of who a specific named person is.
- relationship_alias: a unit whose subject is essentially a RELATIONAL TERM standing in for a person — "Dad", "Mom", "my coach", "Grandma" — where the real identity should be resolved.
- place: a description of a specific place.
- milestone: a major life event (marriage, birth of a child, graduation, a move, military service, a death).
- timeline_event: a dated event that anchors a timeline.
- quote: a saying, motto, or memorable line.
- artifact: an object of significance (a ring, a car, a recipe box).
- media_ref: a reference to a photo, video, or audio recording.
- biography: a longer factual account of a person's life.
- description: a general descriptive passage that is not clearly one of the above.
- unknown: you genuinely cannot tell.

Judge by what the text IS, not by its topic. A single document legitimately contains \
many different kinds. When a unit is a plain fact (a date, a name, a pet, a statistic), \
classify it as "fact", never "story". When you genuinely cannot tell what a unit is, \
return "unknown" with low confidence — NEVER default an uncertain unit to "story". \
Forcing uncertain content into stories pollutes the record.

Return ONLY JSON: {"classifications": [{"index": <int>, "kind": "<one kind>", "confidence": "high|medium|low"}]}"""


def is_available():
    return bool(getattr(settings, "OPENAI_API_KEY", None))


def _client():
    try:
        from openai import OpenAI
    except ImportError:
        return None
    key = getattr(settings, "OPENAI_API_KEY", None)
    if not key:
        return None
    try:
        return OpenAI(api_key=key)
    except Exception:  # pragma: no cover - defensive
        logger.warning("Import classifier: OpenAI client init failed", exc_info=True)
        return None


def _classify(units):
    """units: list of {index, title, body}. Returns {index: (kind, confidence)} or None."""
    client = _client()
    if client is None:
        return None
    model = getattr(settings, "OPENAI_MODEL", "gpt-4o")
    lines = []
    for u in units:
        snippet = (u.get("title") or "").strip()
        body = (u.get("body") or "").strip().replace("\n", " ")
        snippet = (snippet + " — " + body) if snippet else body
        lines.append("[%d] %s" % (u["index"], snippet[:600]))
    user_content = "\n\n".join(lines)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content[:12000]},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        logger.warning("Import classification call failed", exc_info=True)
        return None
    out = {}
    valid = set(_KINDS)
    for row in data.get("classifications", []) or []:
        try:
            idx = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        kind = str(row.get("kind") or "").strip().lower()
        if kind not in valid:
            kind = "unknown"
        conf = str(row.get("confidence") or "").strip().lower()
        if conf not in ("high", "medium", "low"):
            conf = ""
        out[idx] = (kind, conf)
    return out


def classify_chunks(units, classifier=None, batch_size=40):
    """Classify document units. `units` is a list of {index, title, body}. Returns
    {index: (kind, confidence)}. Always safe: on any failure every unit falls back
    to ('story', '') — the exact pre-classification behaviour. `classifier` is
    injectable for tests (defaults to the OpenAI call)."""
    units = list(units or [])
    default = {u["index"]: ("story", "") for u in units}
    if not units:
        return {}

    fn = classifier
    if fn is None:
        if not is_available():
            return default
        fn = _classify

    valid = set(_KINDS)

    narrative = {"story", "journal_entry", "letter"}

    def _clean(pair):
        kind, conf = (pair or ("story", ""))
        kind = str(kind or "").strip().lower()
        if kind not in valid:
            kind = "unknown"
        conf = str(conf or "").strip().lower()
        if conf not in ("high", "medium", "low"):
            conf = ""
        # Unknown is NOT story: never force an uncertain unit into the Story queue.
        # A low-confidence narrative goes to Needs Clarification instead.
        if kind in narrative and conf == "low":
            kind = "unknown"
        return (kind, conf)

    result = {}
    for i in range(0, len(units), batch_size):
        batch = units[i:i + batch_size]
        got = fn(batch)
        if not got:
            # A failed batch degrades to story for those units — never blocks import.
            result.update({u["index"]: ("story", "") for u in batch})
        else:
            for u in batch:
                result[u["index"]] = _clean(got.get(u["index"]))
    return result
