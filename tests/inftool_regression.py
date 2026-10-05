"""Independent MRI/CAB fixtures; installer stubs are data and never executed.

python tests/inftool_regression.py --unpacker PATH --probe PATH [--root DIR]
"""
import argparse
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib


def checksum(data, seed=0):
    aligned = len(data) & ~3
    for at in range(0, aligned, 4):
        seed ^= int.from_bytes(data[at:at + 4], "little")
    return seed ^ int.from_bytes(data[aligned:], "big")


def pe(dll=False, raw_size=512):
    image = bytearray(512 + raw_size)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 60, 128)
    image[128:132] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", image, 132, 0x14c, 1, 0, 0, 0, 224,
                     0x2102 if dll else 0x102)
    struct.pack_into("<H", image, 152, 0x10b)
    struct.pack_into("<I", image, 152 + 60, 512)
    image[376:384] = b".text\0\0\0"
    struct.pack_into("<IIII", image, 384, raw_size, 4096, raw_size, 512)
    struct.pack_into("<I", image, 412, 0x60000020)
    return bytes(image)


def ui_string(data):
    result = bytearray(data)
    state = 555
    for at in range(1, len(result)):
        state = (state * 0x08088405 + 1) & 0xffffffff
        result[at] ^= (state >> 25) | 128
    return bytes(result)


def lzx_uncompressed(data):
    # LZX words are little endian, while each word's bits are read MSB first.
    # Stream has no E8 translation, block type3, 24-bit length, word alignment,
    # three little endian repeated offsets, then uncompressed bytes.
    bits = "0" + "011" + f"{len(data):024b}"
    bits += "0" * (-len(bits) % 16)
    words = b"".join(struct.pack("<H", int(bits[at:at + 16], 2))
                     for at in range(0, len(bits), 16))
    return words + struct.pack("<III", 1, 1, 1) + data + (b"\0" if len(data) & 1 else b"")


def cabinet(method=0, names=("SETUP.INF", "data/payload.bin"), folders=1,
            reserved=False, optional_checksum=False, corrupt_codec=False):
    values = [b"[Version]\r\nSignature=\"$CHICAGO$\"\r\n", bytes(range(251)) * 3]
    flags = 2 | (4 if reserved else 0)
    hr, fr, dr = (b"HR!", b"F", b"DR!") if reserved else (b"", b"", b"")
    extras = (struct.pack("<HBB", len(hr), len(fr), len(dr)) + hr) if reserved else b""
    extras += b"unused-next.cab\0\0"
    files_at = 36 + len(extras) + folders * (8 + len(fr))
    table = b""
    offsets = [0, len(values[0])] if folders == 1 else [0, 0]
    for i, (name, data) in enumerate(zip(names, values)):
        table += struct.pack("<IIHHHH", len(data), offsets[i], i if folders == 2 else 0,
                             0, 0, 32) + name.encode("ascii") + b"\0"
    data_at = files_at + len(table)
    folder_table, blocks = b"", b""
    plains = [b"".join(values)] if folders == 1 else values
    for plain in plains:
        if method == 0:
            packed = plain
        elif method == 1:
            encoder = zlib.compressobj(9, zlib.DEFLATED, -15)
            packed = b"CK" + encoder.compress(plain) + encoder.flush()
            if corrupt_codec:
                packed = b"XX" + packed[2:]
        else:
            packed = lzx_uncompressed(plain)
            if corrupt_codec:
                packed = packed[:4] + struct.pack("<I", 0) + packed[8:]
        lengths = struct.pack("<HH", len(packed), len(plain))
        csum = 0 if optional_checksum else checksum(lengths + dr, checksum(packed))
        block = struct.pack("<I", csum) + lengths + dr + packed
        folder_table += struct.pack("<IHH", data_at + len(blocks), 1,
                                    0x1503 if method == 3 else method) + fr
        blocks += block
    size = data_at + len(blocks)
    header = b"MSCF" + struct.pack("<IIIII", 0, size, 0, files_at, 0)
    header += struct.pack("<BBHHHHH", 3, 1, folders, len(names), flags, 0, 0)
    assert len(header) == 36
    return header + extras + folder_table + table + blocks, dict(zip(names, values))


def package(cab, mask=True, split=False, outer_size=512):
    outer, dll = pe(raw_size=outer_size), pe(dll=True)
    title, inf, publisher = b"Independent fixture", b"SETUP.INF", b"Fixture publisher"
    welcome, license_text = b"Welcome.\r\n", b"Fixture license.\r\n"
    # Keep malformed masked packages from falling back to the generic SFX CAB
    # reader solely because their particular full length yielded XOR key zero.
    length = len(outer) + len(dll) + 24 + len(title) + len(inf) + len(publisher) + len(welcome) + len(license_text) + len(cab)
    if mask and length % 13 == 0:
        license_text += b" "
    strings = title + inf + ui_string(publisher) + ui_string(welcome) + ui_string(license_text)
    total = len(outer) + len(dll) + 24 + len(strings) + len(cab)
    header = b"MRI" + bytes([1, len(title), len(inf), 0, len(publisher)])
    header += struct.pack("<II", len(welcome), len(license_text))
    header += bytes([1, int(split), 1, int(mask)]) + struct.pack("<I", total)
    assert len(header) == 24
    encoded = bytes(x ^ (total % 13) for x in cab) if mask else cab
    return outer + dll + header + strings + encoded


