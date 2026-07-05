"""
Notes background tasks.

Embedding generation calls the OpenAI embeddings API, which must NEVER run on
the request thread (a note save is not a path the user expects to wait on an
LLM). `note_post_save_embedding` and the tag/attachment signals enqueue
`deferred_update_note_embedding` via safe_enqueue instead of embedding inline.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="notes.deferred_update_note_embedding",
    soft_time_limit=60,
    time_limit=90,
    acks_late=True,
    reject_on_worker_lost=True,
)
def deferred_update_note_embedding(note_id):
    """Regenerate a Note's semantic embedding off the request path.

    Enqueued by the notes content/tag/attachment signals. Fail-safe: a missing
    note or an OpenAI hiccup is logged, never raised. The next content edit
    re-enqueues, so a transient failure self-heals.
    """
    from .models import Note
    from .embeddings import update_note_embedding

    note = Note.objects.filter(pk=note_id).first()
    if note is None:
        return {"status": "note_not_found", "note_id": note_id}
    ok = update_note_embedding(note)
    return {"status": "ok" if ok else "skipped", "note_id": note_id}
