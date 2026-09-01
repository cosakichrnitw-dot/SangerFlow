# Contributing to SangerFlow

Thank you for helping improve SangerFlow. Please use GitHub issues for bug
reports and feature proposals, and keep reports free of unpublished sequence,
AB1, project, or sensitive metadata files.

## Development setup

SangerFlow requires Python 3.10 or later. A Python 3.12 environment matches
the public CI configuration.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e . pytest
```

Start the official Studio GUI from the repository root:

```bash
cd SangerFlow-Studio
PYTHONPATH=.. python -m app.main
```

MAFFT is an optional external executable required only for alignment work.

## Tests

Run the public release-gate suites before proposing a change:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q tests -m "not legacy_tk and not private_validation"
QT_QPA_PLATFORM=offscreen python -m pytest -q SangerFlow-Studio/tests
python -m compileall -q core workflow export metadata persistence tools gui SangerFlow-Studio
```

`legacy_tk` and `private_validation` are deliberately outside the public v1.0
release gate. Do not add private research data to make a test pass; use a
public-safe synthetic fixture or an explicit opt-in local validation tier.

## Contribution expectations

- Preserve scientific correctness, coordinate semantics, provenance, and
  immutable revision behavior.
- Add focused regression tests for changed behavior.
- Keep reviewable changes small and avoid unrelated formatting changes.
- Do not commit AB1/ABI files, `.sangerflow` projects, unpublished sequences,
  research metadata, generated reports, or credentials.
