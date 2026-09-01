from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing import stage07_second_parser_bundle_cli
from safe_geocoding_pipeline.preprocessing.stages import s07_second_parser_bundle
from safe_geocoding_pipeline.preprocessing.stages.s07_second_parser_bundle import (
    SecondParserBundleBuildIdentity,
    SecondParserTreeEntry,
    Stage07SecondParserBundleError,
    compare_second_parser_bundle_trees,
    fingerprint_second_parser_bundle_tree,
    publish_second_parser_bundle,
    snapshot_second_parser_bundle_tree,
    validate_second_parser_bundle,
)

_PUBLISH_MODULE = (
    "safe_geocoding_pipeline.preprocessing.stage07_second_parser_bundle_cli"
)
_PYTHON_CONFIGURE_ARGUMENTS = (
    "--prefix=<private-python-prefix>",
    "--with-ensurepip=install",
)
_MODEL_REVISION = "4af74dad1d547804dfc2de8f40fb23fbbec5b811"


def _synthetic_public_assets() -> dict[str, bytes]:
    repository = Path(__file__).resolve().parents[1]
    runtime_lock = (
        repository / "docs/scientific_assets/stage07_deepparse_runtime_lock_v1.txt"
    ).read_bytes()
    runtime_hash_lock = (
        repository / "docs/scientific_assets/stage07_deepparse_runtime_hash_lock_v1.txt"
    ).read_bytes()
    return {
        "runtime/bin/python3.13": b"synthetic runtime",
        "runtime/site-packages/huggingface_hub/__init__.py": (
            b"from pathlib import Path\n"
            b"def try_to_load_from_cache(repository, filename, *, cache_dir, revision):\n"
            b"    ref = Path(cache_dir, 'models--deepparse--bpemb-attention', "
            b"'refs', revision).read_text()\n"
            b"    result = Path(cache_dir, 'models--deepparse--bpemb-attention', "
            b"'snapshots', ref, filename)\n"
            b"    return str(result) if result.is_file() else None\n"
        ),
        (
            "cache/models--deepparse--bpemb-attention/snapshots/"
            f"{_MODEL_REVISION}/config.json"
        ): b"{}",
        (
            "cache/models--deepparse--bpemb-attention/snapshots/"
            f"{_MODEL_REVISION}/model.safetensors"
        ): b"weights",
        "cache/models--deepparse--bpemb-attention/refs/main": (
            _MODEL_REVISION.encode("ascii")
        ),
        "cache/multi/multi.wiki.bpe.vs100000.model": b"tokenizer",
        "cache/multi/multi.wiki.bpe.vs100000.d300.w2v.bin": b"embeddings",
        "sources/Python-3.13.15.tgz": b"synthetic cpython source",
        "sources/sqlite-autoconf-3460100.tar.gz": b"synthetic sqlite source",
        "sources/deepparse-0.10.0-py3-none-any.whl": b"synthetic deepparse wheel",
        "sources/bpemb-0.3.6-py3-none-any.whl": b"synthetic bpemb wheel",
        "sources/multi.wiki.bpe.vs100000.d300.w2v.bin.tar.gz": b"synthetic archive",
        "sources/pip-freeze.txt": runtime_lock,
        "sources/stage07_deepparse_runtime_lock_v1.txt": runtime_lock,
        "sources/stage07_deepparse_runtime_hash_lock_v1.txt": runtime_hash_lock,
        "licenses/BPEmb-LICENSE": b"synthetic BPEmb license",
        "licenses/CPython-LICENSE": b"synthetic CPython license",
        "licenses/DeepParse-LICENSE": b"synthetic DeepParse license",
        "licenses/DeepParse-model-card.md": b"synthetic model card",
        "licenses/SQLite-PUBLIC-DOMAIN-NOTICE": b"synthetic SQLite notice",
        "metadata/runtime-identity.json": b"{}\n",
    }


