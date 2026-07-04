"""
GEDCOM parser — structured genealogy stays structured.

A GEDCOM file is a structured knowledge source, not prose. This parser reads the
INDI (individual) and FAM (family) records straight into PRE-CLASSIFIED import
chunks — people and families routed to their own genealogy review queues, never
flattened into stories. It is deterministic and dependency-free (GEDCOM is a
simple level/tag line format), so it needs no OpenAI classification pass.

`looks_like_gedcom()` lets the ONE importer auto-detect a genealogy file even if
the user didn't say so — they just uploaded "their life"; Legacy recognizes it.
"""

import re

_LINE = re.compile(r"^\s*(\d+)\s+(?:(@[^@]+@)\s+)?(\S+)(?:\s+(.*))?$")


def looks_like_gedcom(raw):
    """True when the raw text is a GEDCOM genealogy file."""
    head = (raw or "")[:2000]
    if "0 HEAD" not in head and not re.search(r"^\s*0\s+HEAD", head, re.M):
        return False
    return bool(re.search(r"\b(INDI|GEDC)\b", head)) or "0 @" in head


def _parse_records(raw):
    """Build the level-0 records as nested {tag, xref, value, children} trees."""
    records, stack = [], []
    for line in (raw or "").splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        level = int(m.group(1))
        node = {"tag": m.group(3), "xref": m.group(2), "value": (m.group(4) or "").strip(),
                "children": []}
        if level == 0:
            records.append(node)
            stack = [(0, node)]
            continue
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        stack.append((level, node))
    return records


def _child(node, tag):
    for c in node["children"]:
        if c["tag"] == tag:
            return c
    return None


def _val(node, tag):
    c = _child(node, tag)
    return c["value"] if c else ""


def _full_text(node):
    """Reassemble a value across GEDCOM CONT (new line) / CONC (concatenation)."""
    if not node:
        return ""
    out = node["value"]
    for c in node["children"]:
        if c["tag"] == "CONT":
            out += "\n" + c["value"]
        elif c["tag"] == "CONC":
            out += c["value"]
    return out.strip()


def _notes(node):
    """All narrative NOTE text on a record, joined."""
    parts = [_full_text(c) for c in node["children"] if c["tag"] == "NOTE"]
    return "\n\n".join(p for p in parts if p).strip()


# A NOTE longer than this is narrative free-text — it goes through Discovery as its
# own unit rather than being pinned to the structured record.
_NOTE_NARRATIVE_MIN = 140


def _event(node, tag):
    """A BIRT/DEAT/MARR sub-record → (date, place)."""
    e = _child(node, tag)
    if not e:
        return "", ""
    return _val(e, "DATE"), _val(e, "PLAC")


# A GEDCOM FAM record defines a family UNIT — a husband, a wife, their children. It
# does NOT by itself mean the couple married. Rather than treating every missing MARR
# tag as identical, the importer reasons about CONFIDENCE, since genealogy sources are
# often incomplete:
#   known   — explicit marriage/divorce evidence           → recorded as married/former
#   likely  — a family unit with several shared children    → surfaced for confirmation,
#             but no marriage event                            NOT asserted as married
#   (none)  — a single shared child / no support            → parent-child only
_MARRIAGE_TAGS = ("MARR", "MARB", "MARC", "MARL", "MARS")   # marriage / banns / contract / licence / settlement
_FORMER_TAGS = ("DIV", "DIVF", "ANUL")                       # divorce / annulment ⇒ they WERE married
_LIKELY_MIN_CHILDREN = 2     # a lasting family unit — enough to suggest, never to assert


def _marriage_bond(rec):
    """The couple's bond from a FAM record as (couple_type, confidence):
      ('former',  'known')  — divorce / annulment evidence (they were married)
      ('married', 'known')  — explicit marriage evidence
      ('married', 'likely') — no marriage event, but >= 2 shared children (suggest only)
      (None,      None)     — no evidence and too little signal → not a couple
    """
    tags = {c["tag"] for c in rec["children"]}
    if tags & set(_FORMER_TAGS):
        return "former", "known"
    if tags & set(_MARRIAGE_TAGS):
        return "married", "known"
    n_children = sum(1 for c in rec["children"] if c["tag"] == "CHIL")
    if n_children >= _LIKELY_MIN_CHILDREN:
        return "married", "likely"
    return None, None


