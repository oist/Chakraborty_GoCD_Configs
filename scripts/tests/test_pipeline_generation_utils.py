import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Constants
import PipelineGenerationUtils as PGU


class AliasableTests(unittest.TestCase):
    def test_equal_content_returns_same_object(self):
        cache = {}
        a = PGU.aliasable({"x": 1, "y": [1, 2, 3]}, cache)
        b = PGU.aliasable({"y": [1, 2, 3], "x": 1}, cache)  # different key order
        self.assertIs(a, b)
        self.assertEqual(len(cache), 1)

    def test_different_content_returns_different_objects(self):
        cache = {}
        a = PGU.aliasable({"x": 1}, cache)
        b = PGU.aliasable({"x": 2}, cache)
        self.assertIsNot(a, b)
        self.assertEqual(len(cache), 2)


class QuoteDependencyNamesTests(unittest.TestCase):
    def test_none_returns_empty_string(self):
        self.assertEqual(PGU.quoteDependencyNames(None), "")

    def test_quotes_and_joins_names(self):
        self.assertEqual(
            PGU.quoteDependencyNames(["Dep1.lvlibp", "Dep2.lvlibp"]),
            '"Dep1.lvlibp" "Dep2.lvlibp"',
        )

    def test_single_name(self):
        self.assertEqual(PGU.quoteDependencyNames(["Dep1.lvlibp"]), '"Dep1.lvlibp"')


class MakeJunctionTaskTests(unittest.TestCase):
    def test_structure_uses_given_path_and_target(self):
        task = PGU.make_junction_task("PPLs\\Current", "Windows\\Release_32")
        args = task["exec"]["arguments"]
        self.assertEqual(task["exec"]["command"], "powershell")
        self.assertIn("PPLs\\Current", args)
        self.assertTrue(any("Windows\\Release_32" in a for a in args))


class GenerateVipkgTaskTests(unittest.TestCase):
    def test_structure(self):
        task = PGU.generateVipkgTask("http://example.com/pkg.vip", "C:\\LabVIEW")
        options = task["plugin"]["options"]
        self.assertEqual(options["Url"], "http://example.com/pkg.vip")
        self.assertEqual(options["LabVIEWDirectory"], "C:\\LabVIEW")
        self.assertEqual(
            task["plugin"]["configuration"], Constants.vipkg_plugin_configuration
        )

    def test_configuration_is_shared_across_calls(self):
        # Regression test: generateVipkgTask must reuse the same
        # configuration object on every call so PyYAML can alias repeated
        # vipkg tasks (e.g. multiple vipkgUrls in one pipeline) instead of
        # inlining a fresh copy of the configuration block for each one.
        t1 = PGU.generateVipkgTask("http://example.com/a.vip", "C:\\LabVIEW")
        t2 = PGU.generateVipkgTask("http://example.com/b.vip", "C:\\LabVIEW")
        self.assertIs(t1["plugin"]["configuration"], t2["plugin"]["configuration"])


class GenerateRTBuildJobTests(unittest.TestCase):
    def test_identical_calls_share_identity_with_cache(self):
        cache = {}
        job1 = PGU.generateRTBuildJob("2019", True, [], [], "", cache)
        job2 = PGU.generateRTBuildJob("2019", True, [], [], "", cache)
        self.assertIs(job1, job2)
        self.assertEqual(len(cache), 1)

    def test_debug_and_release_are_distinct_cache_entries(self):
        cache = {}
        debugJob = PGU.generateRTBuildJob("2019", True, [], [], "", cache)
        releaseJob = PGU.generateRTBuildJob("2019", False, [], [], "", cache)
        self.assertIsNot(debugJob, releaseJob)
        self.assertEqual(len(cache), 2)

    def test_without_cache_each_call_returns_a_fresh_object(self):
        job1 = PGU.generateRTBuildJob("2019", True, [], [], "")
        job2 = PGU.generateRTBuildJob("2019", True, [], [], "")
        self.assertIsNot(job1, job2)
        self.assertEqual(job1, job2)


if __name__ == "__main__":
    unittest.main()
