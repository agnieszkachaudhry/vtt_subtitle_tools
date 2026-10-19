import unittest

from vtt_subtitle_tools import Cue, parse, serialize
from vtt_subtitle_tools.core import RawBlock, format_timestamp, parse_timestamp


class TestTimestamps(unittest.TestCase):
    def test_parse_short_form(self):
        self.assertEqual(parse_timestamp("00:30.000"), 30000)

    def test_parse_long_form(self):
        self.assertEqual(parse_timestamp("01:00:30.000"), 3630000)

    def test_parse_strips_whitespace(self):
        self.assertEqual(parse_timestamp("  00:30.000  "), 30000)

    def test_parse_rejects_two_digit_hours_required_padding(self):
        with self.assertRaises(ValueError):
            parse_timestamp("1:00:30.000")

    def test_parse_rejects_two_digit_ms(self):
        with self.assertRaises(ValueError):
            parse_timestamp("00:30.00")

    def test_parse_rejects_comma_decimal(self):
        with self.assertRaises(ValueError):
            parse_timestamp("00:30,000")

    def test_parse_rejects_non_string(self):
        with self.assertRaises(ValueError):
            parse_timestamp(30000)

    def test_format_zero(self):
        self.assertEqual(format_timestamp(0), "00:00:00.000")

    def test_format_round(self):
        self.assertEqual(format_timestamp(3661500), "01:01:01.500")

    def test_format_rejects_negative(self):
        with self.assertRaises(ValueError):
            format_timestamp(-1)

    def test_format_rejects_non_int(self):
        with self.assertRaises(ValueError):
            format_timestamp("30000")


class TestParse(unittest.TestCase):
    def test_header_required(self):
        with self.assertRaises(ValueError):
            parse("NOTE\nhello")

    def test_empty_after_header(self):
        self.assertEqual(parse("WEBVTT\n"), [])

    def test_basic_cue(self):
        vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello"
        items = parse(vtt)
        self.assertEqual(len(items), 1)
        cue = items[0]
        self.assertIsInstance(cue, Cue)
        self.assertEqual(cue.start, 1000)
        self.assertEqual(cue.end, 2000)
        self.assertEqual(cue.payload, "Hello")
        self.assertIsNone(cue.identifier)

    def test_cue_with_identifier(self):
        vtt = "WEBVTT\n\nintro\n00:00:01.000 --> 00:00:02.000\nHi"
        items = parse(vtt)
        self.assertEqual(items[0].identifier, "intro")

    def test_cue_multiline_payload(self):
        vtt = (
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n"
            "Line one\nLine two"
        )
        items = parse(vtt)
        self.assertEqual(items[0].payload, "Line one\nLine two")

    def test_style_block_preserved(self):
        vtt = (
            "WEBVTT\n\n"
            "STYLE\n::cue { color: red; }\n\n"
            "00:00:01.000 --> 00:00:02.000\nHi"
        )
        items = parse(vtt)
        self.assertEqual(len(items), 2)
        self.assertIsInstance(items[0], RawBlock)
        self.assertEqual(
            items[0].text, "STYLE\n::cue { color: red; }"
        )
        self.assertIsInstance(items[1], Cue)

    def test_region_block_preserved(self):
        vtt = (
            "WEBVTT\n\n"
            "REGION\nwidth: 40%\n\n"
            "00:00:01.000 --> 00:00:02.000\nHi"
        )
        items = parse(vtt)
        self.assertIsInstance(items[0], RawBlock)
        self.assertIn("width: 40%", items[0].text)

    def test_note_block_preserved(self):
        vtt = (
            "WEBVTT\n\n"
            "NOTE\nThis is a note\n\n"
            "00:00:01.000 --> 00:00:02.000\nHi"
        )
        items = parse(vtt)
        self.assertIsInstance(items[0], RawBlock)

    def test_end_before_start_rejected(self):
        vtt = "WEBVTT\n\n00:00:05.000 --> 00:00:02.000\nHi"
        with self.assertRaises(ValueError):
            parse(vtt)

    def test_cue_timestamp_line_without_arrow(self):
        vtt = "WEBVTT\n\n00:00:01.000 00:00:02.000\nHi"
        with self.assertRaises(ValueError):
            parse(vtt)

    def test_identifier_not_followed_by_timestamp(self):
        vtt = "WEBVTT\n\nintro\nHello"
        with self.assertRaises(ValueError):
            parse(vtt)

    def test_short_timestamp_accepted(self):
        vtt = "WEBVTT\n\n00:01.000 --> 00:02.000\nHi"
        items = parse(vtt)
        self.assertEqual(items[0].start, 1000)
        self.assertEqual(items[0].end, 2000)

    def test_header_with_metadata_ignored(self):
        vtt = "WEBVTT - Some notes\n\n00:00:01.000 --> 00:00:02.000\nHi"
        items = parse(vtt)
        self.assertEqual(len(items), 1)

    def test_carriage_returns_normalized(self):
        vtt = "WEBVTT\r\n\r\n00:00:01.000 --> 00:00:02.000\r\nHi"
        items = parse(vtt)
        self.assertEqual(items[0].payload, "Hi")

    def test_parse_rejects_non_string(self):
        with self.assertRaises(ValueError):
            parse(12345)


class TestSerialize(unittest.TestCase):
    def test_round_trip_basic(self):
        original = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:02.000\nHello"
        )
        items = parse(original)
        result = serialize(items)
        self.assertEqual(result, "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello\n")

    def test_round_trip_with_identifier(self):
        original = (
            "WEBVTT\n\n"
            "intro\n00:00:01.000 --> 00:00:02.000\nHello"
        )
        result = serialize(parse(original))
        self.assertIn("intro\n00:00:01.000 --> 00:00:02.000", result)

    def test_short_form_timestamps_normalized_on_output(self):
        original = "WEBVTT\n\n00:01.000 --> 00:02.000\nHi"
        result = serialize(parse(original))
        self.assertIn("00:00:01.000 --> 00:00:02.000", result)

    def test_style_block_round_trips(self):
        original = (
            "WEBVTT\n\n"
            "STYLE\n::cue { color: red; }\n\n"
            "00:00:01.000 --> 00:00:02.000\nHi"
        )
        result = serialize(parse(original))
        self.assertIn("STYLE\n::cue { color: red; }", result)

    def test_serialize_rejects_non_list(self):
        with self.assertRaises(ValueError):
            serialize("WEBVTT")

    def test_serialize_rejects_unknown_type(self):
        with self.assertRaises(ValueError):
            serialize([42])


class TestCueAsDict(unittest.TestCase):
    def test_as_dict_with_identifier(self):
        cue = Cue(
            start=1000, end=2000, payload="Hi", identifier="intro"
        )
        d = cue.as_dict()
        self.assertEqual(d["start"], "00:00:01.000")
        self.assertEqual(d["end"], "00:00:02.000")
        self.assertEqual(d["payload"], "Hi")
        self.assertEqual(d["identifier"], "intro")

    def test_as_dict_without_identifier(self):
        cue = Cue(start=1000, end=2000, payload="Hi")
        d = cue.as_dict()
        self.assertNotIn("identifier", d)


if __name__ == "__main__":
    unittest.main()
