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

Clarifications are first-class, fully CRUD-able entities — never write-only. Beyond
answering (which writes Canonical Truth), a question can be DISMISSED (removed from the
queue) singly, in bulk, or all at once, and that dismissal is reversible (undo). A
dismissal deletes NOTHING in Canonical Truth — it only clears the outstanding question,
suppressed by a stable `cid` (see `dismiss` / `restore` / `pending`).

A clarification item (the evidence contract every type returns):
    {
      "kind":        "<type key>",          # which handler resolves it
      "ref":         "<opaque id>",          # passed back to resolve()
      "cid":         "<stable id>",          # '<kind>:<scope…>:<ref>' — CRUD/dismiss handle
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
    """Every open clarification for a committed import batch, across all types —
    excluding questions the keeper has DISMISSED (removed from the queue)."""
    from apps.legacy.models import ClarificationDismissal
    dismissed = set(ClarificationDismissal.objects.filter(user=batch.user)
                    .values_list("cid", flat=True))
    out = []
    for handler in _REGISTRY:
        for item in handler.detect(batch):
            if item.get("cid") not in dismissed:
                out.append(item)
    return out


def pending_cids(batch):
    """The stable ids of every question currently in the queue (for 'delete all')."""
    return [item["cid"] for item in pending(batch) if item.get("cid")]


def dismiss(user, cids):
    """Remove clarification questions from the queue by `cid`. This is a first-class
    delete of the QUESTION only — it never touches a Person, Relationship, Story,
    Media, or any Canonical Truth. Returns the cids newly dismissed (so the caller can
    offer Undo). Re-dismissing an already-dismissed question is a no-op."""
    from apps.legacy.models import ClarificationDismissal
    done = []
    for cid in cids or []:
        cid = (cid or "").strip()
        if not cid:
            continue
        _obj, created = ClarificationDismissal.objects.get_or_create(user=user, cid=cid)
        if created:
            done.append(cid)
    return done


def restore(user, cids):
    """Undo a dismissal — the question re-derives from the same evidence and reappears.
    Canonical Truth is untouched either way. Returns the cids restored."""
    from apps.legacy.models import ClarificationDismissal
    cids = [(c or "").strip() for c in (cids or []) if (c or "").strip()]
    if not cids:
        return []
    ClarificationDismissal.objects.filter(user=user, cid__in=cids).delete()
    return cids


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
            ref = str(ch.index)
            yield {
                "kind": self.kind,
                "ref": ref,
                # Chunk index is unique only WITHIN a batch → scope the cid by batch.
                "cid": "%s:%d:%s" % (self.kind, batch.id, ref),
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

    def detect(self, batch):
        from apps.legacy.models import Person
        from apps.legacy.services.import_engine import analyze_step_candidates

        user = batch.user
        # Only the AMBIGUOUS candidates come here — the overwhelming-evidence ones were
        # already concluded automatically (single spouse, child a minor at the marriage).
        _infer, clarify = analyze_step_candidates(user)
        if not clarify:
            return
        ids = set()
        for c in clarify:
            ids.add(c["spouse_id"]); ids.add(c["parent_id"]); ids |= c["child_ids"]
        names = dict(Person.all_objects.filter(user=user, pk__in=ids)
                     .values_list("pk", "display_name"))
        for c in clarify:
            spouse_id, parent_id = c["spouse_id"], c["parent_id"]
            kid_names = ", ".join(names.get(k, "?") for k in sorted(c["child_ids"]))
            ref = "%d:%d" % (spouse_id, parent_id)
            yield {
                "kind": self.kind,
                "ref": ref,
                # Step candidates are user-global (a person pair), not batch-scoped.
                "cid": "%s:%s" % (self.kind, ref),
                "title": "Help Legacy understand this relationship",
                "prompt": "How is %s related to %s's %s?" % (
                    names.get(spouse_id, "this person"), names.get(parent_id, "the parent"),
                    "child" if len(c["child_ids"]) == 1 else "children"),
                "reason": "%s married %s, but Legacy can't tell from the file whether %s "
                          "was a step-parent to %s" % (
                              names.get(spouse_id, "This person"), names.get(parent_id, "the parent"),
                              names.get(spouse_id, "they"), kid_names),
                "evidence": [
                    {"label": "Married", "value": "%s & %s" % (
                        names.get(spouse_id, "?"), names.get(parent_id, "?"))},
                    {"label": "Parent", "value": names.get(parent_id, "?"),
                     "href": "/legacy/people/%d/" % parent_id},
                    {"label": "Their child" if len(c["child_ids"]) == 1 else "Their children",
                     "value": kid_names},
                    {"label": "Recorded as a parent?", "value": "No — no parent link in the file"},
                    {"label": "Why Legacy is asking",
                     "value": "another possible step-parent, or the timing is unclear"},
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
