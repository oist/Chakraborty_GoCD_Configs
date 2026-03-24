from enum import Enum

# Simple constants
via_plugin_version = "0.2.2.3"

# Names defined in the Zip_PPL_Builder config file
zipPipelineName = "Zip_PPL_Builder"
zipPipelineStageName = "Zip"
zipPipelineJobName = "Zip"

builderMaterial = {
    "pipeline": zipPipelineName,
    "stage": zipPipelineStageName,
    "ignore_for_scheduling": True,
}

# Git material for the Chakraborty_cRIO-Builder repository.
# Contains LabVIEW build VIs (LabVIEW_BuildTools/) and CI bash scripts (scripts/).
# ignore_for_scheduling=True / auto_update=False: changes to the builder repo do not
# trigger new pipeline runs. Scripts are published as build artifacts from the version
# stage so that publish_to_archive and deploy stages (fetch_materials=no) can access
# them via GoCD fetch tasks without re-checking out all git materials.
rt_builder_git_dir = "Chakraborty_cRIO-Builder"
rt_builder_material = {
    "git": "git@github.com:oist/Chakraborty_cRIO-Builder",
    "destination": rt_builder_git_dir,
    "auto_update": False,
    "shallow_clone": True,
    "branch": "main",
}


class Target(Enum):
    Windows_32_Release = 0
    Windows_32_Debug = 1
    Windows_64_Release = 2
    Windows_64_Debug = 3
    cRIO_Release = 4
    cRIO_Debug = 5
    FPGA_Release = 6
    FPGA_Debug = 7


# The names here are used for the G-CLI call directly.
class BuildType(Enum):
    MAJOR = 0
    MINOR = 1
    PATCH = 2
    BUILD = 3


targetPathEnds = {
    "Windows_32_Release": "Windows\\Release_32",
    "Windows_32_Debug": "Windows\\Debug_32",
    "Windows_64_Release": "Windows\\Release_64",
    "Windows_64_Debug": "Windows\\Debug_64",
    "cRIO_Release": "cRIO-9045\\Release_32\\home\\lvuser\\natinst\\bin",
    "cRIO_Debug": "cRIO-9045\\Debug_32\\home\\lvuser\\natinst\\bin",
    "cRIO_Release": "cRIO-9045\\Release_32\\home\\lvuser\\natinst\\bin",
    "cRIO_Debug": "cRIO-9045\\Debug_32\\home\\lvuser\\natinst\\bin",
    "FPGA_Release": "cRIO-9045\\Release_32\\home\\lvuser\\natinst\\bin",
    "FPGA_Debug": "cRIO-9045\\Debug_32\\home\\lvuser\\natinst\\bin",
}

profileId = {
    "2019": {
        Target.Windows_32_Debug: "labview_2019_x86",
        Target.Windows_32_Release: "labview_2019_x86",
        Target.Windows_64_Debug: "labview_2019_x64",
        Target.Windows_64_Release: "labview_2019_x64",
        Target.cRIO_Debug: "labview_2019_x86_crio",
        Target.cRIO_Release: "labview_2019_x86_crio",
        Target.FPGA_Debug: "labview_2019_x86_fpga",
        Target.FPGA_Release: "labview_2019_x86_fpga",
    },
    "2021": {
        Target.Windows_32_Debug: "labview_2021_x86",
        Target.Windows_32_Release: "labview_2021_x86",
        Target.Windows_64_Debug: "labview_2021_x64",
        Target.Windows_64_Release: "labview_2021_x64",
        Target.cRIO_Debug: "labview_2021_x86_crio",
        Target.cRIO_Release: "labview_2021_x86_crio",
        Target.FPGA_Debug: "labview_2021_x86_fpga",
        Target.FPGA_Release: "labview_2021_x86_fpga",
    },
}

