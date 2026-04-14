import json

from FileUtils import directoryFromGitRepo
from Constants import (
    Target,
    fetch_ppl_configuration,
    profileId,
    create_ppl_dir,
    gcli_rt_build_task,
    gci_recurse_1_task,
    rt_version_fetch_task,
)


def getPackageRootName(pipelineName):
    return pipelineName.replace(".lvlibp", "")


def generateMaterials(gitUrl, dependencies, cachedMaterials, branch=None):
    topDir = directoryFromGitRepo(gitUrl, None)
    materials = {
        topDir: {
            "git": gitUrl,
            "destination": topDir,
            "auto_update": False,
            "shallow_clone": False,
            "branch": branch if branch else "master",
        }
    }
    if dependencies is not None:
        for dep in dependencies:
            materialName = dep + "_pipelineMaterial"
            if not materialName in cachedMaterials:
                cachedMaterials[materialName] = {
                    "pipeline": dep,
                    "stage": "build_ppls",
                    "ignore_for_scheduling": False,
                }
            materials[materialName] = cachedMaterials.get(materialName)
    return materials


def generateRTBuildJob(
    lv_version, isDebug, pplTasks, vipkgTasks, fpgaSuffix, cachedBuildJobs=None
):

    # FPGA fetch tasks (same bitfiles for both debug and release)
    fpgaFetchTasks = [
        generateFetchFPGAJob(f"cRIO_FPGA_Main{fpgaSuffix}"),
        generateFetchFPGAJob(f"cRIO_FPGA_Expansion{fpgaSuffix}"),
    ]

    initialTasks = fpgaFetchTasks + [create_ppl_dir]
    postTasks = vipkgTasks + [
        rt_version_fetch_task,
        gci_recurse_1_task,
        gcli_rt_build_task,
    ]

    target = Target.FPGA_Debug if isDebug else Target.FPGA_Release
    sourceDir = (
        "#{GIT_DIR}\\builds\\RT-Package-Debug"
        if isDebug
        else "#{GIT_DIR}\\builds\\RT-Package-Release"
    )
    buildJob = {
        "timeout": 15,
        "elastic_profile_id": profileId[lv_version][target],
        "environment_variables": {
            "IS_DEBUG_BUILD": 1 if isDebug else 0,
        },
        "artifacts": [
            {
                "build": {
                    "source": f"{sourceDir}\\*",
                    "destination": (
                        "#{APP_NAME}_" + ("debug" if isDebug else "release")
                    ),
                }
            }
        ],
        "tasks": initialTasks
        + pplTasks
        + [
            create_home_link_task(target),
        ]
        + postTasks,
    }

    if cachedBuildJobs is None:
        return buildJob

    # Alias jobs only when the full rendered content is identical.
    jobSignature = json.dumps(buildJob, sort_keys=True, separators=(",", ":"))
    if jobSignature not in cachedBuildJobs:
        cachedBuildJobs[jobSignature] = buildJob

    return cachedBuildJobs[jobSignature]


def create_home_link_task(target):
    targetPathEnd = (
        "cRIO-9045\\Release_32\\home"
        if target == Target.FPGA_Release
        else "cRIO-9045\\Debug_32\\home" if target == Target.FPGA_Debug else None
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


def generateFetchPPLJob(dependency, targetName):
    dependencyRootName = getPackageRootName(dependency)
    packageId = f"{dependencyRootName}_{targetName}_nipkg"
    return {
        "fetch": {
            "run_if": "passed",
            "artifact_origin": "external",
            "pipeline": dependency,
            "stage": "build_ppls",
            "job": targetName,
            "artifact_id": packageId,
            "configuration": fetch_ppl_configuration,
        }
    }


def generateFetchFPGAJob(fpga_pipeline_name):
    """Generate fetch task for FPGA bitfile from FPGA pipeline.

    Fetches the "FPGA Bitfiles" directory (is_file=False) rather than a specific
    file to avoid hardcoding the bitfile name with its hash suffix. Each FPGA
    pipeline produces only a single .lvbitx file in this directory, but the exact
    filename includes a generated hash (e.g., cR9045-FPGAMain_tiGh-z7G0kw.lvbitx).
    By fetching the directory, we get the bitfile regardless of its hash.

    Args:
        fpga_pipeline_name: Name of the FPGA pipeline (e.g., "cRIO_FPGA_Main")

    Returns:
        Dictionary with fetch task configuration
    """
    return {
        "fetch": {
            "run_if": "passed",
            "pipeline": fpga_pipeline_name,
            "stage": "build_fpga",
            "job": "build_fpga",
            "is_file": False,  # Fetch directory, not individual file
            "source": "FPGA Bitfiles",
            "destination": "FPGA Bitfiles/",
        }
    }