def mutate(data, offset, value):
    output = bytearray(data)
    output[offset:offset + len(value)] = value
    return bytes(output)


def run_cases(args, root):
    tests = {}
    for method in (0, 1, 3):
        for folders in (1, 2):
            for reserve in (False, True):
                cab, expected = cabinet(method=method, folders=folders, reserved=reserve)
                tests[f"valid-{method}-{folders}-{reserve}.exe"] = (package(cab), True, True, expected)
    cab, expected = cabinet()
    good = package(cab)
    tests["valid-unmasked.exe"] = (package(cab, mask=False), True, True, expected)
    tests["valid-larger-pe.exe"] = (package(cab, outer_size=1024), True, True, expected)
    no_checksum, expected = cabinet(optional_checksum=True)
    tests["valid-optional-checksum.exe"] = (package(no_checksum), True, True, expected)
    mri_at = 2048
    for name, offset, value in [
        ("outer-pe-bound", 392, struct.pack("<I", 0xffffffff)),
        ("outer-pe-offset", 396, struct.pack("<I", 0xffffffff)),
        ("nested-pe-bound", 1024 + 392, struct.pack("<I", 0xffffffff)),
        ("nested-not-dll", 1024 + 150, struct.pack("<H", 0x102)),
        ("bad-mri", mri_at, b"BAD"),
        ("unsupported-type", mri_at + 3, b"\2"),
        ("zero-inf-name", mri_at + 5, b"\0"),
        ("string-bounds", mri_at + 8, struct.pack("<I", 0xffffffff)),
        ("invalid-flag", mri_at + 19, b"\2"),
        ("split-volume", mri_at + 17, b"\1"),
        ("declared-size", mri_at + 20, struct.pack("<I", len(good) + 1)),
    ]:
        tests[name + ".exe"] = (mutate(good, offset, value), False, False, {})
    tests["truncated.exe"] = (good[:-1], False, False, {})
    tests["suffix.exe"] = (good + b"x", False, False, {})
    # Modify the unmasked CAB, then build a fresh correctly sized/XORed MRI
    # package. Thus these failures cannot be attributed only to its outer size.
    folder_at = 36 + len(b"unused-next.cab\0\0")
    file_at = struct.unpack_from("<I", cab, 16)[0]
    data_at = struct.unpack_from("<I", cab, folder_at)[0]
    for name, offset, value in [
        ("cab-size", 8, struct.pack("<I", len(cab) - 1)),
        ("cab-file-table", 16, struct.pack("<I", 1)),
        ("cab-folder-overlap", folder_at, struct.pack("<I", file_at)),
        ("cab-continued-file", file_at + 8, struct.pack("<H", 0xffff)),
        ("cab-file-overrun", file_at, struct.pack("<I", 0xffffffff)),
        ("cab-split-block", data_at + 6, b"\0\0"),
        ("cab-packed-overrun", data_at + 4, b"\xff\xff"),
        ("cab-checksum", data_at, struct.pack("<I", 1)),
        ("cab-unreferenced-suffix", 8, struct.pack("<I", len(cab) + 1)),
    ]:
        changed = mutate(cab, offset, value)
        if name == "cab-unreferenced-suffix":
            changed += b"x"
        tests[name + ".exe"] = (package(changed), False, False, {})
    for names in [("SETUP.INF", "../escape.bin"), ("SETUP.INF", "C:/escape.bin"),
                  ("SETUP.INF", "data//escape.bin"), ("OTHER.INF", "payload.bin")]:
        bad, _ = cabinet(names=names)
        tests[f"bad-name-{len(tests)}.exe"] = (package(bad), False, False, {})
    for method in (1, 3):
        bad, _ = cabinet(method=method, corrupt_codec=True)
        tests[f"bad-codec-{method}.exe"] = (package(bad), True, False, {})
    for name, (data, parses, extracts, expected) in tests.items():
        source = root / name
        source.write_bytes(data)
        result = subprocess.run([str(args.probe.resolve()), str(source.resolve()), "sfx_inftool"],
                                capture_output=True, text=True, timeout=30)
        valid = "valid=1 parsed=1" in result.stdout
        if result.returncode or valid != parses:
            raise AssertionError(f"{name}: parse differs\n{result.stdout}\n{result.stderr}")
        output = root / (name + "-output")
        result = subprocess.run([str(args.unpacker.resolve()), "x", str(source.resolve()),
                                 "-o" + str(output.resolve())], capture_output=True,
                                text=True, timeout=30)
        files = {p.relative_to(output).as_posix(): p.read_bytes()
                 for p in output.rglob("*") if p.is_file()} if output.exists() else {}
        if extracts:
            if result.returncode or files != expected:
                raise AssertionError(f"{name}: extraction differs\n{result.stdout}\n{result.stderr}")
        elif result.returncode == 0 or files:
            raise AssertionError(f"{name}: invalid package extracted or claimed success\n{result.stdout}")
    print(f"INFTool regression: {len(tests)} independent cases passed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unpacker", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    if args.root:
        args.root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="inftool-", dir=args.root) as temp:
        run_cases(args, Path(temp))


if __name__ == "__main__":
    main()
