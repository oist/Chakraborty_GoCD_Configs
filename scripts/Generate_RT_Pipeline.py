import os
import yaml
from pathlib import Path
from GitTools import cloneRepo
from FileUtils import directoryFromGitRepo, find_file
from NameTransformers import parseMkFile, parseVipkgReqsFile, sanitizeForPipelineName
from PipelineGenerationUtils import (
    generateMaterials,
    generateRTBuildJob,
    generateFetchPPLJob,
    generateFetchFPGAJob,
)
from Constants import (
    Target,
    labviewDir,
    rt_builder_git_dir,
    rt_builder_material,
    rt_version_stage,
    rt_publish_to_feed_stage,
    rt_deploy_stage,
)

cachedMaterials = {}
cachedBuildJobs = {}


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
        self.branch = values.get("branch", "master")
        self.prerelease_tag = values.get("prerelease_tag", "")

    def buildData(self, dumper):
        gitDirName = directoryFromGitRepo(self.gitUrl, None)
        materials = generateMaterials(
            self.gitUrl, self.dependencies, cachedMaterials, branch=self.branch
        )

        if self.minVersion != None:
            lv_version = self.minVersion
        else:
            lv_version = "2019"

        # Add builder repo material — provides LabVIEW_BuildTools/ VIs and scripts/.
        # ignore_for_scheduling / auto_update are False so the builder repo never
        # triggers a new pipeline run on its own.
        materials[rt_builder_git_dir] = rt_builder_material

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

        build_debug = generateRTBuildJob(
            lv_version,
            True,
            pplDepTasks_debug,
            vipkgTasks,
            self.fpga_suffix,
            cachedBuildJobs,
        )
        build_release = generateRTBuildJob(
            lv_version,
            False,
            pplDepTasks_release,
            vipkgTasks,
            self.fpga_suffix,
            cachedBuildJobs,
        )

        return {
            "group": "cRIO",
            "parameters": {
                "GIT_DIR": gitDirName,
                "LV_VERSION": lv_version,
                "Dependency_PPL_Names": dependencyQuotedList,
                "APP_NAME": "TC_cRIO_Application",
                "BASE_PACKAGE_NAME": "crio-9045-rt",
                "DEPLOY_BUILD_TYPE": "debug",  # Allowed values: "debug" or "release"
                # PRERELEASE_TAG: appended to the git tag with a hyphen when non-empty.
                # Set to e.g. "build-attempts" to produce RT-v1.2.3.4-build-attempts.
                "PRERELEASE_TAG": self.prerelease_tag,
                "TAG_PREFIX": "RT-v",  # Prefix for git tags that GitVersion will use to determine version numbers
                "MAIN_BRANCH": "master",
                "BUILD_NUMBER_OFFSET": "540",
            },
            "environment_variables": {
                "PACKAGE_SERVER_UPLOAD_USER": "pkgupload",
                "PACKAGE_SERVER_UPLOAD_KEY": "~/.ssh/id_rsa",
                "PACKAGE_SERVER_REFRESH_USER": "opkg-refresher",
                "PACKAGE_SERVER_REFRESH_KEY": "~/.ssh/id_ed25519_opkg_refresh",
                "PACKAGE_SERVER": "packages.chakraborty.lab",  # Hostname/IP of package archive server
            },
            "materials": materials,
            "stages": [
                # version stage: runs GitVersion on the Linux agent, publishes version.txt
                # as a build artifact before the Windows LabVIEW build jobs run.
                rt_version_stage,
                {
                    "build": {
                        "fetch_materials": "yes",
                        "clean_workspace": "yes",
                        "approval": "success",  # Set to "manual" to prevent auto-scheduling, "success" to allow autotriggering
                        # Git material is set not to autoupdate, so this controls if pipelines are triggered by PPL dependencies
                        "jobs": {
                            "build_debug": build_debug,
                            "build_release": build_release,
                        },
                    }
                },
                # Archive publishing stage (runs automatically after build succeeds)
                {"publish_to_archive": rt_publish_to_feed_stage},
                # Deployment stage (independent of publish_to_archive, requires manual approval)
                {"deploy": rt_deploy_stage},
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

    # Clone/update the cRIO repository once, then re-checkout per branch
    # while reading branch-specific dependency metadata.
    outputDir = directoryFromGitRepo(gitUrl, baseDir)
    forceUpdate = False
    cloneRepo(gitUrl, outputDir, forceUpdate, timeout=20)

    branches = {
        "TC_cRIO_Application": "master",
        "TC_cRIO_Application_build-attempts": "build-attempts",
        "TC_cRIO_Application_psu-switch": "psu-switch",
    }

    pipelineDefinitionContent = {}
    for pipeline_name, branch in branches.items():
        cloneRepo(gitUrl, outputDir, forceUpdate=False, timeout=20, branch=branch)

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

        pipelineDefinitionContent[pipeline_name] = PipelineDefinition_RTapp(
            {
                pipeline_name: {
                    "gitUrl": gitUrl,
                    "Dependencies": depsList,
                    "Dependency PPL Names": depsNames,
                    "minLabVIEWVersion": "2019",
                    "vipkgUrls": vipkgUrls,
                    "branch": branch,
                    # Switch to using the copied bitfiles rather than compiled ones
                    # Comment this to use the compilation pipelines
                    "fpga_suffix": "_noncompile",
                    "prerelease_tag": branch if branch != "master" else "",
                }
            }
        )

    # Convert the list of pipelines into a YAML object
    yamlObject = buildYamlObject(pipelineDefinitionContent)
    # Write to file
    outputFilePath = "./cRIO_RT_Pipelines.gocd.yaml"
    with open(outputFilePath, "w") as outputFile:
        yaml.dump(yamlObject, outputFile, sort_keys=False, width=999999)
