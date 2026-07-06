"""Relationship types — editable kind/status/span/notes; not every parent is a marriage."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import Person, Relationship
from apps.legacy.services import family_tree

User = get_user_model()


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class RelationshipTypeTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)
        self.a = Person.objects.create(user=self.user, display_name="Alice")
        self.b = Person.objects.create(user=self.user, display_name="Bob")

    def test_type_label(self):
        r = Relationship.objects.create(user=self.user, from_person=self.a,
                                        to_person=self.b, relationship_type="married to")
        self.assertEqual(r.type_label, "Spouse")
        r2 = Relationship.objects.create(user=self.user, from_person=self.a,
                                         to_person=self.b, relationship_type="")
        self.assertEqual(r2.type_label, "Unknown")

    def test_create_relationship_with_all_fields(self):
        r = self.client.post(reverse("legacy:relationship_new", args=[self.a.pk]), {
            "to_person": self.b.pk, "relationship_type": "former spouse of",
            "rel_status": "former", "started_year": "1997", "ended_year": "2010",
            "notes": "It was complicated.",
        })
        self.assertRedirects(r, reverse("legacy:person_detail", args=[self.a.pk]))
        rel = Relationship.objects.get(from_person=self.a, to_person=self.b)
        self.assertEqual(rel.relationship_type, "former spouse of")
        self.assertEqual(rel.rel_status, "former")
        self.assertEqual(rel.started_year, 1997)
        self.assertEqual(rel.ended_year, 2010)
        self.assertEqual(rel.notes, "It was complicated.")

    def test_create_requires_other_person(self):
        r = self.client.post(reverse("legacy:relationship_new", args=[self.a.pk]),
                             {"relationship_type": "friend of"})
        self.assertEqual(r.status_code, 200)   # re-rendered, not created
        self.assertFalse(Relationship.objects.filter(from_person=self.a).exists())

    def test_edit_relationship(self):
        rel = Relationship.objects.create(user=self.user, from_person=self.a,
                                          to_person=self.b, relationship_type="partner of")
        self.client.post(reverse("legacy:relationship_edit", args=[rel.pk]), {
            "relationship_type": "married to", "rel_status": "current",
            "started_year": "2015", "ended_year": "", "notes": "Married that year.",
        })
        rel.refresh_from_db()
        self.assertEqual(rel.relationship_type, "married to")
        self.assertEqual(rel.started_year, 2015)

    def test_delete_relationship(self):
        rel = Relationship.objects.create(user=self.user, from_person=self.a,
                                          to_person=self.b, relationship_type="friend of")
        self.client.post(reverse("legacy:relationship_delete", args=[rel.pk]))
        self.assertFalse(Relationship.objects.filter(pk=rel.pk).exists())

    def test_form_renders_with_types(self):
        r = self.client.get(reverse("legacy:relationship_new", args=[self.a.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Step-parent")
        self.assertContains(r, "Coworker")
        self.assertContains(r, "relPeople")   # picker index

    def test_new_types_map_into_family_graph(self):
        me = Person.objects.create(user=self.user, display_name="Me", is_self=True)
        guardian = Person.objects.create(user=self.user, display_name="Guardian")
        partner = Person.objects.create(user=self.user, display_name="Partner")
        Relationship.objects.create(user=self.user, from_person=guardian,
                                    to_person=me, relationship_type="guardian of")
        Relationship.objects.create(user=self.user, from_person=me,
                                    to_person=partner, relationship_type="partner of")
        home = family_tree.home_relatives(self.user)
        self.assertIn("Guardian", [p.display_name for p in home["parents"]])   # guardian → parent
        self.assertIn("Partner", [p.display_name for p in home["spouses"]])    # partner → spouse row
