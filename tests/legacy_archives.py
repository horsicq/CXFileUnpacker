#!/usr/bin/env python3
"""Independent fixtures for legacy PYZ, Lzip, LOFI, and Palm PDB compatibility.

Run: python legacy_archives.py <xfu.exe> [--samples-root F:\\ARC\\ARC1_err]
Fixtures use Python's marshal/zlib/LZMA writers rather than xxfclib's encoders.
"""

import argparse
import hashlib
import lzma
import marshal
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib


def lzip(payload, version):
    packed = lzma.compress(payload, format=lzma.FORMAT_RAW, filters=[
        {"id": lzma.FILTER_LZMA1, "dict_size": 65536, "lc": 3, "lp": 0, "pb": 2}
    ])
    header = b"LZIP" + bytes([version, 16])
    trailer = struct.pack("<IQ", zlib.crc32(payload), len(payload))
    if version == 1:
        trailer += struct.pack("<Q", len(header) + len(packed) + 20)
    return header + packed + trailer


def pyz(payload, *, byte_order=">", dictionary=False, package=False, name="fixture"):
    packed = zlib.compress(payload)
    descriptor = (bool(package) if dictionary else int(package), 12, len(packed))
    table = {name: descriptor} if dictionary else [(name, descriptor)]
    toc = marshal.dumps(table, 2 if dictionary else 4)
    return b"PYZ\0" + b"\x2d\xed\x0d\x0a" + struct.pack(byte_order + "I", 12 + len(packed)) + packed + toc


def lofi(parts, *, algorithm="gzip-9", stored=()):
    segments = []
    for index, part in enumerate(parts):
        if index in stored:
            segments.append(b"\0" + part)
        elif algorithm == "lzma":
            # Python writes an unknown-size LZMA-alone header; lofiadm writes
            # the actual segment length and uses that bound during decode.
            packed = lzma.compress(part, format=lzma.FORMAT_ALONE)
            segments.append(b"\1" + packed[:5] + struct.pack("<Q", len(part)) + packed[13:])
        else:
            segments.append(b"\1" + zlib.compress(part, 9))
    index = [0]
    for segment in segments:
        index.append(index[-1] + len(segment))
    return (algorithm.encode("ascii").ljust(36, b"\0") +
            struct.pack(">III", len(parts[0]), len(index), len(parts[-1])) +
            struct.pack(">" + str(len(index)) + "Q", *index) + b"".join(segments))


def pdb(payload):
    header = bytearray(78)
    header[:32] = b"fixture\0stale\x01bytes".ljust(32, b"\x80")
    struct.pack_into(">H", header, 32, 8)
    header[60:68] = b"TEXTTEST"
    struct.pack_into(">H", header, 76, 1)
    return bytes(header) + struct.pack(">I", 88) + b"\x40\0\0\1\0\0" + payload


