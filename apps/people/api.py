"""
Canonical Person read APIs — the one programmatic lookup/resolution surface.

Request-path-safe by construction: read-only, deterministic, user-scoped, no heavy
compute and no LLM (see docs/WLJ_REQUEST_PATH_SAFETY.md). These back @mention
suggestions, people pickers, and mention resolution across every consumer.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse

from .models import Person
from .normalization import normalize_name
from .services import resolution
from .services import hooks
from .services.mentions import person_surfaces
from .services.phrases import derived_display_names


def _person_json(p):
    return {
        "id": p.pk,
        "display_name": p.display_name,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "is_self": p.is_self,
        "is_deceased": p.is_deceased,
        # Canonical display surfaces (first / full / display name + confirmed custom
        # phrases). The @mention picker chooses the label from these — never the raw typed
        # query — so an explicit selection can never save a partial search fragment.
        "surfaces": person_surfaces(p),
    }


@login_required
def lookup(request):
    """Autocomplete / picker: people whose name matches the query prefix.
    Deterministic, capped, user-scoped. ``members=1`` restricts to People members
    (living/everyday people) so @mention suggestions don't surface genealogy-only
    ancestors."""
    q = normalize_name(request.GET.get("q", ""))
    people = Person.objects.filter(user=request.user)
    if request.GET.get("members") in ("1", "true", "yes"):
        people = people.filter(membership__isnull=False)
    if q:
        # Match any canonical surface — name OR a confirmed custom phrase — so "@hon"
        # surfaces the person whose alias is "Honey", not just name matches.
        people = [
            p for p in people
            if any(q in normalize_name(s) for s in person_surfaces(p))
        ]
    else:
        people = list(people[:20])
    return JsonResponse({"results": [_person_json(p) for p in people[:20]]})


@login_required
def card(request, pk):
    """Lightweight data for the shared Person hover card — canonical identity + the
    words WLJ recognizes for this person + where to open them. User-scoped; cheap
    (canonical Person data + one hook round for feature facts). Used by the shared
    `wlj-person-hover` component on ANY page that renders a recognized person chip."""
    person = Person.objects.filter(user=request.user, pk=pk).first()
    if person is None:
        return JsonResponse({"error": "not_found"}, status=404)
    summary = hooks.person_summary(request.user, person)   # feature facts (relationship, url)
    role_phrases = hooks.person_roles(request.user, person)  # "my wife", "my daughter"
    return JsonResponse({
        "id": person.pk,
        "name": person.display_name,
        # Human-readable recognition surfaces: auto-recognized names + user nicknames.
        "auto_names": derived_display_names(person),
        "nicknames": [rp.phrase for rp in person.recognition_phrases.all().order_by("phrase")],
        "recognition": person_surfaces(person) + role_phrases,
        "relationship": summary.get("relationship", ""),
        # Prefer the rich feature page (relationships) when available; else the canonical
        # Person page. Both host the same Recognition management.
        "url": summary.get("url") or reverse("people:person_detail", args=[person.pk]),
    })


@login_required
def resolve(request):
    """Resolve a name/phrase to a canonical Person (or report ambiguity)."""
    text = request.GET.get("text", "")
    result = resolution.resolve(request.user, text)
    return JsonResponse({
        "text": result.text,
        "status": result.status,
        "source_type": result.source_type,
        "person": _person_json(result.person) if result.person else None,
        "candidates": [_person_json(p) for p in result.candidates],
    })