def _clean_name(node):
    raw = _val(node, "NAME")
    if not raw:
        given = _val(_child(node, "NAME") or node, "GIVN")
        surn = _val(_child(node, "NAME") or node, "SURN")
        raw = ("%s %s" % (given, surn)).strip()
    name = raw.replace("/", " ").strip()
    name = re.sub(r"\s+", " ", name)
    return name or "Unknown person"


def _year(date_str):
    """The 4-digit year from a GEDCOM date ('3 MAR 1945' → 1945), or None."""
    m = re.search(r"\b(\d{4})\b", date_str or "")
    return int(m.group(1)) if m else None


_GED_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
               "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def _full_date(date_str):
    """ISO string ('1971-03-29') for a GEDCOM date that gives day + month + year,
    else None. Approximate/partial dates (ABT, BEF, month-only, year-only) return
    None here — the year is still preserved separately via `_year`."""
    from datetime import date
    up = (date_str or "").upper()
    ym = re.search(r"\b(\d{4})\b", up)
    mm = re.search(r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", up)
    dm = re.search(r"\b(\d{1,2})\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", up)
    if ym and mm and dm:
        try:
            return date(int(ym.group(1)), _GED_MONTHS[mm.group(1)], int(dm.group(1))).isoformat()
        except ValueError:
            return None
    return None


def dates_from_body(body):
    """Recover (birth_iso, death_iso) from a gedcom_person chunk's rendered body
    ("… Born 3 MAR 1945 in …· Died 12 DEC 2010 …") — used to backfill full dates
    onto people imported before structured dates were captured."""
    b = d = None
    mb = re.search(r"Born\s+([^·\n]+)", body or "")
    if mb:
        b = _full_date(mb.group(1))
    md = re.search(r"Died\s+([^·\n]+)", body or "")
    if md:
        d = _full_date(md.group(1))
    return b, d


def _when_where(date, place, verb):
    if not date and not place:
        return ""
    parts = [verb]
    if date:
        parts.append(date)
    if place:
        parts.append("in " + place)
    return " ".join(parts)


# Tags handled structurally elsewhere (not preserved as standalone "facts").
_STRUCTURAL = {"NAME", "GIVN", "SURN", "SEX", "HUSB", "WIFE", "CHIL", "FAMS",
               "FAMC", "CONT", "CONC", "TRLR", "HEAD"}


def _facts(rec):
    """EVERY child tag preserved as a fact (tag, value, date, place). Nothing is
    discarded — including tags Legacy can't yet store and custom (_XXXX) tags. This
    is the preservation guarantee: the raw fact stays in the import session until a
    canonical destination exists."""
    out = []
    for c in rec["children"]:
        tag = c["tag"]
        if tag in ("CONT", "CONC"):
            continue
        val = _full_text(c)
        date = _val(c, "DATE")
        place = _val(c, "PLAC")
        if not (val or date or place or c["children"]):
            continue
        out.append({"tag": tag, "value": val[:2000], "date": date, "place": place})
    return out


# GEDCOM tag → (status, granular label, canonical CONCEPT). status is one of:
#   'supported'      — Legacy has a canonical home for it today
#   'needs_support'  — recognized, no destination yet → preserved permanently + reported
#   'structural'     — used to build People/Relationships, not a standalone fact
# The CONCEPT is deliberately conceptual, not structural: Occupation → Career,
# Residence → Places, Burial → Life Events, Baptism → Faith Journey. It IS the
# roadmap bucket and the recommended canonical domain.
GEDCOM_COVERAGE = {
    "BIRT": ("supported", "Births", "Births"),
    "DEAT": ("supported", "Deaths", "Deaths"),
    "MARR": ("supported", "Marriages", "Marriages"),
    "NOTE": ("supported", "Notes", "Notes"),
    "OBJE": ("supported", "Media references", "Media"),
    "SEX": ("structural", "Sex", None),
    "NAME": ("structural", "Name", None),
    # Recognized, no canonical home yet — preserved permanently, grouped by concept:
    "OCCU": ("needs_support", "Occupation", "Career"),
    "RETI": ("needs_support", "Retirement", "Career"),
    "EDUC": ("needs_support", "Education", "Education"),
    "GRAD": ("needs_support", "Graduation", "Education"),
    "RELI": ("needs_support", "Religion", "Faith Journey"),
    "BAPM": ("needs_support", "Baptism", "Faith Journey"),
    "CHR": ("needs_support", "Christening", "Faith Journey"),
    "CONF": ("needs_support", "Confirmation", "Faith Journey"),
    "ORDN": ("needs_support", "Ordination", "Faith Journey"),
    "BURI": ("needs_support", "Burial", "Life Events"),
    "CREM": ("needs_support", "Cremation", "Life Events"),
    "PROB": ("needs_support", "Probate", "Life Events"),
    "WILL": ("needs_support", "Will", "Life Events"),
    "EVEN": ("needs_support", "Life event", "Life Events"),
    "FACT": ("needs_support", "Personal fact", "Life Events"),
    "CENS": ("needs_support", "Census record", "Life Events"),
    "IMMI": ("needs_support", "Immigration", "Immigration"),
    "EMIG": ("needs_support", "Emigration", "Immigration"),
    "NATU": ("needs_support", "Naturalization", "Immigration"),
    "RESI": ("needs_support", "Residence", "Places"),
    "PROP": ("needs_support", "Property", "Places"),
    "ADDR": ("needs_support", "Address", "Contact"),
    "PHON": ("needs_support", "Phone", "Contact"),
    "EMAIL": ("needs_support", "Email", "Contact"),
    "WWW": ("needs_support", "Website", "Contact"),
    "TITL": ("needs_support", "Title / honorific", "Titles & Honors"),
    "SOUR": ("needs_support", "Source citation", "Sources & Citations"),
    "REPO": ("needs_support", "Repository", "Sources & Citations"),
    "DIV": ("needs_support", "Divorce", "Relationships"),
}

# Where custom / unrecognized tags are preserved on the roadmap.
UNKNOWN_CONCEPT = "Custom Tags"


def classify_fact(tag):
    """Map a raw GEDCOM tag to (status, granular label, canonical concept). Any tag
    Legacy doesn't recognize — including custom `_XXXX` tags — is preserved under the
    'Custom Tags' concept, never dropped."""
    info = GEDCOM_COVERAGE.get(tag)
    if info is not None:
        return info
    return ("unknown", tag, UNKNOWN_CONCEPT)


def analyze_coverage(chunks):
    """A completeness report over parsed chunks: what Legacy preserved into
    Canonical Truth, what it preserved but has no home for yet (grouped by concept),
    and what it didn't recognize. Nothing is ever dropped — this is the audit that
    proves it, and the same concepts drive the Canonical Truth Roadmap."""
    from collections import Counter
    people = sum(1 for c in chunks if c.get("kind") == "gedcom_person")
    families = sum(1 for c in chunks if c.get("kind") == "gedcom_family")
    tags = Counter()
    for ch in chunks:
        for f in (ch.get("data") or {}).get("facts", []):
            tags[f["tag"]] += 1

    supported = {}
    needs = {}
    unknown = {}
    for tag, n in tags.items():
        status, label, concept = classify_fact(tag)
        if status == "structural":
            continue
        elif status == "supported":
            supported[concept] = supported.get(concept, 0) + n
        elif status == "unknown":
            unknown[tag] = unknown.get(tag, 0) + n         # custom (_XXXX) / unrecognized
        else:
            e = needs.setdefault(concept, {"concept": concept, "count": 0, "labels": set()})
            e["count"] += n
            e["labels"].add(label)

    supported_list = ([{"concept": "People", "count": people}] if people else [])
    supported_list += ([{"concept": "Families & relationships", "count": families}] if families else [])
    supported_list += [{"concept": c, "count": n} for c, n in sorted(supported.items())]
    needs_list = [{"concept": e["concept"], "count": e["count"],
                   "labels": sorted(e["labels"])}
                  for e in needs.values()]
    return {
        "supported": supported_list,
        "needs_support": sorted(needs_list, key=lambda x: (-x["count"], x["concept"])),
        "unknown": [{"tag": t, "count": n} for t, n in sorted(unknown.items())],
        "preserved_total": int(sum(tags.values())) + people + families,
    }


def parse_gedcom(raw):
    """Parse GEDCOM text into pre-classified import chunks (people + families).
    Each chunk carries its own `kind` so it skips AI classification and lands in
    the right genealogy queue. EVERY fact on a record is preserved in `data.facts`
    even when Legacy has no canonical home for it yet. Returns a list of chunk dicts."""
    records = _parse_records(raw)
    names = {}   # xref -> display name
    indis, fams = [], []
    for rec in records:
        if rec["tag"] == "INDI":
            indis.append(rec)
            if rec["xref"]:
                names[rec["xref"]] = _clean_name(rec)
        elif rec["tag"] == "FAM":
            fams.append(rec)

    chunks = []
    idx = 0
    # Narrative NOTEs are collected as SEPARATE, un-kinded units so they flow
    # through Discovery (a note may be a story, a fact, a quote). Structured
    # genealogy stays deterministic and never touches Discovery.
    note_chunks = []

    def _emit_note(text, about):
        note_chunks.append({
            "title": ("Note about %s" % about)[:255],
            "body": text,
            "source_ref": "note",
            # No `kind` → classified as prose, then Discovery where appropriate.
        })

    for rec in indis:
        name = _clean_name(rec)
        sex = {"M": "Male", "F": "Female"}.get(_val(rec, "SEX").upper(), "")
        bdate, bplace = _event(rec, "BIRT")
        ddate, dplace = _event(rec, "DEAT")
        lines = []
        life = " · ".join(x for x in (
            sex, _when_where(bdate, bplace, "Born"), _when_where(ddate, dplace, "Died")) if x)
        if life:
            lines.append(life)
        note = _notes(rec)
        if note and len(note) < _NOTE_NARRATIVE_MIN:
            lines.append(note)              # short note stays with the structured record
        elif note:
            _emit_note(note, name)          # narrative note → its own Discovery unit
        idx += 1
        chunks.append({
            "index": idx, "title": name[:255],
            "body": "\n".join(lines) or name,
            "source_ref": (rec["xref"] or "individual").strip("@"),
            "kind": "gedcom_person", "confidence": "high",
            "data": {
                "xref": rec["xref"] or "", "name": name, "sex": _val(rec, "SEX").upper(),
                "birth_year": _year(bdate), "death_year": _year(ddate),
                "birth_date": _full_date(bdate), "death_date": _full_date(ddate),
                "birth_place": bplace, "death_place": dplace,
                "facts": _facts(rec),
            },
        })

    for rec in fams:
        husb = names.get(_val(rec, "HUSB"), "")
        wife = names.get(_val(rec, "WIFE"), "")
        children = [names.get(c["value"], "") for c in rec["children"] if c["tag"] == "CHIL"]
        children = [c for c in children if c]
        mdate, mplace = _event(rec, "MARR")
        couple_type, couple_confidence = _marriage_bond(rec)
        pair = " & ".join(x for x in (husb, wife) if x) or "Family"
        lines = []
        marr = _when_where(mdate, mplace, "Married")
        if marr:
            lines.append(marr)
        if children:
            lines.append("Children: " + ", ".join(children))
        note = _notes(rec)
        if note and len(note) < _NOTE_NARRATIVE_MIN:
            lines.append(note)
        elif note:
            _emit_note(note, pair)
        idx += 1
        chunks.append({
            "index": idx, "title": pair[:255],
            "body": "\n".join(lines) or pair,
            "source_ref": (rec["xref"] or "family").strip("@"),
            "kind": "gedcom_family", "confidence": "high",
            "data": {
                "husb": _val(rec, "HUSB"), "wife": _val(rec, "WIFE"),
                "children": [c["value"] for c in rec["children"] if c["tag"] == "CHIL"],
                "marriage_year": _year(mdate), "marriage_date": _full_date(mdate),
                "marriage_place": mplace,
                "couple_type": couple_type,
                "couple_confidence": couple_confidence,
                "facts": _facts(rec),
            },
        })

    # Append narrative notes after the structured records, renumbering.
    for nc in note_chunks:
        idx += 1
        nc["index"] = idx
        chunks.append(nc)

    return chunks
