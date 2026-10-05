"""Independent Amiga/IBM MFM fixtures and optional real HFE byte comparison.

The writer follows FlashFloppy's published AmigaDOS on-disk layout and creates
regular MFM clock cells, not reader-produced data. Expected sector contents
are generated independently before they are encoded.
"""
import argparse
import functools
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

MASK = 0x55555555
SYNC = "01000100100010010100010010001001"
REVERSE = bytes(int(f"{value:08b}"[::-1], 2) for value in range(256))


def payload(track, sector):
    return bytes((track * 37 + sector * 11 + index * 7) & 255 for index in range(512))


def mfm_word(value, previous):
    data = value & MASK
    encoded = data | ((~((data >> 2) | data) & MASK) << 1)
    encoded &= ~(previous << 31)
    return f"{encoded:032b}", encoded & 1


def sector(track, number, remaining, *, bad_header=False, bad_data=False, wrong_track=False,
           wrong_id=False, different_payload=False, label=False):
    content = payload(track, number)
    if different_payload:
        content = bytes((content[0] ^ 1,)) + content[1:]
    info = (255 << 24) | ((track + int(wrong_track)) << 16) | ((number + 23 * int(wrong_id)) << 8) | remaining
    label_words = (0x12345678, 0xabcdef01, 0x76543210, 0x10203040) if label else (0,) * 4
    header = [(info >> 1) & MASK, info & MASK]
    header += [(value >> 1) & MASK for value in label_words] + [value & MASK for value in label_words]
    checksum = functools.reduce(int.__xor__, header)
    data_words = struct.unpack(">128I", content)
    encoded_data = [(value >> 1) & MASK for value in data_words] + [value & MASK for value in data_words]
    data_checksum = functools.reduce(int.__xor__, encoded_data)
    if bad_header:
        checksum ^= 1
    if bad_data:
        data_checksum ^= 1
    words = header + [(checksum >> 1) & MASK, checksum & MASK,
                      (data_checksum >> 1) & MASK, data_checksum & MASK] + encoded_data
    gap, _ = mfm_word(0, 0)
    output, previous = gap + SYNC, 1
    for value in words:
        encoded, previous = mfm_word(value, previous)
        output += encoded
    assert len(output) == 8704
    return output


def amiga_track(track, count=11, *, rotate=0, order=None, mutation=None, duplicate=False,
                conflicting_duplicate=False, missing=False, label=False):
    order = list(range(count)) if order is None else list(order)
    if missing:
        order.pop()
    bits = ""
    for index, number in enumerate(order):
        options = {mutation: True} if mutation and number == 0 else {}
        bits += sector(track, number, count - index, label=label, **options)
    if duplicate or conflicting_duplicate:
        bits += sector(track, 0, count, different_payload=conflicting_duplicate)
    rotate %= len(bits)
    bits = bits[rotate:] + bits[:rotate]
    assert len(bits) % 8 == 0
    return bytes(int(bits[index:index + 8], 2) for index in range(0, len(bits), 8)).translate(REVERSE)


def hfe(raw_tracks, *, encoding=1):
    assert len(raw_tracks) > 0
    header, table = bytearray(512), bytearray(512)
    header[:8] = b"HXCPICFE"
    header[9:12] = bytes((len(raw_tracks), 2, encoding))
    struct.pack_into("<H", header, 12, 250)
    struct.pack_into("<H", header, 18, 1)
    header[22:26] = b"\xff" * 4
    output = header + table
    for cylinder, sides in enumerate(raw_tracks):
        length = max(map(len, sides))
        assert length * 2 < 65536
        start = len(output) // 512
        struct.pack_into("<HH", output, 512 + cylinder * 4, start, length * 2)
        for index in range(0, length, 256):
            output += sides[0][index:index + 256].ljust(256, b"\0")
            output += sides[1][index:index + 256].ljust(256, b"\0")
    return bytes(output)


def fixture(cylinders=1, count=11, **options):
    if options.get("order") is not None:
        options["order"] = list(options["order"])
    tracks = [(amiga_track(cylinder * 2, count, **options),
               amiga_track(cylinder * 2 + 1, count, **options))
              for cylinder in range(cylinders)]
    plain = b"".join(payload(track, number) for track in range(cylinders * 2) for number in range(count))
    return hfe(tracks), plain


def false_sync_tracks(cylinders=128):
    # Every16cells look like the first half of an Amiga sync, followed by a
    # non0xff info tag. Maximal bounded tracks stress rejection cost, rather
    # than only exercising one short false candidate. The complete128-cylinder
    # container is about8MiB and has no supported sectors.
    raw = (b"\x44\x89" * 16383).translate(REVERSE)
    return hfe([(raw, raw)] * cylinders)


def crc16(data):
    value = 0xffff
    for byte in data:
        value ^= byte << 8
        for _ in range(8):
            value = ((value << 1) ^ (0x1021 if value & 0x8000 else 0)) & 0xffff
    return value


def ibm_track(side):
    body = bytes((index + side) & 255 for index in range(512))
    ident = bytes((0, side, 1, 2))
    fields = [(0xfe, ident), (0xfb, body)]
    bits, previous = "", 0
    for mark, data in fields:
        bits += f"{0x4489:016b}" * 3
        previous = 1
        framed = bytes((mark,)) + data + struct.pack(">H", crc16(b"\xa1\xa1\xa1" + bytes((mark,)) + data))
        for byte in framed:
            # One encoded 16-bit byte; keep the clock history across bytes.
            value = 0
            for bit in range(7, -1, -1):
                current = (byte >> bit) & 1
                value = (value << 2) | ((not (previous or current)) << 1) | current
                previous = current
            bits += f"{value:016b}"
        bits += f"{0xaaaa:016b}" * 8
    return bytes(int(bits[index:index + 8], 2) for index in range(0, len(bits), 8)).translate(REVERSE), body


