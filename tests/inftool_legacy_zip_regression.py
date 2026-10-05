"""Independent legacy MRI/RSFX ZIP local-chain and password fixtures.

python tests/inftool_legacy_zip_regression.py --unpacker PATH --probe PATH [--root DIR]
"""
import argparse
import io
from pathlib import Path
import struct
import subprocess
import tempfile
import zipfile
import zlib

from inftool_regression import pe, ui_string, mutate


def encrypt(data, password):
    keys = [0x12345678, 0x23456789, 0x34567890]

    def crc(old, byte):
        old ^= byte
        for _ in range(8):
            old = (old >> 1) ^ (0xedb88320 if old & 1 else 0)
        return old

    def update(byte):
        keys[0] = crc(keys[0], byte)
        keys[1] = ((keys[1] + (keys[0] & 255)) * 134775813 + 1) & 0xffffffff
        keys[2] = crc(keys[2], keys[1] >> 24)

    for value in password:
        update(value)
    output = bytearray()
    for byte in data:
        value = keys[2] | 2
        output.append(byte ^ (((value * (value ^ 1)) >> 8) & 255))
        update(byte)
    return bytes(output)


def records(password=None, names=("SETUP.INF", "payload.bin"), bad_codec=False):
    values = [b"[Version]\nSignature=\"$CHICAGO$\"\n", bytes(range(239)) * 3]
    local, central = b"", b""
    positions = []
    for method, name, plain in zip((0, 8), names, values):
        offset = len(local)
        flags = 8 | (1 if password is not None else 0)
        if method == 0:
            packed = plain
        else:
            compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
            packed = compressor.compress(plain) + compressor.flush()
            if bad_codec:
                packed = b"\x06" + packed[1:]  # invalid DEFLATE block type3
        if password is not None:
            packed = encrypt(bytes(range(11)) + b"\x12" + packed, password)
        name = name.encode("ascii")
        crc = zlib.crc32(plain)
        header = struct.pack("<IHHHHHIIIHH", 0x04034b50, 20, flags, method,
                             0x1234, 0x2421, crc, len(packed), len(plain), len(name), 0)
        descriptor = struct.pack("<IIII", 0x08074b50, crc, len(packed), len(plain))
        local += header + name + packed + descriptor
        positions.append((offset, offset + 30 + len(name), offset + 30 + len(name) + len(packed)))
        central += struct.pack("<I6H3I5H2I", 0x02014b50, 20, 20, flags, method,
                               0x1234, 0x2421, crc, len(packed), len(plain), len(name),
                               0, 0, 0, 0, 32, offset) + name
    eocd = struct.pack("<I4H2IH", 0x06054b50, 0, 0, 2, 2, len(central), len(local), 0)
    if not bad_codec and password != b"":
        with zipfile.ZipFile(io.BytesIO(local + central + eocd)) as check:
            assert {n: check.read(n, pwd=password) for n in check.namelist()} == dict(zip(names, values))
    return local + b"RSFX", dict(zip(names, values)), positions


def package(local, inf=b"SETUP.INF"):
    outer = pe()
    title, publisher = b"Legacy independent fixture", b"Fixture author"
    welcome, license_text = b"Welcome.\n", b"Fixture license.\n"
    strings = title + inf + ui_string(publisher) + ui_string(welcome) + ui_string(license_text)
    size = len(outer) + 22 + len(strings) + len(local)
    header = b"MRI" + bytes([1, len(title), len(inf), 0, len(publisher)])
    header += struct.pack("<II", len(welcome), len(license_text)) + b"\1\0" + struct.pack("<I", size)
    assert len(header) == 22
    return outer + header + strings + local


