from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .stages.s07_country_eligibility import Stage07CountryEligibilityError
from .stages.s07_prelaunch import (
    BundlePreflightConfig,
    Stage07PrelaunchError,
    SubmissionPreflightConfig,
    run_bundle_preflight,
    run_submission_preflight,
)
from .stages.s07_second_parser_bundle import Stage07SecondParserBundleError


def _submission_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser("submission")
    parser.add_argument("--controlled-root", required=True, type=Path)
    parser.add_argument("--integration-root", required=True, type=Path)
    parser.add_argument("--expected-git-sha", required=True)
    parser.add_argument("--new-path", action="append", default=[], type=Path)
    parser.add_argument("--required-path", action="append", default=[], type=Path)
    parser.add_argument("--eligibility-manifest", required=True, type=Path)
    parser.add_argument("--launcher", required=True, type=Path)
    parser.add_argument("--requested-memory-gib", required=True, type=int)
    parser.add_argument("--requested-cpus", required=True, type=int)
    parser.add_argument("--requested-walltime", required=True)
    parser.add_argument("--minimum-free-bytes", required=True, type=int)
    parser.add_argument("--minimum-free-inodes", required=True, type=int)
    parser.add_argument("--allow-attached-worktree", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--require-model-offline-environment", action="store_true")
    parser.add_argument("--require-compute-smoke-environment", action="store_true")


def _bundle_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser("bundle")
    parser.add_argument("--bundle-directory", required=True, type=Path)
    parser.add_argument("--expected-bundle-fingerprint", required=True)
    parser.add_argument("--smoke-evidence", type=Path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 7 prelaunch gate")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _submission_parser(subparsers)
    _bundle_parser(subparsers)
    args = parser.parse_args()
    try:
        if args.command == "submission":
            result = run_submission_preflight(
                SubmissionPreflightConfig(
                    controlled_root=args.controlled_root,
                    integration_root=args.integration_root,
                    expected_git_sha=args.expected_git_sha,
                    new_paths=tuple(args.new_path),
                    required_paths=tuple(args.required_path),
                    eligibility_manifest_path=args.eligibility_manifest,
                    launcher_path=args.launcher,
                    requested_memory_gib=args.requested_memory_gib,
                    requested_cpus=args.requested_cpus,
                    requested_walltime=args.requested_walltime,
                    minimum_free_bytes=args.minimum_free_bytes,
                    minimum_free_inodes=args.minimum_free_inodes,
                    require_detached=not args.allow_attached_worktree,
                    network_allowed=args.allow_network,
                    require_model_offline_environment=(
                        args.require_model_offline_environment
                    ),
                    require_compute_smoke_environment=(
                        args.require_compute_smoke_environment
                    ),
                )
            )
        else:
            result = run_bundle_preflight(
                BundlePreflightConfig(
                    bundle_directory=args.bundle_directory,
                    expected_bundle_fingerprint=args.expected_bundle_fingerprint,
                    smoke_evidence_path=args.smoke_evidence,
                )
            )
    except (
        Stage07CountryEligibilityError,
        Stage07PrelaunchError,
        Stage07SecondParserBundleError,
    ) as error:
        print(f"status=STAGE07_PRELAUNCH_GATE_FAIL error={error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
