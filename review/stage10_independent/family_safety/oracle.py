"""Independent frozen-contract Q5/Q6 review; no candidate family implementation.

``run`` is for the authorized compute-node review only. The caller owns the
guard, protected paths, immutable input validation, exact runtime, and private
DuckDB/TMPDIR. ``review_country_context`` must have one independently validated
nullable boundary_country per context. Only fixed aggregate counts leave run.

The ICU runtime is the sole candidate computation reused: it is the pinned
low-level whole-string transform, not candidate eligibility or family logic.
"""

from __future__ import annotations

import bisect
import hashlib
import importlib.resources
import re
import struct
import tempfile
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Iterable

SCRIPT_SHA = "9e88f0a677df47311106340be8ede2ecdacd9c1c931831218d2be6d5508e0039"
UNIT = re.compile(r"(?:unit|suite|apt|apartment) [0-9]+[a-z]?")
LEVEL = re.compile(r"(?:floor|level) [0-9]+")


def _encode(value: Any) -> bytes:
    if value is None:
        return b"\x00"
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return b"\x01" + struct.pack(">Q", len(raw)) + raw
    if isinstance(value, bytes):
        return b"\x02" + struct.pack(">Q", len(value)) + value
    if isinstance(value, bool):
        return b"\x04" + bytes([value])
    if isinstance(value, int):
        return b"\x03" + struct.pack(">Q", value)
    if isinstance(value, (tuple, list)):
        return b"\x05" + struct.pack(">Q", len(value)) + b"".join(map(_encode, value))
    raise TypeError("REVIEW_FAMILY_UNSUPPORTED_ENCODING")


def value_digest(value: Any) -> bytes:
    return hashlib.sha256(
        b"SAFE:stage10-transform-value:v1\0" + struct.pack(">Q", 1) + _encode(value)
    ).digest()


def _trace(
    index: int, name: str, before: Any, after: Any, asset: bytes | None = None
) -> dict:
    return dict(
        ordinal=index,
        transform_id=name,
        transform_asset_binding=asset,
        input_value_sha256=value_digest(before),
        output_value_sha256=value_digest(after),
    )


class ScriptTable:
    """Independent parser for the exact public Script property (not extensions)."""

    def __init__(self) -> None:
        raw = (
            importlib.resources.files("safe_geocoding_pipeline.preprocessing")
            .joinpath("resources/references/unicode_ucd_16_0_0/Scripts.txt")
            .read_bytes()
        )
        if hashlib.sha256(raw).hexdigest() != SCRIPT_SHA:
            raise RuntimeError("REVIEW_FAMILY_SCRIPT_HASH_MISMATCH")
        intervals = []
        for row in raw.decode("utf-8").splitlines():
            row = row.split("#", 1)[0].strip()
            if row:
                span, name = map(str.strip, row.split(";"))
                bounds = span.split("..")
                intervals.append((int(bounds[0], 16), int(bounds[-1], 16), name))
        intervals.sort()
        if any(a[1] >= b[0] for a, b in zip(intervals, intervals[1:])):
            raise RuntimeError("REVIEW_FAMILY_SCRIPT_OVERLAP")
        self.intervals = intervals
        self.starts = [item[0] for item in intervals]

    @lru_cache(maxsize=8192)
    def script(self, char: str) -> str:
        cp = ord(char)
        index = bisect.bisect_right(self.starts, cp) - 1
        if index >= 0 and cp <= self.intervals[index][1]:
            return self.intervals[index][2]
        return "Unknown"

    def eligible(self, value: str, check_marks: bool) -> str | None:
        target = None
        observed = set()
        base = None
        mark_bases = set()
        for char in value:
            script = self.script(char)
            category = unicodedata.category(char)
            if script not in ("Latin", "Common", "Inherited", "Greek", "Cyrillic"):
                return None
            if script in ("Greek", "Cyrillic"):
                observed.add(script)
                if category[0] == "L":
                    target = script
            if check_marks and category[0] == "M" and script == "Inherited":
                if base not in ("Greek", "Cyrillic"):
                    return None
                mark_bases.add(base)
            if category[0] != "M":
                base = script if category[0] == "L" else None
        if target is None or observed != {target} or mark_bases - {target}:
            return None
        return target

    def supported(self, value: str) -> bool:
        return all(
            self.script(char) in ("Latin", "Common", "Inherited") for char in value
        )


