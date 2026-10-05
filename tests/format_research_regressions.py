#!/usr/bin/env python3
"""Independent fixtures for researched legacy archive variants.

Run: python format_research_regressions.py <xfu.exe>
"""
import argparse
from pathlib import Path
import struct
import tempfile
import zlib

from legacy_archives import run_case


def leb(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out + bytes([value]))


def ivt_leaf(name, offset, data, previous, following):
    entry = bytes([len(name)]) + name + leb(offset) + leb(len(data)) + b"\0"
    return (struct.pack("<HHII", 8192 - 12 - len(entry), 1, previous, following)
            + entry).ljust(8192, b"\0")


def ivt(two_levels=True):
    first, second = b"first", b"next"
    if two_levels:
        root_entry = b"\5B.txt" + struct.pack("<I", 2)
        root = (struct.pack("<HHI", 8192 - 8 - len(root_entry), 1, 0)
                + root_entry).ljust(8192, b"\0")
        pages = [ivt_leaf(b"A.txt", 8, first, 0xffffffff, 2), root,
                 ivt_leaf(b"B.txt", 13, second, 0, 0xffffffff)]
        root_id, last_id, levels, count = 1, 2, 2, 2
    else:
        pages = [ivt_leaf(b"A.txt", 8, first, 0xffffffff, 0xffffffff)]
        root_id, last_id, levels, count = 0, 0, 1, 1
    header = bytearray(48)
    struct.pack_into("<HHH", header, 0, 0x293b, 0x102, 8192)
    struct.pack_into("<III", header, 26, last_id, root_id, 0xffffffff)
    struct.pack_into("<IHI", header, 38, len(pages), levels, count)
    return ((struct.pack("<II", 0x01045f3f, 64) + first + second).ljust(64, b"\0")
            + header + b"".join(pages))


def hog2(payload=b"first\0second\n"):
    members = [(b"first.bin", payload[:6]), (b"second.bin", payload[6:])]
    header = b"HOG2" + struct.pack("<II", 2, 164) + b"\xff" * 56
    table = b"".join(name.ljust(36, b"\0") + struct.pack("<III", 0, len(data), 0)
                     for name, data in members)
    return header + table + payload


def bff_record(name, data, *, legacy=False, symlink=False, stale_size=0):
    fixed = 48 if legacy else 64
    header = bytearray(fixed)
    name_bytes = (name + b"\0").ljust((len(name) + 8) & ~7, b"\0")
    header[0] = (fixed + len(name_bytes)) // 8
    header[1] = 9 if legacy else 11
    struct.pack_into("<H", header, 2, 0xea6b)
    mode = 0xa1ff if symlink else 0x81a4
    if legacy:
        struct.pack_into("<H", header, 8, mode)
        struct.pack_into("<I", header, 16, len(data))
        struct.pack_into("<I", header, 40, stale_size or len(data))
    else:
        struct.pack_into("<I", header, 12, mode)
        struct.pack_into("<I", header, 24, len(data))
        struct.pack_into("<I", header, 56, stale_size or len(data))
    security = b"" if legacy or symlink else b"\0" * 40
    record = bytes(header) + name_bytes + security + data
    return record.ljust((len(record) + 7) & ~7, b"\0")


def bff(records):
    volume = struct.pack("<I", 0xea6b0009).ljust(72, b"\0")
    return (volume + b"".join(records) + b"\1\7\x6b\xea").ljust(1024, b"\0")


# Mark Adler's independent blast example, not xxfclib-generated compressed
# data: https://github.com/madler/zlib/blob/master/contrib/blast/blast.c
DCL_PACKED = bytes.fromhex("00048224258f807f")
DCL_PLAIN = b"AIAIAIAIAIAIA"


