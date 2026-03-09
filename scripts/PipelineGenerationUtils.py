from FileUtils import directoryFromGitRepo
from Constants import fetch_ppl_configuration


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
