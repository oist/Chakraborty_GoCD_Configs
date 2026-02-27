import os
import yaml
from pathlib import Path
from GitTools import cloneRepo
from FileUtils import directoryFromGitRepo
from PipelineGenerationUtils import generateMaterials
from Constants import (
    Target,
    profileId,
    fpga_build_task,
    fpga_artifact_path,
    script_fpga_version_task,
)

cachedMaterials = {}


class PipelineDefinition_FPGA(yaml.YAMLObject):
    yaml_tag = "!PipelineDefinition"

    def __init__(self, pipelineEntry):
        [name, values] = list(pipelineEntry.items())[0]
        self.name = name
        self.gitUrl = values["gitUrl"]
        self.targetName = values["targetName"]
        self.buildSpecName = values["buildSpecName"]
        self.lv_version = values["lv_version"] if "lv_version" in values else "2019"
        self.version_vi_path = (
            values["version_VI_path"] if "version_VI_path" in values else None
        )
        self.projectFileName = (
            values["projectFileName"] if "projectFileName" in values else None
        )

    def buildData(self, dumper):
        gitDirName = directoryFromGitRepo(self.gitUrl, None)
        materials = generateMaterials(self.gitUrl, None, cachedMaterials)

        targetName = Target.FPGA_Debug

        return {
            "group": "cRIO",
            "parameters": {
                "GIT_DIR": gitDirName,
                "LV_VERSION": self.lv_version,
                "FPGA_TARGET_NAME": self.targetName,
                "FPGA_BUILDSPEC_NAME": self.buildSpecName,
                "PROJECT_PATH": f"C:\\LabVIEW Sources\\{gitDirName}\\{self.projectFileName}",
                "VERSION_VI_PATH": self.version_vi_path,
            },
            "materials": materials,
            "stages": [
                {
                    "build_fpga": {
                        "fetch_materials": "yes",
                        "clean_workspace": "yes",
                        "approval": "manual",  # Set to "manual" to prevent auto-scheduling
                        "jobs": {
                            "build_fpga": {
                                # Timeout in minutes. FPGA builds typically take 40-60 minutes,
                                # with long silent periods during Xilinx synthesis, place & route,
                                # and bitstream generation. Set to 90 minutes to provide margin
                                # for slower builds without aborting prematurely. GoCD will
                                # cancel the job if it exceeds this duration.
                                "timeout": 90,
                                "elastic_profile_id": profileId[self.lv_version][
                                    targetName
                                ],
                                "artifacts": [
                                    {
                                        "build": {
                                            "source": fpga_artifact_path,
                                            "destination": "FPGA Bitfiles",
                                        }
                                    }
                                ],
                                "tasks": [
                                    script_fpga_version_task,
                                    fpga_build_task,
                                ],
                            }
                        },
                    }
                }
            ],
        }

    @classmethod
    def to_yaml(cls, dumper, self):
        data = self.buildData(dumper)
        return dumper.represent_mapping("tag:yaml.org,2002:map", data)


def buildYamlObject(pipelineDictionary):
    full_yaml_object = {"format_version": 10, "pipelines": pipelineDictionary}
    return full_yaml_object


if __name__ == "__main__":
    baseDir = os.path.join(Path.cwd(), "cloned")
    gitUrl = "git@github.com:oist/Chakraborty_cRIO"

    # Clone the cRIO repository
    outputDir = directoryFromGitRepo(gitUrl, baseDir)
    forceUpdate = False
    cloneRepo(gitUrl, outputDir, forceUpdate, timeout=20)

    # Define FPGA pipeline entries
    pipelineEntries = {
        "cRIO_FPGA_Main": {
            "gitUrl": gitUrl,
            "targetName": "FPGA Target",
            "buildSpecName": "FPGA Main",
            "lv_version": "2019",
            "version_VI_path": "FPGA/FPGA Version Number.vi",
            "projectFileName": "cRIO-9045-RT.lvproj",
        },
        "cRIO_FPGA_Expansion": {
            "gitUrl": gitUrl,
            "targetName": "FPGA Target 2",
            "buildSpecName": "Main",
            "lv_version": "2019",
            "version_VI_path": "FPGA Expansion/FPGA Expansion Version Number.vi",
            "projectFileName": "cRIO-9045-RT.lvproj",
        },
    }

    # Build a list of objects describing each pipeline
    pipelineDefinitionContent = {}
    for name, values in pipelineEntries.items():
        pipelineDefinitionContent[name] = PipelineDefinition_FPGA({name: values})

    # Convert the list of pipelines into a YAML object
    yamlObject = buildYamlObject(pipelineDefinitionContent)
    # Write to file
    outputFilePath = "./cRIO_FPGA_Pipelines.gocd.yaml"
    with open(outputFilePath, "w") as outputFile:
        yaml.dump(yamlObject, outputFile, sort_keys=False, width=999999)

    print(f"Generated {outputFilePath} ({os.path.getsize(outputFilePath)} bytes)")
