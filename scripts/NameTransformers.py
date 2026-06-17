import re


def parseMkfileTargetToName(target: str) -> str:
    name = target.replace("+", " ")
    return name


def sanitizeForPipelineName(target: str) -> str:
    # Used for dictionary keys and the pipeline name
    # Must be "only letters, numbers, hyphens, underscores, and periods. Max 255 chars."
    # Can be mixed case.
    pipelineName = target.replace("+", "-").replace(" ", "-")[0:255]
    if re.match(r"^[A-Za-z0-9_.-]*$", pipelineName) is None:
        print("Invalid pipeline name generated: " + pipelineName)
    return pipelineName


def parseDependencyList(depString: str) -> list:
    # Split the group on unescaped spaces
    listDeps = depString.replace(r"\ ", "+").split(" ")
    depsList = [elem.replace("+", " ") for elem in listDeps]
    return depsList


def parseMkFile(mkFilePath, buildObjectName):
    depVarName = buildObjectName.replace(" ", r"\+").replace(".lvlib", "_Deps")
    # Match <depVarName> := (.*)
    depMatcher = re.compile(depVarName + r"[ ]?:=[ ]?(.*)$")
    with open(mkFilePath, "r") as f:
        # print(f"Reading dependencies for {buildObjectName} from {mkFilePath}")
        content = f.readlines()  # Read all lines (not just first)
    for line in content:
        matchedDeps = depMatcher.match(line.strip())
        if matchedDeps:
            return parseDependencyList(matchedDeps.group(1))
    print(
        f"Warning: Found a .mk file ({mkFilePath}) but could not parse it to get dependencies"
    )
    return None


def parseVipkgReqsFile(vipkgReqsPath):
    with open(vipkgReqsPath, "r") as f:
        # print(f"Reading VI package requirements from {vipkgReqsPath}")
        content = f.readlines()  # Read all lines (not just first)
    vipkgUrls = []
    for line in content:
        line = line.strip()
        if line.startswith("#") or line == "":
            continue
        vipkgUrls.append(line)
    return vipkgUrls if len(vipkgUrls) > 0 else None
