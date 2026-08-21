# ==============================================================================
# File: apps/core/migrations/0137_accept_owner_legacy_personal_knowledge.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: One-time, account-scoped acceptance of the owner's legacy PK corpus
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-20
# ==============================================================================
"""Accept ONE named account's already-imported legacy Personal Knowledge as reviewed.

**Explicit owner authorization (2026-08-20).** M5 human validation surfaced 217 unreviewed
legacy facts in Danny's account. Reviewing them one at a time was safe but is not a product
experience anyone should be asked to complete. As product owner — with WLJ pre-production
and ~99% of accounts belonging to testers — Danny explicitly accepted the risk that his own
historical Personal Knowledge contains stale, noisy or compound records, and authorized
accepting the corpus wholesale rather than certifying it record by record.

**This is a migration, not a policy.** The safe legacy-review architecture remains the
default for every future real user. There is no "trust legacy imports" rule, and no Danny
special-case in runtime behaviour — this runs once, for one explicitly named address, and
then it is history.

**It removes the REVIEW gate and nothing else.** Acceptance flips `review_state` only.
Sensitivity exclusion, the domain boundary, deletion/supersession state and every other
standing-context eligibility rule continue to apply exactly as before. Statement text is
never rewritten, compound records are never split, topics are never inferred, near
duplicates are never merged, and the legacy source stores are left intact for M7.
"""

from django.db import migrations

OWNER_EMAIL = "dannyjenkins71@gmail.com"


def accept_owner_legacy_corpus(apps, schema_editor):
    User = apps.get_model("users", "User")
    Fact = apps.get_model("core", "PersonalKnowledgeFact")

    owner = User.objects.filter(email__iexact=OWNER_EMAIL).first()
    if owner is None:
        print(f"  PK acceptance skipped — {OWNER_EMAIL} not present in this database")
        return

    # Scoped THREE ways on purpose: this user, still-active rows, and only the legacy
    # imports that are actually waiting on the review gate. Nothing else is touched.
    qs = Fact.objects.filter(
        user_id=owner.id,
        fact_status="active",
        review_state="unreviewed",
        provenance="legacy_extraction",
    )
    accepted = qs.update(review_state="reviewed")

    # The projection cache is keyed per user, so a stale read would keep the newly
    # accepted knowledge invisible to the model until it expired.
    try:
        from apps.ai.cos_services import personal_truth
        personal_truth.invalidate(owner)   # expects the USER, not an id
    except Exception:  # pragma: no cover - cache is best-effort, never fatal
        pass

    remaining = Fact.objects.filter(
        user_id=owner.id, fact_status="active", review_state="unreviewed").count()
    print(f"  PK acceptance (owner-authorized): {accepted} legacy facts accepted; "
          f"{remaining} unreviewed remain for this account")


def unaccept(apps, schema_editor):
    """Deliberately NOT reversible.

    Reverting would re-gate knowledge the owner has explicitly accepted, and could not
    distinguish these records from anything reviewed normally afterwards. Removing the
    migration is not how you undo a product decision — About Me is, per-fact.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0136_personalknowledgefact"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(accept_owner_legacy_corpus, unaccept),
    ]
