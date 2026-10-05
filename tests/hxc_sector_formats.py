#!/usr/bin/env python3
"""Independent HxC-sector/container fixture writers and byte comparisons.

Run with the hxc_sector_lifecycle executable. This uses direct named readers,
including explicit headerless profiles; it never executes image contents.
Expected bytes are defined before encoding, not produced by xxfclib.
"""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile


def pattern(length, seed=0):
    block = bytes((seed + i * 7) & 255 for i in range(256))
    return (block * ((length + 255) // 256))[:length]


def mutate(data, offset, value):
    result = bytearray(data)
    result[offset:offset + len(value)] = value
    return bytes(result)


def gkh():
    image, author, subject = pattern(2 * 2 * 3 * 256), b"fixture author", b"independent subject"
    tags = [bytes((21, 10)) + struct.pack("<II", len(subject), 58 + len(image) + len(author)),
            bytes((10, 5)) + struct.pack("<4H", 2, 2, 3, 256),
            bytes((1, 4)) + struct.pack("<II", 1, 1),
            bytes((20, 10)) + struct.pack("<II", len(author), 58 + len(image)),
            bytes((11, 11)) + struct.pack("<II", len(image), 58)]
    return b"TDDFI\1" + struct.pack("<H", len(tags)) + b"".join(tags) + image + author + subject, [image, author, subject]


def side_image(cylinders, heads, sectors, size):
    tracks = [[pattern(sectors * size, c * 13 + h * 53) for c in range(cylinders)] for h in range(heads)]
    return b"".join(t for head in tracks for t in head), b"".join(tracks[h][c] for c in range(cylinders) for h in range(heads))


def sad(heads=2):
    source, image = side_image(3, heads, 5, 256)
    return b"Aley's disk backup" + bytes((heads, 3, 5, 4)) + source, [image]


def sdd(heads=2, fm=0):
    source, _ = side_image(3, heads, 5, 256)
    source = bytearray(source)
    source[:5] = b"TRKY2"
    source[13:16] = bytes((fm, 3 | (128 if heads == 2 else 0), 5))
    tracks = [source[i:i + 1280] for i in range(0, len(source), 1280)]
    image = b"".join(tracks[h * 3 + c] for c in range(3) for h in range(heads))
    return bytes(source), [image]


def ede(code, sparse=True):
    heads = 1 if code == 1 else 2
    sectors = 6 if code in (1, 2) else 20 if code in (203, 204) else 10
    stride = 1024 if code in (1, 2) else 512
    bitmap = 96 if sectors == 20 else 160
    header = bytearray(512)
    header[:2] = header[78:80] = b"\r\n"
    header[bitmap - 3:bitmap] = b"\r\n\x1a"
    header[511] = code
    stored, tracks = [], []
    for c in range(80):
        for h in range(heads):
            pieces = []
            for sector in range(sectors):
                ordinal = (c * heads + h) * sectors + sector
                filled = not sparse or ordinal % 19 != 0
                part = (b"\x6d\xb6" * (stride // 2)) if filled else pattern(stride, ordinal)
                if filled:
                    header[bitmap + ordinal // 8] |= 0x80 >> (ordinal % 8)
                else:
                    stored.append(part)
                pieces.append(part)
            # Mixed tracks have sector ID5 first in the transport, then0..4.
            tracks.append(b"".join(pieces[1:]) + pieces[0][:512] if stride == 1024 else b"".join(pieces))
    return bytes(header) + b"".join(stored), [b"".join(tracks)]


def nib(tracks=35, rotated=False):
    encoding = bytes.fromhex("96979a9b9d9e9fa6a7abacadaeafb2b3b4b5b6b7b9babbbcbdbebfcbcdcecfd3d6d7d9dadbdcdddedfe5e6e7e9eaebecedeeeff2f3f4f5f6f7f9fafbfcfdfeff")
    outputs = []
    def four(value):
        return bytes(((value >> 1) | 0xAA, value | 0xAA))
    for c in range(tracks):
        header = b"\xd5\xaa\x96" + b"".join(four(n) for n in (254, c, 7, 254 ^ c ^ 7)) + b"\xde\xaa\xeb"
        previous, encoded = 0, bytearray()
        for j in range(342):
            six = (j * 13 + c) % 64
            encoded.append(encoding[previous ^ six])
            previous = six
        encoded.append(encoding[previous])
        track = (header + b"\xff" * 20 + b"\xd5\xaa\xad" + encoded + b"\xde\xaa\xeb").ljust(6656, b"\xff")
        if rotated:
            track = track[10:] + track[:10]
        outputs.append(track)
    return b"".join(outputs), outputs


def pc99(fm=True, heads=1, placeholder=False):
    length, sectors = (3253, 9) if fm else (6872, 18)
    tracks = []
    def crc(data):
        return b"\xf7\xf7" if placeholder else struct.pack(">H", binascii.crc_hqx(data, 0xFFFF))
    for h in range(heads):
        for c in range(40):
            pieces = [b"\xff" * 25]
            for sector in range(sectors):
                prefix = b"" if fm else b"\xa1" * 3
                header = prefix + bytes((254, c, h, sector, 1))
                data = prefix + b"\xfb" + pattern(256, c + h + sector)
                pieces.extend((header, crc(header), b"\x4e" * 12, data, crc(data), b"\x4e" * 22))
            track = b"".join(pieces)
            assert len(track) <= length
            tracks.append(track.ljust(length, b"\xff"))
    return b"".join(tracks), tracks


def vtr(heads=2, gap=False):
    header, table = bytearray(512), bytearray(512)
    header[:7] = b"VTrucco"
    header[7] = 1
    header[10] = 3
    header[12] = heads
    struct.pack_into("<HH", header, 14, 250, 1)
    reverse = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))
    source, expected = header + table, []
    for c in range(3):
        if gap:
            source += b"unused".ljust(512, b"\0")
        sides = [pattern(777 + c * 15, c * 31 + h * 21) for h in range(2)]
        struct.pack_into("<HH", source, 512 + c * 4, len(source) // 512, 2 * len(sides[0]))
        for at in range(0, len(sides[0]), 256):
            for h in range(2):
                source += sides[h][at:at + 256].translate(reverse).ljust(256, b"\xff")
        expected.extend(sides[:heads])
    return bytes(source), expected


def fzf():
    header = bytearray(2048)
    struct.pack_into("<H", header, 0, 2)
    header[2:4], header[0x42:0x44] = bytes((60, 80)), bytes((20, 61))
    header[0x82:0x84], header[0xC2:0xC4] = b"\x7f\x7f", b"\0\0"
    struct.pack_into("<HH", header, 0x202, 0, 1)
    header[0x282:0x28e] = b"TEST BANK   "
    for voice in range(2):
        at = 1024 + voice * 256
        struct.pack_into("<IIII", header, at, voice * 512, (voice + 1) * 512, voice * 512, (voice + 1) * 512)
        header[at + 0xB2:at + 0xBE] = (f"VOICE{voice}").encode().ljust(12, b" ")
    pcm = pattern(2048, 17)
    return bytes(header) + pcm, [bytes(header[:1024]), bytes(header[1024:1280]), bytes(header[1280:1536]), pcm]


def fzf_declared(banks=2, file_type=0):
    voices = 3 if banks == 2 else 2
    header = bytearray((banks + 1) * 1024)
    for bank in range(banks):
        at = bank * 1024
        struct.pack_into("<H", header, at, 2)
        header[at + 2:at + 4], header[at + 0x42:at + 0x44] = bytes((60, 80)), bytes((20, 61))
        header[at + 0x82:at + 0x84] = b"\x7f\x7f"
        struct.pack_into("<HH", header, at + 0x202, bank, bank + 1)
        header[at + 0x282:at + 0x28e] = (f"BANK {bank}").encode().ljust(12, b" ")
    header[0x3e8 + 5:0x3e8 + 9] = bytes((file_type, 0, banks, voices))
    struct.pack_into("<H", header, 0x3e8 + 12, voices)
    for voice in range(voices):
        at = banks * 1024 + voice * 256
        struct.pack_into("<IIII", header, at, voice * 512, (voice + 1) * 512, voice * 512, (voice + 1) * 512)
        header[at + 0xb2:at + 0xc0] = (f"VOICE{voice}").encode().ljust(14, b" ")
    pcm = pattern(voices * 1024, 19)
    expected = [bytes(header[bank * 1024:(bank + 1) * 1024]) for bank in range(banks)]
    expected += [bytes(header[banks * 1024 + v * 256:banks * 1024 + (v + 1) * 256]) for v in range(voices)]
    return bytes(header) + pcm, expected + [pcm]


def original_fzf(data):
    """Independent declared-layout slicer used only for real reference data."""
    banks, voices = data[1007], data[1008]
    waves = struct.unpack_from("<H", data, 1012)[0]
    assert data[1005] in (0, 2) and data[1006] == 0 and 1 <= banks <= 8 and 1 <= voices <= 64
    audio = banks * 1024 + ((voices + 3) // 4) * 1024
    assert audio + waves * 1024 == len(data)
    for bank in range(banks):
        base = bank * 1024
        count = struct.unpack_from("<H", data, base)[0]
        assert 1 <= count <= 64
        for i in range(count):
            assert struct.unpack_from("<H", data, base + 0x202 + i * 2)[0] < voices
    expected = [data[i * 1024:(i + 1) * 1024] for i in range(banks)]
    for i in range(voices):
        at = banks * 1024 + i * 256
        start, end, genstart, genend = struct.unpack_from("<IIII", data, at)
        assert start <= genstart <= genend <= end <= waves * 512
        expected.append(data[at:at + 256])
    return expected + [data[audio:]]


def fixtures(real_fzf=None):
    data, expected = gkh()
    yield "gkh-shuffled-tags", "ensoniq_gkh", data, expected, False
    yield "gkh-bad-version", "ensoniq_gkh", mutate(data, 5, b"\2"), None, False
    yield "gkh-duplicate-tag", "ensoniq_gkh", mutate(data, 38, bytes((11, 11))), None, False
    yield "gkh-overlap", "ensoniq_gkh", mutate(data, 54, struct.pack("<I", 8)), None, False
    yield "gkh-truncation", "ensoniq_gkh", data[:-1], None, False
    yield "gkh-unknown-datatype", "ensoniq_gkh", mutate(data, 9, b"\x11"), None, False
    for heads in (1, 2):
        data, expected = sad(heads)
        yield f"sad-{heads}-head", "samcoupe_sad", data, expected, False
    yield "sad-zero-cylinders", "samcoupe_sad", mutate(data, 19, b"\0"), None, False
    yield "sad-nonpower-sector", "samcoupe_sad", mutate(data, 21, b"\3"), None, False
    yield "sad-truncation", "samcoupe_sad", data[:-1], None, False
    for code in (0, 1, 2, 3, 4, 7, 203, 204):
        data, expected = ede(code)
        yield f"ede-code-{code}", "ensoniq_ede", data, expected, False
    data, expected = ede(3, False)
    yield "ede-all-fill", "ensoniq_ede", data, expected, False
    yield "ede-wrong-marker", "ensoniq_ede", mutate(data, 159, b"\0"), None, False
    yield "ede-unknown-code", "ensoniq_ede", mutate(data, 511, b"\x99"), None, False
    yield "ede-unresolved-computer-geometry", "ensoniq_ede", mutate(data, 510, b"\1"), None, False
    data, _ = ede(1)
    yield "ede-truncated-mixed-sector", "ensoniq_ede", data[:-1], None, False
    yield "ede-unreferenced-suffix", "ensoniq_ede", data + b"\0", None, False
    header = b"emaxutil v1.1 Fri Mar 19 13:31:05 1993\n"
    bank, samples = pattern(56 * 512, 11), pattern(1024 * 512, 23)
    data = header + bank + samples
    yield "emax-two-available-extents", "emax_disk", data, [bank, samples], True
    yield "emax-bad-marker", "emax_disk", mutate(data, 0, b"X"), None, False
    yield "emax-truncation", "emax_disk", data[:-1], None, False
    tracks = [pattern(3584, i) for i in range(136)]
    data = b"".join(tracks)
    yield "eii-explicit-available-tracks", "emulatorii_eii", data, tracks, True
    yield "eii-truncation", "emulatorii_eii", data[:-1], None, False
    for rotated in (False, True):
        data, expected = nib(rotated=rotated)
        yield f"nib-circular-{rotated}", "apple_nib", data, expected, False
    data, _ = nib()
    yield "nib-low-bit", "apple_nib", mutate(data, 600, b"\x7f"), None, False
    yield "nib-address-checksum", "apple_nib", mutate(data, 9, b"\xaa\xaa"), None, False
    yield "nib-data-checksum", "apple_nib", mutate(data, 14 + 20 + 3 + 342, b"\x96"), None, False
    yield "nib-truncation", "apple_nib", data[:-1], None, False
    for fm, heads, placeholder in ((True, 1, False), (True, 2, True), (False, 1, False), (False, 2, True)):
        data, expected = pc99(fm, heads, placeholder)
        yield f"pc99-fm{fm}-heads{heads}-placeholder{placeholder}", "ti99_pc99", data, expected, False
    data, _ = pc99()
    yield "pc99-header-crc", "ti99_pc99", mutate(data, 30, b"\0\0"), None, False
    yield "pc99-data-crc", "ti99_pc99", mutate(data, 301, b"\0\0"), None, False
    yield "pc99-missing-sector", "ti99_pc99", mutate(data, 25, b"\xff"), None, False
    yield "pc99-truncation", "ti99_pc99", data[:-1], None, False
    for heads, gap in ((1, False), (2, True)):
        data, expected = vtr(heads, gap)
        yield f"vtr-heads-{heads}-gap-{gap}", "vtr_disk", data, expected, False
    yield "vtr-revision", "vtr_disk", mutate(data, 18, b"\1"), None, False
    yield "vtr-overlap", "vtr_disk", mutate(data, 516, data[512:514]), None, False
    yield "vtr-table-alias", "vtr_disk", mutate(data, 512, b"\1\0"), None, False
    yield "vtr-odd-length", "vtr_disk", mutate(data, 514, b"\x13\x06"), None, False
    yield "vtr-truncation", "vtr_disk", data[:-1], None, False
    for heads, fm in ((1, 0), (2, 0), (2, 1)):
        data, expected = sdd(heads, fm)
        yield f"sdd-heads-{heads}-fm-{fm}", "speccydos_sdd", data, expected, False
    yield "sdd-unknown-flags", "speccydos_sdd", mutate(data, 13, b"\2"), None, False
    yield "sdd-truncation", "speccydos_sdd", data[:-1], None, False
    yield "sdd-zero-geometry", "speccydos_sdd", mutate(data, 14, b"\x80"), None, False
    data, expected = fzf()
    yield "fzf-one-bank", "casio_fzf", data, expected, False
    yield "fzf-voice-index-oob", "casio_fzf", mutate(data, 0x202, b"\x40\0"), None, False
    yield "fzf-wave-pointer-oob", "casio_fzf", mutate(data, 1028, struct.pack("<I", 100000)), None, False
    yield "fzf-truncation", "casio_fzf", data[:-1], None, False
    yield "fzf-extra-unproven-block", "casio_fzf", data + bytes(1024), None, False
    data, expected = fzf_declared()
    yield "fzf-declared-two-banks", "casio_fzf", data, expected, False
    yield "fzf-declared-wrong-bank-count", "casio_fzf", mutate(data, 1007, b"\3"), None, False
    yield "fzf-declared-voice-index-oob", "casio_fzf", mutate(data, 1024 + 0x202, b"\3\0"), None, False
    yield "fzf-declared-unknown-kind", "casio_fzf", mutate(data, 1005, b"\4"), None, False
    yield "fzf-declared-continuation", "casio_fzf", mutate(data, 1006, b"\1"), None, False
    yield "fzf-declared-extra-wave-block", "casio_fzf", data + bytes(1024), None, False
    data, expected = fzf_declared(1, 2)
    yield "fzf-declared-bank-dump", "casio_fzf", data, expected, False
    if real_fzf:
        data = real_fzf.read_bytes()
        yield "fzf-real-primary-control", "casio_fzf", data, original_fzf(data), False
    for cylinders in (40, 80):
        source, old = side_image(cylinders, 2, 16, 256)
        yield f"thomson-default-{cylinders}", "thomson_fd", source, [old], False
        yield f"thomson-hxc-{cylinders}", "thomson_fd_hxc", source, [source if cylinders == 40 else old], False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("helper", type=Path, nargs="?")
    parser.add_argument("--helper", dest="helper_option", type=Path)
    parser.add_argument("--emit", type=Path, help="retain independent fixture inputs/expected SHA manifest")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--real-fzf", type=Path, help="optional primary reference dump, independently sliced")
    args = parser.parse_args()
    args.helper = args.helper_option or args.helper
    if not args.helper and not args.emit:
        parser.error("supply the lifecycle helper or --emit")
    rows = []
    with tempfile.TemporaryDirectory(prefix="xfu-hxc-sector-") as temporary:
        folder = args.emit or Path(temporary)
        folder.mkdir(parents=True, exist_ok=True)
        for label, reader, data, expected, partial in fixtures(args.real_fzf):
            source, output = folder / (label + ".bin"), folder / (label + "-output")
            source.write_bytes(data)
            row = {"case": label, "reader": reader, "valid": expected is not None, "incomplete": partial,
                   "source_sha256": hashlib.sha256(data).hexdigest(), "source_size": len(data),
                   "output_sha256": [] if expected is None else [hashlib.sha256(x).hexdigest() for x in expected]}
            if args.helper:
                process = subprocess.run([str(args.helper.resolve()), reader, str(source), str(output)],
                                         capture_output=True, timeout=45)
                files = sorted(p for p in output.rglob("*") if p.is_file()) if output.exists() else []
                actual = [p.read_bytes() for p in files]
                if expected is None:
                    assert process.returncode == 2 and not files, (label, process.returncode, process.stdout, process.stderr)
                else:
                    assert process.returncode == 0 and actual == expected, (label, process.returncode, process.stdout, process.stderr,
                        [len(x) for x in actual], [len(x) for x in expected])
                    assert f"incomplete={int(partial)}".encode() in process.stdout, (label, process.stdout)
                assert hashlib.sha256(source.read_bytes()).hexdigest() == row["source_sha256"], label
                row["passed"] = True
            rows.append(row)
        if args.emit:
            (folder / "fixtures.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    if args.report:
        args.report.write_text(json.dumps({"cases": len(rows), "results": rows}, indent=2) + "\n", encoding="utf-8")
    print(f"HxC sector formats: {len(rows)} independent cases {'passed' if args.helper else 'generated'}")


if __name__ == "__main__":
    main()
