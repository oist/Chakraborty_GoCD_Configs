import yaml
import re
from enum import Enum
from pathlib import Path
from Constants import \
  dir_job, create_ppl_dir, ls_task, ls_currentDir_task,\
  via_job, via_plugin_version, fetch_builder_task,\
  expand_builder_task, gcli_build_task, builderMaterial,\
  fetch_ppl_configuration

directoryNameMatcher = re.compile(r'^.*:.*/(.*)$')
def directoryFromGitRepo(gitRepo, output_dir = None):
	dest = directoryNameMatcher.match(gitRepo).group(1)
	if output_dir:
		dest = Path(output_dir) / dest
	return dest

class Target(Enum):
  Windows_32_Release = 0
  Windows_32_Debug = 1
  Windows_64_Release = 2
  Windows_64_Debug = 3
  cRIO_Release = 4
  cRIO_Debug = 5
  
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
  "cRIO_Debug": "cRIO-9045\\Debug_32\\home\\lvuser\\natinst\\bin"
}

def get_mklink_task(target):
  targetPathEnd = targetPathEnds[target]
  return { "exec": {
  "run_if": "passed",
  "command": "powershell",
  "arguments": [
    "-Command",
    "New-Item",
    "-Force",
    "-ItemType",
    "Junction",
    "-Path",
    "PPLs\\Current", # relative path?
    "-Target",
    f"\\\"C:\\LabVIEW Sources\\PPLs\\{targetPathEnd}\\\""
  ]
}}

mklink_tasks = {}
for target in Target._member_names_:
  mklink_tasks[target] = get_mklink_task(target)

PPLJobTasks_NoDeps = [
  fetch_builder_task,
  expand_builder_task,
  ls_task,
  gcli_build_task
]

ppl_build_artifact = { "build": {
  "source": "PPLs/Current/#{PPL_Name}",
  "destination": "#{PPL_Name}"
}}

nipkg_build_artifact = { "build": {
  "source": "NIPKGs/*",
  "destination": "#{PPL_Name}"
}}

profileId = {
  "2019": {
    Target.Windows_32_Debug: "labview_2019_x86",
    Target.Windows_32_Release: "labview_2019_x86",
    Target.Windows_64_Debug: "labview_2019_x64",
    Target.Windows_64_Release: "labview_2019_x64",
    Target.cRIO_Debug: "labview_2019_x86_crio",
    Target.cRIO_Release: "labview_2019_x86_crio",
  },
  "2021": {
    Target.Windows_32_Debug: "labview_2021_x86",
    Target.Windows_32_Release: "labview_2021_x86",
    Target.Windows_64_Debug: "labview_2021_x64",
    Target.Windows_64_Release: "labview_2021_x64",
    Target.cRIO_Debug: "labview_2021_x86_crio",
    Target.cRIO_Release: "labview_2021_x86_crio",
  },
}

def generatePPLJobTasksWithDeps(dependencies, targetName):
  if dependencies is None:
    raise ValueError("Attempted to generate a PPL Task List with dependencies without passing a list of Dependencies")
  fetchTasks = []
  for dependency in dependencies:
    dependencyRootName = getPackageRootName(dependency)
    packageId = f"{dependencyRootName}_{targetName}_nipkg"
    fetchTasks.append({"fetch": {
      "run_if": "passed",
      "artifact_origin": "external",
      "pipeline": dependency,
      "stage": "build_ppls",
      "job": targetName,
      "artifact_id": packageId,
      "configuration": fetch_ppl_configuration
    }})
  return [ fetch_builder_task, expand_builder_task, create_ppl_dir ] + fetchTasks +\
    [ mklink_tasks[targetName], ls_task, ls_currentDir_task, gcli_build_task ]

nipkgConfigOptions = {
  "options": {
    "PackagePath": "NIPKGs/*.nipkg"
  }
}

environmentVariables = {}
for target in Target.__members__:
  targetT = Target[target]
  is64Bit = targetT in [Target.Windows_64_Debug, Target.Windows_64_Release]
  environmentVariables[targetT] = {
    "TARGET_NAME": target,
    "BUILD_TYPE": "BUILD", # Probably set this elsewhere
    "TARGET_SYSTEM": "Windows" if targetT.value < 4 else "cRIO",
    "IS_DEBUG_BUILD": targetT.value % 2,
    "BITNESS_FLAG": "--x64 -v" if is64Bit else "-v",
    "RELEASE_NOTES": ""
  }

def generatePPLJobList(packageRootName, lv_version, dependencies):
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
        { "external": {
          # This id-value changes per PPL, but could be made into a set of 6 aliases (one per target)
          # Actually, this might not allow parameter usage...
            "id": packageId,
            "store_id": "cicwin",
            "configuration": nipkgConfigOptions
        }}
      ],
      "tasks": PPLJobTasks_NoDeps if dependencies is None else generatePPLJobTasksWithDeps(dependencies, target)
    }
  return ppl_job_list

