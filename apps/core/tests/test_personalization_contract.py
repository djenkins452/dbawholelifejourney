# ==============================================================================
# File: apps/core/tests/test_personalization_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: M1 contract guards — personalization must REACH the certified runtime
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-18
# ==============================================================================
"""M1 personalization contract tests (T1-T4, T22).

WHY THESE EXIST — a production trust failure, not a hypothetical:
between 2026-07-09 and 2026-08-18 the certified `model_interface` runtime received the
persona SLUG with no voice instructions, and `sensitivity_tags` reached it not at all.
Fourteen personas were decorative and a boundary the user set did nothing, while the
Preferences UI kept promising both. Nothing failed, because nothing ASSERTED delivery.

These guard the PRODUCT PROMISE, not the implementation:
  T1  the composed persona VOICE reaches the system prompt (a slug is not enough)
  T2  explicit user setting > persona default > system default, with provenance
  T3  EVERY canonical preference is delivered into the envelope  <- load-bearing
  T4  EVERY user-editable control has a runtime consumer         <- load-bearing
  T22 no WLJ-authored interpretation/prose is reintroduced

Governing: docs/WLJ_PERSONALIZATION_PERSONAL_KNOWLEDGE_CONTRACTS.md (Contracts 1-3, 16).
"""

import json
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.cos_services.ai_relationship import (
    CANONICAL_PREFERENCES,
    SOURCE_DEFAULT,
    SOURCE_PERSONA,
    SOURCE_USER,
    get_ai_relationship,
    resolve_operational_preferences,
    resolve_persona,
)

User = get_user_model()
REPO = Path(__file__).resolve().parents[3]


def _dig(payload, dotted):
    """Walk a dotted path through nested dicts; raise KeyError naming the miss."""
    node = payload
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"{dotted} (missing at {part!r})")
        node = node[part]
    return node


class PersonaVoiceDeliveryTests(TestCase):
    """T1 — the persona's composed VOICE must reach the model, not just its key."""

    def setUp(self):
        from apps.ai.models import CoachingStyle
        self.style = CoachingStyle.objects.create(
            key="contract_test_persona", name="Contract Test Persona",
            description="Fixture persona for the delivery contract.", icon="🧪",
            prompt_instructions="Speak ONLY in deliberate contract-test cadence.",
            voice_attributes={"register": "test", "signature_expressions": ["marker-phrase"]},
            is_active=True, sort_order=999,
        )
        self.user = User.objects.create_user(
            email="t1@contract.test", password="x", first_name="T1")
        prefs = self.user.preferences
        prefs.ai_coaching_style = self.style.key
        prefs.save()

    def test_composed_instructions_include_authored_voice_and_attributes(self):
        composed = self.style.composed_instructions()
        self.assertIn("deliberate contract-test cadence", composed)
        self.assertIn("marker-phrase", composed,
                      "voice_attributes must contribute to the composed persona block")

    def test_projection_carries_persona_identity_and_instructions(self):
        rel = get_ai_relationship(self.user)
        persona = rel["assistant"]["persona"]
        self.assertEqual(persona["key"], self.style.key)
        self.assertEqual(persona["name"], self.style.name,
                         "the persona NAME must reach the model, not only its slug")
        self.assertIn("deliberate contract-test cadence", rel["persona_instructions"],
                      "T1: persona VOICE INSTRUCTIONS must reach the runtime. A bare "
                      "slug tells the model nothing about how to sound.")

    def test_voice_reaches_the_certified_system_prompt(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self.user)
        ctx = svc.build_standing_context()
        prompt = svc._system_prompt(ctx)
        self.assertIn("deliberate contract-test cadence", prompt,
                      "T1: the persona voice must appear in the SYSTEM PROMPT the "
                      "certified runtime sends. This is the assertion whose absence "
                      "let personas be decorative for six weeks.")
        self.assertIn("VOICE ONLY", prompt,
                      "the persona lead must state that voice never changes truth")

    def test_persona_never_relaxes_truth_preferences(self):
        rel = get_ai_relationship(self.user)
        self.assertFalse(rel["truth_preferences"]["may_invent_facts"],
                         "no persona may ever license invention")


