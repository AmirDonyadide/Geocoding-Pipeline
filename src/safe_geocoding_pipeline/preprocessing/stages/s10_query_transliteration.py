"""Exact ICU4C bridge and frozen Q6 eligibility; no system-library fallback."""

from __future__ import annotations

import ctypes
import os
import platform
import stat
import unicodedata
from functools import cache
from pathlib import Path
from typing import Any

from ..script_reference import ScriptReference, unicode_script_reference_paths
from . import s10_query_contract as c

SPEC_NAME = "stage10_transliteration_spec_v1.json"
SPEC_SHA256 = "5d0a8f6906a8d93ac38d73a862d69e31e2e9e454e8d0518e0c13f9792256a916"
LOCK_VERSION = "stage10_transliteration_runtime_build_lock_v1"
SOURCE_SHA256 = "629e7e6e309d1eeeb29c3eaf49e4f4532534fcf2613bcf0e51cd7850fa85a007"
EXPECTED_VERSIONS = ((77, 1, 0, 0), (16, 0, 0, 0), (47, 0, 0, 0))
SYNTHETIC_VECTORS = (
    ("Greek", "12 α road unit 5", "12 a road unit 5"),
    ("Greek", "αβγ", "abg"),
    ("Greek", "Αθήνα", "Athḗna"),
    ("Cyrillic", "улица", "ulica"),
    ("Cyrillic", "12 улица unit 5", "12 ulica unit 5"),
    ("Greek", "Latin 12", "Latin 12"),
)


@cache
def scripts() -> ScriptReference:
    paths = unicode_script_reference_paths()
    return ScriptReference.from_artifact(
        paths["unicode_manifest"], paths["unicode_artifact"]
    )


def eligible_script(value: str, *, check_marks: bool) -> str | None:
    c.require(
        unicodedata.unidata_version == "16.0.0", "STAGE10_UNICODE_RUNTIME_MISMATCH"
    )
    target: str | None = None
    previous_nonmark_script: str | None = None
    previous_nonmark_letter = False
    inherited_mark_base: str | None = None
    for character in value:
        script = scripts().script_for(character)
        category = unicodedata.category(character)
        if script not in ("Latin", "Common", "Inherited", "Greek", "Cyrillic"):
            return None
        if script in ("Greek", "Cyrillic"):
            if target is not None and target != script:
                return None
            if category.startswith("L"):
                target = script
        if check_marks and script == "Inherited" and category.startswith("M"):
            if not previous_nonmark_letter or previous_nonmark_script not in (
                "Greek",
                "Cyrillic",
            ):
                return None
            if (
                inherited_mark_base is not None
                and inherited_mark_base != previous_nonmark_script
            ):
                return None
            inherited_mark_base = previous_nonmark_script
        if not category.startswith("M"):
            previous_nonmark_script = script
            previous_nonmark_letter = category.startswith("L")
    if inherited_mark_base is not None and target != inherited_mark_base:
        return None
    if target is None:
        return None
    # Some script-specific nonletters must also belong to that single target.
    if any(
        scripts().script_for(ch) not in ("Latin", "Common", "Inherited", target)
        for ch in value
    ):
        return None
    return target


def output_supported(value: str) -> bool:
    return all(
        scripts().script_for(ch) in ("Latin", "Common", "Inherited") for ch in value
    )


def _private_file(root: Path, relative: str, expected: str, size: int) -> Path:
    parts = Path(relative).parts
    c.require(
        bool(parts)
        and not Path(relative).is_absolute()
        and all(p not in (".", "..") for p in parts),
        "STAGE10_RUNTIME_ASSET_PATH_INVALID",
    )
    path = root
    for part in parts:
        path /= part
        c.require(not path.is_symlink(), "STAGE10_RUNTIME_ASSET_SYMLINK")
    info = path.lstat()
    c.require(
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and info.st_nlink == 1
        and info.st_size == size
        and stat.S_IMODE(info.st_mode) & 0o077 == 0,
        "STAGE10_RUNTIME_ASSET_TOPOLOGY_INVALID",
    )
    c.require(c.sha256_file(path) == expected, "STAGE10_RUNTIME_ASSET_HASH_MISMATCH")
    return path


