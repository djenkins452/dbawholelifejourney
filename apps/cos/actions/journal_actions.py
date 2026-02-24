"""
JournalCosActions — CoS v2 action contract implementation for the Journal module.

Core behavior: "Append, Don't Duplicate"
- If user says "Create a journal entry for today…" and today's entry exists,
  the CoS appends content to the existing entry instead of creating a new one.
- If no entry exists for the date, a new entry is created.
- Supports update (replace sections), retrieve, and summarise.
"""

import datetime as dt
import logging

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone as dj_timezone

from apps.cos.contracts import (
    ActionResult,
    CosActionContract,
    DuplicateCheck,
)
from apps.cos.models import CosReflection
from apps.journal.models import JournalEntry

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Append separator
# ──────────────────────────────────────────────────────────

APPEND_SEPARATOR = "\n\n---\n\n"


class JournalCosActions(CosActionContract):
    """
    CoS v2 action contract for the Journal module.

    Key behavior: same-date entries are appended, not duplicated.
    The CoS always checks for an existing entry on the target date
    before creating a new one.
    """

    @property
    def module_name(self) -> str:
        return "journal"

    def supports_reflections(self) -> bool:
        return True

    def supports_proactive_prompts(self) -> bool:
        return True

    # ── CRUD ──────────────────────────────────────────────

    def create(self, **kwargs) -> ActionResult:
        """
        Create or append to a journal entry.

        Append-not-duplicate policy:
        - If an active entry exists for the target date, append the body.
        - If no entry exists, create a new one.
        - If force_new=True, always create a new entry (bypass append).

        kwargs:
            title: str (optional — auto-generated from date if blank)
            body: str (required)
            entry_date: date (default: today)
            mood: str (optional)
            force_new: bool (default: False — bypass append)
        """
        body = kwargs.get("body", "")
        if not body:
            return ActionResult(
                success=False,
                error="Journal entry body is required.",
            )

        entry_date = kwargs.get("entry_date", dj_timezone.localdate())
        title = kwargs.get("title", "")
        mood = kwargs.get("mood", "")
        force_new = kwargs.get("force_new", False)

        # ── Check for existing same-date entry ────────────
        if not force_new:
            existing = self._find_same_date_entry(entry_date)
            if existing:
                return self._append_to_entry(existing, body, mood=mood)

        # ── Create new entry ──────────────────────────────
        try:
            entry = JournalEntry(
                user=self.user,
                title=title,
                body=body,
                entry_date=entry_date,
                mood=mood,
            )
            entry.save()

            return ActionResult(
                success=True,
                entity=entry,
                entity_id=entry.pk,
                metadata={
                    "action": "created",
                    "entry_date": str(entry_date),
                    "word_count": entry.word_count,
                },
            )
        except Exception as e:
            logger.error(
                "JournalCosActions.create failed for user=%s: %s",
                self.user.id, e, exc_info=True,
            )
            return ActionResult(success=False, error=str(e))

    def update(self, entity_id: int, **kwargs) -> ActionResult:
        """
        Update a journal entry's fields.

        Supports:
        - title: replace title
        - body: replace entire body
        - mood: update mood
        - append_body: append text to existing body (instead of replacing)
        """
        try:
            entry = JournalEntry.objects.get(pk=entity_id, user=self.user)
        except JournalEntry.DoesNotExist:
            return ActionResult(
                success=False,
                error=f"Journal entry {entity_id} not found.",
            )

        fields_changed = {}

        if "title" in kwargs:
            old = entry.title
            entry.title = kwargs["title"]
            if old != entry.title:
                fields_changed["title"] = {"old": old, "new": entry.title}

        if "body" in kwargs:
            old = entry.body
            entry.body = kwargs["body"]
            if old != entry.body:
                fields_changed["body"] = {"old_len": len(old), "new_len": len(entry.body)}

        if "append_body" in kwargs:
            old_len = len(entry.body)
            entry.body = entry.body + APPEND_SEPARATOR + kwargs["append_body"]
            fields_changed["body"] = {
                "action": "appended",
                "old_len": old_len,
                "new_len": len(entry.body),
            }

        if "mood" in kwargs:
            old = entry.mood
            entry.mood = kwargs["mood"]
            if old != entry.mood:
                fields_changed["mood"] = {"old": old, "new": entry.mood}

        if not fields_changed:
            return ActionResult(
                success=True,
                entity=entry,
                entity_id=entry.pk,
                metadata={"action": "no_changes"},
            )

        try:
            entry.save()
            return ActionResult(
                success=True,
                entity=entry,
                entity_id=entry.pk,
                metadata={
                    "action": "updated",
                    "fields_changed": fields_changed,
                    "word_count": entry.word_count,
                },
            )
        except Exception as e:
            logger.error(
                "JournalCosActions.update failed for entry=%s: %s",
                entity_id, e, exc_info=True,
            )
            return ActionResult(success=False, error=str(e))

    def delete(self, entity_id: int, **kwargs) -> ActionResult:
        """Soft-delete a journal entry."""
        try:
            entry = JournalEntry.objects.get(pk=entity_id, user=self.user)
        except JournalEntry.DoesNotExist:
            return ActionResult(
                success=False,
                error=f"Journal entry {entity_id} not found.",
            )

        entry.soft_delete()
        return ActionResult(
            success=True,
            entity_id=entry.pk,
            metadata={"action": "soft_deleted"},
        )

    def retrieve(self, entity_id: int) -> ActionResult:
        """Retrieve a journal entry by ID."""
        try:
            entry = JournalEntry.objects.get(pk=entity_id, user=self.user)
            return ActionResult(
                success=True,
                entity=entry,
                entity_id=entry.pk,
                metadata={
                    "title": entry.title,
                    "entry_date": str(entry.entry_date),
                    "word_count": entry.word_count,
                    "mood": entry.mood,
                    "body_preview": entry.body_preview,
                },
            )
        except JournalEntry.DoesNotExist:
            return ActionResult(
                success=False,
                error=f"Journal entry {entity_id} not found.",
            )

    def summarise(self, **kwargs) -> ActionResult:
        """
        Summarise journal entries for a date range.

        kwargs:
            date: specific date (default: today)
            start_date / end_date: date range
            limit: max entries to return (default: 10)
            include_body: bool (default: False — include full body)
        """
        target_date = kwargs.get("date")
        start_date = kwargs.get("start_date")
        end_date = kwargs.get("end_date")
        limit = kwargs.get("limit", 10)
        include_body = kwargs.get("include_body", False)

        if target_date:
            start_date = target_date
            end_date = target_date

        qs = JournalEntry.objects.filter(user=self.user)

        if start_date:
            qs = qs.filter(entry_date__gte=start_date)
        if end_date:
            qs = qs.filter(entry_date__lte=end_date)

        entries = qs.order_by("-entry_date", "-created_at")[:limit]

        summary = []
        for e in entries:
            item = {
                "id": e.pk,
                "title": e.title,
                "entry_date": str(e.entry_date),
                "word_count": e.word_count,
                "mood": e.mood,
                "mood_emoji": e.mood_emoji,
            }
            if include_body:
                item["body"] = e.body
            else:
                item["body_preview"] = e.body_preview
            summary.append(item)

        total_words = sum(e.word_count for e in entries)

        return ActionResult(
            success=True,
            metadata={
                "entry_count": len(summary),
                "total_words": total_words,
                "entries": summary,
            },
        )

    # ── Safety Checks ─────────────────────────────────────

    def check_duplicate(self, **kwargs) -> DuplicateCheck:
        """
        Check if a same-date entry exists.

        This is the CoS's "append, don't duplicate" check.
        Returns the existing entry if one exists for the date.
        """
        entry_date = kwargs.get("entry_date", dj_timezone.localdate())

        existing = self._find_same_date_entry(entry_date)
        if existing:
            return DuplicateCheck(
                is_duplicate=True,
                existing_entity=existing,
                existing_entity_id=existing.pk,
                match_type="same_date",
                message=(
                    f"An entry already exists for {entry_date}: "
                    f"'{existing.title}' ({existing.word_count} words). "
                    f"New content will be appended."
                ),
            )
        return DuplicateCheck(is_duplicate=False)

    # ── Reflection hooks ──────────────────────────────────

    def capture_reflection_hook(
        self, entity_id: int, reflection_text: str, **kwargs
    ) -> bool:
        """Store a reflection note against a journal entry."""
        try:
            entry = JournalEntry.objects.get(pk=entity_id, user=self.user)
            ct = ContentType.objects.get_for_model(JournalEntry)

            CosReflection.objects.create(
                user=self.user,
                content_type=ct,
                object_id=entry.pk,
                text=reflection_text,
                activity_date=entry.entry_date,
                activity_type="journal",
                sentiment=kwargs.get("sentiment", ""),
                prompt_text=kwargs.get("prompt_text", ""),
            )
            return True
        except (JournalEntry.DoesNotExist, Exception) as e:
            logger.error(
                "Reflection capture failed for journal entry %s: %s",
                entity_id, e,
            )
            return False

    # ── Private helpers ───────────────────────────────────

    def _find_same_date_entry(self, entry_date):
        """
        Find the most recent active entry for the given date.

        Uses the default manager (SoftDeleteManager) so only active entries
        are considered — deleted/archived entries don't block new creation.
        """
        return (
            JournalEntry.objects.filter(
                user=self.user,
                entry_date=entry_date,
            )
            .order_by("-created_at")
            .first()
        )

    def _append_to_entry(
        self, entry: JournalEntry, new_body: str, mood: str = ""
    ) -> ActionResult:
        """
        Append new content to an existing entry.

        Adds a visual separator between existing and new content.
        Updates mood if provided and entry has no mood set.
        """
        original_word_count = entry.word_count
        entry.body = entry.body + APPEND_SEPARATOR + new_body

        # Update mood only if entry doesn't already have one
        if mood and not entry.mood:
            entry.mood = mood

        try:
            entry.save()
            return ActionResult(
                success=True,
                entity=entry,
                entity_id=entry.pk,
                reused=True,  # Signals that we appended, not created
                metadata={
                    "action": "appended",
                    "entry_date": str(entry.entry_date),
                    "original_word_count": original_word_count,
                    "new_word_count": entry.word_count,
                    "words_added": entry.word_count - original_word_count,
                },
            )
        except Exception as e:
            logger.error(
                "JournalCosActions._append_to_entry failed: %s", e,
                exc_info=True,
            )
            return ActionResult(success=False, error=str(e))
