"""Create deterministic, independently parseable unpack-handle API fixtures."""

import gzip
import io
from pathlib import Path
import struct
import sys
import tarfile
import zipfile
import zlib


def put16(data, at, value):
    struct.pack_into("<H", data, at, value)


def put32(data, at, value):
    struct.pack_into("<I", data, at, value)


def pe32():
    data = bytearray(1024)
    data[:2] = b"MZ"
    put16(data, 4, 2)
    put16(data, 8, 4)
    put16(data, 0x18, 0x40)
    put32(data, 0x3C, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 132, 0x14C, 1, 0, 0, 0, 224, 0x102)
    optional = 152
    put16(data, optional, 0x10B)
    put32(data, optional + 4, 512)
    put32(data, optional + 16, 0x1000)
    put32(data, optional + 20, 0x1000)
    put32(data, optional + 28, 0x400000)
    put32(data, optional + 32, 0x1000)
    put32(data, optional + 36, 512)
    put16(data, optional + 40, 4)
    put16(data, optional + 48, 4)
    put32(data, optional + 56, 0x2000)
    put32(data, optional + 60, 512)
    put16(data, optional + 68, 3)
    for offset, value in ((72, 0x100000), (76, 0x1000),
                          (80, 0x100000), (84, 0x1000), (92, 16)):
        put32(data, optional + offset, value)
    section = optional + 224
    data[section:section + 8] = b".text\0\0\0"
    struct.pack_into("<IIIIIIHHI", data, section + 8,
                     1, 0x1000, 512, 512, 0, 0, 0, 0, 0x60000020)
    data[512] = 0xC3
    return bytes(data)


def term_overlay():
    """The narrow, zero-page-count overlay header used by TERM 90/95."""
    data = bytearray(32)
    data[:2] = b"MZ"
    put16(data, 8, 2)
    put16(data, 0x18, 28)
    put16(data, 0x1A, 1)
    return bytes(data) + b"opaque TERM overlay payload\0\xff\x11"


def v7_tar():
    payload = b"headerless tar member\n"
    header = bytearray(512)
    header[:7] = b"v7.txt\0"
    for at, value in ((100, b"0000644\0"), (108, b"0000000\0"),
                      (116, b"0000000\0"), (124, ("%011o\0" % len(payload)).encode()),
                      (136, b"00000000000\0")):
        header[at:at + len(value)] = value
    header[148:156] = b"        "
    header[156] = ord("0")
    header[148:156] = ("%06o\0 " % sum(header)).encode()
    result = bytes(header) + payload + bytes((-len(payload)) % 512) + bytes(1024)
    assert result[257:263] == bytes(6)
    with tarfile.open(fileobj=io.BytesIO(result)) as archive:
        assert archive.extractfile("v7.txt").read() == payload
    return result


def png_chunk(tag, payload):
    return (struct.pack(">I", len(payload)) + tag + payload +
            struct.pack(">I", zlib.crc32(tag + payload)))


