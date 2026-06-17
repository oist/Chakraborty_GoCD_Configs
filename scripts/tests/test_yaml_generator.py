import os
import sys
import unittest

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Constants
import YamlGenerator as YG
from YamlGenerator import (
    PipelineDefinition,
    buildYamlObject,
    findNonDefaultLVPipelines,
    updateMinimumVersions,
)


def _values(
    PPL_Name,
    artifactId=None,
    gitUrl="git@github.com:oist/Lib",
    libPath="Lib/Lib.lvlib",
    Dependencies=None,
    DependencyPPLNames=None,
    minLabVIEWVersion=None,
    vipkgUrls=None,
):
    return {
        "artifactId": artifactId or (PPL_Name.replace(".lvlibp", "") + "_nipkg"),
        "gitUrl": gitUrl,
        "libPath": libPath,
        "PPL_Name": PPL_Name,
        "Dependencies": Dependencies,
        "Dependency PPL Names": DependencyPPLNames,
        "minLabVIEWVersion": minLabVIEWVersion,
        "vipkgUrls": vipkgUrls,
    }


def _dump(pipelineDict):
    return yaml.dump(buildYamlObject(pipelineDict), sort_keys=False, width=999999)


class PipelineDefinitionTests(unittest.TestCase):
    def setUp(self):
        # dependencyMaterials is a module-level cache keyed by dependency
        # pipeline name; clear it so tests don't leak state into each other.
        YG.dependencyMaterials.clear()

    def test_dumps_as_plain_mapping(self):
        pd = PipelineDefinition("Ap", _values("A.lvlibp"))
        out = _dump({"Ap": pd})
        self.assertNotIn("python/object", out)

    def test_six_ppl_targets_with_no_fpga_leakage(self):
        pd = PipelineDefinition("Ap", _values("A.lvlibp"))
        reparsed = yaml.safe_load(_dump({"Ap": pd}).replace("!PipelineDefinition", ""))
        jobs = reparsed["pipelines"]["Ap"]["stages"][0]["build_ppls"]["jobs"]
        self.assertEqual(set(jobs.keys()), {t.name for t in Constants.ppl_targets})
        self.assertNotIn("FPGA_Release", jobs)
        self.assertNotIn("FPGA_Debug", jobs)

    def test_lv_version_defaults_when_unset(self):
        pd = PipelineDefinition("Ap", _values("A.lvlibp"))
        reparsed = yaml.safe_load(_dump({"Ap": pd}).replace("!PipelineDefinition", ""))
        self.assertEqual(
            reparsed["pipelines"]["Ap"]["parameters"]["LV_VERSION"],
            Constants.DEFAULT_LV_VERSION,
        )

    def test_lv_version_honors_explicit_minimum(self):
        pd = PipelineDefinition("Ap", _values("A.lvlibp", minLabVIEWVersion="2021"))
        reparsed = yaml.safe_load(_dump({"Ap": pd}).replace("!PipelineDefinition", ""))
        self.assertEqual(reparsed["pipelines"]["Ap"]["parameters"]["LV_VERSION"], "2021")

    def test_no_dependencies_means_empty_quoted_string(self):
        pd = PipelineDefinition("Ap", _values("A.lvlibp"))
        reparsed = yaml.safe_load(_dump({"Ap": pd}).replace("!PipelineDefinition", ""))
        self.assertEqual(
            reparsed["pipelines"]["Ap"]["parameters"]["Dependency_PPL_Names"], ""
        )

    def test_dependency_names_quoted(self):
        pdA = PipelineDefinition("Ap", _values("A.lvlibp"))
        pdB = PipelineDefinition(
            "Bp",
            _values("B.lvlibp", Dependencies=["Ap"], DependencyPPLNames=["A.lvlibp"]),
        )
        reparsed = yaml.safe_load(
            _dump({"Ap": pdA, "Bp": pdB}).replace("!PipelineDefinition", "")
        )
        self.assertEqual(
            reparsed["pipelines"]["Bp"]["parameters"]["Dependency_PPL_Names"],
            '"A.lvlibp"',
        )

    def test_anchors_and_aliases_present_for_shared_tasks(self):
        pdA = PipelineDefinition("Ap", _values("A.lvlibp"))
        pdB = PipelineDefinition(
            "Bp",
            _values("B.lvlibp", Dependencies=["Ap"], DependencyPPLNames=["A.lvlibp"]),
        )
        pdC = PipelineDefinition(
            "Cp",
            _values("C.lvlibp", Dependencies=["Ap"], DependencyPPLNames=["A.lvlibp"]),
        )
        out = _dump({"Ap": pdA, "Bp": pdB, "Cp": pdC})
        self.assertIn("&id", out)
        self.assertIn("*id", out)


class FindNonDefaultLVPipelinesTests(unittest.TestCase):
    def setUp(self):
        YG.dependencyMaterials.clear()

    def test_filters_to_non_default_versions(self):
        pdDefault = PipelineDefinition("Ap", _values("A.lvlibp"))
        pdNonDefault = PipelineDefinition(
            "Bp", _values("B.lvlibp", minLabVIEWVersion="2021")
        )
        names = findNonDefaultLVPipelines(
            {"Ap": pdDefault, "Bp": pdNonDefault}, Constants.DEFAULT_LV_VERSION
        )
        self.assertEqual(set(names), {"Bp"})


class UpdateMinimumVersionsTests(unittest.TestCase):
    def setUp(self):
        YG.dependencyMaterials.clear()

    def test_propagates_non_default_version_to_dependents(self):
        pdDefault = PipelineDefinition("Ap", _values("A.lvlibp"))
        pdNonDefault = PipelineDefinition(
            "Bp", _values("B.lvlibp", minLabVIEWVersion="2021")
        )
        pdDependent = PipelineDefinition(
            "Cp",
            _values("C.lvlibp", Dependencies=["Bp"], DependencyPPLNames=["B.lvlibp"]),
        )
        pipelineDict = {"Ap": pdDefault, "Bp": pdNonDefault, "Cp": pdDependent}

        updated = updateMinimumVersions(pipelineDict)

        self.assertIsNone(updated["Ap"].minVersion)
        self.assertEqual(updated["Bp"].minVersion, "2021")
        self.assertEqual(updated["Cp"].minVersion, "2021")

    def test_no_nondefault_pipelines_returns_dict_unchanged(self):
        pipelineDict = {"Ap": PipelineDefinition("Ap", _values("A.lvlibp"))}
        self.assertIs(updateMinimumVersions(pipelineDict), pipelineDict)


if __name__ == "__main__":
    unittest.main()
