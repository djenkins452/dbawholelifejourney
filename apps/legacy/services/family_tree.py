"""
Family View — a focal-person window into Canonical Truth, not a graph database.

A family tree always has a FOCUS. This module never renders the whole imported
graph; it renders the family AROUND one person — their ancestors above (parents →
grandparents → great-grandparents), their spouse and siblings beside them, and
their descendants below (children → grandchildren). Click anyone and they become
the new focus; the neighborhood is recomputed around them. Because only a bounded
neighborhood is ever built, a 1,500-person import stays fast and readable.

Layout is the tidy post-order sweep (parents centered over their children); the
client then centers the viewport on the focus. Pure read model — no writes, no
Discovery, no CoS. Coordinates only; styling lives in the client.
"""

from collections import defaultdict

# Card geometry (kept in sync with .fam-node in legacy.css).
CARD_W, CARD_H = 176, 96
GAP_X, GAP_Y = 30, 92
ROW_STRIDE = CARD_H + GAP_Y
COL_STRIDE = CARD_W + GAP_X

# How far the focal neighborhood reaches (kept small so it fits without zooming).
ANCESTOR_LEVELS = 3      # parents, grandparents, great-grandparents
DESCENDANT_LEVELS = 2    # children, grandchildren

_PARENT_OF = ("parent of", "father of", "mother of", "mom of", "dad of", "mum of",
              "guardian of")   # step-parent / adoptive parent contain "parent of"
_CHILD_OF = ("child of", "son of", "daughter of")
_SPOUSE = ("married", "spouse", "husband", "wife", "wed", "partner",
           "fianc", "boyfriend", "girlfriend", "relationship with")


def _initials(name):
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:1].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


def _edges(user):
    """Parent/child/spouse adjacency over ALL of the user's relationships."""
    from apps.legacy.models import Relationship
    parents, children, spouses = defaultdict(set), defaultdict(set), defaultdict(set)
    for r in Relationship.objects.filter(user=user).values_list(
            "from_person_id", "to_person_id", "relationship_type"):
        f, t, typ = r[0], r[1], (r[2] or "").lower()
        if any(k in typ for k in _PARENT_OF):
            children[f].add(t); parents[t].add(f)
        elif any(k in typ for k in _CHILD_OF):
            children[t].add(f); parents[f].add(t)
        elif any(k in typ for k in _SPOUSE):
            spouses[f].add(t); spouses[t].add(f)
    return parents, children, spouses


def _person_row(p):
    return {
        "id": p.pk, "name": p.display_name, "initials": _initials(p.display_name),
        "birth": p.birth_year, "death": p.death_year, "living": p.death_year is None,
        "birth_display": p.display_birth, "death_display": p.display_death,
        "rel": p.relationship_label,
        "photo": (p.primary_photo.file.url
                  if (p.primary_photo and p.primary_photo.file) else ""),
    }


def _resolve_self(user, people):
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


def _neighborhood(focus, parents, children, spouses):
    """The bounded set of people around `focus` we actually render."""
    keep = {focus}
    frontier = {focus}
    for _ in range(ANCESTOR_LEVELS):
        nxt = set()
        for p in frontier:
            nxt |= parents.get(p, set())
        keep |= nxt
        frontier = nxt
        if not frontier:
            break
    frontier = {focus}
    for _ in range(DESCENDANT_LEVELS):
        nxt = set()
        for p in frontier:
            nxt |= children.get(p, set())
        keep |= nxt
        frontier = nxt
        if not frontier:
            break
    for par in parents.get(focus, set()):     # siblings share a parent with focus
        keep |= children.get(par, set())
    for p in [focus] + list(children.get(focus, set())):  # spouses → couples show
        keep |= spouses.get(p, set())
    return keep


