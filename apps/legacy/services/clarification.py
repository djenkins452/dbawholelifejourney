"""Legacy Clarification Engine — the platform capability for resolving ambiguity.

Responsibilities stay separate and never bleed together:
  • the Importer PRESERVES evidence,
  • Discovery EXTRACTS meaning,
  • the Clarification Engine RESOLVES ambiguity,
  • Canonical Truth stores only CONFIRMED facts.

The engine never guesses and never leads. It presents the EVIDENCE that caused the
ambiguity and asks the user to teach Legacy — "Help Legacy understand" — with neutral
options. Once the user answers, the fact becomes Known and the same question is never
asked again.

This is NOT a marriage system. It is a general ambiguity-resolution engine: each
ambiguity type registers a handler and reuses the same evidence contract, UI, and
resolve dispatch. Marriage status is simply the FIRST registered type; future types
(who is 'Dad', story vs fact, duplicate people, same place, relationship type, …)
plug in the same way.

A clarification item (the evidence contract every type returns):
    {
      "kind":        "<type key>",          # which handler resolves it
      "ref":         "<opaque id>",          # passed back to resolve()
      "title":       "Help Legacy understand …",
      "prompt":      "<neutral question — never leading>",
      "reason":      "<one line: why Legacy is asking>",
      "evidence":    [ {"label", "value", "href"?}, … ],   # the preserved facts
      "options":     [ {"value", "label"}, … ],            # neutral choices
      "allow_other": bool,                    # free-text "Other" permitted
      "other_label": "Other …",
    }
"""


_REGISTRY = []


def register(handler):
    _REGISTRY.append(handler)


def pending(batch):
    """Every open clarification for a committed import batch, across all types."""
    out = []
    for handler in _REGISTRY:
        out.extend(handler.detect(batch))
    return out


def resolve(batch, kind, ref, answer, detail=""):
    """Dispatch the user's answer to the handler for `kind`. Returns True if it was
    resolved (the answer is written into Canonical Truth; the question won't recur)."""
    for handler in _REGISTRY:
        if handler.kind == kind:
            return handler.resolve(batch, ref, answer, detail)
    return False


# ── Marriage status — the first clarification type ─────────────────────────────
class MarriageClarification:
    """A GEDCOM family unit with no marriage event: Legacy cannot tell how the couple
    were related, so it preserves the evidence and asks. It never infers a marriage."""

    kind = "marriage_status"

    # Neutral answer → the relationship Legacy records. 'never' records NO couple
    # relationship (co-parents only); 'other' uses the user's own words.
    _ANSWER_TO_TYPE = {
        "married": "married to",
        "former": "former spouse of",
        "partner": "domestic partner of",
        "never": None,
    }

    def detect(self, batch):
        from django.db.models import Q
        from apps.legacy.models import Relationship
        from apps.legacy.services.import_engine import _couple_bond, _family_persons

        user = batch.user
        for ch in batch.chunks.filter(chunk_kind="gedcom_family").order_by("index"):
            d = ch.data or {}
            if d.get("marriage_clarified"):                  # already taught
                continue
            _ctype, status = _couple_bond(d)
            if status != "needs_clarification":
                continue
            hp, wp = _family_persons(batch, d)
            if not hp or not wp or hp.pk == wp.pk:
                continue
            if Relationship.objects.filter(
                    user=user, relationship_type__icontains="married").filter(
                    Q(from_person=hp, to_person=wp) | Q(from_person=wp, to_person=hp)).exists():
                continue
            n = len(d.get("children") or [])
            yield {
                "kind": self.kind,
                "ref": str(ch.index),
                "title": "Help Legacy understand this relationship",
                "prompt": "How should Legacy represent this relationship?",
                "reason": "They share %d %s, but the file records no marriage event"
                          % (n, "child" if n == 1 else "children"),
                "evidence": [
                    {"label": "Person", "value": hp.display_name,
                     "href": "/legacy/people/%d/" % hp.pk},
                    {"label": "Person", "value": wp.display_name,
                     "href": "/legacy/people/%d/" % wp.pk},
                    {"label": "Shared children", "value": str(n)},
                    {"label": "Marriage record", "value": "None in the imported file"},
                    {"label": "Source", "value": batch.source_name},
                    {"label": "Original record", "value": "GEDCOM family (FAM)"},
                ],
                "options": [
                    {"value": "married", "label": "Married"},
                    {"value": "former", "label": "Formerly married"},
                    {"value": "never", "label": "Never married"},
                    {"value": "partner", "label": "Domestic partner"},
                ],
                "allow_other": True,
                "other_label": "Other relationship",
            }

    def resolve(self, batch, ref, answer, detail):
        from apps.legacy.models import Relationship
        from apps.legacy.services.import_engine import _family_persons

        try:
            index = int(ref)
        except (TypeError, ValueError):
            return False
        ch = batch.chunks.filter(chunk_kind="gedcom_family", index=index).first()
        if not ch:
            return False

        detail = (detail or "").strip()[:60]
        if answer == "other":
            rtype = detail or None
            recorded = "other:%s" % detail if detail else "other"
        elif answer in self._ANSWER_TO_TYPE:
            rtype = self._ANSWER_TO_TYPE[answer]
            recorded = answer
        else:
            return False                                     # unrecognised answer — ask again

        if rtype:
            hp, wp = _family_persons(batch, ch.data or {})
            if hp and wp and hp.pk != wp.pk:
                Relationship.objects.get_or_create(
                    user=batch.user, from_person=hp, to_person=wp, relationship_type=rtype)
        d = ch.data or {}
        d["marriage_clarified"] = recorded                   # taught → never asked again
        ch.data = d
        ch.save(update_fields=["data"])
        return True


register(MarriageClarification())
