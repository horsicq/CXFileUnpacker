"""LTEC relative DOS subpaths and strict path/codec rejection."""

import pathlib
import struct
import subprocess
import sys
import tempfile


def archive(name, symbol=65):
    # Independently encode a 12-literal block with constant pre, literal,
    # and position Huffman tables. The directory has one solid-block member.
    fields = ((0, 16), (12, 16), (0, 5), (0, 5),
              (0, 9), (symbol, 9), (0, 5), (0, 5))
    bits = "".join(f"{value:0{width}b}" for value, width in fields)
    bits += "0" * (-len(bits) % 8)
    payload = int(bits, 2).to_bytes(len(bits) // 8, "big")
    raw_name = name.encode("ascii") + b"\0"
    record = struct.pack("<HIII", 14 + len(raw_name), 0, 0, 12) + raw_name
    return b"LTEC\0" + struct.pack("<I", 9 + len(record)) + record + payload


def check(cli, root, label, name, expected, symbol=65):
    source, output = root / (label + ".lta"), root / (label + "_out")
    source.write_bytes(archive(name, symbol))
    result = subprocess.run([cli, "x", str(source), "-o" + str(output)],
                            capture_output=True, timeout=30)
    actual = {p.relative_to(output).as_posix(): p.read_bytes()
              for p in output.rglob("*") if p.is_file()}
    if actual != expected or (result.returncode == 0) != bool(expected):
        raise AssertionError((label, result.returncode, actual,
                              result.stdout, result.stderr))


def main():
    with tempfile.TemporaryDirectory(prefix="xfu-ltec-paths-") as temporary:
        root = pathlib.Path(temporary)
        check(sys.argv[1], root, "dos_path", "CSI\\HCP_UTIV.CS_",
              {"CSI/HCP_UTIV.CS_": b"A" * 12})
        check(sys.argv[1], root, "unix_path", "CSI/FILE.CS_",
              {"CSI/FILE.CS_": b"A" * 12})
        for label, name in (
                ("parent", "../escape.bin"),
                ("nested_parent", "CSI\\..\\escape.bin"),
                ("drive", "C:\\escape.bin"),
                ("absolute", "\\escape.bin"),
                ("empty_component", "CSI//escape.bin"),
                ("alias_parent", "CSI/.. /escape.bin")):
            check(sys.argv[1], root, label, name, {})
        check(sys.argv[1], root, "invalid_codec", "CSI/FILE.CS_", {}, 510)


if __name__ == "__main__":
    main()
