from __future__ import annotations

import os
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing import stage07_bundle_cli
from safe_geocoding_pipeline.preprocessing.stages.s07_parser_bundle import (
    LIBPOSTAL_SOURCE_COMMIT,
    PYPPOSTAL_SOURCE_COMMIT,
    ParserBundleBuildIdentity,
    Stage07ParserBundleError,
    publish_parser_bundle,
    validate_parser_bundle,
)


def _build_identity() -> ParserBundleBuildIdentity:
    return ParserBundleBuildIdentity(
        execution_git_sha="1" * 40,
        compiler_identity="synthetic gcc",
        base_python_identity="Python 3.14.3 / Unicode 16.0.0",
        glibc_identity="glibc synthetic",
    )


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _synthetic_staging(root: Path) -> Path:
    staging = root / "bundle.in_progress"
    files = {
        "lib/libpostal.so.1.0.1": b"synthetic shared library",
        "lib/libpostal.so.1": b"synthetic shared library",
        "lib/libpostal.so": b"synthetic shared library",
        "data/libpostal/data_version": b"v1\n",
        "data/libpostal/parser/parser.dat": b"synthetic parser model",
        "python/postal/__init__.py": b"",
        "python/postal/parser.py": b"def parse_address(value): return []\n",
        "python/postal/_parser.synthetic.so": b"synthetic extension",
        "python/postal-1.1.11.dist-info/METADATA": b"Version: 1.1.11\n",
        "python/six.py": b"__version__ = '1.17.0'\n",
        "python/six-1.17.0.dist-info/METADATA": b"Version: 1.17.0\n",
        "licenses/libpostal-LICENSE": b"MIT synthetic fixture\n",
        "licenses/libpostal-sparkey-LICENSE": b"Apache synthetic fixture\n",
        "licenses/pypostal-LICENSE": b"MIT synthetic fixture\n",
    }
    for relative, payload in files.items():
        path = staging / relative
        _private_directory(path.parent)
        path.write_bytes(payload)
        path.chmod(0o600)
    for path in staging.rglob("*"):
        if path.is_dir():
            path.chmod(0o700)
    staging.chmod(0o700)
    return staging


def test_parser_bundle_publish_and_full_revalidation(tmp_path: Path) -> None:
    staging = _synthetic_staging(tmp_path)
    output = tmp_path / "frozen_bundle"
    outcome = publish_parser_bundle(staging, output, build_identity=_build_identity())

    assert not staging.exists()
    assert output.is_dir()
    assert outcome.artifact_count == 14
    assert len(outcome.parser_bundle_fingerprint) == 64
    assert len(outcome.parser_model_data_fingerprint) == 64
    assert len(outcome.pypostal_runtime_fingerprint) == 64
    assert len(outcome.libpostal_shared_library_sha256) == 64
    assert (
        validate_parser_bundle(
            output,
            expected_parser_bundle_fingerprint=outcome.parser_bundle_fingerprint,
        )
        == outcome
    )
    assert all(
        (path.stat().st_mode & 0o777) == (0o700 if path.is_dir() else 0o600)
        for path in (output, *output.rglob("*"))
    )


def test_parser_bundle_mutation_and_wrong_fingerprint_fail(tmp_path: Path) -> None:
    outcome = publish_parser_bundle(
        _synthetic_staging(tmp_path),
        tmp_path / "frozen_bundle",
        build_identity=_build_identity(),
    )
    with pytest.raises(Stage07ParserBundleError, match="FINGERPRINT_MISMATCH"):
        validate_parser_bundle(
            outcome.output_directory,
            expected_parser_bundle_fingerprint="0" * 64,
        )

    model = outcome.output_directory / "data/libpostal/parser/parser.dat"
    model.write_bytes(b"changed")
    model.chmod(0o600)
    with pytest.raises(Stage07ParserBundleError, match="MANIFEST_INVALID"):
        validate_parser_bundle(
            outcome.output_directory,
            expected_parser_bundle_fingerprint=outcome.parser_bundle_fingerprint,
        )


