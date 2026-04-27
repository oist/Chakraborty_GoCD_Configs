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
    create_ppl_dir,
    ls_task,
    gci_recurse_1_task,
    rt_builder_git_dir,
    rt_builder_material,
)

cachedMaterials = {}

mklink_fpga_tasks = {
    "debug": {
        "exec": {
            "run_if": "passed",
            "command": "powershell",
            "arguments": [
                "-Command",
                "New-Item",
                "-Force",
                "-ItemType",
                "Junction",
                "-Path",
                "PPLs\\cRIO-9045\\home",  # relative path?
                "-Target",
                f'\\"C:\\LabVIEW Sources\\PPLs\\cRIO-9045\\Debug_32\\home\\"',
            ],
        }
    },
    "release": {
        "exec": {
            "run_if": "passed",
            "command": "powershell",
            "arguments": [
                "-Command",
                "New-Item",
                "-Force",
                "-ItemType",
                "Junction",
                "-Path",
                "PPLs\\cRIO-9045\\home",  # relative path?
                "-Target",
                f'\\"C:\\LabVIEW Sources\\PPLs\\cRIO-9045\\Release_32\\home\\"',
            ],
        }
    },
}


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
                "PROJECT_PATH": f"{gitDirName}\\{self.projectFileName}",
                "VERSION_VI_PATH": self.version_vi_path,
                "FPGA_COMPILE_HOSTNAME": "fmu-build.chakraborty.lab",
                "FPGA_COMPILE_USERNAME": "fpga_builder",
                "FPGA_COMPILE_PASSWORD": "{{SECRET:[secrets.json][fpga_builder_password]}}",
            },
            "materials": {**materials, rt_builder_git_dir: rt_builder_material},
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
                                    create_ppl_dir,
                                    # mklink_fpga_tasks["debug"],
                                    ls_task,
                                    gci_recurse_1_task,
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


class PipelineDefinition_FPGA_Noncompile(yaml.YAMLObject):
    yaml_tag = "!PipelineDefinition"

    def __init__(self, pipelineEntry):
        [name, values] = list(pipelineEntry.items())[0]
        self.name = name
        self.gitUrl = values["gitUrl"]
        self.lv_version = values["lv_version"] if "lv_version" in values else "2019"
        self.noncompile_artifact_file = values["noncompile_artifact_file"]

    def buildData(self, dumper):
        gitDirName = directoryFromGitRepo(self.gitUrl, None)
        materials = generateMaterials(self.gitUrl, None, cachedMaterials)

        targetName = Target.FPGA_Debug

        return {
            "group": "cRIO",
            "parameters": {
                "GIT_DIR": gitDirName,
                "LV_VERSION": self.lv_version,
            },
            "materials": materials,
            "stages": [
                {
                    "build_fpga": {
                        "fetch_materials": "yes",
                        "clean_workspace": "yes",
                        "approval": "manual",
                        "jobs": {
                            "build_fpga": {
                                "timeout": 5,  # Short timeout since this job only copies an existing artifact
                                "elastic_profile_id": profileId[self.lv_version][
                                    targetName
                                ],
                                "artifacts": [
                                    {
                                        "build": {
                                            "source": f"{gitDirName}/FPGA Bitfiles/{self.noncompile_artifact_file}",
                                            "destination": "FPGA Bitfiles",
                                        }
                                    }
                                ],
                                "tasks": [
                                    ls_task,
                                    gci_recurse_1_task,
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
    ENABLE_NONCOMPILE_PIPELINES = True

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

    # Build compile pipeline objects
    pipelineDefinitionContent = {}
    for name, values in pipelineEntries.items():
        pipelineDefinitionContent[name] = PipelineDefinition_FPGA({name: values})

    # Append noncompile pipeline objects when enabled
    if ENABLE_NONCOMPILE_PIPELINES:
        noncompilePipelineEntries = {
            "cRIO_FPGA_Main_noncompile": {
                "gitUrl": gitUrl,
                "lv_version": "2019",
                "noncompile_artifact_file": "cR9045-FPGAMain_tiGh-z7G0kw.lvbitx",
            },
            "cRIO_FPGA_Expansion_noncompile": {
                "gitUrl": gitUrl,
                "lv_version": "2019",
                "noncompile_artifact_file": "crio-9045-rt_FPGATarget2_Main_yKmXqsdb6fY.lvbitx",
            },
        }

        for name, values in noncompilePipelineEntries.items():
            pipelineDefinitionContent[name] = PipelineDefinition_FPGA_Noncompile(
                {name: values}
            )

    # Convert the list of pipelines into a YAML object
    yamlObject = buildYamlObject(pipelineDefinitionContent)
    # Write to file
    outputFilePath = "./cRIO_FPGA_Pipelines.gocd.yaml"
    with open(outputFilePath, "w") as outputFile:
        yaml.dump(yamlObject, outputFile, sort_keys=False, width=999999)

    print(f"Generated {outputFilePath} ({os.path.getsize(outputFilePath)} bytes)")
