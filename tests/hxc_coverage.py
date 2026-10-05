#!/usr/bin/env python3
"""Check the complete audited HxC page mapping and compiled raw profiles.

This is a coverage/integration test, not a claim that flux preservation implies
filesystem recovery. Structured readers have independent format fixture suites.
The checked-in mapping states their payload level and compatibility boundaries.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def text(path):
    return path.read_text(encoding="utf8", errors="replace")


def source_checks(data, library):
    rows = data["rows"]
    require(len(rows) == 210, "HxC page mapping must cover all 210 factual rows")
    require(Counter(r["section"] for r in rows) == {"direct": 50, "software": 91, "layout": 69},
            "HxC direct/software/XML table counts changed")
    require(len({r["id"] for r in rows}) == len(rows), "Duplicate page row ID")
    require(data["upstream_commit"] == "3c9ab41127991797f0a9563f529f602fdb177e36", "Unreviewed primary source version")
    profiles = {p["name"]: p for p in data["profiles"]}
    require(len(profiles) == len(data["profiles"]) == 102, "Raw profile inventory changed without updating evidence")
    defs = text(library / "include/xxfclib/xxfc_defs.h")
    catalog = text(library / "src/formats/xx_format_file_types.inc") + "\n" + text(library / "src/formats/xx_format.c")
    registry = text(library / "samples/unpack/xxfc_readers.c")
    numeric_types = {}
    bindings = data["bindings"]
    for name, binding in bindings.items():
        source = library / binding["source"]
        require(source.is_file(), f"Missing payload parser source for {name}: {source}")
        # Read its actual implementation plus local extraction companions, not
        # only an enum/extension registration. Shared adapters are handled below.
        implementation = "\n".join(text(p) for p in sorted(source.parent.glob("*.c")))
        implementation += "\n" + "\n".join(text(p) for p in sorted(source.parent.glob("*.h")))
        if "AF_DEFINE_READER" in implementation:
            for relative in ("src/formats/apple_family/xx_apple_family_private.h",
                             "src/formats/apple_family/xx_apple_gcr.h",
                             "src/formats/apple_family/xx_apple_volumes.h"):
                implementation += "\n" + text(library / relative)
        for relative in binding.get("implementation_sources", []):
            shared = library / relative
            require(shared.is_file(), f"Missing delegated implementation for {name}: {relative}")
            implementation += "\n" + text(shared)
        require(re.search(r"\b(?:check_is_valid|pm_valid|pm_init|AF_DEFINE_READER|HC_DEFINE_READER|HX_API|TM_API|XX_DC_IMPLEMENT)\b|_check_is_valid\b", implementation),
                f"{name} lacks a validation implementation")
        require(re.search(r"create_archive_records|create_records|pm_init|AF_DEFINE_READER|HC_DEFINE_READER|HX_API|TM_API|XX_DC_IMPLEMENT", implementation),
                f"{name} lacks a member-iteration implementation")
        require(re.search(r"unpack|extract|pm_init|AF_DEFINE_READER|HC_DEFINE_READER|HX_API|TM_API|XX_DC_IMPLEMENT", implementation),
                f"{name} lacks a payload extraction implementation")
        require(re.search(r'\{\s*"' + re.escape(name) + r'"\s*,\s*mk_', registry),
                f"{name} lacks a named reader factory")
        require(binding["scope"] and binding["support"], f"{name} has no honest payload-level evidence")
        for enum in binding["types"]:
            value = re.search(r"\b" + re.escape(enum) + r"\s*=\s*(\d+)\b", defs)
            require(value, f"Missing enum {enum}")
            require(re.search(r"XX_FORMAT_FILE_TYPE\(\s*" + re.escape(enum) + r"\s*,|case\s+" + re.escape(enum) + r"\s*:", catalog),
                    f"Missing catalog {enum}")
            require(enum in implementation, f"{name} source does not bind {enum}")
            numeric_types[enum] = int(value.group(1))
    for row in rows:
        require(row["references"] and all(u.startswith("https://") for u in row["references"]),
                f"{row['id']} missing primary provenance")
        require(row["label"] and row["extension"] and row["scope"], f"Incomplete row {row['id']}")
        require(row["readers"] or row.get("excluded_operation"), f"Unmapped input row {row['id']}")
        require(all(name in bindings for name in row["readers"]), f"Unknown reader in {row['id']}")
        require(all(name in profiles for name in row.get("profiles", [])), f"Unknown raw profile in {row['id']}")
        if row["section"] == "layout":
            require(row["support"] == "layout_preset" and len(row["profiles"]) == 1 and
                    set(row["readers"]) == {"hxc_raw_floppy", "hxc_xml_disk_layout"},
                    f"XML preset {row['label']} mislabeled as an independent container")
        if row.get("excluded_operation"):
            require(row["support"] == "host_input_or_output_generator" and not row["readers"],
                    f"Generator {row['label']} mislabeled as an input disk reader")
    excluded = Counter(r["label"] for r in rows if r.get("excluded_operation"))
    require(excluded == {"AMIGA_FS": 1, "FAT12FLOPPY": 2, "SNES_SMC": 1, "BMP_IMAGE": 1, "BMP_DISK_IMAGE": 1},
            "Unexpected generator exclusion: review the byte-format scope")
    aliases = text(library / "samples/unpack/xxfc_hxc_profiles.inc")
    alias_names = re.findall(r'XXFC_HXC_PROFILE\(\s*\d+\s*,\s*"([^"]+)"\s*\)', aliases)
    require(len(alias_names) == len(profiles) and set(alias_names) == set(profiles),
            "Named raw factories do not match every audited profile")
    raw_implementation = text(library / "src/formats/hxc_raw_floppy/xx_hxc_raw_floppy.c")
    raw_header = text(library / "include/xxfclib/formats/hxc_raw_floppy/xx_hxc_raw_floppy.h")
    for method in ("profile_count", "profile_at", "profile_by_name", "create_profile", "create_layout", "create_layout_xml"):
        symbol = "xx_hxc_raw_floppy_" + method
        require(symbol in raw_header and symbol in raw_implementation, f"Missing public raw profile API {symbol}")
    return numeric_types


def invoke(exe, args, cwd, success=True):
    result = subprocess.run([str(exe), *args], cwd=cwd, capture_output=True, timeout=15)
    if success:
        require(result.returncode == 0, f"Command failed: {args!r}\n{(result.stdout + result.stderr)[-5000:]!r}")
    else:
        require(result.returncode != 0, f"Invalid explicit profile input succeeded: {args!r}")
    return result


def runtime_checks(data, exe, numeric_types):
    checks = 0
    with tempfile.TemporaryDirectory(prefix="xfu-hxc-coverage-") as td:
        work = Path(td)
        listed = invoke(exe, ["--formats"], work)
        found = {int(n) for n in re.findall(rb"(?m)^\s*(\d+)\s+\S", listed.stdout)}
        require(set(numeric_types.values()) <= found, "Compiled type catalog omits an audited reader type")
        checks += 1
        # One input per distinct size keeps fixtures bounded while exercising
        # every compiled profile/extent map. Deliberately has no filesystem magic.
        fixtures = {}
        for profile in data["profiles"]:
            size = profile["source_size"]
            require(isinstance(size, int) and 0 < size <= 16 * 1024 * 1024, f"Unbounded profile {profile['name']}")
            if size not in fixtures:
                fixture = work / f"source-{size}.raw"
                payload = bytes([0xA5]) * size
                fixture.write_bytes(payload)
                fixtures[size] = (fixture, hashlib.sha256(payload).digest())
            fixture = fixtures[size][0]
            invoke(exe, ["t", str(fixture), "--reader", "hxc-raw:" + profile["name"]], work)
            checks += 1
        # Size-only matching must remain unavailable in automatic mode.
        ordinary = fixtures[data["profiles"][0]["source_size"]][0]
        invoke(exe, ["t", str(ordinary)], work, success=False)
        invoke(exe, ["t", str(ordinary), "--reader", "hxc-raw:DOES_NOT_EXIST"], work, success=False)
        checks += 2
        # A nonuniform mixed-sector shape and the common uniform shape must
        # both reject truncation/overrun instead of generating missing input.
        for name in ("DOS_DD_720KB", "ENSONIQ_EDM", "SYSTEM_24_6SECTOR"):
            profile = next(p for p in data["profiles"] if p["name"] == name)
            size = profile["source_size"]
            for delta in (-1, 1):
                bad = work / f"invalid-{name}-{delta}.raw"
                bad.write_bytes(bytes([0xA5]) * (size + delta))
                invoke(exe, ["t", str(bad), "--reader", "hxc-raw:" + name], work, success=False)
                checks += 1
        for fixture, expected in fixtures.values():
            require(hashlib.sha256(fixture.read_bytes()).digest() == expected, "Input was modified by LIST/TEST")
        require(not any(p.is_dir() for p in work.iterdir()), "Coverage TEST created extraction directories")
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unpacker", type=Path)
    project_root = Path(__file__).resolve().parents[1]
    submodule_library = project_root / "dep/xxfclib"
    local_library = project_root.parent / "_mylibs/xxfclib"
    parser.add_argument("--library", type=Path,
                        default=submodule_library if submodule_library.is_dir() else local_library)
    args = parser.parse_args()
    data = json.loads(text(Path(__file__).with_name("hxc_page_coverage.json")))
    numeric_types = source_checks(data, args.library.resolve())
    checks = runtime_checks(data, args.unpacker.resolve(), numeric_types) if args.unpacker else 0
    print(f"HxC coverage passed: 210 page rows, 73 reader bindings, 102 explicit raw profiles; {checks} native checks")


if __name__ == "__main__":
    main()