labviewDir = {
    "2019": {
        Target.Windows_32_Debug: "C:\\Program Files (x86)\\National Instruments\\LabVIEW 2019",
        Target.Windows_32_Release: "C:\\Program Files (x86)\\National Instruments\\LabVIEW 2019",
        Target.Windows_64_Debug: "C:\\Program Files\\National Instruments\\LabVIEW 2019",
        Target.Windows_64_Release: "C:\\Program Files\\National Instruments\\LabVIEW 2019",
        Target.cRIO_Debug: "C:\\Program Files (x86)\\National Instruments\\LabVIEW 2019",
        Target.cRIO_Release: "C:\\Program Files (x86)\\National Instruments\\LabVIEW 2019",
        Target.FPGA_Debug: "C:\\Program Files (x86)\\National Instruments\\LabVIEW 2019",
        Target.FPGA_Release: "C:\\Program Files (x86)\\National Instruments\\LabVIEW 2019",
    },
    "2021": {
        Target.Windows_32_Debug: "C:\\Program Files (x86)\\National Instruments\\LabVIEW 2021",
        Target.Windows_32_Release: "C:\\Program Files (x86)\\National Instruments\\LabVIEW 2021",
        Target.Windows_64_Debug: "C:\\Program Files\\National Instruments\\LabVIEW 2021",
        Target.Windows_64_Release: "C:\\Program Files\\National Instruments\\LabVIEW 2021",
        Target.cRIO_Debug: "C:\\Program Files (x86)\\National Instruments\\LabVIEW 2021",
        Target.cRIO_Release: "C:\\Program Files (x86)\\National Instruments\\LabVIEW 2021",
        Target.FPGA_Debug: "C:\\Program Files (x86)\\National Instruments\\LabVIEW 2021",
        Target.FPGA_Release: "C:\\Program Files (x86)\\National Instruments\\LabVIEW 2021",
    },
}

# -- Configuration for the NIPKG Fetch Artifact step -- #
# DownloadOrInstall
# --
# SuppressIncompatibilityErrors
# AllowUpgrade (default on)
# AllowDowngrade
# AllowUninstallation
# InstallRecommended
# InstallRootDir (only applies to packages with "Plugin: relative-file" attribute)
# --
# DownloadDestDir
# DownloadIncludeDeps
# DownloadSkipDependenciesCheck
fetch_ppl_configuration = {
    "options": {
        "DownloadOrInstall": "Install",
        "SuppressIncompatibilityErrors": False,
        "AllowUpgrade": True,
        "AllowDowngrade": True,
        "AllowUninstallation": False,
        "InstallRecommended": False,
        "InstallRootDir": None,
    }
}

# ------------------- Jobs ---------------------------- #
dir_job = {"tasks": [{"exec": {"command": "dir", "arguments": ["*"]}}]}

via_job = {
    "environment_variables": {"PROJECT_TITLE": "#{PPL_Name}"},
    "timeout": 3,
    "tabs": {
        "VIA_Results": "#{PPL_Name}/viaResultsCheckstyle.xml",
        "VIA_Report": "#{PPL_Name}/CheckstyleReport.html",
    },
    "artifacts": [
        # Checkstyle xml generated by LabVIEW code
        {
            "build": {
                "source": "#{GIT_DIR}/viaResultsCheckstyle.xml",
                "destination": "#{PPL_Name}",
            }
        },
        # Report generated by plugin - the main tab for this job
        {"build": {"source": "CheckstyleReport.html", "destination": "#{PPL_Name}"}},
        # The raw VIA results (could remove)
        {
            "build": {
                "source": "#{GIT_DIR}/viaResults.xml",
                "destination": "#{PPL_Name}",
            }
        },
    ],
    "tasks": [
        {
            "exec": {
                "run_if": "passed",
                "command": "g-cli",
                "working_directory": "#{GIT_DIR}",
                "arguments": [
                    "--verbose",
                    "--lv-ver",
                    "#{LV_VERSION}",
                    "viaRunner.vi",
                    "--",
                    "viaResults.xml",
                ],
            }
        },
        {
            "plugin": {
                "configuration": {
                    "id": "Checkstyle.LabVIEW.VIA",
                    "version": via_plugin_version,
                },
                "run_if": "passed",
                "options": {
                    "SourceVIAFile": "#{GIT_DIR}/viaResults.xml",
                    "SourceCheckstyleFile": "#{GIT_DIR}/viaResultsCheckstyle.xml",
                    "DestinationFile": "CheckstyleReport.html",
                    "AddEmpty": False,
                },
            }
        },
    ],
}

# ------------------- Tasks --------------------------- #
create_ppl_dir = {
    "exec": {
        "run_if": "passed",
        "command": "powershell",
        "arguments": [
            "-Command",
            "New-Item",
            "-Force",
            "-ItemType",
            "Directory",
            "-Path",
            '\\"C:\\LabVIEW Sources\\PPLs\\"',
        ],
    }
}

ls_task = {"exec": {"run_if": "passed", "command": "ls", "arguments": ["*"]}}

# Note that adding a '*' to the end here causes an error
# This seems to be due to the execution via Invoke-Expression and the $RUN_CMD variable in the elastic agent.
ls_currentDir_task = {
    "exec": {"run_if": "passed", "command": "ls", "arguments": ["PPLs\\\\Current"]}
}

