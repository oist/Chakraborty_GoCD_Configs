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
    updateMinimumVersions,
    validateCrioOnlyDependencies,
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
    crioOnly=False,
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
        "crioOnly": crioOnly,
    }


def _dump(pipelineDict):
    return yaml.dump(buildYamlObject(pipelineDict), sort_keys=False, width=999999)


class PipelineDefinitionTests(unittest.TestCase):
    def setUp(self):
        # dependencyMaterials/cachedGitTagStages are module-level caches;
        # clear them so tests don't leak state into each other.
        YG.dependencyMaterials.clear()
        YG.cachedGitTagStages.clear()

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


class UpdateMinimumVersionsTests(unittest.TestCase):
    def setUp(self):
        YG.dependencyMaterials.clear()

    def _pipeline(self, name, minVersion=None, deps=None):
        pplName = name.rstrip("p") + ".lvlibp"
        depPplNames = (
            [d.rstrip("p") + ".lvlibp" for d in deps] if deps is not None else None
        )
        return PipelineDefinition(
            name,
            _values(
                pplName,
                minLabVIEWVersion=minVersion,
                Dependencies=deps,
                DependencyPPLNames=depPplNames,
            ),
        )

    def test_propagates_non_default_version_to_dependents(self):
        pipelineDict = {
            "Ap": self._pipeline("Ap"),
            "Bp": self._pipeline("Bp", minVersion="2021"),
            "Cp": self._pipeline("Cp", deps=["Bp"]),
        }

        updated = updateMinimumVersions(pipelineDict)

        self.assertIsNone(updated["Ap"].minVersion)
        self.assertEqual(updated["Bp"].minVersion, "2021")
        self.assertEqual(updated["Cp"].minVersion, "2021")

    def test_propagates_transitively_through_a_chain(self):
        # D -> C -> B(2021): both C and B's caller D must be lifted to 2021.
        pipelineDict = {
            "Bp": self._pipeline("Bp", minVersion="2021"),
            "Cp": self._pipeline("Cp", deps=["Bp"]),
            "Dp": self._pipeline("Dp", deps=["Cp"]),
        }

        updateMinimumVersions(pipelineDict)

        self.assertEqual(pipelineDict["Cp"].minVersion, "2021")
        self.assertEqual(pipelineDict["Dp"].minVersion, "2021")

    def test_takes_highest_among_multiple_dependencies(self):
        # A caller depending on both a 2019 and a 2021 library is forced to 2021.
        pipelineDict = {
            "Ap": self._pipeline("Ap", minVersion="2019"),
            "Bp": self._pipeline("Bp", minVersion="2021"),
            "Cp": self._pipeline("Cp", deps=["Ap", "Bp"]),
        }

        updateMinimumVersions(pipelineDict)

        self.assertEqual(pipelineDict["Cp"].minVersion, "2021")

    def test_explicit_lower_minimum_is_overridden_by_dependency(self):
        # A caller that pins 2019 but depends on a 2021 library is lifted to 2021.
        pipelineDict = {
            "Bp": self._pipeline("Bp", minVersion="2021"),
            "Cp": self._pipeline("Cp", minVersion="2019", deps=["Bp"]),
        }

        updateMinimumVersions(pipelineDict)

        self.assertEqual(pipelineDict["Cp"].minVersion, "2021")

    def test_default_pipeline_with_default_dependency_stays_none(self):
        pipelineDict = {
            "Ap": self._pipeline("Ap"),
            "Bp": self._pipeline("Bp", deps=["Ap"]),
        }

        updateMinimumVersions(pipelineDict)

        self.assertIsNone(pipelineDict["Ap"].minVersion)
        self.assertIsNone(pipelineDict["Bp"].minVersion)

    def test_dependency_cycle_terminates_and_lifts_both(self):
        # A <-> B cycle where B requires 2021; the fixpoint must terminate and
        # raise both to 2021 rather than loop forever.
        pipelineDict = {
            "Ap": self._pipeline("Ap", deps=["Bp"]),
            "Bp": self._pipeline("Bp", minVersion="2021", deps=["Ap"]),
        }

        updateMinimumVersions(pipelineDict)

        self.assertEqual(pipelineDict["Ap"].minVersion, "2021")
        self.assertEqual(pipelineDict["Bp"].minVersion, "2021")

    def test_no_nondefault_pipelines_returns_dict_unchanged(self):
        pipelineDict = {"Ap": PipelineDefinition("Ap", _values("A.lvlibp"))}
        self.assertIs(updateMinimumVersions(pipelineDict), pipelineDict)


