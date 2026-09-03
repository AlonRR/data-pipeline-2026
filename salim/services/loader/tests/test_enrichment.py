import unittest

from enrichment import BrandDictionary, is_junk_manufacturer, normalize_name, resolve_free


class NormalizeNameTest(unittest.TestCase):
    def test_collapses_whitespace_and_case(self):
        self.assertEqual(normalize_name("  חלב   תנובה  3%  "), "חלב תנובה 3%")
        self.assertEqual(normalize_name("Coca COLA Zero"), "coca cola zero")

    def test_strips_punctuation_but_keeps_hebrew_and_digits(self):
        self.assertEqual(normalize_name("קוטג' 5%, תנובה (250 גרם)"), "קוטג 5% תנובה 250 גרם")

    def test_none_and_blank_normalize_to_empty(self):
        self.assertEqual(normalize_name(None), "")
        self.assertEqual(normalize_name("   "), "")


class JunkManufacturerTest(unittest.TestCase):
    def test_placeholder_values_are_junk(self):
        for raw in (None, "", "לא ידוע", "לא ידוע ", "unknown", "N/A", "-", "0", "כללי"):
            self.assertTrue(is_junk_manufacturer(raw), raw)

    def test_real_names_are_kept(self):
        self.assertFalse(is_junk_manufacturer("תנובה"))
        self.assertFalse(is_junk_manufacturer("Strauss"))


class BrandDictionaryTest(unittest.TestCase):
    def setUp(self):
        self.brands = BrandDictionary({"תנובה": "תנובה", "שטראוס": "שטראוס", "עלית": "עלית", "coca cola": "Coca-Cola"})

    def test_single_brand_in_name_matches(self):
        self.assertEqual(self.brands.match("חלב תנובה 3% 1 ליטר"), "תנובה")

    def test_multiword_brand_and_case_insensitive(self):
        self.assertEqual(self.brands.match("Coca Cola Zero 1.5L"), "Coca-Cola")

    def test_two_brands_is_ambiguous(self):
        self.assertIsNone(self.brands.match("קוטג' תנובה בטעם שוקולד עלית"))

    def test_partial_token_does_not_match(self):
        # "עליתה" contains "עלית" as a substring but is not the brand token.
        self.assertIsNone(self.brands.match("עליתה לחם"))

    def test_no_brand_is_none(self):
        self.assertIsNone(self.brands.match("מלפפון חמוץ"))


class ResolveFreeTest(unittest.TestCase):
    """raw -> cache -> dictionary, in that order; None means 'ask the LLM later'."""

    def setUp(self):
        self.brands = BrandDictionary({"תנובה": "תנובה"})
        self.cache = {normalize_name("קולה זירו 1.5"): "Coca-Cola"}

    def test_raw_wins_when_present(self):
        result = resolve_free("חלב תנובה", "שטראוס", self.cache, self.brands)
        self.assertEqual(result, ("שטראוס", "raw"))

    def test_junk_raw_falls_through_to_cache(self):
        result = resolve_free("קולה  זירו 1.5", "לא ידוע", self.cache, self.brands)
        self.assertEqual(result, ("Coca-Cola", "cache"))

    def test_dictionary_after_cache_miss(self):
        result = resolve_free("חלב תנובה 3%", None, self.cache, self.brands)
        self.assertEqual(result, ("תנובה", "dictionary"))

    def test_known_unknown_in_cache_short_circuits(self):
        cache = {normalize_name("מלפפון חמוץ"): None}
        self.assertEqual(resolve_free("מלפפון חמוץ", None, cache, self.brands), (None, "cache"))

    def test_nothing_matches(self):
        self.assertIsNone(resolve_free("מלפפון", None, self.cache, self.brands))


if __name__ == "__main__":
    unittest.main()
