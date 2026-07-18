"""
Tests for the WLJ Rich Text platform: sanitizer, plain-text shadow, the
RichTextMixin storage contract, and the shared image-upload endpoint.

These lock the security + data-integrity guarantees the whole platform relies on:
sanitized-HTML-in / plain-shadow-out, no XSS survives a save, and existing
plain-text reporting (word count / preview / search / narration) keeps working.
"""
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.rich_text import (
    normalize_mention_whitespace,
    plaintext_to_html,
    rich_text_to_plaintext,
    sanitize_rich_html,
)

User = get_user_model()


class MentionWhitespaceTest(SimpleTestCase):
    """A recognized-person chip must read like ordinary inline text — no
    editor-inserted space before the punctuation that follows it."""

    def _chip(self, label="Heather"):
        return f'<span data-mention data-person-id="112">{label}</span>'

    def test_space_before_punctuation_removed(self):
        for punct in [".", ",", ";", ":", "!", "?", ")"]:
            html = f"<p>Lunch with {self._chip()} {punct} rest</p>"
            out = normalize_mention_whitespace(html)
            self.assertIn(f"</span>{punct}", out, punct)
            self.assertNotIn(f"</span> {punct}", out, punct)

    def test_legitimate_trailing_space_before_word_kept(self):
        html = f"<p>Lunch with {self._chip()} and then home</p>"
        self.assertEqual(normalize_mention_whitespace(html), html)  # space before a word stays

    def test_applied_by_sanitize_and_idempotent(self):
        html = f"<p>Saw {self._chip()} , then left.</p>"
        once = sanitize_rich_html(html)
        self.assertIn("</span>,", once)
        self.assertNotIn("</span> ,", once)
        self.assertEqual(once, sanitize_rich_html(once))

    def test_plain_shadow_reads_naturally(self):
        html = f"<p>Saw {self._chip()} , then left.</p>"
        shadow = rich_text_to_plaintext(sanitize_rich_html(html))
        self.assertEqual(shadow, "Saw Heather, then left.")


class SanitizeRichHtmlTest(SimpleTestCase):
    def test_strips_script_and_event_handlers(self):
        out = sanitize_rich_html(
            '<p>ok</p><script>alert(1)</script>'
            '<img src="x" onerror="alert(1)">'
        )
        self.assertNotIn("<script", out)
        self.assertNotIn("onerror", out)
        self.assertIn("<p>ok</p>", out)

    def test_strips_javascript_url_but_keeps_safe_link(self):
        out = sanitize_rich_html(
            '<a href="javascript:alert(1)">bad</a>'
            '<a href="https://example.com">good</a>'
        )
        self.assertNotIn("javascript:", out)
        self.assertIn('href="https://example.com"', out)
        self.assertIn("nofollow", out)  # link_rel applied

    def test_strips_iframe_and_style_attribute(self):
        # style is never allowed (nh3 can't filter CSS properties → injection risk).
        out = sanitize_rich_html(
            '<iframe src="https://evil"></iframe>'
            '<p style="background:url(javascript:alert(1))">x</p>'
        )
        self.assertNotIn("<iframe", out)
        self.assertNotIn("javascript:", out)
        self.assertNotIn("style=", out)

    def test_keeps_allowed_formatting_and_alignment(self):
        html = (
            '<h1>H</h1><p data-text-align="center">'
            '<strong>b</strong><em>i</em><u>u</u><s>s</s><code>c</code></p>'
            '<ul><li>one</li></ul><blockquote>q</blockquote><hr>'
        )
        out = sanitize_rich_html(html)
        for token in ["<h1>", "data-text-align=\"center\"", "<strong>",
                      "<em>", "<u>", "<code>", "<ul>", "<blockquote>", "<hr"]:
            self.assertIn(token, out)

    def test_idempotent(self):
        html = '<p>hi <strong>there</strong></p>'
        once = sanitize_rich_html(html)
        self.assertEqual(once, sanitize_rich_html(once))

    def test_empty(self):
        self.assertEqual(sanitize_rich_html(""), "")
        self.assertEqual(sanitize_rich_html(None), "")


class PlaintextShadowTest(SimpleTestCase):
    def test_block_boundaries_do_not_fuse_words(self):
        self.assertEqual(rich_text_to_plaintext("<p>a</p><p>b</p>"), "a\nb")

    def test_strips_all_tags(self):
        out = rich_text_to_plaintext("<p>Hello <strong>bold</strong> world</p>")
        self.assertEqual(out, "Hello bold world")

    def test_collapses_whitespace(self):
        out = rich_text_to_plaintext("<p>a    b</p>\n\n\n<p>c</p>")
        self.assertEqual(out, "a b\n\nc")  # runs of blank space collapse to <= 2

    def test_empty(self):
        self.assertEqual(rich_text_to_plaintext(""), "")


