#!/usr/bin/env python3
"""Independent Amiga carrier/header/codec fixtures; archived code never runs."""
from __future__ import annotations
import argparse, pathlib, struct
from archive_additions import adaptive_literals, crc16, raw_crc32
from archive_secondwave import fixture, run

BE16 = lambda n: struct.pack('>H', n)
BE32 = lambda n: struct.pack('>I', n)


def stub(size, words, high=False):
    p = bytearray(size); p[:4] = BE32(0x3f3)
    for at, value in zip([60, 68, 76, 80, 84] if high else [40, 48, 56, 60, 64], words):
        p[at:at+4] = BE32(value)
    return p


def bits(items):
    text = ''.join(format(value, '0%db' % width) for value, width in items)
    text += '0' * (-len(text) % 8)
    return int(text, 2).to_bytes(len(text) // 8, 'big')


def zoom(p, append=False): return adaptive_literals(p, 317, 316) + (b'\0JUNK' if append else b'')


def savage():
    size = 901120; remaining = size; symbols = []
    while remaining:
        count = min(remaining, 65535); remaining -= count
        symbols += [(count, 16), (0, 5), (0, 5), (0, 9), (65, 9), (0, 4), (0, 4)]
    packed = bits(symbols); plain = b'A' * size
    header = bytearray(31); header[0] = 29; header[2:7] = b'*SVG*'
    header[7:15] = struct.pack('<II', len(packed), len(plain)); header[29:31] = struct.pack('<H', crc16(plain))
    return bytes(header) + packed, [plain]


def mxm():
    body = stub(0x264, [0x4eaefdd8, 0x4a806700, 0x01142e28, 0x00a07254, 0x2f410020], True)
    payloads = [b'MXM independent first stored bytes.', bytes(range(128))]
    for i, payload in enumerate(payloads):
        name = ('file%d.bin' % i).encode().ljust(16, b'\0')
        body += BE32(24 + len(payload)) + BE32(len(payload)) + name + payload
    return bytes(body) + bytes(24), payloads


def sds():
    body = stub(0x41c, [0xfdd823c0, 0x2c404eae, 0x0000405a, 0x207c0000, 0x020c7600], True)
    payloads = [b'SDS literal member\0' + bytes(range(64)), b'A' * 10]
    for i, plain in enumerate(payloads):
        if i == 1:
            # One literal plus a nine-byte overlapping distance-zero match.
            # Symbol 1536 uses table index6 (offset1536, width9).
            packed = bits([(1, 1), (65, 8), (0, 1), (6, 4), (0, 9), (0, 3)])
        else:
            packed = bits([(value, width) for c in plain for value, width in [(1, 1), (c, 8)]])
        name = ('sds%d.bin' % i).encode().ljust(20, b'\0')
        body += name + BE32(len(packed)) + BE32(len(plain)) + BE16(sum(plain) & 65535) + packed
    return bytes(body) + bytes(30), payloads


def lhsfx(append=False):
    body = stub(0x918, [0x43f90000, 0x00000318, 0x02ec2c79, 4, 0x4eaefdd8])
    payloads = [b'First LhSFX custom Zoom bytes.', bytes(range(128))]
    for i, plain in enumerate(payloads):
        packed = zoom(plain, append)
        body += BE32(0) + BE32(len(plain)) + BE32(len(packed)) + BE32(0) + ('lhsfx%d.bin' % i).encode().ljust(48, b'\0') + packed
    return bytes(body) + BE32(0xffffffff), payloads


def omni(compressed=True, command=False, append=False):
    body = stub(0x7a8, [0x42adfff4, 0x00044eae, 0x4aac00ac, 0x67026014, 0x41ec005c])
    body[0x208:0x20c] = BE32(0x51cdfffc)
    body += BE16(1 if command else 0)
    if command: body += BE16(8) + b'IGNORED!'
    payloads = [b'Omni verified stored/plain bytes.', bytes(range(128))]
    for i, plain in enumerate(payloads):
        name = ('omni%d.bin' % i).encode(); packed = zoom(plain, append)
        data = b'LH' + BE32(len(plain)) + BE32(len(packed)) + BE32(raw_crc32(packed)) + packed if compressed else plain
        body += BE16(len(name)) + name + BE32(len(data)) + data + bytes(2)
    return bytes(body) + BE16(0), payloads


def lhpak(append=False):
    body = stub(0x100, [0x4c534658, 0x2c790000, 0x01144aaa, 0x00ac6600, 0x001841ea])
    body[20:24] = BE32((len(body) - 128) // 4)
    payload = b'LhPak independent multi-block data\0' + bytes(range(64))
    pieces = [payload[:30], payload[30:]]
    for i, plain in enumerate(pieces):
        packed = zoom(plain, append); header = bytearray(44 if not i else 20)
        if not i:
            name = b'lhpak.bin\0'.ljust(12, b'\0'); header[24:28] = BE32(len(payload)); header[42] = 3; header += name
        header[:16] = BE32(len(header) + len(packed) if not i else 0) + BE16(len(packed)) + BE16(i) + BE32(len(plain)) + BE32(raw_crc32(packed))
        words = sum(struct.unpack('>%dI' % (len(header) // 4), header)) & 0xffffffff
        header[16:20] = BE32((-words) & 0xffffffff)
        body += header + packed
    return bytes(body), [payload]


def cases():
    result = []
    for reader, build in [('savage', savage), ('mxm_simplearc', mxm), ('sds_sfx', sds), ('lhpak_sfx', lhpak), ('lhsfx', lhsfx), ('s_omni', omni)]:
        data, plain = build()
        result.append(fixture(reader, reader, data, plain))
        result.append(fixture(reader + '-truncated', reader, data[:-5], accepted=False))
        result.append(fixture(reader + '-unknown-suffix', reader, data + b'UNRELATED', accepted=False))
        bad = bytearray(data); bad[3 if reader != 'savage' else 4] ^= 1
        result.append(fixture(reader + '-bad-carrier', reader, bad, accepted=False))
        if reader in ['savage', 'sds_sfx', 'lhpak_sfx', 's_omni']:
            bad = bytearray(data)
            at = 29 if reader == 'savage' else 0x41c + 28 if reader == 'sds_sfx' else 0x100 + 16 if reader == 'lhpak_sfx' else len(data) - 8
            bad[at] ^= 1
            result.append(fixture(reader + '-bad-checksum', reader, bad, accepted=False))
    for label, compressed, command in [('stored', False, False), ('command', True, True)]:
        data, plain = omni(compressed, command)
        result.append(fixture('omni-' + label, 's_omni', data, plain))
    for name, build in [('lhpak_sfx', lhpak), ('lhsfx', lhsfx), ('s_omni', lambda append: omni(append=append))]:
        data, _ = build(append=True)
        result.append(fixture(name + '-data-after-codec-eof-with-valid-crc', name, data, accepted=False))
    plain = b'PCompress trailing-byte fixture.'
    packed = zoom(plain, True)
    payload = b'LH' + BE32(len(plain)) + BE32(len(packed)) + BE32(raw_crc32(packed)) + packed
    data = b'PACKtrailing.bin\n' + BE32(len(payload)) + payload
    result.append(fixture('pcompress_pack-data-after-eof-valid-crc', 'pcompress_pack', data, accepted=False))
    return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--probe', required=True, type=pathlib.Path); parser.add_argument('--work-dir', required=True, type=pathlib.Path)
    args = parser.parse_args()
    return 0 if run(args.probe, cases(), args.work_dir) else 1


if __name__ == '__main__': raise SystemExit(main())
