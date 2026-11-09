"""Explicit O-r2 public execution; legacy stage12_probe_cli is unchanged."""
# ruff: noqa: E402
# The successor task clock includes CLI dependency imports and input preparation.

import time

_ENTRY_MONOTONIC_NS = time.monotonic_ns()

import argparse
from pathlib import Path
from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm
from .stages import s12_public_runtime as runtime
from .stages import s12_storage as io
from .stages import s12_retrieval_contract as c


def result_exit_status(config, result):
    """Keep legacy completion semantics; require both lower-profile phases."""
    if config["version"] in (runtime.MATRIX_VERSION, *runtime.WF_CONFIGS):
        passed = (
            result["full_frozen_capability_matrix_completed"] is True
            and result["completed_phases"] == [x["label"] for x in config["campaigns"]]
            and result["qualified_public_rates"] == []
            and (
                config["version"] not in runtime.WF_CONFIGS
                or result.get("diagnostic_persistence_complete") is True
            )
        )
    elif config["version"] == runtime.LOWER_VERSION:
        passed = result["completed_phases"] == [
            "capability_subset",
            "confirmatory1",
        ] and result["qualified_public_rates"] == [1]
    else:
        passed = (
            len(result["completed_phases"]) == 3
            and 40 in result["qualified_public_rates"]
        )
    return 0 if passed else 1


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
        config = io.metadata(raw)
        result = runtime.execute(
            config,
            bundle=args.configuration.parent,
            review=io.metadata(review),
            review_hash=args.review_binding_sha256,
            repository=Path(__file__).resolve().parents[3],
            git_sha=args.implementation_sha,
            **(
                {"task_started_ns": _ENTRY_MONOTONIC_NS}
                if config.get("version") in runtime.WF_CONFIGS
                else {}
            ),
        )
        print(c.canonical(result).decode("ascii"), end="")
        return result_exit_status(config, result)
    except Exception:
        # No arbitrary exception/response/configuration/credential echo.
        print(
            '{"status":"STOPPED","reason":"PUBLIC_OR2_PREFLIGHT_OR_EXECUTION_FAILED"}'
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
