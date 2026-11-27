"""Exercise the Nuitka 4.4 Windows onefile TOC and payload framing."""

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


def launcher(*, overlay=False, path="data\\message.txt"):
    blob = payload(path, checksums=overlay)
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

        for name, overlay in [("embedded.exe", False), ("overlay.exe", True)]:
            (root / name).write_bytes(launcher(overlay=overlay))
            assert f"{name}: Nuitka onefile" in run("l", name)
            assert "data/message.txt" in run("l", name, "--reader", "nuitka_onefile")
            run("t", name)
            output = root / (name + "-out")
            run("x", name, "-o" + str(output))
            assert (output / "probe.dll").read_bytes() == PROGRAM
            assert (output / "data" / "message.txt").read_bytes() == DATA

        (root / "unsafe.exe").write_bytes(launcher(path="..\\escaped.txt"))
        output = root / "unsafe-out"
        run("x", "unsafe.exe", "--reader", "nuitka_onefile", "-o" + str(output), success=False)
        assert not (root / "escaped.txt").exists()
        (root / "bad-crc.exe").write_bytes(launcher(overlay=True).replace(DATA, b"x" * len(DATA)))
        assert "FAILED" in run("t", "bad-crc.exe", "--verbose", success=False)

    print("Nuitka onefile embedded and overlay recovery, path checks and CRC checks passed")


if __name__ == "__main__":
    main()
