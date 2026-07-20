"""The salient ATTACHMENT LEAD — the model must never overlook a file already attached.

Prod defect 2026-07-20: the user attached Danny's Journal.docx and asked to import it; the
attachment reached the model as `current_context.attachments` (proven by the server-side
receipt on the user message) but sat buried in a ~60k-char JSON, so the model replied "please
upload the journal document." The fix lifts this-turn attachments into a salient lead. This is
the layer-5 (conversation assembly → model payload) divergence made prominent.
"""
from django.test import SimpleTestCase

from apps.ai.model_interface.service import ModelInterfaceService

_LEAD = ModelInterfaceService._attachment_lead


class AttachmentLeadTests(SimpleTestCase):
    def test_readable_document_is_surfaced_prominently(self):
        ctx = {"current_context": {"attachments": [
            {"artifact_id": 11, "kind": "document",
             "filename": "Danny's Journal.docx", "text": "Sunday, January 1, 2023..."}]}}
        lead = _LEAD(ctx)
        self.assertIn("ATTACHED THIS TURN", lead)
        self.assertIn("Danny's Journal.docx", lead)
        self.assertIn("do NOT ask them to upload", lead)
        self.assertIn("artifact_id=11", lead)
        self.assertIn("import_journal_entries", lead)   # tells the model exactly what to do
        self.assertIn("readable", lead)

    def test_processing_document_says_still_reading(self):
        ctx = {"current_context": {"attachments": [
            {"artifact_id": 12, "kind": "document", "filename": "scan.pdf",
             "perception": "processing"}]}}
        lead = _LEAD(ctx)
        self.assertIn("scan.pdf", lead)
        self.assertIn("still being read", lead)

    def test_empty_when_no_attachments(self):
        self.assertEqual(_LEAD({"current_context": {}}), "")
        self.assertEqual(_LEAD({"current_context": {"attachments": []}}), "")
        self.assertEqual(_LEAD({}), "")

    def test_never_raises_on_garbage(self):
        self.assertEqual(_LEAD({"current_context": {"attachments": ["x", None, 3]}}), "")
        self.assertEqual(_LEAD(None if False else {"current_context": None}), "")

    def test_lead_is_in_the_system_prompt(self):
        svc = ModelInterfaceService.__new__(ModelInterfaceService)
        ctx = {"current_context": {"attachments": [
            {"artifact_id": 11, "kind": "document",
             "filename": "Danny's Journal.docx", "text": "x"}]}}
        prompt = svc._system_prompt(ctx)
        # Surfaced BEFORE the buried structured-context JSON.
        self.assertIn("Danny's Journal.docx", prompt)
        self.assertLess(prompt.index("Danny's Journal.docx"),
                        prompt.index("=== STRUCTURED CONTEXT"))
