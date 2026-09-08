"""Offline, hash-locked public inputs and bounded reference projections.

This module never downloads data. Archive members are read in place, not
extracted. Public coordinates remain in the retained raw archive only. The
GeoNames physical index is one normalized record per public object, not a new
geographic entity or a cross-product of locality/admin names.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pyarrow as pa

from . import s09_reference_contract as c


ISO_FIELDS = frozenset(
    "alpha_2 alpha_3 numeric code name official_name common_name type parent".split()
)
LIA_FIELDS = frozenset(
    """fmt id isoid key lang languages lfmt lfname lname locality_name_type
name postprefix posturl require state_name_type sub_isoids sub_keys sub_lfnames
sub_lnames sub_mores sub_names sub_xrequires sub_xzips sub_zipexs sub_zips
sublocality_name_type upper xrequire xzip zip zip_name_type zipex""".split()
)
GN_FIELDS = (
    "country_code",
    "postal_code",
    "place_name",
    "admin_name1",
    "admin_code1",
    "admin_name2",
    "admin_code2",
    "admin_name3",
    "admin_code3",
)
INDEX_VERSION = "stage09_reference_index_v1"
GN_INDEX_SCHEMA = pa.schema(
    [
        pa.field("reference_object_id", pa.binary(32), nullable=False),
        *[
            pa.field(n, pa.large_string(), nullable=False)
            for n in ("country", "postcode", "locality", "admin1", "admin2", "admin3")
        ],
    ]
)


def regular_private(path: Path, *, directory: bool = False) -> None:
    try:
        info = path.lstat()
    except OSError:
        raise c.Stage09Error("REQUIRED_PATH_UNAVAILABLE") from None
    c.require(
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode),
        "PATH_TYPE_INVALID",
    )
    c.require(
        stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600),
        "PATH_PERMISSIONS_INVALID",
    )


def confined(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    c.require(
        not relative.is_absolute()
        and ".." not in relative.parts
        and bool(relative.parts),
        "REFERENCE_PATH_ESCAPE",
    )
    target = root.joinpath(*relative.parts)
    c.require(
        target.resolve().is_relative_to(root.resolve()) and not target.is_symlink(),
        "REFERENCE_PATH_ESCAPE",
    )
    return target


def verify_lock(root: Path, lock_path: Path) -> dict[str, Any]:
    """Verify all retained bodies AND every locked compressed member first."""
    c.require(
        c.sha256_file(lock_path) == c.LOCK_SHA256, "FROZEN_REFERENCE_LOCK_MISMATCH"
    )
    lock = c.read_json(lock_path)
    regular_private(root, directory=True)
    for item in lock["file_inventory"]:
        path = confined(root, item["relative_path"])
        regular_private(path)
        c.require(
            path.stat().st_size == item["bytes"]
            and c.sha256_file(path) == item["sha256"],
            "LOCKED_REFERENCE_ASSET_MISMATCH",
        )
        headers = confined(root, item["relative_path"] + ".headers")
        regular_private(headers)
        c.require(
            c.sha256_file(headers) == item["headers_sha256"],
            "REFERENCE_HTTP_PROVENANCE_HASH_MISMATCH",
        )
        if item["member_inventory"]:
            with zipfile.ZipFile(path) as archive:
                expected = {m["path"]: m for m in item["member_inventory"]}
                c.require(
                    len(archive.infolist()) == len(expected)
                    and set(archive.namelist()) == set(expected),
                    "ARCHIVE_INVENTORY_MISMATCH",
                )
                for entry in archive.infolist():
                    member = expected[entry.filename]
                    c.require(
                        entry.file_size == member["bytes"]
                        and entry.compress_size == member["compressed_bytes"],
                        "ARCHIVE_MEMBER_SIZE_MISMATCH",
                    )
                    digest = hashlib.sha256()
                    with archive.open(entry) as stream:
                        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                            digest.update(chunk)
                    c.require(
                        digest.hexdigest() == member["sha256"],
                        "ARCHIVE_MEMBER_HASH_MISMATCH",
                    )
    return lock


def _asset_prototypes(
    lock: Mapping[str, Any], reference: Mapping[str, Any]
) -> list[dict[str, Any]]:
    licenses = {v.split("#")[0] for v in reference["license_assets"]}
    result = []
    for item in lock["file_inventory"]:
        if (
            item["reference_id"] != reference["reference_id"]
            and item["relative_path"] not in licenses
        ):
            continue
        base = {
            "role": item["role"],
            "relative_path": item["relative_path"],
            "source_url": item["source_url"],
            "member_path": None,
            "retrieval_utc": item["retrieval_completed_utc"],
            "publisher_release": reference["dataset_release"],
            "last_modified": item["last_modified"],
            "etag": item["etag"],
            "bytes": item["bytes"],
            "sha256": bytes.fromhex(item["sha256"]),
            "media_type": "application/octet-stream",
            "provenance": "FROZEN_PUBLIC_DOWNLOAD",
        }
        result.append(base)
        for member in item["member_inventory"]:
            result.append(
                {
                    **base,
                    "role": "DATA_MEMBER"
                    if member["scientific_input"]
                    else "ARCHIVE_MEMBER_PROVENANCE",
                    "member_path": member["path"],
                    "bytes": member["bytes"],
                    "sha256": bytes.fromhex(member["sha256"]),
                    "provenance": "EXACT_LOCKED_ARCHIVE_MEMBER",
                }
            )
    c.require(len(result) <= 512, "REFERENCE_ASSET_BOUND_EXCEEDED")
    return sorted(
        result,
        key=lambda a: (
            a["role"],
            a["relative_path"],
            a["member_path"] is not None,
            a["member_path"] or "",
            a["sha256"],
        ),
    )


def registry_rows(lock: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for reference in lock["references"]:
        assets = _asset_prototypes(lock, reference)
        tuples = tuple(
            (a["role"], a["relative_path"], a["member_path"], a["sha256"])
            for a in assets
        )
        raw = c.identity("RAW_REFERENCE", (reference["reference_id"], tuples))
        version = c.identity(
            "REFERENCE_VERSION",
            (
                reference["reference_id"],
                reference["dataset_release"],
                lock["edition"],
                raw,
            ),
        )
        for asset in assets:
            asset["asset_id"] = c.identity(
                "REFERENCE_ASSET",
                (
                    version,
                    asset["relative_path"],
                    asset["member_path"],
                    asset["sha256"],
                ),
            )
        result.append(
            {
                "reference_version_id": version,
                "reference_id": reference["reference_id"],
                "dataset_name": reference["dataset_name"],
                "dataset_release": reference["dataset_release"],
                "edition": lock["edition"],
                "evidence_family": reference["evidence_family"],
                "retrieval_utc": max(a["retrieval_utc"] for a in assets),
                "effective_date": reference["effective_date"],
                "license_expression": reference["license_expression"],
                "license_note": reference.get(
                    "license_note", reference["license_status"]
                ),
                "normalization_contract": c.NORMALIZATION_VERSION,
                "countries": reference["countries"],
                "limitations": reference["limitations"],
                "assets": assets,
                "lineage": [
                    {
                        "token": a,
                        "parent_token": b,
                        "relation": rel,
                        "pelias_overlap": reference["pelias_overlap"],
                        "provenance": "FROZEN_REFERENCE_LOCK",
                    }
                    for a, b, rel in reference["lineage"]
                ],
                "raw_dataset_sha256": raw,
            }
        )
    return sorted(result, key=lambda row: row["reference_version_id"])


def set_capability_id(row: dict[str, Any]) -> dict[str, Any]:
    values = tuple(
        row[f.name]
        for f in c.relation_schema("reference_capability")
        if f.name != "capability_id"
    )
    row["capability_id"] = c.identity("REFERENCE_CAPABILITY", values)
    return row


def matrix_capabilities(
    lock: Mapping[str, Any], registry: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    refs = {r["reference_id"]: r for r in registry}
    templates = {
        (r["reference_id"], r["question_catalog_id"]): r
        for r in lock["capability_registry"]["rules"]
    }
    countries = refs[c.ISO]["countries"] + ["UNRESOLVED"]
    result = []
    for question in c.CATALOG:
        for reference in question.references:
            if reference == "NONE":
                continue
            template = templates[(reference, question.question_id)]
            for country in (
                ["GLOBAL"] if question.question_id in ("Q01", "Q14") else countries
            ):
                enabled = country in template["country_scope_selector"]
                row = {
                    "reference_version_id": refs[reference]["reference_version_id"],
                    "country_scope": country,
                    "question_catalog_id": question.question_id,
                    "capability": c.capability_name(question, reference),
                    "scope_locator": "COUNTRY_MATRIX",
                    "enabled": enabled,
                    "positive_authority": enabled and template["positive_authority"],
                    "positive_authority_basis": template["positive_authority_basis"]
                    if enabled
                    else "NONE",
                    "negative_authority": enabled and template["negative_authority"],
                    "negative_authority_basis": template["negative_authority_basis"]
                    if enabled
                    else "NONE",
                    "claim_scope": question.claim_scope,
                    "coverage_kind": (
                        "UNAVAILABLE"
                        if not enabled
                        else "CODE_NAMESPACE"
                        if reference == c.ISO
                        else "FORMAT_RULE"
                        if question.question_id in ("Q03", "Q04", "Q08", "Q15")
                        else "ENUMERATED_PARTIAL"
                    ),
                    "granularity": question.granularity,
                    "required_roles": list(question.roles),
                    "normalization_id": c.NORMALIZATION_VERSION,
                    "limitations": [
                        template["object_gate"],
                        *refs[reference]["limitations"],
                    ],
                }
                if reference == c.GN:
                    if (
                        country
                        in lock["capability_registry"][
                            "geonames_full_code_disabled_countries"
                        ]
                    ):
                        row["limitations"].append(
                            "PARTIAL_POSTCODE_NO_FULL_CODE_AUTHORITY"
                        )
                    if (
                        country
                        in lock["capability_registry"][
                            "geonames_major_code_only_countries"
                        ]
                    ):
                        row["limitations"].append("MAJOR_POSTCODES_ONLY")
                    if country == "US":
                        row["limitations"].append("ZIP_PLUS_FOUR_ABSTENTION")
                result.append(set_capability_id(row))
    return sorted(result, key=lambda row: row["capability_id"])


def safe_pattern(pattern: str) -> bool:
    """Exactly the freeze audit's ASCII grammar; matching itself uses RE2.

    Python's internal syntax tree is used only with the exact runtime guard.
    Its private API is thus runtime-bound, not an unversioned regex translator.
    """
    from re import _constants as op, _parser  # type: ignore[attr-defined]

    def walk(nodes: Any) -> bool:
        for kind, argument in nodes:
            if kind == op.LITERAL:
                if not 0 <= argument < 128:
                    return False
            elif kind == op.IN:
                for child, value in argument:
                    if child == op.LITERAL and 0 <= value < 128:
                        continue
                    if child == op.RANGE and 0 <= value[0] <= value[1] < 128:
                        continue
                    if child == op.CATEGORY and value == op.CATEGORY_DIGIT:
                        continue
                    if child == op.NEGATE:
                        continue
                    return False
            elif kind == op.SUBPATTERN:
                if argument[1] or argument[2] or not walk(argument[3]):
                    return False
            elif kind == op.BRANCH:
                if not all(walk(branch) for branch in argument[1]):
                    return False
            elif kind == op.MAX_REPEAT:
                if not walk(argument[2]):
                    return False
            elif kind == op.AT:
                if argument not in (op.AT_BEGINNING, op.AT_END):
                    return False
            else:
                return False
        return True

    try:
        tree = _parser.parse(pattern, re.ASCII)
        return tree.state.flags == re.ASCII and walk(tree)
    except re.error:
        return False


def field(
    name: str,
    value: str,
    locator: str,
    *,
    ordinal: int = 0,
    alias: str = "EXPLICIT_FIELD",
    language: str | None = None,
    level: str | None = None,
) -> dict[str, Any]:
    c.require(isinstance(value, str), "REFERENCE_FIELD_NOT_STRING")
    return {
        "field_name": name,
        "ordinal": ordinal,
        "original_value": value,
        "source_field_locator": locator,
        "alias_role": alias,
        "language_tag": language,
        "geographic_level": level,
    }


def make_object(
    version: bytes,
    asset: bytes,
    locator: str,
    kind: str,
    country: str | None,
    fields: list[dict[str, Any]],
    parent: bytes | None = None,
) -> dict[str, Any]:
    c.require(len(fields) <= 512, "REFERENCE_FIELD_BOUND_EXCEEDED")
    return {
        "reference_object_id": c.identity(
            "REFERENCE_OBJECT", (version, asset, locator, kind)
        ),
        "reference_version_id": version,
        "asset_id": asset,
        "source_locator": locator,
        "object_kind": kind,
        "country_code": country,
        "explicit_parent_id": parent,
        "fields": sorted(fields, key=lambda f: (f["field_name"], f["ordinal"])),
    }


def iso_objects(
    data: Sequence[Mapping[str, str]],
    registry: Mapping[str, Any],
    asset: Mapping[str, Any],
    *,
    subdivision: bool,
) -> Iterator[dict[str, Any]]:
    kind, table, key = (
        ("ISO_ADMIN", "3166-2", "code")
        if subdivision
        else ("ISO_COUNTRY", "3166-1", "alpha_2")
    )
    version, aid = registry["reference_version_id"], asset["asset_id"]
    locators = {r[key]: f"/{table}/{i}/{r[key]}" for i, r in enumerate(data)}
    c.require(len(locators) == len(data), "DUPLICATE_ISO_CODE")
    for record in data:
        # The locked country input also has a flag glyph; it is not an
        # approved lookup field and remains solely in the immutable raw JSON.
        c.require(set(record) <= ISO_FIELDS | {"flag"}, "ISO_FIELD_ALLOWLIST_CHANGED")
        locator = locators[record[key]]
        parent = record.get("parent")
        c.require(parent is None or parent in locators, "ISO_PARENT_UNRESOLVED")
        parent_id = (
            c.identity("REFERENCE_OBJECT", (version, aid, locators[parent], kind))
            if parent
            else None
        )
        yield make_object(
            version,
            aid,
            locator,
            kind,
            record[key][:2],
            [
                field(n, v, f"{locator}/{n}")
                for n, v in record.items()
                if n in ISO_FIELDS
            ],
            parent_id,
        )


def _language_path(key: str) -> tuple[str, str | None]:
    path, separator, language = key.partition("--")
    return path, language if separator else None


def metadata_objects(
    data: Mapping[str, Mapping[str, str]],
    registry: Mapping[str, Any],
    asset: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Bounded by the locked 2 MiB metadata member, never by source population."""
    nodes: dict[str, dict[str, Any]] = {}
    version, aid = registry["reference_version_id"], asset["asset_id"]
    countries = frozenset(registry["countries"])

    def ensure(key: str, locator: str) -> dict[str, Any]:
        path, language = _language_path(key)
        depth = path.count("/")
        c.require(depth <= 3, "METADATA_DEPTH_UNSUPPORTED")
        if key not in nodes:
            kind = (
                "FORMAT_COUNTRY",
                "FORMAT_ADMIN",
                "FORMAT_LOCALITY",
                "FORMAT_DEPENDENT_LOCALITY",
            )[depth]
            nodes[key] = make_object(
                version,
                aid,
                key if key in data else locator,
                kind,
                path[:2] if path[:2] in countries else None,
                [],
            )
        return nodes[key]

    for key, record in sorted(data.items()):
        c.require(set(record) <= LIA_FIELDS, "METADATA_FIELD_ALLOWLIST_CHANGED")
        node = ensure(key, key)
        path, suffix = _language_path(key)
        language = record.get("lang", suffix)
        for name, value in sorted(record.items()):
            alias = (
                "LATIN_ALIAS"
                if name in ("lname", "lfname")
                else "NATIVE_ALIAS"
                if name == "name"
                else "EXPLICIT_KEY"
                if name == "key"
                else "EXPLICIT_FIELD"
            )
            node["fields"].append(
                field(
                    name,
                    value,
                    f"{key}/{name}",
                    language=language,
                    alias=alias,
                    level=str(path.count("/")),
                )
            )
        keys = record.get("sub_keys", "").split("~") if record.get("sub_keys") else []
        aligned = {}
        for name in (
            "sub_names",
            "sub_lnames",
            "sub_lfnames",
            "sub_zips",
            "sub_xzips",
            "sub_isoids",
        ):
            if name in record:
                values = record[name].split("~")
                c.require(len(values) == len(keys), "FROZEN_METADATA_ALIGNMENT_CHANGED")
                aligned[name] = values
        for ordinal, subkey in enumerate(keys):
            c.require(bool(subkey), "EMPTY_METADATA_CHILD_KEY")
            child_key = path + "/" + subkey + ("--" + suffix if suffix else "")
            child = ensure(child_key, f"{key}/sub_keys/{ordinal}")
            parent_id = node["reference_object_id"]
            c.require(
                child["explicit_parent_id"] in (None, parent_id),
                "METADATA_PARENT_CONFLICT",
            )
            child["explicit_parent_id"] = parent_id
            child["fields"].append(
                field(
                    "sub_keys",
                    subkey,
                    f"{key}/sub_keys/{ordinal}",
                    ordinal=ordinal,
                    alias="EXPLICIT_KEY",
                    language=language,
                    level=str(path.count("/") + 1),
                )
            )
            for name, values in aligned.items():
                if values[ordinal]:
                    alias = (
                        "LATIN_ALIAS"
                        if name in ("sub_lnames", "sub_lfnames")
                        else "NATIVE_ALIAS"
                        if name == "sub_names"
                        else "EXPLICIT_FIELD"
                    )
                    child["fields"].append(
                        field(
                            name,
                            values[ordinal],
                            f"{key}/{name}/{ordinal}",
                            ordinal=ordinal,
                            alias=alias,
                            language=language,
                            level=str(path.count("/") + 1),
                        )
                    )
    # Nodes absent from sub_keys may still carry an explicit path. Bind the
    # exact same-language parent only; never invent cross-language alignment.
    for key, node in nodes.items():
        path, suffix = _language_path(key)
        if "/" in path and node["explicit_parent_id"] is None:
            parent_key = path.rsplit("/", 1)[0] + ("--" + suffix if suffix else "")
            c.require(parent_key in nodes, "METADATA_PARENT_MISSING")
            node["explicit_parent_id"] = nodes[parent_key]["reference_object_id"]
        # Ordinals belong to the object's field namespace, not to a parent's
        # array. The exact parent array offset stays in source_field_locator.
        node["fields"].sort(key=lambda f: (f["field_name"], f["source_field_locator"]))
        field_counts: dict[str, int] = {}
        for entry in node["fields"]:
            entry["ordinal"] = field_counts.get(entry["field_name"], 0)
            field_counts[entry["field_name"]] = entry["ordinal"] + 1
        c.require(len(node["fields"]) <= 512, "REFERENCE_FIELD_BOUND_EXCEEDED")
        field_keys = [(f["field_name"], f["ordinal"]) for f in node["fields"]]
        c.require(
            len(field_keys) == len(set(field_keys)), "REFERENCE_FIELD_KEY_COLLISION"
        )
    return sorted(nodes.values(), key=lambda row: row["reference_object_id"])