def _identity() -> SecondParserBundleBuildIdentity:
    return SecondParserBundleBuildIdentity(
        execution_git_sha="a" * 40,
        compiler_identity="synthetic gcc",
        glibc_identity="glibc synthetic",
        python_configure_arguments=_PYTHON_CONFIGURE_ARGUMENTS,
    )


@pytest.fixture(autouse=True)
def _synthetic_asset_contract_and_permission_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public_assets = _synthetic_public_assets()
    pinned = {
        path: hashlib.sha256(content).hexdigest()
        for path, content in public_assets.items()
        if path in s07_second_parser_bundle._PINNED_PUBLIC_ARTIFACT_SHA256
    }
    monkeypatch.setattr(
        s07_second_parser_bundle, "_PINNED_PUBLIC_ARTIFACT_SHA256", pinned
    )
    monkeypatch.setattr(
        s07_second_parser_bundle,
        "_PINNED_MODEL_CACHE_FILES",
        frozenset(path for path in pinned if path.startswith("cache/")),
    )
    yield
    for path in sorted(
        tmp_path.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        if path.is_symlink():
            continue
        path.chmod(0o700 if path.is_dir() else 0o600)
    tmp_path.chmod(0o700)


def _staging(tmp_path: Path) -> Path:
    root = tmp_path / "controlled" / "staging"
    for relative in (
        "runtime/bin",
        "runtime/site-packages/huggingface_hub",
        f"cache/models--deepparse--bpemb-attention/snapshots/{_MODEL_REVISION}",
        "cache/models--deepparse--bpemb-attention/refs",
        "cache/multi",
        "sources",
        "licenses",
        "metadata",
    ):
        (root / relative).mkdir(parents=True, mode=0o700, exist_ok=True)
    files = _synthetic_public_assets()
    for relative, content in files.items():
        path = root / relative
        path.write_bytes(content)
        path.chmod(0o700 if relative == "runtime/bin/python3.13" else 0o600)
    for directory in root.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o700)
    root.chmod(0o700)
    return root


def _launcher_publish_argv(
    *,
    staging: Path,
    output: Path,
    execution_git_sha: str = "a" * 40,
    compiler_identity: str = "synthetic gcc",
    glibc_identity: str = "glibc synthetic",
    configure_arguments: tuple[str, ...] = _PYTHON_CONFIGURE_ARGUMENTS,
) -> tuple[str, ...]:
    repository = Path(__file__).resolve().parents[1]
    helper = (
        repository / "cluster/goethe_nhr/stage07_second_parser_bundle_publish_argv.sh"
    )
    shell = r"""
source "$1"
shift
stage07_second_parser_bundle_publish_argv "$@"
printf '%s\0' "${STAGE07_SECOND_PARSER_PUBLISH_ARGV[@]}"
"""
    completed = subprocess.run(
        [
            "bash",
            "-c",
            shell,
            "stage07-publish-argv-test",
            str(helper),
            sys.executable,
            str(staging),
            str(output),
            execution_git_sha,
            compiler_identity,
            glibc_identity,
            *configure_arguments,
        ],
        check=True,
        capture_output=True,
    )
    assert completed.stderr == b""
    return tuple(token.decode("utf-8") for token in completed.stdout.split(b"\0")[:-1])


def test_launcher_exact_publish_argv_survives_shell_and_argparse(
    tmp_path: Path,
) -> None:
    staging = tmp_path / "public staging [synthetic]"
    output = tmp_path / "public output; synthetic"
    configure_arguments = (
        "--prefix=/public synthetic/[prefix]",
        "-Xsynthetic=value with spaces",
        "--with-build-label=public;synthetic",
    )
    compiler_identity = "synthetic gcc 13; make 4"
    glibc_identity = "glibc synthetic (public)"

    argv = _launcher_publish_argv(
        staging=staging,
        output=output,
        compiler_identity=compiler_identity,
        glibc_identity=glibc_identity,
        configure_arguments=configure_arguments,
    )

    assert argv[:5] == (sys.executable, "-B", "-m", _PUBLISH_MODULE, "publish")
    value_tokens = argv[5:]
    assert all(token.startswith("--") and "=" in token for token in value_tokens)
    assert not any(token in configure_arguments for token in value_tokens)
    assert [
        token.removeprefix("--python-configure-argument=")
        for token in value_tokens
        if token.startswith("--python-configure-argument=")
    ] == list(configure_arguments)

    parsed = stage07_second_parser_bundle_cli.build_parser().parse_args(argv[4:])
    assert parsed.staging_directory == staging
    assert parsed.output_directory == output
    assert parsed.execution_git_sha == "a" * 40
    assert parsed.compiler_identity == compiler_identity
    assert parsed.glibc_identity == glibc_identity
    assert tuple(parsed.python_configure_argument) == configure_arguments


