import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Constants


class TargetGroupingsTests(unittest.TestCase):
    def test_ppl_targets_is_windows_plus_crio(self):
        self.assertEqual(
            Constants.ppl_targets,
            Constants.windows_targets + Constants.crio_ppl_targets,
        )

    def test_ppl_targets_excludes_fpga(self):
        fpga_targets = {Constants.Target.FPGA_Release, Constants.Target.FPGA_Debug}
        self.assertFalse(fpga_targets & set(Constants.ppl_targets))

    def test_is_windows_true_for_windows_targets(self):
        for target in Constants.windows_targets:
            self.assertTrue(Constants.is_windows(target))
            self.assertFalse(Constants.is_crio(target))

    def test_is_crio_true_for_crio_targets(self):
        for target in Constants.crio_ppl_targets:
            self.assertTrue(Constants.is_crio(target))
            self.assertFalse(Constants.is_windows(target))

    def test_fpga_targets_are_neither_windows_nor_crio(self):
        for target in (Constants.Target.FPGA_Release, Constants.Target.FPGA_Debug):
            self.assertFalse(Constants.is_windows(target))
            self.assertFalse(Constants.is_crio(target))


class HighestLVVersionTests(unittest.TestCase):
    def test_returns_the_higher_of_two(self):
        self.assertEqual(Constants.highest_lv_version(["2019", "2021"]), "2021")

    def test_order_independent(self):
        self.assertEqual(Constants.highest_lv_version(["2021", "2019"]), "2021")

    def test_single_element(self):
        self.assertEqual(Constants.highest_lv_version(["2019"]), "2019")

    def test_accepts_a_set(self):
        self.assertEqual(Constants.highest_lv_version({"2019", "2021"}), "2021")

    def test_empty_returns_none(self):
        self.assertIsNone(Constants.highest_lv_version([]))

    def test_orders_historical_naming_schemes(self):
        # Dotted, year, year+SP and year+quarter schemes must sort low-to-high.
        versions = ["2026Q3", "2019", "8.2", "2026Q1", "8.0", "2019SP1", "2015"]
        self.assertEqual(
            sorted(versions, key=Constants.version_sort_key),
            ["8.0", "8.2", "2015", "2019", "2019SP1", "2026Q1", "2026Q3"],
        )

    def test_highest_among_historical_schemes(self):
        versions = ["8.0", "8.2", "2015", "2019", "2019SP1", "2026Q1", "2026Q3"]
        self.assertEqual(Constants.highest_lv_version(versions), "2026Q3")

    def test_bare_year_sorts_below_service_pack(self):
        self.assertEqual(Constants.highest_lv_version(["2019", "2019SP1"]), "2019SP1")

    def test_dotted_minor_compared_numerically_not_lexically(self):
        # "8.10" > "8.2" numerically, though it would lose a plain string sort.
        self.assertEqual(Constants.highest_lv_version(["8.2", "8.10"]), "8.10")


class TargetPathEndsTests(unittest.TestCase):
    def test_has_exactly_one_entry_per_target(self):
        # Regression test: cRIO_Release/cRIO_Debug were previously defined
        # twice in this dict, silently collapsing to one entry each.
        expected_keys = {t.name for t in Constants.Target}
        self.assertEqual(set(Constants.targetPathEnds.keys()), expected_keys)
        self.assertEqual(len(Constants.targetPathEnds), len(Constants.Target))


if __name__ == "__main__":
    unittest.main()
