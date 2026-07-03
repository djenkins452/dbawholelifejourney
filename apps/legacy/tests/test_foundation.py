"""Phase 1 foundation tests for the Legacy domain."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import get_domain_truth
from apps.core.truth.entity import CompleteEntity
from apps.legacy.models import Media, Memory, Person

User = get_user_model()


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class RegistryTests(TestCase):
    def test_preservation_domain_class_exists(self):
        from apps.core.domain_registry.descriptors import DomainClass
        self.assertEqual(DomainClass.PRESERVATION, "preservation")
        self.assertIn(DomainClass.PRESERVATION, DomainClass.ALL)
        # Standalone in Phase 1 — kept out of user-life/CoS iteration sets so it
        # never gets pulled into cross-domain reasoning before the assistant phase.
        self.assertNotIn(DomainClass.PRESERVATION, DomainClass.USER_LIFE_DOMAINS)
        self.assertNotIn(DomainClass.PRESERVATION, DomainClass.COS_PARTICIPATING)

    def test_legacy_capability_registered(self):
        from apps.core.domain_registry import registry
        from apps.core.domain_registry.descriptors import DomainClass
        cap = registry.get("legacy")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.domain_class, DomainClass.PRESERVATION)
        self.assertEqual(cap.url_namespace, "legacy")

    def test_module_catalog_seeded(self):
        from apps.users.models import ModuleDefinition
        self.assertTrue(ModuleDefinition.objects.filter(slug="legacy").exists())


class DomainTruthTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_describe_returns_complete_entities(self):
        Memory.objects.create(user=self.user, title="The shop", body="It rained.")
        truth = get_domain_truth(self.user, "legacy")
        entities = truth.describe("memory")
        self.assertTrue(entities)
        self.assertIsInstance(entities[0], CompleteEntity)
        self.assertEqual(entities[0].identity, "The shop")
        # Preservation-shaped provenance lives in extensions.
        self.assertIn("provenance", entities[0].extensions)

    def test_current_metric(self):
        Memory.objects.create(user=self.user, title="A")
        Memory.objects.create(user=self.user, title="B")
        truth = get_domain_truth(self.user, "legacy")
        ct = truth.current("total_memories")
        self.assertIsInstance(ct, CurrentTruth)
        self.assertEqual(ct.value, 2)


class ModelTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_defaults_and_links(self):
        person = Person.objects.create(user=self.user, display_name="Dad")
        m = Memory.objects.create(user=self.user, title="Fishing")
        m.people.add(person)
        self.assertEqual(m.entry_state, Memory.EntryState.DRAFT)
        self.assertEqual(m.source_kind, Memory.SourceKind.OWNER)
        self.assertEqual(person.memories.count(), 1)

    def test_soft_delete(self):
        m = Memory.objects.create(user=self.user, title="X")
        m.soft_delete()
        self.assertFalse(Memory.objects.filter(pk=m.pk).exists())
        self.assertTrue(Memory.all_objects.filter(pk=m.pk).exists())

    def test_media_is_evidence_carrier(self):
        media = Media.objects.create(user=self.user, media_type=Media.MediaType.PHOTO)
        m = Memory.objects.create(user=self.user, title="With photo", primary_media=media)
        m.media.add(media)
        self.assertEqual(m.media.count(), 1)
        self.assertEqual(media.memories.count(), 1)


class ViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_home_renders_with_sample_when_empty(self):
        resp = self.client.get(reverse("legacy:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Welcome home")
        self.assertContains(resp, "Tell your story")
        # Sample fallback content present when there is no real data.
        self.assertContains(resp, "First Day of School")

    def test_home_uses_real_data_when_present(self):
        Memory.objects.create(
            user=self.user, title="Opening Day", body="We opened the shop.",
            entry_state=Memory.EntryState.LEGACY,
        )
        resp = self.client.get(reverse("legacy:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Opening Day")
        self.assertNotContains(resp, "First Day of School")

    def test_placeholder_pages_render(self):
        # Timeline became real (Life Milestones); relationships/search/settings remain.
        for name in ("relationships", "search", "settings"):
            resp = self.client.get(reverse(f"legacy:{name}"))
            self.assertEqual(resp.status_code, 200, name)
            self.assertContains(resp, "being prepared")

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse("legacy:home"))
        self.assertEqual(resp.status_code, 302)
