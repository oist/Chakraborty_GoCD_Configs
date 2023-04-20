#! python3
import contextlib
import multiprocessing
import re
import os
from pathlib import Path
import time
import yaml

from GitTools import cloneRepo
from FileUtils import find_file
from YamlGenerator import PipelineDefinition, buildYamlObject, updateMinimumVersions

@contextlib.contextmanager
def pushd(new_dir):
	prev_dir = os.getcwd()
	os.chdir(new_dir)
	yield
	os.chdir(prev_dir)

def get_libraries_and_urls(path):
  if(not path.exists()):
    raise RuntimeError(f"Bad path passed to get_libraries_and_urls: {path}")
  print('Getting libraries and URLs from file: ' + str(path))
  matcher = re.compile("^(.*?)_REPO\s?:=\s?(.*)$")
  repos = {}
  file = open(path)
  for line in file.readlines():
    if(line.startswith("#")):
      continue
    line = line.strip()
    match = matcher.match(line)
    if (match):
      libraryName = match.group(1)
      libraryUrl = match.group(2)
      pipelineName = getSanitizedName(libraryName)
      userLibraryName = getLibraryName(libraryName)
      if (libraryUrl.startswith("oist/")):
        libraryUrl = "git@github.com:" + libraryUrl
      repos[pipelineName] = {"url": libraryUrl, "filename": userLibraryName + '.lvlib'}

  file.close()
  print('Parsed repository list')
  print()
  return repos

def getLibraryName(libraryName):
  libraryName = libraryName.replace("+", " ")
  return libraryName

def getSanitizedName(libraryName):
  # Used for dictionary keys and the pipeline name
  # Must be "only letters, numbers, hyphens, underscores, and periods. Max 255 chars."
  # Can be mixed case.
  pipelineName = libraryName.replace("+","-").replace(" ","-")[0:255]
  if(re.match(r"^[A-z0-9_.-]*$", pipelineName) is None):
    print('Invalid pipeline name generated: ' + pipelineName)
  return pipelineName

directoryNameMatcher = re.compile(r'^.*:.*/(.*)$')
def directoryFromGitRepo(gitRepo, output_dir = None):
	dest = directoryNameMatcher.match(gitRepo).group(1)
	if output_dir:
		dest = Path(output_dir) / dest
	return dest

def generateEntryDictionary(pipelineName, gitUrl, libPath, PPL_Name, Dependencies, DependencyPPLNames, minLabVIEWVersion):
  return {
    pipelineName: {
      "artifactId": pipelineName + "_nipkg",
      "gitUrl": gitUrl,
      "libPath": libPath,
      "PPL_Name": PPL_Name,
      "Dependencies": Dependencies,
      "Dependency PPL Names": DependencyPPLNames,
      "minLabVIEWVersion": minLabVIEWVersion
    }
  }

def parseMkFile(mkFilePath, libName):
  depVarName = libName.replace(' ',r'\+').replace('.lvlib','_Deps')
  f = open(mkFilePath, "r")
  # print(f"Reading dependencies for {libName} from {mkFilePath}")
  content = f.readlines() # Read all lines (not just first)
  depsList = []
  for line in content:
    # Match <libraryname>_Deps := (.*)
    matchedDeps = re.match(depVarName+r'[ ]?:=[ ]?(.*)$', line.strip())
    if matchedDeps:
      # Split the group on unescaped spaces
      listDeps = matchedDeps.group(1).replace(r'\ ','+').split(' ')
      depsList = [elem.replace('+', ' ') for elem in listDeps]
      return depsList
  print(f"Warning: Found a .mk file ({mkFilePath}) but could not parse it to get dependencies")
  return None

allowedVersionStrings = ["2019", "2021"]

