"""Offline Makeself 1.x fixtures; run only the unpacker, never the stubs.

python tests/makeself_legacy_regression.py --unpacker PATH --probe PATH --root DIR
"""
import argparse
import bz2
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile


def legacy(payload, spaced=True):
    lines = [
        "#! /bin/sh" if spaced else "#!/bin/sh",
        "skip=0",
        "# This script was generated using Makeself 1.5.2",
        'label="Offline regression"',
        "tail +$skip $0 | bzip2 -d | tar xvof -",
        "END_OF_STUB",
    ]
    lines[1] = f"skip={len(lines) + 1}"
    return ("\n".join(lines) + "\n").encode() + payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unpacker", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--root", type=Path, help="Optional parent for temporary fixtures")
    args = parser.parse_args()
    if args.root:
        args.root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="makeself-legacy-", dir=args.root) as temporary:
        run_cases(args, Path(temporary))


def run_cases(args, root):
    plain = io.BytesIO()
    expected = b"An independently generated Makeself payload.\n"
    with tarfile.open(fileobj=plain, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        member = tarfile.TarInfo("payload.txt")
        member.size = len(expected)
        tar.addfile(member, io.BytesIO(expected))
    payload = bz2.compress(plain.getvalue(), compresslevel=9)
    bad_crc = bytearray(payload)
    bad_crc[10] ^= 1  # First block CRC, beyond the BZh/PI magic.
    cases = {
        "spaced-old.run": (legacy(payload), True),
        "unspaced-old.run": (legacy(payload, spaced=False), True),
        "old-script.sh": (legacy(payload), True),
        "wrong-skip.run": (legacy(payload).replace(b"skip=7", b"skip=8", 1), False),
        # The suffix must not route around the rejected shell wrapper and
        # successfully extract its embedded BZip2 payload with the engine.
        "wrong-skip.bz2": (legacy(payload).replace(b"skip=7", b"skip=8", 1), False),
        "missing-marker.run": (legacy(payload).replace(b"END_OF_STUB", b"END_OF_NOPE", 1), False),
        "truncated.run": (legacy(payload[:-1]), False),
        "bad-crc.run": (legacy(bytes(bad_crc)), False),
        "suffix.run": (legacy(payload) + b"extra", False),
        "not-tar.run": (legacy(bz2.compress(b"This is not a TAR archive.")), False),
        "fake-generator.run": (legacy(payload).replace(b"Makeself 1.5.2", b"Something else", 1), False),
    }
    for name, (data, valid) in cases.items():
        source = root / name
        source.write_bytes(data)
        probe = subprocess.run([str(args.probe.resolve()), str(source.resolve()), "makeself"],
                               capture_output=True, text=True, timeout=30)
        actual = "makeself type=makeself valid=1 parsed=1" in probe.stdout
        if probe.returncode or actual != valid:
            raise AssertionError(f"{name}: reader validity differs\n{probe.stdout}\n{probe.stderr}")
        output = root / (name + "-output")
        result = subprocess.run([str(args.unpacker.resolve()), "x", str(source.resolve()),
                                 "-o" + str(output.resolve())],
                                capture_output=True, text=True, timeout=30)
        if valid:
            if result.returncode:
                raise AssertionError(f"{name}: extraction failed\n{result.stdout}\n{result.stderr}")
            extracted = list(output.rglob("*.tar.bz2"))
            if len(extracted) != 1 or extracted[0].read_bytes() != payload:
                raise AssertionError(f"{name}: compressed payload bytes differ")
            with tarfile.open(fileobj=io.BytesIO(bz2.decompress(extracted[0].read_bytes()))) as tar:
                if tar.extractfile("payload.txt").read() != expected:
                    raise AssertionError(f"{name}: independent TAR payload differs")
        elif result.returncode == 0 or (output.exists() and any(output.rglob("*"))):
            raise AssertionError(f"{name}: invalid archive produced success or output")
    print(f"Makeself legacy regression: {len(cases)} cases passed")


if __name__ == "__main__":
    main()
