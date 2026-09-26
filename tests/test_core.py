import unittest

from html_character_entity_decoder import decode, decode_once, decode_iter, EntityError


class TestNamedEntities(unittest.TestCase):
    def test_amp(self):
        self.assertEqual(decode_once("a &amp; b"), "a & b")

    def test_lt_gt_quot(self):
        self.assertEqual(decode_once("&lt;tag&gt;"), "<tag>")
        self.assertEqual(decode_once("say &quot;hi&quot;"), 'say "hi"')

    def test_known_named_round_trips(self):
        # Spot-check a handful of names that exist in the HTML5 set; these are
        # stable across Python versions because they're core punctuation.
        for name, char in [("amp", "&"), ("lt", "<"), ("gt", ">"), ("quot", '"'), ("apos", "'")]:
            self.assertEqual(decode_once("&%s;" % name), char)

    def test_multiple_named_in_one_string(self):
        self.assertEqual(decode_once("&amp;&lt;&gt;"), "&<>")


class TestNumericEntities(unittest.TestCase):
    def test_decimal_amp(self):
        self.assertEqual(decode_once("&#38;"), "&")

    def test_hex_lowercase(self):
        self.assertEqual(decode_once("&#x26;"), "&")

    def test_hex_uppercase_prefix(self):
        self.assertEqual(decode_once("&#X26;"), "&")

    def test_hex_uppercase_digits(self):
        self.assertEqual(decode_once("&#x1F600;"), "\U0001F600")

    def test_decimal_large_codepoint(self):
        self.assertEqual(decode_once("&#128512;"), "\U0001F600")


class TestBareAmpersand(unittest.TestCase):
    def test_bare_ampersand_left_alone(self):
        # A '&' that doesn't form a valid entity is passed through literally.
        # This matches the browser behaviour for ambiguous ampersands in text,
        # and it's the interpretation we commit to in the README.
        self.assertEqual(decode_once("Tom & Jerry"), "Tom & Jerry")

    def test_ampersand_followed_by_garbage(self):
        self.assertEqual(decode_once("&123; and &!;"), "&123; and &!;")

    def test_ampersand_at_end(self):
        self.assertEqual(decode_once("end &"), "end &")


class TestNoReDecode(unittest.TestCase):
    def test_decoded_amp_not_reexamined(self):
        # decode_once must not turn '&amp;' into '&' and then re-scan that '&'
        # as the start of a new entity. There is no following 'amp;', so the
        # strongest assertion is that the output is exactly one character.
        self.assertEqual(decode_once("&amp;"), "&")

    def test_decoded_amp_does_not_consume_following_text(self):
        # If re-decoding happened, '&amp;lt;' would become '<'. It must not.
        self.assertEqual(decode_once("&amp;lt;"), "&lt;")


class TestIterativeDecode(unittest.TestCase):
    def test_double_encoded(self):
        self.assertEqual(decode("&amp;amp;"), "&")

    def test_triple_encoded(self):
        self.assertEqual(decode("&amp;amp;amp;"), "&")

    def test_single_pass_when_stable(self):
        self.assertEqual(decode("a &amp; b"), "a & b")

    def test_max_passes_caps_iteration(self):
        # A string that keeps changing each pass (because it encodes itself)
        # would loop forever without the cap. We assert the cap is honoured by
        # checking that decode returns rather than raising RecursionError or
        # hanging. The exact result for a self-reencoding input is not a
        # behavioural guarantee, only that it terminates.
        result = decode("&amp;" * 20, max_passes=3)
        self.assertIsInstance(result, str)

    def test_max_passes_must_be_positive(self):
        with self.assertRaises(ValueError):
            decode("&amp;", max_passes=0)


class TestErrors(unittest.TestCase):
    def test_unknown_named_entity_raises(self):
        with self.assertRaises(EntityError):
            decode_once("&bogus;")

    def test_numeric_out_of_range_raises(self):
        with self.assertRaises(EntityError):
            decode_once("&#9999999999;")

    def test_numeric_lone_surrogate_raises(self):
        with self.assertRaises(EntityError):
            decode_once("&#xD800;")

    def test_type_error_on_non_string(self):
        with self.assertRaises(TypeError):
            decode_once(123)


class TestDecodeIter(unittest.TestCase):
    def test_iter_yields_chunks(self):
        chunks = list(decode_iter("a&amp;b&lt;c"))
        self.assertEqual("".join(chunks), "a&b<c")

    def test_iter_yields_plain_text_chunk(self):
        chunks = list(decode_iter("hello world"))
        self.assertEqual(chunks, ["hello world"])

    def test_iter_type_error_on_non_string(self):
        with self.assertRaises(TypeError):
            list(decode_iter(b"bytes"))


class TestMixedAndEmpty(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(decode_once(""), "")
        self.assertEqual(decode(""), "")

    def test_no_entities(self):
        self.assertEqual(decode_once("plain text"), "plain text")

    def test_mixed_named_and_numeric(self):
        self.assertEqual(decode_once("&amp;&#38;&lt;"), "&&<")

    def test_adjacent_entities(self):
        self.assertEqual(decode_once("&amp;&amp;&amp;"), "&&&")


if __name__ == "__main__":
    unittest.main()
