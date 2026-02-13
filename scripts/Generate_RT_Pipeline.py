import os
import yaml
from pathlib import Path
from GitTools import cloneRepo
from FileUtils import directoryFromGitRepo, find_file
from NameTransformers import parseMkFile, parseVipkgReqsFile, sanitizeForPipelineName
from PipelineGenerationUtils import generateMaterials, generateFetchPPLJob
from Constants import profileId, Target, create_ppl_dir


def create_home_link_task(target):
    targetPathEnd = (
        "cRIO-9045\\Release_32\\home"
        if target == Target.cRIO_Release
        else "cRIO-9045\\Debug_32\\home" if target == Target.cRIO_Debug else None
    )
    linkRelPath = "PPLs\\cRIO-9045\\home"
    return {
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
                linkRelPath,
                "-Target",
                f'\\"C:\\LabVIEW Sources\\PPLs\\{targetPathEnd}\\"',
            ],
        }
    }


cachedMaterials = {}


class PipelineDefinition_RTapp(yaml.YAMLObject):
    yaml_tag = "!PipelineDefinition"

    def __init__(self, pipelineEntry):
        [name, values] = list(pipelineEntry.items())[0]
        self.name = name
        self.gitUrl = values["gitUrl"]
        self.dependencies = values["Dependencies"]
        self.dependencyPPLNames = values["Dependency PPL Names"]
        self.minVersion = values["minLabVIEWVersion"]
        self.vipkgUrls = values["vipkgUrls"]

    def buildData(self, dumper):
        targetName = "cRIO_Debug"
        gitDirName = directoryFromGitRepo(self.gitUrl, None)
        materials = generateMaterials(self.gitUrl, self.dependencies, cachedMaterials)
        dependencyQuotedList = '"' + '" "'.join(self.dependencyPPLNames) + '"'
        pplDepTasks = [
            generateFetchPPLJob(dependency, targetName)
            for dependency in self.dependencies
        ]

        if self.minVersion != None:
            lv_version = self.minVersion
        else:
            lv_version = "2019"

        return {
            "group": "defaultGroup",
            "parameters": {
                "GIT_DIR": gitDirName,
                "LV_VERSION": lv_version,
                "Dependency_PPL_Names": dependencyQuotedList,
                "APP_NAME": "TC_cRIO_Application",
            },
            "materials": materials,
            "stages": [
                {
                    "build": {
                        "fetch_materials": "yes",
                        "clean_workspace": "yes",
                        "approval": "manual",  # Set to "manual" to prevent auto-scheduling, "success" to allow autotriggering
                        # Git material is set not to autoupdate, so this controls if pipelines are triggered by PPL dependencies
                        "jobs": {
                            "build_debug": {
                                "timeout": 15,
                                "elastic_profile_id": profileId[lv_version][
                                    Target.cRIO_Debug
                                ],
                                "environment_variables": {
                                    "IS_DEBUG_BUILD": 1,
                                    # "TARGET_SYSTEM": "cRIO",
                                    "BUILD_TYPE": "BUILD",  # Overwritten elsewhere
                                },
                                "artifacts": [
                                    {
                                        "build": {
                                            "source": "builds/cRIO-9045-RT",
                                            "destination": "#{APP_NAME}",
                                        }
                                    }
                                ],
                                "tasks": [
                                    create_ppl_dir,
                                ]
                                + pplDepTasks
                                + [
                                    create_home_link_task(Target.cRIO_Debug),
                                    {
                                        "exec": {
                                            "run_if": "passed",
                                            "command": "LabVIEWCLI.exe",
                                            "arguments": [
                                                "-OperationName",
                                                "ExecuteBuildSpec",
                                                "-Verbosity",
                                                "Detailed",
                                                "-ProjectPath",
                                                f'\\"C:\\LabVIEW Sources\\{gitDirName}\\cRIO-9045-RT.lvproj\\"',
                                                "-TargetName",
                                                "RT CompactRIO Target",
                                                "-BuildSpecName",
                                                "RT Main Application",
                                            ],
                                        }
                                    },
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

    # Read dependencies
    mkFilePath = find_file("cRIO-9045-RT.mk", outputDir)
    if mkFilePath is None:
        raise RuntimeError(
            f"Could not find cRIO-9045-RT.mk in cloned repository at {outputDir}"
        )
    depsNames = parseMkFile(mkFilePath, r"RT\+Main\+Application_Deps")
    depsList = list(map(sanitizeForPipelineName, depsNames))

    pipelineEntry = {
        "cRIO_RT_Main_Application_TC": {
            "gitUrl": gitUrl,
            "Dependencies": depsList,
            "Dependency PPL Names": depsNames,
            "minLabVIEWVersion": "2019",
            "vipkgUrls": None,
        }
    }

    # Build a list of objects describing each pipeline (just one)
    pipelineDefinitionContent = {
        "TC_cRIO_Application": PipelineDefinition_RTapp(pipelineEntry)
    }

    # Convert the list of pipelines into a YAML object
    yamlObject = buildYamlObject(pipelineDefinitionContent)
    # Write to file
    outputFilePath = "./cRIO_RT_Pipeline.gocd.yaml"
    with open(outputFilePath, "w") as outputFile:
        yaml.dump(yamlObject, outputFile, sort_keys=False, width=999999)
