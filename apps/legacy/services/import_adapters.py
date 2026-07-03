"""
Legacy Import Engine — source adapters + intelligent chunker.

An adapter turns a raw document into a list of Segments (author, text, ref).
The chunker groups segments into coherent, story-sized chunks. Adding a new
source (Word, PDF, journal, another chat export) is just registering an adapter
— the rest of the pipeline (chunk → Discovery → draft Memory → review) is shared.
"""

import re
from dataclasses import dataclass
from typing import Callable, List


class ImportNotAvailable(Exception):
    """Raised when a source type has no working adapter yet."""


@dataclass
class Segment:
    text: str
    ref: str          # human provenance, e.g. "message 7" / "paragraph 3"
    author: str = ""  # optional (e.g. "Danny", "Assistant")


# ── Adapters ────────────────────────────────────────────────────────────────
_MSG_RE = re.compile(r"^##\s*\[(\d+)\]\s*(.*)$")


def _adapter_chat(raw: str) -> List[Segment]:
    """ChatGPT / Claude / markdown transcript: '## [n] <author> ...' blocks."""
    segments, cur_ref, cur_author, buf = [], None, "", []

    def flush():
        if cur_ref and buf:
            text = "\n".join(buf).strip()
            if text:
                segments.append(Segment(text=text, ref=cur_ref, author=cur_author))

    for line in raw.splitlines():
        m = _MSG_RE.match(line.strip())
        if m:
            flush()
            buf = []
            cur_ref = f"message {m.group(1)}"
            label = re.sub(r"[^\w &'-]", "", m.group(2)).strip()  # strip emoji
            cur_author = label.replace("Assistant", "").strip() or label
        elif cur_ref is not None:
            buf.append(line)
    flush()
    # If there were no message headers at all, fall back to paragraph splitting.
    return segments or _adapter_text(raw)


def _adapter_text(raw: str) -> List[Segment]:
    """Plain text / memoir / journal: split on blank-line paragraphs."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    # Skip a leading document title/metadata block if it's very short + markdowny.
    return [Segment(text=p, ref=f"paragraph {i}") for i, p in enumerate(paras, 1)]


def _adapter_unavailable(_raw: str) -> List[Segment]:
    raise ImportNotAvailable(
        "This source type isn't supported yet. Paste the text, or use a "
        "ChatGPT/Claude export, Markdown, or plain-text file for now.")


_ADAPTERS: dict = {
    "chatgpt": _adapter_chat,
    "claude": _adapter_chat,
    "plain_text": _adapter_text,
    "memoir": _adapter_text,
    "journal": _adapter_text,
    "other": _adapter_text,
    # Extension points — register real extractors later:
    "word": _adapter_unavailable,
    "pdf": _adapter_unavailable,
}


def get_adapter(source_type: str) -> Callable[[str], List[Segment]]:
    return _ADAPTERS.get(source_type, _adapter_text)


# ── Intelligent chunker ──────────────────────────────────────────────────────
def _title_from(body: str, limit: int = 80) -> str:
    first = ""
    for line in body.splitlines():
        line = re.sub(r"^[#>*\-\s]+", "", line).strip()
        if line:
            first = line
            break
    first = re.split(r"(?<=[.!?])\s", first)[0] if first else ""
    if len(first) <= limit:
        return first
    words = first[:limit].rsplit(" ", 1)[0]
    return (words or first[:limit]).strip() + "…"


def _split_long(text: str, hard_max: int) -> List[str]:
    pieces, buf, blen = [], [], 0
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) > hard_max:              # a single giant paragraph
            if buf:
                pieces.append("\n\n".join(buf)); buf, blen = [], 0
            for i in range(0, len(para), hard_max):
                pieces.append(para[i:i + hard_max])
            continue
        if blen and blen + len(para) > hard_max:
            pieces.append("\n\n".join(buf)); buf, blen = [], 0
        buf.append(para); blen += len(para)
    if buf:
        pieces.append("\n\n".join(buf))
    return pieces


def _refspan(refs: List[str]) -> str:
    refs = [r for r in refs if r]
    if not refs:
        return ""
    if len(refs) == 1 or refs[0] == refs[-1]:
        return refs[0]
    return f"{refs[0]}–{refs[-1]}"


def chunk(segments: List[Segment], target: int = 3500, hard_max: int = 7000) -> List[dict]:
    """Group segments into coherent, story-sized chunks."""
    chunks, buf, blen, refs = [], [], 0, []

    def flush():
        nonlocal buf, blen, refs
        if not buf:
            return
        body = "\n\n".join(buf).strip()
        if body:
            chunks.append({"title": _title_from(body), "body": body, "source_ref": _refspan(refs)})
        buf, blen, refs = [], 0, []

    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        if len(text) > hard_max:
            flush()
            parts = _split_long(text, hard_max)
            for j, piece in enumerate(parts):
                ref = seg.ref if len(parts) == 1 else f"{seg.ref} (part {j + 1})"
                chunks.append({"title": _title_from(piece), "body": piece, "source_ref": ref})
            continue
        if blen and blen + len(text) > target:
            flush()
        buf.append(text)
        blen += len(text)
        refs.append(seg.ref)
    flush()

    for i, c in enumerate(chunks, 1):
        c["index"] = i
    return chunks
