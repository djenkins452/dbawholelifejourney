# ==============================================================================
# File: apps/ai/tests/test_agenda_time_frame.py
# Description: LAYER 4 COMPOSITION FIX (Move 1) — one sentence, one coherent time source.
#   The agenda/brief/orientation paths used to glue an item's own clock time ("Workout at
#   6:15 AM") to a frame derived from the CURRENT clock ("This evening…"), producing
#   contradictions like "This evening … at 6:15 AM". This proves the contradiction is now
#   structurally impossible: ahead items are framed by their OWN schedule relation
#   (upcoming), past items are OVERDUE (never upcoming), and no current-clock part-of-day
#   frame is ever wrapped around a timed item. Repair (which calls the brief) inherits it,
#   and existing non-time behavior (filtering, supplements) is unchanged.
# ==============================================================================
from unittest import mock
import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos import executive_brief as eb

User = get_user_model()
_NOW = "apps.core.utils.get_user_now"
_RHYTHM = "apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items"
_WORTH = "apps.ai.chatgpt_cos.executive_brief._agenda_worth_surfacing"
_DAYPART_FRAMES = ("this morning", "this afternoon", "this evening", "tonight")


def _at(h, m=0):
    return datetime.datetime(2026, 7, 3, h, m, tzinfo=datetime.timezone.utc)


def _item(title, hhmm, source_type="appointment"):
    return {"title": title, "scheduled_time": hhmm, "source_type": source_type}


def _mkuser(email):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class AgendaTimeFrameTests(TestCase):
    def setUp(self):
        self.u = _mkuser("agenda@example.com")

    def _narrative(self, now, items):
        # Isolate time-framing: surface every item regardless of the executive filter.
        with mock.patch(_NOW, return_value=now), \
             mock.patch(_RHYTHM, return_value=items), \
             mock.patch(_WORTH, return_value=True):
            return eb._agenda_narrative(self.u, recovery=False)

    def test_future_afternoon_item_not_framed_as_morning(self):
        # 11:50 AM, a 2:00 PM item is upcoming — must NOT be framed "this morning".
        n = self._narrative(_at(11, 50), [_item("Dentist appointment", "14:00")])
        self.assertIn("2:00 PM", n)
        self.assertIn("still ahead today", n.lower())
        for frame in _DAYPART_FRAMES:
            self.assertNotIn(frame, n.lower())

    def test_am_item_in_evening_is_overdue_never_am_tonight(self):
        # THE headline case: a 6:15 AM item, seen at 6 PM. It is OVERDUE — never "tonight".
        n = self._narrative(_at(18, 0), [_item("Workout", "06:15", "task")])
        self.assertIn("6:15 AM", n)
        self.assertIn("overdue", n.lower())
        self.assertNotIn("still ahead", n.lower())        # a past item is not upcoming
        for frame in _DAYPART_FRAMES:
            self.assertNotIn(frame, n.lower())            # no "6:15 AM ... this evening"

    def test_past_item_offers_the_executive_choice(self):
        n = self._narrative(_at(15, 0), [_item("Call the plumber", "09:00", "task")])
        self.assertIn("overdue", n.lower())
        self.assertIn("still need to happen", n.lower())

    def test_no_clock_daypart_frame_at_any_hour(self):
        # Sweep the clock against a mixed set of item times — the narrative must NEVER
        # contain a current-clock part-of-day frame wrapped around timed items.
        items = [_item("Dentist appointment", "14:00"), _item("Workout", "06:15", "task")]
        for h in (7, 9, 11, 13, 15, 17, 19):
            n = self._narrative(_at(h, 0), items).lower()
            for frame in _DAYPART_FRAMES:
                self.assertNotIn(frame, n, f"hour={h} leaked frame '{frame}': {n}")

    def test_relation_is_derived_from_the_item_not_the_clock(self):
        # One source: the same scheduled_time that builds the label sets the relation.
        with mock.patch(_NOW, return_value=_at(12, 0)), \
             mock.patch(_RHYTHM, return_value=[_item("Workout", "06:15", "task"),
                                               _item("Dentist appointment", "15:00")]):
            ahead, past, _hour = eb._rhythm_split(self.u)
        self.assertEqual([r["_relation"] for r in past], ["overdue"])
        self.assertEqual([r["_relation"] for r in ahead], ["upcoming"])


class RepairInheritsFixTests(TestCase):
    def setUp(self):
        self.u = _mkuser("agenda_repair@example.com")

    def test_repair_response_inherits_coherent_time_frame(self):
        from apps.ai.chatgpt_cos.lanes import _repair_response
        with mock.patch(_NOW, return_value=_at(15, 0)), \
             mock.patch(_RHYTHM, return_value=[_item("Workout", "06:15", "task")]), \
             mock.patch(_WORTH, return_value=True), \
             mock.patch("apps.ai.services.ai_service._call_api", side_effect=RuntimeError("x")):
            res = _repair_response(self.u, "you let me slide on my workout", None)
        ans = (res.get("answer") or "").lower()
        self.assertIn("6:15 am", ans)
        self.assertIn("overdue", ans)                     # framed as past, inherited
        for frame in _DAYPART_FRAMES:
            self.assertNotIn(frame, ans)


class NonTimeBehaviorUnchangedTests(TestCase):
    """The filter still drops routine/operating-rhythm and supplement items, and the
    recovery note still appears — only the TIME framing changed."""
    def setUp(self):
        self.u = _mkuser("agenda_filter@example.com")

    def _narrative(self, now, items, recovery=False):
        with mock.patch(_NOW, return_value=now), mock.patch(_RHYTHM, return_value=items):
            return eb._agenda_narrative(self.u, recovery=recovery)

    def test_operating_rhythm_task_still_dropped(self):
        n = self._narrative(_at(10, 0),
                            [_item("Log nutrition", "10:30", "task"),
                             _item("Dentist appointment", "14:00")])
        self.assertIn("Dentist appointment", n)
        self.assertNotIn("Log nutrition", n)

    def test_supplement_dose_still_not_surfaced(self):
        n = self._narrative(_at(10, 0),
                            [_item("Fish Oil", "09:30", "supplement_dose"),
                             _item("Dentist appointment", "14:00")])
        self.assertIn("Dentist appointment", n)
        self.assertNotIn("Fish Oil", n)

    def test_recovery_note_still_appears(self):
        with mock.patch(_WORTH, return_value=True):
            n = self._narrative(_at(10, 0), [_item("Workout", "14:00", "task")],
                                recovery=True)
        self.assertIn("keep it light", n.lower())
