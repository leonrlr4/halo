import tempfile
import unittest
from pathlib import Path

from halo import palette


class HexTest(unittest.TestCase):
    def test_round_trip_of_primaries(self):
        self.assertEqual(palette.hex_to_hsv("#ff0000"), (0, 100, 100))
        self.assertEqual(palette.hex_to_hsv("00ff00"), (120, 100, 100))
        self.assertEqual(palette.hs_to_hex((240, 100)), "#0000ff")

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            palette.hex_to_hsv("#12345")


class PickVividTest(unittest.TestCase):
    def test_drops_greys_darks_and_near_duplicates(self):
        colors = ["#232A2E",   # background: too dark
                  "#ADC9BC",   # foreground: too grey
                  "#F57F82",   # red
                  "#F58082",   # the same red again
                  "#B2CAED"]   # blue
        got = palette.pick_vivid(colors)
        self.assertEqual([h for h, _ in got], [358, 216])

    def test_keeps_theme_order(self):
        got = palette.pick_vivid(["#0000ff", "#ff0000"])
        self.assertEqual([h for h, _ in got], [240, 0])


class WalkHuesTest(unittest.TestCase):
    def test_first_stays_rest_go_clockwise_from_it(self):
        got = palette.walk_hues([(170, 50), (0, 50), (90, 50), (220, 50)])
        self.assertEqual([h for h, _ in got], [170, 220, 0, 90])


class LayoutTest(unittest.TestCase):
    def test_gradient_hits_both_ends(self):
        g = palette.gradient([(0, 100), (120, 100)], 50)
        self.assertEqual(len(g), 50)
        self.assertEqual(g[0], (0, 100))
        self.assertEqual(g[-1], (120, 100))

    def test_gradient_takes_the_short_way_round(self):
        # 350 -> 10 should pass through 0, not through 180.
        mid = palette.gradient([(350, 100), (10, 100)], 3)[1]
        self.assertEqual(mid[0], 0)

    def test_mirror_ends_where_it_starts(self):
        m = palette.layout([(0, 100), (120, 100), (240, 100)], 50, "mirror")
        self.assertEqual(m[0], m[-1])

    def test_blocks_are_equal_bands(self):
        b = palette.layout([(0, 100), (120, 100)], 10, "blocks")
        self.assertEqual(b, [(0, 100)] * 5 + [(120, 100)] * 5)

    def test_positioned_stops(self):
        g = palette.gradient_at([(0.5, (120, 100)), (0.0, (0, 100))], 5)
        self.assertEqual(g[0], (0, 100))
        self.assertEqual(g[2], (120, 100))
        self.assertEqual(g[4], (120, 100))

    def test_unknown_layout(self):
        with self.assertRaises(ValueError):
            palette.layout([(0, 100)], 5, "zigzag")


class ThemeReaderTest(unittest.TestCase):
    def test_reads_accent_first_and_skips_black_and_white_slots(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "colors.toml").write_text(
                'accent = "#B3E6DB"\ncolor0 = "#000000"\ncolor1 = "#F57F82"\n'
                'color7 = "#ffffff"\ncolor4 = "#839E9A"\n')
            self.assertEqual(palette.theme_colors(Path(d)), ["#B3E6DB", "#F57F82", "#839E9A"])

    def test_missing_theme_is_empty(self):
        self.assertEqual(palette.theme_colors(Path("/nonexistent")), [])


if __name__ == "__main__":
    unittest.main()