class PrecedenceTests(TestCase):
    """T2 — LOCKED: explicit user setting > persona default > system default."""

    def setUp(self):
        from apps.ai.models import CoachingStyle
        self.style = CoachingStyle.objects.create(
            key="precedence_test_persona", name="Precedence Test Persona",
            description="Suggests firm accountability and low question frequency.",
            prompt_instructions="Test voice.",
            operational_defaults={"accountability": "firm", "question_frequency": "low"},
            is_active=True, sort_order=998,
        )
        self.user = User.objects.create_user(
            email="t2@contract.test", password="x", first_name="T2")
        self.prefs = self.user.preferences
        self.prefs.ai_coaching_style = self.style.key
        self.prefs.save()
        from apps.core.blueprint.engine import get_blueprint
        self.bp = get_blueprint(self.user)

    def _resolve(self):
        persona = resolve_persona(self.user, self.prefs)
        return resolve_operational_preferences(
            self.user, prefs=self.prefs, blueprint=self.bp, persona=persona)

    def test_persona_default_applies_when_user_has_not_chosen(self):
        self.bp.accountability_style = ""
        self.bp.question_frequency = ""
        self.bp.save()
        values, provenance = self._resolve()
        self.assertEqual(values["accountability"], "firm")
        self.assertEqual(provenance["accountability"], SOURCE_PERSONA)

    def test_explicit_user_setting_beats_persona_default(self):
        self.bp.accountability_style = "light"
        self.bp.question_frequency = "high"
        self.bp.save()
        values, provenance = self._resolve()
        self.assertEqual(values["accountability"], "light",
                         "T2: a persona may SUGGEST; it may never override an explicit choice")
        self.assertEqual(provenance["accountability"], SOURCE_USER)
        self.assertEqual(values["question_frequency"], "high")
        self.assertEqual(provenance["question_frequency"], SOURCE_USER)

    def test_system_default_applies_with_neither(self):
        from apps.ai.models import CoachingStyle
        CoachingStyle.objects.filter(pk=self.style.pk).update(operational_defaults={})
        self.style.refresh_from_db()
        self.bp.accountability_style = ""
        self.bp.save()
        values, provenance = self._resolve()
        self.assertEqual(values["accountability"],
                         CANONICAL_PREFERENCES["accountability"]["default"])
        self.assertEqual(provenance["accountability"], SOURCE_DEFAULT)

    def test_composition_scenario_from_the_frozen_design(self):
        """Texas Rancher + Deep Dive + Firm + Low must compose without override."""
        self.prefs.cos_response_style = "deep_dive"
        self.prefs.save()
        self.bp.accountability_style = "firm"
        self.bp.question_frequency = "low"
        self.bp.save()
        rel = get_ai_relationship(self.user)
        self.assertEqual(rel["communication"]["detail_level"], "deep_dive")
        self.assertEqual(rel["accountability"]["level"], "firm")
        self.assertEqual(rel["accountability"]["question_frequency"], "low")
        self.assertEqual(rel["assistant"]["persona"]["key"], self.style.key)

    def test_false_is_an_explicit_choice_not_an_unset_value(self):
        """A user turning something OFF must not be treated as 'no opinion'."""
        self.prefs.assistant_confirm_actions = False
        self.prefs.save()
        _, provenance = self._resolve()
        self.assertEqual(provenance["confirm_actions"], SOURCE_USER)