def metadata_rule_capabilities(
    objects: Sequence[Mapping[str, Any]], matrix: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    templates = {(r["country_scope"], r["question_catalog_id"]): r for r in matrix}
    result = []
    for obj in objects:
        country = obj["country_code"]
        if country is None:
            continue
        if obj["object_kind"] == "FORMAT_COUNTRY":
            fields = {f["field_name"]: f for f in obj["fields"]}
            # Country rules use the unqualified root, not arbitrary languages.
            if obj["source_locator"] != country:
                continue
            for question, name in (("Q03", "fmt"), ("Q04", "zip"), ("Q15", "require")):
                template = templates[(country, question)]
                entry = fields.get(name)
                if (
                    entry is not None
                    and entry["original_value"]
                    and template["enabled"]
                ):
                    c.require(
                        question != "Q04" or safe_pattern(entry["original_value"]),
                        "FROZEN_ENABLED_PATTERN_UNSAFE",
                    )
                    result.append(
                        set_capability_id(
                            {**template, "scope_locator": entry["source_field_locator"]}
                        )
                    )
        elif obj["object_kind"] == "FORMAT_ADMIN":
            prefixes = [
                f
                for f in obj["fields"]
                if f["field_name"] in ("zip", "sub_zips") and f["original_value"]
            ]
            alternate = any(
                f["field_name"] in ("xzip", "sub_xzips") and f["original_value"]
                for f in obj["fields"]
            )
            template = templates[(country, "Q08")]
            if (
                template["enabled"]
                and prefixes
                and not alternate
                and all(safe_pattern(f["original_value"]) for f in prefixes)
            ):
                locators = sorted(f["source_field_locator"] for f in prefixes)
                result.append(
                    set_capability_id(
                        {
                            **template,
                            "scope_locator": "PREFIX_BUNDLE:"
                            + json.dumps(
                                [obj["source_locator"], country + "/zip", *locators],
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        }
                    )
                )
        # Enumeration permission is positive only. Its object field gate is
        # independently witnessed, not a unique entity selection.
        if obj["object_kind"] in ("FORMAT_ADMIN", "FORMAT_LOCALITY"):
            questions = (
                ("Q10",) if obj["object_kind"] == "FORMAT_ADMIN" else ("Q09", "Q11")
            )
            for question in questions:
                template = templates[(country, question)]
                if template["enabled"]:
                    for entry in obj["fields"]:
                        if (
                            entry["alias_role"]
                            in ("NATIVE_ALIAS", "LATIN_ALIAS", "EXPLICIT_KEY")
                            and entry["original_value"]
                        ):
                            result.append(
                                set_capability_id(
                                    {
                                        **template,
                                        "scope_locator": entry["source_field_locator"],
                                    }
                                )
                            )
    return sorted(result, key=lambda row: row["capability_id"])


def geonames_objects(
    stream: io.TextIOBase, registry: Mapping[str, Any], asset: Mapping[str, Any]
) -> Iterator[dict[str, Any]]:
    countries = frozenset(registry["countries"])
    for ordinal, line in enumerate(stream):
        values = line.removesuffix("\n").removesuffix("\r").split("\t")
        c.require(
            len(values) == 12 and values[0] in countries,
            "GEONAMES_RECORD_SHAPE_CHANGED",
        )
        locator = f"{asset['member_path']}:{ordinal}"
        yield make_object(
            registry["reference_version_id"],
            asset["asset_id"],
            locator,
            "POSTAL_ASSOCIATION",
            values[0],
            [
                field(
                    name,
                    value,
                    f"{locator}/{name}",
                    level=str((i - 1) // 2) if name.startswith("admin_") else None,
                )
                for i, (name, value) in enumerate(
                    zip(GN_FIELDS, values[:9], strict=True)
                )
            ],
        )


def geonames_index_row(obj: Mapping[str, Any]) -> dict[str, Any]:
    values = {f["field_name"]: f["original_value"] for f in obj["fields"]}
    country = values["country_code"]
    method = c.SEPARATOR_NORM if country in c.POSTCODE_SEPARATORS else c.EXACT_NORM
    return {
        "reference_object_id": obj["reference_object_id"],
        "country": country,
        "postcode": c.normalize(method, values["postal_code"], country),
        "locality": c.normalize(c.NAME_NORM, values["place_name"]),
        **{
            f"admin{i}": c.normalize(c.NAME_NORM, values[f"admin_name{i}"])
            for i in (1, 2, 3)
        },
    }


@dataclass(frozen=True)
class PublicInputs:
    root: Path
    lock: Mapping[str, Any]
    registry: Sequence[Mapping[str, Any]]

    def asset(self, reference: str, input_number: int = 0) -> Mapping[str, Any]:
        record = next(
            r for r in self.lock["references"] if r["reference_id"] == reference
        )
        selector = record["scientific_inputs"][input_number]
        path, separator, member = selector.partition("#")
        registry = next(r for r in self.registry if r["reference_id"] == reference)
        return next(
            a
            for a in registry["assets"]
            if a["relative_path"] == path
            and a["member_path"] == (member if separator else None)
        )

    def json_data(self, reference: str, input_number: int = 0) -> dict[str, Any]:
        asset = self.asset(reference, input_number)
        path = confined(self.root, asset["relative_path"])
        if asset["member_path"] is None:
            c.require(
                c.sha256_file(path) == asset["sha256"].hex(),
                "REFERENCE_CHANGED_BEFORE_USE",
            )
            return c.read_json(path)
        with zipfile.ZipFile(path) as archive:
            # The only JSON scientific member is 2 MiB, verified before this call.
            payload = archive.read(asset["member_path"])
            c.require(
                hashlib.sha256(payload).digest() == asset["sha256"],
                "REFERENCE_MEMBER_CHANGED_BEFORE_USE",
            )
            return dict(json.loads(payload, object_pairs_hook=c._unique_pairs))

    def small_objects(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        refs = {r["reference_id"]: r for r in self.registry}
        iso = list(
            iso_objects(
                self.json_data(c.ISO)["3166-1"],
                refs[c.ISO],
                self.asset(c.ISO),
                subdivision=False,
            )
        )
        iso.extend(
            iso_objects(
                self.json_data(c.ISO, 1)["3166-2"],
                refs[c.ISO],
                self.asset(c.ISO, 1),
                subdivision=True,
            )
        )
        metadata = metadata_objects(
            self.json_data(c.LIA), refs[c.LIA], self.asset(c.LIA)
        )
        return iso, metadata

    def postal_objects(self) -> Iterator[dict[str, Any]]:
        asset = self.asset(c.GN)
        registry = next(r for r in self.registry if r["reference_id"] == c.GN)
        archive_path = confined(self.root, asset["relative_path"])
        inventory = next(
            f
            for f in self.lock["file_inventory"]
            if f["relative_path"] == asset["relative_path"]
        )
        c.require(
            c.sha256_file(archive_path) == inventory["sha256"],
            "REFERENCE_ARCHIVE_CHANGED_BEFORE_USE",
        )
        with zipfile.ZipFile(archive_path) as archive:
            with archive.open(asset["member_path"]) as raw:
                with io.TextIOWrapper(
                    raw, encoding="utf-8", errors="strict", newline=""
                ) as stream:
                    yield from geonames_objects(stream, registry, asset)
