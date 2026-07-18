"""Bridge a legacy relationships contact to its canonical people.Person.

Shared by the Person page (surface recognition management) and relationship-role
recognition (resolve "my wife" → the canonical spouse). Idempotent: after the first call
the PersonSourceLink exists and this short-circuits to a single indexed lookup. Uses the
canonical, dedup-safe reconciliation path (never a duplicate identity) and grants People
membership so recognition actually takes effect. Defensive — never raises.
"""
import logging

logger = logging.getLogger(__name__)


def ensure_canonical(user, rel_person):
    """Return the canonical people.Person for a relationships contact (creating/linking it
    on first call), or None if the bridge could not be established."""
    try:
        from apps.people.models import PersonMembership, PersonOrigin
        from apps.people.services.reconciliation import (
            MATCH_NAME_IDENTITY, ingest_source_person,
        )
        person, _outcome = ingest_source_person(
            user,
            source_domain="relationships", source_pk=rel_person.pk,
            display_name=rel_person.display_name or "",
            first_name=rel_person.first_name or "", last_name=rel_person.last_name or "",
            email=getattr(rel_person, "email", "") or "",
            phone=getattr(rel_person, "phone", "") or "",
            origin=PersonOrigin.CONTACT_IMPORT,
            membership_via=PersonMembership.Grant.CONTACT_IMPORT,
            match_mode=MATCH_NAME_IDENTITY,
        )
        return person
    except Exception:
        logger.warning("canonical bridge for relationships person %s failed",
                       getattr(rel_person, "pk", "?"), exc_info=True)
        return None
