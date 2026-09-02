# Stage 8 independent rereview harness failure

## Classification

`STAGE08_INDEPENDENT_REREVIEW_HARNESS_FAILURE`

Review job `1764372` failed after four seconds with exit `2:0` and empty
stderr. Its evidence SHA-256 is
`5b7a2906e8d97f9268f09aa8f1f22f6a3d45480d2ea10ff0344606d82d0f25d9`.
It stopped before protected row values were read.

The failure code `ARTIFACT_FILESYSTEM_IDENTITY_MISMATCH` came from an invalid
review-harness assumption: a later independent SLURM job was required to see
the publication-time `(st_dev, st_ino)` recorded by job `1764273`. That pair
is intra-invocation ownership evidence for the Stage 8 publication state
machine, not a frozen cross-job artifact identity.

Job `1764372` is not evidence that candidate
`231cdbf9db755fb56486c46b3b3faa02f5b5f3b6`, executable
`c04cb97214a9f1e5d2b80512c756400321eefa80`, or the controlled artifact
failed. The candidate and artifact were not modified or rematerialized.

## Corrected independent identity rule

The replacement harness does not compare its current device/inode pair to job
`1764273`. It requires the exact path to be a no-follow real directory with
owner-only permissions and verifies the complete terminal topology, manifest
SHA, success binding, manifest-listed file inventory and file hashes, row
counts, relation/logical fingerprints, Stage 6/7 bindings, and logical dataset
SHA. The job-`1764273` device/inode pair remains historical execution evidence
only.

Parser, reference, network, and geocoder calls were zero. HOLDOUT and
production access were false.