def _layout(user, people, parents, children, spouses, focus_pk, me_pk):
    """Tidy layout of a set of people. `people` is a list of Person; adjacency
    dicts are already restricted to this set. Returns the graph payload."""
    from apps.legacy.models import RelationshipAlias

    pids = {p.pk for p in people}
    P = {p.pk: p for p in people}

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

    # Spouses share a generation — a married-in spouse (no ancestors in view)
    # sits on the couple's row, not floated to the top. Fixpoint over spouse pairs.
    changed = True
    while changed:
        changed = False
        for a, sset in spouses.items():
            if a not in gen:
                continue
            for b in sset:
                if b not in gen:
                    continue
                m = max(gen[a], gen[b])
                if gen[a] != m:
                    gen[a] = m; changed = True
                if gen[b] != m:
                    gen[b] = m; changed = True

    placed, leaf = {}, [0.0]

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
        kids = sorted(k for k in kid_set if k in pids and k not in placed and k not in stack)
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
    for p in people:
        if p.pk not in placed:
            _place(p.pk, set())

    minx = min(placed.values()) if placed else 0
    offset = CARD_W / 2 - minx

    aliases = defaultdict(list)
    for a in RelationshipAlias.objects.filter(user=user, person_id__in=pids).exclude(person__isnull=True):
        aliases[a.person_id].append(a.label)

    pos, nodes = {}, []
    fx = fy = 0
    max_cx = 0
    for p in people:
        cx = placed[p.pk] + offset
        cy = gen[p.pk] * ROW_STRIDE + CARD_H / 2
        pos[p.pk] = (cx, cy)
        max_cx = max(max_cx, cx)
        photo = (p.primary_photo.file.url
                 if (p.primary_photo and p.primary_photo.file) else "")
        search = " ".join([p.display_name, p.also_known_as or ""] + aliases.get(p.pk, [])).lower()
        nodes.append({
            "id": p.pk, "name": p.display_name, "initials": _initials(p.display_name),
            "photo": photo, "birth": p.birth_year, "death": p.death_year,
            "birth_display": p.display_birth, "death_display": p.display_death,
            "living": p.death_year is None, "rel": p.relationship_label,
            "x": round(cx - CARD_W / 2), "y": round(gen[p.pk] * ROW_STRIDE),
            "cx": round(cx), "cy": round(cy), "search": search,
            "is_self": p.pk == me_pk, "is_focus": p.pk == focus_pk,
        })
        if p.pk == focus_pk:
            fx, fy = cx, cy

    focus_gen = gen.get(focus_pk, 0)
    edges = []
    # Parent→child lines, coloured by side of the focus: ancestors above (up),
    # descendants below (down) — matching the legend.
    for cpk, pset in parents.items():
        if cpk not in pos:
            continue
        cx, cy = pos[cpk]
        etype = "up" if gen.get(cpk, 0) <= focus_gen else "down"
        for ppk in pset:
            if ppk in pos:
                px, py = pos[ppk]
                edges.append({"type": etype, "x1": round(px), "y1": round(py + CARD_H / 2),
                              "x2": round(cx), "y2": round(cy - CARD_H / 2)})
    # Spouse ties.
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
    # Sibling ties — a light dotted connector in the gap between adjacent siblings.
    sib_drawn = set()
    for ppk, kids in children.items():
        row = sorted((k for k in kids if k in pos), key=lambda k: pos[k][0])
        for i in range(len(row) - 1):
            a, b = row[i], row[i + 1]
            key = tuple(sorted((a, b)))
            if key in sib_drawn:
                continue
            ax, ay = pos[a]; bx, by = pos[b]
            if abs(round(ay) - round(by)) <= 1 and abs(bx - ax) <= COL_STRIDE + 1:
                sib_drawn.add(key)
                edges.append({"type": "sibling",
                              "x1": round(ax + CARD_W / 2), "y1": round(ay),
                              "x2": round(bx - CARD_W / 2), "y2": round(by)})

    height = ((max(gen.values()) + 1) * ROW_STRIDE - GAP_Y) if gen else 0
    return {"nodes": nodes, "edges": edges, "width": round(max_cx + CARD_W / 2),
            "height": round(height), "shown": len(people),
            "focus": focus_pk, "focus_x": round(fx), "focus_y": round(fy), "me": me_pk}


def _restrict(edges_dicts, keep):
    """Restrict parent/child/spouse dicts to a keep-set."""
    parents, children, spouses = edges_dicts
    def r(d):
        out = defaultdict(set)
        for k in keep:
            out[k] = {v for v in d.get(k, set()) if v in keep}
        return out
    return r(parents), r(children), r(spouses)