gci_recurse_1_task = {
    "exec": {
        "run_if": "passed",
        "command": "powershell",
        "arguments": [
            "-Command",
            "Get-ChildItem",
            "-Recurse",
            "-Depth",
            "1",
        ],
    }
}

gci_recurse_task = {
    "exec": {
        "run_if": "passed",
        "command": "powershell",
        "arguments": ["-Command", "Get-ChildItem", "-Recurse"],
    }
}

find_files_task = {
    "exec": {
        "run_if": "any",
        "command": "find",
        "arguments": [".", "-type", "f"],
    }
}

fetch_builder_task = {
    "fetch": {
        "run_if": "passed",
        "pipeline": zipPipelineName,
        "stage": zipPipelineStageName,
        "job": zipPipelineJobName,
        "source": "PPL_Builder/PPL_Builder.zip",
        "destination": ".",
        "is_file": "yes",
    }
}

expand_builder_task = {
    "exec": {
        "run_if": "passed",
        "command": "powershell",
        "arguments": [
            "-Command",
            "Expand-Archive",
            "-Path",
            "PPL_Builder.zip",
            "-DestinationPath",
            ".",
        ],
    }
}

gcli_build_task = {
    "exec": {
        "run_if": "passed",
        "command": "g-cli",
        "arguments": [
            "--lv-ver",
            "#{LV_VERSION}",
            "%BITNESS_FLAG%",
            "PPL_Builder\\Call_Builder_Wiresmith.vi",  # This must be a backward slash
            "--",
            "#{PPL_LIB_PATH}",
            "PPLs/Current",
            "%IS_DEBUG_BUILD%",
            "%TARGET_SYSTEM%",
            "%BUILD_TYPE%",
            "#{Dependency_PPL_Names}",
        ],
    }
}

# Fetch task inserted into build_debug and build_release jobs to make
# the version.txt artifact (produced by the version stage) available to
# the LabVIEW build VI at #{GIT_DIR}\version\version.txt.
rt_version_fetch_task = {
    "fetch": {
        "run_if": "passed",
        "stage": "version",
        "job": "compute_version",
        "source": "version/version.txt",
        "destination": "#{GIT_DIR}\\version",
        "is_file": True,
    }
}

# Linux-agent stage that runs GitVersion + jq, writes MAJOR.MINOR.PATCH.BUILD
# to version.txt, and publishes it as a GoCD build artifact.
# Must be listed before the `build` stage in the pipeline's stages list.
rt_version_stage = {
    "version": {
        "fetch_materials": "yes",
        "clean_workspace": "yes",
        "approval": "manual",  # Set to "manual" to prevent auto-scheduling, "success" to allow autotriggering
        "jobs": {
            "compute_version": {
                # Agent must carry both the "jq" and "gitversion" resource tags.
                "resources": ["linux", "jq", "gitversion"],
                "timeout": 5,
                "artifacts": [
                    {
                        "build": {
                            "source": "version.txt",
                            "destination": "version/",
                        }
                    },
                    {
                        # Publish build scripts so publish_to_archive and deploy stages
                        # (fetch_materials=no) can access them via GoCD fetch tasks.
                        "build": {
                            "source": "Chakraborty_cRIO-Builder/scripts/*.sh",
                            "destination": "builder_scripts",
                        }
                    },
                ],
                "tasks": [
                    {
                        "exec": {
                            "run_if": "passed",
                            "command": "bash",
                            "arguments": [
                                "-lc",
                                # Delegate to compute_version.sh in the builder repo material.
                                # Produces version.json and version.txt in the agent workdir.
                                "bash Chakraborty_cRIO-Builder/scripts/compute_version.sh '#{GIT_DIR}' '#{TAG_PREFIX}'",
                            ],
                        }
                    }
                ],
            }
        },
    }
}

