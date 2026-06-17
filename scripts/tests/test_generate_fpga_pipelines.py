import os
import sys
import unittest

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Constants
from Generate_FPGA_Pipelines import (
    PipelineDefinition_FPGA,
    PipelineDefinition_FPGA_Noncompile,
    buildYamlObject,
)


def _dump(pipelineDict):
    return yaml.dump(buildYamlObject(pipelineDict), sort_keys=False, width=999999)


class PipelineDefinitionFPGATests(unittest.TestCase):
    def test_dumps_as_plain_mapping_and_defaults_lv_version(self):
        values = {
            "gitUrl": "git@github.com:oist/Chakraborty_cRIO",
            "targetName": "FPGA Target",
            "buildSpecName": "FPGA Main",
            "version_VI_path": "FPGA/FPGA Version Number.vi",
            "projectFileName": "cRIO-9045-RT.lvproj",
        }
        pd = PipelineDefinition_FPGA({"cRIO_FPGA_Main": values})
        out = _dump({"cRIO_FPGA_Main": pd})
        self.assertNotIn("python/object", out)
        reparsed = yaml.safe_load(out.replace("!PipelineDefinition", ""))
        self.assertEqual(
            reparsed["pipelines"]["cRIO_FPGA_Main"]["parameters"]["LV_VERSION"],
            Constants.DEFAULT_LV_VERSION,
        )

    def test_honors_explicit_lv_version(self):
        values = {
            "gitUrl": "git@github.com:oist/Chakraborty_cRIO",
            "targetName": "FPGA Target",
            "buildSpecName": "FPGA Main",
            "lv_version": "2021",
            "projectFileName": "cRIO-9045-RT.lvproj",
        }
        pd = PipelineDefinition_FPGA({"cRIO_FPGA_Main": values})
        reparsed = yaml.safe_load(
            _dump({"cRIO_FPGA_Main": pd}).replace("!PipelineDefinition", "")
        )
        self.assertEqual(
            reparsed["pipelines"]["cRIO_FPGA_Main"]["parameters"]["LV_VERSION"],
            "2021",
        )


class PipelineDefinitionFPGANoncompileTests(unittest.TestCase):
    def test_dumps_as_plain_mapping_and_defaults_lv_version(self):
        values = {
            "gitUrl": "git@github.com:oist/Chakraborty_cRIO",
            "noncompile_artifact_file": "cR9045-FPGAMain.lvbitx",
        }
        pd = PipelineDefinition_FPGA_Noncompile({"cRIO_FPGA_Main_noncompile": values})
        out = _dump({"cRIO_FPGA_Main_noncompile": pd})
        self.assertNotIn("python/object", out)
        reparsed = yaml.safe_load(out.replace("!PipelineDefinition", ""))
        self.assertEqual(
            reparsed["pipelines"]["cRIO_FPGA_Main_noncompile"]["parameters"][
                "LV_VERSION"
            ],
            Constants.DEFAULT_LV_VERSION,
        )


if __name__ == "__main__":
    unittest.main()
