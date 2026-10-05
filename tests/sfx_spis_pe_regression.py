"""Independent PE/SPIS fixtures. Only invoke readers; never execute a stub.

python tests/sfx_spis_pe_regression.py --unpacker PATH --probe PATH [--root DIR]
"""
import argparse
from pathlib import Path
import struct
import subprocess
import tempfile


def u32(value):
    return struct.pack("<I", value)


def pe(payload, certificate=None, extra_padding=0, bits=32):
    image = bytearray(1024)
    image[:2] = b"MZ"
    image[60:64] = u32(128)
    image[128:152] = b"PE\0\0" + struct.pack("<HHIIIHH", 0x14c if bits == 32 else 0x8664,
                                          1, 0, 0, 0, 224 if bits == 32 else 240, 0x102)
    optional = 152
    struct.pack_into("<H", image, optional, 0x10b if bits == 32 else 0x20b)
    image[optional + 60:optional + 64] = u32(512)
    directory_base = 96 if bits == 32 else 112
    image[optional + directory_base - 4:optional + directory_base] = u32(16)
    section = optional + (224 if bits == 32 else 240)
    image[section:section + 8] = b".text\0\0\0"
    image[section + 16:section + 24] = u32(512) + u32(512)
    image += payload
    if certificate is not None:
        image += b"\0" * ((-len(image) % 8) + extra_padding)
        offset = len(image)
        image += certificate
        image[optional + directory_base + 32:optional + directory_base + 40] = (
            u32(offset) + u32(len(certificate)))
    return bytes(image)


def single(payload):
    return b"SPIS\x1aNON" + u32(len(payload)) + b"\0" + u32(sum(payload)) + u32(0) + payload


def stored(name, payload):
    name = name.encode("ascii")
    header = b"SPIS\x1aLZH" + u32(len(payload)) + b"\1" + u32(0) + u32(0)
    record = struct.pack("<HIHII BII", len(name), 0, 0, len(payload), len(payload),
                         0, sum(payload), 0)
    return header + record + name + payload


def installus(first, second):
    strings = [b"", b"Can&cel",
               b"PreSetup will prepare the temporary files needed for installation.",
               b"Setup needs to run on Win-32. Installation may fail!",
               b"Starting Setup!", b"Offline fixture", b"One moment please...",
               b"Error during launching setup", b"PreSetup"]
    prologue = b"".join(bytes([len(value)]) + value for value in strings)
    lengths = b"".join(bytes([len(str(len(value)))]) + str(len(value)).encode()
                       for value in (first, second))
    return prologue + lengths + first + second + b"\0" * 4


def mutate(data, at, value):
    result = bytearray(data)
    result[at:at + len(value)] = value
    return bytes(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unpacker", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--root", type=Path, help="Optional parent for temporary fixtures")
    args = parser.parse_args()
    if args.root:
        args.root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sfx-spis-pe-", dir=args.root) as temporary:
        run_cases(args, Path(temporary))


def run_cases(args, root):
    first_payload, second_payload = b"First independent payload.\n", b"Second payload.\n"
    # Give the two volumes independent member names. Type0 blobs both
    # synthesize payload.bin, which exercises output collision handling
    # instead of the carrier/certificate framing under test here.
    first, second = stored("first.txt", first_payload), stored("second.txt", second_payload)
    chain = u32(len(first)) + first + u32(len(second)) + second
    # Structural certificate fixture: revision 2.0/type PKCS#7, length 11,
    # independently padded to 16 bytes. The reader does not authenticate it.
    certificate = u32(11) + struct.pack("<HH", 0x200, 2) + b"sig" + b"\0" * 5
    signed = pe(chain, certificate)
    cert_offset = struct.unpack_from("<I", signed, 152 + 96 + 32)[0]
    gap = cert_offset - (1024 + len(chain))
    assert 0 < gap <= 7
    iu_first, iu_second = stored("first.txt", first_payload), stored("second.txt", second_payload)
    iu_payload = installus(iu_first, iu_second)
    iu = pe(iu_payload)
    cases = {
        "gp-unsigned.exe": (pe(chain), True),
        "gp-signed.exe": (signed, True),
        "gp-signed-pe64.exe": (pe(chain, certificate, bits=64), True),
        "gp-two-certificates.exe": (pe(chain, certificate + certificate), True),
        "gp-cert-truncated.exe": (signed[:-1], False),
        "gp-cert-suffix.exe": (signed + b"suffix", False),
        "gp-cert-rva.exe": (mutate(signed, 152 + 96 + 32, u32(512)), False),
        "gp-cert-unaligned.exe": (mutate(signed, 152 + 96 + 32, u32(cert_offset + 1)), False),
        "gp-cert-size.exe": (mutate(signed, 152 + 96 + 36, u32(17)), False),
        "gp-cert-short-length.exe": (mutate(signed, cert_offset, u32(7)), False),
        "gp-cert-long-length.exe": (mutate(signed, cert_offset, u32(17)), False),
        "gp-cert-revision.exe": (mutate(signed, cert_offset + 4, b"\0\1"), False),
        "gp-cert-type.exe": (mutate(signed, cert_offset + 6, b"\3\0"), False),
        "gp-cert-nonzero-padding.exe": (mutate(signed, cert_offset + 11, b"x"), False),
        "gp-chain-nonzero-padding.exe": (mutate(signed, 1024 + len(chain), b"x"), False),
        "gp-chain-excess-padding.exe": (pe(chain, certificate, extra_padding=8), False),
        "gp-chain-size.exe": (mutate(signed, 1024, u32(len(first) + 1)), False),
        "gp-chain-checksum.exe": (mutate(signed, 1024 + 4 + 21 + 17, u32(1)), False),
        "installus-pe.exe": (iu, True),
        "installus-pe64.exe": (pe(iu_payload, bits=64), True),
        "installus-prologue.exe": (mutate(iu, 1024 + 2, b"x"), False),
        "installus-size.exe": (pe(iu_payload.replace(str(len(iu_first)).encode(), b"99", 1)), False),
        "installus-checksum.exe": (pe(installus(mutate(iu_first, 21 + 17, u32(1)), iu_second)), False),
        "installus-name.exe": (pe(installus(stored("../a.txt", first_payload), iu_second)), False),
        "installus-truncated.exe": (iu[:-1], False),
        "installus-suffix.exe": (iu + b"x", False),
    }
    for name, (data, valid) in cases.items():
        source = root / name
        source.write_bytes(data)
        probe = subprocess.run([str(args.probe.resolve()), str(source.resolve()), "sfx_spis"],
                               capture_output=True, text=True, timeout=30)
        actual = "sfx_spis type=sfx spis valid=1 parsed=1" in probe.stdout
        if probe.returncode or actual != valid:
            raise AssertionError(f"{name}: reader validity differs\n{probe.stdout}\n{probe.stderr}")
        output = root / (name + "-output")
        result = subprocess.run([str(args.unpacker.resolve()), "x", str(source.resolve()),
                                 "-o" + str(output.resolve())],
                                capture_output=True, text=True, timeout=30)
        files = [p for p in output.rglob("*") if p.is_file()] if output.exists() else []
        if valid:
            if result.returncode or len(files) != 2 or sorted(p.read_bytes() for p in files) != sorted(
                    [first_payload, second_payload]):
                raise AssertionError(f"{name}: extracted payload differs\n{result.stdout}\n{result.stderr}")
        elif result.returncode == 0 or files:
            raise AssertionError(f"{name}: invalid archive produced success or files")
    print(f"SPIS PE regression: {len(cases)} cases passed")


if __name__ == "__main__":
    main()
