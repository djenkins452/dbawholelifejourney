"""
Canonical Person read APIs — the one programmatic lookup/resolution surface.

Request-path-safe by construction: read-only, deterministic, user-scoped, no heavy
compute and no LLM (see docs/WLJ_REQUEST_PATH_SAFETY.md). These back @mention
suggestions, people pickers, and mention resolution across every consumer.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from .models import Person
from .normalization import normalize_name
from .services import resolution


def _person_json(p):
    return {
        "id": p.pk,
        "display_name": p.display_name,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "is_self": p.is_self,
        "is_deceased": p.is_deceased,
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
        people = [
            p for p in people
            if q in normalize_name(p.display_name) or q in normalize_name(p.full_name)
        ]
    else:
        people = list(people[:20])
    return JsonResponse({"results": [_person_json(p) for p in people[:20]]})


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
