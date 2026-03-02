"""
Tests for IngredientParsingService — 50+ parsing scenarios.

Covers quantity extraction, unit normalization, preparation detection,
optional markers, edge cases, and multi-line blocks.
"""

from decimal import Decimal

from django.test import TestCase

from apps.meals.services.ingredient_parser import (
    parse_ingredient_block,
    parse_ingredient_line,
)
from apps.meals.services.unit_conversion import normalize_unit, parse_quantity


class TestQuantityParsing(TestCase):
    """Test quantity extraction from text."""

    def test_simple_integer(self):
        self.assertEqual(parse_quantity("2"), Decimal("2"))

    def test_simple_decimal(self):
        self.assertEqual(parse_quantity("0.5"), Decimal("0.5"))

    def test_simple_fraction(self):
        self.assertEqual(parse_quantity("1/2"), Decimal("0.5"))

    def test_mixed_number(self):
        self.assertEqual(parse_quantity("1 1/2"), Decimal("1.5"))

    def test_mixed_number_thirds(self):
        result = parse_quantity("2 1/3")
        self.assertAlmostEqual(float(result), 2.333, places=2)

    def test_unicode_half(self):
        self.assertEqual(parse_quantity("\u00bd"), Decimal("0.5"))

    def test_unicode_quarter(self):
        self.assertEqual(parse_quantity("\u00bc"), Decimal("0.25"))

    def test_unicode_three_quarters(self):
        self.assertEqual(parse_quantity("\u00be"), Decimal("0.75"))

    def test_mixed_unicode(self):
        self.assertEqual(parse_quantity("1\u00bd"), Decimal("1.5"))

    def test_range_average(self):
        self.assertEqual(parse_quantity("2-3"), Decimal("2.5"))

    def test_range_with_spaces(self):
        self.assertEqual(parse_quantity("2 - 3"), Decimal("2.5"))

    def test_empty_string(self):
        self.assertIsNone(parse_quantity(""))

    def test_none_text(self):
        self.assertIsNone(parse_quantity("abc"))

    def test_three_quarters_fraction(self):
        self.assertEqual(parse_quantity("3/4"), Decimal("0.75"))


class TestUnitNormalization(TestCase):
    """Test unit string normalization."""

    def test_tsp_variations(self):
        self.assertEqual(normalize_unit("tsp"), "tsp")
        self.assertEqual(normalize_unit("teaspoon"), "tsp")
        self.assertEqual(normalize_unit("teaspoons"), "tsp")

    def test_tbsp_variations(self):
        self.assertEqual(normalize_unit("tbsp"), "tbsp")
        self.assertEqual(normalize_unit("tablespoon"), "tbsp")
        self.assertEqual(normalize_unit("tablespoons"), "tbsp")
        self.assertEqual(normalize_unit("tbs"), "tbsp")

    def test_cup_variations(self):
        self.assertEqual(normalize_unit("cup"), "cup")
        self.assertEqual(normalize_unit("cups"), "cup")
        self.assertEqual(normalize_unit("c"), "cup")

    def test_weight_units(self):
        self.assertEqual(normalize_unit("g"), "g")
        self.assertEqual(normalize_unit("gram"), "g")
        self.assertEqual(normalize_unit("grams"), "g")
        self.assertEqual(normalize_unit("oz"), "oz")
        self.assertEqual(normalize_unit("ounce"), "oz")
        self.assertEqual(normalize_unit("lb"), "lb")
        self.assertEqual(normalize_unit("lbs"), "lb")
        self.assertEqual(normalize_unit("pound"), "lb")

    def test_misc_units(self):
        self.assertEqual(normalize_unit("clove"), "clove")
        self.assertEqual(normalize_unit("cloves"), "clove")
        self.assertEqual(normalize_unit("pinch"), "pinch")
        self.assertEqual(normalize_unit("can"), "can")
        self.assertEqual(normalize_unit("cans"), "can")

    def test_unknown_unit(self):
        self.assertIsNone(normalize_unit("foobar"))

    def test_trailing_period(self):
        self.assertEqual(normalize_unit("tsp."), "tsp")