def fls(tag=0x21):
    data, name = b"SaveRam fixture\n", b"SAVE.TXT"
    names = b"\xff\xffSaveRam" + struct.pack("<I", 13) + bytes([len(name)]) + name
    header, record = bytearray(44), bytearray(44)
    header[:8] = bytes.fromhex("fe000000010000ff")
    struct.pack_into("<I", header, 23, len(names))
    record[:8] = bytes([0xfe, 0, 0, 0, 0, 1, tag, ord("A")])
    struct.pack_into("<IH", record, 8, 9, 1)
    struct.pack_into("<II", record, 19, 90 + len(names), len(data))
    struct.pack_into("<I", record, 31, len(data))
    return struct.pack("<H", 2) + header + record + names + data


def gst(*, alternate=True, compressed=True, flags=0):
    data = DCL_PACKED if compressed else DCL_PLAIN
    header = bytearray(32)
    header[:2] = b"\xea\xc9" if alternate else b"\xe9\xc8"
    header[6:8] = bytes([flags, int(compressed)])
    struct.pack_into("<II", header, 8, len(DCL_PLAIN), len(data))
    header[16:28] = b"GST.TXT".ljust(12, b"\0")
    struct.pack_into("<I", header, 28, zlib.crc32(DCL_PLAIN))
    return header + data


def snx(sentinel=True):
    header = bytearray(421)
    header[:32] = b"Second Nature Software Inc. SNX\0"
    struct.pack_into("<HHH", header, 0x160, 1, 640, 480)
    header[0x166:0x166 + 21] = b"DATA.BIN".ljust(13, b"\0") + struct.pack("<II", 421, 7)
    if sentinel:
        header[0x166 + 21:0x166 + 42] = b"\xff" * 21
        header[0x166 + 42:421] = b"MODULE.REF".ljust(13, b"\0") + b"\xff" * 8
    return bytes(value ^ 255 for value in header) + b"picture"


def crc16(data):
    result = 0
    for byte in data:
        result ^= byte
        for _ in range(8):
            result = (result >> 1) ^ (0xa001 if result & 1 else 0)
    return result


def povlab(name=b"IMAGE\\TOOLS.TXT"):
    data = b"relative DOS path\n"
    header = bytearray(27 + len(name))
    header[0] = len(header) - 2
    header[2:7] = b"-ARS-"
    struct.pack_into("<II", header, 7, len(data), len(data))
    header[20:22] = bytes([1, len(name)])
    header[22:22 + len(name)] = name
    struct.pack_into("<H", header, 22 + len(name), crc16(data))
    header[24 + len(name)] = ord("M")
    header[1] = sum(header[2:]) & 255
    return header + data + b"\0"


def qip(version=1, flags=0x20):
    record = bytearray(32 if version == 1 else 36)
    record[:2] = b"QD"
    struct.pack_into("<I", record, 4, len(DCL_PACKED))
    record[10] = flags
    plain_at = 15 if version == 1 else 19
    struct.pack_into("<I", record, plain_at, len(DCL_PLAIN))
    record[plain_at + 4:] = b"QIP.TXT".ljust(13, b"\0")
    return (b"QP" + struct.pack("<HIII", 1, 16, version, 0)
            + struct.pack("<I", 32) + b"QIP.TXT".ljust(12, b"\0")
            + record + DCL_PACKED)


