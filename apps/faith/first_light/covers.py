"""Procedural cover art — a small visual language for journeys.

No custom illustrations, no asset pipeline: each journey gets a warm, drawn scene
chosen deterministically from its own content (topics / title / book), so a card
is recognizable before you read the title and browsing hundreds stays pleasant.
Eight motifs, each with its own natural palette; a per-journey seed varies the
light so even same-theme cards aren't identical.

`cover_svg(plan)` returns a complete <svg> string (300×110) ready to drop into a
card. Deterministic and pure — safe to call anywhere.
"""

from __future__ import annotations

# ── Keyword → motif. First match wins; else "mountains" (a dawn horizon). ──
_MOTIF_KEYWORDS = [
    ("waves",   ("psalm", "comfort", "peace", "anxiety", "anxious", "rest", "still", "water", "sea", "calm", "worry", "fear")),
    ("cross",   ("jesus", "gospel", "cross", "forgive", "grace", "salvation", "easter", "calvary", "matthew", "mark", "luke", "john", "redemption", "sacrifice")),
    ("stars",   ("prophet", "hope", "advent", "promise", "isaiah", "daniel", "revelation", "waiting", "night", "exile", "future", "heaven")),
    ("scroll",  ("law", "torah", "genesis", "exodus", "leviticus", "covenant", "moses", "old testament", "commandment", "beginning")),
    ("field",   ("wisdom", "proverb", "gratitude", "thanks", "harvest", "provision", "work", "purpose", "steward", "generous")),
    ("flame",   ("prayer", "spirit", "pentecost", "worship", "presence", "fire", "devotion", "seek")),
    ("path",    ("journey", "follow", "disciple", "obedience", "faith", "walk", "growth", "identity", "calling", "leadership", "marriage", "family")),
]

# palette = (top, bottom, ink1, ink2, light)
_PALETTES = {
    "mountains": ("#F6CE80", "#93582E", "#8E5E33", "#6F4A2C", "#FCEFC9"),
    "waves":     ("#E2B978", "#2E5A72", "#356079", "#264C61", "#FBEAC4"),
    "cross":     ("#E9A96A", "#6E3B4A", "#5A3A22", "#3C2A1C", "#F6D9A0"),
    "scroll":    ("#E9D6A6", "#A8783E", "#EFE0BC", "#B8925A", "#5A3A22"),
    "stars":     ("#28313F", "#7A5A3E", "#2A2A38", "#4A3E52", "#EFE6CF"),
    "field":     ("#E7D08A", "#6E7A44", "#7E8A4E", "#5E6B36", "#F4E4A6"),
    "flame":     ("#2C2438", "#6E3B2E", "#5A4636", "#3A2E26", "#E9C56B"),
    "path":      ("#EBD79A", "#7E8A4E", "#EFE0BC", "#5E6B36", "#F4E4A6"),
}


def motif_for(plan) -> str:
    hay = " ".join(filter(None, [
        (getattr(plan, "title", "") or ""),
        " ".join(getattr(plan, "topics", None) or []),
        (getattr(plan, "source", "") or ""),
        (getattr(plan, "series", "") or ""),
    ])).lower()
    for motif, keys in _MOTIF_KEYWORDS:
        if any(k in hay for k in keys):
            return motif
    return "mountains"


def _seed(plan) -> int:
    pk = getattr(plan, "pk", None)
    if isinstance(pk, int):
        return pk
    return abs(hash(getattr(plan, "slug", "") or "x")) % 997


def cover_svg(plan) -> str:
    motif = motif_for(plan)
    top, bot, ink1, ink2, light = _PALETTES[motif]
    seed = _seed(plan)
    gid = f"flg{seed}"
    sun_x = 70 + (seed * 37) % 170  # 70..240 — the light sits in a different place per journey
    base = (
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bot}"/>'
        f'</linearGradient></defs><rect width="300" height="110" fill="url(#{gid})"/>'
    )
    body = _MOTIF_BUILDERS[motif](sun_x, ink1, ink2, light, seed)
    return f'<svg viewBox="0 0 300 110" preserveAspectRatio="xMidYMid slice" aria-hidden="true">{base}{body}</svg>'


def _mountains(sx, i1, i2, light, seed):
    return (
        f'<circle cx="{sx}" cy="70" r="24" fill="{light}"/>'
        f'<polygon points="0,110 80,52 160,110" fill="{i1}"/>'
        f'<polygon points="110,110 210,44 300,110" fill="{i2}"/>'
    )


