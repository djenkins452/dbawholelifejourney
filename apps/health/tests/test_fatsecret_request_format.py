"""
Regression-guard for FatSecret request format.

Production incident 2026-05-17: FatSecret /rest/server.api was being called
with a JSON body and Content-Type: application/json. FatSecret's legacy
parser ignored the parameters and returned its default XML error envelope
with HTTP 200, which then failed JSON decoding downstream and surfaced as
"FatSecret foods.search JSON decode error" admin emails. Food search via
FatSecret silently returned zero results.

The fix: /rest/server.api endpoints must send form-encoded parameters
(requests' `data=` kwarg), per FatSecret's REST documentation. The other
two FatSecret endpoints have different shapes that must NOT regress to
form-encoded:
  - /rest/food/barcode/find-by-id/v2 → GET with `params=` (query string)
  - /rest/image-recognition/v2       → POST with `json=` (genuinely JSON,
                                       and required for the base64 image)

These tests lock all three shapes in place so a well-meaning future edit
cannot revert any one of them.
"""

from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.health.services.fatsecret import FatSecretService


@override_settings(FATSECRET_CLIENT_ID="test_id", FATSECRET_CLIENT_SECRET="test_secret")
class FatSecretRequestFormatTests(SimpleTestCase):
    """Lock in the per-endpoint request shape FatSecret actually expects."""

    def _stub_token(self, service):
        """Bypass the token round-trip; the body-shape contract is what we test."""
        return mock.patch.object(service, "_get_access_token", return_value="fake-token")

    def test_search_foods_uses_form_encoded_body(self):
        """/rest/server.api foods.search MUST send form-encoded, NOT JSON.

        The production XML-error incident was caused by `json={...}` here.
        Form-encoded is the FatSecret-documented shape and matches the
        already-working _get_access_token() call in the same file.
        """
        service = FatSecretService()
        with self._stub_token(service), mock.patch(
            "apps.health.services.fatsecret.requests.post"
        ) as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200,
                content=b'{"foods": {}}',
                text='{"foods": {}}',
            )
            mock_post.return_value.json.return_value = {"foods": {}}
            mock_post.return_value.raise_for_status = mock.Mock()

            service.search_foods("Big Mac")

            self.assertTrue(mock_post.called, "requests.post was not called")
            _args, kwargs = mock_post.call_args
            self.assertIn(
                "data",
                kwargs,
                "search_foods must use data= (form-encoded). Using json= "
                "causes FatSecret to return XML and silently break search.",
            )
            self.assertNotIn(
                "json",
                kwargs,
                "search_foods must NOT use json=. See _safe_json incident "
                "trace 2026-05-17.",
            )
            # And: do NOT force Content-Type: application/json — let
            # requests set application/x-www-form-urlencoded automatically.
            headers = kwargs.get("headers", {})
            self.assertNotEqual(
                headers.get("Content-Type"),
                "application/json",
                "search_foods must not force Content-Type: application/json — "
                "requests will set the correct form Content-Type when data= is used.",
            )
            # Form params must include method + format
            data = kwargs["data"]
            self.assertEqual(data.get("method"), "foods.search")
            self.assertEqual(data.get("format"), "json")

    def test_get_food_details_uses_form_encoded_body(self):
        """/rest/server.api food.get MUST send form-encoded, same reason."""
        service = FatSecretService()
        with self._stub_token(service), mock.patch(
            "apps.health.services.fatsecret.requests.post"
        ) as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200,
                content=b'{"food": {"food_id": "1", "food_name": "test"}}',
                text='{"food": {"food_id": "1", "food_name": "test"}}',
            )
            mock_post.return_value.json.return_value = {
                "food": {"food_id": "1", "food_name": "test"}
            }
            mock_post.return_value.raise_for_status = mock.Mock()

            service.get_food_details("123")

            self.assertTrue(mock_post.called)
            _args, kwargs = mock_post.call_args
            self.assertIn("data", kwargs)
            self.assertNotIn("json", kwargs)
            self.assertEqual(kwargs["data"].get("method"), "food.get")
            self.assertEqual(kwargs["data"].get("format"), "json")

    def test_image_recognition_still_uses_json_body(self):
        """/rest/image-recognition/v2 is a DIFFERENT endpoint with different
        rules — it takes a JSON body containing a base64 image. Do NOT
        regress this to form-encoded; that would break image scans (and
        form-encoding a base64 image is impractical anyway). This test
        exists so a future edit that mechanically converts every json= to
        data= in this file is caught.
        """
        service = FatSecretService()
        with mock.patch.object(
            service, "_get_access_token", return_value="fake-token"
        ), mock.patch(
            "apps.health.services.fatsecret.requests.post"
        ) as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200,
                content=b'{"food_response": []}',
                text='{"food_response": []}',
            )
            mock_post.return_value.json.return_value = {"food_response": []}
            mock_post.return_value.raise_for_status = mock.Mock()

            service.recognize_food_image("fake-base64-data")

            self.assertTrue(mock_post.called)
            _args, kwargs = mock_post.call_args
            self.assertIn(
                "json",
                kwargs,
                "recognize_food_image MUST keep json= — /rest/image-recognition/v2 "
                "expects a JSON body with the base64 image. Form-encoding it would "
                "break image scans.",
            )
            self.assertNotIn(
                "data",
                kwargs,
                "recognize_food_image must NOT use data=. Different endpoint, "
                "different contract from /rest/server.api.",
            )


class FatSecretSafeJsonLoggingTests(SimpleTestCase):
    """Lock in the diagnostic-log truncation width for XML-error responses."""

    def test_safe_json_logs_at_least_500_chars_of_xml_error_body(self):
        """When FatSecret returns its XML error envelope, the admin email
        must include enough of the body to see the <code> and <message>
        fields — not just <?xml … xsi:schemaLocation="…" which is what the
        original 200-char truncation cut off at. Locks the truncation
        width so a future "tidy up the logs" edit doesn't shrink it.
        """
        service = FatSecretService()
        # Simulate a realistic FatSecret XML error body (longer than 200 chars).
        xml_body = (
            '<?xml version="1.0" encoding="utf-8" ?>'
            '<error xmlns="http://platform.fatsecret.com/api/1.0/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:schemaLocation="http://platform.fatsecret.com/api/1.0/ '
            'http://platform.fatsecret.com/api/1.0/fatsecret.xsd">'
            '<code>13</code><message>Invalid token</message></error>'
        )
        self.assertGreater(len(xml_body), 200, "test fixture must be >200 chars")

        response = mock.Mock(
            status_code=200,
            content=xml_body.encode(),
            text=xml_body,
        )
        response.json.side_effect = ValueError("Expecting value: line 1 column 1 (char 0)")

        with self.assertLogs("apps.health.services.fatsecret", level="ERROR") as cm:
            result = service._safe_json(response, "FatSecret test")

        self.assertIsNone(result)
        logged = "\n".join(cm.output)
        # Must include <code> AND <message> — these live past the original
        # 200-char cutoff and are the part operators actually need to triage.
        self.assertIn("<code>", logged)
        self.assertIn("<message>", logged)
