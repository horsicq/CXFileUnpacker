"""BVRP name trailers/stored members and DMS verified-track salvage."""

import pathlib
import struct
import subprocess
import sys
import tempfile


def crc16(data):
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 if value & 1 else 0)
    return value


def bits(*fields):
    text = "".join(f"{value:0{width}b}" for value, width in fields)
    text += "0" * (-len(text) % 8)
    return int(text, 2).to_bytes(len(text) // 8, "big")


def lh1_literal(symbol):
    # Stock LH1 initial tree, before any adaptive update. This creates an
    # independently encoded one-literal stream rather than copying output.
    count, total = 314, 627
    parent, child = [0] * (total + count), [0] * total
    for i in range(count):
        child[i] = i + total
        parent[i + total] = i
    source = 0
    for node in range(count, total):
        child[node] = source
        parent[source] = parent[source + 1] = node
        source += 2
    node, code = parent[symbol + total], []
    while node != total - 1:
        ancestor = parent[node]
        code.append(int(child[ancestor] != node))
        node = ancestor
    return bits(*[(bit, 1) for bit in reversed(code)])


def bvrp(corrupt=False):
    header = bytearray(128)
    header[:23] = b"PAC - (c) BVRP Software"
    header[0x4C:0x50] = b"\0\r\n\x1a"
    struct.pack_into("<H", header, 0x50, 0xA9D6)
    struct.pack_into("<I", header, 0x5C, len(header))
    struct.pack_into("<H", header, 0x60, 2)
    archive = header
    for name, method, plain, packed in (
        (b"first.txt", 1, b"A", lh1_literal(65) + b"first.txt\0"),
        (b"stored.txt", 0, b"Stored\r\n", b"Stored\r\n"),
    ):
        entry = bytearray(32)
        entry[:len(name)] = name
        entry[18] = method
        struct.pack_into("<I", entry, 19, len(archive) + 32 + len(packed))
        struct.pack_into("<I", entry, 23, len(plain))
        struct.pack_into("<H", entry, 27, crc16(plain) ^ int(corrupt))
        archive += entry + packed
    return archive


def dms(bad_packed_crc=False, bad_second_sum=False):
    # Two HEAVY2+RLE tracks share a one-symbol Huffman table. Track zero
    # has an invalid plaintext checksum despite intact compressed bytes;
    # track one must still be decoded and independently verified.
    size, symbol = 11264, 65
    header = bytearray(56)
    header[:4] = b"DMS!"
    struct.pack_into(">HHII", header, 16, 0, 1, 8, size * 2)
    struct.pack_into(">H", header, 50, 6)
    struct.pack_into(">H", header, 54, crc16(header[4:54]))
    archive = header
    for number, flags, packed in (
        (0, 7, bits((0, 9), (symbol, 9), (0, 5), (0, 5))),
        (1, 5, b"\0"),
    ):
        entry = bytearray(20)
        entry[:2] = b"TR"
        struct.pack_into(">H", entry, 2, number)
        struct.pack_into(">HHH", entry, 6, len(packed), size, size)
        entry[12:14] = bytes((flags, 6))
        checksum = (size * symbol + int(number == 0 or bad_second_sum)) & 0xFFFF
        struct.pack_into(">HH", entry, 14, checksum,
                         crc16(packed) ^ int(number == 0 and bad_packed_crc))
        struct.pack_into(">H", entry, 18, crc16(entry[:18]))
        archive += entry + packed
    return archive


def extract(cli, root, name, data, expected, exit_code):
    source, output = root / name, root / (name + "_output")
    source.write_bytes(data)
    result = subprocess.run([cli, "x", str(source), "-o" + str(output)],
                            capture_output=True, timeout=30)
    if result.returncode != exit_code:
        raise AssertionError((name, result.returncode, result.stdout, result.stderr))
    actual = {str(p.relative_to(output)).replace("\\", "/"): p.read_bytes()
              for p in output.rglob("*") if p.is_file()}
    if actual != expected:
        raise AssertionError((name, {k: len(v) for k, v in actual.items()},
                              {k: len(v) for k, v in expected.items()}))


def main():
    with tempfile.TemporaryDirectory(prefix="xfu-reader-compat-") as temporary:
        root = pathlib.Path(temporary)
        extract(sys.argv[1], root, "trailers.pac", bvrp(),
                {"first.txt": b"A", "stored.txt": b"Stored\r\n"}, 0)
        extract(sys.argv[1], root, "bad-checksum.pac", bvrp(True), {}, 1)
        extract(sys.argv[1], root, "salvage.dms", dms(),
                {"track_00001": b"A" * 11264}, 1)
        extract(sys.argv[1], root, "bad-packed-crc.dms", dms(True), {}, 1)
        extract(sys.argv[1], root, "bad-second-sum.dms", dms(False, True), {}, 1)
    print("BVRP compatibility and DMS track salvage passed")


if __name__ == "__main__":
    main()
