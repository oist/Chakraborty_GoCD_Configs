from FileUtils import directoryFromGitRepo
from Constants import fetch_ppl_configuration, Target


class MergeKey:
    """A mapping key written as the YAML merge key '<<'.

    {MERGE: base, "key": value} is written as '<<: *base' plus 'key: value', and is read
    (by GoCD's YAML plugin) as the keys of base together with 'key'. The explicit keys
    must not repeat keys of base, since parsers differ in which value wins.
    """


MERGE = MergeKey()


def getPackageRootName(pipelineName):
    return pipelineName.replace(".lvlibp", "")


def generateMaterials(gitUrl, dependencies):
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
            materials[dep + "_pipelineMaterial"] = {
                "pipeline": dep,
                "stage": "build_ppls",
                "ignore_for_scheduling": False,
            }
    return materials


# The repeated parts of a dependency's fetch task.
# Defined per target to allow aliasing.
fetchPPLBases = {}
for target in Target._member_names_:
    fetchPPLBases[target] = {
        "run_if": "passed",
        "artifact_origin": "external",
        "stage": "build_ppls",
        "job": target,
        "configuration": fetch_ppl_configuration,
    }


def generateFetchPPLJob(dependency, targetName):
    dependencyRootName = getPackageRootName(dependency)
    packageId = f"{dependencyRootName}_{targetName}_nipkg"
    return {
        "fetch": {
            MERGE: fetchPPLBases[targetName],
            "pipeline": dependency,
            "artifact_id": packageId,
        }
    }
