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


# ── Step-parent — ask, never infer ─────────────────────────────────────────────
class StepParentClarification:
    """A spouse/partner of someone's parent MIGHT be a step-parent — but marriage does
    NOT prove it (that made Danny have seven parents). Legacy never infers it. When the
    source doesn't explicitly mark a step relationship (pedigree _FREL/_MREL/PEDI, which
    the importer records directly), Legacy PRESENTS the evidence and asks. One question
    per (partner, parent); the answer applies to that parent's children."""

    kind = "step_parent"

    def _graph(self, user):
        from collections import defaultdict
        from apps.legacy.models import Relationship
        from apps.legacy.services.import_engine import _is_parentish

        parents_of, children_of, spouses = defaultdict(set), defaultdict(set), defaultdict(set)
        names, sex = {}, {}
        pairs = set()
        for r in Relationship.objects.filter(user=user).select_related(
                "from_person", "to_person"):
            t = (r.relationship_type or "").lower()
            names[r.from_person_id] = r.from_person.display_name
            names[r.to_person_id] = r.to_person.display_name
            sex[r.from_person_id] = r.from_person.sex
            sex[r.to_person_id] = r.to_person.sex
            pairs.add((r.from_person_id, r.to_person_id))
            if _is_parentish(t):
                children_of[r.from_person_id].add(r.to_person_id)
                parents_of[r.to_person_id].add(r.from_person_id)
            elif any(k in t for k in ("married", "spouse", "partner", "husband", "wife")):
                spouses[r.from_person_id].add(r.to_person_id)
                spouses[r.to_person_id].add(r.from_person_id)
        return parents_of, children_of, spouses, names, sex, pairs

    def detect(self, batch):
        from apps.legacy.models import ClarificationDecision

        user = batch.user
        parents_of, children_of, spouses, names, sex, pairs = self._graph(user)
        decided = set(ClarificationDecision.objects.filter(user=user, kind=self.kind)
                      .values_list("ref", flat=True))
        seen = set()
        for parent_id, kids in children_of.items():
            for spouse_id in spouses.get(parent_id, ()):
                if spouse_id == parent_id:
                    continue
                # children this partner is NOT already a parent of (no invented steps)
                targets = [c for c in kids
                           if spouse_id not in parents_of.get(c, ())
                           and (spouse_id, c) not in pairs]
                if not targets:
                    continue
                ref = "%d:%d" % (spouse_id, parent_id)
                if ref in decided or ref in seen:
                    continue
                seen.add(ref)
                kid_names = ", ".join(names.get(c, "?") for c in sorted(targets))
                yield {
                    "kind": self.kind,
                    "ref": ref,
                    "title": "Help Legacy understand this relationship",
                    "prompt": "How is %s related to %s's %s?" % (
                        names.get(spouse_id, "this person"), names.get(parent_id, "the parent"),
                        "child" if len(targets) == 1 else "children"),
                    "reason": "%s was a partner of %s, but the file does not record %s as a "
                              "parent of %s" % (
                                  names.get(spouse_id, "This person"), names.get(parent_id, "the parent"),
                                  names.get(spouse_id, "them"), kid_names),
                    "evidence": [
                        {"label": "Partner", "value": names.get(spouse_id, "?"),
                         "href": "/legacy/people/%d/" % spouse_id},
                        {"label": "Parent", "value": names.get(parent_id, "?"),
                         "href": "/legacy/people/%d/" % parent_id},
                        {"label": "Their child" if len(targets) == 1 else "Their children",
                         "value": kid_names},
                        {"label": "Recorded as a parent?", "value": "No — no parent link in the file"},
                        {"label": "Source", "value": batch.source_name},
                    ],
                    "options": [
                        {"value": "step", "label": "Step-parent"},
                        {"value": "not_step", "label": "Not a step-parent"},
                    ],
                    "allow_other": True,
                    "other_label": "Other relationship",
                }

    def resolve(self, batch, ref, answer, detail):
        from apps.legacy.models import ClarificationDecision, Person, Relationship
        from apps.legacy.services.import_engine import _is_parentish

        user = batch.user
        try:
            spouse_id, parent_id = (int(x) for x in ref.split(":"))
        except (TypeError, ValueError):
            return False
        if answer not in ("step", "not_step", "other"):
            return False

        ClarificationDecision.objects.update_or_create(
            user=user, kind=self.kind, ref=ref,
            defaults={"answer": answer, "detail": (detail or "")[:120]})

        if answer == "step" or (answer == "other" and detail):
            spouse = Person.all_objects.filter(user=user, pk=spouse_id).first()
            if not spouse:
                return True
            if answer == "step":
                s = (spouse.sex or "").upper()
                rtype = ("stepfather of" if s.startswith("M")
                         else "stepmother of" if s.startswith("F") else "step-parent of")
            else:
                rtype = detail.strip()[:60]
            # apply to the parent's children this partner isn't already a parent of
            parents_of = {}
            kids = set()
            for f, t, typ in Relationship.objects.filter(user=user).values_list(
                    "from_person_id", "to_person_id", "relationship_type"):
                if _is_parentish((typ or "").lower()):
                    parents_of.setdefault(t, set()).add(f)
                    if f == parent_id:
                        kids.add(t)
            for cid in kids:
                if spouse_id in parents_of.get(cid, ()) or cid == spouse_id:
                    continue
                Relationship.objects.get_or_create(
                    user=user, from_person_id=spouse_id, to_person_id=cid,
                    relationship_type=rtype, defaults={"user_edited": True})
        return True


register(MarriageClarification())
register(StepParentClarification())
