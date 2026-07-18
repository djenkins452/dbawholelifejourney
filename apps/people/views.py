"""Canonical Person management endpoints.

Recognition-phrase CRUD is the first user-facing management surface on the canonical
``people.Person``. Every phrase written here is a canonical ``RecognitionPhrase`` — the
ONE authority every consumer (Journal @mentions, passive recognition, the resolver, the
lookup API) already reads. There is no module-specific nickname logic anywhere: add a
phrase here and every surface recognizes it automatically.

These endpoints operate purely on the canonical Person (user-scoped ownership) and are
host-agnostic — any page (today the Person detail page) can POST to them and pass its own
``next`` to return to. All writes go through the single ``services.phrases`` write path,
so provenance events are recorded and the derived/custom/learned invariants hold.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import DetailView

from .models import Person, RecognitionPhrase
from .normalization import normalize_name
from .services import phrases as phrase_service


class PersonDetailView(LoginRequiredMixin, DetailView):
    """The canonical Person page — today, the home for recognition-phrase management
    (works for ANY canonical Person, independent of legacy source links). A
    ``UserOwnedModel`` DetailView, so its Current Context is auto-declared. The fuller
    People experience arrives with the consumer-migration UI; this ships the management
    surface the recognition feature needs now."""

    model = Person
    template_name = "people/person_detail.html"
    context_object_name = "canonical_person"

    def get_queryset(self):
        return Person.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        person = self.object
        ctx["person_label"] = person.display_name
        ctx["auto_names"] = phrase_service.derived_display_names(person)
        from .services import hooks
        ctx["role_phrases"] = hooks.person_roles(self.request.user, person)
        ctx["custom_phrases"] = list(
            person.recognition_phrases.all().order_by("phrase"))
        return ctx


def _person(request, pk):
    """The canonical Person, enforcing ownership (never another user's Person)."""
    return get_object_or_404(Person, pk=pk, user=request.user)


def _safe_next(request):
    """Where to return after a write — the caller's own page, validated as internal."""
    nxt = request.POST.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return "/"


def _already_recognized(person, normalized, *, exclude_pk=None):
    """A phrase is a duplicate if it already resolves to this person — whether as a
    derived name or an existing custom/learned phrase. Prevents clutter and collisions."""
    if normalized in set(phrase_service.derived_phrases(person)):
        return True
    qs = person.recognition_phrases.filter(normalized=normalized)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


@login_required
@require_POST
def phrase_add(request, pk):
    """Add a custom recognition phrase ("Honey", "Babe") to a canonical Person."""
    person = _person(request, pk)
    nxt = _safe_next(request)
    text = (request.POST.get("phrase") or "").strip()
    normalized = normalize_name(text)
    if not normalized:
        messages.error(request, "Enter a recognition phrase.")
        return redirect(nxt)
    if _already_recognized(person, normalized):
        messages.info(request, f'“{text}” is already recognized for {person.display_name}.')
        return redirect(nxt)
    phrase_service.add_custom_phrase(person, text)
    messages.success(
        request, f'“{text}” will now be recognized as {person.display_name}.')
    return redirect(nxt)


@login_required
@require_POST
def phrase_edit(request, pk, phrase_pk):
    """Rename a custom/learned phrase, preserving canonical identity and provenance."""
    person = _person(request, pk)
    rp = get_object_or_404(RecognitionPhrase, pk=phrase_pk, person=person)
    nxt = _safe_next(request)
    text = (request.POST.get("phrase") or "").strip()
    normalized = normalize_name(text)
    if not normalized:
        messages.error(request, "A recognition phrase can’t be empty.")
        return redirect(nxt)
    if normalized == rp.normalized:                       # only capitalization/no change
        if text != rp.phrase:
            rp.phrase = text
            rp.save(update_fields=["phrase", "normalized"])
        return redirect(nxt)
    if _already_recognized(person, normalized, exclude_pk=rp.pk):
        messages.info(request, f'“{text}” is already recognized for {person.display_name}.')
        return redirect(nxt)
    # Rename through the single write path: drop the old, store the new (keeps source).
    source = rp.source
    phrase_service.remove_phrase(person, rp.phrase)
    phrase_service._store(person, text, source)
    messages.success(request, f'Updated to “{text}”.')
    return redirect(nxt)


@login_required
@require_POST
def phrase_delete(request, pk, phrase_pk):
    """Remove a custom/learned recognition phrase (derived names are read-only truth)."""
    person = _person(request, pk)
    rp = get_object_or_404(RecognitionPhrase, pk=phrase_pk, person=person)
    nxt = _safe_next(request)
    phrase_service.remove_phrase(person, rp.phrase)
    messages.success(request, f'Removed “{rp.phrase}”.')
    return redirect(nxt)