def handleUrl(gitUrl, libNames, baseDir):
  outputDir = directoryFromGitRepo(gitUrl, baseDir)
  gitDir = directoryFromGitRepo(gitUrl, None)
  # print(f"{gitUrl}: {libNames}, baseDir: {baseDir}")
  forceUpdate=False
  cloneResponse = cloneRepo(gitUrl, outputDir, forceUpdate)
  retVals = []
  for libName in libNames:
    libPathPartial = find_file(libName, outputDir, False)
    if not libPathPartial:
      raise FileNotFoundError('Could not find ' + libName + ' in ' + str(baseDir))
    libPath = os.path.join(gitDir, libPathPartial).replace(os.sep, "/")
    mkFilePath = find_file(libName.replace('.lvlib', '.mk'), outputDir)
    minVerPath = find_file(libName.replace('.lvlib', '.min_lv_version'), outputDir)
    pipelineName = getSanitizedName(libName) + "p"
    PPL_Name = libName + "p"
    minLabVIEWVersion = None
    if minVerPath != None:
      f = open(minVerPath, "r")
      content = f.read()
      f.close()
      if content in allowedVersionStrings:
        minLabVIEWVersion = content
      else:
        raise RuntimeError('Invalid minimum LabVIEW version: ' + content)
    if mkFilePath == None:
      retVals.append(generateEntryDictionary(pipelineName, gitUrl, libPath, PPL_Name, None, None, minLabVIEWVersion))
    else:
      depsNames = parseMkFile(mkFilePath, libName)
      depsList = list(map(getSanitizedName, depsNames))
      retVals.append(generateEntryDictionary(pipelineName, gitUrl, libPath, PPL_Name, depsList, depsNames, minLabVIEWVersion))
  return retVals

def printFlatDict(flat_dict):
  for key, value in flat_dict.items():
    print(key, ':', value)

def flatten_dict(input):
  return {k: v for d in input for k, v in d.items()}

if __name__ == '__main__':
  this_dir = os.path.dirname((lambda x:x).__code__.co_filename)
  repoListPath = Path(this_dir, 'repoList.txt')
  entries = get_libraries_and_urls(repoListPath)
  unique_repo_urls = set(d['url'] for d in entries.values())
  urlToLibDict = dict()
  for url in unique_repo_urls:
    libNames = list(d['filename'] for d in entries.values() if d['url'] == url)
    urlToLibDict[url] = libNames
  tic_start = time.perf_counter()
  processes: list[multiprocessing.Process] = []
  outputDirectory = Path.cwd()
  forceUpdate = False
  generator = ((keyname, list(value), outputDirectory) for keyname, value in urlToLibDict.items())
  with multiprocessing.Pool(multiprocessing.cpu_count()) as pool:
    results = pool.starmap(handleUrl, generator)

  toc_end = time.perf_counter()
  print(f"Cloned all repositories in {toc_end-tic_start:0.2f} seconds")
  list_dicts = [item for sublist in results for item in sublist]
  flat_dict = {k: v for d in list_dicts for k, v in d.items()}
  # printFlatDict(flat_dict)
  # print("------")
  no_deps_entries = {k: v for k, v in flat_dict.items() if v['Dependencies'] == None}
  deps_entries = {k: v for k, v in flat_dict.items() if v['Dependencies'] != None}

  pipelineDefinitionContent = []
  for k, v in flat_dict.items():
    pipelineDefinitionContent.append({k: PipelineDefinition(k, v)})
  # Sort to ensure the same order on repeated execution
  # This also helps reduce git diffs
  pipelineDict = dict(sorted(flatten_dict(pipelineDefinitionContent).items()))
  updateMinimumVersions(pipelineDict)

  # The behaviour of the sort might depend on Python version -
  # dictionary insertion order is preserved after Python 3.7
  yamlObject = buildYamlObject(pipelineDict)
  # print(yaml.dump(yamlObject, sort_keys=False))

  outputFilePath = "./LabVIEW_PPL-Pipelines.gocd.yaml"
  with open(outputFilePath, 'w') as outputFile:
    yaml.dump(yamlObject, outputFile, sort_keys=False)
  print(str(os.path.getsize(outputFilePath)) + " bytes")
