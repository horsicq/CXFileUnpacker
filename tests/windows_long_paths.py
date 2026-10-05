"""Windows long paths, staging cleanup, and reparse ancestor rejection.

The 7z fixture is independently encoded with one Copy coder and a data CRC.
It exercises the reader's 45-character staging suffix without an encoder
dependency. ZIP uses Python's standard library.
"""

import os
import pathlib
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib


DATA = b"Long path regression: \x00\x01\xfe\xff\n" * 13


def number(value):
    """Encode the 7z variable-length UInt64, independently of the reader."""
    for extra in range(8):
        if value < 1 << (7 + 7 * extra):
            prefix = (0xff << (8 - extra)) & 0xff
            high = value >> (8 * extra)
            return bytes((prefix | high,)) + value.to_bytes(8, "little")[:extra]
    return b"\xff" + value.to_bytes(8, "little")


def seven_zip(name, corrupt=False):
    encoded_name = name.encode("utf-16le") + b"\0\0"
    streams = (b"\x06" + number(0) + number(1) + b"\x09" + number(len(DATA)) +
               b"\0\x07\x0b" + number(1) + b"\0" +
               number(1) + b"\x01\0" + b"\x0c" + number(len(DATA)) +
               b"\x0a\x01" + struct.pack("<I", zlib.crc32(DATA)) + b"\0\0")
    header = (b"\x01\x04" + streams + b"\x05" + number(1) +
              b"\x11" + number(1 + len(encoded_name)) + b"\0" +
              encoded_name + b"\0\0")
    start = struct.pack("<QQI", len(DATA), len(header), zlib.crc32(header))
    packed = bytes((DATA[0] ^ 1,)) + DATA[1:] if corrupt else DATA
    return (b"7z\xbc\xaf\x27\x1c\x00\x04" +
            struct.pack("<I", zlib.crc32(start)) + start + packed + header)


def member_for_length(output, target):
    remaining = target - len(str(output.resolve())) - 1
    components = []
    while remaining > 100:
        component = "目录_" + "d" * 44
        components.append(component)
        remaining -= len(component) + 1
    leaf = "报告_" + "f" * (remaining - 7) + ".bin"
    if len(leaf) < 7:
        raise AssertionError("temporary directory too long for fixture")
    components.append(leaf)
    name = "/".join(components)
    if len(str(output.resolve() / pathlib.Path(name))) != target:
        raise AssertionError((output, name, target))
    return name


def invoke(cli, source, output, cwd=None, succeeds=True):
    result = subprocess.run([cli, "x", str(source), "-o" + str(output)],
                            cwd=cwd, capture_output=True, timeout=30)
    if (result.returncode == 0) != succeeds:
        raise AssertionError((result.returncode, result.stdout, result.stderr))


def no_stages(output):
    leftovers = [str(path) for path in output.rglob("*")
                 if ".xxfclib.tmp." in path.name]
    if leftovers:
        raise AssertionError(("staging files left behind", leftovers))


def check(cli, root, label, target_length=None, kind="7z",
          relative=False, extended=False, long_input=False):
    output = root / (label + "_out")
    name = member_for_length(output, target_length) if target_length else "目录/报告.bin"
    destination = output / pathlib.Path(name)
    if target_length == 235:
        assert len(str(destination)) < 260 < len(str(destination)) + 45
    source = root / (label + "." + kind)
    if long_input:
        source = root / ("input_" + "a" * 44) / ("b" * 50) / ("c" * 50) / ("d" * 50) / source.name
        source.parent.mkdir(parents=True)
        assert len(str(source)) > 260
    if kind == "7z":
        source.write_bytes(seven_zip(name))
    else:
        with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(name, DATA)
    output_arg = output.name if relative else str(output)
    if extended:
        output_arg = "\\\\?\\" + str(output)
    invoke(cli, source, output_arg, cwd=root if relative else None)
    if destination.read_bytes() != DATA:
        raise AssertionError((label, "output differs"))
    no_stages(output)

    # Existing long target exercises exists and atomic replacement. A corrupt
    # member must remove its staging file and leave the previous target intact.
    if kind == "7z":
        destination.write_bytes(b"previous file")
        invoke(cli, source, output_arg, cwd=root if relative else None)
        if destination.read_bytes() != DATA:
            raise AssertionError((label, "replacement differs"))
        no_stages(output)
        source.write_bytes(seven_zip(name, corrupt=True))
        destination.write_bytes(b"preserve on CRC failure")
        invoke(cli, source, output_arg, cwd=root if relative else None, succeeds=False)
        if destination.read_bytes() != b"preserve on CRC failure":
            raise AssertionError((label, "failed extraction replaced existing file"))
        no_stages(output)


def junction_check(cli, root):
    outside = root / "outside"
    outside.mkdir()
    sentinel = outside / "bad.bin"
    sentinel.write_bytes(b"outside file must survive")
    output = root / "junction_output"
    output.mkdir()
    junction = output / "escape"
    result = subprocess.run(["cmd", "/d", "/c", "mklink", "/J",
                             str(junction), str(outside)], capture_output=True)
    if result.returncode:
        raise AssertionError(("cannot create junction fixture", result.stdout,
                              result.stderr))
    source = root / "junction.7z"
    source.write_bytes(seven_zip("escape/bad.bin"))
    try:
        invoke(cli, source, output, succeeds=False)
        assert sentinel.read_bytes() == b"outside file must survive"
        no_stages(outside)
        # The output root itself can also be a junction; its ancestors still
        # need validation when the reader creates a member's parent directory.
        source.write_bytes(seven_zip("bad.bin"))
        invoke(cli, source, junction, succeeds=False)
        assert sentinel.read_bytes() == b"outside file must survive"
        no_stages(outside)
    finally:
        os.rmdir(junction)


def main():
    if os.name != "nt":
        print("Windows long-path regression skipped on this platform")
        return
    cli = str(pathlib.Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory(prefix="xfu-win-paths-") as temporary:
        root = pathlib.Path(temporary)
        check(cli, root, "normal")
        check(cli, root, "staging_over_260", 235)
        check(cli, root, "final_over_260", 320)
        check(cli, root, "relative_over_260", 320, relative=True)
        check(cli, root, "extended_over_260", 320, extended=True)
        check(cli, root, "long_input", 320, long_input=True)
        check(cli, root, "zip_over_260", 320, kind="zip")
        junction_check(cli, root)
    print("Windows long paths, CRC cleanup, and junction rejection passed")


if __name__ == "__main__":
    main()
