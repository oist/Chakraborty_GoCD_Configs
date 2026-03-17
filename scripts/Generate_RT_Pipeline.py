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
    gci_recurse_1_task,
    find_files_task,
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
            self.gitUrl, self.dependencies, cachedMaterials, branch="master"
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

        sharedInitialTasks = fpgaFetchTasks + [create_ppl_dir]
        sharedPostTasks = vipkgTasks + [gci_recurse_1_task, gcli_rt_build_task]

        return {
            "group": "cRIO",
            "parameters": {
                "GIT_DIR": gitDirName,
                "LV_VERSION": lv_version,
                "Dependency_PPL_Names": dependencyQuotedList,
                "APP_NAME": "TC_cRIO_Application",
                "DEPLOY_BUILD_TYPE": "debug",  # Which build to deploy: "debug" or "release"
            },
            "environment_variables": {
                "BUILD_TYPE": "BUILD",  # Can be MAJOR, MINOR, PATCH, or BUILD
                "CRIO_HOST": "",  # Must be set when triggering deployment
                "CRIO_USER": "admin",  # Default SSH user for cRIO
                "PACKAGE_SERVER_UPLOAD_USER": "pkgupload",
                "PACKAGE_SERVER_UPLOAD_KEY": "~/.ssh/id_rsa",
                "PACKAGE_SERVER_REFRESH_USER": "opkg-refresher",
                "PACKAGE_SERVER_REFRESH_KEY": "~/.ssh/id_ed25519_opkg_refresh",
                "PACKAGE_SERVER": "packages.chakraborty.lab",  # Hostname/IP of package archive server
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
                                },
                                "artifacts": [
                                    {
                                        "build": {
                                            "source": "#{GIT_DIR}\\builds\\RT-Package-Debug\\*",
                                            "destination": "#{APP_NAME}_debug",
                                        }
                                    }
                                ],
                                "tasks": sharedInitialTasks
                                + pplDepTasks_debug
                                + [
                                    create_home_link_task(Target.cRIO_Debug),
                                ]
                                + sharedPostTasks,
                            },
                            "build_release": {
                                "timeout": 15,
                                "elastic_profile_id": profileId[lv_version][
                                    Target.cRIO_Release
                                ],
                                "environment_variables": {
                                    "IS_DEBUG_BUILD": 0,
                                },
                                "artifacts": [
                                    {
                                        "build": {
                                            "source": "#{GIT_DIR}\\builds\\RT-Package-Release\\*",
                                            "destination": "#{APP_NAME}_release",
                                        }
                                    }
                                ],
                                "tasks": sharedInitialTasks
                                + pplDepTasks_release
                                + [
                                    create_home_link_task(Target.cRIO_Release),
                                ]
                                + sharedPostTasks,
                            },
                        },
                    }
                },
                # Archive publishing stage (runs automatically after build succeeds)
                {
                    "publish_to_archive": {
                        "fetch_materials": "no",
                        "clean_workspace": "yes",
                        "approval": "success",
                        "jobs": {
                            "publish_to_feed": {
                                "resources": ["linux"],
                                "timeout": 5,
                                "tasks": [
                                    {
                                        "fetch": {
                                            "run_if": "passed",
                                            "stage": "build",
                                            "job": "build_debug",
                                            "source": "#{APP_NAME}_debug",
                                            "is_file": False,
                                            "destination": "artifacts",
                                        }
                                    },
                                    {
                                        "fetch": {
                                            "run_if": "passed",
                                            "stage": "build",
                                            "job": "build_release",
                                            "source": "#{APP_NAME}_release",
                                            "is_file": False,
                                            "destination": "artifacts",
                                        }
                                    },
                                    find_files_task,
                                    {
                                        "exec": {
                                            "run_if": "passed",
                                            "command": "bash",
                                            "arguments": [
                                                "-lc",
                                                # /packages (not e.g. /var/www/pkgupload/packages) because the user is chrooted.
                                                (
                                                    "scp -i ${PACKAGE_SERVER_UPLOAD_KEY} "
                                                    "artifacts/#{APP_NAME}_*/*.ipk "
                                                    "${PACKAGE_SERVER_UPLOAD_USER}@${PACKAGE_SERVER}:/packages/"
                                                ),
                                            ],
                                        }
                                    },
                                    {
                                        "exec": {
                                            "run_if": "passed",
                                            "command": "bash",
                                            "arguments": [
                                                "-lc",
                                                (
                                                    "ssh -Ti ${PACKAGE_SERVER_REFRESH_KEY} "
                                                    "${PACKAGE_SERVER_REFRESH_USER}@${PACKAGE_SERVER}"
                                                ),
                                                # No need for a command - the user is bound to a single command which will execute on connection.
                                            ],
                                        }
                                    },
                                    {
                                        "exec": {
                                            "run_if": "passed",
                                            "command": "bash",
                                            "arguments": [
                                                "-lc",
                                                (
                                                    "set -euo pipefail; "
                                                    'IPK="$(ls -1 artifacts/#{APP_NAME}_release/*.ipk | head -n1)"; '
                                                    'BASE="$(basename "$IPK" .ipk)"; '
                                                    "BUILD_VER_RAW=\"$(printf '%s\\n' \"$BASE\" | sed -E 's/^.*_([^_]*)_[^_]*$/\\1/')\"; "
                                                    "BUILD_VER=\"$(printf '%s\\n' \"$BUILD_VER_RAW\" | sed -E 's/^(.*)-([^-]+)$/\\1.\\2/')\"; "
                                                    'TAG="RT-v${BUILD_VER}"; '
                                                    'REPO_URL="${GO_MATERIAL_URL_CHAKRABORTY_CRIO:?GO_MATERIAL_URL_CHAKRABORTY_CRIO is required}"; '
                                                    'REV="${GO_REVISION_CHAKRABORTY_CRIO:?GO_REVISION_CHAKRABORTY_CRIO is required}"; '
                                                    'WORKDIR="$(mktemp -d)"; '
                                                    'trap "rm -rf ${WORKDIR}" EXIT; '
                                                    'git -C "$WORKDIR" init -q; '
                                                    'git -C "$WORKDIR" remote add origin "$REPO_URL"; '
                                                    'git -C "$WORKDIR" fetch --depth=1 origin "$REV"; '
                                                    'git -C "$WORKDIR" tag -a "$TAG" "$REV" -m "RT build $TAG"; '
                                                    'git -C "$WORKDIR" push origin "$TAG"'
                                                ),
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
                        "clean_workspace": "yes",
                        "approval": "manual",  # Manual approval before deployment
                        "jobs": {
                            "deploy_to_crio": {
                                "resources": ["linux"],
                                "timeout": 5,
                                "tasks": [
                                    {
                                        "fetch": {
                                            "run_if": "passed",
                                            "stage": "build",
                                            "job": "build_#{DEPLOY_BUILD_TYPE}",
                                            "source": "#{APP_NAME}_#{DEPLOY_BUILD_TYPE}",
                                            "destination": "artifacts",
                                        }
                                    },
                                    find_files_task,
                                    {
                                        "exec": {
                                            "run_if": "passed",
                                            "command": "bash",
                                            "arguments": [
                                                "-lc",
                                                (
                                                    'IPK="$(ls -1 artifacts/*.ipk | head -n1)"; '
                                                    'BASE="$(basename "$IPK" .ipk)"; '
                                                    "PKG_NAME=\"$(printf '%s\\n' \"$BASE\" | sed -E 's/_[^_]*_[^_]*$//')\"; "
                                                    "PKG_VER=\"$(printf '%s\\n' \"$BASE\" | sed -E 's/^.*_([^_]*)_[^_]*$/\\1/')\"; "
                                                    'echo "Deploying ${PKG_NAME}=${PKG_VER} from feed"; '
                                                    'sshpass -p "{{SECRET:[secrets.json][crio_ssh_password]}}" '
                                                    "ssh -o StrictHostKeyChecking=no ${CRIO_USER}@${CRIO_HOST} "
                                                    '"opkg update && opkg remove ${PKG_NAME} || true; opkg install ${PKG_NAME}=${PKG_VER}"'
                                                ),
                                            ],
                                        }
                                    },
                                    {
                                        "exec": {
                                            # This may need redirection through bash to correctly set the CRIO_USER and CRIO_HOST
                                            "run_if": "passed",
                                            "command": "sshpass",
                                            "arguments": [
                                                "-p",
                                                "{{SECRET:[secrets.json][crio_ssh_password]}}",
                                                "ssh",
                                                "-o",
                                                "StrictHostKeyChecking=no",
                                                "${CRIO_USER}@${CRIO_HOST}",
                                                "reboot",
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
