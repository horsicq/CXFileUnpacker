"""Metadata JSON, encrypted ZIP flags, and audited no-output verification."""
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import zipfile
import zlib


def probe(executable, source, *options):
    result = subprocess.run([executable, str(source), *options],
                            capture_output=True, timeout=30)
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    report = json.loads(result.stdout.decode("utf-8"))
    assert report["schema_version"] == 1
    assert report["path"] == str(source)
    return report


def encrypted_zip():
    # A complete ZipCrypto-framed stored member with its encryption flag set.
    # Listing does not need a password; the probe must skip verification.
    name, data = b"secret.txt", b"AB"
    payload = b"\0" * 12 + data
    crc = zlib.crc32(data)
    local = struct.pack("<IHHHHHIIIHH", 0x04034b50, 20, 1, 0, 0, 0,
                        crc, len(payload), len(data), len(name), 0) + name + payload
    central = struct.pack("<IHHHHHHIIIHHHHHII", 0x02014b50, 20, 20, 1, 0,
                          0, 0, crc, len(payload), len(data), len(name),
                          0, 0, 0, 0, 0, 0) + name
    return local + central + struct.pack("<IHHHHIIH", 0x06054b50, 0, 0,
                                        1, 1, len(central), len(local), 0)


def leb(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes((value,)))


def compressed_ivt(broken=False):
    # One independently encoded MSZIP block and a one-page IVT directory.
    plain = b"IVT" * 100
    compressor = zlib.compressobj(wbits=-15)
    raw_deflate = compressor.compress(plain) + compressor.flush()
    block = (struct.pack("<HH", len(plain), len(raw_deflate) + 2) +
             (b"QK" if broken else b"CK") + raw_deflate)
    member = b"mszp" + struct.pack("<II", len(plain), 0) + block
    name = b"content.txt"
    entry = bytes((len(name),)) + name + leb(8) + leb(len(member)) + b"\0"
    page = (struct.pack("<HHII", 8192 - 12 - len(entry), 1,
                        0xffffffff, 0xffffffff) + entry).ljust(8192, b"\0")
    directory = bytearray(48)
    struct.pack_into("<HHH", directory, 0, 0x293b, 0x102, 8192)
    struct.pack_into("<III", directory, 26, 0, 0, 0xffffffff)
    struct.pack_into("<IHI", directory, 38, 1, 1, 1)
    assert len(member) + 8 <= 64
    return (struct.pack("<II", 0x01045f3f, 64) + member).ljust(64, b"\0") + directory + page


def crc16(data):
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xa001 if value & 1 else 0)
    return value


def lha(method=b"-lh0-", payload=None, bad_crc=False):
    plain, name = b"A" * 12, b"plain.bin"
    if payload is None:
        payload = plain
    header = bytearray(24 + len(name))
    header[0] = len(header) - 2
    header[2:7] = method
    struct.pack_into("<II", header, 7, len(payload), len(plain))
    header[19:22] = bytes((0x20, 0, len(name)))
    header[22:22 + len(name)] = name
    struct.pack_into("<H", header, 22 + len(name), crc16(plain) ^ int(bad_crc))
    header[1] = sum(header[2:]) & 255
    return bytes(header) + payload + b"\0"


def lha_constant_block():
    # A block of 12 literal 'A's with constant pre/literal/position trees.
    fields = ((12, 16), (0, 5), (0, 5), (0, 9), (65, 9), (0, 4), (0, 4))
    bits = "".join(f"{value:0{width}b}" for value, width in fields)
    bits += "0" * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, "big")


def silmarils():
    # An exact eight-byte byte-run resource, little-endian scalar header.
    return struct.pack("<IH", 0x8100000e, 1) + b"\x08ABCDEFGH"


def gst(bad_crc=False):
    plain = b"GST member\n"
    header = bytearray(32)
    header[:2] = b"\xe9\xc8"
    struct.pack_into("<II", header, 8, len(plain), len(plain))
    header[16:25] = b"plain.bin"
    struct.pack_into("<I", header, 28, zlib.crc32(plain) ^ int(bad_crc))
    return bytes(header) + plain


