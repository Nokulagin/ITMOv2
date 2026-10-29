"""Field rules without database and HTTP (spec tests 3-10, 16-17)."""

import unittest

from server import validation


class TitleRuleTests(unittest.TestCase):
    def test_valid_title_is_kept(self):
        self.assertEqual(validation.normalize_title("Купить молоко"), "Купить молоко")

    def test_outer_whitespace_and_newlines_are_stripped(self):
        self.assertEqual(validation.normalize_title("  Купить молоко \n"), "Купить молоко")

    def test_inner_spaces_are_kept(self):
        self.assertEqual(validation.normalize_title("Купить  два молока"), "Купить  два молока")

    def test_one_character_title_is_accepted(self):
        self.assertEqual(validation.normalize_title("A"), "A")

    def test_200_characters_are_accepted(self):
        self.assertEqual(len(validation.normalize_title("a" * 200)), 200)

    def test_201_characters_are_rejected(self):
        with self.assertRaises(validation.ValidationError) as ctx:
            validation.normalize_title("a" * 201)
        self.assertEqual(ctx.exception.message, validation.ERROR_TITLE_TOO_LONG)

    def test_200_cyrillic_letters_are_accepted_and_201_rejected(self):
        self.assertEqual(len(validation.normalize_title("я" * 200)), 200)
        with self.assertRaises(validation.ValidationError):
            validation.normalize_title("я" * 201)

    def test_length_is_counted_in_code_points_not_bytes(self):
        # One emoji is one code point but four UTF-8 bytes.
        self.assertEqual(len(validation.normalize_title("😀" * 200)), 200)
        with self.assertRaises(validation.ValidationError):
            validation.normalize_title("😀" * 201)

    def test_empty_and_spaces_only_are_rejected(self):
        for value in ("", "   ", " \n\t "):
            with self.subTest(value=value):
                with self.assertRaises(validation.ValidationError) as ctx:
                    validation.normalize_title(value)
                self.assertEqual(ctx.exception.message, validation.ERROR_TITLE_EMPTY)

    def test_non_string_is_rejected(self):
        for value in (1, None, [], {}, True):
            with self.subTest(value=value):
                with self.assertRaises(validation.ValidationError) as ctx:
                    validation.normalize_title(value)
                self.assertEqual(ctx.exception.message, validation.ERROR_TITLE_NOT_STRING)


class DoneRuleTests(unittest.TestCase):
    def test_booleans_are_accepted(self):
        self.assertIs(validation.validate_done(True), True)
        self.assertIs(validation.validate_done(False), False)

    def test_string_true_is_rejected(self):
        with self.assertRaises(validation.ValidationError) as ctx:
            validation.validate_done("true")
        self.assertEqual(ctx.exception.message, validation.ERROR_DONE_NOT_BOOL)

    def test_number_one_is_rejected(self):
        with self.assertRaises(validation.ValidationError):
            validation.validate_done(1)

    def test_missing_value_is_rejected(self):
        with self.assertRaises(validation.ValidationError):
            validation.validate_done(None)


if __name__ == "__main__":
    unittest.main()
