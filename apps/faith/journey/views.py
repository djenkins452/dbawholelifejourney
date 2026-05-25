"""
Journey views — daily reading, settings, annotation endpoints.

Scope per Commit 4:
- Daily reading view at /faith/journey/today/ (current day)
- Addressable read-only review at /faith/journey/<arc_slug>/day/<n>/
- "I'm stuck" deterministic surface (no Beth)
- Annotation reuse endpoints (highlight, bookmark, save verse, note)
  — thin wrappers that create rows in the existing four annotation models
- Start-journey + settings + complete-day actions

Not in this commit:
- Beth tool / chat affordance
- Calendar projection
- Push notifications
- Streak visibility
"""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseNotFound, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

# Reuse-only annotation models — the four documented carve-outs.
from apps.faith.models import BibleBookmark, BibleHighlight, BibleStudyNote, SavedVerse

from apps.faith.journey.forms import CompleteDayForm, JourneySettingsForm
from apps.faith.journey.models import JourneyDay, JourneyPath, UserJourney
from apps.faith.journey.services import (
    can_view_day,
    get_active_journey,
    get_current_day,
    get_day_in_arc,
    get_or_create_journey,
    get_progress_for_day,
    mark_day_complete,
    parse_reference,
)


JOURNEY_PATH_SLUG = "walking_with_god"  # Phase 1 ships one journey


# ---------------------------------------------------------------------------
# Routing helpers
# ---------------------------------------------------------------------------

def _render_no_journey(request):
    path = JourneyPath.objects.filter(slug=JOURNEY_PATH_SLUG, is_active=True).first()
    return render(request, "faith/journey/no_journey.html", {"journey_path": path})


def _render_day(request, user_journey, day, *, review_mode: bool, welcome_back: bool = False):
    """Render a single day's reading.

    review_mode=True means the user is viewing a past day (no complete button).
    welcome_back=True means the user returned after a ≥3-day gap; banner shown.
    """
    progress = get_progress_for_day(user_journey, day)
    tier = user_journey.preferred_difficulty
    plain_english = day.plain_english_for_tier(tier)

    context = {
        "user_journey": user_journey,
        "day": day,
        "arc": day.arc,
        "path": day.arc.journey_path,
        "tier": tier,
        "plain_english": plain_english,
        "progress": progress,
        "complete_form": CompleteDayForm(initial={
            "reflection_notes": progress.reflection_notes,
            "application_committed": progress.application_committed,
        }),
        "review_mode": review_mode,
        "is_complete": progress.is_completed,
        "welcome_back": welcome_back,
    }
    return render(request, "faith/journey/day.html", context)


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------

@login_required
def journey_today(request):
    """Canonical entry point. Renders the user's current day.

    Welcome-back logic: if the user hasn't visited in ≥3 days, render the
    banner and emit the journey.resumed signal once. Updates last_visited_at
    on every load. last_engaged_at is intentionally NOT updated here (that
    fires only on day completion, preserving days_since_last_read accuracy).
    """
    user_journey = get_active_journey(request.user)
    if user_journey is None:
        return _render_no_journey(request)

    now = timezone.now()
    welcome_back = False
    if user_journey.last_visited_at is not None:
        gap_days = (now - user_journey.last_visited_at).days
        if gap_days >= 3:
            welcome_back = True
            from apps.faith.journey.signals import emit_resumed
            emit_resumed(request.user, user_journey=user_journey, days_since_last_visit=gap_days)
    user_journey.last_visited_at = now
    user_journey.save(update_fields=["last_visited_at"])

    day = get_current_day(user_journey)
    if day is None:
        return render(request, "faith/journey/no_day.html", {
            "user_journey": user_journey,
        })
    return _render_day(request, user_journey, day, review_mode=False, welcome_back=welcome_back)


@login_required
def journey_review_day(request, arc_slug: str, day_number: int):
    """Addressable read-only review of a past day."""
    user_journey = get_active_journey(request.user)
    if user_journey is None:
        return _render_no_journey(request)
    day = get_day_in_arc(arc_slug, day_number)
    if day is None:
        return HttpResponseNotFound("Day not found.")
    if not can_view_day(user_journey, day):
        return HttpResponseForbidden("This day is not yet available on your journey.")
    review_mode = (day.id != getattr(get_current_day(user_journey), "id", None))
    return _render_day(request, user_journey, day, review_mode=review_mode)


@login_required
@require_POST
def journey_start(request):
    """Start the canonical Walking With God journey."""
    try:
        uj = get_or_create_journey(request.user, JOURNEY_PATH_SLUG)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect(reverse("journey:today"))
    messages.success(request, f"Welcome to {uj.journey_path.name}.")
    return redirect(reverse("journey:today"))


@login_required
def journey_settings(request):
    user_journey = get_active_journey(request.user)
    if user_journey is None:
        return _render_no_journey(request)
    if request.method == "POST":
        form = JourneySettingsForm(request.POST, instance=user_journey)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings updated.")
            return redirect(reverse("journey:settings"))
    else:
        form = JourneySettingsForm(instance=user_journey)
    return render(request, "faith/journey/settings.html", {
        "form": form,
        "user_journey": user_journey,
    })


@login_required
@require_POST
def journey_complete_day(request, arc_slug: str, day_number: int):
    user_journey = get_active_journey(request.user)
    if user_journey is None:
        return HttpResponseForbidden("No active journey.")
    day = get_day_in_arc(arc_slug, day_number)
    if day is None:
        return HttpResponseNotFound("Day not found.")
    if not can_view_day(user_journey, day):
        return HttpResponseForbidden("Day not available.")

    form = CompleteDayForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest("Invalid form data.")

    mark_day_complete(
        user_journey,
        day,
        reflection_notes=form.cleaned_data["reflection_notes"],
        application_committed=form.cleaned_data["application_committed"],
    )
    messages.success(request, "Day complete. Tomorrow's reading is ready.")
    return redirect(reverse("journey:today"))


