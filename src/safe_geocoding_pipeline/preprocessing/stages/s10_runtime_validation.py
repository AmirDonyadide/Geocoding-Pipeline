"""Bounded public/invented runtime checks; no pipeline input readers."""

from __future__ import annotations

import copy
import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

from . import s10_query_contract as c
from . import s10_query_transliteration as t
from . import s10_runtime_lock as lock_identity

SCRIPT_CASES = (
    ("α", "Greek"),
    ("б", "Cyrillic"),
    ("Latin α 12", "Greek"),
    ("Latin б 12", "Cyrillic"),
    ("αб", None),
    ("Latin", None),
    ("ع", None),
    ("漢", None),
    ("α\u0301", "Greek"),
    ("α \u0301", None),
    ("a\u0301 α", None),
    ("\u0301α", None),
    ("α\u0378", None),
    ("α\u05b0", None),
)


def validate(root: Path, repository: Path) -> dict[str, Any]:
    spec = repository / "docs/scientific_assets" / t.SPEC_NAME
    bridge = repository / lock_identity.DEPENDENCIES["CPP_BRIDGE"]
    lock_path = root / "runtime_build_lock.json"
    runtime = t.ICUTransliterator(root, lock_path, spec, bridge)
    checks = 0
    try:
        for script, value, expected in t.SYNTHETIC_VECTORS:
            c.require(
                runtime.transform(script, value)
                == runtime.transform(script, value)
                == expected,
                "STAGE10_PUBLIC_VECTOR_FAILED",
            )
            checks += 1
        for value, expected_script in SCRIPT_CASES:
            c.require(
                t.eligible_script(value, check_marks=True) == expected_script,
                "STAGE10_PUBLIC_SCRIPT_GATE_FAILED",
            )
            checks += 1
        decomposed = "12 α\u0301, Latin-5!"
        native = str(decomposed)
        normalized = unicodedata.normalize("NFC", native)
        c.require(
            t.eligible_script(native, check_marks=False)
            == t.eligible_script(normalized, check_marks=True)
            == "Greek",
            "STAGE10_PUBLIC_NFC_ELIGIBILITY_FAILED",
        )
        actual = unicodedata.normalize("NFC", runtime.transform("Greek", normalized))
        c.require(
            actual == "12 á, Latin-5!"
            and native == decomposed
            and t.output_supported(actual),
            "STAGE10_PUBLIC_NFC_VECTOR_FAILED",
        )
        checks += 1
        c.require(
            runtime.transform("Greek", "Latin 12!") == "Latin 12!",
            "STAGE10_PUBLIC_UNCHANGED_FAILED",
        )
        c.require(
            not t.output_supported("ع") and t.output_supported("Latin 12!"),
            "STAGE10_PUBLIC_OUTPUT_GATE_FAILED",
        )
        checks += 2
        filters = runtime.verify_filter_equivalence()
        checks += 2
        pristine = copy.deepcopy(runtime.lock)
        mutations: list[tuple[str, str, Any]] = [
            ("ICU", "icu_version", "78.3"),
            ("UNICODE", "unicode_version", "17.0.0"),
            ("CLDR", "cldr_version", "48"),
            ("TRANSLITERATOR", "transliterator_ids", ["Any-Latin", "Cyrl-Latn"]),
            ("DIRECTION", "direction", "UTRANS_REVERSE"),
            ("WRAPPER", "bridge_source_sha256", "0" * 64),
            ("SEMANTIC_ID", "runtime_semantic_fingerprint", "0" * 64),
        ]
        faults: list[tuple[str, dict[str, Any] | bytes]] = []
        for label, key, replacement in mutations:
            altered = copy.deepcopy(pristine)
            altered[key] = replacement
            faults.append((label, altered))
        for role in ("BRIDGE", "ICU_DATA_STATIC"):
            altered = copy.deepcopy(pristine)
            next(a for a in altered["artifacts"] if a["role"] == role)["sha256"] = (
                "0" * 64
            )
            faults.append((role + "_HASH", altered))
        altered = copy.deepcopy(pristine)
        next(a for a in altered["artifacts"] if a["role"] == "ICU_DATA_STATIC")[
            "relative_path"
        ] = "invented-missing-asset.a"
        faults.append(("MISSING_DATA", altered))
        faults.extend((("CORRUPTED_LOCK", b"{"), ("EMPTY_LOCK", {})))
        passed = []
        # Never mutate real installed assets/lock. Fault files are public only.
        with tempfile.TemporaryDirectory(prefix="public-faults-", dir=root) as temp:
            for ordinal, (label, fault_payload) in enumerate(faults):
                path = Path(temp) / f"lock-{ordinal}.json"
                with os.fdopen(
                    os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb"
                ) as out:
                    out.write(
                        fault_payload
                        if isinstance(fault_payload, bytes)
                        else c.canonical(fault_payload)
                    )
                try:
                    unexpected = t.ICUTransliterator(root, path, spec, bridge)
                except c.Stage10Error:
                    passed.append(label)
                else:
                    unexpected.close()
                    raise c.Stage10Error("STAGE10_PUBLIC_FAULT_DID_NOT_FAIL_CLOSED")
        return {
            "validation_version": "stage10_public_runtime_validation_v1",
            "status": "PASS",
            "positive_checks": checks,
            "fault_checks": len(passed),
            "fault_checks_passed": passed,
            "filter_table_sha256": filters,
            "filter_codepoints_compared": 2 * 0x110000,
            "runtime_build_lock_sha256": runtime.lock_sha256,
            "runtime_semantic_fingerprint": runtime.semantic_fingerprint,
            "protected_payloads_accessed": 0,
        }
    finally:
        runtime.close()
