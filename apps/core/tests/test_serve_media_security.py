"""
Security tests for the local-disk media fallback view (config.urls.serve_media).

Covers the Phase 0.1 hardening from docs/WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md §4:
  - Authentication is required (anonymous requests are denied, never served).
  - Path traversal is blocked (`../` escapes MEDIA_ROOT → 404, not an arbitrary
    file read).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import RequestFactory, TestCase

from config.urls import serve_media

User = get_user_model()


class ServeMediaSecurityTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _get(self, path, user):
        request = self.factory.get(f"/media/{path}")
        request.user = user
        return serve_media(request, path)

    def test_anonymous_is_denied(self):
        """An unauthenticated request must not be served media (login_required)."""
        resp = self._get("some/file.jpg", AnonymousUser())
        # login_required returns a redirect to the login page for anonymous users.
        self.assertEqual(resp.status_code, 302)
        self.assertNotIsInstance(getattr(resp, "streaming", False), bytes)

    def test_path_traversal_is_blocked(self):
        """A traversal path must raise 404, never read outside MEDIA_ROOT."""
        user = User.objects.create_user(
            email="media-sec@example.com", password="x"
        )
        for evil in (
            "../../etc/passwd",
            "../../../etc/passwd",
            "..%2f..%2fetc/passwd",  # literal, since <path:path> passes it through
            "subdir/../../secret.key",
        ):
            with self.subTest(evil=evil):
                with self.assertRaises(Http404):
                    self._get(evil, user)

    def test_missing_file_is_404_for_authenticated_user(self):
        """A well-formed but nonexistent path is a clean 404 (no traceback)."""
        user = User.objects.create_user(
            email="media-sec2@example.com", password="x"
        )
        with self.assertRaises(Http404):
            self._get("definitely/not/here.png", user)
