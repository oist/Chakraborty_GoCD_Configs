import os

def find_file(filename, top_directory, absolute=True):
  for dirpath, dirnames, files in os.walk(top_directory):
    for file in files:
      if file == filename:
        return os.path.join(dirpath, file) if absolute else os.path.relpath(os.path.join(dirpath, file), top_directory)
  return None