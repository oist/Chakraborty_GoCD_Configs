import os
import sys
import unittest

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Constants
import Generate_RT_Pipeline as GRT
from Generate_RT_Pipeline import PipelineDefinition_RTapp, buildYamlObject


def _entry(
    name,
    vipkgUrls=None,
    minLabVIEWVersion=None,
    dependencies=None,
    dependencyPPLNames=None,
):
    return name, {
        "gitUrl": "git@github.com:oist/Chakraborty_cRIO",
        "Dependencies": dependencies or [],
        "Dependency PPL Names": dependencyPPLNames or [],
        "minLabVIEWVersion": minLabVIEWVersion,
        "vipkgUrls": vipkgUrls,
        "branch": "master",
    }


def _dump(pipelineDict):
    return yaml.dump(buildYamlObject(pipelineDict), sort_keys=False, width=999999)


class PipelineDefinitionRTappTests(unittest.TestCase):
    def setUp(self):
        # Both caches are module-level and keyed by content/name; clear them
        # so tests don't leak cached objects into each other.
        GRT.cachedMaterials.clear()
        GRT.cachedBuildJobs.clear()

    def test_dumps_as_plain_mapping(self):
        pd = PipelineDefinition_RTapp(*_entry("AppA"))
        out = _dump({"AppA": pd})
        self.assertNotIn("python/object", out)

    def test_lv_version_defaults_when_unset(self):
        pd = PipelineDefinition_RTapp(*_entry("AppA"))
        reparsed = yaml.safe_load(
            _dump({"AppA": pd}).replace("!PipelineDefinition", "")
        )
        self.assertEqual(
            reparsed["pipelines"]["AppA"]["parameters"]["LV_VERSION"],
            Constants.DEFAULT_LV_VERSION,
        )

    def test_dependency_names_quoted(self):
        pd = PipelineDefinition_RTapp(
            *_entry(
                "AppA", dependencies=["Dep1p"], dependencyPPLNames=["Dep1.lvlibp"]
            )
        )
        reparsed = yaml.safe_load(
            _dump({"AppA": pd}).replace("!PipelineDefinition", "")
        )
        self.assertEqual(
            reparsed["pipelines"]["AppA"]["parameters"]["Dependency_PPL_Names"],
            '"Dep1.lvlibp"',
        )

    def test_multiple_vipkg_urls_alias_the_shared_configuration(self):
        # Regression test: generateRTBuildJob used to hoist a single
        # vipkgPluginConfig dict shared by every vipkg task in the pipeline,
        # so PyYAML emitted one anchor for it no matter how many vipkgUrls
        # were configured. Extracting generateVipkgTask() initially rebuilt
        # that dict on every call, silently breaking the alias and bloating
        # cRIO_RT_Pipelines.gocd.yaml. Pin the aliasing behavior down here.
        pd = PipelineDefinition_RTapp(
            *_entry(
                "AppA",
                vipkgUrls=[
                    "http://example.com/a.vip",
                    "http://example.com/b.vip",
                ],
            )
        )
        out = _dump({"AppA": pd})
        self.assertEqual(out.count("vi-package-installer"), 1)
        self.assertIn("&id", out)


if __name__ == "__main__":
    unittest.main()
