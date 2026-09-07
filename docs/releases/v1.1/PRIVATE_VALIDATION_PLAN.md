# Private validation plan for v1.1 scientific-core changes

## Public-repository boundary

Private biological AB1 files, research metadata, and generated research
outputs must remain outside public Git history. Public synthetic or explicitly
approved fixtures may be used for ordinary automated tests, but they do not
replace controlled private validation.

The repository already defines the `private_validation` pytest marker. The
existing private consensus-review bridge test obtains local AB1 paths from
environment variables rather than versioning the files. Keep that mechanism
separate from the public release gate.

## Local validation set

Maintain an external, non-versioned validation collection with at least these
categories:

- clean F/R pair;
- noisy pair;
- one low-quality direction;
- short overlap;
- disagreement/conflict;
- indel-like sequencing artifact;
- orphan Forward read;
- orphan Reverse read;
- ambiguous bases; and
- poor-quality ends.

No directory name, local path, sequence, or metadata value is prescribed by
this document. Local operators are responsible for configuring the private
paths required by marked tests.

## Comparison procedure

For any proposed scientific-core change:

1. Record the v1.0.0 result and relevant evidence/coordinates for each case.
2. Run the candidate implementation without changing the public fixture set.
3. Compare pairing state, trimming, alignment, consensus candidate, review
   evidence, and reviewed output where applicable.
4. Investigate every difference; do not assume a changed result is an
   improvement.
5. Retain the comparison record outside the public repository unless it is
   explicitly anonymized and approved for publication.

UI-only work should still confirm that the same inputs yield the same
scientific outputs.