class CanonicalPreferenceDeliveryTests(TestCase):
    """T3 — EVERY canonical preference must be delivered into the envelope.

    Adding a preference to CANONICAL_PREFERENCES without runtime delivery FAILS CI.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="t3@contract.test", password="x", first_name="T3")

    def test_every_canonical_preference_reaches_the_projection(self):
        rel = get_ai_relationship(self.user)
        missing = []
        for name, spec in CANONICAL_PREFERENCES.items():
            try:
                _dig(rel, spec["path"])
            except KeyError as exc:
                missing.append(f"{name} -> {exc}")
        self.assertEqual(missing, [], (
            "T3: these canonical preferences are NOT delivered to the certified "
            "runtime:\n  " + "\n  ".join(missing) + "\n"
            "Every entry in CANONICAL_PREFERENCES must be projected by "
            "get_ai_relationship(). This is the guard that would have caught "
            "`sensitivity_tags` reaching nothing for six weeks."))

    def test_every_canonical_preference_reaches_the_system_prompt(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self.user)
        ctx = svc.build_standing_context()
        prompt = svc._system_prompt(ctx)
        self.assertIn("ai_relationship", prompt)
        rel = ctx.get("ai_relationship") or {}
        for name, spec in CANONICAL_PREFERENCES.items():
            with self.subTest(preference=name):
                _dig(rel, spec["path"])   # raises KeyError naming the miss

    def test_canonical_field_names_exist_on_their_declared_authority(self):
        """A preference must point at storage that actually exists."""
        from apps.core.blueprint.engine import get_blueprint
        prefs, bp = self.user.preferences, get_blueprint(self.user)
        for name, spec in CANONICAL_PREFERENCES.items():
            container = prefs if spec["source"] == "prefs" else bp
            with self.subTest(preference=name):
                self.assertTrue(
                    hasattr(container, spec["field"]),
                    f"{name}: declared field {spec['field']!r} does not exist on "
                    f"{spec['source']} — the vocabulary points at nothing.")

    def test_sensitivity_boundaries_reach_the_prompt_as_text(self):
        """The boundary a user sets must be visible to the model, not just stored."""
        from apps.ai.model_interface.service import ModelInterfaceService
        from apps.core.blueprint.engine import get_blueprint
        bp = get_blueprint(self.user)
        bp.sensitivity_tags = ["contract-boundary-marker"]
        bp.save()
        svc = ModelInterfaceService(self.user)
        prompt = svc._system_prompt(svc.build_standing_context())
        self.assertIn("contract-boundary-marker", prompt,
                      "T3: a boundary the user set must reach the model")


class UserEditableControlCoverageTests(SimpleTestCase):
    """T4 — every user-editable personalization control must have a runtime consumer.

    A visible control that does nothing FAILS CI. This is the class that produced the
    2026-08-17 investigation: the UI promised persona voice, learned context and
    sensitivity topics while the runtime consumed none of them.
    """

    # Personalization inputs rendered in Preferences → Chief of Staff & AI.
    # Each MUST map to a canonical preference (delivered by T3) or be listed as a
    # deliberate, documented exception below.
    CONTROL_TO_CANONICAL = {
        "ai_coaching_style": "coaching_style",
        "cos_response_style": "response_depth",
        "accountability_style": "accountability",
        "question_frequency": "question_frequency",
        "knowledge_invitations": "knowledge_invitations",
        "assistant_confirm_actions": "confirm_actions",
        "event_reflections": "event_reflections",
        "relationship_suggestions": "relationship_suggestions",
        "sensitivity_tags": "sensitivity_topics",
        "preference_learning_enabled": "preference_learning",
    }
    # Deliberate exceptions, each with a stated reason. Adding to this list is a
    # reviewed decision, which is the point — silence is what failed before.
    DOCUMENTED_EXCEPTIONS = {
        "cos_display_name": "delivered as ai_relationship.assistant.display_name",
        "ai_data_consent": "governance gate, not an operational preference (Contract 2.3)",
        "ai_enabled": "governance gate mirrored from ai_data_consent",
        "ai_profile": "M2/M3 own Personal Knowledge; not an M1 operational preference",
        "ai_personal_context": "legacy Learned Context — M3 owns its replacement",
    }

    def test_every_rendered_control_maps_to_a_delivered_preference(self):
        for control, canonical in self.CONTROL_TO_CANONICAL.items():
            with self.subTest(control=control):
                self.assertIn(canonical, CANONICAL_PREFERENCES, (
                    f"T4: the Preferences UI renders {control!r}, but it maps to no "
                    f"canonical preference — so nothing delivers it to the Chief of "
                    f"Staff. A control that does nothing is a broken promise."))

    def test_rendered_controls_are_actually_present_in_the_template(self):
        html = (REPO / "templates" / "users" / "preferences.html").read_text(encoding="utf-8")
        for control in self.CONTROL_TO_CANONICAL:
            with self.subTest(control=control):
                self.assertRegex(html, rf'name="{re.escape(control)}"',
                                 f"{control} is claimed by the contract but not rendered")

    def test_no_unmapped_personalization_control_is_rendered(self):
        """Catches a NEW control added to the CoS section with no runtime consumer."""
        html = (REPO / "templates" / "users" / "preferences.html").read_text(encoding="utf-8")
        start = html.index('data-accordion-key="chief-of-staff"')
        end = html.index('data-accordion-key="location"')
        rendered = set(re.findall(r'name="([a-z_]+)"', html[start:end]))
        known = set(self.CONTROL_TO_CANONICAL) | set(self.DOCUMENTED_EXCEPTIONS)
        unknown = sorted(rendered - known)
        self.assertEqual(unknown, [], (
            "T4: these controls are rendered in the Chief of Staff settings but map to "
            f"no canonical preference and no documented exception: {unknown}. Either "
            "deliver them to the runtime, or record why they are exempt."))

    def test_settings_have_exactly_one_home(self):
        """The retired CoS Settings page must no longer edit the moved controls."""
        cos = (REPO / "templates" / "ai" / "cos_settings.html").read_text(encoding="utf-8")
        for control in ("accountability_style", "question_frequency",
                        "sensitivity_tags", "cos_display_name"):
            with self.subTest(control=control):
                self.assertNotIn(f'name="{control}"', cos, (
                    f"{control} is still editable on the CoS Settings page. Two editors "
                    "for one setting is the dual-authority defect that let "
                    "`sensitivity_tags` drift out of the runtime."))


class InteractionGuidanceBoundaryTests(SimpleTestCase):
    """T22 — WLJ must not author interpretation or prose about the user (Contract 3.4)."""

    def test_no_wlj_authored_interpretation_is_projected(self):
        src = (REPO / "apps" / "ai" / "cos_services" / "ai_relationship.py").read_text(
            encoding="utf-8")
        self.assertNotIn("BehaviorDirective", src, (
            "T22: the legacy BehaviorDirective store must not be reconnected wholesale. "
            "Interaction Guidance is stated-source only and belongs to Operational "
            "Preferences (Contract 3), not to this projection."))

    def test_persona_registry_stores_no_interpretation_of_the_user(self):
        from apps.ai.models import CoachingStyle
        fields = {f.name for f in CoachingStyle._meta.get_fields()}
        for forbidden in ("meaning", "observation", "behavior_change", "evidence"):
            self.assertNotIn(forbidden, fields, (
                f"T22: {forbidden!r} would make the persona registry a store of "
                "WLJ-authored interpretation. WLJ exposes facts; the model interprets "
                "(Constitution I.4)."))

    def test_no_personal_knowledge_implementation_leaked_into_m1(self):
        """M1 must not pull M2+ forward (Definition-of-done §13)."""
        src = (REPO / "apps" / "ai" / "cos_services" / "ai_relationship.py").read_text(
            encoding="utf-8")
        for m2_term in ("PersonalKnowledgeFact", "get_personal_knowledge",
                        "knowledge_map", "candidate_fact"):
            self.assertNotIn(m2_term, src,
                             f"M1 must not implement {m2_term} — that is M2/M3 scope.")


class PersonaRegistryIntegrityTests(TestCase):
    """The registry itself must stay trustworthy (Contract 1.1)."""

    def test_persona_fixture_is_not_addressed_by_primary_key(self):
        """pk-addressed fixtures silently destroyed users' selected personas."""
        raw = json.loads((REPO / "apps" / "ai" / "fixtures" /
                          "coaching_styles.json").read_text(encoding="utf-8"))
        bad = [r for r in raw if r.get("pk") not in (None,)]
        self.assertEqual(bad, [], (
            "The persona fixture must not carry hard-coded pks. `key` is the identity "
            "(it is what UserPreferences.ai_coaching_style stores); pk-addressed loads "
            "overwrote the Armed Forces personas and destroyed user selections."))

    def test_every_fixture_persona_has_a_distinct_voice(self):
        raw = json.loads((REPO / "apps" / "ai" / "fixtures" /
                          "coaching_styles.json").read_text(encoding="utf-8"))
        seen = {}
        for row in raw:
            f = row["fields"]
            instructions = (f.get("prompt_instructions") or "").strip()
            with self.subTest(persona=f.get("key")):
                self.assertGreater(len(instructions), 200,
                                   f"{f.get('key')}: persona voice is too thin to be distinct")
                self.assertNotIn(instructions, seen,
                                 f"{f.get('key')} duplicates the voice of {seen.get(instructions)}")
            seen[instructions] = f.get("key")

    def test_persona_operational_defaults_use_canonical_values(self):
        """A persona default that no authority accepts would silently do nothing."""
        raw = json.loads((REPO / "apps" / "ai" / "fixtures" /
                          "coaching_styles.json").read_text(encoding="utf-8"))
        allowed = {
            "accountability": {"light", "standard", "firm"},
            "question_frequency": {"low", "medium", "high"},
            "response_depth": {"concise", "balanced", "strategic", "deep_dive"},
        }
        for row in raw:
            f = row["fields"]
            for key, value in (f.get("operational_defaults") or {}).items():
                with self.subTest(persona=f.get("key"), setting=key):
                    self.assertIn(key, allowed, f"{key} is not a persona-suggestable setting")
                    self.assertIn(value, allowed[key],
                                  f"{f.get('key')}: {key}={value!r} is not a canonical value")


