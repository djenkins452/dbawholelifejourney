# ==============================================================================
# File: apps/health/tests/test_fatsecret_outcomes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: An empty FatSecret result must say which kind of empty it is
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-08
# ==============================================================================
"""Five different failures used to look identical, and one of them was happening.

`search_foods` returned `[]` for an HTTP failure, for FatSecret's XML error envelope
arriving with HTTP 200, for a missing `foods` payload, for a genuinely empty result, and for
any parse exception. In production on 2026-09-08 authentication succeeded and every live
search returned nothing — including "banana" and "big mac", which FatSecret certainly holds.
Nothing in the system could say why, because the five causes had one shape.

Each condition now names itself. The list-only contract is unchanged, so no provider problem
can break a page — the reason simply travels alongside it now.

No network and no provider: every response is constructed.
"""

from unittest import mock

import requests
from django.test import SimpleTestCase

from apps.health.services import fatsecret as fs


class _Response:
    def __init__(self, status_code=200, body="", json_body=None):
        self.status_code = status_code
        self._json = json_body
        self.text = body if json_body is None else ""
        self.content = (self.text or ("x" if json_body is not None else "")).encode()

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def _service(available=True, token="tok"):
    service = fs.FatSecretService()
    service.client_id = "id" if available else None
    service.client_secret = "secret" if available else None
    service._get_access_token = mock.Mock(return_value=token)
    return service


def _outcome(response=None, service=None, exc=None):
    service = service or _service()
    with mock.patch.object(fs.requests, "post",
                           side_effect=exc if exc else None,
                           return_value=response):
        return service.search_foods_outcome("anything")


class OutcomeTests(SimpleTestCase):
    def test_results_are_reported_as_results(self):
        body = {"foods": {"food": [{"food_id": "1", "food_name": "Banana",
                                    "food_description": "Per 100g - Calories: 89kcal"}]}}
        out = _outcome(_Response(json_body=body))
        self.assertEqual(out.status, fs.OK_WITH_RESULTS)
        self.assertEqual(len(out.foods), 1)
        self.assertTrue(out.ok)

    def test_a_genuine_empty_result_says_so(self):
        out = _outcome(_Response(json_body={"foods": {}}))
        self.assertEqual(out.status, fs.OK_NO_RESULTS)
        self.assertTrue(out.ok, "an honest zero-match is not a failure")

    def test_an_xml_error_envelope_at_http_200_is_a_provider_error(self):
        """FatSecret's documented behaviour on a rejected request — and the condition
        that was silently indistinguishable from 'no such food'."""
        body = ('<?xml version="1.0"?><error><code>21</code>'
                '<message>Invalid IP address detected</message></error>')
        out = _outcome(_Response(status_code=200, body=body))
        self.assertEqual(out.status, fs.PROVIDER_ERROR)
        self.assertEqual(out.provider_code, "21")
        self.assertEqual(out.body_kind, "xml")
        self.assertIn("Invalid IP address", out.detail)
        self.assertFalse(out.ok)

    def test_a_json_error_object_at_http_200_is_also_a_provider_error(self):
        out = _outcome(_Response(json_body={"error": {"code": 12,
                                                      "message": "Missing required"}}))
        self.assertEqual(out.status, fs.PROVIDER_ERROR)
        self.assertEqual(out.provider_code, "12")

    def test_an_http_failure_is_an_http_error(self):
        out = _outcome(_Response(status_code=503, body="upstream down"))
        self.assertEqual(out.status, fs.HTTP_ERROR)
        self.assertEqual(out.http_status, 503)

    def test_a_transport_exception_is_an_http_error(self):
        out = _outcome(exc=requests.exceptions.ConnectTimeout("timed out"))
        self.assertEqual(out.status, fs.HTTP_ERROR)

    def test_an_unrecognised_shape_is_invalid_not_empty(self):
        out = _outcome(_Response(json_body={"something_else": True}))
        self.assertEqual(out.status, fs.INVALID_RESPONSE)

    def test_an_empty_body_is_invalid_not_empty(self):
        out = _outcome(_Response(status_code=200, body=""))
        self.assertEqual(out.status, fs.INVALID_RESPONSE)
        self.assertEqual(out.body_kind, "empty")

    def test_unreadable_non_xml_content_is_a_parse_error(self):
        out = _outcome(_Response(status_code=200, body="not json, not xml"))
        self.assertEqual(out.status, fs.PARSE_ERROR)

    def test_a_broken_record_is_a_parse_error_not_a_silent_drop(self):
        body = {"foods": {"food": [{"food_id": "1"}]}}
        service = _service()
        service._parse_food = mock.Mock(side_effect=KeyError("food_name"))
        out = _outcome(_Response(json_body=body), service=service)
        self.assertEqual(out.status, fs.PARSE_ERROR)

    def test_no_token_is_an_auth_error(self):
        out = _outcome(_Response(json_body={"foods": {}}), service=_service(token=None))
        self.assertEqual(out.status, fs.AUTH_ERROR)

    def test_absent_credentials_are_reported_as_not_configured(self):
        service = _service(available=False)
        self.assertEqual(service.search_foods_outcome("x").status, fs.NOT_CONFIGURED)

    def test_every_status_is_distinct(self):
        """The whole point: no two conditions may share a code."""
        codes = [fs.OK_WITH_RESULTS, fs.OK_NO_RESULTS, fs.AUTH_ERROR, fs.PROVIDER_ERROR,
                 fs.HTTP_ERROR, fs.INVALID_RESPONSE, fs.PARSE_ERROR, fs.NOT_CONFIGURED]
        self.assertEqual(len(codes), len(set(codes)))


