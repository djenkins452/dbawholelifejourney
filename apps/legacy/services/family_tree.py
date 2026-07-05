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

# Card geometry (kept in sync with .fam-node in legacy.css). Larger cards — only
# three generations are ever shown, so there is room to breathe.
CARD_W, CARD_H = 208, 176
UNIT_GAP = 40                          # horizontal gap between adjacent family units
COUPLE_GAP = 36                        # visible gap between two partners in a couple
COUPLE_HALF = (CARD_W + COUPLE_GAP) / 2   # each partner sits this far off the couple centre
ROW_GAP = 118                          # vertical gap between generation rows
ROW_STRIDE = CARD_H + ROW_GAP
COL_STRIDE = CARD_W + UNIT_GAP
GUTTER = 150                           # left margin reserved for generation labels

# STRICT three-generation window: parents above, focus + spouse + siblings, children
# below. Never grandparents, grandchildren, cousins, aunts, or uncles — those appear
# only after navigating to that person. Readability over completeness.
ANCESTOR_LEVELS = 1
DESCENDANT_LEVELS = 1


def _pack_row(units):
    """Place a row of family units left→right by desired centre, guaranteeing NO
    horizontal overlap (each unit starts at least UNIT_GAP past the previous one),
    then shift the whole row so its mean centre matches the mean desired centre —
    keeping parents sitting over the middle of their children. Mutates each unit
    dict with a `left`. `units` = [{members, width, desired}, …]."""
    units.sort(key=lambda u: u["desired"])
    prev_right = None
    for u in units:
        left = u["desired"] - u["width"] / 2.0
        if prev_right is not None and left < prev_right + UNIT_GAP:
            left = prev_right + UNIT_GAP
        u["left"] = left
        prev_right = left + u["width"]
    if units:
        cur = sum(u["left"] + u["width"] / 2.0 for u in units) / len(units)
        des = sum(u["desired"] for u in units) / len(units)
        shift = des - cur
        for u in units:
            u["left"] += shift

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


# A parent→child bond is drawn DASHED when it isn't biological (step / adoptive /
# foster / guardian); solid otherwise. Reflects Canonical Truth, never implies a
# biological bond that doesn't exist.
_NON_BIO = ("step", "adopt", "foster", "guardian")


def _link_style(rtype):
    t = (rtype or "").lower()
    return "dashed" if any(k in t for k in _NON_BIO) else "solid"


def _initials(name):
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:1].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


def _life_years(p):
    """A compact life-span string for the inspector: '1937 – 2010', '1971 – living',
    'd. 1990', or '' when unknown."""
    if p.birth_year and p.death_year:
        return "%s – %s" % (p.birth_year, p.death_year)
    if p.birth_year:
        return "%s – living" % p.birth_year
    if p.death_year:
        return "d. %s" % p.death_year
    return ""


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
    the user's relationships.

    Membership is decided by the ONE stored category (family / romantic) when it is
    present — the Family View owns no 'is this family?' policy. But it SELF-HEALS: a
    relationship whose category is blank (e.g. imported before the category backfill
    ran) is still included when its TYPE is clearly familial, so the tree never
    renders empty just because a migration hasn't caught up. A relationship with an
    explicit NON-family category is always excluded. The keyword matching picks the
    graph ROLE (parent / child / spouse) and the couple's connector style."""
    from apps.legacy.models import Relationship
    fam_cats = set(Relationship.FAMILY_TREE_CATEGORIES)
    parents, children, spouses = defaultdict(set), defaultdict(set), defaultdict(set)
    couples = {}      # frozenset({a, b}) -> couple style
    link_style = {}   # (parent_id, child_id) -> 'solid' | 'dashed'
    for f, t, typ, cat in Relationship.objects.filter(user=user).values_list(
            "from_person_id", "to_person_id", "relationship_type",
            "relationship_category"):
        typ = (typ or "").lower()
        if any(k in typ for k in _PARENT_OF):
            role = "parent"
        elif any(k in typ for k in _CHILD_OF):
            role = "child"
        elif any(k in typ for k in _COUPLE):
            role = "couple"
        else:
            continue
        # Authoritative category wins; a blank category falls back to the familial
        # role we just derived (self-heals pre-backfill data).
        if cat and cat not in fam_cats:
            continue
        if role == "parent":
            children[f].add(t); parents[t].add(f)
            link_style[(f, t)] = _link_style(typ)
        elif role == "child":
            children[t].add(f); parents[f].add(t)
            link_style[(t, f)] = _link_style(typ)
        else:
            spouses[f].add(t); spouses[t].add(f)
            couples[frozenset((f, t))] = _couple_style(typ)
    return parents, children, spouses, couples, link_style