def test_exact_launcher_argv_publishes_synthetic_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    staging = _staging(tmp_path)
    output = staging.parent / "published bundle with spaces"
    compiler_identity = "synthetic gcc 13; make 4"
    glibc_identity = "glibc synthetic (public)"
    argv = _launcher_publish_argv(
        staging=staging,
        output=output,
        compiler_identity=compiler_identity,
        glibc_identity=glibc_identity,
    )
    monkeypatch.setattr(
        stage07_second_parser_bundle_cli,
        "require_goethe_nhr_slurm",
        lambda _operation: None,
    )

    assert stage07_second_parser_bundle_cli.main(argv[4:]) == 0
    stdout = capsys.readouterr().out
    assert "status=STAGE07_SECOND_PARSER_BUNDLE_FROZEN" in stdout
    assert "stage07_second_parser_complete_tree_fingerprint=" in stdout
    assert not staging.exists()
    assert output.is_dir()
    assert (output.stat().st_mode & 0o777) == 0o555
    assert ((output / "_SUCCESS.json").stat().st_mode & 0o777) == 0o444
    assert ((output / "runtime/bin/python3.13").stat().st_mode & 0o777) == 0o555

    manifest = json.loads(
        (output / "stage07_second_parser_bundle_manifest.json").read_text()
    )
    assert manifest["scientific_identity"]["python"]["configure_arguments"] == list(
        _PYTHON_CONFIGURE_ARGUMENTS
    )
    assert manifest["scientific_identity"]["build"] == {
        "compiler_identity": compiler_identity,
        "execution_git_sha": "a" * 40,
        "glibc_identity": glibc_identity,
    }
    fingerprint = manifest["second_parser_bundle_fingerprint"]
    validate_second_parser_bundle(
        output,
        expected_second_parser_bundle_fingerprint=fingerprint,
    )


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
    assert manifest["scientific_identity"]["sqlite"] == {
        "configure_arguments": [
            "--disable-shared",
            "--enable-static",
            "CFLAGS=-O2 -fPIC",
            "LIBSQLITE3_LIBS=-lsqlite3 -lm -lz",
        ],
        "license": "PUBLIC_DOMAIN",
        "linkage": "STATIC_IN_CPYTHON_SQLITE3_EXTENSION",
        "source_sha256": (
            "67d3fe6d268e6eaddcae3727fce58fcc8e9c53869bdd07a0c61e38ddf2965071"
        ),
        "version": "3.46.1",
    }
    assert manifest["scientific_identity"]["parser_call"]["caller_preprocessors"] == []
    assert manifest["scientific_identity"]["runtime_dependency_lock"] == {
        "exact_final_freeze_required": True,
        "sha256": "3a4fd33e5530c554125e11b040adeb97828a0381549ac8ca36ce2399711cdc83",
        "source": "MANIFEST_BOUND_PUBLIC_PIP_FREEZE_FROM_JOB_1762661",
        "version": "stage07_deepparse_runtime_lock_v1",
    }
    assert manifest["scientific_identity"]["runtime_acquisition_hash_lock"] == {
        "package_count": 79,
        "provenance_manifest_sha256": (
            "78b1c6e277461c72c893789d9fa2dc91a3fd89c757a8b7026a9c237a28459f32"
        ),
        "require_hashes": True,
        "sha256": "b8663547cc790a05a1ce2ff21810134bea2b0494b5dd17c2fe07d669fdc2aae8",
        "version": "stage07_deepparse_runtime_hash_lock_v1",
    }
    assert manifest["public_assets_only"] is True
    assert manifest["protected_inputs_opened"] is False
    for path in output.rglob("*"):
        if path.is_dir():
            assert stat.S_IMODE(path.stat().st_mode) == 0o555
        elif path == output / "runtime" / "bin" / "python3.13":
            assert stat.S_IMODE(path.stat().st_mode) == 0o555
        else:
            assert stat.S_IMODE(path.stat().st_mode) == 0o444