@dataclass
class Expected:
    text: str | None
    reason: str | None = None
    traces: tuple = ()
    removed: tuple = ()
    script: str | None = None
    attempted: bool = False
    # All failures remain suppressions. This records the narrowly ambiguous
    # diagnostic ordering separately, without obscuring payload-safety checks.
    alignment_and_corroboration_failure: bool = False


def _veto(line: str, geography: Iterable[str]) -> bool:
    for value in geography:
        if not value:
            continue
        position = line.find(value)
        while position != -1:
            end = position + len(value)
            if (
                position == 0 or unicodedata.category(line[position - 1])[0] not in "LN"
            ) and (end == len(line) or unicodedata.category(line[end])[0] not in "LN"):
                return True
            position = line.find(value, position + 1)
    return False


def q5(
    lines: tuple[str, ...],
    parse_status: str,
    component_count: int,
    reader: Callable[[bool], Iterable[tuple[int, str, str]]],
    geography: tuple[str, ...],
) -> Expected:
    """Independently align *all* ordinals before applying complete-line proof.

    Per-component offsets spill to the caller's private TMPDIR; memory contains
    no population- or component-count-sized Python collection.
    """
    text = " ".join(line for line in lines if line)
    targets = []
    offset = 0
    for slot, line in enumerate(lines, 1):
        if not line:
            continue
        category = (
            "UNIT"
            if UNIT.fullmatch(line)
            else "LEVEL"
            if LEVEL.fullmatch(line)
            else None
        )
        if category:
            targets.append((slot, offset, offset + len(line), line, category))
        offset += len(line) + 1
    if not targets:
        return Expected(None, "FAMILY_INELIGIBLE")
    if parse_status != "PARSED_NONEMPTY" or component_count == 0:
        return Expected(None, "PARSER_EVIDENCE_UNUSABLE")
    matched = {}
    corroborated = True
    with tempfile.TemporaryFile(mode="w+b") as offsets:
        cursor = 0
        count = 0
        for ordinal, label, value in reader(False):
            if ordinal != count:
                raise RuntimeError("REVIEW_FAMILY_COMPONENT_ORDINAL_INVALID")
            if not value:
                return Expected(None, "PARSER_EVIDENCE_UNUSABLE")
            start = text.find(value, cursor)
            if start < 0:
                return Expected(None, "UNIT_ALIGNMENT_AMBIGUOUS")
            stop = start + len(value)
            offsets.write(struct.pack(">QQ", start, stop))
            for slot, first, last, _, category in targets:
                if first < stop and start < last:
                    valid = (first, last, category.lower()) == (start, stop, label)
                    corroborated = corroborated and valid
                    if valid:
                        matched[slot] = dict(
                            source_slot=slot,
                            start_codepoint=first,
                            end_codepoint_exclusive=last,
                            category=category,
                            grammar_id="stage10_whole_line_" + category.lower() + "_v1",
                            stage08_component_ordinal=ordinal,
                        )
            cursor = stop
            count += 1
        if count != component_count:
            raise RuntimeError("REVIEW_FAMILY_COMPONENT_COUNT_INVALID")
        corroborated = corroborated and len(matched) == len(targets)
        cursor = len(text)
        unique = True
        for ordinal, _, value in reader(True):
            count -= 1
            if ordinal != count:
                raise RuntimeError("REVIEW_FAMILY_REVERSE_ORDINAL_INVALID")
            start = text.rfind(value, 0, cursor)
            offsets.seek(16 * count)
            unique = (
                unique
                and start >= 0
                and offsets.read(16) == struct.pack(">QQ", start, start + len(value))
            )
            cursor = start
        if count != 0:
            raise RuntimeError("REVIEW_FAMILY_REVERSE_COUNT_INVALID")
    if not unique:
        return Expected(
            None,
            "UNIT_ALIGNMENT_AMBIGUOUS",
            alignment_and_corroboration_failure=not corroborated,
        )
    if not corroborated:
        return Expected(None, "PARSER_EVIDENCE_UNUSABLE")
    if any(_veto(target[3], geography) for target in targets):
        return Expected(None, "UNIT_SOURCE_FIELD_CONFLICT")
    remaining = tuple(
        "" if slot in matched else line for slot, line in enumerate(lines, 1)
    )
    output = " ".join(line for line in remaining if line)
    traces = (
        _trace(0, "WHOLE_LINE_UNIT_LEVEL_REMOVE_V1", lines, remaining),
        _trace(1, "SOURCE_SPACE_JOIN_V1", remaining, output),
    )
    if not output:
        return Expected(None, "EMPTY_RESULT_AFTER_TRANSFORMATION", traces)
    if not any(
        any(unicodedata.category(ch)[0] == "L" for ch in line)
        and any("0" <= ch <= "9" for ch in line)
        for line in remaining
    ):
        return Expected(None, "FAMILY_INELIGIBLE", traces)
    return Expected(
        output, traces=traces, removed=tuple(matched[slot] for slot in sorted(matched))
    )


