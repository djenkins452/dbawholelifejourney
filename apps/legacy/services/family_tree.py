"""
Family View — a focal-person, family-UNIT pedigree of Canonical Truth.

A family tree is not a generic graph laid out by generation number. It is built
from FAMILIES (a couple and their children). This module renders the family AROUND
a focus person:
  • generations are measured RELATIVE to the focus (parents one level up, children
    one level down, spouse and siblings on the SAME level as the focus) — so
    siblings never float onto a parent row;
  • the focus's descendants are a tidy tree (children centered beneath the couple);
  • siblings sit on the focus's row; ancestors fan upward as a pedigree, with each
    couple placed together and centered over their children;
  • connectors respect the actual relationship TYPE — a marriage is drawn
    differently from a partner, a former spouse, or an affair, and two people who
    were never a couple are NOT drawn as one.

Click anyone → they become the new focus and the neighborhood is recomputed.
Bounded, so a 1,500-person import stays fast. Pure read model — no writes, no CoS.
"""

from collections import defaultdict, deque

# Card geometry (kept in sync with .fam-node in legacy.css).
CARD_W, CARD_H = 176, 96
GAP_X, GAP_Y = 34, 96
ROW_STRIDE = CARD_H + GAP_Y
COL_STRIDE = CARD_W + GAP_X
COUPLE_HALF = (CARD_W + 16) / 2       # spouses sit this far either side of centre

ANCESTOR_LEVELS = 3      # parents, grandparents, great-grandparents
DESCENDANT_LEVELS = 2    # children, grandchildren

_PARENT_OF = ("parent of", "father of", "mother of", "mom of", "dad of", "mum of",
              "guardian of")   # step-parent / adoptive parent contain "parent of"
_CHILD_OF = ("child of", "son of", "daughter of")
_COUPLE = ("married", "spouse", "wed", "partner", "fianc", "boyfriend",
           "girlfriend", "relationship with", "affair")


def _couple_style(rtype):
    """How a couple's connector should read, from the relationship type."""
    t = (rtype or "").lower()
    if "former" in t:
        return "former"
    if "affair" in t or "relationship with" in t:
        return "affair"
    if "married" in t or ("spouse" in t):
        return "married"
    if any(k in t for k in ("partner", "fianc", "boyfriend", "girlfriend")):
        return "partner"
    return "unknown"


def _initials(name):
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:1].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


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
    from apps.legacy.services.self_binding import get_self_person
    p = get_self_person(user)
    return p.pk if p else None


def _edges(user):
    """parent/child adjacency + typed couple links for the FAMILY-tree subset of
    the user's relationships. Membership in the family tree is decided by the ONE
    stored category (family / romantic) — the Family View owns no 'is this family?'
    keyword logic. The keyword matching below only picks the graph ROLE
    (parent / child / spouse) and the couple's connector style — both structural,
    both live here alone."""
    from apps.legacy.models import Relationship
    parents, children, spouses = defaultdict(set), defaultdict(set), defaultdict(set)
    couples = {}   # frozenset({a, b}) -> style
    for r in Relationship.objects.filter(
            user=user,
            relationship_category__in=list(Relationship.FAMILY_TREE_CATEGORIES),
    ).values_list("from_person_id", "to_person_id", "relationship_type"):
        f, t, typ = r[0], r[1], (r[2] or "").lower()
        if any(k in typ for k in _PARENT_OF):
            children[f].add(t); parents[t].add(f)
        elif any(k in typ for k in _CHILD_OF):
            children[t].add(f); parents[f].add(t)
        elif any(k in typ for k in _COUPLE):
            spouses[f].add(t); spouses[t].add(f)
            couples[frozenset((f, t))] = _couple_style(typ)
    return parents, children, spouses, couples


def _neighborhood(focus, parents, children, spouses):
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
    for par in parents.get(focus, set()):        # siblings
        keep |= children.get(par, set())
        keep |= spouses.get(par, set())          # step-parents (a parent's spouse)
    for p in [focus] + list(children.get(focus, set())):  # couples of focus & children
        keep |= spouses.get(p, set())
    return keep


def _restrict(edges, keep):
    parents, children, spouses, couples = edges
    keep = set(keep)

    def r(d):
        out = defaultdict(set)
        for k in keep:
            out[k] = {v for v in d.get(k, set()) if v in keep}
        return out

    cp = {k: v for k, v in couples.items() if k <= keep}
    return r(parents), r(children), r(spouses), cp


