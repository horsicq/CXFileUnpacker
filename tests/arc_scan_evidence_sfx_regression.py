"""Independent byte fixtures for conservative all-files scan evidence.

Run with Python only. Does not build, execute samples, or decompress payloads.
"""
from pathlib import Path
import importlib.util
import struct
import tempfile
import zlib


MODULE = Path(__file__).resolve().parents[1] / "tools" / "arc_scan_evidence_sfx.py"
spec = importlib.util.spec_from_file_location("evidence_sfx", MODULE)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


def crc16(data):
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = value >> 1 ^ (0xa001 if value & 1 else 0)
    return value


def pe(payload=b"", raw_size=512):
    blob = bytearray(1024)
    blob[:2] = b"MZ"
    struct.pack_into("<I", blob, 60, 128)
    blob[128:132] = b"PE\0\0"
    struct.pack_into("<HH", blob, 132, 0x14c, 1)
    struct.pack_into("<H", blob, 148, 224)
    struct.pack_into("<H", blob, 152, 0x10b)
    struct.pack_into("<I", blob, 212, 512)
    blob[376:384] = b".data\0\0\0"
    struct.pack_into("<II", blob, 392, raw_size, 512)
    return bytes(blob) + payload


def dos(payload):
    blob = bytearray(64)
    blob[:2] = b"MZ"
    struct.pack_into("<4H", blob, 2, 64, 1, 0, 4)
    struct.pack_into("<H", blob, 24, 28)
    return bytes(blob) + payload


def zip_record(flags=1, method=8, descriptor=False):
    name, packed, raw, checksum = b"file.txt", b"E" * 17, 5, 0x12345678
    flags |= 8 if descriptor else 0
    fields = (0, 0, 0) if descriptor else (checksum, len(packed), raw)
    local = struct.pack("<4s5H3I2H", b"PK\3\4", 20, flags, method, 0, 0,
                        *fields, len(name), 0) + name + packed
    if descriptor:
        local += b"PK\7\10" + struct.pack("<3I", checksum, len(packed), raw)
    central = struct.pack("<4s6H3I5H2I", b"PK\1\2", 20, 20, flags, method, 0, 0,
                          checksum, len(packed), raw, len(name), 0, 0, 0, 0, 0, 0) + name
    return local + central + struct.pack("<4s4H2IH", b"PK\5\6", 0, 0, 1, 1,
                                         len(central), len(local), 0)


def ace_header(body):
    return struct.pack("<HH", (zlib.crc32(body) ^ 0xffffffff) & 0xffff, len(body)) + body


def ace(packed=8, actual=8, encrypted=True, split=False):
    main = bytearray(27)
    struct.pack_into("<BH", main, 0, 0, 0x800 if split else 0)
    main[3:10] = b"**ACE**"
    main[10:12] = b"\x14\x14"
    name = b"file.txt"
    file = bytearray(31 + len(name))
    struct.pack_into("<BHII", file, 0, 1, 1 | (0x4000 if encrypted else 0), packed, 5)
    file[23] = 1
    struct.pack_into("<H", file, 29, len(name))
    file[31:] = name
    return ace_header(main) + ace_header(file) + b"P" * actual


def rar_header(header):
    struct.pack_into("<H", header, 0, zlib.crc32(header[2:]) & 0xffff)
    return bytes(header)


def rar(packed=40, actual=5, split=False):
    main = bytearray(13)
    struct.pack_into("<BHH", main, 2, 0x73, 0, len(main))
    name = b"file.txt"
    file = bytearray(32 + len(name))
    struct.pack_into("<BHHII", file, 2, 0x74, 0x8000 | (1 if split else 0),
                     len(file), packed, 50)
    file[24:26] = b"\x14\x30"
    struct.pack_into("<H", file, 26, len(name))
    file[32:] = name
    return b"Rar!\x1a\x07\0" + rar_header(main) + rar_header(file) + b"P" * actual


def arj_header(main, packed=0, volume=False):
    h = bytearray(30)
    h[:7] = bytes((30, 3, 1, 0, 4 if volume else 0, 0, 2 if main else 0))
    struct.pack_into("<I", h, 12, packed)
    h.extend(b"archive\0\0" if main else b"file.txt\0\0")
    return b"\x60\xea" + struct.pack("<H", len(h)) + h + struct.pack("<I", zlib.crc32(h)) + b"\0\0"


def arc_header(name, packed):
    h = bytearray(29)
    h[:2] = b"\x1a\2"
    h[2:2 + len(name)] = name
    struct.pack_into("<I", h, 15, packed)
    struct.pack_into("<I", h, 25, packed)
    return bytes(h)


