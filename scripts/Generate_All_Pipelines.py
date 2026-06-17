#! python3
"""Run all three GoCD pipeline generators in a single invocation.

Executes, in order:
    1. Generate_PPL_Pipelines.py   -> LabVIEW_PPL-Pipelines.gocd.yaml
    2. Generate_FPGA_Pipelines.py  -> cRIO_FPGA_Pipelines.gocd.yaml
    3. Generate_RT_Pipeline.py     -> cRIO_RT_Pipelines.gocd.yaml

Each generator clones the git repositories it needs into a shared ./cloned
directory (relative to the current working directory) before emitting its YAML.
The generators are run as subprocesses that inherit this process's working
directory, so they all share that one ./cloned tree.

Clone reuse
-----------
GitTools.cloneRepo does a `git fetch` + `git reset --hard` (not a fresh clone)
whenever the destination directory already exists. Combined with the shared
./cloned tree, that means each unique repository is fully cloned at most once
per run.

The remaining redundancy is that single extra fetch of Chakraborty_cRIO by RT.
Eliminating it would require refactoring the generators to share an in-process
clone step (they currently each own a `__main__` block); as separate processes
they cannot share that state. See the module docstring note in the README/commit
for the trade-off. The full re-clone of every repo on each run is already
avoided by the default forceUpdate=False behaviour.
"""
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Order matters only for clone reuse, not correctness: FPGA before RT lets the
# single Chakraborty_cRIO full clone happen once (in FPGA), after which RT just
# fetches the existing checkout.
GENERATORS = [
    "Generate_PPL_Pipelines.py",
    "Generate_FPGA_Pipelines.py",
    "Generate_RT_Pipeline.py",
]


def run_generator(script_name):
    script_path = SCRIPT_DIR / script_name
    print(f"\n=== Running {script_name} ===", flush=True)
    start = time.perf_counter()
    # Inherit cwd so every generator shares the same ./cloned directory.
    result = subprocess.run([sys.executable, str(script_path)])
    elapsed = time.perf_counter() - start
    print(
        f"=== {script_name} finished in {elapsed:0.2f}s (exit {result.returncode}) ===",
        flush=True,
    )
    return result.returncode, elapsed


def main():
    overall_start = time.perf_counter()
    timings = []
    for script_name in GENERATORS:
        returncode, elapsed = run_generator(script_name)
        timings.append((script_name, elapsed))
        if returncode != 0:
            print(
                f"\n{script_name} failed with exit code {returncode}; aborting.",
                file=sys.stderr,
            )
            return returncode

    total = time.perf_counter() - overall_start
    print("\n=== Summary ===")
    for script_name, elapsed in timings:
        print(f"  {script_name}: {elapsed:0.2f}s")
    print(f"  Total: {total:0.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
