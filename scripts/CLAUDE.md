# scripts/

Python generators that emit GoCD pipeline config (`*.gocd.yaml`) for the
LabVIEW/cRIO build pipelines.

## Running the tests

The test suite uses the standard-library `unittest` framework (no pytest
required). From the `scripts/` directory:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## YAML aliasing

Generated YAML deliberately relies on PyYAML anchors/aliases for
deduplication, which come from **shared object identity**. Module-level
singleton tasks (in `Constants.py`) and the `aliasable(...)` helper
(`PipelineGenerationUtils.py`) exist to preserve that identity. Refactors should
not replace these shared objects with per-use freshly-built copies, or the
aliasing — and the resulting YAML — will change. Seek approval for changes that
will reduce aliasing and increase the size of the resulting YAML.