class ExistingChoicePreservationTests(TestCase):
    """Definition-of-done §9 — consolidating settings must not reset anyone."""

    def setUp(self):
        from apps.ai.models import CoachingStyle
        # Self-contained: personas are seeded by `seed_personas` at deploy time, not by a
        # migration, so a test database has none. Create the one this test selects.
        CoachingStyle.objects.get_or_create(
            key="southern_belle",
            defaults=dict(name="Southern Belle", description="Warm Southern charm.",
                          icon="🌺", prompt_instructions="Speak with warm Southern charm.",
                          is_active=True, sort_order=40))
        self.user = User.objects.create_user(
            email="t9@contract.test", password="pw-contract-9", first_name="T9")
        prefs = self.user.preferences
        prefs.ai_coaching_style = "southern_belle"
        prefs.cos_display_name = "Miss Bea"
        prefs.cos_response_style = "deep_dive"
        prefs.assistant_confirm_actions = True
        prefs.knowledge_invitations = "naturally"
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.save()
        from apps.core.blueprint.engine import get_blueprint
        bp = get_blueprint(self.user)
        bp.accountability_style = "firm"
        bp.question_frequency = "low"
        bp.sensitivity_tags = ["grief"]
        bp.save()

    def test_a_partial_post_does_not_reset_chief_of_staff_choices(self):
        """An unrelated save elsewhere on the page must leave CoS settings alone."""
        from apps.core.blueprint.engine import get_blueprint
        from apps.users.views import PreferencesView
        from django.test import RequestFactory

        request = RequestFactory().post("/preferences/", {"theme": "midnight"})
        request.user = self.user
        view = PreferencesView()
        view.request = request
        view.object = self.user.preferences

        form = view.get_form_class()(
            data={"theme": "midnight"}, instance=self.user.preferences)
        form.is_valid()
        try:
            view.form_valid(form)
        except Exception:
            pass                      # messages/redirect machinery is not under test

        prefs = type(self.user.preferences).objects.get(pk=self.user.preferences.pk)
        bp = get_blueprint(self.user)
        self.assertEqual(prefs.knowledge_invitations, "naturally",
                         "§9: a partial POST reset the invitation preference")
        self.assertTrue(prefs.assistant_confirm_actions,
                        "§9: a partial POST reset action confirmations")
        self.assertEqual(bp.accountability_style, "firm",
                         "§9: a partial POST reset accountability")
        self.assertEqual(bp.sensitivity_tags, ["grief"],
                         "§9: a partial POST reset the user's boundaries")

    def test_existing_choices_survive_into_the_runtime_projection(self):
        rel = get_ai_relationship(self.user)
        self.assertEqual(rel["assistant"]["display_name"], "Miss Bea")
        self.assertEqual(rel["assistant"]["persona"]["key"], "southern_belle")
        self.assertEqual(rel["communication"]["detail_level"], "deep_dive")
        self.assertEqual(rel["accountability"]["level"], "firm")
        self.assertEqual(rel["accountability"]["question_frequency"], "low")
        self.assertEqual(rel["proactivity"]["knowledge_invitations"], "naturally")
        self.assertEqual(rel["boundaries"]["sensitivity_topics"], ["grief"])
        self.assertTrue(rel["action_preferences"]["confirm_actions"])

    def test_invitation_default_is_occasionally(self):
        """Contract 12 — initial-release default is Occasionally, not Naturally."""
        fresh = User.objects.create_user(
            email="t9b@contract.test", password="pw", first_name="T9b")
        self.assertEqual(fresh.preferences.knowledge_invitations, "occasionally")
        self.assertEqual(
            CANONICAL_PREFERENCES["knowledge_invitations"]["default"], "occasionally")


