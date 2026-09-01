# SangerFlow

SangerFlow is an open-source desktop application for transparent,
provenance-aware Sanger sequencing workflows. Its official interface is
**SangerFlow Studio**, built with PySide6/Qt.

## v1.0 features

- AB1 and sequence-file import, chromatogram inspection, quality review, and
  trimming.
- Sequence editing, forward/reverse consensus review, and reviewed-consensus
  output.
- Sample-metadata import, Project Records filtering, and derived Dataset
  creation.
- MAFFT alignment, alignment editing, and chromatogram-evidence review.
- NCBI BLAST online and official website/XML-import workflows.
- Immutable Dataset revisions, provenance-aware projects, and project
  save/reload.
- FASTA, NEXUS, PHYLIP, PopART NEXUS, and applicable result exports.

## Typical workflow

```text
AB1 import
→ QC and trimming
→ sequence editing or F/R consensus review
→ metadata import and cross-dataset selection
→ derived Dataset
→ BLAST and/or MAFFT alignment
→ evidence review and export
```

## Installation from source

SangerFlow requires Python 3.10 or later. Python 3.12 matches the public CI
configuration.

```bash
git clone https://github.com/cosakichrnitw-dot/SangerFlow.git
cd SangerFlow
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Start Studio:

```bash
cd SangerFlow-Studio
PYTHONPATH=.. python -m app.main
```

The legacy Tkinter GUI remains in the repository for historical/reference use,
but it is not a supported v1.0 workflow.

## External services and tools

- **MAFFT** is an optional external executable required for alignment. Install
  it separately and configure its path in Studio when needed.
- **NCBI BLAST** requires network access. Online queries are submitted to NCBI;
  use the website/XML-import workflow when you prefer to run a search on the
  official NCBI site yourself. Do not submit sensitive or unpublished sequence
  data unless that is appropriate for your research and institutional policy.
- **BOLD online identification** is not supported in v1.0.

## Platforms and packaging

Public CI covers source installs on macOS and Windows. Primary hands-on
validation has been performed on macOS Apple Silicon. A signed/notarized public
macOS application is not yet published; packaging instructions are available
for maintainers in [packaging/macos/README.md](packaging/macos/README.md).

## Data and project files

SangerFlow project files preserve datasets, revisions, provenance, and analysis
results. Keep independent backups of research data and review all quality,
consensus, and identification decisions before drawing biological conclusions.
Never upload unpublished AB1/ABI files, sequence exports, `.sangerflow`
projects, or sensitive metadata in a public issue.

## Documentation

- [Current Status](docs/CURRENT_STATUS.md) — v1.0 support boundary and test tiers.
- [Workflow](docs/Workflow.md) — Studio workflow and requirements.
- [BLAST status](docs/BLAST_CURRENT_STATUS.md) — NCBI BLAST support notes.
- [Architecture](docs/Architecture.md) — code and data-flow architecture.
- [Contributing](CONTRIBUTING.md) — development setup and contribution safeguards.
- [Security policy](SECURITY.md) — responsible disclosure guidance.

Documents described as design, migration, or historical Tkinter references are
not v1.0 user instructions. They remain in the repository to preserve project
history and design context.

## Citation

Please use the metadata in [CITATION.cff](CITATION.cff) when citing SangerFlow.

## License and notices

SangerFlow is released under the [MIT License](LICENSE). Third-party components
remain subject to their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Project-original and commissioned icon assets are described in
[PROJECT_ASSETS_NOTICE.md](PROJECT_ASSETS_NOTICE.md).
