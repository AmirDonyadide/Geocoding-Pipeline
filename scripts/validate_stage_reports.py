#!/usr/bin/env python3
"""Validate the frozen sanitized Stage 0-8 report consolidation."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
STAGES = tuple(range(9))
REPORT_VERSION = "stage_acceptance_summary_v1"
TOP_LEVEL_KEYS = {
    "report_version",
    "stage",
    "stage_name",
    "status",
    "scope",
    "accepted",
    "provenance",
    "inputs",
    "outputs",
    "counts",
    "fingerprints",
    "validation",
    "independent_review",
    "historical_events",
    "prohibited_activity",
}
REQUIRED_SECTIONS = (
    "Status",
    "Purpose",
    "Scope and scientific boundary",
    "Inputs",
    "Outputs",
    "Scientific contract",
    "Implementation provenance",
    "DEVELOPMENT execution",
    "Validation and review",
    "Historical findings and rejected attempts",
    "Accepted decision",
    "Known limitations",
    "Downstream handoff",
)
MARKDOWN_LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")
ACCEPTED_METADATA: tuple[tuple[int, tuple[str, ...], object], ...] = (
    (
        7,
        ("provenance", "candidate_sha"),
        "656a16d3d1f33cb152ace557c26f42df047bc7d6",
    ),
    (
        7,
        ("provenance", "executable_sha"),
        "e684d84a8d68498ea790542143c8e125b3eb87b5",
    ),
    (
        7,
        ("fingerprints", "contract"),
        "c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4",
    ),
    (
        7,
        ("fingerprints", "schema"),
        "b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2",
    ),
    (
        7,
        ("fingerprints", "logical"),
        "0f0706c1396803737f22845837753878bfd2e8b3f9af59b48cfcc1b8c5774530",
    ),
    (
        7,
        ("fingerprints", "manifest"),
        "f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266",
    ),
    (
        8,
        ("provenance", "candidate_sha"),
        "231cdbf9db755fb56486c46b3b3faa02f5b5f3b6",
    ),
    (
        8,
        ("provenance", "executable_sha"),
        "c04cb97214a9f1e5d2b80512c756400321eefa80",
    ),
    (
        8,
        ("fingerprints", "contract"),
        "8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e",
    ),
    (
        8,
        ("fingerprints", "schema_bundle"),
        "6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f",
    ),
    (
        8,
        ("fingerprints", "logical_dataset"),
        "9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526",
    ),
    (
        8,
        ("fingerprints", "manifest"),
        "2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827",
    ),
    (8, ("counts", "candidate_defects"), 0),
    (8, ("prohibited_activity", "stage09_started"), False),
)


def _expected_report_paths() -> set[Path]:
    paths = {
        REPORTS / "README.md",
        REPORTS / "development" / "README.md",
        REPORTS / "generated" / "README.md",
    }
    for stage in STAGES:
        paths.add(REPORTS / "development" / f"stage{stage:02d}.md")
        paths.add(REPORTS / "generated" / f"stage{stage:02d}.json")
    return paths


def _load_summaries(errors: list[str]) -> dict[int, dict[str, object]]:
    summaries: dict[int, dict[str, object]] = {}
    for stage in STAGES:
        path = REPORTS / "generated" / f"stage{stage:02d}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path.relative_to(ROOT)}: top level is not an object")
            continue
        payload = {str(key): item for key, item in value.items()}
        summaries[stage] = payload
        if set(payload) != TOP_LEVEL_KEYS:
            errors.append(f"{path.relative_to(ROOT)}: common schema keys differ")
        if payload.get("report_version") != REPORT_VERSION:
            errors.append(f"{path.relative_to(ROOT)}: report_version mismatch")
        if payload.get("stage") != stage:
            errors.append(f"{path.relative_to(ROOT)}: stage mismatch")
        if payload.get("status") != f"STAGE_{stage}_ACCEPTED":
            errors.append(f"{path.relative_to(ROOT)}: accepted status mismatch")
        if payload.get("scope") != "DEVELOPMENT" or payload.get("accepted") is not True:
            errors.append(f"{path.relative_to(ROOT)}: scope/acceptance mismatch")
        provenance = payload.get("provenance")
        if not isinstance(provenance, dict) or not isinstance(
            provenance.get("jobs"), list
        ):
            errors.append(f"{path.relative_to(ROOT)}: invalid provenance/jobs")
        prohibited = payload.get("prohibited_activity")
        if not isinstance(prohibited, dict):
            errors.append(f"{path.relative_to(ROOT)}: invalid prohibited_activity")
        elif any(item not in (False, 0) for item in prohibited.values()):
            errors.append(f"{path.relative_to(ROOT)}: prohibited activity is nonzero")
    return summaries


def _nested_int(
    summaries: dict[int, dict[str, object]], stage: int, *keys: str
) -> int | None:
    value: object = summaries.get(stage, {})
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _nested_str(
    summaries: dict[int, dict[str, object]], stage: int, *keys: str
) -> str | None:
    value: object = summaries.get(stage, {})
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value if isinstance(value, str) else None


def _nested_value(
    summaries: dict[int, dict[str, object]], stage: int, keys: tuple[str, ...]
) -> object:
    value: object = summaries.get(stage, {})
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _validate_cross_stage(
    summaries: dict[int, dict[str, object]], errors: list[str]
) -> None:
    expected_source_rows = 35000
    for stage in (2, 3, 4, 5):
        if (
            _nested_int(summaries, stage, "counts", "input_rows")
            != expected_source_rows
        ):
            errors.append(f"stage{stage:02d}: input row count is not 35,000")
        if (
            _nested_int(summaries, stage, "counts", "output_rows")
            != expected_source_rows
        ):
            errors.append(f"stage{stage:02d}: output row count is not 35,000")
    if _nested_int(summaries, 6, "counts", "source_rows") != expected_source_rows:
        errors.append("stage06: source row count is not 35,000")
    if _nested_int(summaries, 8, "counts", "source_rows") != expected_source_rows:
        errors.append("stage08: source row count is not 35,000")

    candidates = _nested_int(summaries, 6, "counts", "unique_candidates")
    occurrences = _nested_int(summaries, 6, "counts", "total_occurrences")
    for stage in (7, 8):
        stage_candidates = _nested_int(summaries, stage, "counts", "candidate_rows")
        if stage == 8:
            stage_candidates = _nested_int(summaries, stage, "counts", "candidates")
        if stage_candidates != candidates:
            errors.append(f"stage{stage:02d}: candidate count disagrees with Stage 6")
        if _nested_int(summaries, stage, "counts", "occurrences") != occurrences:
            errors.append(f"stage{stage:02d}: occurrence count disagrees with Stage 6")

    parsed = _nested_int(summaries, 7, "counts", "parsed_nonempty")
    empty = _nested_int(summaries, 7, "counts", "parsed_empty")
    if parsed is None or empty is None or parsed + empty != candidates:
        errors.append("stage07: technical statuses do not sum to candidate rows")

    if _nested_str(summaries, 7, "fingerprints", "manifest") != _nested_str(
        summaries, 8, "inputs", "stage07", "manifest"
    ):
        errors.append("stage07/stage08: manifest binding mismatch")
    if _nested_str(summaries, 6, "fingerprints", "manifest") != _nested_str(
        summaries, 8, "inputs", "stage06", "manifest"
    ):
        errors.append("stage06/stage08: manifest binding mismatch")

    for stage, keys, expected in ACCEPTED_METADATA:
        if _nested_value(summaries, stage, keys) != expected:
            errors.append(
                f"stage{stage:02d}: accepted metadata mismatch at {'.'.join(keys)}"
            )

    stage08 = summaries.get(8, {})
    accepted_logical = _nested_str(summaries, 8, "fingerprints", "logical_dataset")
    events = stage08.get("historical_events")
    if not isinstance(events, list) or any(
        not isinstance(event, dict) for event in events
    ):
        errors.append("stage08: malformed historical event ledger")
        return
    logical_events = [event for event in events if "logical_dataset" in event]
    if len(logical_events) != 4 or any(
        event.get("logical_dataset") != accepted_logical for event in logical_events
    ):
        errors.append("stage08: remediation logical datasets are not identical")
    review_only = [event for event in events if event.get("event_id") == "RH-001"]
    if len(review_only) != 1 or review_only[0].get("classification") != "REVIEW_ONLY":
        errors.append("stage08: RH-001 is not classified REVIEW_ONLY")
    elif review_only[0].get("candidate_defect") is not False:
        errors.append("stage08: RH-001 is incorrectly classified as a candidate defect")


def _validate_markdown(errors: list[str]) -> None:
    for stage in STAGES:
        path = REPORTS / "development" / f"stage{stage:02d}.md"
        try:
            payload = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        if not payload.startswith(f"# Stage {stage:02d} — "):
            errors.append(f"{path.relative_to(ROOT)}: canonical title missing")
        positions = [payload.find(f"## {section}") for section in REQUIRED_SECTIONS]
        if -1 in positions or positions != sorted(positions):
            errors.append(
                f"{path.relative_to(ROOT)}: required sections missing/out of order"
            )
        if f"`STAGE_{stage}_ACCEPTED`" not in payload:
            errors.append(f"{path.relative_to(ROOT)}: accepted status missing")


def _markdown_files() -> list[Path]:
    paths = [ROOT / "README.md"]
    paths.extend((ROOT / "docs").rglob("*.md"))
    paths.extend(REPORTS.rglob("*.md"))
    return sorted(set(paths))


def _validate_local_links(errors: list[str]) -> None:
    for path in _markdown_files():
        payload = path.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(payload):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                errors.append(
                    f"{path.relative_to(ROOT)}: broken local link {raw_target!r}"
                )


def main() -> int:
    errors: list[str] = []
    observed = {path for path in REPORTS.rglob("*") if path.is_file()}
    expected = _expected_report_paths()
    if observed != expected:
        unexpected = sorted(path.relative_to(ROOT) for path in observed - expected)
        missing = sorted(path.relative_to(ROOT) for path in expected - observed)
        if unexpected:
            errors.append(f"unexpected report files: {unexpected}")
        if missing:
            errors.append(f"missing report files: {missing}")

    summaries = _load_summaries(errors)
    _validate_cross_stage(summaries, errors)
    _validate_markdown(errors)
    _validate_local_links(errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("STAGE_REPORTS_VALIDATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
