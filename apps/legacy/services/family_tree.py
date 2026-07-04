"""
Family View — a visualization of Canonical Truth, not a genealogy database.

Builds a laid-out family graph from the People + Relationships Legacy already
holds (however they arrived — added by hand, discovered in a story, or committed
from a GEDCOM). Parent/child and spouse edges are read from the free-text
relationship types with keyword matching; generations are computed by longest
path from the roots. Pure read model — no writes, no Discovery, no CoS.

Coordinates are emitted so the client can position cards and draw edges; nothing
here decides styling.
"""

from collections import defaultdict

# Card geometry (kept in sync with .fam-node in legacy.css).
CARD_W, CARD_H = 176, 96
GAP_X, GAP_Y = 30, 92
ROW_STRIDE = CARD_H + GAP_Y
COL_STRIDE = CARD_W + GAP_X

_PARENT_OF = ("parent of", "father of", "mother of", "mom of", "dad of", "mum of")
_CHILD_OF = ("child of", "son of", "daughter of")
_SPOUSE = ("married", "spouse", "husband", "wife", "wed", "partner")


def _initials(name):
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:1].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


def _order_row(row, spouses):
    """Order a generation so spouses sit next to each other."""
    placed, seen = [], set()
    for p in row:
        if p.pk in seen:
            continue
        placed.append(p)
        seen.add(p.pk)
        for other in row:
            if other.pk not in seen and other.pk in spouses.get(p.pk, ()):
                placed.append(other)
                seen.add(other.pk)
    return placed


def build_family_graph(user):
    from apps.legacy.models import Person, Relationship

    people = list(Person.objects.filter(user=user).select_related("primary_photo"))
    if not people:
        return {"nodes": [], "edges": [], "width": 0, "height": 0, "count": 0}
    pids = {p.pk for p in people}

    parents, children, spouses = defaultdict(set), defaultdict(set), defaultdict(set)
    for r in Relationship.objects.filter(user=user):
        f, t = r.from_person_id, r.to_person_id
        if f not in pids or t not in pids:
            continue
        typ = (r.relationship_type or "").lower()
        if any(k in typ for k in _PARENT_OF):
            children[f].add(t); parents[t].add(f)
        elif any(k in typ for k in _CHILD_OF):
            children[t].add(f); parents[f].add(t)
        elif any(k in typ for k in _SPOUSE):
            spouses[f].add(t); spouses[t].add(f)

    # Generation = longest path from a root (someone with no known parent).
    gen = {}

    def _gen(pk, stack):
        if pk in gen:
            return gen[pk]
        if pk in stack:                 # defensive cycle guard
            return 0
        ps = [pp for pp in parents.get(pk, ()) if pp in pids]
        gen[pk] = (max(_gen(pp, stack | {pk}) for pp in ps) + 1) if ps else 0
        return gen[pk]

    for p in people:
        _gen(p.pk, set())

    by_gen = defaultdict(list)
    for p in people:
        by_gen[gen[p.pk]].append(p)

    # Lay out each generation as a centered row.
    rows = {g: _order_row(by_gen[g], spouses) for g in by_gen}
    max_cols = max(len(r) for r in rows.values())
    total_w = max_cols * COL_STRIDE - GAP_X
    pos = {}
    nodes = []
    for g in sorted(rows):
        row = rows[g]
        row_w = len(row) * COL_STRIDE - GAP_X
        x0 = (total_w - row_w) / 2
        y = g * ROW_STRIDE
        for i, p in enumerate(row):
            x = x0 + i * COL_STRIDE
            pos[p.pk] = (x, y)
            photo = (p.primary_photo.file.url
                     if (p.primary_photo and p.primary_photo.file) else "")
            nodes.append({
                "id": p.pk, "name": p.display_name, "initials": _initials(p.display_name),
                "photo": photo, "birth": p.birth_year, "death": p.death_year,
                "living": p.death_year is None,
                "rel": p.relationship_label, "x": round(x), "y": round(y),
            })

    edges = []
    for cpk, pset in parents.items():
        if cpk not in pos:
            continue
        cx, cy = pos[cpk]
        for ppk in pset:
            if ppk in pos:
                px, py = pos[ppk]
                edges.append({"type": "parent",
                              "x1": round(px + CARD_W / 2), "y1": round(py + CARD_H),
                              "x2": round(cx + CARD_W / 2), "y2": round(cy)})
    drawn = set()
    for a, sset in spouses.items():
        for b in sset:
            key = tuple(sorted((a, b)))
            if key in drawn or a not in pos or b not in pos:
                continue
            drawn.add(key)
            ax, ay = pos[a]; bx, by = pos[b]
            edges.append({"type": "spouse",
                          "x1": round(ax + CARD_W / 2), "y1": round(ay + CARD_H / 2),
                          "x2": round(bx + CARD_W / 2), "y2": round(by + CARD_H / 2)})

    height = (max(gen.values()) + 1) * ROW_STRIDE - GAP_Y
    return {"nodes": nodes, "edges": edges,
            "width": round(total_w), "height": round(height), "count": len(people)}
