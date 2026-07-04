"""Relationship graph integrity — no name-merge, correct parents, user binding, rebuild."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import LegacyProfile, Person, Relationship
from apps.legacy.services import import_engine
from apps.legacy.services.import_engine import commit_genealogy, create_batch
from apps.legacy.services.self_binding import bind_self, get_self_person

User = get_user_model()


def _make_user(email="keeper@example.com", first="", last=""):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!", first_name=first, last_name=last)
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _boom(units):
    raise AssertionError("classifier must not run for GEDCOM")


# Two DISTINCT individuals share the name "James Robertson" — each with their OWN
# two parents. The old name-merging importer collapsed them into one person with
# four parents; the fix must keep them separate.
GED_COLLISION = """0 HEAD
0 @I1@ INDI
1 NAME James /Robertson/
0 @I2@ INDI
1 NAME Mary /Ash/
0 @I3@ INDI
1 NAME John /Ash/
0 @I4@ INDI
1 NAME James /Robertson/
0 @I5@ INDI
1 NAME Sue /Bell/
0 @I6@ INDI
1 NAME Bob /Bell/
0 @F1@ FAM
1 HUSB @I3@
1 WIFE @I2@
1 CHIL @I1@
0 @F2@ FAM
1 HUSB @I6@
1 WIFE @I5@
1 CHIL @I4@
0 TRLR
"""


class NoNameMergeTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_distinct_individuals_stay_distinct(self):
        commit_genealogy(create_batch(self.user, "T", "gedcom", GED_COLLISION, classifier=_boom))
        jameses = Person.objects.filter(user=self.user, display_name="James Robertson")
        self.assertEqual(jameses.count(), 2)                       # NOT merged by name
        for j in jameses:
            n = Relationship.objects.filter(
                user=self.user, to_person=j, relationship_type="parent of").count()
            self.assertEqual(n, 2)                                 # exactly two parents each
        self.assertEqual(import_engine.validate_family_graph(self.user), [])  # no impossibilities

    def test_recommit_is_idempotent_per_xref(self):
        batch = create_batch(self.user, "T", "gedcom", GED_COLLISION, classifier=_boom)
        commit_genealogy(batch)
        commit_genealogy(batch)   # again
        self.assertEqual(Person.objects.filter(user=self.user).count(), 6)   # no duplicates


class BindingTests(TestCase):
    def test_binding_persists_via_profile(self):
        user = _make_user()
        p = Person.objects.create(user=user, display_name="Someone")
        bind_self(user, p)
        self.assertEqual(get_self_person(user), p)
        self.assertTrue(LegacyProfile.objects.filter(user=user, self_person=p).exists())
        p.refresh_from_db(); self.assertTrue(p.is_self)

    def test_fuzzy_name_match_binds_middle_name(self):
        user = _make_user("danny@x.com", first="Danny", last="Jenkins")
        p = Person.objects.create(user=user, display_name="Danny Ray Jenkins")
        self.assertEqual(get_self_person(user), p)                 # first+last tokens match
        self.assertTrue(LegacyProfile.objects.filter(user=user, self_person=p).exists())

    def test_this_is_me_view_binds(self):
        user = _make_user()
        self.client.force_login(user)
        p = Person.objects.create(user=user, display_name="Me")
        self.client.post(reverse("legacy:person_set_self", args=[p.pk]))
        self.assertEqual(get_self_person(user), p)


class RebuildTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_rebuild_fixes_name_merged_data(self):
        batch = create_batch(self.user, "T", "gedcom", GED_COLLISION, classifier=_boom)
        # Simulate the OLD buggy state: a single merged "James Robertson" with 4 parents,
        # created via import with no stories (a placeholder), plus its 4 grandparents.
        merged = Person.objects.create(user=self.user, display_name="James Robertson",
                                       created_via=Person.CREATED_VIA_IMPORT)
        for name in ("Mary Ash", "John Ash", "Sue Bell", "Bob Bell"):
            par = Person.objects.create(user=self.user, display_name=name,
                                        created_via=Person.CREATED_VIA_IMPORT)
            Relationship.objects.create(user=self.user, from_person=par,
                                        to_person=merged, relationship_type="parent of")
        self.assertTrue(import_engine.validate_family_graph(self.user))   # 4 parents → broken

        removed, created, links = import_engine.rebuild_genealogy(self.user)
        self.assertGreater(removed, 0)
        self.assertEqual(import_engine.validate_family_graph(self.user), [])   # healthy now
        jameses = Person.objects.filter(user=self.user, display_name="James Robertson")
        self.assertEqual(jameses.count(), 2)             # rebuilt as two distinct people

    def test_rebuild_preserves_people_with_stories(self):
        from apps.legacy.models import Memory
        kept = Person.objects.create(user=self.user, display_name="Storied Person",
                                     created_via=Person.CREATED_VIA_IMPORT)
        m = Memory.objects.create(user=self.user, title="A story"); m.people.add(kept)
        import_engine.rebuild_genealogy(self.user)
        self.assertTrue(Person.objects.filter(pk=kept.pk).exists())   # kept (has a story)

    def test_rebuild_view_renders_and_runs(self):
        self.client.force_login(self.user)
        create_batch(self.user, "T", "gedcom", GED_COLLISION, classifier=_boom)
        r = self.client.get(reverse("legacy:family_rebuild"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Rebuild your family tree")
        r2 = self.client.post(reverse("legacy:family_rebuild"))
        self.assertRedirects(r2, reverse("legacy:family"))