def test_parser_bundle_rejects_symlink_permission_and_collision(
    tmp_path: Path,
) -> None:
    staging = _synthetic_staging(tmp_path)
    target = staging / "licenses/libpostal-LICENSE"
    link = staging / "licenses/linked-license"
    link.symlink_to(target)
    with pytest.raises(Stage07ParserBundleError, match="SYMLINK_PROHIBITED"):
        publish_parser_bundle(
            staging, tmp_path / "frozen_bundle", build_identity=_build_identity()
        )

    link.unlink()
    target.chmod(0o644)
    with pytest.raises(Stage07ParserBundleError, match="PERMISSION_FAILURE"):
        publish_parser_bundle(
            staging, tmp_path / "frozen_bundle", build_identity=_build_identity()
        )

    target.chmod(0o600)
    output = tmp_path / "frozen_bundle"
    _private_directory(output)
    with pytest.raises(Stage07ParserBundleError, match="OUTPUT_COLLISION"):
        publish_parser_bundle(staging, output, build_identity=_build_identity())


def test_parser_bundle_rejects_holdout_path(tmp_path: Path) -> None:
    staging = _synthetic_staging(tmp_path)
    with pytest.raises(Stage07ParserBundleError, match="HOLDOUT_ACCESS_PROHIBITED"):
        publish_parser_bundle(
            staging,
            tmp_path / "sealed_holdout" / "bundle",
            build_identity=_build_identity(),
        )


def test_bundle_cli_requires_goethe_slurm_before_path_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stage07-bundle",
            "validate",
            "--output-directory",
            str(tmp_path / "missing"),
            "--expected-parser-bundle-fingerprint",
            "0" * 64,
        ],
    )
    assert stage07_bundle_cli.main() == 1
    assert "HEAVY_PROCESS_CLUSTER_REQUIRED" in capsys.readouterr().err


def test_stage07_bundle_launcher_is_exact_public_only() -> None:
    repository = Path(__file__).resolve().parents[1]
    launcher = (
        repository / "cluster/goethe_nhr/stage07_build_parser_bundle.sbatch"
    ).read_text(encoding="utf-8")
    assert LIBPOSTAL_SOURCE_COMMIT in launcher
    assert PYPPOSTAL_SOURCE_COMMIT in launcher
    assert "libpostal.so.1.0.1" in launcher
    assert "libpostal.so.1.1.4" not in launcher
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in launcher
    assert "SLURM_JOB_ID:?SLURM_JOB_ID is required" in launcher
    assert "libtool-2.4.6.tar.gz" in launcher
    assert "https://mirrors.ibiblio.org/gnu/libtool/" in launcher
    assert "https://ftp.gnu.org/" not in launcher
    assert (
        "e3bd4d5d3d025a36c21dd6af7ea818a2afcd4dfc1ea5a17b39d7854bcd0c06e3" in launcher
    )
    assert '"${LIBTOOL_PREFIX}/bin/libtoolize" --copy --force' in launcher
    assert '"${LIBTOOL_PREFIX}/bin/libtoolize" --version' in launcher
    assert 'PATH="${LIBTOOL_PREFIX}/bin:${PATH}" ./bootstrap.sh' in launcher
    assert "protected_inputs_opened=false" in launcher
    assert "/scratch" not in launcher
    assert "/work/footprint/public" not in launcher
    assert "rsync" not in launcher
    assert "git pull" not in launcher
    assert "stage06" not in launcher.casefold()
    assert "holdout" in launcher.casefold()


def test_build_identity_rejects_non_exact_commit(tmp_path: Path) -> None:
    with pytest.raises(Stage07ParserBundleError, match="INVALID_GIT_COMMIT"):
        publish_parser_bundle(
            _synthetic_staging(tmp_path),
            tmp_path / "frozen_bundle",
            build_identity=ParserBundleBuildIdentity(
                execution_git_sha="short",
                compiler_identity="synthetic gcc",
                base_python_identity="Python 3.14.3",
                glibc_identity="glibc synthetic",
            ),
        )


def test_synthetic_bundle_contains_no_environment_specific_path(
    tmp_path: Path,
) -> None:
    outcome = publish_parser_bundle(
        _synthetic_staging(tmp_path),
        tmp_path / "frozen_bundle",
        build_identity=_build_identity(),
    )
    manifest = (
        outcome.output_directory / "stage07_parser_bundle_manifest.json"
    ).read_text(encoding="utf-8")
    assert str(tmp_path) not in manifest
    assert os.environ.get("HOME", "not-present") not in manifest
