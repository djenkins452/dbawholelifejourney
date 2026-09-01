"""Rich Confirmation — engine + contract + both resolution paths.

docs/WLJ_RICH_CONFIRMATION_ARCHITECTURE.md. Certifies the reusable capability: the
presentation-independent view, deterministic typed matching, the bound record (conversation-
bound, single-use, replay/expiry-safe), and BOTH a clicked button (endpoint) and a typed
confirm/cancel converging on the SAME resolver. The production defect — typing "yes" losing a
valid journal-import confirmation — is covered by TypedResolutionTests + JournalImportE2E.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.confirmation_contract import build_view, match_typed
from apps.ai.cos_services.action_interface import (
    request_action,
    resolve_pending_action,
    resolve_typed_confirmation,
)
from apps.ai.model_interface import confirmation as C
from apps.ai.models import AssistantConversation
from apps.journal.models import JournalEntry

User = get_user_model()

ENTRIES = [
    {"entry_date": "2022-09-10", "entry_time": "10:00", "body": "A."},
    {"entry_date": "2022-09-08", "entry_time": "07:00", "body": "B."},
    {"entry_date": "2022-09-05", "skipped": True},
]


class ContractTests(TestCase):
    def test_import_binary_view(self):
        detail = {"kind": "record", "noun": "entries",
                  "records": [{"date_iso": "2022-09-10", "has_time": True},
                              {"date_iso": "2022-08-30", "has_time": False}],
                  "skipped": [{"date_iso": "2022-09-05"}]}
        view = build_view("import_journal_entries", {}, detail)
        self.assertEqual(view["actions"]["primary"]["label"], "Import")
        self.assertEqual(view["actions"]["primary"]["key"], "confirm")
        self.assertEqual(view["actions"]["secondary"][0]["key"], "cancel")
        self.assertIn("yes", view["actions"]["primary"]["aliases"])
        self.assertTrue(any("will be imported" in p for p in view["preview"]))
        self.assertTrue(any("Date range" in p for p in view["preview"]))
        self.assertIn("I found 3 entries", view["summary"])

    def test_delete_is_danger(self):
        view = build_view("delete_entries", {"count": 5})
        self.assertEqual(view["actions"]["primary"]["label"], "Delete")
        self.assertEqual(view["actions"]["primary"]["style"], "danger")

    def test_generic_confirm(self):
        view = build_view("some_action", {})
        self.assertEqual(view["actions"]["primary"]["label"], "Confirm")

    def test_measurement_view(self):
        detail = {"kind": "measurement", "noun": "measurements",
                  "measurements": [{"label": "Waist"}, {"label": "Hips"}], "skipped": []}
        view = build_view("log_body_measurements", {}, detail)
        self.assertEqual(view["actions"]["primary"]["label"], "Save")
        self.assertIn("I found 2 measurements", view["summary"])

    def test_nway_explicit_actions(self):
        detail = {"actions": {
            "primary": {"key": "merge", "label": "Merge", "action": "merge_meds"},
            "secondary": [{"key": "keep_both", "label": "Keep Both", "action": "keep_both_meds"}]}}
        view = build_view("resolve_med_dupe", {}, detail)
        self.assertEqual(view["actions"]["primary"]["key"], "merge")
        keys = [s["key"] for s in view["actions"]["secondary"]]
        self.assertIn("keep_both", keys)
        self.assertIn("cancel", keys)  # cancel escape hatch always present

    def test_match_typed(self):
        view = build_view("import_journal_entries", {}, {"kind": "record"})
        for yes in ("yes", "import", "go ahead", "looks good", "do it", "confirm", "yes please"):
            self.assertEqual(match_typed(yes, view), "confirm", yes)
        for no in ("no", "cancel", "stop", "never mind", "don't do it", "no thanks"):
            self.assertEqual(match_typed(no, view), "cancel", no)
        for unrelated in ("what did I eat yesterday", "tell me about my goals", ""):
            self.assertIsNone(match_typed(unrelated, view), unrelated)


class StoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="s@ex.com", password="x")

    def test_create_get_consume_peek(self):
        view = build_view("import_journal_entries", {}, {"kind": "record"})
        h = C.create(self.user, "import_journal_entries", {"entries": ENTRIES},
                     "summary", view=view, conversation_id=7)
        cid = h["confirmation_id"]
        self.assertIsNotNone(C.get(self.user, cid))
        card = C.client_view(C.get(self.user, cid))
        self.assertEqual(card["confirmation_id"], cid)
        self.assertEqual(card["actions"]["primary"]["label"], "Import")
        # consume → not pending; peek shows the tombstone status.
        C.consume(self.user, cid, status="resolved")
        self.assertIsNone(C.get(self.user, cid))
        self.assertEqual(C.peek(self.user, cid)["status"], "resolved")

    def test_owner_scoped(self):
        other = User.objects.create_user(email="o@ex.com", password="x")
        h = C.create(self.user, "a", {}, "s", conversation_id=1)
        self.assertIsNone(C.get(other, h["confirmation_id"]))

    def test_bind_and_open_for_conversation(self):
        C.create(self.user, "import_journal_entries", {}, "s",
                 view=build_view("import_journal_entries", {}, {"kind": "record"}))
        card = C.bind_conversation(self.user, 42)
        self.assertIsNotNone(card)
        self.assertEqual(len(C.open_for_conversation(self.user, 42)), 1)
        self.assertEqual(len(C.open_for_conversation(self.user, 99)), 0)


class ResolveTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="r@ex.com", password="x")

    def _mint(self):
        out = request_action(self.user, "import_journal_entries",
                             {"entries": ENTRIES}, conversation_id=5)
        return out

    def test_request_action_mints_rich_confirmation(self):
        out = self._mint()
        self.assertEqual(out["status"], "confirmation_required")
        card = out["confirmation"]
        self.assertIn("confirmation_id", card)
        self.assertEqual(card["actions"]["primary"]["label"], "Import")
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 0)

    def test_resolve_confirm_executes(self):
        cid = self._mint()["confirmation"]["confirmation_id"]
        out = resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 2)

    def test_resolve_cancel_declines(self):
        cid = self._mint()["confirmation"]["confirmation_id"]
        out = resolve_pending_action(self.user, cid, confirm=False)
        self.assertEqual(out["status"], "declined")
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 0)

    def test_replay_is_already_resolved(self):
        cid = self._mint()["confirmation"]["confirmation_id"]
        resolve_pending_action(self.user, cid, confirm=True)
        again = resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(again["code"], "already_resolved")
        # single-use: no second import
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 2)

    def test_missing_is_no_matching(self):
        out = resolve_pending_action(self.user, "deadbeef", confirm=True)
        self.assertEqual(out["code"], "no_matching_confirmation")

    def test_wrong_user_cannot_resolve(self):
        cid = self._mint()["confirmation"]["confirmation_id"]
        other = User.objects.create_user(email="x@ex.com", password="x")
        out = resolve_pending_action(other, cid, confirm=True)
        self.assertEqual(out["code"], "no_matching_confirmation")
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 0)


class TypedResolutionTests(TestCase):
    """The production defect: a typed 'yes' must resolve the pending confirmation."""

    def setUp(self):
        self.user = User.objects.create_user(email="t@ex.com", password="x")

    def _mint(self, conversation_id=5):
        return request_action(self.user, "import_journal_entries",
                              {"entries": ENTRIES}, conversation_id=conversation_id
                              )["confirmation"]["confirmation_id"]

    def test_typed_yes_resolves(self):
        self._mint(conversation_id=5)
        out = resolve_typed_confirmation(self.user, 5, "yes")
        self.assertIsNotNone(out)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 2)

    def test_typed_import_and_go_ahead(self):
        self._mint(conversation_id=6)
        self.assertIsNotNone(resolve_typed_confirmation(self.user, 6, "go ahead"))

    def test_typed_cancel_declines(self):
        self._mint(conversation_id=7)
        out = resolve_typed_confirmation(self.user, 7, "no")
        self.assertEqual(out["status"], "declined")
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 0)

    def test_unrelated_text_falls_through(self):
        self._mint(conversation_id=8)
        self.assertIsNone(resolve_typed_confirmation(self.user, 8, "what did I weigh last week"))
        # confirmation remains open for the model to handle
        self.assertEqual(len(C.open_for_conversation(self.user, 8)), 1)

    def test_scoped_to_conversation(self):
        self._mint(conversation_id=9)
        # A 'yes' in a DIFFERENT conversation must not resolve it.
        self.assertIsNone(resolve_typed_confirmation(self.user, 999, "yes"))


class EndpointTests(TestCase):
    def setUp(self):
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(email="e@ex.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        prefs = self.user.preferences
        prefs.has_completed_onboarding = True
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.proactive_assistance_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()
        self.client.force_login(self.user)
        self.conv = AssistantConversation.get_or_create_active(self.user)

    def _mint(self):
        return request_action(self.user, "import_journal_entries",
                              {"entries": ENTRIES}, conversation_id=self.conv.id
                              )["confirmation"]["confirmation_id"]

    def test_click_import_executes(self):
        cid = self._mint()
        resp = self.client.post("/assistant/api/confirm/",
                                data={"confirmation_id": cid, "choice": "confirm"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["confirmation_resolved"]["status"], "resolved")
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 2)

    def test_click_cancel(self):
        cid = self._mint()
        resp = self.client.post("/assistant/api/confirm/",
                                data={"confirmation_id": cid, "choice": "cancel"},
                                content_type="application/json")
        self.assertEqual(resp.json()["confirmation_resolved"]["status"], "cancelled")
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 0)

    def test_double_click_protected(self):
        cid = self._mint()
        for _ in range(2):
            resp = self.client.post("/assistant/api/confirm/",
                                    data={"confirmation_id": cid, "choice": "confirm"},
                                    content_type="application/json")
        self.assertEqual(resp.json()["confirmation_resolved"]["status"], "already_resolved")
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 2)

    def test_missing_id(self):
        resp = self.client.post("/assistant/api/confirm/", data={"choice": "confirm"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)
