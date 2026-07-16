"""The deterministic resolution service — the one way to identify a Person."""

from django.test import TestCase

from apps.people.models import Person
from apps.people.services import hooks, phrases, resolution

from ._helpers import make_user


class ResolutionTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.heather = Person.objects.create(
            user=self.user, first_name="Heather", last_name="Jenkins")
        self.haley = Person.objects.create(
            user=self.user, first_name="Haley", last_name="Jenkins")

    def tearDown(self):
        hooks._reset_for_tests()

    def test_exact_full_name_resolves(self):
        r = resolution.resolve(self.user, "Heather Jenkins")
        self.assertTrue(r.is_resolved)
        self.assertEqual(r.person.pk, self.heather.pk)
        self.assertEqual(r.source_type, resolution.EXACT_NAME)

    def test_unique_first_name_resolves(self):
        r = resolution.resolve(self.user, "Haley")
        self.assertTrue(r.is_resolved)
        self.assertEqual(r.person.pk, self.haley.pk)

    def test_compact_handle_resolves(self):
        r = resolution.resolve(self.user, "@HeatherJenkins")
        self.assertTrue(r.is_resolved)
        self.assertEqual(r.person.pk, self.heather.pk)

    def test_duplicate_first_name_is_ambiguous(self):
        Person.objects.create(user=self.user, first_name="Heather", last_name="Smith")
        r = resolution.resolve(self.user, "Heather")
        self.assertTrue(r.is_ambiguous)
        self.assertEqual(len(r.candidates), 2)

    def test_unresolved_when_unknown(self):
        r = resolution.resolve(self.user, "Nobody Here")
        self.assertEqual(r.status, resolution.UNRESOLVED)
        self.assertIsNone(r.person)

    def test_confirmed_phrase_resolves(self):
        phrases.add_custom_phrase(self.heather, "Honey")
        r = resolution.resolve(self.user, "honey")
        self.assertTrue(r.is_resolved)
        self.assertEqual(r.person.pk, self.heather.pk)
        self.assertEqual(r.source_type, resolution.CONFIRMED_ALIAS)

    def test_derived_role_resolves_via_registered_resolver(self):
        # A feature module (Relationships/Legacy) registers a role resolver.
        def wife_resolver(user, normalized_role):
            if normalized_role in {"wife", "my wife"} and user.id == self.user.id:
                return self.heather
            return None
        hooks.register_role_resolver(wife_resolver)

        r = resolution.resolve(self.user, "my wife")
        self.assertTrue(r.is_resolved)
        self.assertEqual(r.person.pk, self.heather.pk)
        self.assertEqual(r.source_type, resolution.RELATIONSHIP_ROLE)

    def test_role_unresolved_when_no_resolver_registered(self):
        # Phase 0b default: no feature resolver wired yet → role does not resolve.
        r = resolution.resolve(self.user, "my wife")
        self.assertEqual(r.status, resolution.UNRESOLVED)

    def test_conflicting_role_resolvers_are_ambiguous_none(self):
        hooks.register_role_resolver(lambda u, role: self.heather if role == "cousin" else None)
        hooks.register_role_resolver(lambda u, role: self.haley if role == "cousin" else None)
        r = resolution.resolve(self.user, "cousin")
        self.assertEqual(r.status, resolution.UNRESOLVED)  # conflict → no guess

    def test_resolution_is_user_scoped(self):
        other = make_user("other@example.com")
        r = resolution.resolve(other, "Heather Jenkins")
        self.assertEqual(r.status, resolution.UNRESOLVED)
