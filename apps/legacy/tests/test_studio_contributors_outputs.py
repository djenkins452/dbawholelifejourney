"""Slice 4 tests — Dashboard/Studio, Review queue, Contributors, Outputs."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import Contributor, Media, Memory, Output, Person, Place

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


class DashboardTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)
        Memory.objects.create(user=self.user, title="D1")
        Memory.objects.create(user=self.user, title="L1", entry_state=Memory.EntryState.LEGACY)
        Person.objects.create(user=self.user, display_name="Dad")
        Place.objects.create(user=self.user, name="Shop")
        Media.objects.create(user=self.user, media_type=Media.MediaType.PHOTO)
        Contributor.objects.create(user=self.user, name="Sarah")

    def test_dashboard_counts_and_actions(self):
        r = self.client.get(reverse("legacy:dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Dashboard")
        self.assertContains(r, "New memory")   # quick action
        self.assertContains(r, "Needs you")
        self.assertEqual(r.context["counts"]["memories"], 2)
        self.assertEqual(r.context["counts"]["drafts"], 1)
        self.assertEqual(r.context["counts"]["legacy"], 1)
        self.assertEqual(r.context["counts"]["people"], 1)
        self.assertEqual(r.context["counts"]["contributors"], 1)
        # Expanded stats for the testing dashboard.
        for key in ("relationships", "imports", "imported_stories", "waiting_review", "suggestions"):
            self.assertIn(key, r.context["counts"])

    def test_status_filter_recent(self):
        r = self.client.get(reverse("legacy:dashboard"), {"status": "legacy"})
        titles = [m.title for m in r.context["recent"]]
        self.assertIn("L1", titles)
        self.assertNotIn("D1", titles)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("legacy:dashboard")).status_code, 302)


class ReviewQueueTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_sections_and_empty(self):
        r = self.client.get(reverse("legacy:studio"))
        self.assertContains(r, "Nothing needs tending")
        Memory.objects.create(user=self.user, title="Draft memory")
        Media.objects.create(user=self.user, media_type=Media.MediaType.PHOTO, caption="orphan photo")
        r2 = self.client.get(reverse("legacy:studio"))
        self.assertContains(r2, "Draft memory")
        self.assertContains(r2, "Unfinished memories")
        self.assertContains(r2, "Media without a story")

    def test_add_to_legacy_preserves_content(self):
        m = Memory.objects.create(user=self.user, title="Keep me", body="important text")
        self.client.post(reverse("legacy:memory_set_state", args=[m.pk]),
                        {"to": "legacy", "next": reverse("legacy:studio")})
        m.refresh_from_db()
        self.assertEqual(m.entry_state, Memory.EntryState.LEGACY)
        self.assertEqual(m.body, "important text")   # content NOT wiped
        self.assertEqual(m.updated_by, self.user)


class ContributorTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.other = _make_user("other@example.com")
        self.client.force_login(self.user)

    def test_list_create_edit_detail(self):
        self.assertContains(self.client.get(reverse("legacy:contributors")), "remembered together")
        self.client.post(reverse("legacy:contributor_new"),
                        {"name": "Sarah", "email": "s@x.com", "relationship_label": "your daughter",
                         "permission_level": "add"})
        c = Contributor.objects.get(name="Sarah")
        self.assertEqual(c.user, self.user)
        self.assertTrue(c.invite_token)   # placeholder token generated
        self.client.post(reverse("legacy:contributor_edit", args=[c.pk]),
                        {"name": "Sarah J", "email": "s@x.com", "relationship_label": "", "permission_level": "add"})
        c.refresh_from_db(); self.assertEqual(c.name, "Sarah J")
        r = self.client.get(reverse("legacy:contributor_detail", args=[c.pk]))
        self.assertEqual(r.status_code, 200)

    def test_detail_shows_attributed_contributions(self):
        c = Contributor.objects.create(user=self.user, name="Sarah")
        Memory.objects.create(user=self.user, title="Lake house summers", contributor=c,
                              source_kind=Memory.SourceKind.CONTRIBUTOR)
        r = self.client.get(reverse("legacy:contributor_detail", args=[c.pk]))
        self.assertContains(r, "Lake house summers")

    def test_cannot_view_others_contributor(self):
        c = Contributor.objects.create(user=self.other, name="Secret")
        self.assertEqual(self.client.get(reverse("legacy:contributor_detail", args=[c.pk])).status_code, 404)

    def test_archive(self):
        c = Contributor.objects.create(user=self.user, name="Temp")
        self.client.post(reverse("legacy:contributor_archive", args=[c.pk]))
        c.refresh_from_db(); self.assertEqual(c.status, "archived")


class OutputTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.other = _make_user("other2@example.com")
        self.client.force_login(self.user)

    def test_create_placeholder_output(self):
        self.assertContains(self.client.get(reverse("legacy:outputs")), "Make a gift")
        r = self.client.post(reverse("legacy:output_new"),
                            {"output_type": "memoir", "scope_kind": "whole_life",
                             "audience": "grandchildren", "title": "For the grandkids",
                             "scope_person": "", "scope_place": ""})
        self.assertEqual(r.status_code, 302)
        o = Output.objects.get(title="For the grandkids")
        self.assertEqual(o.user, self.user)
        self.assertEqual(o.output_type, Output.OutputType.MEMOIR)
        self.assertEqual(o.audience, Output.Audience.GRANDCHILDREN)
        # Output is a projection, never canonical — starts as a draft placeholder.
        self.assertEqual(o.generation_status, Output.GenerationStatus.DRAFT)

    def test_detail_and_listing(self):
        o = Output.objects.create(user=self.user, output_type=Output.OutputType.TIMELINE, title="My timeline")
        self.assertContains(self.client.get(reverse("legacy:outputs")), "My timeline")
        r = self.client.get(reverse("legacy:output_detail", args=[o.pk]))
        self.assertContains(r, "placeholder")

    def test_cannot_view_others_output(self):
        o = Output.objects.create(user=self.other, output_type=Output.OutputType.MEMOIR)
        self.assertEqual(self.client.get(reverse("legacy:output_detail", args=[o.pk])).status_code, 404)

    def test_archive(self):
        o = Output.objects.create(user=self.user, output_type=Output.OutputType.MEMOIR)
        self.client.post(reverse("legacy:output_archive", args=[o.pk]))
        o.refresh_from_db(); self.assertEqual(o.status, "archived")