def main(destination):
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    (root / "overlay-extracted").mkdir(exist_ok=True)
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w:", format=tarfile.USTAR_FORMAT) as archive:
        for name, payload in (("first.txt", b"first member\n"), ("second.txt", b"second member\n")):
            entry = tarfile.TarInfo(name)
            entry.size = len(payload)
            entry.mode = 0o644
            archive.addfile(entry, io.BytesIO(payload))
    tar_data = tar_stream.getvalue()
    gzip_data = gzip.compress(tar_data, mtime=0)
    zip_stream = io.BytesIO()
    with zipfile.ZipFile(zip_stream, "w", compression=zipfile.ZIP_STORED) as archive:
        entry = zipfile.ZipInfo("payload.txt", (1980, 1, 1, 0, 0, 0))
        entry.create_system = 3
        entry.external_attr = 0o100644 << 16
        archive.writestr(entry, b"zip member\n")
    zip_data = zip_stream.getvalue()
    prefixed_zip = b"opaque non-executable prefix\0" + bytes(range(1, 32)) + zip_data
    image = (b"\x89PNG\r\n\x1a\n" +
             png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)) +
             png_chunk(b"IDAT", zlib.compress(b"\0\xff\0\0\xff")) + png_chunk(b"IEND", b""))
    dos = bytearray(512)
    dos[:2] = b"MZ"
    put16(dos, 4, 1)
    put16(dos, 8, 4)
    put16(dos, 0x18, 0x40)
    dos[64] = 0xC3
    ne = bytearray(dos)
    put32(ne, 0x3C, 64)
    ne[64:66] = b"NE"
    put16(ne, 64 + 28, 1)  # One segment, table immediately after the NE header.
    put16(ne, 64 + 34, 64)
    put16(ne, 64 + 50, 4)
    struct.pack_into("<HHHH", ne, 128, 16, 128, 0, 128)
    ne[256:384] = bytes(range(128))
    invalid_ne = bytearray(ne)
    put16(invalid_ne, 128, 0xFFFF)  # Segment start lies outside the image.
    com = b"\xe9\x01\0\xc3" + bytes(124)
    executable = pe32()
    invalid_pe = bytearray(executable)
    put16(invalid_pe, 152, 0xFFFF)  # PE signature alone does not authenticate the carrier.
    # These are executable images stored consecutively, not an archive found by
    # scanning for an MZ marker. Every positive boundary is declared by the
    # preceding image, and the expected extracted bytes are the original bytes.
    overlay_tail = b"unparsed executable overlay tail\0\xff\x87"
    overlay_chain = executable + bytes(dos) + bytes(511) + executable + overlay_tail
    hidden_image = bytearray(2048)
    hidden_image[:512] = dos
    put16(hidden_image, 4, 4)  # Declared outer end is 2048, not internal MZ at 512.
    hidden_image[512:1536] = executable
    oversized_pe = bytearray(executable)
    put32(oversized_pe, 376 + 16, 0xFFFFFFFF)  # Section raw size cannot fit.
    put32(oversized_pe, 376 + 20, 0xFFFFFFF0)
    invalid_dos = bytearray(dos)
    put16(invalid_dos, 8, 0xFFFF)  # Header exceeds declared executable size.
    term = term_overlay()
    invalid_term_number = bytearray(term)
    put16(invalid_term_number, 0x1A, 0)
    invalid_term_header = bytearray(term)
    put16(invalid_term_header, 8, 4)
    # Auxiliary PE data uses physical file ranges outside the section table.
    # Each such range still belongs to the host, so its bytes must be skipped
    # before considering the immediately following executable as an overlay.
    pe_certificate = bytearray(executable)
    put32(pe_certificate, 152 + 96 + 4 * 8, 1024)
    put32(pe_certificate, 152 + 96 + 4 * 8 + 4, 16)
    pe_certificate += struct.pack("<IHH8s", 16, 0x0200, 2, b"CERTDATA")
    pe_symbols = bytearray(executable)
    put32(pe_symbols, 128 + 12, 1024)
    put32(pe_symbols, 128 + 16, 1)
    pe_symbols += bytes(18) + struct.pack("<I", 4)
    pe_debug = bytearray(executable)
    put32(pe_debug, 152 + 96 + 6 * 8, 0x1100)
    put32(pe_debug, 152 + 96 + 6 * 8 + 4, 28)
    struct.pack_into("<IIHHIIII", pe_debug, 768, 0, 0, 0, 0, 0, 16, 0, 1024)
    pe_debug += b"0123456789abcdef"
    # A complete embedded MZ image inside a certificate remains host data.
    pe_certificate_data = bytearray(executable)
    put32(pe_certificate_data, 152 + 96 + 4 * 8, 1024)
    put32(pe_certificate_data, 152 + 96 + 4 * 8 + 4, 528)
    pe_certificate_data += struct.pack("<IHH8s", 528, 0x0200, 2, bytes(8)) + bytes(dos)
    # NE relocation records follow their segment data. Resource-only images
    # have no segment extent, so their resource ranges delimit the host.
    ne_relocations = bytearray(ne)
    struct.pack_into("<HHHH", ne_relocations, 128, 16, 256, 0x0100, 256)
    ne_relocations += struct.pack("<H", 1) + bytes(8)
    ne_resources = bytearray(ne)
    put16(ne_resources, 64 + 28, 0)
    put16(ne_resources, 64 + 36, 64)
    put16(ne_resources, 64 + 38, 96)
    struct.pack_into("<HHHIHHHHHHH", ne_resources, 128,
                     4, 0x800A, 1, 0, 32, 8, 0, 0x8001, 0, 0, 0)
    ne_resources += b"R" * 128
    fixtures = {
        "payload.tar": tar_data,
        "payload.tar.gz": gzip_data,
        "magic-wrong.zip": gzip_data,
        "archive.zip": zip_data,
        "prefixed.bin": prefixed_zip,
        "prefixed.zip": prefixed_zip,
        "image": image,
        "v7.bin": v7_tar(),
        "plain.exe": executable,
        "pe-sfx.bin": executable + zip_data,
        "dos-sfx.bin": bytes(dos) + zip_data,
        "com-sfx.bin": com + zip_data,
        "bad-pe-sfx.bin": bytes(invalid_pe) + zip_data,
        "parts.001": b"first split member\n",
        "parts.002": b"second split member\n",
        "empty.001": b"",
        "compressed.001": gzip_data,
        "garbage.bin": b"unrecognized binary\0\xfe\x85\x03\x97",
        "misleading.tar.gz": b"unrecognized binary\0\xfe\x85\x03\x97",
        "ordinary.txt": b"Ordinary readable prose without an unpackable container.\n",
        "cut.zip": zip_data[:12],
        "bad.zip": b"PK\3\4" + bytes(36),
        "cut.gz": gzip_data[:5],
        "bad-png": image[:16],
        "cut-pe.bin": executable[:128],
        "overlay-dos.bin": bytes(dos) + bytes(dos),
        "overlay-pe.bin": bytes(dos) + executable,
        "overlay.exe": bytes(dos) + executable,
        "overlay-ne.bin": bytes(dos) + bytes(ne),
        "overlay-ne-host.bin": bytes(ne) + bytes(dos),
        "overlay-bad-ne.bin": bytes(dos) + bytes(invalid_ne),
        "overlay-padding.bin": bytes(dos) + bytes(511) + executable,
        "overlay-ff.bin": bytes(dos) + b"\xff" + bytes(dos),
        "overlay-chain.bin": overlay_chain,
        "overlay-nonzero-base.bin": b"opaque prefix 17!" + overlay_chain,
        "overlay-term.bin": bytes(dos) + term,
        "overlay-bad-term-number.bin": bytes(dos) + bytes(invalid_term_number),
        "overlay-bad-term-header.bin": bytes(dos) + bytes(invalid_term_header),
        "overlay-bad-padding.bin": bytes(dos) + b"\x42" + executable,
        "overlay-too-much-padding.bin": bytes(dos) + bytes(512) + executable,
        "overlay-hidden-mz.bin": bytes(hidden_image),
        "overlay-cut-header.bin": bytes(dos) + b"MZ" + bytes(22),
        "overlay-overflow.bin": bytes(dos) + bytes(oversized_pe),
        "overlay-bad-outer.bin": bytes(invalid_dos) + executable,
        "overlay-pe-certificate.bin": bytes(pe_certificate) + bytes(dos),
        "overlay-pe-symbols.bin": bytes(pe_symbols) + bytes(dos),
        "overlay-pe-debug.bin": bytes(pe_debug) + bytes(dos),
        "overlay-pe-certificate-data.bin": bytes(pe_certificate_data),
        "overlay-ne-relocations.bin": bytes(ne_relocations) + bytes(dos),
        "overlay-ne-resources.bin": bytes(ne_resources) + bytes(dos),
    }
    for name, data in fixtures.items():
        (root / name).write_bytes(data)
    print("Created %d unpack-handle fixtures in %s" % (len(fixtures), root))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: create_unpack_handle_fixtures.py OUTPUT_DIRECTORY")
    main(sys.argv[1])
