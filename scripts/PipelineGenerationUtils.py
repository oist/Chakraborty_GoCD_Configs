from FileUtils import directoryFromGitRepo
from Constants import fetch_ppl_configuration


def getPackageRootName(pipelineName):
    return pipelineName.replace(".lvlibp", "")


def generateMaterials(gitUrl, dependencies, cachedMaterials):
    topDir = directoryFromGitRepo(gitUrl, None)
    materials = {
        topDir: {
            "git": gitUrl,
            "destination": topDir,
            "auto_update": False,
            "shallow_clone": False,
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