# ---------------------------------------------------------------------------
# Annotation endpoints (reuse-only — create rows in existing models)
# ---------------------------------------------------------------------------

def _parse_json_body(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def _require_active_user_journey(request):
    if not request.user.is_authenticated:
        return None, JsonResponse({"error": "auth_required"}, status=401)
    user_journey = get_active_journey(request.user)
    if user_journey is None:
        return None, JsonResponse({"error": "no_active_journey"}, status=400)
    return user_journey, None


@login_required
@require_POST
def annotation_highlight_create(request):
    """Create a BibleHighlight for the verse currently being read."""
    user_journey, error = _require_active_user_journey(request)
    if error:
        return error
    data = _parse_json_body(request)
    if not data:
        return JsonResponse({"error": "invalid_json"}, status=400)
    try:
        parsed = parse_reference(data["reference"])
    except (KeyError, ValueError) as e:
        return JsonResponse({"error": "invalid_reference", "detail": str(e)}, status=400)
    color = data.get("color", "yellow")
    text = data.get("text", "")
    if not text:
        return JsonResponse({"error": "missing_text"}, status=400)

    h = BibleHighlight.objects.create(
        user=request.user,
        reference=parsed.display(),
        text=text,
        translation="WEB",
        book_name=parsed.book_name,
        book_order=parsed.book_order,
        chapter=parsed.chapter,
        verse_start=parsed.verse_start,
        verse_end=parsed.verse_end,
        color=color,
    )
    return JsonResponse({"id": h.id, "color": h.color, "reference": h.reference})


@login_required
@require_POST
def annotation_bookmark_create(request):
    """Create a BibleBookmark for the chapter or specific verse."""
    user_journey, error = _require_active_user_journey(request)
    if error:
        return error
    data = _parse_json_body(request)
    if not data:
        return JsonResponse({"error": "invalid_json"}, status=400)
    try:
        parsed = parse_reference(data["reference"])
    except (KeyError, ValueError) as e:
        return JsonResponse({"error": "invalid_reference", "detail": str(e)}, status=400)

    bookmark = BibleBookmark.objects.create(
        user=request.user,
        reference=parsed.display(),
        translation="WEB",
        book_name=parsed.book_name,
        book_order=parsed.book_order,
        chapter=parsed.chapter,
        verse=parsed.verse_start if data.get("include_verse") else None,
        title=data.get("title", ""),
        notes=data.get("notes", ""),
    )
    return JsonResponse({"id": bookmark.id, "reference": bookmark.reference})


@login_required
@require_POST
def annotation_save_verse(request):
    """Save a verse to the user's SavedVerse collection."""
    user_journey, error = _require_active_user_journey(request)
    if error:
        return error
    data = _parse_json_body(request)
    if not data:
        return JsonResponse({"error": "invalid_json"}, status=400)
    try:
        parsed = parse_reference(data["reference"])
    except (KeyError, ValueError) as e:
        return JsonResponse({"error": "invalid_reference", "detail": str(e)}, status=400)
    text = data.get("text", "")
    if not text:
        return JsonResponse({"error": "missing_text"}, status=400)

    sv = SavedVerse.objects.create(
        user=request.user,
        reference=parsed.display(),
        text=text,
        translation="WEB",
        book_name=parsed.book_name,
        book_order=parsed.book_order,
        chapter=parsed.chapter,
        verse_start=parsed.verse_start,
        verse_end=parsed.verse_end,
        is_memory_verse=bool(data.get("is_memory_verse", False)),
    )
    return JsonResponse({"id": sv.id, "reference": sv.reference, "is_memory_verse": sv.is_memory_verse})


@login_required
@require_POST
def confusion_flagged(request):
    """Fire journey.confusion.flagged when the user taps a confusion topic.

    Internal observability only. No response surface beyond a 204.
    """
    user_journey = get_active_journey(request.user)
    data = _parse_json_body(request) or {}
    arc_slug = data.get("arc_slug", "")
    day_number = data.get("day_number")
    topic = data.get("topic", "")
    if not arc_slug or not isinstance(day_number, int) or not topic:
        return HttpResponseBadRequest("missing fields")
    from apps.faith.journey.signals import emit_confusion_flagged
    emit_confusion_flagged(
        request.user,
        user_journey=user_journey,
        arc_slug=arc_slug,
        day_number=day_number,
        topic=topic,
    )
    return HttpResponse(status=204)


@login_required
@require_POST
def annotation_note_create(request):
    """Create a BibleStudyNote attached to a verse or passage."""
    user_journey, error = _require_active_user_journey(request)
    if error:
        return error
    data = _parse_json_body(request)
    if not data:
        return JsonResponse({"error": "invalid_json"}, status=400)
    try:
        parsed = parse_reference(data["reference"])
    except (KeyError, ValueError) as e:
        return JsonResponse({"error": "invalid_reference", "detail": str(e)}, status=400)
    content = data.get("content", "")
    title = data.get("title", "")
    if not content:
        return JsonResponse({"error": "missing_content"}, status=400)

    note = BibleStudyNote.objects.create(
        user=request.user,
        reference=parsed.display(),
        translation="WEB",
        book_name=parsed.book_name,
        book_order=parsed.book_order,
        chapter=parsed.chapter,
        verse_start=parsed.verse_start,
        verse_end=parsed.verse_end,
        title=title,
        content=content,
    )
    return JsonResponse({"id": note.id, "reference": note.reference})