class CrioOnlyTests(unittest.TestCase):
    def setUp(self):
        YG.dependencyMaterials.clear()
        YG.cachedGitTagStages.clear()

    def test_crio_only_pipeline_builds_only_crio_targets(self):
        pd = PipelineDefinition("Ap", _values("A.lvlibp", crioOnly=True))
        reparsed = yaml.safe_load(_dump({"Ap": pd}).replace("!PipelineDefinition", ""))
        jobs = reparsed["pipelines"]["Ap"]["stages"][0]["build_ppls"]["jobs"]
        self.assertEqual(set(jobs.keys()), {t.name for t in Constants.crio_ppl_targets})

    def test_non_crio_only_pipeline_still_builds_all_targets(self):
        pd = PipelineDefinition("Ap", _values("A.lvlibp", crioOnly=False))
        reparsed = yaml.safe_load(_dump({"Ap": pd}).replace("!PipelineDefinition", ""))
        jobs = reparsed["pipelines"]["Ap"]["stages"][0]["build_ppls"]["jobs"]
        self.assertEqual(set(jobs.keys()), {t.name for t in Constants.ppl_targets})

    def test_git_tag_stage_only_fetches_crio_artifacts_for_crio_only(self):
        pd = PipelineDefinition("Ap", _values("A.lvlibp", crioOnly=True))
        reparsed = yaml.safe_load(_dump({"Ap": pd}).replace("!PipelineDefinition", ""))
        git_tag_tasks = reparsed["pipelines"]["Ap"]["stages"][1]["git_tag"]["tasks"]
        fetched_jobs = {
            t["fetch"]["job"]
            for t in git_tag_tasks
            if "fetch" in t and t["fetch"].get("stage") == "build_ppls"
        }
        self.assertEqual(fetched_jobs, {t.name for t in Constants.crio_ppl_targets})

    def test_git_tag_stage_fetches_all_targets_when_not_crio_only(self):
        pd = PipelineDefinition("Ap", _values("A.lvlibp", crioOnly=False))
        reparsed = yaml.safe_load(_dump({"Ap": pd}).replace("!PipelineDefinition", ""))
        git_tag_tasks = reparsed["pipelines"]["Ap"]["stages"][1]["git_tag"]["tasks"]
        fetched_jobs = {
            t["fetch"]["job"]
            for t in git_tag_tasks
            if "fetch" in t and t["fetch"].get("stage") == "build_ppls"
        }
        self.assertEqual(fetched_jobs, {t.name for t in Constants.ppl_targets})

    def test_git_tag_stage_aliases_across_pipelines_with_same_target_set(self):
        # Regression-style test for the point-2 cache requirement: every
        # cRIO-only pipeline should share one git_tag_stage object (and every
        # full-target pipeline should share a different one), so PyYAML
        # anchors it once instead of inlining a copy per pipeline.
        stageA = YG.get_git_tag_stage(True)
        stageB = YG.get_git_tag_stage(True)
        stageFull = YG.get_git_tag_stage(False)
        self.assertIs(stageA, stageB)
        self.assertIsNot(stageA, stageFull)


class ValidateCrioOnlyDependenciesTests(unittest.TestCase):
    def setUp(self):
        YG.dependencyMaterials.clear()

    def test_raises_when_windows_pipeline_depends_on_crio_only(self):
        pdCrioOnly = PipelineDefinition("Ap", _values("A.lvlibp", crioOnly=True))
        pdWindows = PipelineDefinition(
            "Bp",
            _values(
                "B.lvlibp", Dependencies=["Ap"], DependencyPPLNames=["A.lvlibp"]
            ),
        )
        with self.assertRaises(ValueError):
            validateCrioOnlyDependencies({"Ap": pdCrioOnly, "Bp": pdWindows})

    def test_allows_crio_only_pipeline_to_depend_on_crio_only(self):
        pdCrioOnly = PipelineDefinition("Ap", _values("A.lvlibp", crioOnly=True))
        pdAlsoCrioOnly = PipelineDefinition(
            "Bp",
            _values(
                "B.lvlibp",
                Dependencies=["Ap"],
                DependencyPPLNames=["A.lvlibp"],
                crioOnly=True,
            ),
        )
        # Should not raise.
        validateCrioOnlyDependencies({"Ap": pdCrioOnly, "Bp": pdAlsoCrioOnly})

    def test_allows_normal_dependencies(self):
        pdA = PipelineDefinition("Ap", _values("A.lvlibp"))
        pdB = PipelineDefinition(
            "Bp",
            _values("B.lvlibp", Dependencies=["Ap"], DependencyPPLNames=["A.lvlibp"]),
        )
        # Should not raise.
        validateCrioOnlyDependencies({"Ap": pdA, "Bp": pdB})


if __name__ == "__main__":
    unittest.main()
