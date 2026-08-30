from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages.s07_second_parser_bundle import (
    SecondParserBundleBuildIdentity,
    Stage07SecondParserBundleError,
    publish_second_parser_bundle,
    validate_second_parser_bundle,
)


def _identity() -> SecondParserBundleBuildIdentity:
    return SecondParserBundleBuildIdentity(
        execution_git_sha="a" * 40,
        compiler_identity="synthetic gcc",
        glibc_identity="glibc synthetic",
        python_configure_arguments=(
            "--prefix=<private-python-prefix>",
            "--with-ensurepip=install",
        ),
    )


def _staging(tmp_path: Path) -> Path:
    root = tmp_path / "controlled" / "staging"
    for relative in (
        "runtime/bin",
        "cache/models--deepparse--bpemb-attention/snapshots/revision",
        "cache/multi",
        "sources",
        "licenses",
        "metadata",
    ):
        (root / relative).mkdir(parents=True, mode=0o700, exist_ok=True)
    files = {
        "runtime/bin/python3.13": b"synthetic runtime",
        "cache/models--deepparse--bpemb-attention/snapshots/revision/config.json": b"{}",
        "cache/models--deepparse--bpemb-attention/snapshots/revision/model.safetensors": b"weights",
        "cache/multi/multi.wiki.bpe.vs100000.model": b"tokenizer",
        "cache/multi/multi.wiki.bpe.vs100000.d300.w2v.bin": b"embeddings",
        "sources/pip-freeze.txt": b"deepparse==0.10.0\n",
        "licenses/DeepParse-LICENSE": b"LGPL synthetic fixture",
        "metadata/runtime-identity.json": b"{}\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.write_bytes(content)
        path.chmod(0o700 if relative == "runtime/bin/python3.13" else 0o600)
    for directory in root.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o700)
    root.chmod(0o700)
    return root


def test_publish_and_reopen_second_parser_bundle(tmp_path: Path) -> None:
    staging = _staging(tmp_path)
    output = staging.parent / "bundle"
    result = publish_second_parser_bundle(staging, output, build_identity=_identity())
    reopened = validate_second_parser_bundle(
        output,
        expected_second_parser_bundle_fingerprint=(
            result.second_parser_bundle_fingerprint
        ),
    )
    assert reopened == result
    manifest = json.loads(
        (output / "stage07_second_parser_bundle_manifest.json").read_text()
    )
    assert manifest["scientific_identity"]["model"]["revision"] == (
        "4af74dad1d547804dfc2de8f40fb23fbbec5b811"
    )
    assert manifest["scientific_identity"]["parser_call"]["caller_preprocessors"] == []
    assert manifest["public_assets_only"] is True
    assert manifest["protected_inputs_opened"] is False


def test_second_parser_bundle_mutation_fails_closed(tmp_path: Path) -> None:
    staging = _staging(tmp_path)
    output = staging.parent / "bundle"
    result = publish_second_parser_bundle(staging, output, build_identity=_identity())
    runtime = output / "runtime" / "bin" / "python3.13"
    runtime.write_bytes(b"mutated")
    runtime.chmod(0o700)
    with pytest.raises(Stage07SecondParserBundleError) as raised:
        validate_second_parser_bundle(
            output,
            expected_second_parser_bundle_fingerprint=(
                result.second_parser_bundle_fingerprint
            ),
        )
    assert raised.value.code == "SECOND_PARSER_BUNDLE_MANIFEST_MISMATCH"


def test_second_parser_bundle_permission_failure(tmp_path: Path) -> None:
    staging = _staging(tmp_path)
    (staging / "sources" / "pip-freeze.txt").chmod(0o644)
    with pytest.raises(Stage07SecondParserBundleError) as raised:
        publish_second_parser_bundle(
            staging, staging.parent / "bundle", build_identity=_identity()
        )
    assert raised.value.code == "PERMISSION_FAILURE"


def test_second_parser_bundle_rejects_holdout_and_collision(tmp_path: Path) -> None:
    staging = _staging(tmp_path)
    output = staging.parent / "bundle"
    output.mkdir(mode=0o700)
    with pytest.raises(Stage07SecondParserBundleError) as collision:
        publish_second_parser_bundle(staging, output, build_identity=_identity())
    assert collision.value.code == "OUTPUT_COLLISION"

    holdout = tmp_path / "HOLDOUT" / "staging"
    holdout.mkdir(parents=True, mode=0o700)
    with pytest.raises(Stage07SecondParserBundleError) as prohibited:
        validate_second_parser_bundle(
            holdout, expected_second_parser_bundle_fingerprint="0" * 64
        )
    assert prohibited.value.code == "HOLDOUT_ACCESS_PROHIBITED"


def test_second_parser_bundle_symlink_rejected(tmp_path: Path) -> None:
    staging = _staging(tmp_path)
    os.symlink(
        staging / "sources" / "pip-freeze.txt",
        staging / "sources" / "linked.txt",
    )
    with pytest.raises(Stage07SecondParserBundleError) as raised:
        publish_second_parser_bundle(
            staging, staging.parent / "bundle", build_identity=_identity()
        )
    assert raised.value.code == "SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED"
