"""Place map preview — the map is another consumer of the canonical Place. It centres on
the Place's coordinates; when only a city/address is known, the view geocodes it once and
caches lat/long on the Place (no separate location model). Keyless OpenStreetMap embed."""

from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.forms import PlaceForm
from apps.legacy.models import Place
from apps.legacy.services import geocode as geocode_svc

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

    def test_embed_centres_on_coordinates_via_openstreetmap(self):
        p = self._place(name="Marvin's home", location_text="Maryville, Tennessee",
                        latitude=Decimal("35.756000"), longitude=Decimal("-83.972000"))
        self.assertTrue(p.has_coordinates)
        url = p.maps_embed_url
        self.assertTrue(url.startswith("https://www.openstreetmap.org/export/embed.html"))
        self.assertIn("marker=35.756000,-83.972000", url)
        self.assertIn("bbox=", url)

    def test_no_coordinates_yields_no_embed(self):
        p = self._place(name="Grandma's house", location_text="Maryville, Tennessee")
        self.assertFalse(p.has_coordinates)
        self.assertEqual(p.maps_embed_url, "")          # geocoded lazily by the view

    def test_open_in_maps_link_uses_text_query(self):
        # The "Open in Google Maps" link works from text alone (city), coords not required.
        p = self._place(name="Grandma's house", location_text="Maryville, Tennessee")
        self.assertEqual(p.map_query, "Maryville, Tennessee")
        self.assertIn("Maryville", p.maps_link_url)
        self.assertNotIn("Grandma", p.maps_link_url)    # personal name never geocoded
        self.assertTrue(p.maps_link_url.startswith("https://www.google.com/maps/search/"))

    def test_name_only_place_has_no_map(self):
        # A bare personal name (no location text) would not geocode — no map, no link.
        p = self._place(name="Grandma's house")
        self.assertEqual(p.map_query, "")
        self.assertEqual(p.maps_embed_url, "")
        self.assertEqual(p.maps_link_url, "")

    def test_no_location_yields_nothing(self):
        p = self._place(name="   ")
        self.assertEqual(p.map_query, "")
        self.assertEqual(p.maps_embed_url, "")
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

    def test_detail_geocodes_a_city_and_embeds_the_map(self):
        p = Place.objects.create(user=self.user, name="The lake house",
                                 location_text="Maryville, Tennessee")
        with mock.patch.object(geocode_svc, "geocode",
                               return_value=(Decimal("35.756000"), Decimal("-83.972000"))):
            html = self.client.get(reverse("legacy:place_detail", args=[p.pk])).content.decode()
        self.assertIn("place-map-frame", html)                          # embedded map
        self.assertIn("openstreetmap.org/export/embed.html", html)      # keyless, frameable
        self.assertIn("Open in Google Maps", html)
        self.assertIn("Where this is", html)
        p.refresh_from_db()
        self.assertTrue(p.has_coordinates)                              # cached for reuse

    def test_detail_without_geocode_still_offers_open_in_maps(self):
        p = Place.objects.create(user=self.user, name="Mystery spot", location_text="ZzzUnknown")
        with mock.patch.object(geocode_svc, "geocode", return_value=None):
            html = self.client.get(reverse("legacy:place_detail", args=[p.pk])).content.decode()
        self.assertNotIn("place-map-frame", html)                       # no coords → no embed
        self.assertIn("Open in Google Maps", html)                      # link still works

    def test_detail_shows_coordinates_when_known(self):
        p = Place.objects.create(user=self.user, name="Home", location_text="Knoxville, TN",
                                 latitude=Decimal("35.960600"), longitude=Decimal("-83.920700"))
        html = self.client.get(reverse("legacy:place_detail", args=[p.pk])).content.decode()
        self.assertIn("place-map-coords", html)
        self.assertIn("35.9606", html)

    def test_place_form_accepts_coordinates(self):
        form = PlaceForm(data={"name": "Home", "location_text": "Knoxville, TN",
                               "description": "", "latitude": "35.9606", "longitude": "-83.9207"})
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        self.assertEqual(str(obj.latitude), "35.9606")


class GeocodeSearchReverseTests(TestCase):
    def test_search_returns_labelled_candidates(self):
        sample = [{"display_name": "Tuscaloosa, AL, USA", "lat": "33.209", "lon": "-87.569"},
                  {"display_name": "Tuscaloosa County, AL", "lat": "33.29", "lon": "-87.52"}]
        with mock.patch.object(geocode_svc, "_get", return_value=sample):
            hits = geocode_svc.search("Tuscaloosa")
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["label"], "Tuscaloosa, AL, USA")
        self.assertEqual(str(hits[0]["lat"]), "33.209000")

    def test_search_empty_query_skips_network(self):
        with mock.patch.object(geocode_svc, "_get") as g:
            self.assertEqual(geocode_svc.search("   "), [])
            g.assert_not_called()

    def test_reverse_returns_address(self):
        with mock.patch.object(geocode_svc, "_get", return_value={"display_name": "1 Main St, Maryville"}):
            self.assertEqual(geocode_svc.reverse("35.75", "-83.97"), "1 Main St, Maryville")

    def test_reverse_miss_returns_blank(self):
        with mock.patch.object(geocode_svc, "_get", return_value=None):
            self.assertEqual(geocode_svc.reverse("35.75", "-83.97"), "")

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

    def test_resolver_shows_when_unresolved(self):
        # No location text → auto-geocode is skipped → the resolver (search + pin) shows.
        html = self.client.get(reverse("legacy:place_detail", args=[self.place.pk])).content.decode()
        self.assertIn('id="placeLocate"', html)
        self.assertIn('id="locateMap"', html)
        self.assertIn("leaflet/leaflet.js", html)          # interactive map assets
        self.assertIn("Where is this?", html)

    def test_resolver_hidden_once_resolved(self):
        self.place.latitude = Decimal("35.0"); self.place.longitude = Decimal("-83.0")
        self.place.save(update_fields=["latitude", "longitude"])
        html = self.client.get(reverse("legacy:place_detail", args=[self.place.pk])).content.decode()
        self.assertNotIn('id="placeLocate"', html)          # never asked again
        self.assertIn("place-map-frame", html)              # shows the resolved map instead

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
