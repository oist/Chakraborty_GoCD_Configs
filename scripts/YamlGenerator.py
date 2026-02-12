import yaml
from FileUtils import directoryFromGitRepo
from Constants import (
    dir_job,
    create_ppl_dir,
    ls_task,
    ls_currentDir_task,
    via_job,
    via_plugin_version,
    fetch_builder_task,
    expand_builder_task,
    gcli_build_task,
    builderMaterial,
    labviewDir,
    profileId,
    Target,
    targetPathEnds,
)
from PipelineGenerationUtils import (
    generateMaterials,
    generateFetchPPLJob,
    getPackageRootName,
)


def get_mklink_task(target):
    targetPathEnd = targetPathEnds[target]
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
                "PPLs\\Current",  # relative path?
                "-Target",
                f'\\"C:\\LabVIEW Sources\\PPLs\\{targetPathEnd}\\"',
            ],
        }
    }


mklink_tasks = {}
for target in Target._member_names_:
    mklink_tasks[target] = get_mklink_task(target)

PPLJobTasks_NoDeps = [fetch_builder_task, expand_builder_task, ls_task, gcli_build_task]

ppl_build_artifact = {
    "build": {"source": "PPLs/Current/#{PPL_Name}", "destination": "#{PPL_Name}"}
}

nipkg_build_artifact = {"build": {"source": "NIPKGs/*", "destination": "#{PPL_Name}"}}


def generatePPLJobTasksWithDeps(dependencies, vipkgUrls, targetName, lv_version):
    if dependencies is None and vipkgUrls is None:
        raise ValueError(
            "Attempted to generate a PPL Task List with dependencies without passing a list of Dependencies"
        )
    pplDepTasks = []
    if dependencies is not None:
        pplDepTasks.append(create_ppl_dir)
        for dependency in dependencies:
            pplDepTasks.append(generateFetchPPLJob(dependency, targetName))
        pplDepTasks.append(mklink_tasks[targetName])
        pplDepTasks.append(ls_currentDir_task)
    vipkgTasks = []
    if vipkgUrls is not None:
        targetT = Target[targetName]
        for vipkgUrl in vipkgUrls:
            vipkgTasks.append(
                {
                    "plugin": {
                        "run_if": "passed",
                        "options": {
                            "Url": vipkgUrl,
                            "LabVIEWDirectory": labviewDir[lv_version][targetT],
                            "Verbose": False,
                        },
                        "configuration": {
                            "id": "jp.oist.chakraborty.vi-package-installer",
                            "version": "0.1",
                        },
                    }
                }
            )
    return (
        [fetch_builder_task, expand_builder_task]
        + pplDepTasks
        + vipkgTasks
        + [ls_task, gcli_build_task]
    )


nipkgConfigOptions = {"options": {"PackagePath": "NIPKGs/*.nipkg"}}

environmentVariables = {}
for target in Target.__members__:
    targetT = Target[target]
    is64Bit = targetT in [Target.Windows_64_Debug, Target.Windows_64_Release]
    environmentVariables[targetT] = {
        "TARGET_NAME": target,
        "BUILD_TYPE": "BUILD",  # Probably set this elsewhere
        "TARGET_SYSTEM": "Windows" if targetT.value < 4 else "cRIO",
        "IS_DEBUG_BUILD": targetT.value % 2,
        "BITNESS_FLAG": "--x64 -v" if is64Bit else "-v",
        "RELEASE_NOTES": "",
    }


def generatePPLJobList(packageRootName, lv_version, dependencies, vipkgUrls):
    ppl_job_list = {}
    for target in Target.__members__:
        targetT = Target[target]
        packageId = f"{packageRootName}_{target}_nipkg"
        ppl_job_list[target] = {
            "timeout": 15,
            "elastic_profile_id": profileId[lv_version][targetT],
            "environment_variables": environmentVariables[targetT],
            "artifacts": [
                ppl_build_artifact,
                nipkg_build_artifact,
                {
                    "external": {
                        # This id-value changes per PPL, but could be made into a set of 6 aliases (one per target)
                        # Actually, this might not allow parameter usage...
                        "id": packageId,
                        "store_id": "cicwin",
                        "configuration": nipkgConfigOptions,
                    }
                },
            ],
            "tasks": (
                PPLJobTasks_NoDeps
                if dependencies is None and vipkgUrls is None
                else generatePPLJobTasksWithDeps(
                    dependencies, vipkgUrls, target, lv_version
                )
            ),
        }
    return ppl_job_list


def generatePPLStage(packageRootName, lv_version, dependencies, vipkgUrls):
    return {
        "build_ppls": {
            "fetch_materials": "yes",
            "clean_workspace": "yes",
            "approval": "manual",  # Set to "manual" to prevent auto-scheduling, "success" to allow autotriggering
            # Git material is set not to autoupdate, so this controls if pipelines are triggered by PPL dependencies
            "jobs": generatePPLJobList(
                packageRootName, lv_version, dependencies, vipkgUrls
            ),
        }
    }


def get_fetch_built_ppl_task(target):
    return {
        "fetch": {
            "run_if": "passed",
            "stage": "build_ppls",  # Same as the name given in 'generatePPLStage'
            "job": target,
            "is_file": False,
            "source": "#{PPL_Name}",
            "destination": f"artifacts/{target}",
        }
    }


