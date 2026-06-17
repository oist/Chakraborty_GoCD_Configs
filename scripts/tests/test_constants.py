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


class TargetPathEndsTests(unittest.TestCase):
    def test_has_exactly_one_entry_per_target(self):
        # Regression test: cRIO_Release/cRIO_Debug were previously defined
        # twice in this dict, silently collapsing to one entry each.
        expected_keys = {t.name for t in Constants.Target}
        self.assertEqual(set(Constants.targetPathEnds.keys()), expected_keys)
        self.assertEqual(len(Constants.targetPathEnds), len(Constants.Target))


if __name__ == "__main__":
    unittest.main()