def run(args, root):
    body, expected, positions = records()
    good = package(body)
    cases = {"legacy-unencrypted.exe": (good, True, True, expected, None)}
    cases["legacy-tempdir-placeholder.exe"] = (package(body, inf=b"><SETUP.INF"), True, True, expected, None)
    for inf in [b"><../SETUP.INF", b"><C:/SETUP.INF", b"><", b"bad><SETUP.INF"]:
        cases[f"legacy-unsafe-template-{len(cases)}.exe"] = (package(body, inf=inf), False, False, {}, None)
    encrypted, expected, positions_enc = records(password=b"fixture-secret")
    if args.lifecycle_probe:
        lifecycle = root / "persistent-password.exe"
        lifecycle.write_bytes(package(encrypted))
        checked = subprocess.run([str(args.lifecycle_probe.resolve()), str(lifecycle.resolve())],
                                 capture_output=True, text=True, timeout=30)
        if checked.returncode:
            raise AssertionError(f"Persistent password lifecycle failed\n{checked.stdout}\n{checked.stderr}")
        print(checked.stdout.strip())
    for label, password, extracts in [("missing", None, False), ("wrong", "wrong", False),
                                      ("correct", "fixture-secret", True)]:
        cases[f"legacy-password-{label}.exe"] = (package(encrypted), True, extracts, expected, password)
    cases["legacy-empty-password.exe"] = (package(records(password=b"")[0]), True, True, expected, "")
    bad_codec, _, _ = records(bad_codec=True)
    # The first stored member can be extracted before the later codec failure.
    cases["legacy-codec.exe"] = (package(bad_codec), True, False, {"SETUP.INF": expected["SETUP.INF"]}, None)
    at = 1024
    for name, offset, value in [
        ("size", at + 18, struct.pack("<I", len(good) + 1)),
        ("string", at + 12, struct.pack("<I", 0xffffffff)),
        ("split", at + 17, b"\1"),
        ("type", at + 3, b"\2"),
    ]:
        cases[f"legacy-{name}.exe"] = (mutate(good, offset, value), False, False, {}, None)
    for name, offset, value in [
        ("descriptor-crc", positions[0][2] + 4, struct.pack("<I", 1)),
        ("descriptor-packed", positions[0][2] + 8, struct.pack("<I", 1)),
        ("packed-bound", positions[0][0] + 18, struct.pack("<I", 0xffffffff)),
        ("name-bound", positions[0][0] + 26, b"\xff\xff"),
        ("method", positions[0][0] + 8, b"\x63\0"),
        ("missing-descriptor-flag", positions[0][0] + 6, b"\0\0"),
        ("strong-encryption", positions[0][0] + 6, b"\x48\0"),
        ("missing-local", 0, b"XXXX"),
        ("trailer", len(body) - 4, b"xxxx"),
    ]:
        cases[f"legacy-{name}.exe"] = (package(mutate(body, offset, value)), False, False, {}, None)
    for label, changed in [("truncated-body", body[:-1]), ("body-suffix", body + b"x"),
                           ("unindexed-body", body[:-4] + b"xRSFX")]:
        cases[f"legacy-{label}.exe"] = (package(changed), False, False, {}, None)
    for names in [("SETUP.INF", "../escape.bin"), ("SETUP.INF", "C:/escape.bin"),
                  ("OTHER.INF", "payload.bin")]:
        changed, _, _ = records(names=names)
        cases[f"legacy-name-{len(cases)}.exe"] = (package(changed), False, False, {}, None)
    for name, (data, valid, extracts, expected, password) in cases.items():
        source = root / name; source.write_bytes(data)
        probe = subprocess.run([str(args.probe.resolve()), str(source.resolve()), "sfx_inftool"],
                               capture_output=True, text=True, timeout=30)
        if probe.returncode or ("valid=1 parsed=1" in probe.stdout) != valid:
            raise AssertionError(f"{name}: parse differs\n{probe.stdout}\n{probe.stderr}")
        output = root / (name + "-output")
        command = [str(args.unpacker.resolve()), "x", str(source.resolve()), "-o" + str(output.resolve())]
        if password is not None:
            command += ["-p" + password]
        process = subprocess.run(command, capture_output=True, text=True, timeout=30)
        files = {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob("*") if p.is_file()} if output.exists() else {}
        if extracts:
            if process.returncode or files != expected:
                raise AssertionError(f"{name}: extraction differs\n{process.stdout}\n{process.stderr}")
        elif not process.returncode or (files != expected if "codec" in name else bool(files)):
            raise AssertionError(f"{name}: invalid/password input falsely succeeded or created files\n{process.stdout}")
    print(f"INFTool legacy ZIP regression: {len(cases)} cases passed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unpacker", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--lifecycle-probe", type=Path,
                        help="Optional dedicated C persistent-reader password lifecycle executable")
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    if args.root:
        args.root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="inftool-legacy-", dir=args.root) as temporary:
        run(args, Path(temporary))


if __name__ == "__main__":
    main()
