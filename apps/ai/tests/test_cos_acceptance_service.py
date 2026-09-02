# ==============================================================================
# File: apps/ai/tests/test_cos_acceptance_service.py
# Description: Chief-of-Staff runner — the DEEP DEPENDENCY GATE + persistence. Beth
#   is injected (ask_fn) so the gate and scoring are tested without OpenAI.
# ==============================================================================
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.chatgpt_cos import cos_acceptance as cos
from apps.ai.chatgpt_cos.cos_acceptance_service import (
    CoSDeepNotGreen, create_and_execute_cos, cos_status,
)

User = get_user_model()


def _deep_run(grade):
    from apps.admin_console.models import AcceptanceRun
    return AcceptanceRun.objects.create(
        suite_name="full", depth="deep", status="completed", grade=grade,
        completed_at=timezone.now())


# Chief-of-Staff-quality answers (one per seed scenario), keyed by question.
_GOOD = {
    "Good morning": "Good morning. I don't have last night's sleep yet — Apple Health "
                    "hasn't synced; I'll have it once it syncs.",
    "Did I workout today?": "You haven't worked out today — no workout logged yet.",
    "How many steps did I get yesterday?": "You got 8,123 steps yesterday.",
    "Can you list each medicine I take and what each is commonly used for?":
        "Here's what you take and what each is commonly used for, based on your list: "
        "Metformin — diabetes/blood sugar; Lisinopril — blood pressure. Worth confirming "
        "with your doctor.",
    "My Dexcom says my glucose is 45 but I just ate a big slice of pizza.":
        "A 45 right after pizza doesn't quite fit what I'd expect — that can be a "
        "compression low or sensor artifact. I'd verify with a finger stick before treating.",
    "How do I get back on track with my France 2027 goal?":
        "You're behind pace on the France 18K. This week, schedule three training runs "
        "and add a mile to your long run.",
    "What should I focus on today?":
        "Start with your 10am meeting on the calendar, then the health action; there's a "
        "deadline coming up before your goal work.",
    "How's my weight trending?":
        "Your weight is trending down toward your goal weight; as of your last entry "
        "you're at 285 lb — you haven't logged in a few days.",
    # Scenarios added to COS_SCENARIOS after this fixture was written. Without an answer
    # here `_ask_good` returned "ok" for each, so a first-class assistant graded YELLOW
    # on five questions it was never given a chance to answer.
    # Temporal validation: the stored timestamp is in the future, so the reading is
    # reported WITHOUT pretending the time is real.
    "What's my latest glucose reading?":
        "Your latest glucose reading is 112 mg/dL, but its recorded time is unconfirmed "
        "— the timestamp is in the future, which usually means a sensor clock or sync "
        "issue. The value stands; I'd verify the timing before reading anything into "
        "when it happened.",
    # Clinical interpretation: a 43 is surfaced as dangerous and sent for verification,
    # never reassured away.
    "What was my last glucose reading?":
        "Your last glucose reading was 43 mg/dL — that is dangerously low and needs "
        "your attention now. Verify it with a fingerstick, and if it confirms, treat it "
        "straight away and let your care team know.",
    "What did I eat yesterday?":
        "Yesterday you had oatmeal and coffee in the morning, a chicken salad at lunch "
        "and salmon with rice for dinner — about 1,800 calories across the day.",
    "Should I be concerned?":
        "A 45 right after a big meal doesn't fit the pattern I'd expect, so I'd verify "
        "it with a finger stick before acting on it. If a finger stick agrees, treat it "
        "and let your care team know — that number deserves attention rather than a "
        "reassurance from me.",
    "Why do you say that?":
        "Because of the reading itself: 45 mg/dL right after a large carbohydrate meal "
        "is the opposite of what the food would do, which is why I'd treat the sensor "
        "value as suspect and confirm it before acting.",
    "How am I doing?":
        "Overall you're holding steady. Your weight is trending down toward your goal "
        "and you've kept your training going; sleep is the one that's slipped — a few "
        "short nights this week. A concrete next step: protect your bedtime tonight, "
        "since that's the thing most likely to move everything else.",
}
# A chatbot that ignores intent and presents stale data.
_BAD = {q: "You slept 6.9 hours last night." for q in _GOOD}


def _ask_good(user, q):
    return _GOOD.get(q, "ok")


def _ask_bad(user, q):
    return _BAD.get(q, "ok")


class DeepGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cosrun@example.com", password="x")

    def test_locked_when_no_deep_run(self):
        with self.assertRaises(CoSDeepNotGreen):
            create_and_execute_cos(self.user, ask_fn=_ask_good)

    def test_locked_when_deep_red(self):
        _deep_run("RED")
        with self.assertRaises(CoSDeepNotGreen):
            create_and_execute_cos(self.user, ask_fn=_ask_good)
        status = cos_status()
        self.assertFalse(status["enabled"])
        self.assertIn("Deep is RED", status["reason"])

    def test_unlocked_when_deep_green(self):
        _deep_run("GREEN")
        self.assertTrue(cos_status()["enabled"])


class RunPersistenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cospersist@example.com", password="x")

    def test_green_deep_first_class_beth_passes(self):
        _deep_run("GREEN")
        run = create_and_execute_cos(self.user, ask_fn=_ask_good)
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.suite_name, "chief_of_staff")
        self.assertEqual(run.grade, "GREEN")
        self.assertEqual(run.critical_count, 0)
        self.assertEqual(run.pass_count, run.total_count)
        self.assertEqual(run.total_count, len(cos.COS_SCENARIOS))

    def test_green_deep_chatbot_beth_fails_with_report(self):
        _deep_run("GREEN")
        run = create_and_execute_cos(self.user, ask_fn=_ask_bad)
        self.assertEqual(run.grade, "RED")
        self.assertGreater(run.critical_count, 0)         # hard trust/intent failures
        self.assertGreater(run.fail_count, 0)
        # The report guides engineering priorities by capability.
        self.assertTrue(run.category_summary)
        self.assertTrue(run.analysis.get("entries"))
