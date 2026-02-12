#! python3
import contextlib
import os
import shutil
import stat
import subprocess

@contextlib.contextmanager
def pushd(new_dir):
	prev_dir = os.getcwd()
	os.chdir(new_dir)
	yield
	os.chdir(prev_dir)

def remove_readonly(func, path, excinfo):
	os.chmod(path, stat.S_IWRITE)
	func(path)

def runCmd(cmd):
  return subprocess.run(cmd, capture_output=True, text=True, shell=False).stdout

def cloneRepo(gitUrl, destinationDirectory, forceUpdate=False):
  # Can add --depth 1 but only marginal improvement at the moment...
  # gitCmd = f'wsl git clone -q  -- {gitUrl}'
  gitCmd = ['git',  'clone', '-q',  '--', gitUrl, destinationDirectory]
  cloneResult = subprocess.run(gitCmd, capture_output=True, text=True, shell=False)
  exists = "already exists and is not an empty directory" in cloneResult.stderr
  if cloneResult.returncode == 128 and exists:
    if forceUpdate:
      print(f"Directory already exists. Deleting and re-cloning repository")
      shutil.rmtree(destinationDirectory, onerror=remove_readonly)
      return cloneRepo(gitUrl, destinationDirectory, False) # Don't pass true again, to prevent infinite recursion.
    else:
      response = updateRepo(destinationDirectory, True)
      return f"Directory already existed at {destinationDirectory}. Updated the repository\n" + response.strip() + "\n"
  elif cloneResult.returncode != 0:
    # Other error, possibly authentication or bad argument
    raise RuntimeError(f"Error executing command: {gitCmd}\n" + str(cloneResult.stderr))
  else:
    # Success
    return f"Cloned {gitUrl} to {destinationDirectory}\n" + cloneResult.stdout.strip() + "\n"

def updateRepo(destinationDirectory, useRemote = True):
  with pushd(destinationDirectory):
    if (useRemote):
      runCmd(["git", "fetch"])
    response = runCmd(["git", "reset", "--hard", "origin/master"])
    runCmd(["git", "clean", "-f"])
    return response.strip()
