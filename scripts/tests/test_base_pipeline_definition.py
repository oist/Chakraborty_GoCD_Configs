import os
import sys
import unittest

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PipelineGenerationUtils import BasePipelineDefinition


class _DumpableA(BasePipelineDefinition):
    def __init__(self, x):
        self.x = x

    def buildData(self, dumper):
        return {"x": self.x}


class _DumpableB(BasePipelineDefinition):
    def __init__(self, y):
        self.y = y

    def buildData(self, dumper):
        return {"y": self.y}


class BasePipelineDefinitionTests(unittest.TestCase):
    def test_subclasses_dump_as_plain_mappings(self):
        # Regression test: yaml.YAMLObjectMetaclass only auto-registers a
        # dumper representer for classes that declare yaml_tag in their own
        # body. A subclass that only inherits yaml_tag from a shared base
        # (instead of redeclaring it) would silently fall back to a verbose
        # python/object dump unless the base explicitly re-registers each
        # subclass via __init_subclass__.
        out = yaml.dump({"a": _DumpableA(1), "b": _DumpableB(2)}, sort_keys=False)
        self.assertNotIn("python/object", out)
        self.assertEqual(yaml.safe_load(out), {"a": {"x": 1}, "b": {"y": 2}})

    def test_real_pipeline_classes_are_registered_with_the_dumper(self):
        from YamlGenerator import PipelineDefinition
        from Generate_RT_Pipeline import PipelineDefinition_RTapp
        from Generate_FPGA_Pipelines import (
            PipelineDefinition_FPGA,
            PipelineDefinition_FPGA_Noncompile,
        )

        for cls in (
            PipelineDefinition,
            PipelineDefinition_RTapp,
            PipelineDefinition_FPGA,
            PipelineDefinition_FPGA_Noncompile,
        ):
            self.assertIn(cls, yaml.Dumper.yaml_representers)


if __name__ == "__main__":
    unittest.main()
