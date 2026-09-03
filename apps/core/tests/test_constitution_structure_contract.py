# ==============================================================================
# File: apps/core/tests/test_constitution_structure_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The invariant/guidance split cannot lose, add, or reword policy
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-03
# ==============================================================================
"""Stage 1 separated the constitution into law and coaching. This proves it separated
NOTHING ELSE.

The danger in classifying 69k characters of governing prose is silent loss: a paragraph
that stops being represented, a rule quietly demoted from invariant to guidance, or a new
rule added with no classification at all. Each of those is invisible in review and fatal in
production, so each is a test here.

The load-bearing assertion is byte-exact reconstruction. If every classified block, joined
in order, is character-for-character the constitution the model actually receives, then no
policy can have been dropped or reworded — whatever else the classification says about it.

No provider calls.
"""

from django.test import SimpleTestCase

from apps.ai.model_interface import constitution_map as cmap
from apps.ai.model_interface.constitution import CONSTITUTION


class CompletenessTests(SimpleTestCase):
    """Every rule that was in the constitution is still in the constitution."""

    def test_the_classification_reconstructs_the_constitution_exactly(self):
        self.assertEqual(cmap.reconstruct(), CONSTITUTION,
                         "the split changed the text the model receives")

    def test_every_block_is_classified(self):
        self.assertEqual(cmap.UNCLASSIFIED, [],
                         "constitution policy exists that nothing has classified — a rule "
                         "was added without deciding whether it is law or coaching")

    def test_no_classification_entry_is_orphaned(self):
        """A stale entry means a rule was DELETED from the constitution."""
        live = {b.anchor for b in cmap.BLOCKS}
        orphans = sorted(set(cmap._CLASSIFICATION) - live)
        self.assertEqual(orphans, [],
                         f"classification entries with no matching policy: {orphans}")

    def test_every_character_is_accounted_for(self):
        counted = (sum(b.chars for b in cmap.BLOCKS)
                   + len(cmap.SEPARATOR) * (len(cmap.BLOCKS) - 1))
        self.assertEqual(counted, len(CONSTITUTION))

    def test_anchors_are_unique(self):
        anchors = [b.anchor for b in cmap.BLOCKS]
        self.assertEqual(len(anchors), len(set(anchors)),
                         "two blocks share an anchor — classification would be ambiguous")

    def test_the_split_is_not_empty_on_either_side(self):
        self.assertTrue(cmap.invariants())
        self.assertTrue(cmap.guidance())


class ClassificationDisciplineTests(SimpleTestCase):
    """An invariant must name what it protects; guidance must not pretend to."""

    def test_every_invariant_protects_a_named_boundary(self):
        for block in cmap.invariants():
            self.assertIn(block.protects, cmap.PROTECTS,
                          f"invariant {block.heading!r} protects {block.protects!r}, which "
                          f"is not a WLJ boundary — then it is guidance, not law")

    def test_guidance_never_claims_to_protect_a_boundary(self):
        for block in cmap.guidance():
            self.assertIsNone(block.protects,
                              f"{block.heading!r} is classified as guidance but claims a "
                              f"protected boundary")

    def test_the_boundaries_that_must_be_defended_have_an_invariant(self):
        """The safety categories this runtime cannot operate without."""
        covered = {b.protects for b in cmap.invariants()}
        for required in ("canonical_truth", "grounding", "confirmation",
                         "exact_target_integrity", "write_postcondition_integrity",
                         "privacy_sensitivity", "personal_knowledge_authority"):
            self.assertIn(required, covered,
                          f"no constitution invariant defends {required}")

    def test_kinds_are_exhaustive(self):
        for block in cmap.BLOCKS:
            self.assertIn(block.kind, (cmap.INVARIANT, cmap.GUIDANCE))


class HistoricalPatchTests(SimpleTestCase):
    """A patch is a Stage-2 candidate only when something else already holds the job."""

    def test_only_guidance_may_be_a_historical_patch(self):
        for block in cmap.BLOCKS:
            if block.patch_of:
                self.assertEqual(block.kind, cmap.GUIDANCE,
                                 f"{block.heading!r} is an invariant marked as a removable "
                                 f"patch — safety boundaries do not retire")

    def test_every_patch_names_the_mechanism_that_replaced_it(self):
        for block in cmap.historical_patches():
            self.assertTrue(block.replacement,
                            f"{block.heading!r} is marked as a historical patch but names "
                            f"no replacement responsibility — it cannot be a candidate for "
                            f"removal on the basis of length alone")

    def test_patches_were_actually_identified(self):
        self.assertGreaterEqual(len(cmap.historical_patches()), 1)


class NoBehaviourChangeTests(SimpleTestCase):
    """Stage 1 classifies. It does not reorder, rewrite, or shorten."""

    def test_the_constitution_is_still_delivered_whole_and_first(self):
        from apps.ai.model_interface.constitution import CONSTITUTION as live
        self.assertTrue(live.startswith(cmap.BLOCKS[0].text))
        self.assertTrue(live.endswith(cmap.BLOCKS[-1].text))

    def test_block_order_is_the_constitution_order(self):
        self.assertEqual([b.index for b in cmap.BLOCKS],
                         sorted(b.index for b in cmap.BLOCKS))

    def test_composition_reports_only_numbers_and_category_names(self):
        comp = cmap.composition()
        for key, value in comp.items():
            if key == "protects_covered":
                self.assertTrue(set(value) <= set(cmap.PROTECTS))
            else:
                self.assertIsInstance(value, (int, float),
                                      f"composition key {key} leaked non-numeric content")