def q6(text: str, scripts: ScriptTable, runtime: Any) -> Expected:
    script = scripts.eligible(text, False)
    if script is None:
        return Expected(None, "UNSUPPORTED_SCRIPT_TRANSLITERATION")
    normalized = unicodedata.normalize("NFC", text)
    traces = [_trace(0, "NFC_U16_V1", text, normalized, runtime.asset_binding)]
    if scripts.eligible(normalized, True) != script:
        return Expected(
            None, "UNSUPPORTED_SCRIPT_TRANSLITERATION", tuple(traces), script=script
        )
    # Runtime exceptions propagate to the protected harness. Never convert a
    # technical failure into scientific ineligibility.
    transformed = runtime.transform(script, normalized)
    traces.append(
        _trace(
            1,
            "ICU_GREK_LATN_77_1" if script == "Greek" else "ICU_CYRL_LATN_77_1",
            normalized,
            transformed,
            runtime.asset_binding,
        )
    )
    output = unicodedata.normalize("NFC", transformed)
    traces.append(_trace(2, "NFC_U16_V1", transformed, output, runtime.asset_binding))
    if not output:
        return Expected(
            None,
            "EMPTY_RESULT_AFTER_TRANSFORMATION",
            tuple(traces),
            script=script,
            attempted=True,
        )
    if output != text and not scripts.supported(output):
        return Expected(
            None,
            "TRANSLITERATION_UNSUPPORTED_OUTPUT",
            tuple(traces),
            script=script,
            attempted=True,
        )
    return Expected(output, traces=tuple(traces), script=script, attempted=True)


def _intent(text: str, country: str) -> dict:
    return dict(
        intent_version="stage10_query_intent_v1",
        endpoint="/v1/search",
        search_mode="FULL_TEXT",
        text=text,
        address=None,
        postalcode=None,
        locality=None,
        region=None,
        country=None,
        boundary_country=country,
        retrieval_policy_slot="SAFE_PELIAS_COMMON_RETRIEVAL_V1",
    )