def test_second_parser_bundle_mutation_fails_closed(tmp_path: Path) -> None:
    staging = _staging(tmp_path)
    output = staging.parent / "bundle"
    result = publish_second_parser_bundle(staging, output, build_identity=_identity())
    runtime = output / "runtime" / "bin" / "python3.13"
    before = fingerprint_second_parser_bundle_tree(output)
    with pytest.raises(PermissionError):
        runtime.write_bytes(b"mutated")
    assert fingerprint_second_parser_bundle_tree(output) == before

    runtime.chmod(0o644)
    runtime.write_bytes(b"owner-authorized synthetic mutation")
    runtime.chmod(0o555)
    with pytest.raises(Stage07SecondParserBundleError) as raised:
        validate_second_parser_bundle(
            output,
            expected_second_parser_bundle_fingerprint=(
                result.second_parser_bundle_fingerprint
            ),
        )
    assert raised.value.code == "SECOND_PARSER_BUNDLE_MANIFEST_MISMATCH"


def test_read_only_bundle_behavior_and_cache_resolution_are_nonmutating(
    tmp_path: Path,
) -> None:
    if os.geteuid() == 0:
        pytest.fail("Read-only permission gate requires an ordinary execution UID")
    staging = _staging(tmp_path)
    output = staging.parent / "bundle"
    publish_second_parser_bundle(staging, output, build_identity=_identity())
    before = snapshot_second_parser_bundle_tree(output)
    before_fingerprint = fingerprint_second_parser_bundle_tree(output)

    with pytest.raises(PermissionError):
        (output / "new-file").write_text("prohibited", encoding="utf-8")
    with pytest.raises(PermissionError):
        (output / "new-directory").mkdir()
    with pytest.raises(PermissionError):
        (output / "sources" / "pip-freeze.txt").write_text(
            "prohibited", encoding="utf-8"
        )

    runtime_state = tmp_path / "external-runtime-state"
    runtime_state.mkdir(mode=0o700)
    (runtime_state / "write-test").write_text("allowed", encoding="utf-8")
    module_root = output / "runtime" / "site-packages"
    model_cache = output / "cache"
    script = (
        "from huggingface_hub import try_to_load_from_cache\n"
        "for name in ('config.json', 'model.safetensors'):\n"
        " result = try_to_load_from_cache('deepparse/bpemb-attention', name, "
        "cache_dir=r'" + str(model_cache) + "', revision='main')\n"
        " assert result is not None\n"
    )
    environment = os.environ.copy()
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    environment.pop("PYTHONPYCACHEPREFIX", None)
    environment["PYTHONPATH"] = str(module_root)
    subprocess.run([sys.executable, "-c", script], check=True, env=environment)
    assert not tuple(output.rglob("__pycache__"))
    assert not tuple(output.rglob("*.pyc"))

    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPYCACHEPREFIX"] = str(runtime_state)
    subprocess.run([sys.executable, "-B", "-c", script], check=True, env=environment)
    after = snapshot_second_parser_bundle_tree(output)
    difference = compare_second_parser_bundle_trees(before, after)
    assert difference.identical
    assert fingerprint_second_parser_bundle_tree(output) == before_fingerprint