def run(executable, folder, name, data, expected=None, *, partial=False, probe=None):
    source, output = folder / (name + ".hfe"), folder / (name + "-output")
    source.write_bytes(data)
    process = subprocess.run([str(executable), "x", str(source), "-o" + str(output)],
                             capture_output=True, timeout=30, cwd=folder)
    diagnostic = (process.stdout + process.stderr).decode("utf-8", "replace")
    files = {str(path.relative_to(output)).replace("\\", "/"): path.read_bytes()
             for path in output.rglob("*") if path.is_file()} if output.exists() else {}
    if expected is None:
        assert process.returncode != 0 and not files, (name, "invalid input accepted", diagnostic, files.keys())
    else:
        member = "image.partial.adf" if partial else "image.adf"
        assert process.returncode == int(partial), (name, process.returncode, diagnostic)
        assert files == {member: expected}, (name, files.keys(), diagnostic)
        assert ("incomplete archive" in diagnostic) == partial, (name, diagnostic)
    if probe:
        checked = subprocess.run([str(probe), str(source), "hfe"], capture_output=True, timeout=30)
        text = checked.stdout.decode("utf-8", "replace")
        assert ("valid=1 parsed=1" in text) == (expected is not None), (name, text)
        if expected is not None:
            assert "incomplete=" + str(int(partial)) in text, (name, text)
    print(name + ": passed")
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--sector-manifest", type=Path)
    parser.add_argument("--cancellation-probe", type=Path)
    args = parser.parse_args()
    executable = args.executable.resolve()
    probe = args.probe.resolve() if args.probe else None
    with tempfile.TemporaryDirectory(prefix="xfu-hfe-amiga-") as temporary:
        folder = Path(temporary)
        def check(name, data, expected=None, partial=False):
            return run(executable, folder, name, data, expected, partial=partial, probe=probe)
        for count in (11, 22):
            data, plain = fixture(2, count, rotate=47, order=reversed(range(count)), label=True)
            check("amiga-dd" if count == 11 else "amiga-hd", data, plain)
        data, plain = fixture(duplicate=True)
        check("amiga-identical-duplicate", data, plain)
        for mutation in ("bad_header", "bad_data", "wrong_track", "wrong_id"):
            data, _ = fixture(mutation=mutation)
            check("amiga-" + mutation, data)
        data, _ = fixture(missing=True)
        check("amiga-missing-sector", data)
        data, _ = fixture(conflicting_duplicate=True)
        check("amiga-conflicting-duplicate", data)
        data, _ = fixture()
        check("amiga-truncated-track", data[:-257])
        bad = bytearray(data)
        struct.pack_into("<H", bad, 514, 1)
        check("amiga-odd-track-length", bad)
        first = (amiga_track(0, rotate=31), amiga_track(1, rotate=87))
        empty = (b"\xaa" * len(first[0]), b"\xaa" * len(first[1]))
        expected = b"".join(payload(track, number) for track in range(2) for number in range(11))
        check("amiga-trailing-raw-cylinder", hfe([first, empty]), expected, partial=True)
        check("amiga-leading-undecoded-cylinder", hfe([empty, (amiga_track(2), amiga_track(3))]))
        check("amiga-hole-followed-by-data", hfe([first, empty, (amiga_track(4), amiga_track(5))]))
        check("amiga-only-one-side", hfe([(first[0], empty[1])]))
        check("amiga-no-sector-track", hfe([empty]))
        check("amiga-repeated-false-sync", false_sync_tracks())
        # False candidates preceding valid sectors must remain harmless.
        filler = (b"\x44\x89" * 2048).translate(REVERSE)
        valid = hfe([(filler + amiga_track(0), filler + amiga_track(1))])
        check("amiga-false-sync-before-valid", valid, expected)
        if args.cancellation_probe:
            source = folder / "amiga-cancellation.hfe"
            source.write_bytes(valid)
            checked = subprocess.run([str(args.cancellation_probe.resolve()), str(source)],
                                     capture_output=True, timeout=10)
            assert checked.returncode == 0, checked.stdout + checked.stderr
            print(checked.stdout.decode("utf-8", "replace").strip())
        side0, body0 = ibm_track(0)
        side1, body1 = ibm_track(1)
        source, output = folder / "ibm-control.hfe", folder / "ibm-control-output"
        source.write_bytes(hfe([(side0, side1)], encoding=0))
        result = subprocess.run([str(executable), "x", str(source), "-o" + str(output)], capture_output=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (output / "image.img").read_bytes() == body0 + body1
        print("ibm-mfm-existing-control: passed")
        if args.sample:
            assert args.reference, "--sample requires an independent --reference"
            expected = args.reference.read_bytes()
            files = check("real-amiga-82-cylinders", args.sample.read_bytes(), expected, partial=True)
            result = files["image.partial.adf"]
            print("Real HFE sector image SHA256: " + hashlib.sha256(result).hexdigest())
            if args.sector_manifest:
                manifest = json.loads(args.sector_manifest.read_text(encoding="utf-8"))["HFE_err"]["sector_hashes"]
                assert len(manifest) * 512 == len(result)
                for item in manifest:
                    at = (item["track"] * 11 + item["sector"]) * 512
                    assert hashlib.sha256(result[at:at + 512]).hexdigest() == item["sha256"]
                print(f"Real HFE {len(manifest)} independent sector hashes match")
    print("HFE Amiga regressions passed")


if __name__ == "__main__":
    main()
