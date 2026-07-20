"""ARCHITECTURAL CONTRACT — Conversation State has ONE deterministic writer authority.

Conversation State is deterministic conversational truth carried inside the Executive Context
Envelope. It must never become an open-ended shared object arbitrary systems mutate, and it must
NEVER be written from model reasoning / prose. This contract fails CI if either invariant breaks:

  1. Only `apps/ai/model_interface/` may WRITE it (call record_turn / clear / _save, or assign
     metadata["conversation_state"]). Every other module may READ it only.
  2. The writer's inputs are deterministic — record_turn accepts only concrete signals
     (conversation, attachments, retrieved_subject, now), never a model-output / prose parameter.

See docs/WLJ_CONVERSATION_STATE_ARCHITECTURE.md §4a (Deterministic Writers).
"""
import inspect
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.ai.model_interface import conversation_state as cs

_APPS = Path(settings.BASE_DIR) / "apps"
_AUTHORITY = "apps/ai/model_interface"        # the ONE writer authority (dir)

# Unambiguous writer signals (record_turn/_save are conversation_state-specific names; clear is
# only flagged when module-qualified to avoid matching unrelated `.clear()` calls).
_WRITER_PATTERNS = [
    re.compile(r"\brecord_turn\s*\("),
    re.compile(r"conversation_state\s*\.\s*_save\s*\("),
    re.compile(r"(?:conversation_state|_cs)\s*\.\s*clear\s*\("),
    re.compile(r"""metadata\s*\[\s*['"]conversation_state['"]\s*\]\s*="""),
]
# A model-output parameter name would mean the model could write state — forbidden.
_FORBIDDEN_WRITER_PARAMS = {
    "content", "text", "answer", "message", "prose", "summary", "reasoning",
    "completion", "response", "topic", "subject_text", "inferred", "guess",
}


def _scan_files():
    for path in _APPS.rglob("*.py"):
        rel = path.relative_to(settings.BASE_DIR).as_posix()
        if (rel.startswith(_AUTHORITY) or "/tests/" in rel or "/migrations/" in rel
                or path.name.startswith("test_")):
            continue
        yield rel, path.read_text(encoding="utf-8", errors="ignore")


class ConversationStateWriterContractTests(SimpleTestCase):
    def test_only_the_authority_writes_conversation_state(self):
        offenders = []
        for rel, src in _scan_files():
            if "conversation_state" not in src and "record_turn" not in src:
                continue
            for pat in _WRITER_PATTERNS:
                if pat.search(src):
                    offenders.append(f"{rel}: {pat.pattern}")
        self.assertEqual(
            offenders, [],
            "Conversation State may only be WRITTEN by apps/ai/model_interface/ (the single "
            "deterministic authority). These modules write it and must not:\n  "
            + "\n  ".join(offenders))

    def test_record_turn_inputs_are_deterministic_not_model_output(self):
        params = set(inspect.signature(cs.record_turn).parameters) - {"conversation"}
        leaked = params & _FORBIDDEN_WRITER_PARAMS
        self.assertEqual(
            leaked, set(),
            f"record_turn must accept only deterministic signals; a model-output parameter "
            f"({leaked}) would let the model write Conversation State.")
        # positive: the only accepted signals are the concrete ones.
        self.assertTrue(params <= {"attachments", "retrieved_subject", "now"},
                        f"unexpected record_turn params: {params}")

    def test_authority_module_is_the_writer(self):
        # sanity: the documented authority actually contains the writer functions.
        for fn in ("record_turn", "clear", "read"):
            self.assertTrue(callable(getattr(cs, fn, None)), f"missing {fn}")
