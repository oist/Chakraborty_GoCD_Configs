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
    print_labview_logs_task,
    fetch_ppl_configuration,
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
    fetchPPLBases,
    MergeKey,
    MERGE,
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

PPLJobTasks_NoDeps = [
    fetch_builder_task,
    expand_builder_task,
    ls_task,
    gcli_build_task,
    print_labview_logs_task,
]

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
        + [ls_task, gcli_build_task, print_labview_logs_task]
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


# The parts of a PPL build job which depend only on the LabVIEW version and target, merged into each job.
jobBases = {}
for lv_version in profileId:
    for targetT in Target:
        jobBases[(lv_version, targetT)] = {
            "timeout": 15,
            "elastic_profile_id": profileId[lv_version][targetT],
            # Written in full in the first base using them. If bases for several LabVIEW versions
            # are written, the others alias it (see the environment_<target> names in namedAnchors).
            "environment_variables": environmentVariables[targetT],
        }


def generatePPLJobList(packageRootName, lv_version, dependencies, vipkgUrls):
    ppl_job_list = {}
    for target in Target.__members__:
        targetT = Target[target]
        packageId = f"{packageRootName}_{target}_nipkg"
        ppl_job_list[target] = {
            MERGE: jobBases[(lv_version, targetT)],
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


# Define shared tasks for reuse across pipelines.
# Defining here prevents aliasing against the first pipeline that uses the element.
commonDefinitions = {
    "create_ppl_dir_task": create_ppl_dir,
    "ls_current_dir_task": ls_currentDir_task,
    "fetch_ppl_configuration": fetch_ppl_configuration,
    "ppl_build_artifact": ppl_build_artifact,
    "nipkg_build_artifact": nipkg_build_artifact,
    "nipkg_store_configuration": nipkgConfigOptions,
    "builder_material": builderMaterial,
}
for target, base in fetchPPLBases.items():
    commonDefinitions["fetch_ppl_base_" + target] = base
commonDefinitions["git_tag_stage"] = git_tag_stage


def jobBaseName(lv_version, targetT):
    return f"job_base_{lv_version}_{targetT.name}"


# Defines all of the 'common' parts of the pipeline config file
def getCommonSection(lv_versions):
    commonSection = {
        "via_plugin_version": via_plugin_version,
        "dir_job": dir_job,
        "via_job": via_job,
        "PPL_Job": PPLJobTasks_NoDeps,
    }
    for k, v in mklink_tasks.items():
        commonSection["mklink_task_" + k] = v
    commonSection |= commonDefinitions
    # Only the job bases for LabVIEW versions used by a pipeline, to avoid unused definitions
    for (lv_version, targetT), base in jobBases.items():
        if lv_version in lv_versions:
            commonSection[jobBaseName(lv_version, targetT)] = base
    return commonSection


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

    def labviewVersion(self):
        return self.minVersion if self.minVersion != None else "2019"

    def buildData(self, dumper):
        materials = {"builder": builderMaterial} | generateMaterials(
            self.gitUrl, self.dependencies
        )
        if self.dependencies != None:
            dependencyQuotedList = '"' + '" "'.join(self.dependencyPPLNames) + '"'
        else:
            dependencyQuotedList = ""
        gitDirName = directoryFromGitRepo(self.gitUrl, None)
        lv_version = self.labviewVersion()
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


# These tasks are named, not numbered.
# This allows reduced churn in the output yaml when changing jobs/tasks.
namedAnchors = {
    "ppl_job_tasks_no_deps": PPLJobTasks_NoDeps,
    "fetch_builder_task": fetch_builder_task,
    "expand_builder_task": expand_builder_task,
    "ls_task": ls_task,
    "gcli_build_task": gcli_build_task,
    "print_labview_logs_task": print_labview_logs_task,
}
for k, v in mklink_tasks.items():
    namedAnchors["mklink_task_" + k] = v
namedAnchors |= commonDefinitions
for (lv_version, targetT), base in jobBases.items():
    namedAnchors[jobBaseName(lv_version, targetT)] = base
# Not listed in commonDefinitions: the variables are only anchored (in a job base) when
# bases for more than one LabVIEW version share them, and are otherwise written inline.
for targetT in Target:
    namedAnchors["environment_" + targetT.name] = environmentVariables[targetT]


def describeNode(node, maxLength=300):
    # One-line preview of a node
    text = " ".join(yaml.serialize(node, width=999999).split())
    return text if len(text) <= maxLength else text[:maxLength] + "..."


class PipelineDumper(yaml.Dumper):
    def generate_anchor(self, node):
        # represented_objects maps id(object) to its node while the document is serialized
        for name, obj in namedAnchors.items():
            if self.represented_objects.get(id(obj)) is node:
                return name
        # return super().generate_anchor(node)
        # Rather than falling back to a numbered &idNNN anchor, require each shared object to be named.
        raise ValueError(
            "An object is written in more than one place but has no name in namedAnchors: "
            + describeNode(node)
        )

    def ignore_aliases(self, data):
        # MERGE is a single shared object, but must be written as a plain '<<' each time, not aliased
        return isinstance(data, MergeKey) or super().ignore_aliases(data)


# The merge tag makes the key '<<' resolve as a merge key, so it is written unquoted
PipelineDumper.add_representer(
    MergeKey,
    lambda dumper, data: dumper.represent_scalar("tag:yaml.org,2002:merge", "<<"),
)


def buildYamlObject(pipelineDictionary):
    full_yaml_object = {
        "format_version": 10,
        "common": getCommonSection(
            {p.labviewVersion() for p in pipelineDictionary.values()}
        ),
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
