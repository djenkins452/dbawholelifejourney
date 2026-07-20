"""ARCHITECTURAL CONTRACT — Conversation State is a compact DETERMINISTIC index.

It must contain only deterministic references + deterministic state — never a conversation
summary, transcript, AI-generated prose, inferred intent, reflection output, or any other
model-authored / free-text field. This contract fails CI the moment a summary/prose key is
introduced into the schema, so the "compact deterministic index" boundary cannot silently erode.

See docs/WLJ_CONVERSATION_STATE_ARCHITECTURE.md §5a (Permitted Data) / §5b (Expansion Test).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.models import AssistantConversation
from apps.ai.model_interface import conversation_state as cs

User = get_user_model()

# The ALLOW-LIST — the complete permitted schema. Adding a key here is a deliberate governance
# decision (must pass the Expansion Test); it is not a place to sneak in generated text.
_ALLOWED_TOP = {"schema_version", "turn", "updated_ts", "active_subject",
                "active_artifacts", "last_answer_turn"}
_ALLOWED_SUBJECT = {"kind", "ref", "label", "source_turn", "first_ts", "artifact", "turns_ago"}
_ALLOWED_ARTIFACT = {"artifact_id", "kind", "filename", "ts"}

# Key-name fragments that signal model-authored / free-text / memory content — forbidden anywhere.
_FORBIDDEN_FRAGMENTS = (
    "summary", "transcript", "prose", "analysis", "explanation", "reasoning", "memory",
    "inferred", "intent", "interpretation", "classification", "reflection", "generated",
    "freetext", "free_text", "narrative", "description", "notes", "comment", "insight",
)
# The single free-form-looking value (`label`) is a deterministic display name — bound its length
# so it can never become a prose blob.
_LABEL_MAX = 200


class ConversationStateSchemaContractTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cs_schema@example.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user, session_type="chat")

    def _state(self):
        # Exercise BOTH write paths (upload subject + retrieved subject) then read it back.
        cs.record_turn(self.conv, attachments=[{"artifact_id": 7, "kind": "image",
                                                "filename": "bottle.png"}])
        cs.record_turn(self.conv, retrieved_subject={"kind": "entity", "ref": "Dad health",
                                                     "label": "Dad health"})
        return (self.conv.metadata or {}).get("conversation_state") or {}

    def test_schema_is_allow_listed(self):
        st = self._state()
        self.assertTrue(set(st) <= _ALLOWED_TOP, f"unexpected top-level keys: {set(st) - _ALLOWED_TOP}")
        subj = st.get("active_subject") or {}
        self.assertTrue(set(subj) <= _ALLOWED_SUBJECT,
                        f"unexpected active_subject keys: {set(subj) - _ALLOWED_SUBJECT}")
        for a in st.get("active_artifacts") or []:
            self.assertTrue(set(a) <= _ALLOWED_ARTIFACT,
                            f"unexpected active_artifacts keys: {set(a) - _ALLOWED_ARTIFACT}")

    def test_no_prose_or_summary_keys_anywhere(self):
        offenders = []

        def _walk(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    kl = str(k).lower()
                    if any(f in kl for f in _FORBIDDEN_FRAGMENTS):
                        offenders.append(f"{path}{k}")
                    _walk(v, f"{path}{k}.")
            elif isinstance(obj, list):
                for it in obj:
                    _walk(it, path)

        _walk(self._state())
        self.assertEqual(offenders, [],
                         f"forbidden model-authored / free-text keys in Conversation State: {offenders}")

    def test_label_is_a_bounded_display_name_not_a_blob(self):
        subj = self._state().get("active_subject") or {}
        label = subj.get("label") or ""
        self.assertIsInstance(label, str)
        self.assertLessEqual(len(label), _LABEL_MAX,
                             "active_subject.label must be a short deterministic name, not prose")

    def test_all_values_are_deterministic_scalars_refs_or_timestamps(self):
        # No nested free-form structures beyond the known reference shapes.
        st = self._state()
        for k, v in st.items():
            if k in ("active_subject", "active_artifacts"):
                continue
            self.assertIsInstance(v, (int, str), f"{k} must be a scalar/ref/timestamp, got {type(v)}")