def build_family_view(user, focus_pk=None):
    """The family AROUND a focal person (their branch only). Defaults the focus to
    the keeper ('me'); pass focus_pk to re-center on anyone. Bounded + fast."""
    from apps.legacy.models import Person

    all_people = list(Person.objects.filter(user=user).only(
        "pk", "display_name", "is_self", "also_known_as", "birth_year", "death_year",
        "birth_date", "death_date", "relationship_label", "primary_photo",
    ).select_related("primary_photo"))
    total = len(all_people)
    if not all_people:
        return {"nodes": [], "edges": [], "width": 0, "height": 0, "shown": 0,
                "count": 0, "focus": None, "focus_x": 0, "focus_y": 0, "me": None}

    by_id = {p.pk: p for p in all_people}
    parents, children, spouses = _edges(user)
    me_pk = _resolve_self(user, all_people)

    # Resolve the focus: an explicitly requested (owned) person, else me, else a
    # sensible default (the most-connected person, so the first view isn't lonely).
    focus = None
    try:
        focus = int(focus_pk) if focus_pk else None
    except (TypeError, ValueError):
        focus = None
    if focus not in by_id:
        focus = None
    if focus is None:
        focus = me_pk
    if focus is None:
        focus = max(all_people, key=lambda p: len(parents.get(p.pk, ())) +
                    len(children.get(p.pk, ())) + len(spouses.get(p.pk, ()))).pk

    keep = _neighborhood(focus, parents, children, spouses)
    people = [by_id[pk] for pk in keep if pk in by_id]
    rp, rc, rs = _restrict((parents, children, spouses), set(keep))
    graph = _layout(user, people, rp, rc, rs, focus, me_pk)
    graph["count"] = total

    # Side profile panel for the focal person — ALL their direct relatives
    # (even any cropped from the tree view), each a link that re-centers.
    def _rows(idset):
        seen, out = set(), []
        for pk in idset:
            if pk in by_id and pk not in seen:
                seen.add(pk)
                out.append(_person_row(by_id[pk]))
        return out

    fp = by_id[focus]
    sib_ids = [k for par in parents.get(focus, ()) for k in children.get(par, ())
               if k != focus]
    graph["panel"] = {
        "person": _person_row(fp), "is_self": focus == me_pk,
        "parents": _rows(sorted(parents.get(focus, ()))),
        "spouses": _rows(sorted(spouses.get(focus, ()))),
        "children": _rows(sorted(children.get(focus, ()))),
        "siblings": _rows(sorted(set(sib_ids))),
    }
    return graph


def home_relatives(user):
    """The keeper's closest family for the People Home — you, parents, spouse(s),
    siblings, children (three generations). Returns Person objects grouped, or
    None when 'me' isn't known yet. Read-only."""
    from apps.legacy.models import Person
    people = list(Person.objects.filter(user=user).select_related("primary_photo"))
    if not people:
        return None
    by_id = {p.pk: p for p in people}
    me_pk = _resolve_self(user, people)
    if me_pk is None:
        return None
    parents, children, spouses = _edges(user)

    def rows(ids):
        return [by_id[i] for i in ids if i in by_id]

    sib_ids = {k for par in parents.get(me_pk, ()) for k in children.get(par, ())
               if k != me_pk}
    return {
        "me": by_id[me_pk],
        "parents": rows(sorted(parents.get(me_pk, ()))),
        "spouses": rows(sorted(spouses.get(me_pk, ()))),
        "siblings": rows(sorted(sib_ids)),
        "children": rows(sorted(children.get(me_pk, ()))),
    }


def family_search_index(user):
    """A lightweight index of EVERY person (id, name, meta, search text) so the
    Family search finds anyone — selecting one re-centers the tree on them."""
    from apps.legacy.models import Person, RelationshipAlias
    aliases = defaultdict(list)
    for a in RelationshipAlias.objects.filter(user=user).exclude(person__isnull=True):
        aliases[a.person_id].append(a.label)
    out = []
    for p in Person.objects.filter(user=user).only(
            "pk", "display_name", "also_known_as", "birth_year", "death_year"):
        meta = ""
        if p.birth_year or p.death_year:
            meta = "%s – %s" % (p.birth_year or "", p.death_year or "")
        text = " ".join([p.display_name, p.also_known_as or ""] + aliases.get(p.pk, [])).lower()
        out.append({"id": p.pk, "name": p.display_name, "meta": meta, "text": text})
    return out


# Retained: full-graph builder (not used by the focal page, kept for tests/tools).
def build_family_graph(user):
    from apps.legacy.models import Person
    people = list(Person.objects.filter(user=user).select_related("primary_photo"))
    if not people:
        return {"nodes": [], "edges": [], "width": 0, "height": 0, "count": 0,
                "shown": 0, "me": None, "focus": None, "focus_x": 0, "focus_y": 0}
    parents, children, spouses = _edges(user)
    me_pk = _resolve_self(user, people)
    g = _layout(user, people, parents, children, spouses, me_pk, me_pk)
    g["count"] = len(people)
    g["me_x"], g["me_y"] = g["focus_x"], g["focus_y"]
    return g
