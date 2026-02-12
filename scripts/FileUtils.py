import os
import contextlib
import re
from pathlib import Path


@contextlib.contextmanager
def pushd(new_dir):
    prev_dir = os.getcwd()
    os.chdir(new_dir)
    yield
    os.chdir(prev_dir)


def find_file(filename, top_directory, absolute=True):
    for dirpath, dirnames, files in os.walk(top_directory):
        for file in files:
            if file == filename:
                return (
                    os.path.join(dirpath, file)
                    if absolute
                    else os.path.relpath(os.path.join(dirpath, file), top_directory)
                )
    return None


directoryNameMatcher = re.compile(r"^.*:.*/(.*)$")


def directoryFromGitRepo(gitRepo, output_dir=None):
    dest = directoryNameMatcher.match(gitRepo).group(1)
    if output_dir:
        dest = os.path.join(Path(output_dir), dest)
    return dest