def _layout(user, people, parents, children, spouses, couples, focus_pk, me_pk):
    from apps.legacy.models import RelationshipAlias

    pids = {p.pk for p in people}
    P = {p.pk: p for p in people}
    if focus_pk not in pids:
        focus_pk = next(iter(pids))

    # 1. Generation RELATIVE to focus (parents up, children down, spouse level).
    gen = {focus_pk: 0}
    dq = deque([focus_pk])
    while dq:
        x = dq.popleft()
        g = gen[x]
        for pp in parents.get(x, ()):
            if pp in pids and pp not in gen:
                gen[pp] = g - 1; dq.append(pp)
        for c in children.get(x, ()):
            if c in pids and c not in gen:
                gen[c] = g + 1; dq.append(c)
        for s in spouses.get(x, ()):
            if s in pids and s not in gen:
                gen[s] = g; dq.append(s)
    for p in people:
        gen.setdefault(p.pk, 0)

    pos = {}
    leaf = [0.0]

    def partner_of(pk):
        sp = sorted(s for s in spouses.get(pk, ())
                    if s in pids and gen.get(s) == gen.get(pk) and s not in pos)
        return sp[0] if sp else None

    # 2a. Descendants of the focus — a tidy tree, children centred under the couple.
    def place_down(pk, stack):
        if pk in pos:
            return pos[pk]
        if pk in stack:
            return None
        stack = stack | {pk}
        partner = partner_of(pk)
        kidset = set(children.get(pk, ()))
        if partner:
            kidset |= set(children.get(partner, ()))
        kids = sorted(k for k in kidset
                      if k in pids and gen.get(k) == gen.get(pk) + 1
                      and k not in pos and k not in stack)
        centers = [c for c in (place_down(k, stack) for k in kids) if c is not None]
        center = sum(centers) / len(centers) if centers else leaf[0] * COL_STRIDE
        if not centers:
            leaf[0] += 1
        if partner and partner not in pos:
            pos[pk] = center - COUPLE_HALF
            pos[partner] = center + COUPLE_HALF
            return center
        pos[pk] = center
        return center

    place_down(focus_pk, set())

    # 2b. Siblings share the focus's row, flanking the focus's block.
    sib = []
    for par in parents.get(focus_pk, ()):
        for k in children.get(par, ()):
            if (k in pids and k != focus_pk and gen.get(k) == 0
                    and k not in pos and k not in sib):
                sib.append(k)
    sib.sort(key=lambda k: (P[k].birth_year or 0, P[k].display_name))
    row0 = [x for x in pos if gen.get(x) == 0]
    left_x = (min(pos[x] for x in row0) if row0 else 0) - COL_STRIDE
    right_x = (max(pos[x] for x in row0) if row0 else 0) + COL_STRIDE
    half = (len(sib) + 1) // 2
    lx = left_x
    for k in reversed(sib[:half]):
        pos[k] = lx; lx -= COL_STRIDE
    rx = right_x
    for k in sib[half:]:
        pos[k] = rx; rx += COL_STRIDE

    # 2c. Ancestors — a pedigree fanning up, couples together, centred over children.
    def _units(pks):
        units, used = [], set()
        for a in sorted(pks, key=lambda k: (P[k].birth_year or 0, P[k].display_name)):
            if a in used:
                continue
            mate = next((b for b in pks if b != a and b not in used
                         and frozenset((a, b)) in couples), None)
            if mate:
                units.append([a, mate]); used |= {a, mate}
            else:
                units.append([a]); used.add(a)
        return units

    def place_up(child_pks, depth):
        cps = [c for c in child_pks if c in pos]
        if not cps:
            return
        ps = set()
        for c in cps:
            ps |= {pp for pp in parents.get(c, ()) if pp in pids and gen.get(pp) == gen[c] - 1
                   and pp not in pos}
        if not ps:
            return
        center = sum(pos[c] for c in cps) / len(cps)
        spread = COL_STRIDE * (1.7 ** (depth - 1))
        units = _units(ps)
        start = center - spread * (len(units) - 1) / 2.0
        for i, unit in enumerate(units):
            ux = start + i * spread
            if len(unit) == 2:
                pos[unit[0]] = ux - COUPLE_HALF
                pos[unit[1]] = ux + COUPLE_HALF
            else:
                pos[unit[0]] = ux
        for pp in ps:
            place_up([pp], depth + 1)

    place_up([focus_pk] + sib, 1)
    # place any straggler (e.g. a step-parent couple) near their partner / focus
    for p in people:
        if p.pk not in pos:
            mate = next((s for s in spouses.get(p.pk, ()) if s in pos), None)
            pos[p.pk] = (pos[mate] + COUPLE_HALF) if mate is not None else 0.0

    # 3. Normalise to screen coordinates.
    min_gen = min(gen.values())
    min_x = min(pos.values()) if pos else 0
    off_x = CARD_W / 2 - min_x

    aliases = defaultdict(list)
    for a in RelationshipAlias.objects.filter(user=user, person_id__in=pids).exclude(person__isnull=True):
        aliases[a.person_id].append(a.label)

    coords, nodes = {}, []
    fx = fy = 0
    max_cx = 0
    for p in people:
        cx = pos[p.pk] + off_x
        y = (gen[p.pk] - min_gen) * ROW_STRIDE
        cy = y + CARD_H / 2
        coords[p.pk] = (cx, cy, y)
        max_cx = max(max_cx, cx)
        search = " ".join([p.display_name, p.also_known_as or ""] + aliases.get(p.pk, [])).lower()
        nodes.append({
            "id": p.pk, "name": p.display_name, "initials": _initials(p.display_name),
            "photo": (p.primary_photo.file.url if (p.primary_photo and p.primary_photo.file) else ""),
            "birth": p.birth_year, "death": p.death_year,
            "birth_display": p.display_birth, "death_display": p.display_death,
            "living": p.death_year is None, "rel": p.relationship_label,
            "x": round(cx - CARD_W / 2), "y": round(y), "cx": round(cx), "cy": round(cy),
            "search": search, "is_self": p.pk == me_pk, "is_focus": p.pk == focus_pk,
        })
        if p.pk == focus_pk:
            fx, fy = cx, cy

    # 4. Connectors. Children descend from the couple midpoint (or a single parent).
    edges = []
    for cpk in pids:
        if cpk not in coords:
            continue
        ccx, _ccy, cy_top = coords[cpk][0], coords[cpk][1], coords[cpk][2]
        ps = [pp for pp in parents.get(cpk, ()) if pp in coords and gen.get(pp) == gen[cpk] - 1]
        if not ps:
            continue
        side = "up" if gen[cpk] <= 0 else "down"
        coupled = [pp for pp in ps if any(frozenset((pp, o)) in couples for o in ps if o != pp)]
        if len(ps) == 2 and frozenset(ps) in couples:
            px = (coords[ps[0]][0] + coords[ps[1]][0]) / 2
            py = coords[ps[0]][2] + CARD_H
            edges.append({"type": side, "x1": round(px), "y1": round(py),
                          "x2": round(ccx), "y2": round(cy_top)})
        else:
            for pp in ps:
                edges.append({"type": side, "x1": round(coords[pp][0]), "y1": round(coords[pp][2] + CARD_H),
                              "x2": round(ccx), "y2": round(cy_top)})
    for key, style in couples.items():
        a, b = tuple(key)
        if a in coords and b in coords and gen.get(a) == gen.get(b):
            edges.append({"type": "couple-" + style,
                          "x1": round(coords[a][0]), "y1": round(coords[a][1]),
                          "x2": round(coords[b][0]), "y2": round(coords[b][1])})

    height = (max(gen.values()) - min_gen + 1) * ROW_STRIDE - GAP_Y if gen else 0
    return {"nodes": nodes, "edges": edges, "width": round(max_cx + CARD_W / 2),
            "height": round(height), "shown": len(people),
            "focus": focus_pk, "focus_x": round(fx), "focus_y": round(fy), "me": me_pk}


