"""Independent LDM variable-record length and component completeness controls.

Wire facts: Linux block/partitions/ldm.h and ldm.c. No upstream implementation
is imported. The probe borrows RAM input and runs TEST in a memory-only scope.
"""
import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path

DISK_UUID = "12345678-1234-5678-9abc-123456789abc"
CONFIG = 64 * 512
VMDB = CONFIG + 17 * 512
FRAME_START = VMDB + 512
PAYLOAD = b"L" * 1024 + b"D" * 512


def number(value):
    body = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    return bytes([len(body)]) + body


def string(value):
    body = value.encode("ascii")
    assert len(body) <= 255
    return bytes([len(body)]) + body


def opaque(value):
    assert len(value) <= 255
    return bytes([len(value)]) + value


def place(buf, at, body):
    assert 0 <= at <= len(buf) and len(body) <= len(buf) - at
    buf[at:at + len(body)] = body


def record(kind, identity, name, flags=0, capacity=128):
    buf = bytearray(capacity)
    place(buf, 0, b"VBLK")
    struct.pack_into(">IHH", buf, 8, identity, 0, 1)
    buf[18], buf[19] = flags, kind
    fields = number(identity) + string(name)
    place(buf, 24, fields)
    return buf, len(fields)


def declare(buf, length):
    struct.pack_into(">I", buf, 20, length)
    return bytes(buf)


def disk(version=3, long=False, opaque_alt=False):
    buf, width = record(0x34 if version == 3 else 0x44, 1,
                        "disk" * 15 if long else "disk", capacity=240 if long else 128)
    if version == 3:
        extra = string(DISK_UUID) + (opaque(b"\x00\xff\x80A\x01B") if opaque_alt else string("alternate" * 10 if long else "disk"))
        place(buf, 24 + width, extra)
        return declare(buf, 12 + width + len(extra))
    place(buf, 24 + width, bytes.fromhex(DISK_UUID.replace("-", "")))
    return declare(buf, 45 + width)


def component(children=2):
    buf, width = record(0x32, 3, "component")
    state = string("ACTIVE")
    place(buf, 24 + width, state)
    width += len(state)
    buf[24 + width] = 2  # Basic single-disk/spanned component.
    child = number(children)
    place(buf, 29 + width, child)
    width += len(child)
    parent = number(2)
    place(buf, 45 + width, parent)
    width += len(parent)
    return declare(buf, 22 + width)


def partition(identity, start, logical, size, indexed=False):
    buf, width = record(0x33, identity, "part", 8 if indexed else 0)
    struct.pack_into(">QQ", buf, 36 + width, start, logical)
    extra = number(size) + number(3) + number(1)
    if indexed:
        extra += number(identity)
    place(buf, 52 + width, extra)
    return declare(buf, 28 + width + len(extra))


def volume(flags=0, size=3, opaque_ids=False):
    buf, width = record(0x51, 2, "data", flags)
    extra = string("gen") + string("")
    place(buf, 24 + width, extra)
    width += len(extra)
    child = number(1)
    place(buf, 45 + width, child)
    width += len(child)
    length = number(size)
    place(buf, 61 + width, length)
    width += len(length)
    buf[65 + width] = 7
    place(buf, 66 + width, bytes(range(16)))
    extra = b""
    if flags & 8:
        extra += opaque(b"\x00\xff\x80A\x01B") if opaque_ids else string("id-one")
    if flags & 32:
        extra += opaque(b"\xfe\x00\x81C\x02D") if opaque_ids else string("id-two")
    if flags & 128:
        extra += number(size)
    if flags & 2:
        extra += opaque(b"\xff:\x00") if opaque_ids else string("D:")
    place(buf, 82 + width, extra)
    return declare(buf, 58 + width + len(extra))


def disk_group(version, optional=False, opaque_ids=False):
    buf, width = record(0x35 if version == 3 else 0x45, 10,
                        "group", 8 if optional else 0)
    if version == 3:
        identifier = string(DISK_UUID)
        place(buf, 24 + width, identifier)
        width += len(identifier)
    if optional:
        extra = opaque(b"\x00\xff\x80A\x01B") + opaque(b"\xfe\x00\x81C\x02D") if opaque_ids else string("id-one") + string("id-two")
        place(buf, (36 if version == 3 else 68) + width, extra)
        width += len(extra)
    return declare(buf, (12 if version == 3 else 44) + width)