class PlaintextToHtmlTest(SimpleTestCase):
    def test_wraps_paragraphs_and_escapes(self):
        out = plaintext_to_html("line one\n\nline two <b>")
        self.assertIn("<p>line one</p>", out)
        self.assertIn("<p>line two &lt;b&gt;</p>", out)

    def test_single_newline_becomes_br(self):
        self.assertIn("<br>", plaintext_to_html("a\nb"))

    def test_literal_angle_brackets_are_escaped_not_treated_as_html(self):
        # Legacy plain text containing "<b>" must stay literal text (no data loss).
        out = plaintext_to_html("I scored 3<b in chess")
        self.assertIn("3&lt;b in chess", out)
        self.assertNotIn("<b ", out)

    def test_roundtrip_preserves_words(self):
        # The shadow normalizes paragraph breaks (double newline -> single); it is
        # for search/preview/word-count, not exact reproduction.
        original = "First thought.\n\nSecond thought."
        plain = rich_text_to_plaintext(plaintext_to_html(original))
        self.assertEqual(plain, "First thought.\nSecond thought.")


class RichTextMixinStorageTest(TestCase):
    """JournalEntry is the reference RichTextMixin adopter."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="rte@example.com", password="x"
        )

    def _entry(self, body):
        from apps.journal.models import JournalEntry
        return JournalEntry.objects.create(
            user=self.user, title="T", body=body
        )

    def test_save_sanitizes_body_and_populates_plain_shadow(self):
        e = self._entry("<p>Hello <script>alert(1)</script><strong>world</strong></p>")
        e.refresh_from_db()
        self.assertNotIn("<script", e.body)
        self.assertIn("<strong>world</strong>", e.body)
        self.assertEqual(e.body_plain, "Hello world")

    def test_word_count_and_preview_use_plain_shadow(self):
        e = self._entry("<h1>Title</h1><p>one two three</p>")
        e.refresh_from_db()
        self.assertEqual(e.word_count, 4)          # Title one two three
        self.assertNotIn("<", e.body_preview)      # no markup in preview

    def test_plain_shadow_regenerates_on_edit(self):
        e = self._entry("<p>original</p>")
        e.body = "<p>changed <em>text</em></p>"
        e.save()
        e.refresh_from_db()
        self.assertEqual(e.body_plain, "changed text")


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class RichTextImageUploadEndpointTest(TestCase):
    def setUp(self):
        from django.conf import settings
        self.user = User.objects.create_user(
            email="up@example.com", password="x"
        )
        # Satisfy the terms/onboarding middleware so authenticated POSTs aren't
        # redirected (302) before reaching the endpoint.
        try:
            from apps.users.models import TermsAcceptance
            TermsAcceptance.objects.get_or_create(
                user=self.user,
                defaults={"terms_version": settings.WLJ_SETTINGS["TERMS_VERSION"]},
            )
        except Exception:
            pass
        try:
            prefs = self.user.preferences
            prefs.has_completed_onboarding = True
            prefs.save()
        except Exception:
            pass
        self.url = reverse("core:rich_text_image_upload")

    def _png_bytes(self):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, "PNG")
        return buf.getvalue()

    def test_valid_upload_returns_url(self):
        c = Client()
        c.force_login(self.user)
        resp = c.post(self.url, {
            "image": SimpleUploadedFile("t.png", self._png_bytes(), content_type="image/png"),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn("url", resp.json())

    def test_rejects_non_image_content_type(self):
        c = Client()
        c.force_login(self.user)
        resp = c.post(self.url, {
            "image": SimpleUploadedFile("t.txt", b"nope", content_type="text/plain"),
        })
        self.assertEqual(resp.status_code, 400)

    def test_rejects_bytes_that_are_not_a_real_image(self):
        c = Client()
        c.force_login(self.user)
        resp = c.post(self.url, {
            "image": SimpleUploadedFile("fake.png", b"notreallypng", content_type="image/png"),
        })
        self.assertEqual(resp.status_code, 400)

    def test_requires_login(self):
        resp = Client().post(self.url, {
            "image": SimpleUploadedFile("t.png", self._png_bytes(), content_type="image/png"),
        })
        self.assertIn(resp.status_code, (302, 403))

    def test_get_not_allowed(self):
        c = Client()
        c.force_login(self.user)
        self.assertEqual(c.get(self.url).status_code, 405)
