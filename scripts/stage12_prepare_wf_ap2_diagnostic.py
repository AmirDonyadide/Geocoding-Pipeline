"""Canonicalize a supplied prospective AP2 diagnostic draft; issue no authority.

Profiles, plans, starts, public response provenance and finite resource values
must be supplied. This does not invent a memory record or inspect a host/kernel.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path

from stage12_wf_ap2_diagnostic import canonical, validate_envelope, validate_workloads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.draft.open("rb") as stream:
        raw = stream.read(64 * 2**20 + 1)
    if len(raw) > 64 * 2**20:
        raise RuntimeError("AP2_DIAGNOSTIC_INPUT_INVALID")
    value = json.loads(raw)
    validate_envelope(value, args.source_sha, for_execution=False)
    if value["selection"]["status"] != "UNISSUED":
        raise RuntimeError("AP2_DIAGNOSTIC_PREPARER_CANNOT_ISSUE")
    validate_workloads(value)
    encoded = canonical(value)
    if len(encoded) > value["limits"]["maximum_input_bytes"]:
        raise RuntimeError("AP2_DIAGNOSTIC_INPUT_INVALID")
    fd = os.open(
        args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    print(
        json.dumps(
            dict(
                status="UNISSUED_NON_EXECUTABLE",
                bytes=len(encoded),
                sha256=hashlib.sha256(encoded).hexdigest(),
            )
        )
    )


if __name__ == "__main__":
    main()