def test_tree_difference_reports_every_mutation_category() -> None:
    def entry(
        path: str,
        kind: str,
        mode: str,
        size: int = 0,
        digest: str | None = None,
        target: str | None = None,
    ) -> SecondParserTreeEntry:
        return SecondParserTreeEntry(path, kind, mode, size, digest, target)

    before = (
        entry(".", "DIRECTORY", "0555"),
        entry("same", "FILE", "0444", 1, "a" * 64),
        entry("removed-file", "FILE", "0444", 1, "b" * 64),
        entry("removed-directory", "DIRECTORY", "0555"),
        entry("content", "FILE", "0444", 1, "c" * 64),
        entry("mode", "FILE", "0444", 1, "d" * 64),
    )
    after = (
        entry(".", "DIRECTORY", "0555"),
        entry("same", "FILE", "0444", 1, "a" * 64),
        entry("added-file", "FILE", "0444", 1, "e" * 64),
        entry("new-directory", "DIRECTORY", "0555"),
        entry("new-symlink", "SYMLINK", "0777", 6, target="target"),
        entry("content", "FILE", "0444", 2, "f" * 64),
        entry("mode", "FILE", "0555", 1, "d" * 64),
    )
    assert compare_second_parser_bundle_trees(before, after).to_dict() == {
        "added": 3,
        "removed": 2,
        "content_modified": 1,
        "mode_modified": 1,
        "new_directories": 1,
        "removed_directories": 1,
        "new_symlinks": 1,
        "identical": False,
    }


def test_second_parser_bundle_permission_failure(tmp_path: Path) -> None:
    staging = _staging(tmp_path)
    (staging / "sources" / "pip-freeze.txt").chmod(0o644)
    with pytest.raises(Stage07SecondParserBundleError) as raised:
        publish_second_parser_bundle(
            staging, staging.parent / "bundle", build_identity=_identity()
        )
    assert raised.value.code == "PERMISSION_FAILURE"


def test_second_parser_bundle_rejects_bytecode_before_publication(
    tmp_path: Path,
) -> None:
    staging = _staging(tmp_path)
    bytecode = staging / "runtime" / "site-packages" / "synthetic.pyc"
    bytecode.write_bytes(b"synthetic bytecode")
    bytecode.chmod(0o600)
    with pytest.raises(Stage07SecondParserBundleError) as raised:
        publish_second_parser_bundle(
            staging, staging.parent / "bundle", build_identity=_identity()
        )
    assert raised.value.code == "SECOND_PARSER_BYTECODE_CACHE_PROHIBITED"


def test_second_parser_bundle_rejects_wrong_pinned_asset(
    tmp_path: Path,
) -> None:
    staging = _staging(tmp_path)
    weights = staging / (
        "cache/models--deepparse--bpemb-attention/snapshots/"
        f"{_MODEL_REVISION}/model.safetensors"
    )
    weights.write_bytes(b"wrong synthetic weights")
    with pytest.raises(Stage07SecondParserBundleError) as raised:
        publish_second_parser_bundle(
            staging, staging.parent / "bundle", build_identity=_identity()
        )
    assert raised.value.code == "SECOND_PARSER_PINNED_ARTIFACT_HASH_MISMATCH"


def test_second_parser_bundle_rejects_external_hard_link(tmp_path: Path) -> None:
    staging = _staging(tmp_path)
    os.link(
        staging / "metadata/runtime-identity.json",
        staging / "metadata/runtime-identity-alias.json",
    )
    with pytest.raises(Stage07SecondParserBundleError) as raised:
        publish_second_parser_bundle(
            staging, staging.parent / "bundle", build_identity=_identity()
        )
    assert raised.value.code == "SECOND_PARSER_BUNDLE_HARD_LINK_PROHIBITED"