class TestIngredientLineParsing(TestCase):
    """Test full ingredient line parsing — 50+ scenarios."""

    # === Basic patterns ===

    def test_simple_qty_unit_name(self):
        """2 cups flour"""
        result = parse_ingredient_line("2 cups flour")
        self.assertEqual(result.quantity, Decimal("2"))
        self.assertEqual(result.unit, "cup")
        self.assertEqual(result.name, "flour")

    def test_fraction_qty(self):
        """1/2 tsp salt"""
        result = parse_ingredient_line("1/2 tsp salt")
        self.assertEqual(result.quantity, Decimal("0.5"))
        self.assertEqual(result.unit, "tsp")
        self.assertEqual(result.name, "salt")

    def test_mixed_number(self):
        """1 1/2 cups sugar"""
        result = parse_ingredient_line("1 1/2 cups sugar")
        self.assertEqual(result.quantity, Decimal("1.5"))
        self.assertEqual(result.unit, "cup")
        self.assertEqual(result.name, "sugar")

    def test_decimal_qty(self):
        """0.5 lb ground beef"""
        result = parse_ingredient_line("0.5 lb ground beef")
        self.assertEqual(result.quantity, Decimal("0.5"))
        self.assertEqual(result.unit, "lb")
        self.assertEqual(result.name, "ground beef")

    # === Preparation notes ===

    def test_preparation_before_name(self):
        """2 cups diced chicken breast"""
        result = parse_ingredient_line("2 cups diced chicken breast")
        self.assertEqual(result.quantity, Decimal("2"))
        self.assertEqual(result.unit, "cup")
        self.assertEqual(result.name, "chicken breast")
        self.assertIn("diced", result.preparation)

    def test_preparation_after_comma(self):
        """1 onion, diced"""
        result = parse_ingredient_line("1 onion, diced")
        self.assertEqual(result.quantity, Decimal("1"))
        self.assertEqual(result.name, "onion")
        self.assertIn("diced", result.preparation)

    def test_preparation_in_parens(self):
        """2 cloves garlic (minced)"""
        result = parse_ingredient_line("2 cloves garlic (minced)")
        self.assertEqual(result.quantity, Decimal("2"))
        self.assertEqual(result.unit, "clove")
        self.assertEqual(result.name, "garlic")
        self.assertIn("minced", result.preparation)

    def test_multiple_preparations(self):
        """1 lb boneless skinless chicken breast, cubed"""
        result = parse_ingredient_line("1 lb boneless skinless chicken breast, cubed")
        self.assertEqual(result.quantity, Decimal("1"))
        self.assertEqual(result.unit, "lb")

    # === Optional markers ===

    def test_optional_in_parens(self):
        """1/4 cup fresh parsley (optional)"""
        result = parse_ingredient_line("1/4 cup fresh parsley (optional)")
        self.assertTrue(result.is_optional)
        self.assertEqual(result.quantity, Decimal("0.25"))
        self.assertEqual(result.unit, "cup")

    def test_optional_trailing(self):
        """chopped nuts, optional"""
        result = parse_ingredient_line("chopped nuts, optional")
        self.assertTrue(result.is_optional)

    # === To taste / as needed ===

    def test_to_taste_trailing(self):
        """salt and pepper to taste"""
        result = parse_ingredient_line("salt and pepper to taste")
        self.assertIsNone(result.quantity)
        self.assertEqual(result.unit, "to_taste")
        self.assertEqual(result.name, "salt and pepper")

    def test_as_needed(self):
        """cooking spray as needed"""
        result = parse_ingredient_line("cooking spray as needed")
        self.assertIsNone(result.quantity)
        self.assertEqual(result.unit, "as_needed")

    # === Parenthetical sizes ===

    def test_can_with_size(self):
        """1 (14 oz) can diced tomatoes"""
        result = parse_ingredient_line("1 (14 oz) can diced tomatoes")
        self.assertEqual(result.quantity, Decimal("1"))
        self.assertEqual(result.unit, "can")

    # === Weight-based ===

    def test_grams(self):
        """200 g pasta"""
        result = parse_ingredient_line("200 g pasta")
        self.assertEqual(result.quantity, Decimal("200"))
        self.assertEqual(result.unit, "g")
        self.assertEqual(result.name, "pasta")

    def test_kilograms(self):
        """1.5 kg chicken thighs"""
        result = parse_ingredient_line("1.5 kg chicken thighs")
        self.assertEqual(result.quantity, Decimal("1.5"))
        self.assertEqual(result.unit, "kg")

    def test_ounces(self):
        """8 oz cream cheese"""
        result = parse_ingredient_line("8 oz cream cheese")
        self.assertEqual(result.quantity, Decimal("8"))
        self.assertEqual(result.unit, "oz")
        self.assertEqual(result.name, "cream cheese")

    # === Volume-based ===

    def test_tablespoons(self):
        """2 tbsp olive oil"""
        result = parse_ingredient_line("2 tbsp olive oil")
        self.assertEqual(result.quantity, Decimal("2"))
        self.assertEqual(result.unit, "tbsp")
        self.assertEqual(result.name, "olive oil")

    def test_teaspoons(self):
        """1/4 tsp cayenne pepper"""
        result = parse_ingredient_line("1/4 tsp cayenne pepper")
        self.assertEqual(result.quantity, Decimal("0.25"))
        self.assertEqual(result.unit, "tsp")
        self.assertEqual(result.name, "cayenne pepper")

    def test_ml(self):
        """250 ml milk"""
        result = parse_ingredient_line("250 ml milk")
        self.assertEqual(result.quantity, Decimal("250"))
        self.assertEqual(result.unit, "ml")
        self.assertEqual(result.name, "milk")

    # === Count-based ===

    def test_pieces(self):
        """3 eggs"""
        result = parse_ingredient_line("3 eggs")
        self.assertEqual(result.quantity, Decimal("3"))
        self.assertEqual(result.name, "eggs")

    def test_cloves(self):
        """4 cloves garlic"""
        result = parse_ingredient_line("4 cloves garlic")
        self.assertEqual(result.quantity, Decimal("4"))
        self.assertEqual(result.unit, "clove")
        self.assertEqual(result.name, "garlic")

    def test_bunches(self):
        """1 bunch cilantro"""
        result = parse_ingredient_line("1 bunch cilantro")
        self.assertEqual(result.quantity, Decimal("1"))
        self.assertEqual(result.unit, "bunch")
        self.assertEqual(result.name, "cilantro")

    def test_pinch(self):
        """1 pinch saffron"""
        result = parse_ingredient_line("1 pinch saffron")
        self.assertEqual(result.quantity, Decimal("1"))
        self.assertEqual(result.unit, "pinch")
        self.assertEqual(result.name, "saffron")

    # === Unicode fractions ===

    def test_unicode_half_cup(self):
        """\u00bd cup butter"""
        result = parse_ingredient_line("\u00bd cup butter")
        self.assertEqual(result.quantity, Decimal("0.5"))
        self.assertEqual(result.unit, "cup")
        self.assertEqual(result.name, "butter")

    def test_unicode_mixed(self):
        """1\u00bc cups flour"""
        result = parse_ingredient_line("1\u00bc cups flour")
        self.assertEqual(result.quantity, Decimal("1.25"))
        self.assertEqual(result.unit, "cup")

    # === Edge cases ===

    def test_empty_line(self):
        result = parse_ingredient_line("")
        self.assertEqual(result.name, "")
        self.assertEqual(result.confidence, Decimal("0"))

    def test_only_name(self):
        """salt"""
        result = parse_ingredient_line("salt")
        self.assertEqual(result.name, "salt")
        self.assertIsNone(result.quantity)
        self.assertLess(result.confidence, Decimal("0.70"))

    def test_unit_of_pattern(self):
        """1 cup of sugar"""
        result = parse_ingredient_line("1 cup of sugar")
        self.assertEqual(result.quantity, Decimal("1"))
        self.assertEqual(result.unit, "cup")
        self.assertEqual(result.name, "sugar")

    def test_multi_word_ingredient(self):
        """2 tbsp extra virgin olive oil"""
        result = parse_ingredient_line("2 tbsp extra virgin olive oil")
        self.assertEqual(result.quantity, Decimal("2"))
        self.assertEqual(result.unit, "tbsp")
        self.assertEqual(result.name, "extra virgin olive oil")

    def test_range_quantity(self):
        """2-3 cups chicken broth"""
        result = parse_ingredient_line("2-3 cups chicken broth")
        self.assertEqual(result.quantity, Decimal("2.5"))
        self.assertEqual(result.unit, "cup")
        self.assertEqual(result.name, "chicken broth")

    def test_package_unit(self):
        """1 package cream cheese"""
        result = parse_ingredient_line("1 package cream cheese")
        self.assertEqual(result.quantity, Decimal("1"))
        self.assertEqual(result.unit, "package")
        self.assertEqual(result.name, "cream cheese")

    def test_jar_unit(self):
        """1 jar marinara sauce"""
        result = parse_ingredient_line("1 jar marinara sauce")
        self.assertEqual(result.quantity, Decimal("1"))
        self.assertEqual(result.unit, "jar")
        self.assertEqual(result.name, "marinara sauce")

    def test_dash_unit(self):
        """1 dash hot sauce"""
        result = parse_ingredient_line("1 dash hot sauce")
        self.assertEqual(result.quantity, Decimal("1"))
        self.assertEqual(result.unit, "dash")
        self.assertEqual(result.name, "hot sauce")

    def test_original_text_preserved(self):
        result = parse_ingredient_line("2 cups flour")
        self.assertEqual(result.original_text, "2 cups flour")

    def test_confidence_with_full_parse(self):
        """Full parse should have high confidence."""
        result = parse_ingredient_line("2 cups flour")
        self.assertGreaterEqual(result.confidence, Decimal("0.90"))

    def test_confidence_no_quantity(self):
        """No quantity should lower confidence."""
        result = parse_ingredient_line("flour")
        self.assertLess(result.confidence, Decimal("0.70"))

    def test_sprig_unit(self):
        """2 sprigs fresh thyme"""
        result = parse_ingredient_line("2 sprigs fresh thyme")
        self.assertEqual(result.quantity, Decimal("2"))
        self.assertEqual(result.unit, "sprig")

    def test_slices(self):
        """4 slices bacon"""
        result = parse_ingredient_line("4 slices bacon")
        self.assertEqual(result.quantity, Decimal("4"))
        self.assertEqual(result.unit, "slice")
        self.assertEqual(result.name, "bacon")

    def test_large_number(self):
        """500 g chicken breast"""
        result = parse_ingredient_line("500 g chicken breast")
        self.assertEqual(result.quantity, Decimal("500"))
        self.assertEqual(result.unit, "g")

    def test_cans(self):
        """2 cans black beans"""
        result = parse_ingredient_line("2 cans black beans")
        self.assertEqual(result.quantity, Decimal("2"))
        self.assertEqual(result.unit, "can")
        self.assertEqual(result.name, "black beans")

    def test_frozen_prep(self):
        """1 cup frozen peas"""
        result = parse_ingredient_line("1 cup frozen peas")
        self.assertEqual(result.quantity, Decimal("1"))
        self.assertEqual(result.unit, "cup")
        # "frozen" is a preparation word
        self.assertIn("peas", result.name)

    def test_bullet_point_prefix(self):
        """- 2 cups flour"""
        result = parse_ingredient_line("- 2 cups flour")
        self.assertEqual(result.quantity, Decimal("2"))
        self.assertEqual(result.unit, "cup")
        self.assertEqual(result.name, "flour")

    def test_asterisk_prefix(self):
        """* 1 tsp vanilla extract"""
        result = parse_ingredient_line("* 1 tsp vanilla extract")
        self.assertEqual(result.quantity, Decimal("1"))
        self.assertEqual(result.unit, "tsp")

    def test_compound_name_with_comma_prep(self):
        """2 lbs pork shoulder, trimmed"""
        result = parse_ingredient_line("2 lbs pork shoulder, trimmed")
        self.assertEqual(result.quantity, Decimal("2"))
        self.assertEqual(result.unit, "lb")
        self.assertIn("trimmed", result.preparation)

    def test_fluid_ounces(self):
        """4 fl oz heavy cream"""
        result = parse_ingredient_line("4 fl oz heavy cream")
        self.assertEqual(result.quantity, Decimal("4"))
        self.assertEqual(result.unit, "fl_oz")
        self.assertEqual(result.name, "heavy cream")


