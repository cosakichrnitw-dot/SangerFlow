# Scientific core stability policy for v1.1

## Purpose

v1.1 development begins from the v1.0.0 scientific baseline. The following
implemented workflow is treated as scientific core:

```text
AB1
→ trimming
→ F/R orientation
→ pair alignment
→ consensus candidate
→ evidence review
→ reviewed consensus
```

The stages are represented by the existing AB1/read models, trimming helpers,
filename-based F/R classification, coordinate-preserving `PairAlignment`,
production pair-consensus builder, review models, and reviewed-consensus
dataset adapter. This policy does not redefine their algorithms.

## Stability rules

- GUI refactoring must not silently change scientific output.
- A change to alignment, trimming, consensus, quality interpretation, or any
  coordinate mapping requires explicit validation against the v1.0 baseline.
- Scientific algorithm changes must be isolated from cosmetic and UI changes.
- A production algorithm must not be replaced without regression and, where
  appropriate, benchmark evidence.
- Raw evidence and its existing coordinate references must remain recoverable
  throughout review.
- F/R reads and orphan reads must never be silently discarded.

## Candidate and shadow implementations

The existing `core/consensus_v2.py`, `core/consensus_v2_1.py`, and
`core/consensus_experimental.py` describe experimental or shadow candidate
calculations. They remain non-production unless an intentionally scoped
validation and promotion decision changes that status. Their presence must not
silently alter the production pair-consensus path.

## Evidence, decision, reviewed dataset

The review boundary is:

```text
Evidence → Decision → Reviewed Dataset
```

- Evidence is traceable to the existing pair alignment and source-read
  coordinates.
- Decisions are recorded separately from the candidate; the review session is
  append-only and does not mutate the candidate.
- A reviewed result is derived from the original candidate plus recorded human
  decisions, then can be projected into a reviewed-consensus dataset with
  provenance.

This separation is required so review remains auditable and raw chromatogram
evidence can be revisited.

## Validation expectation

Every proposed scientific-core change must state: the affected stage, the
expected output/coordinate impact, the relevant automated regression tests,
and the private validation cases required before promotion. UI-only work should
state explicitly that it does not change scientific output.
