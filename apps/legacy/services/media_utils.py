"""Shared media helpers for Legacy."""

from apps.legacy.models import Media

_EXT_TYPE = {
    "jpg": Media.MediaType.PHOTO, "jpeg": Media.MediaType.PHOTO, "png": Media.MediaType.PHOTO,
    "gif": Media.MediaType.PHOTO, "webp": Media.MediaType.PHOTO, "heic": Media.MediaType.PHOTO,
    "mp4": Media.MediaType.VIDEO, "mov": Media.MediaType.VIDEO, "m4v": Media.MediaType.VIDEO,
    "webm": Media.MediaType.VIDEO,
    "mp3": Media.MediaType.AUDIO, "m4a": Media.MediaType.AUDIO, "wav": Media.MediaType.AUDIO,
    "aac": Media.MediaType.AUDIO,
    "pdf": Media.MediaType.DOCUMENT, "doc": Media.MediaType.DOCUMENT, "docx": Media.MediaType.DOCUMENT,
    "txt": Media.MediaType.DOCUMENT, "rtf": Media.MediaType.DOCUMENT,
}


def file_ext(filename):
    return (filename.rsplit(".", 1)[-1] if filename and "." in filename else "").lower()


def guess_media_type(filename):
    """Best-effort media type from a filename extension."""
    return _EXT_TYPE.get(file_ext(filename), Media.MediaType.OTHER)


# Written life (memoirs, journals) belongs in Import — not the media library.
NARRATIVE_TEXT_EXTS = {"txt", "md", "markdown"}
# Photos / video / audio belong with a story — never in Import.
VISUAL_AV_EXTS = {
    "jpg", "jpeg", "png", "gif", "webp", "heic",
    "mp4", "mov", "m4v", "webm",
    "mp3", "m4a", "wav", "aac",
}


def is_narrative_text(filename):
    """A plain-text document a person would think of as 'their written life'."""
    return file_ext(filename) in NARRATIVE_TEXT_EXTS


def is_visual_media(filename):
    """A photo, video, or audio clip — supporting media, never an import."""
    return file_ext(filename) in VISUAL_AV_EXTS