def frames(records, fragment_disk=False, reverse_fragments=False):
    result = []
    for data in records:
        if len(data) <= 128:
            result.append(data)
            continue
        assert fragment_disk and len(data) == 240
        pieces = []
        for piece in range(2):
            buf = bytearray(128)
            place(buf, 0, b"VBLK")
            struct.pack_into(">IHH", buf, 8, 100, piece, 2)
            place(buf, 16, data[16 + piece * 112:16 + (piece + 1) * 112])
            pieces.append(bytes(buf))
        result.extend(reversed(pieces) if reverse_fragments else pieces)
    return result


def image(records):
    buf = bytearray(96 * 512)
    place(buf, 3072, b"PRIVHEAD")
    struct.pack_into(">HH", buf, 3084, 2, 12)
    place(buf, 3120, DISK_UUID.encode("ascii"))
    struct.pack_into(">QQQQ", buf, 3355, 16, 32, 64, 32)
    toc = bytearray(512)
    place(toc, 0, b"TOCBLOCK")
    place(toc, 36, b"config\0")
    struct.pack_into(">QQ", toc, 46, 17, 14)
    place(toc, 70, b"log\0")
    struct.pack_into(">QQ", toc, 80, 31, 1)
    place(buf, CONFIG + 512, toc)
    place(buf, CONFIG + 1024, toc)
    place(buf, VMDB, b"VMDB")
    struct.pack_into(">IIIHHH", buf, VMDB + 4, 4 + len(records), 128, 512, 1, 4, 10)
    for i, data in enumerate(records):
        assert len(data) == 128
        place(buf, FRAME_START + i * 128, data)
    place(buf, 24 * 512, PAYLOAD[:1024])
    place(buf, 18 * 512, PAYLOAD[1024:])
    return buf


def base_records(version=3, children=2, flags=0, indexed=False, size=3, long=False):
    return [disk(version, long), component(children), volume(flags, size),
            partition(4, 8, 0, 2, indexed), partition(5, 2, 2, 1, indexed)]


def cases():
    result = []

    def add(name, records=None, good=True, mutate=None):
        data = image(frames(records if records is not None else base_records(),
                            fragment_disk=records is not None and len(records[0]) > 128))
        if mutate:
            mutate(data)
        result.append((name, bytes(data), good))

    add("disk3-basic")
    add("disk4-basic", base_records(version=4))
    records = base_records()
    records[0] = disk(opaque_alt=True)
    add("disk3-opaque-alternate", records)
    add("partition-index", base_records(indexed=True))
    for flags in (8, 32, 128, 2, 8 | 32 | 128 | 2):
        add("volume-option-%02x" % flags, base_records(flags=flags))
    records = base_records()
    records[2] = volume(flags=8 | 32 | 128 | 2, opaque_ids=True)
    add("volume-opaque-identifiers", records)
    for version in (3, 4):
        for optional in (False, True):
            add("disk-group-%d-%s" % (version, optional),
                base_records() + [disk_group(version, optional)])
        add("disk-group-%d-opaque-identifiers" % version,
            base_records() + [disk_group(version, True, opaque_ids=True)])
    add("fragmented-disk3", base_records(long=True))
    reversed_parts = base_records()
    reversed_parts[3], reversed_parts[4] = reversed_parts[4], reversed_parts[3]
    add("physical-record-order", reversed_parts)
    add("partition-extension-length", mutate=lambda b: struct.pack_into(">I", b, FRAME_START + 3 * 128 + 20,
                                                                          struct.unpack_from(">I", b, FRAME_START + 3 * 128 + 20)[0] + 1))
    add("volume-extension-length", mutate=lambda b: struct.pack_into(">I", b, FRAME_START + 2 * 128 + 20,
                                                                       struct.unpack_from(">I", b, FRAME_START + 2 * 128 + 20)[0] + 1))
    # Each active known object must have a valid declared static+variable size.
    for slot, name in enumerate(("disk", "component", "volume", "partition", "partition-two")):
        for mode in ("zero", "short", "oversized"):
            def mutate(buf, slot=slot, mode=mode):
                at = FRAME_START + slot * 128 + 20
                value = struct.unpack_from(">I", buf, at)[0]
                struct.pack_into(">I", buf, at, {"zero": 0, "short": value - 1, "oversized": 129}[mode])
            add("%s-length-%s" % (name, mode), good=False, mutate=mutate)
    for slot, name in ((0, "disk"), (1, "component")):
        add(name + "-nonexact-length", good=False,
            mutate=lambda b, slot=slot: struct.pack_into(">I", b, FRAME_START + slot * 128 + 20,
                                                       struct.unpack_from(">I", b, FRAME_START + slot * 128 + 20)[0] + 1))
    for version in (3, 4):
        records = base_records(version=4 if version == 4 else 3)
        if version == 4:
            add("disk4-length-short", records, good=False,
                mutate=lambda b: struct.pack_into(">I", b, FRAME_START + 20,
                                                 struct.unpack_from(">I", b, FRAME_START + 20)[0] - 1))
        for optional in (False, True):
            records = base_records() + [disk_group(version, optional)]
            add("disk-group-%d-%s-bad-length" % (version, optional), records, good=False,
                mutate=lambda b: struct.pack_into(">I", b, FRAME_START + 5 * 128 + 20,
                                                 struct.unpack_from(">I", b, FRAME_START + 5 * 128 + 20)[0] + 1))
    for count in (0, 1, 3, 16385):
        add("children-%d" % count, base_records(children=count), good=False)
    records = base_records(size=2)
    records[4] = partition(5, 2, 3, 1)
    add("logical-gap-prefix-matches-volume", records, good=False)
    records = base_records(size=2)
    records[4] = partition(5, 2, 2, 0)
    add("zero-length-unconsumed-child", records, good=False)
    records = base_records(children=3) + [partition(6, 4, 99, 1)]
    add("extra-child-beyond-volume", records, good=False)
    records = base_records()
    records[4] = partition(5, 2, 0, 1)
    add("duplicate-logical-offset", records, good=False)
    orphan = bytearray(128)
    place(orphan, 0, b"VBLK")
    struct.pack_into(">IHH", orphan, 8, 999, 1, 2)
    add("orphan-continuation", base_records() + [bytes(orphan)], good=False)
    fragmented = frames(base_records(long=True), fragment_disk=True)
    # Reordered continuation remains valid; missing or duplicate pieces fail.
    for name, data, good in (("continuation-before-root", fragmented[1:2] + fragmented[:1] + fragmented[2:], True),
                             ("missing-continuation", fragmented[:1] + fragmented[2:], False),
                             ("duplicate-continuation", fragmented + fragmented[1:2], False)):
        result.append((name, bytes(image(data)), good))
    add("unaligned-vmdb", good=False,
        mutate=lambda b: struct.pack_into(">I", b, VMDB + 12, 7679))
    add("frame-domain-out-of-bounds", good=False,
        mutate=lambda b: struct.pack_into(">I", b, VMDB + 4, 61))
    return result