class CallerResilienceTests(SimpleTestCase):
    """Diagnostics gained a reason; callers lost nothing."""

    def test_search_foods_still_returns_a_plain_list(self):
        body = {"foods": {"food": [{"food_id": "1", "food_name": "Banana",
                                    "food_description": "Per 100g - Calories: 89kcal"}]}}
        with mock.patch.object(fs.requests, "post", return_value=_Response(json_body=body)):
            foods = _service().search_foods("banana")
        self.assertEqual([f.name for f in foods], ["Banana"])

    def test_every_failure_still_yields_an_empty_list_rather_than_raising(self):
        failures = [
            _Response(status_code=500, body="boom"),
            _Response(status_code=200, body="<error><code>21</code></error>"),
            _Response(status_code=200, body=""),
            _Response(json_body={"nope": 1}),
        ]
        for response in failures:
            with mock.patch.object(fs.requests, "post", return_value=response):
                self.assertEqual(_service().search_foods("x"), [])

    def test_a_transport_exception_never_escapes_to_the_caller(self):
        with mock.patch.object(fs.requests, "post",
                               side_effect=requests.exceptions.ConnectionError("x")):
            self.assertEqual(_service().search_foods("x"), [])


class NoSecretLeakTests(SimpleTestCase):
    """A diagnostic that leaks a credential is worse than no diagnostic."""

    def test_a_token_shaped_string_is_redacted_from_a_detail(self):
        token = "A" * 60
        out = _outcome(_Response(status_code=200,
                                 body=f"<error><message>Bearer {token}</message></error>"))
        self.assertNotIn(token, out.detail)
        self.assertIn("[redacted]", out.detail)

    def test_details_are_bounded(self):
        out = _outcome(_Response(status_code=500, body="e" * 5000))
        self.assertLessEqual(len(out.detail), fs._DETAIL_CAP)

    def test_the_diagnostic_shape_carries_no_payload(self):
        body = {"foods": {"food": [{"food_id": "1", "food_name": "SECRET FOOD",
                                    "food_description": "Per 100g - Calories: 89kcal"}]}}
        diag = _outcome(_Response(json_body=body)).as_diagnostic()
        self.assertEqual(diag["count"], 1)
        self.assertNotIn("SECRET FOOD", str(diag))
