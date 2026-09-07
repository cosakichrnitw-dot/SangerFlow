# v1.1 automated-test audit

This is a compact audit of the public v1.0.0 test suite. Assessments describe
automated coverage, not a claim that every scientific condition has been
validated with real biological data.

| Area | Existing tests | Coverage assessment | Missing regression coverage | Priority |
| --- | --- | --- | --- | --- |
| Trimming | `tests/test_chromatogram_alignment.py`, model/workflow tests exercising trimmed reads | Partial | Curated real-read edge cases remain private validation work. | High |
| Quality calculations | consensus, review, and chromatogram tests that carry Phred-quality inputs | Partial | A focused public quality/QC fixture matrix would make threshold and edge behavior clearer. | Medium |
| Reverse complement | `tests/test_reverse_complement.py` | Strong | Real AB1 orientation cases remain outside public fixtures. | Medium |
| Pair alignment | `tests/test_pair_alignment.py`, `tests/test_assembly_models.py`, `tests/test_inspect_pair_alignment.py` | Strong | Private checks for difficult sequencing artifacts. | High |
| F/R pairing | `tests/test_samples.py`, `SangerFlow-Studio/tests/test_fr_consensus_workflow.py` | Strong | Broader filename and ambiguous-pair private validation cases. | High |
| Production consensus | `tests/test_consensus.py`, `tests/test_pair_consensus.py`, `tests/test_review.py` | Strong | Benchmark set before any algorithm promotion. | High |
| Consensus review/session | `tests/test_consensus_review_session.py`, `tests/test_human_review.py`, review viewer/workflow tests | Strong | Human-review acceptance cases with external private data. | High |
| Metadata | `tests/test_sample_metadata.py`, `tests/test_metadata_export.py`, Studio Project Records tests | Strong | Larger mixed-source metadata validation sets. | Medium |
| Project persistence | `tests/test_project_json.py`, `tests/test_project_bundle.py`, Studio bundle-open tests | Strong | Cross-version migration testing when a schema change is proposed. | High |
| Revisions | `tests/test_dataset_revisions.py`, Studio revision workflow and working-view tests | Strong | Long revision-chain acceptance scenario. | Medium |
| Derived datasets | `tests/test_cross_dataset_builder.py`, Studio cross-dataset builder tests | Strong | Collision/provenance cases from independently imported source batches. | Medium |
| MAFFT integration | `tests/test_mafft_workflow.py`, `tests/test_mafft_alignment_dataset.py`, tool-settings tests | Partial | Real executable/platform integration remains environment dependent. | High |
| Offline BLAST logic | `tests/test_blast_result.py`, `tests/test_blast_filter.py`, `tests/test_ncbi_blast_service.py`, `tests/test_ncbi_blast_xml_import.py` | Partial | Live NCBI service behavior is network-dependent and needs controlled manual validation. | Medium |
| Export logic | `tests/test_sequence_export.py`, `tests/test_blast_export.py`, `tests/test_popart_export.py`, `tests/test_partition_export.py`, reviewed-export tests | Strong | External-tool round trips and long-lived compatibility fixtures. | Medium |

`tests/test_consensus_review_bridge.py` contains a `private_validation` case
that resolves input paths through local environment variables. It is explicitly
excluded from the public release gate.
