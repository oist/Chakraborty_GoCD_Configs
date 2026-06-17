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
    ppl_targets,
    crio_ppl_targets,
    is_windows,
    DEFAULT_LV_VERSION,
    highest_lv_version,
)
from PipelineGenerationUtils import (
    generateMaterials,
    generateFetchPPLJob,
    getPackageRootName,
    BasePipelineDefinition,
    make_junction_task,
    generateVipkgTask,
    quoteDependencyNames,
    aliasable,
    buildYamlObject as buildYamlObjectBase,
)


def get_mklink_task(target):
    return make_junction_task("PPLs\\Current", targetPathEnds[target])


mklink_tasks = {}
for target in ppl_targets:
    mklink_tasks[target.name] = get_mklink_task(target.name)

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
                generateVipkgTask(vipkgUrl, labviewDir[lv_version][targetT])
            )
    return (
        [fetch_builder_task, expand_builder_task]
        + pplDepTasks
        + vipkgTasks
        + [ls_task, gcli_build_task]
    )


nipkgConfigOptions = {"options": {"PackagePath": "NIPKGs/*.nipkg"}}

environmentVariables = {}
for targetT in ppl_targets:
    is64Bit = targetT in [Target.Windows_64_Debug, Target.Windows_64_Release]
    environmentVariables[targetT] = {
        "TARGET_NAME": targetT.name,
        "BUILD_TYPE": "BUILD",  # Probably set this elsewhere
        "TARGET_SYSTEM": "Windows" if is_windows(targetT) else "cRIO",
        "IS_DEBUG_BUILD": targetT.value % 2,
        "BITNESS_FLAG": "--x64 -v" if is64Bit else "-v",
        "RELEASE_NOTES": "",
    }


def generatePPLJobList(
    packageRootName, lv_version, dependencies, vipkgUrls, crioOnly=False
):
    ppl_job_list = {}
    targets = crio_ppl_targets if crioOnly else ppl_targets
    for targetT in targets:
        target = targetT.name
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


def generatePPLStage(
    packageRootName, lv_version, dependencies, vipkgUrls, crioOnly=False
):
    return {
        "build_ppls": {
            "fetch_materials": "yes",
            "clean_workspace": "yes",
            "approval": "manual",  # Set to "manual" to prevent auto-scheduling, "success" to allow autotriggering
            # Git material is set not to autoupdate, so this controls if pipelines are triggered by PPL dependencies
            "jobs": generatePPLJobList(
                packageRootName, lv_version, dependencies, vipkgUrls, crioOnly
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


def generateGitTagTasks(targets):
    tasks = [fetch_builder_task, expand_builder_task]
    for target in targets:
        tasks.append(get_fetch_built_ppl_task(target.name))
    tasks.append({"exec": {"run_if": "passed", "command": "dir", "arguments": ["*"]}})
    tasks.append(
        {
            "exec": {
                "run_if": "passed",
                "command": "py",
                "arguments": ["-3", "-u", "PPL_Builder/publish_github.py"],
            }
        }
    )
    return tasks


def generateGitTagStage(targets):
    return {
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
            "tasks": generateGitTagTasks(targets),
        }
    }


# crioOnly only ever selects between two target sets (full vs. cRIO-only), so
# this cache lets every pipeline sharing a target set alias back to a single
# git_tag_stage object instead of each inlining its own copy.
cachedGitTagStages = {}


def get_git_tag_stage(crioOnly):
    targets = crio_ppl_targets if crioOnly else ppl_targets
    return aliasable(generateGitTagStage(targets), cachedGitTagStages)


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


class PipelineDefinition(BasePipelineDefinition):
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
        self.crioOnly = values.get("crioOnly", False)

    def buildData(self, dumper):
        materials = {"builder": builderMaterial} | generateMaterials(
            self.gitUrl, self.dependencies, dependencyMaterials
        )
        dependencyQuotedList = quoteDependencyNames(self.dependencyPPLNames)
        gitDirName = directoryFromGitRepo(self.gitUrl, None)
        lv_version = (
            self.minVersion if self.minVersion is not None else DEFAULT_LV_VERSION
        )
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
                    self.crioOnly,
                ),
                get_git_tag_stage(self.crioOnly),
            ],
        }


def buildYamlObject(pipelineDictionary):
    return buildYamlObjectBase(pipelineDictionary, common=getCommonSection())


def updateMinimumVersions(pipelineDictionary):
    # A pipeline must build with a LabVIEW version at least as high as every
    # version required transitively by its dependencies: a PPL built in a newer
    # LabVIEW cannot be consumed by an older build. So each pipeline's effective
    # version is the highest of its own minimum and those of all its
    # dependencies, and that version is forced onto the caller.
    def resolvedVersion(pipeline):
        if pipeline.minVersion is not None:
            return pipeline.minVersion
        return DEFAULT_LV_VERSION

    effective = {name: resolvedVersion(p) for name, p in pipelineDictionary.items()}

    # Fixpoint: repeatedly lift each pipeline to the highest version among itself
    # and its dependencies until nothing changes. Versions only ever rise and are
    # bounded by the highest version in play, so this terminates even if the
    # dependency graph contains a cycle. Dependencies that aren't generated
    # pipelines (absent from the dict) contribute nothing and are skipped.
    changed = True
    while changed:
        changed = False
        for name, pipeline in pipelineDictionary.items():
            if pipeline.dependencies is None:
                continue
            candidates = [effective[name]]
            candidates.extend(
                effective[dep] for dep in pipeline.dependencies if dep in effective
            )
            highest = highest_lv_version(candidates)
            if highest != effective[name]:
                effective[name] = highest
                changed = True

    # Only bump above the default: pipelines that resolve to the default keep
    # their existing minVersion (typically None) so the generated YAML is
    # unchanged for them.
    updated = []
    for name, pipeline in pipelineDictionary.items():
        if effective[name] != resolvedVersion(pipeline):
            pipeline.minVersion = effective[name]
            updated.append(name)
    if updated:
        print("Updating target LabVIEW versions for " + str(set(updated)))
    return pipelineDictionary


def validateCrioOnlyDependencies(pipelineDictionary):
    # A cRIO-only library never builds Windows-target PPLs, so a pipeline
    # that still builds Windows targets can't fetch a Windows PPL from it.
    for name, pipeline in pipelineDictionary.items():
        if pipeline.crioOnly or pipeline.dependencies is None:
            continue
        for dependency in pipeline.dependencies:
            dependencyPipeline = pipelineDictionary.get(dependency)
            if dependencyPipeline is not None and dependencyPipeline.crioOnly:
                raise ValueError(
                    f"{name} builds Windows targets but depends on "
                    f"{dependency}, which is marked cRIO-only"
                )
