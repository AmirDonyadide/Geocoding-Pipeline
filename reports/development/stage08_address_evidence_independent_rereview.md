# Stage 8 address-evidence independent rereview

## Verdict

`STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REREVIEW_FAIL`

Affected reporting candidate:
`70e3de9536aee7074e27018d39e0164f3a2200ae`.

Affected executable:
`bdea7232a3f92ebd381be87610b753b8e4c35481`.

Defect class: `publication`.

## Blocking defect

Policy-A adoption verifies the final path's captured device/inode identity,
then fsyncs the parent and performs the complete final reopen validation. It
does not re-observe the final path identity after either operation. A
byte-identical directory with a different inode can replace the final path in
that interval. The complete candidate validator then passes and the
materializer returns success even though the exact captured owned publication
is no longer at the final path.

This falsifies the required invariant that every success-returning invocation
has the exact complete validated owned final publication at the final path. It
also demonstrates that final-path replacement can trick adoption.

## Shortest independent reproduction

The independent synthetic harness:

1. invokes the real Stage 8 materializer on independently constructed
   synthetic Stage 6 and Stage 7 relations;
2. wraps the real rename with `os.rename`, verifies without following symlinks
   that TEMP disappeared and FINAL appeared with the captured identity, and
   then raises;
3. first confirms the ordinary post-effect exception is correctly adopted;
4. in a separate run, creates a byte-identical directory with a different
   inode and swaps it into FINAL after `_verify_post_rename_state` but during
   the immediately following parent-fsync call;
5. allows the real parent-directory fsync and complete final reopen validator
   to finish; and
6. independently confirms that the materializer returned success, FINAL has a
   different inode from the captured attempt, and FINAL passes the Stage 8
   validator.

The original owned tree remains separately visible with its success marker in
the synthetic reproduction. No protected value or artifact is used.

## Stop decision

The controlled job `1764219` artifact was not accessed. No Goethe review job
was submitted. The reviewed candidate branch remained unchanged. Return Stage
8 to DEVELOPMENT without repair in this session.