def _neighborhood(focus, parents, children, spouses):
    """The STRICT immediate family around the focus — exactly three generations:

      • the focus's parents (and each parent's spouse → step-parents),
      • the focus, the focus's spouse(s), and the focus's siblings,
      • the focus's children.

    Deliberately NOT included: grandparents, grandchildren, aunts/uncles, cousins,
    nieces/nephews, in-laws, or siblings' spouses/children. Those appear only when
    that person becomes the focus. This is what keeps the tree readable at a glance."""
    keep = {focus}
    par = set(parents.get(focus, set()))
    keep |= par
    for p in par:
        keep |= spouses.get(p, set())            # step-parents (a parent's spouse)
        keep |= children.get(p, set())           # siblings (share a parent)
    keep |= spouses.get(focus, set())            # the focus's own spouse(s)
    keep |= children.get(focus, set())           # the focus's children
    return keep


def _restrict(edges, keep):
    parents, children, spouses, couples, link_style = edges
    keep = set(keep)

    def r(d):
        out = defaultdict(set)
        for k in keep:
            out[k] = {v for v in d.get(k, set()) if v in keep}
        return out

    cp = {k: v for k, v in couples.items() if k <= keep}
    ls = {(a, b): v for (a, b), v in link_style.items() if a in keep and b in keep}
    return r(parents), r(children), r(spouses), cp, ls


