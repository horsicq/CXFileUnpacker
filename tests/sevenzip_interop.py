#!/usr/bin/env python3
"""Independent 7-Zip interoperability checks; extraction alone writes payloads.

Requires the official 7-Zip 26.03 executable, never the XFU helper as the oracle.
Run directories and a JSON report are preserved for inspection. Optional fixtures
are a JSON array of {"handler": "Chm", "path": "absolute/path", "label": "..."}.
Optional links_as_files names verify link-target streams without creating links.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HANDLERS = (
    "APFS APM Ar Arj Base64 bzip2 Compound Cpio CramFS Dmg ELF Ext FAT FLV "
    "gzip GPT HFS IHex LP Lzh lzma lzma86 MachO MBR MsLZ Mub NTFS PE COFF "
    "TE Ppmd QCOW Rpm Sparse Split SquashFS SWFc SWF UEFIc UEFIf VDI VHD "
    "VHDX VMDK Xar xz Z zstd 7z Cab Chm Hxs Iso Nsis Rar Rar5 tar Udf wim zip"
).split()
WRITERS = {"7z": "7z", "zip": "zip", "tar": "tar", "gz": "gzip",
           "bz2": "bzip2", "xz": "xz", "wim": "wim"}
RAW = {"gz", "bz2", "xz"}
PASSWORD = "7Zip interoperability password"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree(path: Path) -> dict[str, str]:
    return {p.relative_to(path).as_posix(): digest(p.read_bytes())
            for p in sorted(path.rglob("*")) if p.is_file()}


class Suite:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.root = args.root / ("run-" + time.strftime("%Y%m%d-%H%M%S") + "-" + str(os.getpid()))
        self.root.mkdir(parents=True)
        self.input = self.root / "input"
        (self.input / "nested").mkdir(parents=True)
        self.payloads = {
            "binary.bin": bytes(range(256)) * 257 + b"SevenZip\0interoperability\xff",
            "empty.bin": b"",
            "nested/данные.txt": "Unicode names and payloads: Привет, 世界.\n".encode(),
        }
        for name, data in self.payloads.items():
            (self.input / name).write_bytes(data)
        self.blocked_temp = self.root / "TEMP-is-a-file"
        self.blocked_temp.write_bytes(b"No disk spool allowed during TEST.\n")
        self.calls: list[dict] = []
        self.checks: list[dict] = []

    def require(self, condition: bool, label: str, **details):
        self.checks.append({"check": label, "passed": bool(condition), **details})
        if not condition:
            raise AssertionError(label + ": " + json.dumps(details, ensure_ascii=True))

    def run(self, program: Path, *arguments: object, success: bool = True,
            test_memory: bool = False, cwd: Path | None = None,
            extra_env: dict[str, str | None] | None = None) -> subprocess.CompletedProcess:
        command = [str(program)] + [str(a) for a in arguments]
        env = os.environ.copy()
        for name, value in (extra_env or {}).items():
            if value is None:
                env.pop(name, None)
            else:
                env[name] = value
        if test_memory:
            env.update({"TEMP": str(self.blocked_temp), "TMP": str(self.blocked_temp),
                        "TMPDIR": str(self.blocked_temp)})
        result = subprocess.run(command, cwd=cwd or self.input, env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=90)
        self.calls.append({"command": command, "returncode": result.returncode,
                           "stdout": result.stdout.decode("utf-8", "replace")[:8000],
                           "stderr": result.stderr.decode("utf-8", "replace")[:8000]})
        self.require((result.returncode == 0) == success, "command status",
                     command=command, returncode=result.returncode,
                     stdout=self.calls[-1]["stdout"], stderr=self.calls[-1]["stderr"])
        return result

    def snapshot(self) -> dict[str, tuple[int, int]]:
        return {p.relative_to(self.root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
                for p in self.root.rglob("*") if p.is_file()}

    def test(self, archive: Path, reader: str | None = None, password: str | None = None,
             success: bool = True, verbose: bool = False):
        arguments = ["t", archive]
        if reader:
            arguments.extend(["--reader", reader])
        if password is not None:
            arguments.append("-p" + password)
        if verbose:
            arguments.append("--verbose")
        before = self.snapshot()
        result = self.run(self.args.xfu, *arguments, success=success, test_memory=True)
        self.require(self.snapshot() == before, "TEST creates or changes no files",
                     archive=str(archive), reader=reader, success=success)
        lines = result.stdout.decode("utf-8", "replace").splitlines()
        if not verbose and lines:
            self.require(all(re.fullmatch(r"\s*\d+%\s*", line) for line in lines),
                         "quiet output contains percentages only", lines=lines)
            values = [int(line.strip()[:-1]) for line in lines]
            self.require(values == sorted(set(values)) and 0 <= values[0] <= values[-1] <= 100,
                         "TEST percentages increase within 0..100", values=values)
        if verbose and success:
            self.require(any(line.endswith(" -- OK") for line in lines), "verbose member results")
            self.require(not any(re.fullmatch(r"\s*\d+%\s*", line) for line in lines),
                         "verbose suppresses percentages")
        elif success:
            self.require(bool(lines) and all(re.fullmatch(r"\s*\d+%\s*", line) for line in lines),
                         "quiet output contains percentages only", lines=lines)
            self.require(lines[-1].strip() == "100%", "successful TEST reaches 100 percent")

    def extract(self, archive: Path, label: str, oracle: bool,
                reader: str | None = None, password: str | None = None,
                exclude: list[str] | None = None) -> dict[str, str]:
        output = self.root / "extracted" / label
        output.mkdir(parents=True)
        if oracle:
            arguments = ["x", "-y", "-bd", "-bb0", "-o" + str(output), archive]
            if reader:
                arguments.append("-t" + reader)
            arguments.extend("-x!" + name for name in (exclude or []))
        else:
            arguments = ["x", archive, "-o" + str(output)]
            if reader:
                arguments.extend(["--reader", reader])
        if password is not None:
            arguments.append("-p" + password)
        self.run(self.args.sevenzip if oracle else self.args.xfu, *arguments)
        return tree(output)

    def check_archive(self, archive: Path, slug: str, label: str,
                      expected: dict[str, bytes], password: str | None = None):
        oracle_args = ["t", "-bd", "-bb0", archive]
        if password is not None:
            oracle_args.append("-p" + password)
        self.run(self.args.sevenzip, *oracle_args)
        reference = self.extract(archive, label + "-official", True, password=password)
        self.require(sorted(reference.values()) == sorted(digest(p) for p in expected.values()),
                     "official extraction equals all original bytes", format=slug, tree=reference)
        self.test(archive, password=password)
        self.test(archive, "sevenzip_" + WRITERS[slug].lower(), password)
        self.test(archive, "sevenzip", password)
        self.test(archive, password=password, verbose=True)
        for reader, suffix in [(None, "automatic"), ("sevenzip_" + WRITERS[slug].lower(), "engine")]:
            actual = self.extract(archive, label + "-" + suffix, False, reader, password)
            if slug == "wim" and reader is None and "wim.xml" in actual and "wim.xml" not in reference:
                # Native WIM intentionally exposes its XML resource as a member.
                # Validate the exact stored resource, then compare only file payloads.
                image = archive.read_bytes()
                self.require(len(image) >= 96 and image[:8] == b"MSWIM\0\0\0", "valid WIM resource header")
                packed, offset, unpacked = struct.unpack_from("<QQQ", image, 72)
                size = packed & 0x00FFFFFFFFFFFFFF
                self.require(not ((packed >> 56) & 4) and size == unpacked and offset + size <= len(image),
                             "WIM XML is a complete stored resource")
                xml = (self.root / "extracted" / (label + "-" + suffix) / "wim.xml").read_bytes()
                self.require(xml == image[offset:offset + size], "native WIM XML equals exact archive resource")
                document = ET.fromstring(xml)
                images = document.findall("IMAGE")
                self.require(document.tag == "WIM" and len(images) == struct.unpack_from("<I", image, 44)[0] == 1,
                             "native WIM XML describes the single stored image")
                total = images[0].findtext("TOTALBYTES")
                if total is not None:
                    self.require(int(total) == sum(len(data) for data in expected.values()),
                                 "WIM XML image TOTALBYTES equals original payload sizes")
                del actual["wim.xml"]
            # Raw streams derive a name from the archive suffix; compare their only payload.
            self.require((sorted(actual.values()) == sorted(reference.values())) if slug in RAW
                         else actual == reference, "XFU extraction equals official extraction",
                         format=slug, reader=reader, actual=actual, reference=reference)
        self.run(self.args.xfu, "l", archive, "--reader", "sevenzip_" + WRITERS[slug].lower(),
                 *(["-p" + password] if password is not None else []))
        if self.args.engine_probe:
            self.run(self.args.engine_probe, archive, WRITERS[slug],
                     *([password] if password is not None else []), test_memory=True)

    def writers(self):
        for slug in WRITERS:
            cases = [("binary", {"binary.bin": self.payloads["binary.bin"]}),
                     ("empty", {"empty.bin": b""}),
                     ("unicode", {"nested/данные.txt": self.payloads["nested/данные.txt"]})]
            if slug not in RAW:
                cases.append(("multiple", self.payloads))
            for case, expected in cases:
                archive = self.root / ("xfu-" + case + "." + slug)
                self.run(self.args.xfu, "a", archive, *expected)
                self.check_archive(archive, slug, "xfu-" + slug + "-" + case, expected)
            reverse = self.root / ("official." + slug)
            names = {"binary.bin": self.payloads["binary.bin"]} if slug in RAW else self.payloads
            self.run(self.args.sevenzip, "a", "-y", "-bd", "-bb0",
                     "-t" + WRITERS[slug], reverse, *names)
            self.check_archive(reverse, slug, "official-" + slug, names)

    def rejected_writes(self):
        for slug in RAW:
            archive = self.root / ("keep-multiple." + slug)
            sentinel = b"Existing archive must survive rejected inputs.\0"
            archive.write_bytes(sentinel)
            result = self.run(self.args.xfu, "a", archive, "binary.bin", "empty.bin", success=False)
            self.require(b"requires exactly one input file" in result.stderr, "raw writer rejects input count explicitly")
            self.require(archive.read_bytes() == sentinel, "multiple raw inputs rejected before truncation",
                         format=slug)
        for slug in set(WRITERS) - {"7z", "zip"}:
            archive = self.root / ("keep-password." + slug)
            sentinel = b"Existing archive must survive unsupported encryption.\0"
            archive.write_bytes(sentinel)
            result = self.run(self.args.xfu, "a", archive, "binary.bin", "-p" + PASSWORD, success=False)
            self.require(b"password protection is supported" in result.stderr,
                         "unsupported encryption rejected by writer preflight")
            self.require(archive.read_bytes() == sentinel, "unsupported password rejected before truncation",
                         format=slug)

    def encryption(self):
        environment_name = "XFU_SEVENZIP_INTEROP_PASSWORD"
        missing_name = "XFU_SEVENZIP_INTEROP_MISSING_PASSWORD"
        literal_name = "-p-literal.txt"
        literal_payload = b"This filename begins with a password-option prefix.\n"
        (self.input / literal_name).write_bytes(literal_payload)
        for slug in ("7z", "zip"):
            archive = self.root / ("encrypted." + slug)
            self.run(self.args.xfu, "a", archive, *self.payloads, "-p" + PASSWORD)
            self.check_archive(archive, slug, "encrypted-" + slug, self.payloads, PASSWORD)
            for reader in (None, "sevenzip_" + slug):
                self.test(archive, reader, success=False)
                self.test(archive, reader, "wrong password", success=False)
            archive = self.root / ("environment-password." + slug)
            self.run(self.args.xfu, "a", archive, *self.payloads, "--password-env=" + environment_name,
                     extra_env={environment_name: PASSWORD})
            self.check_archive(archive, slug, "environment-password-" + slug, self.payloads, PASSWORD)
            for index, flags in enumerate((
                    ["-pfirst", "-psecond"],
                    ["-p" + PASSWORD, "--password-env=" + environment_name],
                    ["--password-env=" + missing_name])):
                kept = self.root / ("keep-password-options-" + str(index) + "." + slug)
                sentinel = b"Rejected password options must preserve the existing archive.\0"
                kept.write_bytes(sentinel)
                self.run(self.args.xfu, "a", kept, "binary.bin", *flags, success=False,
                         extra_env={environment_name: PASSWORD, missing_name: None})
                self.require(kept.read_bytes() == sentinel, "invalid password option rejected before truncation",
                             format=slug, flags=flags)
            archive = self.root / ("literal-password-name." + slug)
            self.run(self.args.xfu, "a", archive, "-p" + PASSWORD, "--", literal_name)
            self.check_archive(archive, slug, "literal-password-name-" + slug,
                               {literal_name: literal_payload}, PASSWORD)

    def registration(self):
        if os.name == "nt":
            # Inspect the shipped engine itself, not merely static aliases.
            runtime = self.args.xfu.parent / "xfusevenzip2603.dll"
            self.require(runtime.is_file(), "bundled engine runtime exists", path=str(runtime))
            dll = ctypes.WinDLL(str(runtime))
            count = ctypes.c_uint32()
            dll.GetNumberOfFormats.argtypes = [ctypes.POINTER(ctypes.c_uint32)]
            dll.GetNumberOfFormats.restype = ctypes.c_long
            dll.GetHandlerProperty2.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
            dll.GetHandlerProperty2.restype = ctypes.c_long
            ole = ctypes.WinDLL("oleaut32")
            ole.SysFreeString.argtypes = [ctypes.c_void_p]
            self.require(dll.GetNumberOfFormats(ctypes.byref(count)) == 0,
                         "engine returns actual handler count")
            names, writers = [], []
            for index in range(count.value):
                properties = []
                for property_id in (0, 4):
                    value = ctypes.create_string_buffer(32)
                    self.require(dll.GetHandlerProperty2(index, property_id, value) == 0,
                                 "engine returns handler property", index=index, property=property_id)
                    variant_type = struct.unpack_from("<H", value.raw)[0]
                    if property_id == 0:
                        self.require(variant_type == 8, "handler name is a BSTR", index=index)
                        pointer = struct.unpack_from("<Q" if ctypes.sizeof(ctypes.c_void_p) == 8 else "<I",
                                                     value.raw, 8)[0]
                        properties.append(ctypes.wstring_at(pointer))
                        ole.SysFreeString(pointer)
                    else:
                        self.require(variant_type == 11, "handler update flag is BOOL", index=index)
                        properties.append(bool(struct.unpack_from("<h", value.raw, 8)[0]))
                names.append(properties[0])
                if properties[1]:
                    writers.append(properties[0])
            self.require(names == HANDLERS, "shipped engine has all 60 exact upstream handlers", names=names)
            self.require(set(writers) == set(WRITERS.values()), "shipped engine has exactly seven writers",
                         writers=writers)
        archive = self.root / "not-an-archive.bin"
        archive.write_bytes(b"Definitely not an archive.\0\xff" * 2)
        for handler in HANDLERS:
            alias = "sevenzip_" + handler.lower()
            result = self.run(self.args.xfu, "l", archive, "--reader", alias, success=False)
            output = (result.stdout + result.stderr).decode("utf-8", "replace")
            self.require("invalid explicit reader selection" not in output,
                         "exact upstream handler is registered", handler=handler, alias=alias)
        result = self.run(self.args.xfu, "l", archive, "--reader", "sevenzip_not_real", success=False)
        self.require(b"invalid explicit reader selection" in result.stderr,
                     "unknown handler is rejected by registry")

    def fixture(self, path: Path, handler: str, label: str,
                links_as_files: list[str] | None = None):
        self.run(self.args.sevenzip, "t", "-bd", "-bb0", "-t" + handler, path)
        links = links_as_files or []
        reference = self.extract(path, label + "-official", True, handler, exclude=links)
        for name in links:
            metadata = self.run(self.args.sevenzip, "l", "-slt", "-ba", "-t" + handler, path, name)
            fields = metadata.stdout.decode("utf-8", "replace").splitlines()
            self.require(any(line.startswith("Mode = l") for line in fields),
                         "declared link fixture is an upstream symlink", handler=handler, member=name)
            raw = self.run(self.args.sevenzip, "x", "-so", "-bd", "-bb0", "-t" + handler, path, name)
            sizes = [int(line[7:]) for line in fields if line.startswith("Size = ")]
            self.require(sizes == [len(raw.stdout)], "official link stream has its exact declared size",
                         handler=handler, member=name, sizes=sizes, decoded_size=len(raw.stdout))
            normalized = name.replace("\\", "/")
            self.require(normalized not in reference, "link is excluded only from filesystem oracle extraction",
                         handler=handler, member=name)
            reference[normalized] = digest(raw.stdout)
        self.require(bool(reference), "fixture contains extractable payload", handler=handler, fixture=str(path))
        # Executable carriers expose sections only through an explicit engine
        # reader; automatic fallback must preserve their native validation.
        carrier = handler in {"PE", "ELF", "MachO"}
        self.test(path, success=not carrier)
        self.test(path, "sevenzip_" + handler.lower())
        actual = self.extract(path, label + "-engine", False, "sevenzip_" + handler.lower())
        self.require(actual == reference, "read-only handler payload equals official extraction",
                     handler=handler, reference=reference, actual=actual)
        if carrier:
            self.test(path, "sevenzip")
            automatic = self.extract(path, label + "-explicit-auto-engine", False, "sevenzip")
            self.require(automatic == reference, "explicit engine exposes official carrier sections",
                         handler=handler, reference=reference, actual=automatic)
        if self.args.engine_probe:
            self.run(self.args.engine_probe, path, handler, test_memory=True)

    def read_only_fixtures(self):
        raw = self.payloads["binary.bin"][:257]
        b64 = self.root / "payload.b64"
        b64.write_bytes(base64.encodebytes(raw))
        self.fixture(b64, "Base64", "base64")
        ihex = self.root / "payload.ihex"
        lines = []
        for offset in range(0, len(raw), 16):
            record = bytes((min(16, len(raw) - offset), offset >> 8, offset & 255, 0)) + raw[offset:offset + 16]
            lines.append(":" + record.hex().upper() + f"{(-sum(record)) & 255:02X}")
        ihex.write_text("\n".join(lines) + "\n:00000001FF\n", encoding="ascii")
        self.fixture(ihex, "IHex", "ihex")
        split = self.root / "split"
        split.mkdir()
        data = self.payloads["binary.bin"]
        for index, offset in enumerate(range(0, len(data), 20000), 1):
            (split / f"payload.{index:03d}").write_bytes(data[offset:offset + 20000])
        self.fixture(split / "payload.001", "Split", "split")
        # Valid CFBF v3 with a regular 4096-byte stream: eight payload sectors,
        # one directory sector and one FAT sector. No mini-stream is needed.
        compound = self.root / "payload.doc"
        header = bytearray(512)
        header[:8] = bytes.fromhex("D0CF11E0A1B11AE1")
        struct.pack_into("<HHHHH", header, 24, 0x3E, 3, 0xFFFE, 9, 6)
        struct.pack_into("<IIIIIIIII", header, 40, 0, 1, 8, 0, 4096,
                         0xFFFFFFFE, 0, 0xFFFFFFFE, 0)
        struct.pack_into("<109I", header, 76, 9, *([0xFFFFFFFF] * 108))
        directory = bytearray(512)
        for offset, name, kind, child, start, size in (
                (0, "Root Entry", 5, 1, 0xFFFFFFFE, 0),
                (128, "Payload", 2, 0xFFFFFFFF, 0, 4096)):
            encoded = (name + "\0").encode("utf-16-le")
            directory[offset:offset + len(encoded)] = encoded
            struct.pack_into("<HBBIII", directory, offset + 64, len(encoded), kind, 1,
                             0xFFFFFFFF, 0xFFFFFFFF, child)
            struct.pack_into("<IQ", directory, offset + 116, start, size)
        fat = [1, 2, 3, 4, 5, 6, 7, 0xFFFFFFFE, 0xFFFFFFFE, 0xFFFFFFFD]
        fat += [0xFFFFFFFF] * (128 - len(fat))
        compound.write_bytes(header + self.payloads["binary.bin"][:4096] + directory
                             + struct.pack("<128I", *fat))
        self.fixture(compound, "Compound", "compound")
        if self.args.fixtures:
            for index, fixture in enumerate(json.loads(self.args.fixtures.read_text(encoding="utf-8"))):
                self.fixture(Path(fixture["path"]), fixture["handler"],
                             "corpus-" + str(index) + "-" + fixture.get("label", fixture["handler"]),
                             fixture.get("links_as_files"))

    def execute(self):
        self.run(self.args.sevenzip, "i")
        self.registration()
        self.writers()
        self.rejected_writes()
        self.encryption()
        self.read_only_fixtures()

    def save(self, failure: str | None = None):
        report = self.root / "sevenzip-interop-report.json"
        report.write_text(json.dumps({"passed": failure is None, "failure": failure,
                                     "upstream_handler_count": len(HANDLERS),
                                     "upstream_writer_count": len(WRITERS),
                                     "checks": self.checks, "commands": self.calls}, indent=2,
                                    ensure_ascii=False), encoding="utf-8")
        print(str(report), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xfu", required=True, type=Path)
    parser.add_argument("--sevenzip", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--engine-probe", type=Path)
    parser.add_argument("--fixtures", type=Path)
    args = parser.parse_args()
    for name in ("xfu", "sevenzip", "engine_probe", "fixtures"):
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, value.resolve(strict=True))
    args.root = args.root.resolve()
    suite = Suite(args)
    try:
        suite.execute()
    except (AssertionError, OSError, ValueError, ET.ParseError, struct.error, subprocess.TimeoutExpired) as error:
        suite.save(str(error))
        print(str(error), file=sys.stderr)
        return 1
    suite.save()
    print(f"Passed {len(suite.checks)} checks; 60 registered readers and all seven writer families.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
