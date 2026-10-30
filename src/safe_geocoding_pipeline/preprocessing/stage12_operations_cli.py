"""Explicit O-r2 public execution; legacy stage12_probe_cli is unchanged."""

import argparse
from pathlib import Path
from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm
from .stages import s12_public_runtime as runtime
from .stages import s12_storage as io
from .stages import s12_retrieval_contract as c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--configuration-sha256", required=True)
    parser.add_argument("--review-binding", type=Path, required=True)
    parser.add_argument("--review-binding-sha256", required=True)
    parser.add_argument("--implementation-sha", required=True)
    args = parser.parse_args()
    try:
        require_goethe_nhr_slurm("stage12 O-r2 public startup")
        raw = io.read(args.configuration)
        review = io.read(args.review_binding)
        c.require(
            c.sha(raw).hex() == args.configuration_sha256
            and c.sha(review).hex() == args.review_binding_sha256,
            "PUBLIC_PROBE_INPUT_IDENTITY_MISMATCH",
        )
        c.require(
            args.configuration.parent == args.review_binding.parent,
            "PUBLIC_PROBE_AUTHORITY_BUNDLE_MISMATCH",
        )
        result = runtime.execute(
            io.metadata(raw),
            bundle=args.configuration.parent,
            review=io.metadata(review),
            review_hash=args.review_binding_sha256,
            repository=Path(__file__).resolve().parents[3],
            git_sha=args.implementation_sha,
        )
        print(c.canonical(result).decode("ascii"), end="")
        return (
            0
            if len(result["completed_phases"]) == 3
            and 40 in result["qualified_public_rates"]
            else 1
        )
    except Exception:
        # No arbitrary exception/response/configuration/credential echo.
        print(
            '{"status":"STOPPED","reason":"PUBLIC_OR2_PREFLIGHT_OR_EXECUTION_FAILED"}'
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