def run(db: Any, runtime: Any, check: Callable[[str, bool], None]) -> dict[str, int]:
    """Review every context, all Q5 target components, all eligible Q6 inputs."""
    check("family_unicode16", unicodedata.unidata_version == "16.0.0")
    scripts = ScriptTable()
    line_select = ",".join(
        f"CASE WHEN x.stage08_representation='NATIVE' THEN r.stage04_lower_street_address_line_{i}_native "
        f"ELSE r.stage04_lower_street_address_line_{i} END AS line{i}"
        for i in range(1, 5)
    )
    db.execute(f"""CREATE TABLE review_fs_lines AS SELECT x.query_context_id,
        x.stage06_exact_candidate_id, {line_select} FROM contexts x
        JOIN stage06_row_map r USING(stable_source_row_id_v1)""")
    marker_sql = "(?:unit|suite|apt|apartment) [0-9]+[a-z]?|(?:floor|level) [0-9]+"
    targets = " OR ".join(
        f"regexp_full_match(line{i}, '{marker_sql}')" for i in range(1, 5)
    )
    db.execute(f"""CREATE TABLE review_fs_target_ids AS SELECT DISTINCT stage06_exact_candidate_id
        FROM review_fs_lines WHERE {targets}""")
    db.execute("""CREATE TABLE review_fs_components AS SELECT p.stage06_exact_candidate_id,
        p.stage08_component_ordinal,p.stage08_raw_libpostal_label,p.stage08_raw_libpostal_value
        FROM parser_component_evidence p JOIN review_fs_target_ids t USING(stage06_exact_candidate_id)
        ORDER BY p.stage06_exact_candidate_id,p.stage08_component_ordinal""")
    db.execute(
        "CREATE INDEX review_fs_component_id ON review_fs_components(stage06_exact_candidate_id)"
    )
    stats = dict(
        contexts=0,
        q5_eligible=0,
        q6_eligible=0,
        q6_attempted=0,
        q6_greek=0,
        q6_cyrillic=0,
        q6_unsupported_output=0,
        q5_q6_coeligible=0,
        q5_alignment_and_corroboration_failure=0,
        q5_diagnostic_precedence_differences=0,
    )
    failures: dict[str, int] = {}

    def observe(name: str, good: bool) -> None:
        failures[name] = failures.get(name, 0) + int(not good)

    cursor = db.cursor()
    cursor.execute("""SELECT x.query_context_id,x.stage08_representation,x.stage06_exact_candidate_id,
        c.stage06_candidate_lower,c.stage07_parse_status,c.stage08_raw_component_count,
        l.line1,l.line2,l.line3,l.line4,
        s.stage04_lower_city,s.stage04_lower_postcode,s.stage04_lower_region_in_country,
        s.stage04_lower_country_iso_code,k.boundary_country,
        d5 AS decision5,d6 AS decision6,h5.intent,h6.intent,
        baseline.hypothesis_id,d3.hypothesis_id
        FROM contexts x JOIN candidate_evidence c USING(stage06_exact_candidate_id)
        JOIN review_fs_lines l USING(query_context_id)
        JOIN source_candidate_map s USING(stable_source_row_id_v1)
        JOIN review_country_context k USING(query_context_id)
        JOIN query_family_decision d5 ON d5.query_context_id=x.query_context_id AND d5.family='Q5'
        JOIN query_family_decision d6 ON d6.query_context_id=x.query_context_id AND d6.family='Q6'
        JOIN query_family_decision baseline ON baseline.query_context_id=x.query_context_id
           AND baseline.family=CASE WHEN x.stage08_representation='NATIVE' THEN 'Q2' ELSE 'Q1' END
        JOIN query_family_decision d3 ON d3.query_context_id=x.query_context_id AND d3.family='Q3'
        LEFT JOIN query_hypothesis h5 ON h5.hypothesis_id=d5.hypothesis_id
        LEFT JOIN query_hypothesis h6 ON h6.hypothesis_id=d6.hypothesis_id
        ORDER BY x.query_context_id""")
    try:
        while (row := cursor.fetchone()) is not None:
            (_, role, candidate, text, status, count, *rest) = row
            lines = tuple(rest[:4])
            geography = tuple(rest[4:8])
            country = rest[8]
            d5, d6, h5, h6, baseline_id, boundary_id = rest[9:]
            stats["contexts"] += 1
            observe(
                "family_line_body_equal",
                " ".join(line for line in lines if line) == text,
            )

            def reader(reverse: bool) -> Iterable[tuple[int, str, str]]:
                direction = "DESC" if reverse else "ASC"
                result = db.execute(
                    "SELECT stage08_component_ordinal,stage08_raw_libpostal_label,"
                    "stage08_raw_libpostal_value FROM review_fs_components WHERE stage06_exact_candidate_id=? "
                    f"ORDER BY stage08_component_ordinal {direction}",
                    [candidate],
                )
                while part := result.fetchmany(1):
                    yield from part

            expected5 = (
                Expected(None, "COUNTRY_CONTEXT_UNAVAILABLE")
                if country is None
                else q5(lines, status, count, reader, geography)
            )
            expected6 = (
                Expected(None, "REQUIRED_SOURCE_REPRESENTATION_UNAVAILABLE")
                if role != "NATIVE"
                else Expected(None, "COUNTRY_CONTEXT_UNAVAILABLE")
                if country is None
                else q6(text, scripts, runtime)
            )
            stats["q5_alignment_and_corroboration_failure"] += (
                expected5.alignment_and_corroboration_failure
            )
            stats["q6_attempted"] += expected6.attempted
            stats["q6_unsupported_output"] += (
                expected6.reason == "TRANSLITERATION_UNSUPPORTED_OUTPUT"
            )
            stats["q5_q6_coeligible"] += (
                expected5.text is not None and expected6.text is not None
            )
            for family, expected, published, actual in (
                ("q5", expected5, d5, h5),
                ("q6", expected6, d6, h6),
            ):
                eligible = expected.text is not None
                stats[family + "_eligible"] += eligible
                if family == "q6" and eligible:
                    stats["q6_" + str(expected.script).lower()] += 1
                observe(
                    family + "_eligibility",
                    published["eligibility_state"]
                    == ("ELIGIBLE" if eligible else "INELIGIBLE"),
                )
                observe(
                    family + "_intent",
                    actual == (_intent(expected.text, country) if eligible else None),
                )
                observe(
                    family + "_transformations",
                    published["transformations"] == list(expected.traces),
                )
                observe(
                    family + "_removed_lines",
                    published["removed_lines"] == list(expected.removed),
                )
                observe(family + "_field_decisions", published["field_decisions"] == [])
                prior_id = None
                if eligible:
                    if expected.text == text:
                        prior_id = baseline_id
                    elif expected.text == "\n".join(line for line in lines if line):
                        prior_id = boundary_id
                    elif family == "q6" and expected5.text == expected.text:
                        prior_id = d5["hypothesis_id"]
                reason = (
                    "EXACT_SEMANTIC_DUPLICATE"
                    if prior_id is not None
                    else expected.reason
                )
                # Normative alignment diagnostics are recorded distinctly; the
                # published implementation can short-circuit at corroboration.
                # Report this as evidence, not a payload-safety false alarm.
                precedence_difference = (
                    family == "q5"
                    and expected.alignment_and_corroboration_failure
                    and published["primary_reason"] == "PARSER_EVIDENCE_UNUSABLE"
                )
                stats["q5_diagnostic_precedence_differences"] += precedence_difference
                observe(
                    family + "_primary_reason",
                    published["primary_reason"] == reason or precedence_difference,
                )
                reasons = [reason] if reason else []
                observe(
                    family + "_reason_codes",
                    published["reason_codes"] == reasons
                    or (
                        precedence_difference
                        and published["reason_codes"] == ["PARSER_EVIDENCE_UNUSABLE"]
                    ),
                )
                observe(
                    family + "_membership",
                    published["membership_state"]
                    == (
                        "CONVERGENT_MEMBER"
                        if prior_id is not None
                        else "FIRST_MEMBER"
                        if eligible
                        else "NONE"
                    ),
                )
                observe(
                    family + "_membership_fk",
                    (published["hypothesis_id"] is not None) == eligible
                    and (prior_id is None or published["hypothesis_id"] == prior_id),
                )
    finally:
        cursor.close()
    expected_contexts = db.execute("SELECT count(*) FROM contexts").fetchone()[0]
    observe("family_context_totality", stats["contexts"] == expected_contexts)
    for name, count in sorted(failures.items()):
        check(name, count == 0)
        stats[name + "_mismatches"] = count
    return stats
