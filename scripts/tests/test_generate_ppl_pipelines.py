import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Generate_PPL_Pipelines import generateEntry


class GenerateEntryTests(unittest.TestCase):
    def test_returns_name_values_tuple(self):
        name, values = generateEntry(
            "Foop",
            "git@github.com:oist/Foo",
            "Foo/Foo.lvlib",
            "Foo.lvlibp",
            None,
            None,
            None,
            None,
            False,
        )
        self.assertEqual(name, "Foop")
        self.assertEqual(
            values,
            {
                "artifactId": "Foop_nipkg",
                "gitUrl": "git@github.com:oist/Foo",
                "libPath": "Foo/Foo.lvlib",
                "PPL_Name": "Foo.lvlibp",
                "Dependencies": None,
                "Dependency PPL Names": None,
                "minLabVIEWVersion": None,
                "vipkgUrls": None,
                "crioOnly": False,
            },
        )

    def test_with_dependencies_and_vipkg_urls(self):
        name, values = generateEntry(
            "Barp",
            "git@github.com:oist/Bar",
            "Bar/Bar.lvlib",
            "Bar.lvlibp",
            ["Foop"],
            ["Foo.lvlibp"],
            "2021",
            ["http://example.com/pkg.vip"],
            False,
        )
        self.assertEqual(values["Dependencies"], ["Foop"])
        self.assertEqual(values["Dependency PPL Names"], ["Foo.lvlibp"])
        self.assertEqual(values["minLabVIEWVersion"], "2021")
        self.assertEqual(values["vipkgUrls"], ["http://example.com/pkg.vip"])

    def test_crio_only_flag_passed_through(self):
        _, values = generateEntry(
            "Foop",
            "git@github.com:oist/Foo",
            "Foo/Foo.lvlib",
            "Foo.lvlibp",
            None,
            None,
            None,
            None,
            True,
        )
        self.assertTrue(values["crioOnly"])

    def test_entries_flatten_into_a_dict_via_chain(self):
        # Mirrors how __main__ flattens pool.starmap results: a list of
        # per-repo entry lists, each containing (name, values) tuples.
        import itertools

        entryA = generateEntry(
            "Foop", "git@github.com:oist/Foo", "Foo/Foo.lvlib", "Foo.lvlibp",
            None, None, None, None, False,
        )
        entryB = generateEntry(
            "Barp", "git@github.com:oist/Bar", "Bar/Bar.lvlib", "Bar.lvlibp",
            ["Foop"], ["Foo.lvlibp"], None, None, False,
        )
        perRepoEntries = [[entryA], [entryB]]

        flattened = dict(itertools.chain.from_iterable(perRepoEntries))

        self.assertEqual(set(flattened.keys()), {"Foop", "Barp"})
        self.assertEqual(flattened["Barp"]["Dependencies"], ["Foop"])


if __name__ == "__main__":
    unittest.main()
