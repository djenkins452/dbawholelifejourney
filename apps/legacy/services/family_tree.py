"""
Family View — a visualization of Canonical Truth, not a genealogy database.

Lays the People + Relationships Legacy already holds out as a TIDY FAMILY TREE:
generations stack vertically (ancestors above, descendants below), children are
centered beneath their parents, siblings sit side by side, spouses adjacent. The
keeper's own node ("me") is found so the view can open centered on them.

Layout is O(n) (a single post-order sweep that centers each parent over its
already-placed children) so it scales to large imported trees. Pure read model —
no writes, no Discovery, no CoS. Coordinates only; styling lives in the client.
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


def _resolve_self(user, people):
    """The keeper's own Person node: an explicit is_self, else a name match to
    the WLJ user's full name, else None (the view then just fits the whole tree)."""
    for p in people:
        if p.is_self:
            return p.pk
    full = ""
    getter = getattr(user, "get_full_name", None)
    if callable(getter):
        full = (getter() or "").strip().lower()
    if full:
        for p in people:
            if p.display_name.strip().lower() == full:
                return p.pk
    return None


def build_family_graph(user):
    from apps.legacy.models import Person, Relationship, RelationshipAlias

    empty = {"nodes": [], "edges": [], "width": 0, "height": 0, "count": 0,
             "me": None, "me_x": 0, "me_y": 0}
    people = list(Person.objects.filter(user=user).select_related("primary_photo"))
    if not people:
        return empty
    pids = {p.pk for p in people}
    P = {p.pk: p for p in people}

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

    # Vertical level = longest path from a root (someone with no known parent).
    gen = {}

    def _gen(pk, stack):
        if pk in gen:
            return gen[pk]
        if pk in stack:
            return 0
        ps = [pp for pp in parents.get(pk, ()) if pp in pids]
        gen[pk] = (max(_gen(pp, stack | {pk}) for pp in ps) + 1) if ps else 0
        return gen[pk]

    for p in people:
        _gen(p.pk, set())

    # Tidy horizontal layout: place a person's children first, then center the
    # person (and their spouse) over them. Leaves take sequential slots, so
    # siblings land adjacent and subtrees never overlap.
    placed = {}
    leaf = [0.0]

    def _partner(pk):
        sp = sorted(s for s in spouses.get(pk, ()) if s in pids)
        return sp[0] if sp else None

    def _place(pk, stack):
        if pk in placed:
            return placed[pk]
        if pk in stack:
            return None
        stack = stack | {pk}
        partner = _partner(pk)
        kid_set = set(children.get(pk, ()))
        if partner:
            kid_set |= set(children.get(partner, ()))
        kids = sorted(k for k in kid_set
                      if k in pids and k not in placed and k not in stack)
        centers = [c for c in (_place(k, stack) for k in kids) if c is not None]
        if centers:
            center = sum(centers) / len(centers)
        else:
            center = leaf[0] * COL_STRIDE
            leaf[0] += 1
        if partner and partner not in placed and partner not in stack:
            placed[pk] = center - COL_STRIDE * 0.5
            placed[partner] = center + COL_STRIDE * 0.5
        else:
            placed[pk] = center
        return placed[pk]

    roots = sorted((p.pk for p in people if not (parents.get(p.pk, set()) & pids)),
                   key=lambda k: (gen.get(k, 0), P[k].display_name))
    for rpk in roots:
        _place(rpk, set())
    for p in people:                       # cycles / disconnected branches
        if p.pk not in placed:
            _place(p.pk, set())

    minx = min(placed.values())
    offset = CARD_W / 2 - minx             # so the leftmost card starts at x=0

    aliases = defaultdict(list)
    for a in RelationshipAlias.objects.filter(user=user).exclude(person__isnull=True):
        aliases[a.person_id].append(a.label)

    self_pk = _resolve_self(user, people)
    pos, nodes = {}, []
    me_x = me_y = 0
    max_cx = 0
    for p in people:
        cx = placed[p.pk] + offset
        cy = gen[p.pk] * ROW_STRIDE + CARD_H / 2
        pos[p.pk] = (cx, cy)
        max_cx = max(max_cx, cx)
        photo = (p.primary_photo.file.url
                 if (p.primary_photo and p.primary_photo.file) else "")
        aka = aliases.get(p.pk, [])
        search = " ".join([p.display_name, p.also_known_as or ""] + aka).lower()
        nodes.append({
            "id": p.pk, "name": p.display_name, "initials": _initials(p.display_name),
            "photo": photo, "birth": p.birth_year, "death": p.death_year,
            "living": p.death_year is None, "rel": p.relationship_label,
            "x": round(cx - CARD_W / 2), "y": round(gen[p.pk] * ROW_STRIDE),
            "cx": round(cx), "cy": round(cy), "search": search, "is_self": p.pk == self_pk,
        })
        if p.pk == self_pk:
            me_x, me_y = cx, cy

    edges = []
    for cpk, pset in parents.items():
        if cpk not in pos:
            continue
        cx, cy = pos[cpk]
        for ppk in pset:
            if ppk in pos:
                px, py = pos[ppk]
                edges.append({"type": "parent",
                              "x1": round(px), "y1": round(py + CARD_H / 2),
                              "x2": round(cx), "y2": round(cy - CARD_H / 2)})
    drawn = set()
    for a, sset in spouses.items():
        for b in sset:
            key = tuple(sorted((a, b)))
            if key in drawn or a not in pos or b not in pos:
                continue
            drawn.add(key)
            ax, ay = pos[a]; bx, by = pos[b]
            edges.append({"type": "spouse", "x1": round(ax), "y1": round(ay),
                          "x2": round(bx), "y2": round(by)})

    height = (max(gen.values()) + 1) * ROW_STRIDE - GAP_Y
    return {"nodes": nodes, "edges": edges, "width": round(max_cx + CARD_W / 2),
            "height": round(height), "count": len(people),
            "me": self_pk, "me_x": round(me_x), "me_y": round(me_y)}