def infogrames(gap=b"unused bytes", duplicate=False):
    parts = [b"indexed first\n" * 8, b"indexed second\n" * 9]
    records = []
    for data in parts:
        writer = zlib.compressobj(wbits=-15)
        packed = writer.compress(data) + writer.flush()
        records.append(struct.pack("<IIIBBH", 0, len(packed), len(data), 4, 0, 0) + packed)
    start = 16 if duplicate else 12
    second = start + len(records[0]) + len(gap)
    slots = [0, start, start, second] if duplicate else [0, start, second]
    return struct.pack("<" + str(len(slots)) + "I", *slots) + records[0] + gap + records[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="xfu-formats-") as temporary:
        folder = Path(temporary)
        run_case(args.executable, folder, "ivt-single-leaf", ivt(False), {"A.txt": b"first"})
        tree = ivt()
        run_case(args.executable, folder, "ivt-interleaved-index", tree,
                 {"A.txt": b"first", "B.txt": b"next"})
        root = 64 + 48 + 8192
        for label, offset, value in [
                ("ivt-cycle", root + 4, 1),
                ("ivt-child-outside", root + 4, 3),
                ("ivt-duplicate-child", root + 14, 0),
                ("ivt-wrong-leaf-link", 64 + 48 + 8, 1)]:
            broken = bytearray(tree)
            struct.pack_into("<I", broken, offset, value)
            run_case(args.executable, folder, label, broken)
        broken = bytearray(tree)
        broken[root + 9] = ord("C")
        run_case(args.executable, folder, "ivt-wrong-separator", broken)
        broken = bytearray(tree)
        struct.pack_into("<I", broken, 64 + 44, 3)
        run_case(args.executable, folder, "ivt-wrong-entry-total", broken)

        packed = hog2()
        expected = {"first.bin": b"first\0", "second.bin": b"second\n"}
        run_case(args.executable, folder, "hog2-normal", packed, expected)
        run_case(args.executable, folder, "hog2-identical-duplicate", packed + packed[164:], expected)
        wrong = bytearray(packed[164:])
        wrong[-1] ^= 1
        run_case(args.executable, folder, "hog2-different-duplicate", packed + wrong)
        run_case(args.executable, folder, "hog2-partial-duplicate", packed + packed[164:-1])
        run_case(args.executable, folder, "hog2-two-duplicates", packed + packed[164:] * 2)

        run_case(args.executable, folder, "bff-legacy-fs-name",
                 bff([bff_record(b"old.txt", b"legacy\n", legacy=True)]),
                 {"old.txt": b"legacy\n"})
        run_case(args.executable, folder, "bff-stale-symlink-size",
                 bff([bff_record(b"link", b"/usr/lib", symlink=True, stale_size=27),
                      bff_record(b"after.txt", b"after link\n")]),
                 {"link": b"/usr/lib", "after.txt": b"after link\n"})
        broken = bytearray(bff([bff_record(b"link", b"target", symlink=True)]))
        struct.pack_into("<I", broken, 72 + 24, 2000)
        run_case(args.executable, folder, "bff-symlink-outside", broken)
        run_case(args.executable, folder, "bff-legacy-unix-root",
                 bff([bff_record(b"/usr/bin/tool", b"rooted\n", legacy=True)]),
                 {"usr/bin/tool": b"rooted\n"})
        for name in (b"/../escape", b"//server/file", b"\\root", b"C:/file", b"/usr/../escape"):
            run_case(args.executable, folder, "bff-unsafe-" + name.hex(),
                     bff([bff_record(name, b"unsafe", legacy=True)]))

        run_case(args.executable, folder, "fls-attribute-21", fls(), {"SAVE.TXT": b"SaveRam fixture\n"})
        run_case(args.executable, folder, "fls-unknown-attribute", fls(0x22))
        run_case(args.executable, folder, "fls-truncated-21", fls()[:-1])

        for alternate in (False, True):
            for compressed in (False, True):
                label = "gst-" + ("eac9" if alternate else "e9c8") + ("-dcl" if compressed else "-stored")
                run_case(args.executable, folder, label, gst(alternate=alternate, compressed=compressed),
                         {"GST.TXT": DCL_PLAIN})
        broken = bytearray(gst())
        broken[28] ^= 1
        run_case(args.executable, folder, "gst-eac9-bad-crc", broken)
        broken = bytearray(gst())
        broken[0] = 0xeb
        run_case(args.executable, folder, "gst-unknown-magic", broken)
        run_case(args.executable, folder, "gst-unknown-flags", gst(flags=2))
        run_case(args.executable, folder, "gst-eac9-truncated", gst()[:-1])

        run_case(args.executable, folder, "snx-sentinel-slots", snx(), {"DATA.BIN": b"picture"})
        run_case(args.executable, folder, "snx-zero-slots", snx(False), {"DATA.BIN": b"picture"})
        broken = bytearray(snx())
        broken[0x166 + 21 + 13] = 1  # unmasked offset 0xfffffffe, size still 0xffffffff
        run_case(args.executable, folder, "snx-mismatched-sentinel", broken)
        broken = bytearray(snx())
        broken[0x166 + 42] = ord("/") ^ 255
        run_case(args.executable, folder, "snx-unsafe-sentinel-name", broken)
        run_case(args.executable, folder, "snx-payload-outside", snx()[:-1])

        run_case(args.executable, folder, "povlab-dos-subpath", povlab(), {"IMAGE/TOOLS.TXT": b"relative DOS path\n"})
        run_case(args.executable, folder, "povlab-posix-subpath", povlab(b"IMAGE/TOOLS.TXT"),
                 {"IMAGE/TOOLS.TXT": b"relative DOS path\n"})
        for name in (b"../BAD.TXT", b"IMAGE\\..\\BAD.TXT", b"/BAD.TXT", b"C:\\BAD.TXT",
                     b"IMAGE\\\\BAD.TXT", b"IMAGE\\.\\BAD.TXT", b"IMAGE\\"):
            run_case(args.executable, folder, "povlab-unsafe-" + name.hex(), povlab(name))
        broken = bytearray(povlab())
        broken[1] ^= 1
        run_case(args.executable, folder, "povlab-bad-header-checksum", broken)

        for version in (1, 2):
            run_case(args.executable, folder, "qip-indexed-version-" + str(version), qip(version),
                     {"QIP.TXT": DCL_PLAIN})
        run_case(args.executable, folder, "qip-v1-zero-flags", qip(flags=0), {"QIP.TXT": DCL_PLAIN})
        for label, offset, value in [("qip-unknown-version", 8, 3), ("qip-nonzero-reserved", 12, 1),
                                     ("qip-index-outside", 16, 400), ("qip-wrong-extent", 32 + 4, 999)]:
            broken = bytearray(qip())
            struct.pack_into("<I", broken, offset, value)
            run_case(args.executable, folder, label, broken)
        broken = bytearray(qip())
        broken[32 + 10] = 1
        run_case(args.executable, folder, "qip-v1-unknown-flags", broken)
        run_case(args.executable, folder, "qip-v1-trailing-data", qip() + b"junk")
        run_case(args.executable, folder, "qip-v1-v2-descriptor-mismatch", qip(2)[:8] + struct.pack("<I", 1) + qip(2)[12:])

        expected = {"00000.bin": b"indexed first\n" * 8, "00001.bin": b"indexed second\n" * 9}
        run_case(args.executable, folder, "infogrames-contiguous", infogrames(b""), expected)
        run_case(args.executable, folder, "infogrames-indexed-gap", infogrames(), expected)
        run_case(args.executable, folder, "infogrames-indexed-duplicate-slot", infogrames(duplicate=True),
                 {"00000.bin": expected["00000.bin"], "00002.bin": expected["00001.bin"]})
        broken = bytearray(infogrames())
        struct.pack_into("<I", broken, 8, 29)
        run_case(args.executable, folder, "infogrames-indexed-overlap", broken)
        run_case(args.executable, folder, "infogrames-indexed-truncation", infogrames()[:-1])
        run_case(args.executable, folder, "infogrames-indexed-unbounded-gap", infogrames(b"x" * 17))
        run_case(args.executable, folder, "infogrames-indexed-suffix", infogrames() + b"x")
        broken = bytearray(infogrames())
        second = struct.unpack_from("<I", broken, 8)[0]
        broken[second + 16] = 7  # reserved DEFLATE block type in second stream
        run_case(args.executable, folder, "infogrames-indexed-second-codec-invalid", broken)
    print("Format research regressions passed")


if __name__ == "__main__":
    main()