def _waves(sx, i1, i2, light, seed):
    return (
        f'<rect width="300" height="58" fill="{light}" opacity=".55"/>'
        f'<circle cx="{sx}" cy="34" r="15" fill="{light}"/>'
        f'<path d="M0,74 Q60,62 120,74 T300,74 V110 H0Z" fill="{i1}"/>'
        f'<path d="M0,90 Q60,80 120,90 T300,90 V110 H0Z" fill="{i2}"/>'
    )


def _cross(sx, i1, i2, light, seed):
    return (
        f'<circle cx="150" cy="66" r="26" fill="{light}"/>'
        f'<rect x="146" y="28" width="8" height="70" fill="{i2}"/>'
        f'<rect x="130" y="48" width="40" height="8" fill="{i2}"/>'
        f'<rect x="96" y="52" width="6" height="46" fill="{i1}"/><rect x="84" y="66" width="30" height="6" fill="{i1}"/>'
        f'<rect x="200" y="52" width="6" height="46" fill="{i1}"/><rect x="188" y="66" width="30" height="6" fill="{i1}"/>'
        f'<polygon points="0,110 300,110 300,96 0,100" fill="{i2}"/>'
    )


def _scroll(sx, i1, i2, light, seed):
    return (
        f'<rect x="40" y="24" width="220" height="62" rx="4" fill="{i1}"/>'
        f'<rect x="40" y="18" width="220" height="10" rx="5" fill="{i2}"/>'
        f'<rect x="40" y="82" width="220" height="10" rx="5" fill="{i2}"/>'
        f'<rect x="70" y="40" width="160" height="4" rx="2" fill="{i2}" opacity=".5"/>'
        f'<rect x="70" y="52" width="130" height="4" rx="2" fill="{i2}" opacity=".4"/>'
        f'<rect x="70" y="64" width="150" height="4" rx="2" fill="{i2}" opacity=".4"/>'
    )


def _stars(sx, i1, i2, light, seed):
    dots = "".join(
        f'<circle cx="{(30 + (seed * (k + 3) * 53) % 260)}" cy="{(14 + (seed * (k + 1) * 31) % 46)}" r="{1 + k % 2}" fill="{light}" opacity=".8"/>'
        for k in range(7)
    )
    return (
        f'{dots}<circle cx="{sx}" cy="30" r="12" fill="{light}"/>'
        f'<path d="M0,110 L0,82 Q150,66 300,80 L300,110Z" fill="{i2}"/>'
    )


def _field(sx, i1, i2, light, seed):
    rows = "".join(
        f'<path d="M0,{78 + r*8} Q150,{72 + r*8} 300,{78 + r*8}" stroke="{i2}" stroke-width="2" fill="none" opacity=".5"/>'
        for r in range(4)
    )
    return (
        f'<circle cx="{sx}" cy="34" r="15" fill="{light}"/>'
        f'<path d="M0,110 L0,72 Q150,60 300,72 L300,110Z" fill="{i1}"/>{rows}'
    )


def _flame(sx, i1, i2, light, seed):
    return (
        f'<ellipse cx="150" cy="60" rx="60" ry="44" fill="{light}" opacity=".16"/>'
        f'<rect x="140" y="60" width="20" height="42" rx="3" fill="{i1}"/>'
        f'<path d="M150 30 C160 44 164 50 164 60 a14 14 0 0 1-28 0 c0-10 4-16 14-30z" fill="{light}"/>'
        f'<path d="M150 42 C156 50 158 54 158 60 a8 8 0 0 1-16 0 c0-6 2-10 8-18z" fill="{i2}" opacity=".6"/>'
    )


def _path(sx, i1, i2, light, seed):
    return (
        f'<circle cx="{sx}" cy="30" r="13" fill="{light}"/>'
        f'<path d="M0,110 L0,86 Q150,72 300,84 L300,110Z" fill="{i2}"/>'
        f'<path d="M150,110 C150,92 120,88 138,76 C156,66 150,58 150,54" stroke="{i1}" stroke-width="9" fill="none" stroke-linecap="round" opacity=".9"/>'
    )


_MOTIF_BUILDERS = {
    "mountains": _mountains,
    "waves": _waves,
    "cross": _cross,
    "scroll": _scroll,
    "stars": _stars,
    "field": _field,
    "flame": _flame,
    "path": _path,
}
