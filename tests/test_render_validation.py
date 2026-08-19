import unittest

from bot.services.render_validation import (
    frame_source_time,
    normalize_hex,
    parse_resolution,
    row_layout,
)


class RenderValidationTests(unittest.TestCase):
    def test_normalize_hex(self) -> None:
        self.assertEqual(normalize_hex("0a84ff"), "#0A84FF")
        self.assertEqual(normalize_hex("#ffffff"), "#FFFFFF")
        with self.assertRaises(ValueError):
            normalize_hex("#FFFF")

    def test_explicit_resolution(self) -> None:
        self.assertEqual(parse_resolution("1920x530"), (1920, 530))
        self.assertEqual(parse_resolution("1080×1080"), (1080, 1080))
        with self.assertRaises(ValueError):
            parse_resolution("1919x530")
        with self.assertRaises(ValueError):
            parse_resolution("1920x1200")

    def test_ratio_presets(self) -> None:
        self.assertEqual(parse_resolution("2.35:1"), (1920, 818))
        self.assertEqual(parse_resolution("16:9"), (1920, 1080))
        self.assertEqual(parse_resolution("1:1"), (1080, 1080))

    def test_row_layout_is_centered_and_limited(self) -> None:
        boxes = row_layout(3, 1920, 530, 55)
        self.assertEqual(len(boxes), 3)
        self.assertEqual(boxes[0][1], boxes[-1][1])
        self.assertLess(boxes[0][0], boxes[-1][0])
        self.assertLessEqual(boxes[-1][0] + boxes[-1][2], 1920)
        with self.assertRaises(ValueError):
            row_layout(11, 1920, 530, 55)

    def test_frame_source_time_loops(self) -> None:
        self.assertAlmostEqual(frame_source_time(90, 60, 1.0), 0.5)
        self.assertEqual(frame_source_time(10, 60, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