def main():
    executable = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory(prefix="xfu-metadata-") as temporary:
        root = Path(temporary)
        source = root / "样本.zip"
        with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("a.txt", b"A" * 5)
            archive.writestr("sub/", b"")
            archive.writestr("中.txt", b"B" * 7)
        before = {p.name for p in root.iterdir()}
        report = probe(executable, source)
        assert report["status"] == "ok" and report["is_archive"]
        assert report["member_count"] == report["declared_member_count"] == 3
        assert report["directory_count"] == 1
        assert report["declared_unpacked_bytes"] == 12
        assert report["max_unpacked_member"] == 7
        assert report["names_sample"] == ["a.txt", "sub/", "中.txt"]
        assert report["any_encrypted_members"] is False
        assert report["verification_attempted"] is False
        report = probe(executable, source, "--verify")
        assert report["verification_passed"] is True
        assert report["verified_members"] == 3 and report["failed_members"] == 0
        assert {p.name for p in root.iterdir()} == before
        report = probe(executable, source, "--verify", "--record-limit", "1")
        assert report["status"] == "record_limit" and report["member_count"] == 1
        assert report["member_iteration_complete"] is False
        assert report["verification_passed"] is None
        report = probe(executable, source, "--verify", "--max-member-size", "1")
        assert report["status"] == "verification_limited"
        assert report["verification_limited_members"] == 2
        assert report["failed_members"] == 0 and report["verification_passed"] is None
        damaged = bytearray(source.read_bytes())
        damaged[30 + len(b"a.txt")] ^= 1
        source.write_bytes(damaged)
        report = probe(executable, source, "--verify")
        assert report["status"] == "verification_failed"
        assert report["verification_passed"] is False and report["failed_members"] == 1
        assert report["first_error_code"] != 0 and report["first_error_text"]

        source = root / "encrypted.zip"
        source.write_bytes(encrypted_zip())
        report = probe(executable, source, "--verify")
        assert report["any_encrypted_members"] is True
        assert report["encrypted_member_count"] == 1
        assert report["verification_skipped_encrypted_members"] == 1
        assert report["verification_attempted"] is False
        assert report["verification_passed"] is None and report["failed_members"] == 0

        source = root / "compressed.ivt"
        source.write_bytes(compressed_ivt())
        report = probe(executable, source, "--verify")
        assert report["selected_type_name"].lower() == "ivt"
        assert report["verification_passed"] is True
        assert report["declared_unpacked_bytes"] == 300
        report = probe(executable, source, "--verify", "--memory-limit", "100")
        assert report["status"] == "verification_limited" and report["failed_members"] == 0
        source.write_bytes(compressed_ivt(broken=True))
        report = probe(executable, source)
        assert report["status"] == "ok" and report["parsed"] is True
        report = probe(executable, source, "--verify")
        assert report["verification_passed"] is False and report["failed_members"] == 1

        source = root / "stored.lha"
        source.write_bytes(lha())
        report = probe(executable, source, "--verify")
        assert report["reader"] == "lha" and report["verification_passed"] is True
        assert report["verification_integrity"] == "decode_size_only_crc_unverified"
        assert report["verification_limitations"]
        report = probe(executable, source, "--verify", "--memory-limit", "20")
        assert report["status"] == "verification_limited" and report["failed_members"] == 0
        source.write_bytes(lha(bad_crc=True))
        report = probe(executable, source, "--verify")
        # Explicitly capture the current native reader's integrity limit;
        # this pass must retain the CRC-unverified contract in the report.
        assert report["verification_passed"] is True
        assert report["verification_integrity"] == "decode_size_only_crc_unverified"
        source.write_bytes(lha(b"-lh5-", lha_constant_block()))
        report = probe(executable, source, "--verify")
        assert report["verification_passed"] is True
        source.write_bytes(lha(b"-lh5-", b"\0" * 7))
        report = probe(executable, source, "--verify", "--reader", "lha")
        assert report["parsed"] is True and report["verification_passed"] is False
        source.write_bytes(lha(b"-lh9-"))
        report = probe(executable, source, "--verify", "--reader", "lha")
        assert report["parsed"] is True and report["verification_passed"] is False

        source = root / "resource.io"
        source.write_bytes(silmarils())
        report = probe(executable, source, "--verify", "--reader", "silmarilsft")
        assert report["verification_passed"] is True
        assert report["verification_integrity"] == "decode_size_token_framing_no_format_checksum"
        assert report["known_unpacked_bytes"] == 8
        report = probe(executable, source, "--verify", "--reader", "silmarilsft", "--memory-limit", "1")
        assert report["status"] == "verification_limited" and report["failed_members"] == 0
        source.write_bytes(silmarils()[:-1])
        report = probe(executable, source, "--verify", "--reader", "silmarilsft")
        assert report["verification_passed"] is not True

        source = root / "stored.gst"
        source.write_bytes(gst())
        report = probe(executable, source, "--verify", "--reader", "gst")
        assert report["verification_passed"] is True
        assert report["verification_integrity"] == "decode_size_crc32"
        source.write_bytes(gst(bad_crc=True))
        report = probe(executable, source, "--verify", "--reader", "gst")
        assert report["parsed"] is True and report["verification_passed"] is False

        source = root / "unsupported_verify.tar"
        with tarfile.open(source, "w") as archive:
            entry = tarfile.TarInfo("plain.txt")
            entry.size = 5
            archive.addfile(entry, io.BytesIO(b"plain"))
        report = probe(executable, source, "--verify")
        assert report["parsed"] and report["member_count"] == 1
        assert report["verification_supported"] is False
        assert report["verification_attempted"] is False
        assert report["verification_passed"] is None

        source = root / "opaque.bin"
        source.write_bytes(b"opaque corpus metadata test\0")
        report = probe(executable, source)
        assert report["status"] == "unrecognized"
        assert report["parsed"] is None and report["any_encrypted_members"] is None
        report = probe(executable, root / "missing.bin")
        assert report["status"] == "open_failed" and report["parsed"] is None
    print("Metadata JSON, limits, encryption flags, and audited no-output verification passed")


if __name__ == "__main__":
    main()