rt_publish_to_feed_stage = {
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
                        "stage": "version",
                        "job": "compute_version",
                        "source": "version/version.txt",
                        "destination": "version",
                        "is_file": True,
                    }
                },
                {
                    # Fetch CI scripts published as artifacts by the version stage.
                    "fetch": {
                        "run_if": "passed",
                        "stage": "version",
                        "job": "compute_version",
                        "source": "builder_scripts",
                        "is_file": False,
                        "destination": ".",
                    }
                },
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
                                # version.txt contains MAJOR.MINOR.PATCH.BUILD (all dots)
                                'BUILD_VER="$(cat version/version.txt)"; '
                                # PRERELEASE_TAG appended with a hyphen when non-empty
                                # (e.g. "build-attempts" → RT-v1.2.3.456-build-attempts)
                                "PT='#{PRERELEASE_TAG}'; "
                                'TAG="RT-v${BUILD_VER}${PT:+-${PT}}"; '
                                'REPO_URL="${GO_MATERIAL_URL_CHAKRABORTY_CRIO:?GO_MATERIAL_URL_CHAKRABORTY_CRIO is required}"; '
                                'REV="${GO_REVISION_CHAKRABORTY_CRIO:?GO_REVISION_CHAKRABORTY_CRIO is required}"; '
                                # Delegate git init/fetch/tag/push to the extracted script
                                'bash builder_scripts/tag_rt_release.sh "$REPO_URL" "$REV" "$TAG"'
                            ),
                        ],
                    }
                },
            ],
        }
    },
}

rt_deploy_stage = {
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
                        "stage": "version",
                        "job": "compute_version",
                        "source": "version/version.txt",
                        "destination": "version",
                        "is_file": True,
                    }
                },
                {
                    # Fetch CI scripts published as artifacts by the version stage.
                    "fetch": {
                        "run_if": "passed",
                        "stage": "version",
                        "job": "compute_version",
                        "source": "builder_scripts",
                        "is_file": False,
                        "destination": ".",
                    }
                },
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
                                "set -euo pipefail; "
                                # version.txt contains MAJOR.MINOR.PATCH.BUILD (all dots);
                                # convert last dot to hyphen for opkg's MAJOR.MINOR.PATCH-BUILD format.
                                'BUILD_VER="$(cat version/version.txt)"; '
                                "OPKG_VER=\"$(printf '%s' \"$BUILD_VER\" | sed 's/\\.\\([^.]*\\)$/-\\1/')\"; "
                                # Extract package name by stripping _VERSION_BUILDTYPE suffix from IPK filename.
                                'IPK="$(ls -1 artifacts/*.ipk | head -n1)"; '
                                'BASE="$(basename "$IPK" .ipk)"; '
                                "PKG_NAME=\"$(printf '%s\\n' \"$BASE\" | sed -E 's/_[^_]*_[^_]*$//')\"; "
                                'echo "Deploying ${PKG_NAME}=${OPKG_VER} from feed"; '
                                # Inject password from GoCD secret as env var for deploy_crio.sh
                                "export CRIO_SSH_PASSWORD='{{SECRET:[secrets.json][crio_ssh_password]}}'; "
                                'bash builder_scripts/deploy_crio.sh "${CRIO_HOST}" "${CRIO_USER}" "${PKG_NAME}" "${OPKG_VER}"'
                            ),
                        ],
                    }
                },
            ],
        }
    },
}

# ------------------- FPGA Build Tasks -------------------- #
fpga_build_task = {
    "exec": {
        "run_if": "passed",
        "command": "LabVIEWCLI.exe",
        "arguments": [
            "-OperationName",
            "ExecuteBuildSpec",
            "-Verbosity",
            "Detailed",
            "-ProjectPath",
            '"$PWD\\#{PROJECT_PATH}"',
            "-TargetName",
            "#{FPGA_TARGET_NAME}",
            "-BuildSpecName",
            "#{FPGA_BUILDSPEC_NAME}",
        ],
    }
}

fpga_artifact_path = "FPGA Bitfiles/*.lvbitx"

script_fpga_version_task = {
    "exec": {
        "run_if": "passed",
        "command": "g-cli",
        "arguments": [
            "--lv-ver",
            "#{LV_VERSION}",
            "--verbose",
            "Builder\\Script_FPGA_Version_VI_Wrapper.vi",
            "--",
            "#{VERSION_VI_PATH}",
        ],
        "working_directory": "#{GIT_DIR}",
    }
}

# ------------------- RT Build with G-CLI ----------------- #
gcli_rt_build_task = {
    "exec": {
        "run_if": "passed",
        "command": "g-cli",
        "arguments": [
            "--lv-ver",
            "#{LV_VERSION}",
            "--verbose",
            f"{rt_builder_git_dir}\\LabVIEW_BuildTools\\RT\\Build_RT_Application.vi",
            "--",
            "cRIO-9045-RT.lvproj",
            "RT CompactRIO Target",
            "RT Main Application",
            "%BUILD_TYPE%",
            "%IS_DEBUG_BUILD%",
            "#{PRERELEASE_TAG}",
            "#{Dependency_PPL_Names}",
        ],
    }
}
