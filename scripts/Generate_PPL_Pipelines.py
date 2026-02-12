#! python3
import multiprocessing
import re
import os
from pathlib import Path
import time
import yaml

from GitTools import cloneRepo
from FileUtils import find_file, pushd, directoryFromGitRepo
from YamlGenerator import PipelineDefinition, buildYamlObject, updateMinimumVersions
from NameTransformers import sanitizeForPipelineName, parseMkfileTargetToName, parseMkFile, parseVipkgReqsFile

def get_libraries_and_urls(path):
  if(not path.exists()):
    raise RuntimeError(f"Bad path passed to get_libraries_and_urls: {path}")
  print('Getting libraries and URLs from file: ' + str(path))
  matcher = re.compile(r"^(.*?)_REPO\s?:=\s?(.*)$")
  repos = {}
  file = open(path)
  for line in file.readlines():
    if(line.startswith("#")):
      continue
    line = line.strip()
    match = matcher.match(line)
    if (match):
      libraryName = match.group(1)
      repoUrl = match.group(2)
      pipelineName = sanitizeForPipelineName(libraryName)
      userLibraryName = parseMkfileTargetToName(libraryName)
      if (repoUrl.startswith("oist/")):
        repoUrl = "git@github.com:" + repoUrl
      repos[pipelineName] = {"url": repoUrl, "filename": userLibraryName + '.lvlib'}

  file.close()
  print('Parsed repository list')
  print()
  return repos

def generateEntryDictionary(pipelineName, gitUrl, libPath, PPL_Name, Dependencies, DependencyPPLNames, minLabVIEWVersion, vipkgUrls):
  return {
    pipelineName: {
      "artifactId": pipelineName + "_nipkg",
      "gitUrl": gitUrl,
      "libPath": libPath,
      "PPL_Name": PPL_Name,
      "Dependencies": Dependencies,
      "Dependency PPL Names": DependencyPPLNames,
      "minLabVIEWVersion": minLabVIEWVersion,
      "vipkgUrls": vipkgUrls
    }
  }

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
    vipkgReqsPath = find_file(libName.replace('.lvlib', '.vipm_reqs'), outputDir)
    pipelineName = sanitizeForPipelineName(libName) + "p"
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
    depsNames = None
    depsList = None
    vipkgUrls = None
    if mkFilePath != None:
      depsNames = parseMkFile(mkFilePath, libName)
      depsList = list(map(sanitizeForPipelineName, depsNames))
    if vipkgReqsPath != None:
      vipkgUrls = parseVipkgReqsFile(vipkgReqsPath)
    retVals.append(generateEntryDictionary(pipelineName, gitUrl, libPath, PPL_Name, depsList, depsNames, minLabVIEWVersion, vipkgUrls))
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
  outputDirectory = os.path.join(Path.cwd(), "cloned")
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
    yaml.dump(yamlObject, outputFile, sort_keys=False, width=999999)
  print(str(os.path.getsize(outputFilePath)) + " bytes")
