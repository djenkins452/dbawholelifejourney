# ==============================================================================
# File: apps/life/services/document_upload.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The ONE way a Document and its file are saved together.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-13
# ==============================================================================
"""Save a Document and its file as one unit, or not at all.

Django's FileField uploads the file in `pre_save` and only THEN runs the INSERT, with no
transaction around either. So a database failure after the upload leaves the blob in
storage with no row pointing at it — which is exactly what happened on 2026-09-13: a
`DataError` on the INSERT, a 500 for the user, and a 0.27 MB orphan in Cloudinary.

This module gives the two steps the guarantee the model cannot:

  * the row is written inside `transaction.atomic()`;
  * if anything fails AFTER the file reached storage, the blob is removed again;
  * if storage itself fails, no row was ever written;
  * every failure is one typed exception carrying a short correlation id that is
    logged (with `exc_info`) and shown to the user — never a bare 500;
  * a re-sent `upload_token` returns the document the first submission created.

Nothing here reads, logs or prints the file's contents.
"""
import logging
import os
import uuid

from django.db import IntegrityError, transaction

from apps.life.models import Document

logger = logging.getLogger(__name__)


class DocumentUploadError(Exception):
    """A save that could not complete. `user_message` is safe to render; `ref` is the
    correlation id that finds the logged traceback."""

    def __init__(self, user_message, ref, *, field=None):
        super().__init__(user_message)
        self.user_message = user_message
        self.ref = ref
        self.field = field            # bind the message to a control when one applies


def _discard_blob(document, ref):
    """Remove a file that reached storage for a row that never did."""
    name = getattr(getattr(document, "file", None), "name", None)
    if not name:
        return
    try:
        document.file.storage.delete(name)
        logger.warning("document upload %s: discarded orphaned blob (%d chars)", ref, len(name))
    except Exception:
        # The blob is already an orphan; a failed cleanup must not hide the original
        # error. Logged loudly so an operator can remove it by hand.
        logger.error("document upload %s: could not discard orphaned blob (%d chars)",
                     ref, len(name), exc_info=True)


def existing_for_token(user, token):
    """The Document a previous submission with this token already created, or None."""
    if not token:
        return None
    return Document.objects.filter(user=user, upload_token=token).first()


def save_document_upload(form, user, *, created_via=None):
    """Persist `form` (a bound, valid DocumentForm) for `user`.

    Returns `(document, created)`. `created` is False when the token had already been
    used — the earlier submission's document is returned and nothing new is written.
    Raises `DocumentUploadError` for anything the user can act on or should be told.
    """
    ref = uuid.uuid4().hex[:8]
    token = (form.cleaned_data.get("upload_token") or "").strip() or None

    prior = existing_for_token(user, token)
    if prior is not None:
        logger.info("document upload %s: token already used, returning document %s", ref, prior.pk)
        return prior, False

    upload = form.cleaned_data.get("file")
    is_new_file = upload is not None and hasattr(upload, "content_type")

    document = form.instance
    document.user = user
    if created_via:
        document.created_via = created_via
    if token and document.pk is None:
        document.upload_token = token
    if is_new_file:
        document.original_filename = os.path.basename(getattr(upload, "name", "") or "")[:255]

    try:
        with transaction.atomic():
            document = form.save()
    except IntegrityError as exc:
        # The only integrity rule on a create is the token: a concurrent double-click
        # got there first. Hand back its document and drop our copy of the blob.
        if is_new_file:
            _discard_blob(document, ref)
        prior = existing_for_token(user, token)
        if prior is not None:
            logger.info("document upload %s: lost the token race to document %s", ref, prior.pk)
            return prior, False
        logger.error("document upload %s: integrity error without a token match", ref, exc_info=True)
        raise DocumentUploadError(
            f"This document couldn't be saved. Reference {ref}.", ref) from exc
    except Exception as exc:
        # Either the upload itself failed (no row was written) or the INSERT did (the
        # blob must go). FieldFile.save() flips `_committed` only once storage accepted
        # the file, so that flag says which side of the line we failed on.
        if is_new_file and _blob_was_stored(document):
            _discard_blob(document, ref)
            logger.error("document upload %s: database write failed after storage; rolled back",
                         ref, exc_info=True)
            raise DocumentUploadError(
                f"The file uploaded but the document couldn't be saved, so nothing was kept. "
                f"Please try again. Reference {ref}.", ref) from exc
        logger.error("document upload %s: storage write failed; nothing saved", ref, exc_info=True)
        raise DocumentUploadError(
            f"The file couldn't be stored right now, so nothing was saved. "
            f"Please try again in a moment. Reference {ref}.", ref, field="file") from exc

    logger.info("document upload %s: saved document %s (%s bytes, %s)",
                ref, document.pk, document.file_size, document.file_type)
    return document, True


def _blob_was_stored(document):
    """True once storage has accepted the file: FieldFile.save() sets `_committed`
    only after `storage.save()` returned a key."""
    ff = getattr(document, "file", None)
    return bool(ff is not None and getattr(ff, "_committed", False) is True and ff.name)