def generatePPLStage(packageRootName, lv_version, dependencies):
  return {"build_ppls": {
      "fetch_materials": "yes",
      "clean_workspace": "yes",
      "approval": "success", # Set to manual to prevent auto-scheduling
      # Git material is set not to autoupdate, so this controls if pipelines are triggered by PPL dependencies
      "jobs": generatePPLJobList(packageRootName, lv_version, dependencies)
  }}

def get_fetch_built_ppl_task(target):
  return {
    "fetch": {
      "run_if": "passed",
      "stage": "build_ppls", # Same as the name given in 'generatePPLStage'
      "job": target,
      "is_file": False,
      "source": "#{PPL_Name}",
      "destination": f"artifacts/{target}"
    }
  }

git_tag_tasks = [fetch_builder_task, expand_builder_task]
for target in Target._member_names_:
  git_tag_tasks.append(get_fetch_built_ppl_task(target))
git_tag_tasks.append({
  "exec": {
    "run_if": "passed",
    "command": "dir",
    "arguments": [ "*" ]
  }
})
git_tag_tasks.append(
  { "exec": {
      "run_if": "passed",
      "command": "py",
      "arguments": [ "-3", "-u", "PPL_Builder/publish_github.py"]
  }}
)

git_tag_stage = {"git_tag": {
    "approval": "success",
    "fetch_materials": "yes",
    "environment_variables": {
      "GITHUB_RELEASE_TOKEN": "{{SECRET:[secrets.json][github_publishing_token]}}",
      "PPL_NAME": "#{PPL_Name}"
    },
    # Single job, so no need for jobs entry
    "tasks": git_tag_tasks
  }
}

dependencyMaterials = {}
def generateMaterials(gitUrl, dependencies):
  topDir = directoryFromGitRepo(gitUrl, None)
  materials = {
    "builder": builderMaterial,
    topDir: {
      "git": gitUrl,
      "destination": topDir,
      "auto_update": False,
      "shallow_clone": False
    }
  }
  if dependencies is not None:
    for dependency in dependencies:
      materialName = dependency+"_pipelineMaterial"
      if(not materialName in dependencyMaterials):
        dependencyMaterials[materialName] = {
          "pipeline": dependency,
          "stage": "build_ppls",
          "ignore_for_scheduling": False # Default
        }
      materials[materialName] = dependencyMaterials.get(materialName)
  return materials

# Defines all of the 'common' parts of the pipeline config file
def getCommonSection():
  commonSection = {
    "via_plugin_version": via_plugin_version,
    "dir_job": dir_job,
    "via_job": via_job,
    "PPL_Job": PPLJobTasks_NoDeps
  }
  for k, v in mklink_tasks.items():
    commonSection["mklink_task_" + k] = v
  return commonSection

def getPackageRootName(pipelineName):
  return pipelineName.replace(".lvlibp", "")

class PipelineDefinition(yaml.YAMLObject):
  yaml_tag = u"!PipelineDefinition"
  def __init__(self, pipelineName, values):
    self.name = pipelineName
    self.artifactId = values['artifactId']
    self.gitUrl = values['gitUrl']
    self.libPath = values['libPath']
    self.PPL_Name = values['PPL_Name']
    self.dependencies = values['Dependencies']
    self.dependencyPPLNames = values['Dependency PPL Names']
    self.minVersion = values.get('minLabVIEWVersion')
  def buildData(self, dumper):
    materials = generateMaterials(self.gitUrl, self.dependencies)
    if self.dependencies != None:
      dependencyQuotedList = "\"" + "\" \"".join(self.dependencyPPLNames) + "\""
    else:
      dependencyQuotedList = ""
    gitDirName = directoryFromGitRepo(self.gitUrl, None)
    if self.minVersion != None:
      lv_version = self.minVersion
    else:
      lv_version = '2019'
    return {
      "group": "PPLs",
      "parameters": {
        "PPL_Name": self.PPL_Name,
        "PPL_LIB_PATH": self.libPath,
        "GIT_DIR": gitDirName,
        "LV_VERSION": lv_version,
        "Dependency_PPL_Names": dependencyQuotedList
      },
      "materials": materials,
      "stages": [
        generatePPLStage(getPackageRootName(self.name), lv_version, self.dependencies),
        git_tag_stage
      ]
    }

  @classmethod
  def to_yaml(cls, dumper, self):
    data = self.buildData(dumper)
    return dumper.represent_mapping(u'tag:yaml.org,2002:map', data)
  
def buildYamlObject(pipelineDictionary):
  full_yaml_object = {
    "format_version": 10,
    "common": getCommonSection(),
    "pipelines": pipelineDictionary
  }
  return full_yaml_object