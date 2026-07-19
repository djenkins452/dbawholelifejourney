"""
Deterministic perception — WLJ's mechanical decoders for uploaded artifacts.

The ONE place content is turned into text/transcript the conversational model can
read. This is DETERMINISTIC DECODE, not interpretation: pdfplumber returns the
characters literally present in a PDF; a future Whisper step returns the literal
transcript. WLJ never summarizes, understands, or reasons here — the model does
all perception/reasoning over the returned text
(docs/WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md §2, §3).

Dispatched by content type so every attachment reuses the SAME arrival pipeline
and only THIS component varies. Milestone 1 implements PDF; documents/audio/video
plug in the same way. Pure + defensive: never raises; returns a status.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

# Cap the stored extracted text (Postgres TEXT is fine, but keep a sane ceiling
# so a pathological PDF can't store tens of MB). Full doc still fits for the vast
# majority of real documents (a 50-page policy ≈ 120K chars).
MAX_EXTRACTED_CHARS = 400_000

# Content types that have a deterministic extractor TODAY. Grows one milestone at
# a time (documents → audio → video); everything else stores + surfaces without
# perception until its extractor lands.
PERCEIVABLE_TYPES = frozenset({
    "application/pdf",
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/aac",
})

# content_type → filename (extension) the shared transcription capability uses to
# tell Whisper the format.
_AUDIO_FILENAMES = {
    "audio/mpeg": "audio.mp3",
    "audio/mp4": "audio.m4a",   # our sniffer reports M4A (AAC-in-MP4) as audio/mp4
    "audio/wav": "audio.wav",
    "audio/aac": "audio.aac",   # converted to mp3 by the transcription core
}


def is_perceivable(content_type: str) -> bool:
    """True if WLJ has a deterministic extractor for this content type today."""
    return (content_type or "").lower() in PERCEIVABLE_TYPES


def perceive(content_type: str, raw: bytes) -> dict:
    """Extract deterministic text from raw bytes based on content type.

    Returns a dict: {status, text, page_count}. `status` is one of the
    MultimodalArtifact.PERCEPTION_* string values ('done' / 'failed' /
    'unsupported'). Never raises.
    """
    ct = (content_type or "").lower()
    try:
        if ct == "application/pdf":
            return _perceive_pdf(raw)
        if ct in _AUDIO_FILENAMES:
            return _perceive_audio(raw, ct)
        # Office documents / video plug in here in later milestones.
        return {"status": "unsupported", "text": "", "page_count": None}
    except Exception as exc:  # pragma: no cover - defensive; perception never breaks a turn
        logger.warning("perceive failed for %s (%s)", ct, exc, exc_info=True)
        return {"status": "failed", "text": "", "page_count": None}


def _perceive_audio(raw: bytes, content_type: str) -> dict:
    """Transcribe audio via the ONE shared transcription capability (Capture's
    Whisper integration). WLJ produces the literal transcript; the model reasons
    over it. No second transcription system.
    """
    from apps.capture.services.transcription import transcription_service

    filename = _AUDIO_FILENAMES.get(content_type, "audio.mp3")
    transcript = (transcription_service.transcribe_bytes(raw, filename) or "").strip()
    if not transcript:
        return {"status": "unsupported", "text": "", "page_count": None}
    if len(transcript) > MAX_EXTRACTED_CHARS:
        transcript = transcript[:MAX_EXTRACTED_CHARS]
    return {"status": "done", "text": transcript, "page_count": None}


def _perceive_pdf(raw: bytes) -> dict:
    """Extract text from a text-based PDF via pdfplumber (page-delimited)."""
    import pdfplumber

    pages_text = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        page_count = len(pdf.pages)
        for idx, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or ""
            if txt.strip():
                pages_text.append(f"[Page {idx}]\n{txt.strip()}")
            # Bound total work — stop once we've gathered enough characters.
            if sum(len(p) for p in pages_text) >= MAX_EXTRACTED_CHARS:
                break

    text = "\n\n".join(pages_text).strip()
    if len(text) > MAX_EXTRACTED_CHARS:
        text = text[:MAX_EXTRACTED_CHARS]

    if not text:
        # A scanned/image-only PDF yields no text here — OCR is a later step.
        return {"status": "unsupported", "text": "", "page_count": page_count}
    return {"status": "done", "text": text, "page_count": page_count}
