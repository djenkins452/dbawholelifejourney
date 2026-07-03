"""
Story Cleanup (Legacy Discovery pipeline, Phase 1).

A careful copy-editor that runs BEFORE Story Discovery. It fixes the mechanics
of writing — spelling, punctuation, grammar, paragraph breaks, duplicated words,
obvious transcription slips — and NOTHING ELSE. It never rewrites voice, humor,
tone, dialect, or meaning, and never adds or removes information. Think Grammarly,
not ChatGPT. The user must still recognize their own words.

Entirely inside the Legacy domain: one direct OpenAI call, no CoS / Beth /
personal_assistant coupling. Fails safe — if unavailable or anything goes wrong,
it returns the original text unchanged so Discovery still proceeds.
"""

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a meticulous, invisible copy-editor preserving a person's \
life story. You fix ONLY the mechanics of writing. You must never change the \
author's voice — a reader who knows them should not be able to tell an editor touched it.

ALLOWED (fix silently):
- Spelling mistakes and obvious typos
- Punctuation and capitalization errors (but KEEP intentional capitalization of names/places)
- Grammar mistakes
- Duplicated words ("the the", "and and")
- Obvious voice-transcription errors (clear homophones, run-together words)
- Breaking a very long run-on paragraph into natural paragraphs at real sentence boundaries

FORBIDDEN (never do):
- Rewriting sentences to "sound better"
- Changing word choice, phrasing, humor, tone, or emotion
- Altering dialect, regional speech, or the author's natural rhythm
- Adding, removing, or inferring any information
- Changing the meaning of any sentence
- "Improving" the storytelling

If the text is already clean, return it unchanged with an empty changes list.

Return ONLY JSON:
{
  "cleaned": "the full corrected text, same voice, same meaning",
  "changes": ["short human labels of the KINDS of fixes made, e.g. 'Spelling corrected', 'Paragraphs separated', 'Punctuation tidied'"]
}
Keep the changes list to the distinct KINDS of fixes (max 5), not a list of every edit."""


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
        logger.warning("Legacy cleanup: OpenAI client init failed", exc_info=True)
        return None


def _edit(text):
    """Call the model. Returns (cleaned_text, changes_list) or None on failure."""
    client = _client()
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=getattr(settings, "OPENAI_MODEL", "gpt-4o"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        logger.warning("Legacy cleanup call failed", exc_info=True)
        return None
    cleaned = (data.get("cleaned") or "").strip()
    changes = [str(c).strip() for c in (data.get("changes") or []) if str(c).strip()][:5]
    if not cleaned:
        return None
    return cleaned, changes


def run_cleanup(text, editor=None):
    """Gently copy-edit `text`. Returns a dict:
        {"changed": bool, "cleaned": str, "original": str, "changes": [labels]}
    Always safe: on any failure or when nothing needs fixing, `changed` is False
    and `cleaned` == the original text, so Discovery proceeds on real content."""
    original = text or ""
    if not original.strip() or len(original.strip()) < 15:
        return {"changed": False, "cleaned": original, "original": original, "changes": []}

    result = (editor or _edit)(original)
    if not result:
        return {"changed": False, "cleaned": original, "original": original, "changes": []}

    cleaned, changes = result
    # Guardrail against a model that "improves" too much: cleanup should never
    # dramatically change length. If it did, distrust it and keep the original.
    if abs(len(cleaned) - len(original)) > max(60, int(len(original) * 0.4)):
        logger.info("Legacy cleanup rejected: length drift too large (%d -> %d)",
                    len(original), len(cleaned))
        return {"changed": False, "cleaned": original, "original": original, "changes": []}

    changed = cleaned != original
    return {
        "changed": changed,
        "cleaned": cleaned,
        "original": original,
        "changes": changes if changed else [],
    }
