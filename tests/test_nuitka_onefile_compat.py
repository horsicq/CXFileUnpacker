"""Exercise the Windows Nuitka onefile TOC and legacy KAY layouts."""

from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib

from create_unpack_handle_fixtures import pe32, put32


PROGRAM = pe32()
DATA = b"onefile fixture data\n"
MARKER = b"NUITKA_ONEFILE_PARENT\0"


def payload(path="data\\message.txt", checksums=False):
    entries = [(0, "probe.dll", PROGRAM), (4, path, DATA)]
    toc = bytearray()
    for flags, name, content in entries:
        toc += struct.pack("<IIQ", flags, zlib.crc32(content) or 1, len(content)) if checksums else struct.pack("<IQ", flags, len(content))
        toc += name.encode("utf-16le") + b"\0\0"
    body = PROGRAM + DATA
    return struct.pack("<QQ", len(toc), len(body)) + toc + body


def legacy_payload(path="data\\message.txt", checksums=False):
    records = bytearray()
    for name, content in [("probe.dll", PROGRAM), (path, DATA)]:
        records += name.encode("utf-16le") + b"\0\0"
        records += struct.pack("<Q", len(content))
        if checksums:
            records += struct.pack("<I", zlib.crc32(content) or 1)
        records += content
    records += b"\0\0"
    # One single-segment Zstandard frame containing a final raw block.
    block = ((len(records) << 3) | 1).to_bytes(3, "little")
    return b"KAY\x28\xb5\x2f\xfd\xa0" + struct.pack("<I", len(records)) + block + records


def long_offset_payload():
    padding_size = 1 << 25
    first_header = "probe.dll".encode("utf-16le") + b"\0\0" + struct.pack("<Q", len(PROGRAM))
    second_header = "large.bin".encode("utf-16le") + b"\0\0" + struct.pack("<Q", padding_size + 3)
    prefix = first_header + PROGRAM + second_header
    # A raw prefix and 256 RLE blocks fill the history. A final compressed
    # block uses one match with 25 offset bits to copy the start of probe.dll.
    frame = b"KAY\x28\xb5\x2f\xfd\xa0" + struct.pack("<I", len(prefix) + padding_size + 5)
    frame += (len(prefix) << 3).to_bytes(3, "little") + prefix
    frame += (((131072 << 3) | 2).to_bytes(3, "little") + b"\0") * 256
    distance = len(prefix) + padding_size - len(first_header)
    offset_bits = (1 << 25) | (distance - ((1 << 25) - 3))
    # Two trailing NUL bytes end the member stream after the match.
    block = b"\x10\0\0\x01\x54\x00\x19\x00" + offset_bits.to_bytes(4, "little")
    return frame + ((len(block) << 3) | 5).to_bytes(3, "little") + block


def launcher(*, overlay=False, path="data\\message.txt", legacy=False):
    blob = (legacy_payload if legacy else payload)(path, checksums=overlay)
    return launcher_image(blob, overlay)


def launcher_image(blob, overlay):
    section_data = MARKER + bytes(-len(MARKER) % 8)
    if not overlay:
        section_data += blob
    section_data += bytes(-len(section_data) % 512)
    image = bytearray(pe32()[:512] + section_data)
    section = 152 + 224
    image[section:section + 8] = b".rdata\0\0"
    put32(image, section + 8, len(section_data))
    put32(image, section + 16, len(section_data))
    if overlay:
        image += blob + struct.pack("<Q", len(blob))
    return bytes(image)


def main():
    executable = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="xfu-nuitka-") as temp:
        root = Path(temp)

        def run(*args, success=True):
            proc = subprocess.run([str(executable), *map(str, args)], cwd=root,
                                  capture_output=True, text=True, timeout=60)
            assert (proc.returncode == 0) == success, (args, proc.stdout, proc.stderr)
            return proc.stdout + proc.stderr

        for name, overlay, legacy in [
            ("embedded.exe", False, False), ("overlay.exe", True, False),
            ("legacy-embedded.exe", False, True), ("legacy-overlay.exe", True, True),
        ]:
            (root / name).write_bytes(launcher(overlay=overlay, legacy=legacy))
            assert f"{name}: Nuitka onefile" in run("l", name)
            assert "data/message.txt" in run("l", name, "--reader", "nuitka_onefile")
            run("t", name)
            output = root / (name + "-out")
            run("x", name, "-o" + str(output))
            assert (output / "probe.dll").read_bytes() == PROGRAM
            assert (output / "data" / "message.txt").read_bytes() == DATA

        for legacy in (False, True):
            (root / "unsafe.exe").write_bytes(launcher(path="..\\escaped.txt", legacy=legacy))
            output = root / "unsafe-out"
            run("x", "unsafe.exe", "--reader", "nuitka_onefile", "-o" + str(output), success=False)
            assert not (root / "escaped.txt").exists()
            (root / "bad-crc.exe").write_bytes(launcher(overlay=True, legacy=legacy).replace(DATA, b"x" * len(DATA)))
            assert "FAILED" in run("t", "bad-crc.exe", "--verbose", success=False)

        (root / "long-offset.exe").write_bytes(launcher_image(long_offset_payload(), False))
        output = root / "long-offset-out"
        run("x", "long-offset.exe", "-o" + str(output))
        assert (output / "large.bin").read_bytes() == bytes(1 << 25) + PROGRAM[:3]

    print("Nuitka modern and legacy embedded and overlay extraction, path checks and CRC checks passed")


if __name__ == "__main__":
    main()