def test_atomic_publication_never_replaces_racing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = _staging(tmp_path)
    output = staging.parent / "bundle"
    real_rename = s07_second_parser_bundle._atomic_rename_directory_no_replace

    def create_collision_then_rename(source: Path, destination: Path) -> None:
        destination.mkdir(mode=0o700)
        (destination / "preexisting").write_text("preserve", encoding="utf-8")
        real_rename(source, destination)

    monkeypatch.setattr(
        s07_second_parser_bundle,
        "_atomic_rename_directory_no_replace",
        create_collision_then_rename,
    )
    with pytest.raises(Stage07SecondParserBundleError) as raised:
        publish_second_parser_bundle(staging, output, build_identity=_identity())
    assert raised.value.code == "OUTPUT_COLLISION"
    assert (output / "preexisting").read_text(encoding="utf-8") == "preserve"
    assert staging.exists()


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


def test_second_parser_launcher_pins_required_sqlite_runtime() -> None:
    repository = Path(__file__).resolve().parents[1]
    launcher = (
        repository / "cluster/goethe_nhr/stage07_build_second_parser_bundle.sbatch"
    ).read_text()
    assert 'readonly SQLITE_VERSION="3.46.1"' in launcher
    assert (
        'readonly SQLITE_SHA256="67d3fe6d268e6eaddcae3727fce58fcc'
        '8e9c53869bdd07a0c61e38ddf2965071"'
    ) in launcher
    assert "--disable-shared" in launcher
    assert 'LIBSQLITE3_LIBS="-L${SQLITE_PREFIX}/lib -lsqlite3 -lm -lz"' in launcher
    assert 'assert sqlite3.sqlite_version == "3.46.1"' in launcher
    assert "--no-compile" in launcher
    assert "STAGE07_SECOND_PARSER_BUILD_TOOL_MISSING" in launcher
    assert "STAGE07_SECOND_PARSER_BYTECODE_CACHE_PROHIBITED" in launcher
    assert '"pymagnitudelight"' in launcher
    assert '"sentencepiece"' in launcher
    assert "readelf" in launcher
    assert "ldd" in launcher
    assert 'printf \'%s\' "${MODEL_REVISION}" > "${HF_REFS}/main"' in launcher
    assert '"$(wc -c < "${HF_REFS}/main")" -eq 40' in launcher
    assert "public_huggingface_cache_binding=PASS" in launcher
    assert 'revision="main"' in launcher
    assert "stage07_second_parser_bundle_publish_argv" in launcher
    assert '"${STAGE07_SECOND_PARSER_PUBLISH_ARGV[@]}"' in launcher
    assert "stage07_second_parser_bind_runtime_state" in launcher
    assert '"${PUBLISHED_PYTHON}" -B' in launcher
    assert "STAGE07_SECOND_PARSER_MODEL_CACHE" in launcher
    assert "stage07_second_parser_complete_tree_fingerprint" in launcher
    assert "postpublication_tree_fingerprint_match=true" in launcher
    assert "STAGE07_SECOND_PARSER_WRITABLE_BUNDLE_PATH_PROHIBITED" in launcher
    runtime_lock = (
        repository / "docs/scientific_assets/stage07_deepparse_runtime_lock_v1.txt"
    ).read_bytes()
    assert len(runtime_lock) == 1433
    assert hashlib.sha256(runtime_lock).hexdigest() == (
        "3a4fd33e5530c554125e11b040adeb97828a0381549ac8ca36ce2399711cdc83"
    )
    runtime_hash_lock = (
        repository / "docs/scientific_assets/stage07_deepparse_runtime_hash_lock_v1.txt"
    ).read_bytes()
    assert len(runtime_hash_lock.splitlines()) == 79
    assert hashlib.sha256(runtime_hash_lock).hexdigest() == (
        "b8663547cc790a05a1ce2ff21810134bea2b0494b5dd17c2fe07d669fdc2aae8"
    )
    assert 'readonly RUNTIME_LOCK_SHA256="3a4fd33e5530c554125e11b040adeb978' in launcher
    assert '--requirement "${RUNTIME_HASH_LOCK}"' in launcher
    assert "--require-hashes" in launcher
    assert 'cmp "${RUNTIME_LOCK}" "${PUBLIC_DOWNLOADS}/pip-freeze.txt"' in launcher
    assert launcher.count("--no-deps") >= 2
