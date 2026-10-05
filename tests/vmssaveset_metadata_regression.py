"""Independent BACKUP fixtures for metadata, header-only files, strict bodies."""
import argparse
from pathlib import Path
import struct
import subprocess
import tempfile


BLOCK_SIZE = 1024
HEADER_SIZE = 256


def record(kind, body=b"", spare=0, declared=None):
    size = len(body) if declared is None else declared
    return struct.pack("<HHIII", size, kind, 0, 0, spare) + body


def attribute(tag, body):
    return struct.pack("<HH", len(body), tag) + body


def file_attributes(size, name=b"PAYLOAD.TXT", characteristics=0, file_id=None,
                    extra=b""):
    fat = bytearray(32)
    fat[:2] = b"\1\0"  # Fixed bytes, without variable-record conversion.
    struct.pack_into("<HHH", fat, 8, 0, size // 512 + 1, size % 512)
    attributes = b"\1\1" + attribute(0x2a, name)
    if file_id is not None:
        attributes += attribute(0x2c, struct.pack("<3H", *file_id))
    attributes += (attribute(0x33, struct.pack("<I", characteristics)) +
                   attribute(0x34, bytes(fat)) + extra)
    return record(3, attributes)


def file_records(payload):
    return file_attributes(len(payload)) + record(4, payload)


def block(records, application=1, sequence=1, block_size=BLOCK_SIZE, pad=True):
    header = bytearray(HEADER_SIZE)
    struct.pack_into("<4H", header, 0, HEADER_SIZE, 0x400, 1, application)
    struct.pack_into("<I", header, 8, sequence)
    struct.pack_into("<I", header, 32, 0x10101)
    struct.pack_into("<I", header, 40, block_size)
    if pad:
        remaining = block_size - HEADER_SIZE - len(records)
        assert remaining >= 16
        records += record(0, b"\0" * (remaining - 16))
    return bytes(header) + records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unpacker", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    if args.root:
        args.root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vmssaveset-metadata-", dir=args.root) as temporary:
        run_cases(args, Path(temporary))


def run_cases(args, root):
    payload = b"Independent VMS metadata regression payload.\n"
    files = file_records(payload)
    volume = record(2, b"\1\1" + attribute(0x15, b"OFFLINE_VOLUME"))
    fid = record(7, b"\1\1" + attribute(1, struct.pack("<3H", 1, 1, 0)))
    summary = record(1, b"\1\1" + attribute(1, b"OFFLINE.BCK"))
    cases = {
        "old-file-only.bck": (block(files), True),
        "volume.bck": (block(volume + files), True),
        "fid.bck": (block(fid + files), True),
        "volume-and-fid.bck": (block(summary + volume + fid + fid + files), True),
        "metadata-in-prior-block.bck": (block(volume + fid) + block(files, sequence=2), True),
        # Filler application2 has opaque bytes, including apparent bad records.
        "metadata-after-filler.bck": (block(volume + fid) +
                                       block(b"\xff" * 768, application=2, sequence=2, pad=False) +
                                       block(files, sequence=3), True),
        "final-opaque-filler.bck": (block(volume + fid + files) +
                                    block(b"\xff" * 768, application=2, sequence=2, pad=False), True),
        "unknown-type.bck": (block(record(8, b"unknown") + files), False),
        "unhandled-physical-volume.bck": (block(record(5, b"unknown") + files), False),
        "volume-nonzero-spare.bck": (block(record(2, b"metadata", spare=1) + files), False),
        "fid-nonzero-spare.bck": (block(record(7, b"metadata", spare=1) + files), False),
        # A metadata record cannot borrow bytes from the next physical block.
        "volume-block-overrun.bck": (block(record(2, b"\0" * 752, declared=768), pad=False) +
                                     block(files, sequence=2), False),
        "fid-block-overrun.bck": (block(record(7, b"\0" * 752, declared=768), pad=False) +
                                  block(files, sequence=2), False),
        "volume-eof-overrun.bck": (block(record(2, b"short", declared=768), pad=False), False),
        "fid-truncated-header.bck": (block(record(7, b"metadata")[:10], pad=False), False),
        # A decoded prefix must never turn a later unsupported/incomplete
        # member or malformed record into successful partial extraction.
        "unknown-after-valid-file.bck": (block(files + record(8, b"unknown")), False),
        "metadata-only-system-file.bck": (block(file_attributes(0, b"BACKUP.SYS") +
                                               file_attributes(1536, b"BADBLK.SYS") +
                                               file_attributes(0, b"BADLOG.SYS")), False),
        "missing-body-after-valid-file.bck": (block(files + file_attributes(1024, b"MISSING.TXT") +
                                                  record(4, b"short")), False),
        "invalid-final-block-after-file.bck": (block(files) + b"\0" * HEADER_SIZE, False),
        "partial-final-header-after-file.bck": (block(files) + b"\0" * 10, False),
    }
    header_only = file_attributes(1536, b"[000000]BADBLK.SYS;1", file_id=(3, 3, 1))
    no_backup = file_attributes(1024, b"PAGEFILE.SYS;1", characteristics=2)
    for number, name in ((1, b"INDEXF"), (2, b"BITMAP"), (3, b"BADBLK"), (9, b"BADLOG")):
        cases[f"reserved-header-{number}.bck"] = (
            block(file_attributes(1536, b"[000000]" + name + b".SYS;1",
                                  file_id=(number, number, 1)) + files), True)
    cases.update({
        "nobackup-header-only.bck": (block(no_backup + files), True),
        "header-only-after-complete-file.bck": (block(files + header_only + no_backup), True),
        "header-only-across-filler.bck": (
            block(header_only) + block(b"\xff" * 768, application=2, sequence=2, pad=False) +
            block(files, sequence=3), True),
        "reserved-name-wrong-fid.bck": (
            block(file_attributes(1536, b"[000000]BADBLK.SYS;1", file_id=(100, 3, 1)) + files), False),
        "reserved-name-wrong-sequence.bck": (
            block(file_attributes(1536, b"[000000]BADBLK.SYS;1", file_id=(3, 4, 1)) + files), False),
        "reserved-name-zero-volume.bck": (
            block(file_attributes(1536, b"[000000]BADBLK.SYS;1", file_id=(3, 3, 0)) + files), False),
        "reserved-fid-wrong-name.bck": (
            block(file_attributes(1536, b"ORDINARY.TXT", file_id=(3, 3, 1)) + files), False),
        "reserved-fid-wrong-directory.bck": (
            block(file_attributes(1536, b"[USER]BADBLK.SYS;1", file_id=(3, 3, 1)) + files), False),
        "reserved-name-missing-fid.bck": (
            block(file_attributes(1536, b"[000000]BADBLK.SYS;1") + files), False),
        "reserved-partial-body.bck": (block(header_only + record(4, b"short") + files), False),
        "nobackup-partial-body.bck": (block(no_backup + record(4, b"short") + files), False),
        # Ancillary metadata must not hide an unexpected body from the
        # header-only test. This ordering remains unsupported, not omitted.
        "nobackup-fid-then-partial-body.bck": (
            block(no_backup + fid + record(4, b"short") + files), False),
        "reserved-fid-then-full-body.bck": (
            block(header_only + fid + record(4, b"x" * 1536), block_size=4096), False),
        "nobackup-final-block-truncated.bck": (block(files + no_backup) + b"\0" * 10, False),
        "ordinary-missing-body-before-next-file.bck": (
            block(file_attributes(1536, b"ORDINARY.TXT") + files), False),
        "duplicate-nobackup-characteristics.bck": (
            block(file_attributes(1024, characteristics=0, extra=attribute(0x33, struct.pack("<I", 2))) + files), False),
        "duplicate-reserved-fid.bck": (
            block(file_attributes(1024, b"[000000]BADBLK.SYS;1", file_id=(100, 1, 1),
                                  extra=attribute(0x2c, struct.pack("<3H", 3, 3, 1))) + files), False),
        "attribute-length-overrun.bck": (
            block(record(3, b"\1\1" + struct.pack("<HH", 6, 0x2c) + b"\3\0\3\0") + files), False),
    })
    reserved_data = b"Actual saved reserved file bytes."
    overridden_data = b"Data saved by /IGNORE=NOBACKUP."
    extra_outputs = {
        "reserved-with-real-body.bck": {"[000000]BADBLK.SYS;1": reserved_data},
        "nobackup-with-real-body.bck": {"PAGEFILE.SYS;1": overridden_data},
    }
    cases["reserved-with-real-body.bck"] = (
        block(file_attributes(len(reserved_data), b"[000000]BADBLK.SYS;1", file_id=(3, 3, 1)) +
              record(4, reserved_data) + files), True)
    cases["nobackup-with-real-body.bck"] = (
        block(file_attributes(len(overridden_data), b"PAGEFILE.SYS;1", characteristics=2) +
              record(4, overridden_data) + files), True)
    for name, (data, valid) in cases.items():
        source = root / name
        source.write_bytes(data)
        probe = subprocess.run([str(args.probe.resolve()), str(source.resolve()), "vmssaveset"],
                               capture_output=True, text=True, timeout=30)
        actual = "vmssaveset type=VMSSaveset valid=1 parsed=1" in probe.stdout
        if probe.returncode or actual != valid:
            raise AssertionError(f"{name}: reader validity differs\n{probe.stdout}\n{probe.stderr}")
        output = root / (name + "-output")
        result = subprocess.run([str(args.unpacker.resolve()), "x", str(source.resolve()),
                                 "-o" + str(output.resolve())],
                                capture_output=True, text=True, timeout=30)
        files_out = [p for p in output.rglob("*") if p.is_file()] if output.exists() else []
        if valid:
            expected = {"PAYLOAD.TXT": payload, **extra_outputs.get(name, {})}
            actual_files = {str(p.relative_to(output)): p.read_bytes() for p in files_out}
            if result.returncode or actual_files != expected:
                raise AssertionError(f"{name}: extracted bytes differ\n{result.stdout}\n{result.stderr}")
        elif result.returncode == 0 or files_out:
            raise AssertionError(f"{name}: invalid archive produced success or files")
    print(f"VMS metadata regression: {len(cases)} cases passed")


if __name__ == "__main__":
    main()
