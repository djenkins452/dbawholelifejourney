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
    step_pairs = set()   # (parent_id, child_id) where the parent is a STEP-parent
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
            if "step" in typ:
                step_pairs.add((f, t))
        elif role == "child":
            children[t].add(f); parents[f].add(t)
            link_style[(t, f)] = _link_style(typ)
            if "step" in typ:
                step_pairs.add((t, f))
        else:
            spouses[f].add(t); spouses[t].add(f)
            couples[frozenset((f, t))] = _couple_style(typ)
    return parents, children, spouses, couples, link_style, step_pairs


def _neighborhood(focus, parents, children, spouses):
    """The immediate family around the focus — exactly three generations, rendered as
    FAMILY UNITS (each blood relative paired with their spouse):

      • the focus's parents (and each parent's spouse → step-parents),
      • the focus + spouse(s), and the focus's siblings + their spouses,
      • the focus's children + their spouses.

    In-law spouses are included ONLY so siblings/children render as couples (the way a
    person reads a family). Deliberately NOT included: grandparents, grandchildren,
    aunts/uncles, cousins, nieces/nephews. Those appear only when that person becomes
    the focus. This is what keeps the tree readable at a glance."""
    keep = {focus}
    par = set(parents.get(focus, set()))
    keep |= par
    sibs_and_half = set()
    for p in par:
        keep |= spouses.get(p, set())            # step-parents / a parent's other spouses
        sibs_and_half |= children.get(p, set())  # full siblings AND half-siblings
    sibs_and_half.discard(focus)
    keep |= sibs_and_half
    for sib in sibs_and_half:                     # a half-sibling's OTHER parent forms the
        keep |= parents.get(sib, set())           #   couple that produced them (Donald…)
        keep |= spouses.get(sib, set())           # and their spouse (couple pairing)
    keep |= spouses.get(focus, set())            # the focus's own spouse(s)
    keep |= children.get(focus, set())           # the focus's children
    for kid in children.get(focus, set()):       # children's spouses (couple pairing)
        keep |= spouses.get(kid, set())
    return keep


def _restrict(edges, keep):
    parents, children, spouses, couples, link_style, step_pairs = edges
    keep = set(keep)

    def r(d):
        out = defaultdict(set)
        for k in keep:
            out[k] = {v for v in d.get(k, set()) if v in keep}
        return out

    cp = {k: v for k, v in couples.items() if k <= keep}
    ls = {(a, b): v for (a, b), v in link_style.items() if a in keep and b in keep}
    sp = {(a, b) for (a, b) in step_pairs if a in keep and b in keep}
    return r(parents), r(children), r(spouses), cp, ls, sp


