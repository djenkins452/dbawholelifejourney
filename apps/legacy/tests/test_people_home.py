"""People Home: close family first, browse-all paginated, search spans everyone."""

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


class PeopleHomeTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def _p(self, name, **kw):
        return Person.objects.create(user=self.user, display_name=name, **kw)

    def _parent(self, parent, child):
        Relationship.objects.create(user=self.user, from_person=parent,
                                    to_person=child, relationship_type="parent of")

    def _spouse(self, a, b):
        Relationship.objects.create(user=self.user, from_person=a,
                                    to_person=b, relationship_type="married to")

    def test_home_shows_close_family_not_everyone(self):
        me = self._p("Me", is_self=True)
        dad = self._p("Dad"); self._parent(dad, me)
        sib = self._p("Sib"); self._parent(dad, sib)
        sp = self._p("Spouse"); self._spouse(me, sp)
        kid = self._p("Kiddo"); self._parent(me, kid)
        self._p("Zzz Stranger")   # in the DB but not close family
        r = self.client.get(reverse("legacy:people"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["mode"], "home")
        for name in ("Dad", "Sib", "Spouse", "Kiddo"):
            self.assertContains(r, name)
        self.assertNotContains(r, "Zzz Stranger")          # not on the home view
        self.assertContains(r, "Browse all")               # browse-everyone affordance

    def test_home_relatives_helper(self):
        me = self._p("Me", is_self=True)
        dad = self._p("Dad"); self._parent(dad, me)
        h = family_tree.home_relatives(self.user)
        self.assertEqual(h["me"].pk, me.pk)
        self.assertEqual([p.display_name for p in h["parents"]], ["Dad"])

    def test_no_me_falls_back_to_browse(self):
        self._p("Someone")   # no is_self, no name match
        r = self.client.get(reverse("legacy:people"))
        self.assertEqual(r.context["mode"], "all")
        self.assertTrue(r.context.get("no_me"))
        self.assertContains(r, "Someone")

    def test_browse_all_paginated(self):
        self._p("Me", is_self=True)
        for i in range(45):
            self._p("Person %02d" % i)
        r = self.client.get(reverse("legacy:people"), {"view": "all"})
        self.assertEqual(r.context["mode"], "all")
        self.assertEqual(r.context["page_obj"].paginator.num_pages, 2)   # 46 / 40
        self.assertEqual(len(r.context["page_obj"].object_list), 40)
        r2 = self.client.get(reverse("legacy:people"), {"view": "all", "page": 2})
        self.assertTrue(r2.context["page_obj"].has_previous())
        self.assertFalse(r2.context["page_obj"].has_next())

    def test_search_spans_everyone_paginated(self):
        self._p("Me", is_self=True)
        self._p("Findable Cousin")
        r = self.client.get(reverse("legacy:people"), {"q": "findable"})
        self.assertEqual(r.context["mode"], "search")
        self.assertContains(r, "Findable Cousin")

    def test_empty_state(self):
        r = self.client.get(reverse("legacy:people"))
        self.assertContains(r, "will gather here")
