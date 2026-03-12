import os
import yaml
from pathlib import Path
from GitTools import cloneRepo
from FileUtils import directoryFromGitRepo, find_file
from NameTransformers import parseMkFile, parseVipkgReqsFile, sanitizeForPipelineName
from PipelineGenerationUtils import (
    generateMaterials,
    generateFetchPPLJob,
    generateFetchFPGAJob,
)
from Constants import (
    profileId,
    Target,
    labviewDir,
    create_ppl_dir,
    gcli_rt_build_task,
    ipkg_build_task_debug,
    ipkg_build_task_release,
    gci_recurse_1_task,
)


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
        self.fpga_suffix = values.get(
            "fpga_suffix", ""
        )  # Optional suffix for FPGA pipeline names

    def buildData(self, dumper):
        gitDirName = directoryFromGitRepo(self.gitUrl, None)
        materials = generateMaterials(
            self.gitUrl, self.dependencies, cachedMaterials, branch="build-attempts"
        )

        if self.minVersion != None:
            lv_version = self.minVersion
        else:
            lv_version = "2019"

        # Add FPGA pipeline materials
        # ignore_for_scheduling=False means this pipeline will automatically trigger
        # when the upstream FPGA pipelines complete successfully. Set to True if you
        # only want to use the FPGA artifacts without auto-triggering on FPGA changes.
        materials["cRIO_FPGA_Main_material"] = {
            "pipeline": f"cRIO_FPGA_Main{self.fpga_suffix}",
            "stage": "build_fpga",
            "ignore_for_scheduling": False,
        }
        materials["cRIO_FPGA_Expansion_material"] = {
            "pipeline": f"cRIO_FPGA_Expansion{self.fpga_suffix}",
            "stage": "build_fpga",
            "ignore_for_scheduling": False,
        }

        dependencyQuotedList = '"' + '" "'.join(self.dependencyPPLNames) + '"'
        # FPGA fetch tasks (same bitfiles for both debug and release)
        fpgaFetchTasks = [
            generateFetchFPGAJob(f"cRIO_FPGA_Main{self.fpga_suffix}"),
            generateFetchFPGAJob(f"cRIO_FPGA_Expansion{self.fpga_suffix}"),
        ]

        pplDepTasks_debug = [
            generateFetchPPLJob(dependency, "cRIO_Debug")
            for dependency in self.dependencies
        ]
        pplDepTasks_release = [
            generateFetchPPLJob(dependency, "cRIO_Release")
            for dependency in self.dependencies
        ]

        vipkgTasks = []
        vipkgPluginConfig = {
            "id": "jp.oist.chakraborty.vi-package-installer",
            "version": "0.1",
        }
        # VIPKG dependencies are the same for debug and release
        lvdir = labviewDir[lv_version][Target.cRIO_Debug]

        if self.vipkgUrls is not None:
            for vipkgUrl in self.vipkgUrls:
                vipkgTasks.append(
                    {
                        "plugin": {
                            "run_if": "passed",
                            "options": {
                                "Url": vipkgUrl,
                                "LabVIEWDirectory": lvdir,
                                "Verbose": False,
                            },
                            "configuration": vipkgPluginConfig,
                        }
                    }
                )

        return {
            "group": "cRIO",
            "parameters": {
                "GIT_DIR": gitDirName,
                "LV_VERSION": lv_version,
                "Dependency_PPL_Names": dependencyQuotedList,
                "APP_NAME": "TC_cRIO_Application",
                "BUILD_TYPE": "BUILD",  # Can be MAJOR, MINOR, PATCH, or BUILD
                "DEPLOY_BUILD_TYPE": "debug",  # Which build to deploy: "debug" or "release"
                "CRIO_HOST": "",  # Must be set when triggering deployment
                "CRIO_USER": "admin",  # Default SSH user for cRIO
                "PACKAGE_SERVER": "packageserver",  # Hostname/IP of package archive server
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
                                    "BUILD_TYPE": "#{BUILD_TYPE}",
                                },
                                "artifacts": [
                                    {
                                        "build": {
                                            "source": "builds/cRIO-9045-RT",
                                            "destination": "#{APP_NAME}",
                                        }
                                    }
                                ],
                                "tasks": fpgaFetchTasks
                                + [
                                    create_ppl_dir,
                                ]
                                + pplDepTasks_debug
                                + vipkgTasks
                                + [
                                    create_home_link_task(Target.cRIO_Debug),
                                    gcli_rt_build_task,
                                ],
                            },
                            "build_release": {
                                "timeout": 15,
                                "elastic_profile_id": profileId[lv_version][
                                    Target.cRIO_Release
                                ],
                                "environment_variables": {
                                    "IS_DEBUG_BUILD": 0,
                                    "BUILD_TYPE": "#{BUILD_TYPE}",
                                },
                                "artifacts": [
                                    {
                                        "build": {
                                            "source": "builds/cRIO-9045-RT",
                                            "destination": "#{APP_NAME}",
                                        }
                                    }
                                ],
                                "tasks": fpgaFetchTasks
                                + [
                                    create_ppl_dir,
                                ]
                                + pplDepTasks_release
                                + [
                                    create_home_link_task(Target.cRIO_Release),
                                    gci_recurse_1_task,
                                    gcli_rt_build_task,
                                ],
                            },
                        },
                    }
                },
                # Package build stage
                {
                    "build_packages": {
                        "fetch_materials": "no",
                        "clean_workspace": "no",
                        "approval": "success",
                        "jobs": {
                            "package_debug": {
                                "timeout": 10,
                                "elastic_profile_id": profileId[lv_version][
                                    Target.cRIO_Debug
                                ],
                                "artifacts": [
                                    {
                                        "build": {
                                            "source": "builds/packages/*.ipkg",
                                            "destination": "packages",
                                        }
                                    }
                                ],
                                "tasks": [
                                    {
                                        "fetch": {
                                            "run_if": "passed",
                                            "stage": "build",
                                            "job": "build_debug",
                                            "source": "#{APP_NAME}",
                                            "destination": "builds",
                                        }
                                    },
                                    ipkg_build_task_debug,
                                ],
                            },
                            "package_release": {
                                "timeout": 10,
                                "elastic_profile_id": profileId[lv_version][
                                    Target.cRIO_Release
                                ],
                                "artifacts": [
                                    {
                                        "build": {
                                            "source": "builds/packages/*.ipkg",
                                            "destination": "packages",
                                        }
                                    }
                                ],
                                "tasks": [
                                    {
                                        "fetch": {
                                            "run_if": "passed",
                                            "stage": "build",
                                            "job": "build_release",
                                            "source": "#{APP_NAME}",
                                            "destination": "builds",
                                        }
                                    },
                                    ipkg_build_task_release,
                                ],
                            },
                        },
                    }
                },
                # Archive publishing stage (runs automatically after build_packages succeeds)
                {
                    "publish_to_archive": {
                        "fetch_materials": "no",
                        "clean_workspace": "no",
                        "approval": "success",
                        "jobs": {
                            "publish_to_feed": {
                                "timeout": 5,
                                "environment_variables": {
                                    "PACKAGE_SERVER": "#{PACKAGE_SERVER}",
                                },
                                "tasks": [
                                    {
                                        "fetch": {
                                            "run_if": "passed",
                                            "stage": "build_packages",
                                            "job": "package_release",
                                            "source": "packages",
                                            "destination": "artifacts",
                                        }
                                    },
                                    {
                                        "exec": {
                                            "run_if": "passed",
                                            "command": "scp",
                                            "arguments": [
                                                "artifacts/packages/*.ipkg",
                                                "#{PACKAGE_SERVER}:/var/www/packages/",
                                            ],
                                        }
                                    },
                                    {
                                        "exec": {
                                            "run_if": "passed",
                                            "command": "ssh",
                                            "arguments": [
                                                "#{PACKAGE_SERVER}",
                                                "cd /var/www/packages && opkg-make-index . > Packages && gzip -c Packages > Packages.gz",
                                            ],
                                        }
                                    },
                                ],
                            }
                        },
                    }
                },
                # Deployment stage (independent of publish_to_archive, requires manual approval)
                {
                    "deploy": {
                        "fetch_materials": "no",
                        "clean_workspace": "no",
                        "approval": "manual",  # Manual approval before deployment
                        "jobs": {
                            "deploy_to_crio": {
                                "timeout": 5,
                                "environment_variables": {
                                    "CRIO_HOST": "#{CRIO_HOST}",
                                    "CRIO_USER": "#{CRIO_USER}",
                                },
                                "tasks": [
                                    {
                                        "fetch": {
                                            "run_if": "passed",
                                            "stage": "build_packages",
                                            "job": "package_#{DEPLOY_BUILD_TYPE}",
                                            "source": "packages",
                                            "destination": "artifacts",
                                        }
                                    },
                                    {
                                        "exec": {
                                            "run_if": "passed",
                                            "command": "sshpass",
                                            "arguments": [
                                                "-p",
                                                "{{SECRET:[secrets.json][crio_ssh_password]}}",
                                                "scp",
                                                "-o",
                                                "StrictHostKeyChecking=no",
                                                "artifacts/packages/*.ipkg",
                                                "#{CRIO_USER}@#{CRIO_HOST}:/tmp/",
                                            ],
                                        }
                                    },
                                    {
                                        "exec": {
                                            "run_if": "passed",
                                            "command": "sshpass",
                                            "arguments": [
                                                "-p",
                                                "{{SECRET:[secrets.json][crio_ssh_password]}}",
                                                "ssh",
                                                "-o",
                                                "StrictHostKeyChecking=no",
                                                "#{CRIO_USER}@#{CRIO_HOST}",
                                                "opkg remove tc-crio-app || true; opkg install /tmp/*.ipkg",
                                            ],
                                        }
                                    },
                                    {
                                        "exec": {
                                            "run_if": "passed",
                                            "command": "sshpass",
                                            "arguments": [
                                                "-p",
                                                "{{SECRET:[secrets.json][crio_ssh_password]}}",
                                                "ssh",
                                                "-o",
                                                "StrictHostKeyChecking=no",
                                                "#{CRIO_USER}@#{CRIO_HOST}",
                                                "/etc/init.d/niapp restart || systemctl restart niapp",
                                            ],
                                        }
                                    },
                                ],
                            }
                        },
                    }
                },
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

    vipkgReqsPath = find_file("cRIO-9045-RT.vipm_reqs", outputDir)
    vipkgUrls = None
    if vipkgReqsPath != None:
        vipkgUrls = parseVipkgReqsFile(vipkgReqsPath)

    pipelineEntry = {
        "cRIO_RT_Main_Application_TC": {
            "gitUrl": gitUrl,
            "Dependencies": depsList,
            "Dependency PPL Names": depsNames,
            "minLabVIEWVersion": "2019",
            "vipkgUrls": vipkgUrls,
            # Switch to using the copied bitfiles rather than compiled ones
            # Comment this to use the compilation pipelines
            "fpga_suffix": "_noncompile",
        }
    }

    # Build a list of objects describing each pipeline (just one)
    pipelineDefinitionContent = {
        "TC_cRIO_Application": PipelineDefinition_RTapp(pipelineEntry)
    }

    # Convert the list of pipelines into a YAML object
    yamlObject = buildYamlObject(pipelineDefinitionContent)
    # Write to file
    outputFilePath = "./cRIO_RT_Pipelines.gocd.yaml"
    with open(outputFilePath, "w") as outputFile:
        yaml.dump(yamlObject, outputFile, sort_keys=False, width=999999)