class ICUTransliterator:
    """Hash-pinned statically linked ICU/data; single-threaded owned handles."""

    def __init__(
        self, root: Path, lock_path: Path, spec_path: Path, bridge_source: Path
    ) -> None:
        self.handles: dict[str, int] = {}
        c.require(
            c.sha256_file(spec_path) == SPEC_SHA256,
            "STAGE10_FROZEN_TRANSLITERATION_SPEC_MISMATCH",
        )
        self.lock = c.read_json(lock_path)
        spec = c.read_json(spec_path)
        c.require(
            self.lock["lock_version"] == LOCK_VERSION
            and self.lock["specification_sha256"] == c.sha256_file(spec_path)
            and self.lock["bridge_source_sha256"] == c.sha256_file(bridge_source)
            and self.lock["source_archive_sha256"] == SOURCE_SHA256,
            "STAGE10_TRANSLITERATION_LOCK_MISMATCH",
        )
        c.require(
            self.lock["icu_version"] == spec["icu"]["version"] == "77.1"
            and self.lock["unicode_version"]
            == spec["icu"]["unicode_version"]
            == "16.0.0"
            and self.lock["cldr_version"] == spec["icu"]["cldr_source_version"] == "47"
            and self.lock["source_commit"] == spec["icu"]["source_commit"]
            and self.lock["platform"]
            == {"system": platform.system(), "machine": platform.machine()},
            "STAGE10_TRANSLITERATION_VERSION_MISMATCH",
        )
        c.require(
            not os.environ.get("ICU_DATA"), "STAGE10_ICU_DATA_OVERRIDE_PROHIBITED"
        )
        c.require(
            not root.is_symlink()
            and root.is_dir()
            and stat.S_IMODE(root.stat().st_mode) == 0o700,
            "STAGE10_RUNTIME_ROOT_NOT_PRIVATE",
        )
        c.require(
            self.lock["synthetic_vectors"] == [list(v) for v in SYNTHETIC_VECTORS],
            "STAGE10_TRANSLITERATION_VECTOR_LOCK_MISMATCH",
        )
        paths = {}
        for asset in self.lock["artifacts"]:
            c.require(asset["role"] not in paths, "STAGE10_RUNTIME_DUPLICATE_ASSET")
            paths[asset["role"]] = _private_file(
                root, asset["relative_path"], asset["sha256"], asset["bytes"]
            )
        c.require(
            set(paths)
            == {"BRIDGE", "ICU_I18N_STATIC", "ICU_COMMON_STATIC", "ICU_DATA_STATIC"},
            "STAGE10_RUNTIME_ASSET_SET_MISMATCH",
        )
        self.library: Any = ctypes.CDLL(str(paths["BRIDGE"]), mode=ctypes.RTLD_LOCAL)
        byte_pointer = ctypes.POINTER(ctypes.c_uint8)
        int_pointer = ctypes.POINTER(ctypes.c_int32)
        self.library.safe_stage10_versions.argtypes = [
            byte_pointer,
            byte_pointer,
            byte_pointer,
        ]
        self.library.safe_stage10_versions.restype = ctypes.c_int32
        self.library.safe_stage10_open.argtypes = [ctypes.c_int32, int_pointer]
        self.library.safe_stage10_open.restype = ctypes.c_void_p
        self.library.safe_stage10_transform.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int32,
            ctypes.c_void_p,
            ctypes.c_int32,
            int_pointer,
        ]
        self.library.safe_stage10_transform.restype = ctypes.c_int32
        self.library.safe_stage10_close.argtypes = [ctypes.c_void_p]
        self.library.safe_stage10_close.restype = None
        versions = [(ctypes.c_uint8 * 4)() for _ in range(3)]
        status = self.library.safe_stage10_versions(*versions)
        c.require(
            status == 0 and tuple(tuple(v) for v in versions) == EXPECTED_VERSIONS,
            "STAGE10_ICU_LOADED_VERSION_MISMATCH",
        )
        try:
            for ordinal, script in enumerate(("Greek", "Cyrillic"), 1):
                error = ctypes.c_int32()
                handle = self.library.safe_stage10_open(ordinal, ctypes.byref(error))
                c.require(
                    bool(handle) and error.value == 0,
                    "STAGE10_ICU_TRANSFORM_OPEN_FAILED",
                )
                self.handles[script] = handle
            for script, value, expected in SYNTHETIC_VECTORS:
                c.require(
                    self.transform(script, value) == expected,
                    "STAGE10_ICU_SYNTHETIC_VECTOR_MISMATCH",
                )
        except BaseException:
            self.close()
            raise
        self.lock_sha256 = c.sha256_file(lock_path)
        self.asset_binding = c.identity(
            "stage10-transform-assets:v1",
            bytes.fromhex(c.sha256_file(spec_path)),
            bytes.fromhex(self.lock_sha256),
        )

    def transform(self, script: str, value: str) -> str:
        c.require(script in self.handles, "STAGE10_ICU_SCRIPT_INVALID")
        raw = value.encode(
            "utf-16-le" if sys_byteorder() == "little" else "utf-16-be", errors="strict"
        )
        c.require(len(raw) // 2 < 2**31, "STAGE10_ICU_SCALAR_CAPACITY_EXCEEDED")
        required = ctypes.c_int32()
        capacity = max(32, len(raw))
        c.require(capacity < 2**31, "STAGE10_ICU_SCALAR_CAPACITY_EXCEEDED")
        output = ctypes.create_string_buffer(capacity * 2)
        status = self.library.safe_stage10_transform(
            self.handles[script],
            raw,
            len(raw) // 2,
            output,
            capacity,
            ctypes.byref(required),
        )
        if status == 15:  # U_BUFFER_OVERFLOW_ERROR, exact required UTF-16 length.
            c.require(
                0 < required.value < 2**31 - 1, "STAGE10_ICU_SCALAR_CAPACITY_EXCEEDED"
            )
            capacity = required.value + 1
            output = ctypes.create_string_buffer(capacity * 2)
            status = self.library.safe_stage10_transform(
                self.handles[script],
                raw,
                len(raw) // 2,
                output,
                capacity,
                ctypes.byref(required),
            )
        c.require(
            status <= 0 and 0 <= required.value <= capacity,
            "STAGE10_ICU_TRANSFORM_FAILED",
        )
        return output.raw[: required.value * 2].decode(
            "utf-16-le" if sys_byteorder() == "little" else "utf-16-be", errors="strict"
        )

    def close(self) -> None:
        for handle in self.handles.values():
            self.library.safe_stage10_close(handle)
        self.handles.clear()


def sys_byteorder() -> str:
    import sys

    return sys.byteorder
