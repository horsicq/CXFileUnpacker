"""Independent Jugglor 1.01 fixtures; never execute carrier stubs."""
import argparse
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

from sfx_spis_pe_regression import mutate, pe, u32


def jugglor(payload, version="1.01", reserved=797, packed=None, declared=None):
    if packed is None:
        packed = zlib.compress(payload)
    if declared is None:
        declared = len(payload)
    header = bytearray(0x31c)
    header[:4] = u32(0x6a4a61a3)
    name = b"payload.txt"
    header[4:5 + len(name)] = bytes([len(name)]) + name
    header[0x304:0x30c] = u32(declared) + u32(len(packed))
    header[0x318:0x31c] = u32(0x8cf9bf0d)
    chain = bytes(header) + packed
    trailer = bytearray(220)
    trailer[:24] = struct.pack("<6I", 0x6a4a61a3, 1024, len(chain), 1, reserved, declared)
    text = ("Jester Jugglor Version " + version).encode("ascii")
    trailer[24:25 + len(text)] = bytes([len(text)]) + text
    trailer[216:220] = u32(0x8cf9bf0d)
    return pe(chain + trailer)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unpacker", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    if args.root:
        args.root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jugglor-legacy-", dir=args.root) as temporary:
        run_cases(args, Path(temporary))


def run_cases(args, root):
    payload = b"Independently compressed Jugglor legacy payload.\n"
    valid = jugglor(payload)
    packed = zlib.compress(payload)
    bad_checksum = packed[:-1] + bytes([packed[-1] ^ 1])
    cases = {
        "legacy.exe": (valid, True, True),
        "legacy-zero.exe": (jugglor(payload, reserved=0), True, True),
        "modern-zero.exe": (jugglor(payload, version="2.01", reserved=0), True, True),
        "wrong-reserved.exe": (jugglor(payload, reserved=798), False, False),
        "wrong-version.exe": (jugglor(payload, version="1.02"), False, False),
        "version-suffix.exe": (jugglor(payload, version="1.01extra"), False, False),
        "wrong-count.exe": (mutate(valid, len(valid) - 220 + 12, u32(2)), False, False),
        "wrong-total.exe": (mutate(valid, len(valid) - 220 + 20, u32(len(payload) + 1)), False, False),
        "wrong-overlay.exe": (mutate(valid, len(valid) - 220 + 4, u32(1025)), False, False),
        "wrong-chain-size.exe": (mutate(valid, len(valid) - 220 + 8, u32(1)), False, False),
        "truncated.exe": (valid[:-1], False, False),
        # Framing remains valid; extraction must retain exact inflate/Adler32 checks.
        "bad-adler.exe": (jugglor(payload, packed=bad_checksum), True, False),
        "wrong-raw-size.exe": (jugglor(payload, declared=len(payload) - 1), True, False),
    }
    for name, (data, parsed, extracted) in cases.items():
        source = root / name
        source.write_bytes(data)
        probe = subprocess.run([str(args.probe.resolve()), str(source.resolve()),
                                "sfx_flashjester_jugglor"],
                               capture_output=True, text=True, timeout=30)
        actual = "sfx_flashjester_jugglor type=FlashJester Jugglor valid=1 parsed=1" in probe.stdout
        if probe.returncode or actual != parsed:
            raise AssertionError(f"{name}: reader validity differs\n{probe.stdout}\n{probe.stderr}")
        output = root / (name + "-output")
        result = subprocess.run([str(args.unpacker.resolve()), "x", str(source.resolve()),
                                 "-o" + str(output.resolve())],
                                capture_output=True, text=True, timeout=30)
        files = [p for p in output.rglob("*") if p.is_file()] if output.exists() else []
        if extracted:
            if result.returncode or len(files) != 1 or files[0].read_bytes() != payload:
                raise AssertionError(f"{name}: extracted payload differs\n{result.stdout}\n{result.stderr}")
        elif result.returncode == 0 or files:
            raise AssertionError(f"{name}: invalid archive produced success or files")
    print(f"FlashJester legacy regression: {len(cases)} cases passed")


if __name__ == "__main__":
    main()