def run_case(executable, folder, label, data, expected=None, timeout=30):
    archive = folder / (label + ".data")
    output = folder / (label + "-output")
    archive.write_bytes(data)
    result = subprocess.run([str(executable), "x", str(archive), "-o" + str(output)],
                            capture_output=True, timeout=timeout, cwd=folder)
    files = {str(p.relative_to(output)).replace("\\", "/"): p.read_bytes()
             for p in output.rglob("*") if p.is_file()} if output.exists() else {}
    diagnostic = (result.stdout + result.stderr).decode("utf-8", "replace")
    if expected is None:
        assert result.returncode != 0, (label, "malformed input accepted", diagnostic)
        assert not files, (label, "malformed input produced files", files.keys())
    else:
        assert result.returncode == 0, (label, result.returncode, diagnostic)
        assert files == expected, (label, files.keys(), expected.keys(), diagnostic)
    print(label + ": passed")
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--samples-root", type=Path)
    args = parser.parse_args()
    executable = args.executable.resolve()
    payload = marshal.dumps(compile("result = 42\n", "fixture.py", "exec"))
    with tempfile.TemporaryDirectory(prefix="xfu-legacy-") as temporary:
        folder = Path(temporary)
        run_case(executable, folder, "pyz-modern-list", pyz(payload),
                 {"fixture.pyc.marshal": payload})
        run_case(executable, folder, "pyz-legacy-le-dict", pyz(payload, byte_order="<", dictionary=True),
                 {"fixture.pyc.marshal": payload})
        run_case(executable, folder, "pyz-be-dict-package", pyz(payload, dictionary=True, package=True),
                 {"fixture/__init__.pyc.marshal": payload})
        run_case(executable, folder, "pyz-unsafe-name", pyz(payload, byte_order="<", dictionary=True, name="../escape"))
        run_case(executable, folder, "pyz-dict-missing-terminator", pyz(payload, byte_order="<", dictionary=True)[:-1])
        broken = bytearray(pyz(payload, byte_order="<", dictionary=True))
        broken[8:12] = struct.pack("<I", len(broken) + 100)
        run_case(executable, folder, "pyz-invalid-toc", broken)
        decoded = b"Version zero and one Lzip fixture.\n" * 8
        version0 = lzip(decoded, 0)
        run_case(executable, folder, "lzip-v0", version0, {"payload": decoded})
        run_case(executable, folder, "lzip-v0-empty", lzip(b"", 0), {"payload": b""})
        run_case(executable, folder, "lzip-v1-concatenated", lzip(decoded, 1) + lzip(b"second member\n", 1),
                 {"payload": decoded + b"second member\n"})
        broken = bytearray(version0)
        broken[-12] ^= 1
        run_case(executable, folder, "lzip-v0-bad-crc", broken)
        broken = bytearray(version0)
        broken[-8:] = struct.pack("<Q", len(decoded) + 1)
        run_case(executable, folder, "lzip-v0-bad-size", broken)
        run_case(executable, folder, "lzip-v0-truncated", version0[:-3])
        run_case(executable, folder, "lzip-v0-concatenation-rejected", version0 + version0)
        lofi_parts = [b"first lofi segment\n" * 100, b"stored lofi segment\n" * 100, b"x"]
        # Full segments have the same geometry; the final stored segment is
        # intentionally one byte to exercise the minimum index extent.
        lofi_parts[1] = bytes(range(256)) * 7 + bytes(range(108))
        assert len(lofi_parts[0]) == len(lofi_parts[1])
        for algorithm in ("gzip", "gzip-6", "gzip-9", "lzma"):
            data = lofi(lofi_parts, algorithm=algorithm, stored=(1, 2))
            run_case(executable, folder, "lofi-" + algorithm + "-mixed", data,
                     {"lofi_image.img": b"".join(lofi_parts)})
        data = bytearray(lofi([b"lofi zlib checksum\n" * 100]))
        data[-1] ^= 1
        run_case(executable, folder, "lofi-bad-adler", data)
        data = bytearray(lofi(lofi_parts, stored=(1, 2)))
        struct.pack_into(">Q", data, 56, 0)  # a repeated, non-ascending index
        run_case(executable, folder, "lofi-descending-index", data)
        data = bytearray(lofi([b"lofi segment flag\n" * 100]))
        data[64] = 2
        run_case(executable, folder, "lofi-unknown-segment-flag", data)
        run_case(executable, folder, "pdb-stale-name-padding", pdb(b"Palm record\n"),
                 {"record_00000.bin": b"Palm record\n"})
        data = bytearray(pdb(b"Palm record\n"))
        struct.pack_into(">I", data, 78, len(data) + 1)
        run_case(executable, folder, "pdb-out-of-range-record", data)
        data = bytearray(pdb(b"Palm record\n"))
        data[0] = 0
        run_case(executable, folder, "pdb-empty-name", data)
        if args.samples_root:
            corpus = args.samples_root.resolve()
            def select(name, group="ARC3_err"):
                source = corpus / group / name
                if not source.is_dir():
                    source = corpus / name
                return min((p for p in source.iterdir() if p.is_file()),
                           key=lambda p: (p.stat().st_size, p.name.casefold()))
            data = select("PYZ_err").read_bytes()
            toc = marshal.loads(data[struct.unpack("<I", data[8:12])[0]:])
            expected = {}
            for name, (kind, offset, size) in toc.items():
                name = name.decode("ascii") if isinstance(name, bytes) else name
                target = name.replace(".", "/") + ("/__init__.pyc.marshal" if kind else ".pyc.marshal")
                expected[target] = zlib.decompress(data[offset:offset + size])
            run_case(executable, folder, "arc1-pyz-98-modules", data, expected)
            data = select("LZIP_err").read_bytes()
            code = data[5]
            base = 1 << (code & 31)
            decoded = lzma.decompress(data[6:-12], format=lzma.FORMAT_RAW, filters=[
                {"id": lzma.FILTER_LZMA1, "dict_size": base - base // 16 * (code >> 5), "lc": 3, "lp": 0, "pb": 2}
            ])
            crc, size = struct.unpack("<IQ", data[-12:])
            assert crc == zlib.crc32(decoded) and size == len(decoded)
            run_case(executable, folder, "arc1-lzip-v0", data, {"payload": decoded})
            data = select("PDB_err").read_bytes()
            count = struct.unpack_from(">H", data, 76)[0]
            offsets = [struct.unpack_from(">I", data, 78 + index * 8)[0]
                       for index in range(count)] + [len(data)]
            expected = {f"record_{index:05d}.bin": data[offsets[index]:offsets[index + 1]]
                        for index in range(count)}
            run_case(executable, folder, "arc1-palm-pdb", data, expected)
            data = select("LOFI_err", "ARC2_err").read_bytes()
            segment_size, count, last_size = struct.unpack_from(">III", data, 36)
            offsets = struct.unpack_from(">" + str(count) + "Q", data, 48)
            base = 48 + count * 8
            parts = []
            for index in range(count - 1):
                part = data[base + offsets[index]:base + offsets[index + 1]]
                decoded = part[1:] if part[0] == 0 else zlib.decompress(part[1:])
                assert len(decoded) == (last_size if index == count - 2 else segment_size)
                parts.append(decoded)
            image = b"".join(parts)
            print("ARC1 LOFI independent disk SHA256: " + hashlib.sha256(image).hexdigest())
            # The reader exposes embedded ISO files. Compare its files byte
            # for byte with extraction of the independently decoded image.
            raw_image = folder / "independent-lofi.iso"
            raw_output = folder / "independent-lofi-output"
            raw_image.write_bytes(image)
            result = subprocess.run([str(executable), "x", str(raw_image), "-o" + str(raw_output)],
                                    capture_output=True, timeout=120, cwd=folder)
            assert result.returncode == 0, result.stdout + result.stderr
            expected = {"ISO/" + str(p.relative_to(raw_output)).replace("\\", "/"): p.read_bytes()
                        for p in raw_output.rglob("*") if p.is_file()}
            assert expected, "LOFI reference disk has no ISO members"
            run_case(executable, folder, "arc1-lofi-gzip-9", data, expected, timeout=120)
    print("Legacy archive regressions passed")


if __name__ == "__main__":
    main()
