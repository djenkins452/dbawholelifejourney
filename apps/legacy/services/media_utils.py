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


def guess_media_type(filename):
    """Best-effort media type from a filename extension."""
    ext = (filename.rsplit(".", 1)[-1] if filename and "." in filename else "").lower()
    return _EXT_TYPE.get(ext, Media.MediaType.OTHER)