def _layout(user, people, parents, children, spouses, couples, link_style,
            focus_pk, me_pk):
    """Lay out the family AROUND the focus as clean generation rows of family UNITS.

    Descendants are a tidy tree (each leaf gets its own column, every parent sits
    over the middle of its children — so nothing overlaps). Siblings flank the focus
    on its own row. Ancestors fan upward: each parent couple is centred over its
    children, then the whole row is collision-packed so it can never overlap. Every
    parent→children link is an orthogonal T (a stem down from the couple, a bus
    across the children, a riser up to each child) — the visual language of a family
    tree, not a web of diagonals. Couples are joined by a short typed connector."""
    from apps.legacy.models import RelationshipAlias

    pids = {p.pk for p in people}
    P = {p.pk: p for p in people}
    if focus_pk not in pids:
        focus_pk = next(iter(pids))

    # Generation RELATIVE to focus (parents −1, children +1, spouse same level).
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

    def bkey(pk):
        return (P[pk].birth_year or 0, P[pk].display_name or "")

    def couple_partner(pk):
        """A spouse of pk on the same row that forms an actual couple (earliest-born
        preferred, for a stable pairing)."""
        best = None
        for s in spouses.get(pk, ()):
            if (s in pids and gen.get(s) == gen.get(pk)
                    and frozenset((pk, s)) in couples):
                if best is None or bkey(s) < bkey(best):
                    best = s
        return best

    def unit_width(members):
        return CARD_W if len(members) == 1 else 2 * CARD_W + COUPLE_GAP

    def order_couple(a, b):
        return [a, b] if bkey(a) <= bkey(b) else [b, a]

    center = {}     # pk -> centre x (float)
    used = set()

    def set_unit_center(members, cx):
        if len(members) == 1:
            center[members[0]] = cx
        else:
            m0, m1 = members
            center[m0] = cx - COUPLE_HALF
            center[m1] = cx + COUPLE_HALF

    def make_unit(pk):
        used.add(pk)
        mate = couple_partner(pk)
        if mate and mate not in used:
            used.add(mate)
            return order_couple(pk, mate)
        return [pk]

    # ── Descendants: a tidy tree rooted at the focus's couple ──────────────────
    cursor = [0.0]

    def child_units_of(members, cg):
        kids = set()
        for m in members:
            for c in children.get(m, ()):
                if c in pids and gen.get(c) == cg and c not in used:
                    kids.add(c)
        out = []
        for k in sorted(kids, key=bkey):
            if k not in used:
                out.append(make_unit(k))
        return out

    def tidy(members):
        g = gen[members[0]]
        kids = child_units_of(members, g + 1)
        w = unit_width(members)
        if not kids:
            cx = cursor[0] + w / 2.0
            cursor[0] += w + UNIT_GAP
        else:
            kcenters = [tidy(k) for k in kids]
            cx = (min(kcenters) + max(kcenters)) / 2.0
        set_unit_center(members, cx)
        return cx

    focus_unit = make_unit(focus_pk)
    focus_center = tidy(focus_unit)

    # ── Siblings: flank the focus on its own row, in birth order ───────────────
    row0_centers = [center[pk] for pk in center if gen.get(pk) == 0]
    bmin = min(row0_centers) - CARD_W / 2.0
    bmax = max(row0_centers) + CARD_W / 2.0
    sibs = []
    for par in parents.get(focus_pk, ()):
        if par in pids:
            for k in children.get(par, ()):
                if (k in pids and k != focus_pk and gen.get(k) == 0
                        and k not in used and k not in sibs):
                    sibs.append(k)
    sibs.sort(key=bkey)
    fb = bkey(focus_pk)
    left_sibs = [k for k in sibs if bkey(k) <= fb][::-1]   # nearest-older first, going left
    right_sibs = [k for k in sibs if bkey(k) > fb]
    step = CARD_W + UNIT_GAP
    lx = bmin - UNIT_GAP - CARD_W / 2.0
    for k in left_sibs:
        used.add(k); center[k] = lx; lx -= step
    rx = bmax + UNIT_GAP + CARD_W / 2.0
    for k in right_sibs:
        used.add(k); center[k] = rx; rx += step

    # ── Ancestors: parent couples centred over their children, then packed ─────
    g = -1
    while g >= -ANCESTOR_LEVELS:
        row_pks = [pk for pk in pids if gen.get(pk) == g and pk not in center]
        if row_pks:
            units, seen = [], set()
            for pk in sorted(row_pks, key=bkey):
                if pk in seen:
                    continue
                mate = couple_partner(pk)
                if mate and mate in row_pks and mate not in seen:
                    units.append(order_couple(pk, mate)); seen |= {pk, mate}
                else:
                    units.append([pk]); seen.add(pk)
            row_units = []
            for members in units:
                kids = [center[c] for m in members for c in children.get(m, ())
                        if c in center and gen.get(c) == g + 1]
                desired = sum(kids) / len(kids) if kids else focus_center
                row_units.append({"members": members, "width": unit_width(members),
                                  "desired": desired})
            _pack_row(row_units)
            for u in row_units:
                set_unit_center(u["members"], u["left"] + u["width"] / 2.0)
        g -= 1

    for p in people:                                   # any straggler → near focus
        center.setdefault(p.pk, focus_center)

    # ── Final guarantee: no two cards overlap, ever ────────────────────────────
    # Whatever the placement produced (real imported data has messier shapes than
    # any synthetic test), sweep each generation row left→right at UNIT granularity
    # and push overlapping units apart. Rows are on distinct y's, so a per-row 1-D
    # sweep makes overlap mathematically impossible.
    rows = defaultdict(list)
    for pk in center:
        if pk in pids:
            rows[gen.get(pk, 0)].append(pk)
    for g, pks in rows.items():
        pset = set(pks)
        used, units = set(), []
        for pk in sorted(pks, key=lambda k: center[k]):
            if pk in used:
                continue
            mate = next((s for s in spouses.get(pk, ())
                         if s in pset and s not in used
                         and frozenset((pk, s)) in couples), None)
            members = sorted([pk, mate], key=lambda k: center[k]) if mate else [pk]
            for m in members:
                used.add(m)
            c = sum(center[m] for m in members) / len(members)
            units.append({"members": members, "c": c, "w": unit_width(members)})
        units.sort(key=lambda u: u["c"])
        prev_right = None
        for u in units:
            left = u["c"] - u["w"] / 2.0
            if prev_right is not None and left < prev_right + UNIT_GAP:
                left = prev_right + UNIT_GAP
            shift = (left + u["w"] / 2.0) - u["c"]
            if shift:
                for m in u["members"]:
                    center[m] += shift
            prev_right = left + u["w"]

    # ── Screen coordinates ─────────────────────────────────────────────────────
    min_gen = min(gen.values())
    min_center = min(center.values()) if center else 0
    off_x = GUTTER + CARD_W / 2.0 - min_center   # leave a left gutter for gen labels

    aliases = defaultdict(list)
    for a in RelationshipAlias.objects.filter(
            user=user, person_id__in=pids).exclude(person__isnull=True):
        aliases[a.person_id].append(a.label)

    coords, nodes = {}, []
    fx = fy = 0
    max_cx = 0
    for p in people:
        cx = center[p.pk] + off_x
        y = (gen[p.pk] - min_gen) * ROW_STRIDE
        cy = y + CARD_H / 2.0
        coords[p.pk] = (cx, cy, y)
        max_cx = max(max_cx, cx)
        search = " ".join([p.display_name, p.also_known_as or ""] + aliases.get(p.pk, [])).lower()
        nodes.append({
            "id": p.pk, "name": p.display_name, "initials": _initials(p.display_name),
            "photo": (p.primary_photo.file.url if (p.primary_photo and p.primary_photo.file) else ""),
            "birth": p.birth_year, "death": p.death_year,
            "birth_display": p.display_birth, "death_display": p.display_death,
            "living": p.death_year is None, "rel": p.relationship_label,
            "x": round(cx - CARD_W / 2.0), "y": round(y), "cx": round(cx), "cy": round(cy),
            "search": search, "is_self": p.pk == me_pk, "is_focus": p.pk == focus_pk,
        })
        if p.pk == focus_pk:
            fx, fy = cx, cy

    # ── Connectors ─────────────────────────────────────────────────────────────
    # Orthogonal parent→children T's, grouped by the actual parent unit (a couple
    # draws ONE T to all its children; two non-coupled parents draw separate stems).
    # Each child's riser carries the bond's TRUTH: solid = biological, dashed =
    # step / adoptive / foster / guardian.
    edges = []
    groups = {}   # frozenset(parent members) -> {members, stem_x, p_bottom, kids:[(cid,cx)]}

    def group_for(members):
        key = frozenset(members)
        if key not in groups:
            xs = [coords[m][0] for m in members]
            groups[key] = {"members": list(members), "stem_x": sum(xs) / len(xs),
                           "p_bottom": coords[members[0]][2] + CARD_H, "kids": []}
        return groups[key]

    for cpk in pids:
        if cpk not in coords:
            continue
        pv = [pp for pp in parents.get(cpk, ())
              if pp in coords and gen.get(pp) == gen.get(cpk) - 1]
        if not pv:
            continue
        pair = None
        for i in range(len(pv)):
            for j in range(i + 1, len(pv)):
                if frozenset((pv[i], pv[j])) in couples:
                    pair = [pv[i], pv[j]]; break
            if pair:
                break
        if pair:
            group_for(pair)["kids"].append((cpk, coords[cpk][0]))
        else:
            for pp in pv:
                group_for([pp])["kids"].append((cpk, coords[cpk][0]))

    for grp in groups.values():
        members, stem_x = grp["members"], grp["stem_x"]
        p_bottom = grp["p_bottom"]
        kids = grp["kids"]
        bus_y = p_bottom + ROW_GAP / 2.0
        child_top = p_bottom + ROW_GAP
        kxs = [kx for _cid, kx in kids]
        xs = kxs + [stem_x]
        edges.append({"type": "link", "x1": round(stem_x), "y1": round(p_bottom),
                      "x2": round(stem_x), "y2": round(bus_y)})
        edges.append({"type": "link", "x1": round(min(xs)), "y1": round(bus_y),
                      "x2": round(max(xs)), "y2": round(bus_y)})
        for cid, kx in kids:
            dashed = any(link_style.get((m, cid)) == "dashed" for m in members)
            edges.append({"type": "link-dashed" if dashed else "link",
                          "x1": round(kx), "y1": round(bus_y),
                          "x2": round(kx), "y2": round(child_top)})

    for key, style in couples.items():
        a, b = tuple(key)
        if a in coords and b in coords and gen.get(a) == gen.get(b):
            edges.append({"type": "couple-" + style,
                          "x1": round(coords[a][0]), "y1": round(coords[a][1]),
                          "x2": round(coords[b][0]), "y2": round(coords[b][1])})

    # ── Generation labels (left gutter), numbered top → bottom ─────────────────
    gens_present = sorted(set(gen[p.pk] for p in people))
    self_focus = (focus_pk == me_pk)
    labels = []
    for i, gg in enumerate(gens_present):
        if gg < 0:
            title = "Parents"
        elif gg == 0:
            title = "You & Siblings" if self_focus else "Siblings"
        else:
            title = "Children"
        y = (gg - min_gen) * ROW_STRIDE
        labels.append({"num": i + 1, "title": title, "y": round(y),
                       "cy": round(y + CARD_H / 2.0)})

    height = (max(gen.values()) - min_gen + 1) * ROW_STRIDE - ROW_GAP if gen else 0
    return {"nodes": nodes, "edges": edges, "labels": labels, "gutter": GUTTER,
            "width": round(max_cx + CARD_W / 2.0),
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
    parents, children, spouses, _couples, _ls = _edges(user)

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
    parents, children, spouses, couples, link_style = _edges(user)
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
    rp, rc, rs, rcp, rls = _restrict((parents, children, spouses, couples, link_style), keep)
    graph = _layout(user, people, rp, rc, rs, rcp, rls, focus, me_pk)
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

    # Per-node inspector data — the "Details" panel for ANY card in the view, without
    # navigating (the tree stays put). Each person's relatives come from the FULL
    # graph, so the panel is complete even for people at the edge of the 3-gen window.
    def _rel_rows(ids):
        out = []
        for pk in sorted(ids):
            p = by_id.get(pk)
            if p:
                out.append({"id": pk, "name": p.display_name, "years": _life_years(p)})
        return out

    panels = {}
    for n in graph["nodes"]:
        pk = n["id"]
        p = by_id[pk]
        sibs = {k for par in parents.get(pk, ()) for k in children.get(par, ())
                if k != pk}
        panels[pk] = {
            "id": pk, "name": p.display_name, "initials": _initials(p.display_name),
            "photo": (p.primary_photo.file.url
                      if (p.primary_photo and p.primary_photo.file) else ""),
            "years": _life_years(p), "living": p.death_year is None,
            "rel": p.relationship_label or "", "is_self": pk == me_pk,
            "parents": _rel_rows(parents.get(pk, ())),
            "spouses": _rel_rows(spouses.get(pk, ())),
            "children": _rel_rows(children.get(pk, ())),
            "siblings": _rel_rows(sibs),
        }
    graph["panels"] = panels
    return graph


def build_family_graph(user):
    """Full-graph builder — retained for tests/tools (the page uses build_family_view)."""
    from apps.legacy.models import Person
    people = list(Person.objects.filter(user=user).select_related("primary_photo"))
    if not people:
        return {"nodes": [], "edges": [], "width": 0, "height": 0, "count": 0,
                "shown": 0, "me": None, "focus": None, "focus_x": 0, "focus_y": 0}
    parents, children, spouses, couples, link_style = _edges(user)
    me_pk = _resolve_self(user, people)
    focus = me_pk or people[0].pk
    g = _layout(user, people, parents, children, spouses, couples, link_style, focus, me_pk)
    g["count"] = len(people)
    g["me_x"], g["me_y"] = g["focus_x"], g["focus_y"]
    return g


# ── Relationships browser (canonical, person-centric) ────────────────────────
# Category → display label for the Relationships hub sections (non-family).
CATEGORY_LABELS = {
    "social": "Friends", "professional": "Professional", "faith": "Faith",
    "education": "Education", "military": "Military & service",
    "community": "Neighbors & community", "medical": "Care", "other": "Other",
    "unknown": "Other",
}


_SIBLING_KW = ("sibling", "brother", "sister")


def _child_role(sex):
    s = (sex or "").upper()
    return "Son" if s.startswith("M") else "Daughter" if s.startswith("F") else "Child"


def browse_person_relationships(user, focal_id=None):
    """The canonical, person-centric relationship browser behind the Relationships
    page: the ACTUAL relationship records that touch one focal person, oriented from
    their point of view and grouped by role (Parents, Spouse, Siblings, Children,
    then Friends/Professional/…). The displayed role is the relationship's OWN type
    (Biological father, Stepmother, Guardian…) via `type_label` — never flattened to
    'Parent'. The visualization reflects Canonical Truth; it never reinterprets it.
    Defaults the focus to the keeper. Siblings are also derived from shared parents."""
    from django.db.models import Q

    from apps.legacy.models import Person, Relationship

    people = list(Person.objects.filter(user=user).only(
        "pk", "display_name", "birth_year", "death_year", "relationship_label", "is_self"))
    if not people:
        return None
    by_id = {p.pk: p for p in people}
    me_pk = _resolve_self(user, people)

    try:
        focal_id = int(focal_id) if focal_id else None
    except (TypeError, ValueError):
        focal_id = None
    if focal_id not in by_id:
        focal_id = me_pk or people[0].pk
    focal = by_id[focal_id]

    rels = list(Relationship.objects.filter(user=user)
                .filter(Q(from_person_id=focal_id) | Q(to_person_id=focal_id))
                .select_related("from_person", "to_person"))

    groups = {}   # key -> {label, order, items}

    def add(key, order, label, other, role, pk):
        g = groups.setdefault(key, {"label": label, "order": order, "items": []})
        g["items"].append({"id": other.pk, "name": other.display_name,
                           "years": _life_years(other), "role": role, "pk": pk})

    parent_ids = set()
    stored_sibs = set()
    for r in rels:
        outgoing = r.from_person_id == focal_id
        other = r.to_person if outgoing else r.from_person
        if other.pk == focal_id:
            continue
        t = (r.relationship_type or "").lower()
        label = r.type_label     # Canonical Truth — the relationship's OWN label
        if any(k in t for k in _COUPLE):
            style = _couple_style(t)
            if style == "former":
                add("former", 25, "Former spouse", other, label, r.pk)
            elif style in ("partner", "affair"):
                add("partner", 22, "Partner", other, label, r.pk)
            else:
                add("spouse", 20, "Spouse", other, label, r.pk)
        elif any(k in t for k in _SIBLING_KW):
            add("siblings", 30, "Siblings", other, label, r.pk)
            stored_sibs.add(other.pk)
        elif any(k in t for k in _PARENT_OF):
            if outgoing:                       # focal is the parent → other is the child
                add("children", 40, "Children", other, _child_role(other.sex), r.pk)
            else:                              # other is focal's parent → its exact type
                add("parents", 10, "Parents", other, label, r.pk)
                parent_ids.add(other.pk)
        elif any(k in t for k in _CHILD_OF):
            if outgoing:                       # focal is other's child → other is a parent
                add("parents", 10, "Parents", other, "Parent", r.pk)
                parent_ids.add(other.pk)
            else:                              # other is focal's child
                add("children", 40, "Children", other, _child_role(other.sex), r.pk)
        else:
            cat = r.relationship_category or "other"
            add("cat_" + cat, 60, CATEGORY_LABELS.get(cat, "Other"), other, label, r.pk)

    # Siblings — also derived from shared parents (inferred, not stored). Matches any
    # parent-type ('father of', 'stepmother of', …), and skips anyone already recorded
    # as an explicit sibling relationship.
    if parent_ids:
        sib = set()
        for r in (Relationship.objects.filter(user=user, from_person_id__in=parent_ids)
                  .select_related("to_person")):
            tt = (r.relationship_type or "").lower()
            if r.to_person_id != focal_id and any(k in tt for k in _PARENT_OF):
                sib.add(r.to_person_id)
        for sid in sorted(sib - stored_sibs):
            p = by_id.get(sid)
            if p:
                add("siblings", 30, "Siblings", p, "Sibling", None)

    ordered = sorted(groups.values(), key=lambda g: (g["order"], g["label"]))
    return {
        "focal": {"id": focal_id, "name": focal.display_name,
                  "years": _life_years(focal), "is_self": focal_id == me_pk,
                  "initials": _initials(focal.display_name)},
        "groups": ordered,
        "count": len(rels),
    }
