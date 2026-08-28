from __future__ import annotations

from collections.abc import Iterable
import importlib
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.preprocessing import stage07_supervisor_cli
from safe_geocoding_pipeline.preprocessing.stages.s07_libpostal_adapter import (
    PARSED_EMPTY,
    PARSED_NONEMPTY,
    LibpostalComponent,
    ParsedAddress,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_output_schema import (
    STAGE07_COMPONENTS_FIELD,
    component_list_field,
    component_list_type,
    one_component_list_array,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_supervised_parser import (
    NATIVE_PROCESS_CRASH,
    PARSER_PROCESS_CRASH,
    ParseAttempt,
    ProcessFailureSignature,
    Stage07SupervisorError,
    SupervisedParser,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_supervisor_diagnostic import (
    EXPECTED_PARSER_BUNDLE_FINGERPRINT,
    EXPECTED_PRIOR_DIAGNOSTIC_SHA256,
    Stage07SupervisorDiagnosticConfig,
    Stage07SupervisorDiagnosticError,
)


def _parsed(*pairs: tuple[str, str]) -> ParsedAddress:
    components = tuple(
        LibpostalComponent(label=label, value=value) for label, value in pairs
    )
    return ParsedAddress(
        status=PARSED_NONEMPTY if components else PARSED_EMPTY,
        components=components,
    )


def _success(parsed: ParsedAddress) -> ParseAttempt:
    return ParseAttempt(
        outcome="SUCCESS",
        parsed=parsed,
        technical_code=None,
        failure_signature=None,
        wall_seconds=0.01,
        child_max_rss_kib=100,
        input_codepoints_verified=True,
        input_sha256_verified=True,
        result_framing_completed=True,
    )


def _crash(
    signal_number: int = 11,
    signal_name: str = "SIGSEGV",
    *,
    input_verified: bool = True,
) -> ParseAttempt:
    return ParseAttempt(
        outcome="PROCESS_CRASH",
        parsed=None,
        technical_code=None,
        failure_signature=ProcessFailureSignature(
            exit_category="SIGNAL",
            exit_code=None,
            signal_number=signal_number,
            signal_name=signal_name,
            result_framing_completed=False,
        ),
        wall_seconds=0.02,
        child_max_rss_kib=200,
        input_codepoints_verified=input_verified,
        input_sha256_verified=input_verified,
        result_framing_completed=False,
    )


def _technical(code: str = "PARSER_EXCEPTION") -> ParseAttempt:
    return ParseAttempt(
        outcome="TECHNICAL_FAILURE",
        parsed=None,
        technical_code=code,
        failure_signature=None,
        wall_seconds=0.01,
        child_max_rss_kib=100,
        input_codepoints_verified=True,
        input_sha256_verified=True,
        result_framing_completed=True,
    )


class _ScriptedWorker:
    initialization_seconds = 0.001

    def __init__(self, attempts: Iterable[ParseAttempt]) -> None:
        self._attempts = iter(attempts)
        self.closed = False

    def attempt(self, candidate: str) -> ParseAttempt:
        assert not self.closed
        return next(self._attempts)

    def close(self) -> None:
        self.closed = True


class _WorkerFactory:
    def __init__(self, scripts: Iterable[Iterable[ParseAttempt]]) -> None:
        self._scripts = iter(scripts)
        self.workers: list[_ScriptedWorker] = []

    def __call__(self) -> _ScriptedWorker:
        worker = _ScriptedWorker(next(self._scripts))
        self.workers.append(worker)
        return worker


def test_supervisor_reuses_long_lived_worker_for_normal_results() -> None:
    factory = _WorkerFactory(
        [[_success(_parsed(("road", "example"))), _success(_parsed())]]
    )
    supervisor = SupervisedParser(factory)
    first = supervisor.parse("synthetic one")
    second = supervisor.parse("synthetic two")
    supervisor.close()

    assert first.status == PARSED_NONEMPTY
    assert second.status == PARSED_EMPTY
    assert second.components == ()
    assert supervisor.workers_started == 1
    assert supervisor.worker_restarts == 0


def test_two_identical_native_crashes_become_null_component_failure() -> None:
    factory = _WorkerFactory([[_crash()], [_crash()]])
    supervisor = SupervisedParser(factory)
    outcome = supervisor.parse("synthetic crash")
    supervisor.close()

    assert outcome.status == PARSER_PROCESS_CRASH
    assert outcome.components is None
    assert outcome.failure_code == NATIVE_PROCESS_CRASH
    assert len(outcome.attempts) == 2
    assert supervisor.first_attempt_crashes == 1
    assert supervisor.confirmed_repeated_crashes == 1
    assert supervisor.worker_restarts == 1


def test_crash_then_success_fails_publication_instead_of_using_result() -> None:
    supervisor = SupervisedParser(
        _WorkerFactory([[_crash()], [_success(_parsed(("road", "example")))]])
    )
    with pytest.raises(
        Stage07SupervisorError, match="PARSER_CRASH_SUCCESS_NONDETERMINISM"
    ):
        supervisor.parse("synthetic unstable")
    assert [attempt.outcome for attempt in supervisor.last_failed_attempts] == [
        "PROCESS_CRASH",
        "SUCCESS",
    ]
    supervisor.close()


def test_changed_crash_signal_fails_publication() -> None:
    supervisor = SupervisedParser(_WorkerFactory([[_crash()], [_crash(6, "SIGABRT")]]))
    with pytest.raises(
        Stage07SupervisorError, match="PARSER_CRASH_SIGNATURE_NONDETERMINISM"
    ):
        supervisor.parse("synthetic unstable")
    supervisor.close()


def test_crash_before_exact_input_acknowledgement_aborts() -> None:
    supervisor = SupervisedParser(_WorkerFactory([[_crash(input_verified=False)]]))
    with pytest.raises(Stage07SupervisorError, match="PARSER_CRASH_INPUT_UNVERIFIED"):
        supervisor.parse("synthetic unacknowledged")
    supervisor.close()


def test_wrapper_or_python_failure_aborts_without_new_status() -> None:
    supervisor = SupervisedParser(_WorkerFactory([[_technical()]]))
    with pytest.raises(Stage07SupervisorError, match="PARSER_EXCEPTION"):
        supervisor.parse("synthetic wrapper failure")
    supervisor.close()
    assert supervisor.first_attempt_crashes == 0


def test_spawned_supervisor_contains_real_public_signal_and_restarts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    postal = tmp_path / "postal"
    postal.mkdir()
    (postal / "__init__.py").write_text("", encoding="utf-8")
    (postal / "parser.py").write_text(
        """import os
import signal

def parse_address(value):
    if value == "synthetic crash":
        os.kill(os.getpid(), signal.SIGABRT)
    return [(value, "road")]
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    supervisor = SupervisedParser()
    success = supervisor.parse("synthetic success")
    crash = supervisor.parse("synthetic crash")
    after = supervisor.parse("synthetic after restart")
    supervisor.close()

    assert success.components == (
        LibpostalComponent(label="road", value="synthetic success"),
    )
    assert crash.status == PARSER_PROCESS_CRASH
    assert crash.components is None
    assert all(attempt.input_sha256_verified for attempt in crash.attempts)
    assert all(attempt.input_codepoints_verified for attempt in crash.attempts)
    assert all(
        attempt.failure_signature and attempt.failure_signature.signal_name == "SIGABRT"
        for attempt in crash.attempts
    )
    assert after.components == (
        LibpostalComponent(label="road", value="synthetic after restart"),
    )
    assert supervisor.workers_started == 3
    assert supervisor.worker_restarts == 2


def test_large_list_distinguishes_empty_crash_and_duplicate_labels(
    tmp_path: Path,
) -> None:
    values = (
        LibpostalComponent(label="road", value="first"),
        LibpostalComponent(label="road", value="second"),
    )
    array = pa.concat_arrays(
        (
            one_component_list_array(values),
            one_component_list_array(()),
            one_component_list_array(None),
        )
    )
    assert array.type == component_list_type()
    assert array[0].as_py() == [
        {"label": "road", "value": "first"},
        {"label": "road", "value": "second"},
    ]
    assert array[1].as_py() == []
    assert array[2].as_py() is None

    schema = pa.schema((component_list_field(),))
    path = tmp_path / "nested.parquet"
    pq.write_table(
        pa.Table.from_arrays((array,), schema=schema),
        path,
        write_page_checksum=True,
        row_group_size=1,
    )
    read = pq.ParquetFile(path, page_checksum_verification=True).read(use_threads=False)
    assert read.schema == schema
    assert read.column(STAGE07_COMPONENTS_FIELD)[1].as_py() == []
    assert read.column(STAGE07_COMPONENTS_FIELD)[2].as_py() is None


def test_supervisor_config_rejects_holdout_and_bad_commit(tmp_path: Path) -> None:
    common = dict(
        stage05_output_directory=tmp_path / "stage05",
        stage06_output_directory=tmp_path / "stage06",
        expected_stage06_manifest_sha256="1" * 64,
        prior_diagnostic_directory=tmp_path / "prior",
        expected_prior_diagnostic_sha256=EXPECTED_PRIOR_DIAGNOSTIC_SHA256,
        parser_bundle_directory=tmp_path / "bundle",
        expected_parser_bundle_fingerprint=EXPECTED_PARSER_BUNDLE_FINGERPRINT,
        output_directory=tmp_path / "output",
        execution_git_sha="2" * 40,
    )
    Stage07SupervisorDiagnosticConfig(**common).validate()
    with pytest.raises(
        Stage07SupervisorDiagnosticError, match="HOLDOUT_ACCESS_PROHIBITED"
    ):
        Stage07SupervisorDiagnosticConfig(
            **{**common, "output_directory": tmp_path / "holdout" / "output"}
        ).validate()
    with pytest.raises(Stage07SupervisorDiagnosticError, match="INVALID_GIT_COMMIT"):
        Stage07SupervisorDiagnosticConfig(
            **{**common, "execution_git_sha": "short"}
        ).validate()


def test_supervisor_cli_requires_slurm_before_input_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stage07-supervisor",
            "--stage05-output-directory",
            str(tmp_path / "stage05"),
            "--stage06-output-directory",
            str(tmp_path / "stage06"),
            "--expected-stage06-manifest-sha256",
            "1" * 64,
            "--prior-diagnostic-directory",
            str(tmp_path / "prior"),
            "--expected-prior-diagnostic-sha256",
            EXPECTED_PRIOR_DIAGNOSTIC_SHA256,
            "--parser-bundle-directory",
            str(tmp_path / "bundle"),
            "--expected-parser-bundle-fingerprint",
            EXPECTED_PARSER_BUNDLE_FINGERPRINT,
            "--output-directory",
            str(tmp_path / "output"),
            "--execution-git-sha",
            "2" * 40,
        ],
    )
    assert stage07_supervisor_cli.main() == 1
    assert "HEAVY_PROCESS_CLUSTER_REQUIRED" in capsys.readouterr().err


def test_targeted_launcher_has_global_limits_but_no_candidate_timeout() -> None:
    repository = Path(__file__).resolve().parents[1]
    launcher_path = (
        repository / "cluster/goethe_nhr/stage07_supervisor_diagnostic.sbatch"
    )
    launcher = launcher_path.read_text(encoding="utf-8")
    supervisor = (
        repository / "src/safe_geocoding_pipeline/preprocessing/stages/"
        "s07_supervised_parser.py"
    ).read_text(encoding="utf-8")
    assert "#SBATCH --mem=180G" in launcher
    assert "#SBATCH --time=12:00:00" in launcher
    assert "candidate_timeout_exists=false" in launcher
    assert "per_candidate_address_space_limit=none" in launcher
    assert "RLIMIT_AS" not in launcher + supervisor
    assert "--giant-timeout" not in launcher
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in launcher
    assert "protected_parsing_network_calls=false" in launcher
    for forbidden in ("/scratch", "/work/footprint/public", "rsync", "git pull"):
        assert forbidden not in launcher
    assert "HOLDOUT" in launcher
    assert "STAGE08" not in launcher