def lha(level=0, packed=40, actual=5, checksum=True, ext=True, method=b"-lh0-"):
    name = b"file.txt"
    h = bytearray(24 + len(name) if level == 0 else 27 + len(name) if level == 1 else 26)
    h[2:7] = method
    struct.pack_into("<II", h, 7, packed, packed)
    h[19:21] = bytes((0x20, level))
    if level <= 1:
        h[0] = len(h) - 2
        h[21] = len(name)
        h[22:22 + len(name)] = name
        if level == 1:
            h[24 + len(name)] = ord("M")
            if ext:
                extra = b"\1other.txt\0\0"
                struct.pack_into("<H", h, len(h) - 2, len(extra))
                struct.pack_into("<I", h, 7, packed + len(extra))
            else:
                extra = b""
        else:
            extra = b""
        h[1] = (sum(h[2:]) + (0 if checksum else 1)) & 255
        h += extra
    else:
        # Common extension contributes its CRC; the filename follows it.
        common = b"\0\0\0" + struct.pack("<H", len(name) + 3)
        filename = b"\1" + name + b"\0\0"
        h[23] = ord("M")
        struct.pack_into("<H", h, 24, len(common))
        h += common + filename
        struct.pack_into("<H", h, 0, len(h))
        struct.pack_into("<H", h, 27, crc16(h) ^ (0 if checksum else 1))
    return bytes(h) + b"P" * actual


def main():
    cases = []
    cases.extend((
        ("zipcrypto", zip_record(), "password"),
        ("zipcrypto-dd", pe(zip_record(descriptor=True)), "password"),
        ("zip-not-encrypted", zip_record(flags=0), None),
        ("zip-strong-opaque", zip_record(flags=0x41), None),
        ("zip-aes-opaque", zip_record(method=99), None),
        ("zip-missing-central", zip_record()[:60], None),
        ("ace-password", ace(), "password"),
        ("ace-unencrypted", ace(encrypted=False), None),
        ("ace-split", ace(split=True), None),
        ("ace-packed-truncated", pe(ace(packed=40)), "corrupted"),
        ("pe-section-truncated", pe(raw_size=4096), "corrupted"),
        ("pe-complete", pe(), None),
        ("rar-packed-truncated", pe(rar()), "corrupted"),
        ("rar-split", rar(split=True), None),
        ("rar-complete", rar(packed=5), None),
        ("arj-packed-truncated", arj_header(True) + arj_header(False, packed=40) + b"P" * 5, "corrupted"),
        ("arj-volume", arj_header(True, volume=True) + arj_header(False, packed=40) + b"P" * 5, None),
        ("arc-second-truncated", dos(arc_header(b"first", 1) + b"P" + arc_header(b"second", 40) + b"P"), "corrupted"),
        ("arc-first-unconfirmed", arc_header(b"first", 40) + b"P", None),
        ("pe-truncated.001", pe(raw_size=4096), None),
        ("lha-truncated.~~1", dos(lha()), None),
        ("lha-truncated.EX1", dos(lha()), None),
        ("lha-truncated.-01", dos(lha()), None),
        ("lha-truncated1.BIN", dos(lha()), None),
        ("zip-complete.001", zip_record(), "password"),
        ("arbitrary-signatures", b"X" * 512 + b"Rar!\x1a\x07\0**ACE**\x60\xea-lh5-", None),
    ))
    for level in range(3):
        cases.extend((
            (f"lha{level}-complete", dos(lha(level=level, packed=5)), None),
            (f"lha{level}-truncated", dos(lha(level=level)), None),
            (f"lha{level}-bad-header-check", dos(lha(level=level, packed=5, checksum=False)), "corrupted"),
            (f"lha{level}-scanned-bad-header", dos(b"padding" + lha(level=level, packed=5, checksum=False)), None),
            (f"lha{level}-scanned-first-overrun", dos(b"padding" + lha(level=level)), None),
            (f"lha{level}-scanned-chain-overrun", dos(b"padding" + lha(level=level, packed=5) + lha(level=level)), None),
            (f"lha{level}-unknown-method", dos(lha(level=level, method=b"-xx9-")), None),
        ))
    corrupt = bytearray(ace()); corrupt[0] ^= 1
    cases.append(("ace-invalid-crc", bytes(corrupt), None))
    corrupt = bytearray(rar()); corrupt[20] ^= 1
    cases.append(("rar-invalid-main-crc", bytes(corrupt), None))
    corrupt = bytearray(arj_header(True) + arj_header(False, packed=40)); corrupt[8] ^= 1
    cases.append(("arj-invalid-main-crc", bytes(corrupt), None))
    corrupt = bytearray(zip_record()); struct.pack_into("<H", corrupt, 6, 0)
    cases.append(("zip-local-central-disagreement", bytes(corrupt), None))
    outer = bytearray(pe()); markers = b"INFTool.pkgINFTool.Tmp!"
    outer[600:600 + len(markers)] = markers
    cases.append(("inftool-two-images", bytes(outer) + pe() + b"payload", "new file format"))
    with tempfile.TemporaryDirectory(prefix="arc-evidence-sfx-") as directory:
        for name, blob, expected in cases:
            path = Path(directory) / name
            path.write_bytes(blob)
            result = evidence.classify(path, None, {"status": "failed"})
            assert result["category"] == expected, (name, expected, result)
        path = Path(directory) / "pe-section-truncated"
        assert evidence.classify(path, None, {"status": "passed"})["category"] is None
        path = Path(directory) / "inftool-two-images"
        assert evidence.classify(path, {"parsed": True}, {"status": "failed"})["category"] is None
    print(f"PASS {len(cases) + 2} independent SFX scan evidence fixtures")


if __name__ == "__main__":
    main()
