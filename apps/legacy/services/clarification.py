"""Legacy clarification engine.

Legacy PRESERVES EVIDENCE; it never infers truth. When an import leaves a gap that
only the user can resolve, the importer records the gap and THIS engine — not the
importer — turns it into a plain question and writes the user's answer into Canonical
Truth. The user resolves ambiguity; Legacy never guesses.

Today the only gap is marriage status: a family unit with several shared children but
no marriage event in the file. Legacy asks "were they married?"; it does not decide.
The internal *reason* (several shared children) is why we ask — it is never a
user-facing "likely married" state.
"""

from django.db.models import Q

from apps.legacy.services.import_engine import _couple_bond, _family_persons


def pending(batch):
    """Open clarification questions for a committed import batch. Each item:
    {kind, ref, husband, wife, reason, question}. Empty until people are committed."""
    from apps.legacy.models import Relationship

    user = batch.user
    out = []
    for ch in batch.chunks.filter(chunk_kind="gedcom_family").order_by("index"):
        d = ch.data or {}
        if d.get("marriage_clarified"):                      # already resolved by the user
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
        out.append({
            "kind": "marriage", "ref": ch.index, "husband": hp, "wife": wp,
            "children": n,
            "reason": "%d shared %s, but no marriage record in the file"
                      % (n, "child" if n == 1 else "children"),
            "question": "Were %s and %s married?" % (hp.display_name, wp.display_name),
        })
    return out


def resolve(batch, ref, answer):
    """Apply the user's answer to a marriage question. answer 'yes' records a real
    marriage (now KNOWN); 'no' records that they were co-parents only. Either way the
    decision is remembered so the question is never asked again. Returns True if a
    question was resolved."""
    from apps.legacy.models import Relationship

    ch = batch.chunks.filter(chunk_kind="gedcom_family", index=ref).first()
    if not ch:
        return False
    d = ch.data or {}
    if answer == "yes":
        hp, wp = _family_persons(batch, d)
        if hp and wp and hp.pk != wp.pk:
            Relationship.objects.get_or_create(
                user=batch.user, from_person=hp, to_person=wp,
                relationship_type="married to")
        d["marriage_clarified"] = "married"
    else:
        d["marriage_clarified"] = "not_married"
    ch.data = d
    ch.save(update_fields=["data"])
    return True