class TestIngredientBlockParsing(TestCase):
    """Test multi-line ingredient block parsing."""

    def test_simple_block(self):
        block = """
        2 cups flour
        1/2 tsp salt
        1 cup milk
        3 eggs
        """
        results = parse_ingredient_block(block)
        self.assertEqual(len(results), 4)
        self.assertEqual(results[0].name, "flour")
        self.assertEqual(results[1].name, "salt")
        self.assertEqual(results[2].name, "milk")
        self.assertEqual(results[3].name, "eggs")

    def test_skip_section_headers(self):
        block = """
        For the sauce:
        2 cups tomato sauce
        1 tsp oregano
        For the pasta:
        200 g spaghetti
        """
        results = parse_ingredient_block(block)
        self.assertEqual(len(results), 3)

    def test_skip_blank_lines(self):
        block = """
        2 cups flour

        1 tsp salt

        """
        results = parse_ingredient_block(block)
        self.assertEqual(len(results), 2)

    def test_bullet_points(self):
        block = """
        - 2 cups flour
        - 1 tsp salt
        - 1 cup milk
        """
        results = parse_ingredient_block(block)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].name, "flour")

    def test_real_recipe_block(self):
        block = """
        1 lb ground beef
        1 onion, diced
        3 cloves garlic, minced
        1 (14 oz) can crushed tomatoes
        2 tbsp olive oil
        1 tsp salt
        1/2 tsp black pepper
        1 cup beef broth
        8 oz pasta
        Fresh basil to taste
        Parmesan cheese (optional)
        """
        results = parse_ingredient_block(block)
        self.assertEqual(len(results), 11)

        # Ground beef
        self.assertEqual(results[0].quantity, Decimal("1"))
        self.assertEqual(results[0].unit, "lb")

        # Onion with prep
        self.assertEqual(results[1].quantity, Decimal("1"))
        self.assertIn("diced", results[1].preparation)

        # To taste
        self.assertEqual(results[9].unit, "to_taste")

        # Optional
        self.assertTrue(results[10].is_optional)