def _layout(user, people, parents, children, spouses, couples, link_style,
            step_pairs, focus_pk, me_pk):
    """Family-UNIT pedigree renderer. The PRIMARY object is a FAMILY UNIT — a couple and
    the children THEY had together — never a parent or a person.

    Children belong to the unit that produced them, so a parent with children by several
    partners yields several units (Marvin+Barbara → Danny & full sibs; Donald+Barbara →
    half-sibs; …), each its own sibling cluster. The focus's own unit is centred; the
    other units of each of the focus's parents flank on that parent's side, joined back
    to the shared parent by a couple line ("connected through Barbara"). Real parents sit
    over the middle of THEIR children; children descend from the couple's centre.
    Relationship types render exactly as Canonical Truth records them (solid =
    biological / married, dashed = step / adoptive / former)."""
    from collections import defaultdict

    from apps.legacy.models import RelationshipAlias

    P = {p.pk: p for p in people}
    pids = set(P)
    if focus_pk not in pids:
        focus_pk = next(iter(pids)) if pids else None
    if not pids:
        return {"nodes": [], "edges": [], "labels": [], "gutter": GUTTER,
                "width": 0, "height": 0, "shown": 0, "focus": None,
                "focus_x": 0, "focus_y": 0, "me": me_pk}
    F = focus_pk

    def bkey(pk):
        return (P[pk].birth_year or 9999, P[pk].display_name or "")

    def inp(ids):
        return [i for i in ids if i in pids]

    def sex_order(pk):
        return (0 if (P[pk].sex or "").upper().startswith("M") else 1, bkey(pk))

    UNIT_STEP = CARD_W + UNIT_GAP           # gap between adjacent couples in one cluster
    CLUSTER_GAP = CARD_W + UNIT_GAP * 2     # wider gap between distinct family-unit clusters

    def lineage_parents(c):
        return frozenset(q for q in parents.get(c, ())
                         if q in pids and (q, c) not in step_pairs)

    # ── Roles + family units ────────────────────────────────────────────────────
    f_spouses = sorted(inp(spouses.get(F, ())), key=bkey)
    f_children = sorted(inp(children.get(F, ())), key=bkey)
    f_parents = inp(parents.get(F, ()))
    real_parents = [p for p in f_parents if (p, F) not in step_pairs]
    bio = sorted(real_parents, key=sex_order)

    # A unit = a distinct lineage parent-SET → the children with exactly that parent-set.
    unit_kids = defaultdict(set)
    for p in real_parents:
        for c in children.get(p, ()):
            if c in pids:
                unit_kids[lineage_parents(c)].add(c)
    focus_key = lineage_parents(F) or frozenset(real_parents)
    unit_kids.setdefault(focus_key, set()).add(F)
    unit_kids = {k: sorted(v, key=bkey) for k, v in unit_kids.items()}

    taken = set()

    def couple_units(blood_list, first=None, first_spouses=None):
        """Turn a list of blood relatives into couple-units [blood, spouse?]."""
        out = []
        for b in blood_list:
            if b == first and first_spouses is not None:
                for s in first_spouses:
                    taken.add(s)
                out.append([b] + list(first_spouses))
            else:
                members = [b]
                for s in sorted([s for s in spouses.get(b, ())
                                 if s in pids and s not in taken and s != b], key=bkey):
                    members.append(s)
                    taken.add(s)
                    break
                out.append(members)
        return out

    def place_units(units):
        """x-centres along a strip; couples kept tight, units UNIT_GAP apart; leftmost 0."""
        pos, x = {}, None
        for members in units:
            for mi, m in enumerate(members):
                x = 0.0 if x is None else x + CARD_W + (COUPLE_GAP if mi else UNIT_GAP)
                pos[m] = x
        return pos

    row1, cluster_cx = {}, {}

    # Focus cluster (Danny + full siblings), centred on the focus.
    focus_units = couple_units(unit_kids[focus_key], first=F, first_spouses=f_spouses)
    fpos = place_units(focus_units)
    fshift = -fpos[F]
    for m in fpos:
        row1[m] = fpos[m] + fshift
    cluster_cx[focus_key] = (sum(row1[c] for c in unit_kids[focus_key])
                             / len(unit_kids[focus_key]))

    # Other units flank on their shared parent's side (left parent → left, right → right).
    left_pivot = bio[0] if bio else None
    right_pivot = bio[1] if len(bio) > 1 else None

    def unit_pivot(k):
        inter = [p for p in bio if p in k]
        return inter[0] if inter else None

    others = [k for k in unit_kids if k != focus_key]
    left_units = sorted([k for k in others if unit_pivot(k) == left_pivot and left_pivot],
                        key=lambda kk: min(bkey(c) for c in unit_kids[kk]))
    right_units = sorted([k for k in others if unit_pivot(k) != left_pivot],
                         key=lambda kk: min(bkey(c) for c in unit_kids[kk]))

    fc_min = min(row1.values()) - CARD_W / 2.0
    fc_max = max(row1.values()) + CARD_W / 2.0
    right_cursor = fc_max + CLUSTER_GAP
    for k in right_units:
        upos = place_units(couple_units(unit_kids[k]))
        sh = right_cursor + CARD_W / 2.0 - min(upos.values())
        for m in upos:
            row1[m] = upos[m] + sh
        cluster_cx[k] = sum(row1[c] for c in unit_kids[k]) / len(unit_kids[k])
        right_cursor = max(row1[m] for m in upos) + CARD_W / 2.0 + CLUSTER_GAP
    left_cursor = fc_min - CLUSTER_GAP
    for k in left_units:
        upos = place_units(couple_units(unit_kids[k]))
        sh = left_cursor - CARD_W / 2.0 - max(upos.values())
        for m in upos:
            row1[m] = upos[m] + sh
        cluster_cx[k] = sum(row1[c] for c in unit_kids[k]) / len(unit_kids[k])
        left_cursor = min(row1[m] for m in upos) - CARD_W / 2.0 - CLUSTER_GAP

    # ── Parents row (gen −1): each unit's couple over ITS cluster; steps flank ─────
    row0 = {}
    fcc = cluster_cx[focus_key]
    if len(bio) >= 2:
        row0[bio[0]] = fcc - COUPLE_HALF
        row0[bio[1]] = fcc + COUPLE_HALF
    elif len(bio) == 1:
        row0[bio[0]] = fcc
    # each other unit: its OUTER parent sits over that unit's cluster (pivot already placed)
    for k in others:
        outer = sorted([q for q in k if q not in real_parents], key=sex_order)
        base = cluster_cx[k]
        for i, q in enumerate(outer):
            row0.setdefault(q, base + (i - (len(outer) - 1) / 2.0) * UNIT_STEP)
    # a real parent's remaining spouses with no children shown (e.g. a step-parent) flank
    left_x = min(row0.values()) if row0 else fcc
    right_x = max(row0.values()) if row0 else fcc
    extras = set()
    for p in real_parents:                       # a real parent's other spouses
        extras |= {s for s in spouses.get(p, ()) if s in pids and s not in row0}
    for sp, c in step_pairs:                      # step-parents of anyone on the focus row
        if sp in pids and sp not in row0 and c in row1:
            extras.add(sp)
    for sp in sorted(extras, key=bkey):
        if sp in row0:
            continue
        partner = next((p for p in real_parents
                        if sp in spouses.get(p, ()) and p in row0), None)
        if partner is not None and row0[partner] <= fcc:
            left_x -= UNIT_STEP
            row0[sp] = left_x
        else:
            right_x += UNIT_STEP
            row0[sp] = right_x

    # ── Children row (gen +1): the focus's children under the focus couple ─────────
    ctaken = set()
    child_units = []
    for c in f_children:
        members = [c]
        for s in sorted([s for s in spouses.get(c, ())
                         if s in pids and s not in ctaken and s != c], key=bkey):
            members.append(s)
            ctaken.add(s)
            break
        child_units.append(members)
    row2 = place_units(child_units)
    focus_couple = [F] + f_spouses
    focus_cx = sum(row1[m] for m in focus_couple) / len(focus_couple)
    if row2:
        cshift = focus_cx - (min(row2.values()) + max(row2.values())) / 2.0
        for m in row2:
            row2[m] += cshift

    # ── Merge → centre + row index ─────────────────────────────────────────────
    center, row = {}, {}
    for m, x in row0.items():
        center[m], row[m] = x, 0
    for m, x in row1.items():
        center[m], row[m] = x, 1
    for m, x in row2.items():
        center[m], row[m] = x, 2
    for p in people:
        center.setdefault(p.pk, row1.get(F, 0.0))
        row.setdefault(p.pk, 1)

    min_center = min(center.values())
    off_x = GUTTER + CARD_W / 2.0 - min_center
    rows_present = sorted(set(row.values()))
    min_row = rows_present[0]

    aliases = defaultdict(list)
    for a in RelationshipAlias.objects.filter(
            user=user, person_id__in=pids).exclude(person__isnull=True):
        aliases[a.person_id].append(a.label)

    coords, nodes, fx, fy, max_cx = {}, [], 0, 0, 0
    for p in people:
        cx = center[p.pk] + off_x
        y = (row[p.pk] - min_row) * ROW_STRIDE
        cy = y + CARD_H / 2.0
        coords[p.pk] = (cx, cy, y)
        max_cx = max(max_cx, cx)
        search = " ".join([p.display_name, p.also_known_as or ""]
                          + aliases.get(p.pk, [])).lower()
        nodes.append({
            "id": p.pk, "name": p.display_name, "initials": _initials(p.display_name),
            "photo": (p.primary_photo.file.url
                      if (p.primary_photo and p.primary_photo.file) else ""),
            "sex": (p.sex or "").upper()[:1],
            "birth": p.birth_year, "death": p.death_year,
            "birth_display": p.display_birth, "death_display": p.display_death,
            "living": p.death_year is None, "rel": p.relationship_label,
            "x": round(cx - CARD_W / 2.0), "y": round(y), "cx": round(cx), "cy": round(cy),
            "search": search, "is_self": p.pk == me_pk, "is_focus": p.pk == focus_pk,
        })
        if p.pk == focus_pk:
            fx, fy = cx, cy

    # ── Connectors ─────────────────────────────────────────────────────────────
    edges = []

    def child_style(child, parent_ids):
        styles = [link_style.get((pp, child)) for pp in parent_ids
                  if (pp, child) in link_style]
        return "dashed" if styles and all(s == "dashed" for s in styles) else "solid"

    def draw_T(stem_xs, parent_row, child_list, child_row, base="link"):
        """A family-unit connector: a stem drops from EACH parent to a shared bus, the
        bus spans the children, a riser rises to each child (typed by Canonical Truth).
        Dropping a stem from every parent is what visibly connects a shared parent
        (Barbara) to each of her family units."""
        if not child_list:
            return
        stem_xs = list(stem_xs)
        p_bottom = (parent_row - min_row) * ROW_STRIDE + CARD_H
        child_top = (child_row - min_row) * ROW_STRIDE
        bus_y = p_bottom + ROW_GAP / 2.0
        xs = [cx for cx, _ in child_list] + stem_xs
        for sx in stem_xs:
            edges.append({"type": base, "x1": round(sx), "y1": round(p_bottom),
                          "x2": round(sx), "y2": round(bus_y)})
        edges.append({"type": base, "x1": round(min(xs)), "y1": round(bus_y),
                      "x2": round(max(xs)), "y2": round(bus_y)})
        for cx, style in child_list:
            edges.append({"type": "link-dashed" if style == "dashed" else "link",
                          "x1": round(cx), "y1": round(bus_y),
                          "x2": round(cx), "y2": round(child_top)})

    # One connector per family UNIT — from the parents that produced it to its children.
    for k, kids in unit_kids.items():
        placed = [c for c in kids if c in coords]
        if not placed:
            continue
        stem_parents = [q for q in (bio if k == focus_key else k) if q in coords]
        if not stem_parents:
            continue
        draw_T([coords[q][0] for q in stem_parents], 0,
               [(coords[c][0], child_style(c, k)) for c in placed], 1)

    # Focus couple → the focus's own children
    if f_children:
        draw_T([coords[m][0] for m in focus_couple if m in coords], 1,
               [(coords[c][0], child_style(c, focus_couple))
                for c in f_children if c in coords], 2)

    # A standalone step-parent's bond (not conveyed by a couple line) → dashed
    for sp, c in step_pairs:
        if sp in coords and c in coords and row.get(sp) == 0 and row.get(c) == 1:
            paired = any(frozenset((sp, rp)) in couples for rp in parents.get(c, ())
                         if (rp, c) not in step_pairs and rp in coords)
            if not paired:
                draw_T([coords[sp][0]], 0, [(coords[c][0], "dashed")], 1, base="link-dashed")

    # Couple connectors (typed) — spouses joined by a horizontal line
    for key, style in couples.items():
        a, b = tuple(key)
        if a in coords and b in coords and row.get(a) == row.get(b):
            edges.append({"type": "couple-" + style,
                          "x1": round(coords[a][0]), "y1": round(coords[a][1]),
                          "x2": round(coords[b][0]), "y2": round(coords[b][1])})

    # ── Generation labels (left gutter), Ancestry-style by the focus's name ─────
    self_focus = (focus_pk == me_pk)
    fp = P.get(focus_pk)
    first = (fp.display_name.split()[0] if fp else "This person")
    whose = "Your" if self_focus else "%s's" % first
    title_for = {0: "%s parents" % whose,
                 1: "You & siblings" if self_focus else "%s & siblings" % first,
                 2: "%s children" % whose}
    labels = []
    for i, rr in enumerate(rows_present):
        y = (rr - min_row) * ROW_STRIDE
        labels.append({"num": i + 1, "title": title_for.get(rr, ""),
                       "y": round(y), "cy": round(y + CARD_H / 2.0)})

    height = (rows_present[-1] - min_row + 1) * ROW_STRIDE - ROW_GAP if rows_present else 0
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
    parents, children, spouses, _couples, _ls, _sp = _edges(user)

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
        "birth_date", "death_date", "relationship_label", "primary_photo", "sex",
    ).select_related("primary_photo"))
    total = len(all_people)
    if not all_people:
        return {"nodes": [], "edges": [], "width": 0, "height": 0, "shown": 0,
                "count": 0, "focus": None, "focus_x": 0, "focus_y": 0, "me": None}

    by_id = {p.pk: p for p in all_people}
    parents, children, spouses, couples, link_style, step_pairs = _edges(user)
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
    rp, rc, rs, rcp, rls, rsp = _restrict((parents, children, spouses, couples, link_style, step_pairs), keep)
    graph = _layout(user, people, rp, rc, rs, rcp, rls, rsp, focus, me_pk)
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
    parents, children, spouses, couples, link_style, step_pairs = _edges(user)
    me_pk = _resolve_self(user, people)
    focus = me_pk or people[0].pk
    g = _layout(user, people, parents, children, spouses, couples, link_style, step_pairs, focus, me_pk)
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