def family_search_index(user):
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


def home_relatives(user):
    """The keeper's closest family for the People Home — you, parents, spouse(s),
    siblings, children. Returns Person objects grouped, or None when 'me' isn't
    known yet."""
    from apps.legacy.models import Person
    people = list(Person.objects.filter(user=user).select_related("primary_photo"))
    if not people:
        return None
    by_id = {p.pk: p for p in people}
    me_pk = _resolve_self(user, people)
    if me_pk is None:
        return None
    parents, children, spouses, _couples = _edges(user)

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


def build_family_view(user, focus_pk=None):
    """The family AROUND a focal person — a family-unit pedigree. Defaults the
    focus to the keeper; pass focus_pk to re-center on anyone. Bounded + fast."""
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
    parents, children, spouses, couples = _edges(user)
    me_pk = _resolve_self(user, all_people)

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
    rp, rc, rs, rcp = _restrict((parents, children, spouses, couples), keep)
    graph = _layout(user, people, rp, rc, rs, rcp, focus, me_pk)
    graph["count"] = total

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


def build_family_graph(user):
    """Full-graph builder — retained for tests/tools (the page uses build_family_view)."""
    from apps.legacy.models import Person
    people = list(Person.objects.filter(user=user).select_related("primary_photo"))
    if not people:
        return {"nodes": [], "edges": [], "width": 0, "height": 0, "count": 0,
                "shown": 0, "me": None, "focus": None, "focus_x": 0, "focus_y": 0}
    parents, children, spouses, couples = _edges(user)
    me_pk = _resolve_self(user, people)
    focus = me_pk or people[0].pk
    g = _layout(user, people, parents, children, spouses, couples, focus, me_pk)
    g["count"] = len(people)
    g["me_x"], g["me_y"] = g["focus_x"], g["focus_y"]
    return g