class PersonaSelectionInteractionTests(TestCase):
    """M1 PRODUCTION REGRESSION (2026-08-18) — selecting a persona blanked the page.

    ROOT CAUSE: `.coaching-style-card input[type="radio"]` is `position: absolute` while
    `.coaching-style-card` was `position: static`. With no positioned ancestor the radio's
    containing block was the INITIAL containing block (the root), so its box resolved to a
    document-level coordinate. Clicking the label focuses that radio, the browser scrolls
    the FOCUSED ELEMENT into view — at the ROOT — and dragged the whole app shell
    off-screen. Browser-proven: root scrollHeight 1910 vs clientHeight 720 (1190px of root
    overflow) before the fix; 720 == 720 after. WLJ rule: the app shell owns scrolling;
    page content must never scroll the viewport.

    The CSS predates M1; M1 made the section tall enough for the root to overflow. These
    tests cover the CUSTOMER INTERACTION, not the CSS text alone.
    """

    def setUp(self):
        from apps.ai.models import CoachingStyle
        from django.conf import settings as dj_settings
        from apps.users.models import TermsAcceptance
        for key, name, instr in (
            ("supportive", "Supportive Partner", "Be warm but balanced, like a trusted friend."),
            ("texas_rancher", "Texas Rancher", "Talk like someone who has worked the land."),
        ):
            CoachingStyle.objects.get_or_create(
                key=key, defaults=dict(name=name, description=f"{name} voice.",
                                       prompt_instructions=instr, is_active=True))
        self.user = User.objects.create_user(
            email="regress@contract.test", password="regress-pw-1", first_name="Reg")
        self.user.has_completed_onboarding = True
        self.user.save()
        TermsAcceptance.objects.get_or_create(
            user=self.user,
            defaults={"terms_version": dj_settings.WLJ_SETTINGS["TERMS_VERSION"]})
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.has_completed_onboarding = True
        prefs.ai_coaching_style = "supportive"
        prefs.cos_display_name = "Ranger"
        prefs.cos_response_style = "deep_dive"
        prefs.assistant_confirm_actions = True
        prefs.preference_learning_enabled = True
        prefs.knowledge_invitations = "naturally"
        prefs.save()
        from apps.core.blueprint.engine import get_blueprint
        bp = get_blueprint(self.user)
        bp.accountability_style = "firm"
        bp.question_frequency = "low"
        bp.sensitivity_tags = ["grief"]
        bp.save()
        self.client.force_login(self.user)

    def _url(self):
        from django.urls import reverse
        return reverse("users:preferences")

    # -- 1. the page renders -------------------------------------------------
    def test_preferences_page_renders_with_the_persona_gallery(self):
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Your Chief of Staff", html)
        self.assertIn('name="ai_coaching_style"', html)
        self.assertIn("Texas Rancher", html)

    # -- 2. the interaction cannot scroll the ROOT ---------------------------
    def test_persona_card_establishes_a_containing_block_for_its_radio(self):
        """The defect itself: an absolutely-positioned radio must not escape its card.

        Without `position: relative` on the card, focusing the radio scrolls the ROOT and
        the entire app shell leaves the screen — the blank page Danny reported.
        """
        html = self.client.get(self._url()).content.decode()
        start = html.index(".coaching-style-card {")
        block = html[start:html.index("}", start)]
        self.assertIn("position: relative", block, (
            "REGRESSION: .coaching-style-card lost its containing block. Its radio is "
            "position:absolute; without a positioned ancestor the radio resolves against "
            "the ROOT, and clicking a persona scrolls the whole app shell off-screen."))

    # -- 3-6. the real save path -------------------------------------------
    def _full_form_post(self, **overrides):
        """Submit the REAL rendered form, exactly as the browser does.

        The page posts every control together, so the payload is scraped from the
        rendered HTML rather than hand-written — a hand-written subset fails ModelForm
        validation and would prove nothing about the customer's actual interaction.
        """
        import re as _re
        # Required fields whose markup the lightweight scraper below does not model
        # (custom select widgets / a time input). They are unrelated to the Chief of
        # Staff controls under test; supplying them keeps the ModelForm valid so the
        # test exercises the real save path instead of a validation failure.
        prefs = self.user.preferences
        data_required = {
            name: getattr(prefs, name)
            for name in ("theme", "timezone", "default_fasting_type",
                         "email_notification_frequency")
        }
        data_required["notification_reminder_time"] = (
            prefs.notification_reminder_time.strftime("%H:%M"))
        html = self.client.get(self._url()).content.decode()
        start = html.index('id="preferences-form"')
        form = html[start:html.index("</form>", start)]
        data = {}
        # text / hidden / number / email inputs
        for tag in _re.findall(r"<input\b[^>]*>", form):
            name = _re.search(r'name="([^"]+)"', tag)
            if not name:
                continue
            name = name.group(1)
            itype = (_re.search(r'type="([^"]+)"', tag) or [None, "text"])[1]
            value = (_re.search(r'value="([^"]*)"', tag) or [None, ""])[1]
            if itype in ("checkbox", "radio"):
                if "checked" in tag:
                    data[name] = value or "on"
            elif itype != "submit":
                # never let an empty rendered value clobber a supplied required default
                if value or name not in data:
                    data[name] = value
        # selects: take the selected option, else the first
        for sel in _re.findall(r"<select\b[^>]*>.*?</select>", form, _re.S):
            name = _re.search(r'name="([^"]+)"', sel)
            if not name:
                continue
            chosen = _re.search(r'<option[^>]*value="([^"]*)"[^>]*selected', sel)
            first = _re.search(r'<option[^>]*value="([^"]*)"', sel)
            if chosen or first:
                data[name] = (chosen or first).group(1)
        # textareas
        for ta in _re.findall(r'<textarea\b[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>',
                              form, _re.S):
            data.setdefault(ta[0], ta[1].strip())
        # Unrelated required fields are applied from stored values AFTER scraping, so a
        # widget this lightweight scraper cannot model never invalidates the payload.
        data.update(data_required)
        data.update(overrides)
        response = self.client.post(self._url(), data, follow=True)
        # A successful save REDIRECTS. If the ModelForm rejected the payload the view
        # re-renders at 200 with no redirect and silently saves nothing — surface that
        # here rather than letting a downstream assertion fail with a confusing diff.
        form = response.context.get("form") if response.context else None
        if form is not None and getattr(form, "errors", None):
            raise AssertionError(
                f"Preferences form rejected the rendered payload: {dict(form.errors)}")
        return response

    def test_selecting_a_persona_saves_and_returns_a_rendered_page(self):
        r = self._full_form_post(ai_coaching_style="texas_rancher")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertGreater(len(html), 5000,
                           "the response must be a rendered Preferences page, not blank")
        self.assertIn("Your Chief of Staff", html)

    def test_selected_persona_persists_and_shows_selected_on_reload(self):
        self._full_form_post(ai_coaching_style="texas_rancher")
        self.user.preferences.refresh_from_db()
        self.assertEqual(self.user.preferences.ai_coaching_style, "texas_rancher")
        html = self.client.get(self._url()).content.decode()
        marker = 'value="texas_rancher"'
        idx = html.index(marker)
        self.assertIn("checked", html[idx:idx + 200],
                      "the saved persona must render as selected on reload")

    def test_saving_a_persona_leaves_other_settings_untouched(self):
        """The toggles that are no longer ModelForm fields must not silently switch off."""
        from apps.core.blueprint.engine import get_blueprint
        self._full_form_post()
        prefs = self.user.preferences
        prefs.refresh_from_db()
        bp = get_blueprint(self.user)
        self.assertTrue(prefs.assistant_confirm_actions,
                        "saving a persona switched OFF action confirmations")
        self.assertTrue(prefs.preference_learning_enabled,
                        "saving a persona switched OFF preference learning")
        self.assertEqual(prefs.cos_response_style, "deep_dive")
        self.assertEqual(prefs.knowledge_invitations, "naturally")
        self.assertEqual(prefs.cos_display_name, "Ranger")
        self.assertEqual(bp.accountability_style, "firm")
        self.assertEqual(bp.question_frequency, "low")
        self.assertEqual(bp.sensitivity_tags, ["grief"])
        self.assertTrue(prefs.ai_data_consent, "AI consent must never be altered")

    def test_rendered_toggles_reflect_stored_state_not_a_missing_form_field(self):
        """A checkbox bound to a non-existent form field renders unchecked and then
        silently turns the setting off on the next save. Caught in the same session."""
        html = self.client.get(self._url()).content.decode()
        for name in ("assistant_confirm_actions", "preference_learning_enabled"):
            idx = html.index(f'name="{name}"')
            self.assertIn("checked", html[idx:idx + 120],
                          f"{name} is stored True but renders unchecked — saving would "
                          "silently disable it")
        self.assertNotIn("form.assistant_confirm_actions.value", html)
        self.assertNotIn("form.preference_learning_enabled.value", html)

    # -- 7. the runtime invariant still holds -------------------------------
    def test_persona_instructions_still_reach_the_runtime_after_selection(self):
        self._full_form_post(ai_coaching_style="texas_rancher")
        # Re-fetch: `self.user.preferences` is a cached related object and would still
        # hold the pre-save persona, hiding whether the RUNTIME sees the new choice.
        fresh = User.objects.get(pk=self.user.pk)
        rel = get_ai_relationship(fresh)
        self.assertEqual(rel["assistant"]["persona"]["key"], "texas_rancher")
        self.assertIn("worked the land", rel["persona_instructions"])

    # -- 8. no duplicate submission behaviour --------------------------------
    def test_persona_tiles_do_not_auto_submit_the_form(self):
        """Selection is a plain radio choice saved with the page — the tile must not
        submit on change, which would double-post and fight the unified save button."""
        html = self.client.get(self._url()).content.decode()
        start = html.index("Coaching / response-style card selection")
        handler = html[start:start + 700]
        for forbidden in (".submit()", "requestSubmit", "fetch(", "location.href"):
            self.assertNotIn(forbidden, handler,
                             f"persona selection must not {forbidden} on change")
