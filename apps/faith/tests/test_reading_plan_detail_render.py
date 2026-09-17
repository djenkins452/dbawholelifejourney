"""The reading-plan detail page renders titles as words, not letters.

Origin: `/faith/reading-plans/surrendering-blind-spots/` showed every day title as
"D, o, I, H, a, v, e, …". The stored data was correct — titles are strings, references
are lists, for every plan in production. The template did
`{{ d.title|default:d.scripture_references|join:", " }}`: Django filters chain left to
right, so when the title existed `default` returned the STRING and `join` iterated its
characters. These tests push real strings through the real template and would fail if
anything joins a title again.
"""
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.faith.models import ReadingPlanDay, ReadingPlanTemplate

User = get_user_model()

TITLES = [
    "Do I Have a Control Problem?",
    "The Root of Control - Worry",
    "The Illusion of Control",
    "Control's Ugly Tools",
    "Trust - The Opposite of Control",
    "Waving the White Flag",
]
REFS = [
    ["Genesis 2:15-25", "Genesis 3:1-7"],
    ["Matthew 6:25-27"],
    ["Matthew 6:28-32"],
    ["James 4:1-10"],
    ["Matthew 6:25-34"],
    ["1 Peter 5:6-11", "Psalm 37:1-9"],
]

# "D, o, I" — any run of single characters separated by ", " is the defect's fingerprint.
LETTER_JOIN = re.compile(r"(?:\b[A-Za-z], ){3,}")


def _user(email, first_light):
    from django.conf import settings
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password="x-passphrase-123")
    TermsAcceptance.objects.create(user=user, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"])
    prefs = user.preferences
    prefs.faith_enabled = True
    prefs.has_completed_onboarding = True
    ff = dict(prefs.faith_features or {})
    ff["first_light"] = first_light
    prefs.faith_features = ff
    prefs.save()
    return user


def _plan(slug="surrendering-blind-spots", days=6, titled=True):
    plan = ReadingPlanTemplate.objects.create(
        title="Surrendering My Blind Spots", slug=slug, description="d",
        category="topical", difficulty="beginner", duration_days=days,
        is_active=True, is_featured=False)
    for i in range(days):
        ReadingPlanDay.objects.create(
            plan=plan, day_number=i + 1,
            title=TITLES[i % len(TITLES)] if titled else "",
            scripture_references=REFS[i % len(REFS)])
    return plan


class FirstLightDetailRendersTitlesAsText(TestCase):

    def setUp(self):
        self.user = _user("fl-detail@example.com", first_light=True)
        self.client.login(email="fl-detail@example.com", password="x-passphrase-123")

    def _get(self, plan):
        r = self.client.get(reverse("faith:reading_plan_detail", kwargs={"slug": plan.slug}))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "faith/reading_plans/detail_first_light.html")
        return r.content.decode()

    def test_every_title_appears_whole(self):
        html = self._get(_plan())
        for title in TITLES:
            self.assertIn(title.replace("'", "&#x27;"), html)
        self.assertIsNone(LETTER_JOIN.search(html), "a title was joined character by character")

    def test_references_render_beside_each_title(self):
        html = self._get(_plan())
        self.assertIn("Genesis 2:15-25, Genesis 3:1-7", html)
        self.assertIn("1 Peter 5:6-11, Psalm 37:1-9", html)

    def test_each_day_once_in_order(self):
        html = self._get(_plan())
        nums = re.findall(r'class="fl-day-num fl-tnum">(\d+)<', html)
        self.assertEqual(nums, ["1", "2", "3", "4", "5", "6"])
        for title in TITLES:
            escaped = title.replace("'", "&#x27;")
            self.assertEqual(html.count(f'class="fl-day-title">{escaped}<'), 1, title)

    def test_untitled_day_falls_back_to_references_as_a_list(self):
        html = self._get(_plan(slug="untitled", days=2, titled=False))
        self.assertIn('class="fl-day-title">Genesis 2:15-25, Genesis 3:1-7<', html)
        self.assertIsNone(LETTER_JOIN.search(html))

    def test_heading_is_honest_about_how_many_days_are_shown(self):
        # A 6-day plan previews all 6 — "the first days" would imply more.
        self.assertIn("Every day of the journey", self._get(_plan()))
        # A 30-day plan previews 7.
        html = self._get(_plan(slug="long", days=30))
        self.assertIn("The first 7 days", html)
        self.assertIn("30 in all", html)
        self.assertEqual(len(re.findall(r'class="fl-day-num fl-tnum">', html)), 7)

    def test_sample_day_title_is_whole(self):
        html = self._get(_plan())
        self.assertIn("Day 1 · Do I Have a Control Problem?", html)


class ClassicDetailRendersTitlesAsText(TestCase):
    """The non-First-Light template must hold the same line."""

    def test_titles_whole(self):
        _user("classic@example.com", first_light=False)
        self.client.login(email="classic@example.com", password="x-passphrase-123")
        plan = _plan()
        r = self.client.get(reverse("faith:reading_plan_detail", kwargs={"slug": plan.slug}))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Do I Have a Control Problem?", html)
        self.assertIsNone(LETTER_JOIN.search(html))


class NoTemplateJoinsAString(TestCase):
    """Static guard for the whole Faith template tree: `|join` may only follow a value
    that is a list. A `|default:<list>|join` chain is exactly the defect and is rejected
    outright; every other `|join` must sit on a known list-valued field."""

    LIST_FIELDS = {"scripture_references", "scripture_refs", "topics"}

    def test_no_default_then_join(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[3] / "templates" / "faith"
        offenders = []
        for path in root.rglob("*.html"):
            for n, line in enumerate(path.read_text().splitlines(), 1):
                for m in re.finditer(r"\{\{\s*([^}]*?)\|join:", line):
                    chain = m.group(1)
                    if "|default:" in chain:
                        offenders.append(f"{path.relative_to(root)}:{n}: {chain}|join")
                        continue
                    head = chain.split("|")[0].strip().rsplit(".", 1)[-1]
                    if head not in self.LIST_FIELDS:
                        offenders.append(f"{path.relative_to(root)}:{n}: {chain}|join (not a known list)")
        self.assertEqual(offenders, [])
