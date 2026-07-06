"""Place map + geocoding — the canonical Place owns its coordinates (no separate location
model). One interactive Leaflet map over Esri tiles; geocoding (search/reverse/auto) via the
Esri World Geocoding Service; coordinate provenance on every write; and the provider-
independent one-time location review."""

from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.forms import PlaceForm
from apps.legacy.models import Place
from apps.legacy.services import geocode as geocode_svc
from apps.legacy.services import location_review

User = get_user_model()


def _make_user(email="places@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class PlaceMapHelperTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def _place(self, **kw):
        return Place.objects.create(user=self.user, **kw)

    def test_open_in_maps_link_uses_text_query(self):
        # The "Open in Google Maps" link works from text alone (city), coords not required.
        p = self._place(name="Grandma's house", location_text="Maryville, Tennessee")
        self.assertEqual(p.map_query, "Maryville, Tennessee")
        self.assertIn("Maryville", p.maps_link_url)
        self.assertNotIn("Grandma", p.maps_link_url)    # personal name never geocoded
        self.assertTrue(p.maps_link_url.startswith("https://www.google.com/maps/search/?api=1&query="))

    def test_open_in_maps_uses_documented_coordinate_format(self):
        # Google's DOCUMENTED raw-coordinate pin: search action with URL-ENCODED comma
        # (%2C). Which format Google actually honours is confirmed in production via the
        # /legacy/debug/map/ glass box — not asserted here.
        p = self._place(name="Home", location_text="Knoxville, TN",
                        latitude=Decimal("35.9606"), longitude=Decimal("-83.9207"))
        self.assertEqual(p.maps_link_url,
                         "https://www.google.com/maps/search/?api=1&query=35.9606%2C-83.9207")

    def test_name_only_place_has_no_maps_link(self):
        # A bare personal name (no location text) would not geocode — no Google link.
        p = self._place(name="Grandma's house")
        self.assertEqual(p.map_query, "")
        self.assertEqual(p.maps_link_url, "")

    def test_no_location_yields_nothing(self):
        p = self._place(name="   ")
        self.assertEqual(p.map_query, "")
        self.assertEqual(p.maps_link_url, "")


class GeocodeTests(TestCase):
    def setUp(self):
        self.user = _make_user("geo@example.com")

    def test_ensure_coordinates_caches_lat_long_on_the_place(self):
        p = Place.objects.create(user=self.user, name="Home", location_text="Maryville, Tennessee")
        with mock.patch.object(geocode_svc, "geocode",
                               return_value=(Decimal("35.756000"), Decimal("-83.972000"))) as g:
            changed = geocode_svc.ensure_place_coordinates(p)
        self.assertTrue(changed)
        g.assert_called_once_with("Maryville, Tennessee")
        p.refresh_from_db()
        self.assertEqual(str(p.latitude), "35.756000")
        self.assertTrue(p.has_coordinates)

    def test_ensure_is_noop_when_already_geocoded(self):
        p = Place.objects.create(user=self.user, name="Home", location_text="X",
                                 latitude=Decimal("1.0"), longitude=Decimal("2.0"))
        with mock.patch.object(geocode_svc, "geocode") as g:
            self.assertFalse(geocode_svc.ensure_place_coordinates(p))
            g.assert_not_called()                       # never re-geocodes

    def test_ensure_is_noop_without_location_text(self):
        p = Place.objects.create(user=self.user, name="Grandma's house")
        with mock.patch.object(geocode_svc, "geocode") as g:
            self.assertFalse(geocode_svc.ensure_place_coordinates(p))
            g.assert_not_called()

    def test_geocode_miss_leaves_place_unchanged(self):
        p = Place.objects.create(user=self.user, name="Home", location_text="Nowhereville XYZ")
        with mock.patch.object(geocode_svc, "geocode", return_value=None):
            self.assertFalse(geocode_svc.ensure_place_coordinates(p))
        p.refresh_from_db()
        self.assertFalse(p.has_coordinates)             # degrades gracefully


class PlaceMapViewTests(TestCase):
    def setUp(self):
        self.user = _make_user("placeview@example.com")
        self.client.force_login(self.user)

    def test_every_place_has_one_interactive_esri_map(self):
        p = Place.objects.create(user=self.user, name="The lake house",
                                 location_text="Maryville, Tennessee")
        with mock.patch.object(geocode_svc, "geocode",
                               return_value=(Decimal("35.756000"), Decimal("-83.972000"))):
            html = self.client.get(reverse("legacy:place_detail", args=[p.pk])).content.decode()
        self.assertIn('id="placeMapCard"', html)                        # one unified map
        self.assertIn("World_Street_Map", html)                         # Esri Streets default
        self.assertIn("World_Imagery", html)                            # Esri Satellite option
        self.assertIn("leaflet/leaflet.js", html)                       # interactive (Leaflet)
        self.assertIn(">Streets<", html)
        self.assertIn(">Satellite<", html)
        self.assertIn("Save changes", html)
        self.assertIn("Open in Google Maps", html)
        self.assertNotIn("tile.openstreetmap.org", html)                # OSM tile server retired
        self.assertNotIn("export/embed.html", html)
        p.refresh_from_db()
        self.assertTrue(p.has_coordinates)                              # cached for reuse

    def test_unresolved_place_still_gets_the_map(self):
        # Even with no coordinates, the map is present (read-only prompt to search/pin).
        p = Place.objects.create(user=self.user, name="Mystery spot", location_text="ZzzUnknown")
        with mock.patch.object(geocode_svc, "geocode", return_value=None):
            html = self.client.get(reverse("legacy:place_detail", args=[p.pk])).content.decode()
        self.assertIn('id="placeMapCard"', html)
        self.assertIn("Not located yet", html)

    def test_detail_shows_coordinates_when_known(self):
        p = Place.objects.create(user=self.user, name="Home", location_text="Knoxville, TN",
                                 latitude=Decimal("35.960600"), longitude=Decimal("-83.920700"))
        html = self.client.get(reverse("legacy:place_detail", args=[p.pk])).content.decode()
        self.assertIn("pmap-coords", html)
        self.assertIn("35.9606", html)

    def test_no_comparison_mode_remains(self):
        # The temporary provider-comparison mode is gone — ?compare=1 is inert.
        p = Place.objects.create(user=self.user, name="Home", location_text="Knoxville, TN",
                                 latitude=Decimal("35.9606"), longitude=Decimal("-83.9207"))
        html = self.client.get(
            reverse("legacy:place_detail", args=[p.pk]) + "?compare=1").content.decode()
        self.assertNotIn('id="compareMap"', html)
        self.assertNotIn("Compare map styles", html)
        self.assertNotIn("CARTO", html)

    def test_place_form_accepts_coordinates(self):
        form = PlaceForm(data={"name": "Home", "location_text": "Knoxville, TN",
                               "description": "", "latitude": "35.9606", "longitude": "-83.9207"})
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        self.assertEqual(str(obj.latitude), "35.9606")


class GeocodeSearchReverseTests(TestCase):
    # Esri findAddressCandidates / reverseGeocode shapes (location: x=lon, y=lat).
    ESRI_SEARCH = ('{"candidates":['
                   '{"address":"3242 Old Plantation Way, Maryville, Tennessee, 37804",'
                   '"location":{"x":-83.8936,"y":35.7686},"score":100},'
                   '{"address":"Tuscaloosa County, AL","location":{"x":-87.525,"y":33.2895},"score":95}]}')
    ESRI_REVERSE = '{"address":{"LongLabel":"1 Main St, Maryville, TN, USA","Match_addr":"1 Main St"}}'
    ESRI_EMPTY = '{"candidates":[]}'

    def test_search_returns_a_valid_residential_address(self):
        # The exact address Nominatim returned [] for — Esri resolves it (score 100).
        with mock.patch.object(geocode_svc, "_http_get", return_value=(200, self.ESRI_SEARCH)):
            hits = geocode_svc.search("3242 Old Plantation Way, Maryville, TN 37804")
        self.assertEqual(len(hits), 2)
        self.assertIn("Old Plantation Way", hits[0]["label"])
        self.assertEqual(str(hits[0]["lat"]), "35.768600")     # y → lat
        self.assertEqual(str(hits[0]["lon"]), "-83.893600")    # x → lon, not swapped
        self.assertEqual(hits[0]["score"], 100)

    def test_search_empty_query_skips_network(self):
        with mock.patch.object(geocode_svc, "_http_get") as g:
            self.assertEqual(geocode_svc.search("   "), [])
            g.assert_not_called()

    def test_search_empty_result_returns_empty(self):
        with mock.patch.object(geocode_svc, "_http_get", return_value=(200, self.ESRI_EMPTY)):
            self.assertEqual(geocode_svc.search("nowhere xyz"), [])

    def test_reverse_returns_address(self):
        with mock.patch.object(geocode_svc, "_http_get", return_value=(200, self.ESRI_REVERSE)):
            self.assertEqual(geocode_svc.reverse("35.75", "-83.97"), "1 Main St, Maryville, TN, USA")

    def test_reverse_miss_returns_blank(self):
        with mock.patch.object(geocode_svc, "_http_get", return_value=(None, None)):
            self.assertEqual(geocode_svc.reverse("35.75", "-83.97"), "")

    def test_probe_exposes_request_and_raw_response(self):
        with mock.patch.object(geocode_svc, "_http_get", return_value=(200, self.ESRI_SEARCH)):
            p = geocode_svc.probe("3242 Old Plantation Way, Maryville, TN 37804")
        self.assertEqual(p["provider"], "esri")
        self.assertIn("geocode.arcgis.com", p["request_url"])
        self.assertEqual(p["http_status"], 200)
        self.assertEqual(p["raw_candidate_count"], 2)
        self.assertEqual(p["returned_count"], 2)
        self.assertEqual(p["dropped_no_coords"], 0)

    def test_parse_latlon_validates_range(self):
        self.assertIsNotNone(geocode_svc.parse_latlon("35.75", "-83.97"))
        self.assertIsNone(geocode_svc.parse_latlon("120", "0"))      # lat out of range
        self.assertIsNone(geocode_svc.parse_latlon("0", "200"))      # lon out of range
        self.assertIsNone(geocode_svc.parse_latlon("abc", "1"))      # not a number


class PlaceLocateWorkflowTests(TestCase):
    def setUp(self):
        self.user = _make_user("locate@example.com")
        self.client.force_login(self.user)
        self.place = Place.objects.create(user=self.user, name="Grandma's farm")  # unresolvable

    def test_unresolved_place_gets_the_editable_map(self):
        # No location text → the one map shows, inviting a search or dropped pin.
        html = self.client.get(reverse("legacy:place_detail", args=[self.place.pk])).content.decode()
        self.assertIn('id="placeMapCard"', html)
        self.assertIn('id="placeMap"', html)
        self.assertIn("leaflet/leaflet.js", html)          # interactive map assets
        self.assertIn("Not located yet", html)
        self.assertIn("Search", html)

    def test_resolved_place_uses_the_same_map(self):
        self.place.latitude = Decimal("35.0"); self.place.longitude = Decimal("-83.0")
        self.place.save(update_fields=["latitude", "longitude"])
        html = self.client.get(reverse("legacy:place_detail", args=[self.place.pk])).content.decode()
        self.assertIn('id="placeMapCard"', html)            # same single map, now centred
        self.assertIn("World_Imagery", html)                # Satellite toggle available too

    def test_search_endpoint_returns_json(self):
        with mock.patch.object(geocode_svc, "search",
                               return_value=[{"label": "Tuscaloosa, AL", "lat": Decimal("33.2"),
                                              "lon": Decimal("-87.5")}]):
            r = self.client.post(reverse("legacy:place_locate_search", args=[self.place.pk]),
                                 {"q": "Tuscaloosa"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["results"][0]["label"], "Tuscaloosa, AL")
        self.assertEqual(data["results"][0]["lat"], "33.2")

    def test_reverse_endpoint_returns_json(self):
        with mock.patch.object(geocode_svc, "reverse", return_value="1 Main St"):
            r = self.client.post(reverse("legacy:place_locate_reverse", args=[self.place.pk]),
                                 {"lat": "35.7", "lon": "-83.9"})
        self.assertEqual(r.json()["address"], "1 Main St")

    def test_save_stores_coordinates_permanently(self):
        r = self.client.post(reverse("legacy:place_locate_save", args=[self.place.pk]),
                             {"lat": "35.756500", "lon": "-83.970500"})
        self.assertEqual(r.status_code, 302)
        self.place.refresh_from_db()
        self.assertTrue(self.place.has_coordinates)
        self.assertEqual(str(self.place.latitude), "35.756500")

    def test_save_rejects_invalid_pin(self):
        r = self.client.post(reverse("legacy:place_locate_save", args=[self.place.pk]),
                             {"lat": "999", "lon": "0"})
        self.assertEqual(r.status_code, 302)
        self.place.refresh_from_db()
        self.assertFalse(self.place.has_coordinates)

    def test_locate_endpoints_are_owner_scoped(self):
        other = _make_user("intruder2@example.com")
        self.client.force_login(other)
        r = self.client.post(reverse("legacy:place_locate_save", args=[self.place.pk]),
                             {"lat": "1", "lon": "1"})
        self.assertEqual(r.status_code, 404)
        self.place.refresh_from_db()
        self.assertFalse(self.place.has_coordinates)


class CoordinateProvenanceTests(TestCase):
    def setUp(self):
        self.user = _make_user("prov@example.com")
        self.client.force_login(self.user)

    def test_auto_geocode_records_esri(self):
        p = Place.objects.create(user=self.user, name="Home", location_text="Maryville, TN")
        with mock.patch.object(geocode_svc, "geocode",
                               return_value=(Decimal("35.75"), Decimal("-83.97"))):
            self.client.get(reverse("legacy:place_detail", args=[p.pk]))
        p.refresh_from_db()
        self.assertEqual(p.coordinate_source, "esri")

    def test_save_from_search_is_esri_from_pin_is_pin(self):
        p = Place.objects.create(user=self.user, name="Spot")
        self.client.post(reverse("legacy:place_locate_save", args=[p.pk]),
                         {"lat": "35.1", "lon": "-83.1", "source": "esri"})
        p.refresh_from_db(); self.assertEqual(p.coordinate_source, "esri")
        self.client.post(reverse("legacy:place_locate_save", args=[p.pk]),
                         {"lat": "35.2", "lon": "-83.2", "source": "pin"})
        p.refresh_from_db(); self.assertEqual(p.coordinate_source, "pin")

    def test_save_defaults_to_pin_when_source_missing(self):
        p = Place.objects.create(user=self.user, name="Spot")
        self.client.post(reverse("legacy:place_locate_save", args=[p.pk]),
                         {"lat": "35.1", "lon": "-83.1"})
        p.refresh_from_db(); self.assertEqual(p.coordinate_source, "pin")

    def test_manual_form_entry_is_manual(self):
        r = self.client.post(reverse("legacy:place_new"),
                             {"name": "Typed", "location_text": "X", "description": "",
                              "latitude": "35.5", "longitude": "-83.5"})
        self.assertEqual(r.status_code, 302)
        p = Place.objects.get(user=self.user, name="Typed")
        self.assertEqual(p.coordinate_source, "manual")


class LocationReviewTests(TestCase):
    def setUp(self):
        self.user = _make_user("review@example.com")
        self.client.force_login(self.user)

    def _legacy_place(self, **kw):
        # Legacy = coordinate_source blank (set before provenance).
        kw.setdefault("coordinate_source", "")
        return Place.objects.create(user=self.user, **kw)

    def test_haversine_is_reasonable(self):
        # ~0.01 deg latitude ≈ 1.11 km.
        d = location_review.haversine_m(35.0, -83.0, 35.01, -83.0)
        self.assertTrue(1000 < d < 1200, d)

    def test_diverging_legacy_place_is_a_candidate(self):
        p = self._legacy_place(name="Old Home", location_text="Maryville, TN",
                               latitude=Decimal("35.756472"), longitude=Decimal("-83.970459"))
        with mock.patch.object(geocode_svc, "search",
                               return_value=[{"label": "Maryville, Tennessee",
                                              "lat": Decimal("35.750607"),
                                              "lon": Decimal("-83.973082"), "score": 100}]):
            cands = location_review.review_candidates(self.user, min_distance_m=25)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["place"].pk, p.pk)
        self.assertGreater(cands[0]["distance_m"], 300)      # ~695 m apart

    def test_agreeing_coordinate_is_not_a_candidate(self):
        self._legacy_place(name="Good", location_text="Maryville, TN",
                           latitude=Decimal("35.750600"), longitude=Decimal("-83.973080"))
        with mock.patch.object(geocode_svc, "search",
                               return_value=[{"label": "Maryville", "lat": Decimal("35.750607"),
                                              "lon": Decimal("-83.973082"), "score": 100}]):
            self.assertEqual(location_review.review_candidates(self.user), [])

    def test_already_sourced_place_excluded(self):
        self._legacy_place(name="Pinned", location_text="Maryville, TN", coordinate_source="pin",
                           latitude=Decimal("35.756472"), longitude=Decimal("-83.970459"))
        with mock.patch.object(geocode_svc, "search") as s:
            self.assertEqual(location_review.review_candidates(self.user), [])
            s.assert_not_called()                            # not even scanned

    def test_place_without_location_text_excluded(self):
        self._legacy_place(name="Grandma's farm",
                           latitude=Decimal("35.7"), longitude=Decimal("-83.9"))
        with mock.patch.object(geocode_svc, "search") as s:
            self.assertEqual(location_review.review_candidates(self.user), [])
            s.assert_not_called()

    def test_use_suggested_adopts_esri_and_records_source(self):
        p = self._legacy_place(name="Old", location_text="X",
                               latitude=Decimal("35.0"), longitude=Decimal("-83.0"))
        r = self.client.post(reverse("legacy:location_review_apply", args=[p.pk]),
                             {"action": "use", "lat": "35.75", "lon": "-83.97"})
        self.assertEqual(r.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(str(p.latitude), "35.750000")
        self.assertEqual(p.coordinate_source, "esri")

    def test_keep_current_preserves_coords_and_marks_reviewed(self):
        p = self._legacy_place(name="Mine", location_text="X",
                               latitude=Decimal("35.111111"), longitude=Decimal("-83.222222"))
        self.client.post(reverse("legacy:location_review_apply", args=[p.pk]), {"action": "keep"})
        p.refresh_from_db()
        self.assertEqual(str(p.latitude), "35.111111")       # unchanged
        self.assertEqual(p.coordinate_source, "reviewed")    # drops out of future reviews

    def test_review_apply_is_owner_scoped(self):
        other = _make_user("intruder3@example.com")
        p = self._legacy_place(name="Mine", latitude=Decimal("35.0"), longitude=Decimal("-83.0"))
        self.client.force_login(other)
        r = self.client.post(reverse("legacy:location_review_apply", args=[p.pk]), {"action": "keep"})
        self.assertEqual(r.status_code, 404)