git_tag_tasks = [fetch_builder_task, expand_builder_task]
for target in Target._member_names_:
    git_tag_tasks.append(get_fetch_built_ppl_task(target))
git_tag_tasks.append(
    {"exec": {"run_if": "passed", "command": "dir", "arguments": ["*"]}}
)
git_tag_tasks.append(
    {
        "exec": {
            "run_if": "passed",
            "command": "py",
            "arguments": ["-3", "-u", "PPL_Builder/publish_github.py"],
        }
    }
)

git_tag_stage = {
    "git_tag": {
        "approval": "success",
        "fetch_materials": "yes",
        "environment_variables": {
            "GITHUB_RELEASE_TOKEN": "{{SECRET:[secrets.json][github_publishing_token]}}",
            "PPL_NAME": "#{PPL_Name}",
            "RELEASE_NOTES": "",
        },
        "resources": ["powershell"],
        # Single job, so no need for jobs entry
        "tasks": git_tag_tasks,
    }
}


# Defines all of the 'common' parts of the pipeline config file
def getCommonSection():
    commonSection = {
        "via_plugin_version": via_plugin_version,
        "dir_job": dir_job,
        "via_job": via_job,
        "PPL_Job": PPLJobTasks_NoDeps,
    }
    for k, v in mklink_tasks.items():
        commonSection["mklink_task_" + k] = v
    return commonSection


dependencyMaterials = {}


class PipelineDefinition(yaml.YAMLObject):
    yaml_tag = "!PipelineDefinition"

    def __init__(self, pipelineName, values):
        self.name = pipelineName
        self.artifactId = values["artifactId"]
        self.gitUrl = values["gitUrl"]
        self.libPath = values["libPath"]
        self.PPL_Name = values["PPL_Name"]
        self.dependencies = values["Dependencies"]
        self.dependencyPPLNames = values["Dependency PPL Names"]
        self.minVersion = values.get("minLabVIEWVersion")
        self.vipkgUrls = values.get("vipkgUrls")

    def buildData(self, dumper):
        materials = {"builder": builderMaterial} | generateMaterials(
            self.gitUrl, self.dependencies, dependencyMaterials
        )
        if self.dependencies != None:
            dependencyQuotedList = '"' + '" "'.join(self.dependencyPPLNames) + '"'
        else:
            dependencyQuotedList = ""
        gitDirName = directoryFromGitRepo(self.gitUrl, None)
        if self.minVersion != None:
            lv_version = self.minVersion
        else:
            lv_version = "2019"
        return {
            "group": "PPLs",
            "parameters": {
                "PPL_Name": self.PPL_Name,
                "PPL_LIB_PATH": self.libPath,
                "GIT_DIR": gitDirName,
                "LV_VERSION": lv_version,
                "Dependency_PPL_Names": dependencyQuotedList,
            },
            "materials": materials,
            "stages": [
                generatePPLStage(
                    getPackageRootName(self.name),
                    lv_version,
                    self.dependencies,
                    self.vipkgUrls,
                ),
                git_tag_stage,
            ],
        }

    @classmethod
    def to_yaml(cls, dumper, self):
        data = self.buildData(dumper)
        return dumper.represent_mapping("tag:yaml.org,2002:map", data)


def buildYamlObject(pipelineDictionary):
    full_yaml_object = {
        "format_version": 10,
        "common": getCommonSection(),
        "pipelines": pipelineDictionary,
    }
    return full_yaml_object


def findNonDefaultLVPipelines(pipelineDictionary, defaultVersion):
    def myfilter(item):
        return item[1].minVersion != None and item[1].minVersion != defaultVersion

    return dict(filter(myfilter, pipelineDictionary.items())).keys()


def updateMinimumVersions(pipelineDictionary):
    # This code only works for 2 versions. With multiple non-default versions, needs more care
    nonDefaultPipelineNames = findNonDefaultLVPipelines(pipelineDictionary, "2019")
    if len(nonDefaultPipelineNames) == 0:
        return pipelineDictionary
    pipelinesToUpdate = set(nonDefaultPipelineNames)
    newElements = []

    def dependsOnElems(dependenciesToInclude):
        def innerFilter(item):
            itemDependencies = item[1].dependencies
            if itemDependencies == None:
                return False
            return (
                set(itemDependencies) & set(dependenciesToInclude)
                and item[0] not in dependenciesToInclude
            )

        return innerFilter

    while True:
        newElements = dict(
            filter(dependsOnElems(pipelinesToUpdate), pipelineDictionary.items())
        ).keys()
        pipelinesToUpdate.update(newElements)
        if len(newElements) == 0:
            break
    print("Updating target LabVIEW versions for " + str(pipelinesToUpdate))

    def updateVers(name, pipeline):
        if name in pipelinesToUpdate:
            pipeline.minVersion = "2021"
        return pipeline

    # Seems like the comprehension here forces the function to iterate over the items
    # Calling the function without creating the dictionary leaves it unexecuted
    newDict = {k: updateVers(k, v) for k, v in pipelineDictionary.items()}
    return newDict