def execute(probe, root):
    root.mkdir(parents=True, exist_ok=True)
    checks = []
    for name, data, valid in cases():
        source = root / (name + ".img")
        source.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        before = source.stat()
        run = subprocess.run([str(probe), "t", "2582", str(source)],
                             capture_output=True, text=True, timeout=30)
        good = (run.returncode == 0) == valid
        item = {"case": name, "expected_valid": valid, "passed": good,
                "returncode": run.returncode, "source_sha256": digest}
        if not good:
            item.update(stdout=run.stdout, stderr=run.stderr)
        if valid and good:
            output = root / (name + "-output")
            output.mkdir(exist_ok=True)
            run = subprocess.run([str(probe), "x", "2582", str(source), str(output)],
                                 capture_output=True, text=True, timeout=30)
            member = output / "0000-data.img"
            item["exact_plaintext"] = run.returncode == 0 and member.is_file() and member.read_bytes() == PAYLOAD
            item["passed"] &= item["exact_plaintext"]
        item["source_unchanged"] = source.stat().st_mtime_ns == before.st_mtime_ns and source.read_bytes() == data
        item["passed"] &= item["source_unchanged"]
        checks.append(item)
    report = {"probe_sha256": hashlib.sha256(probe.read_bytes()).hexdigest(), "cases": checks,
              "count": len(checks), "passed": sum(row["passed"] for row in checks),
              "source": "https://github.com/torvalds/linux/blob/master/block/partitions/ldm.h"}
    (root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    failed = [row["case"] for row in checks if not row["passed"]]
    if failed:
        raise AssertionError("Failed LDM controls: " + ", ".join(failed))
    print("PASS: %d independent LDM controls; exact spanned bytes and unchanged sources" % len(checks))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    if args.root:
        execute(args.probe, args.root)
    else:
        with tempfile.TemporaryDirectory(prefix="xfu-ldm-records-") as directory:
            execute(args.probe, Path(directory))


if __name__ == "__main__":
    main()
