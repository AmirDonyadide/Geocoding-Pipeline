#!/usr/bin/env bash

# Build the exact Python argv used at the Stage 7 public bundle publication
# boundary. Every value-bearing option uses --option=value framing so a value
# beginning with "-" cannot be reinterpreted by argparse as another option.
stage07_second_parser_bundle_publish_argv() {
  if [[ "$#" -lt 7 ]]; then
    echo "STAGE07_SECOND_PARSER_PUBLISH_ARGV_INVALID" >&2
    return 2
  fi

  local python_executable="$1"
  local staging_directory="$2"
  local output_directory="$3"
  local execution_git_sha="$4"
  local compiler_identity="$5"
  local glibc_identity="$6"
  shift 6

  STAGE07_SECOND_PARSER_PUBLISH_ARGV=(
    "${python_executable}"
    -m
    safe_geocoding_pipeline.preprocessing.stage07_second_parser_bundle_cli
    publish
    "--staging-directory=${staging_directory}"
    "--output-directory=${output_directory}"
    "--execution-git-sha=${execution_git_sha}"
    "--compiler-identity=${compiler_identity}"
    "--glibc-identity=${glibc_identity}"
  )

  local configure_argument
  for configure_argument in "$@"; do
    STAGE07_SECOND_PARSER_PUBLISH_ARGV+=(
      "--python-configure-argument=${configure_argument}"
    )
  done
}
