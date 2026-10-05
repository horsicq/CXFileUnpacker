#!/usr/bin/env python3
"""Independent byte-layout fixtures for the additional disk/tape readers.

Constructors use documented fields, not reader output. Inputs are never run.
Every positive compares all exported bytes and preserves source SHA/mtime;
the optional C probe verifies memory-only IO, limits, cancellation and dispatch.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

P = struct.pack


def pattern(n, seed=11):
    return bytes((i * 29 + seed) & 255 for i in range(n))


def crc16(data):
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ (0xA001 if c & 1 else 0)
    return c


def fixtures():
    cases = []

    def add(reader, name, data, members, sidecars=None):
        cases.append(dict(reader=reader, name=name, data=bytes(data),
                          members=members, sidecars=sidecars or {}))

    h = bytearray(532)
    h[:13] = b'BLU DEVICE   '
    h[18:21] = (2).to_bytes(3, 'big')
    h[21:23] = P('>H', 532)
    body = pattern(512) + pattern(20, 1) + pattern(512, 2) + pattern(20, 3)
    add('lisa_blu', 'tagged.blu', h + body,
        {'descriptor.blu': bytes(h), 'sector-image.img': pattern(512) + pattern(512, 2),
         'sector-tags.bin': pattern(20, 1) + pattern(20, 3)})

    h = bytes([0, 1, 1, 2, 2, 3, 0, 0])
    body = pattern(3072)
    add('maxi_disk', 'maxi.hdk', h + body, {'descriptor.hdk': h, 'sector-image.img': body})
    for flags, n in [(0, 1024), (1, 768)]:
        h = bytearray(144)
        h[:7] = b'RS-IDE\x1a'
        h[7:11] = bytes([1, flags]) + P('<H', 144)
        body = pattern(n)
        add('rs_ide', f'rs-{flags}.ide', h + body,
            {'descriptor.ide': bytes(h), 'sector-image.img': body})
    h = P('<I', 1) + bytes(252)
    body = pattern(8 * 33 * 256)
    add('t98_hdd', 't98.thd', h + body, {'descriptor.thd': h, 'sector-image.img': body})

    h = bytes([1]) + bytes([0x4C, 0xFA]) + bytes([0xFE] * 78) + b'\0'
    body = pattern(4096)
    add('ciscopy', 'dc-file.dcf', h + body,
        {'descriptor.dcf': h, 'sector-image.img': body + bytes([0xF6]) * (39 * 4096)})
    body = b'first tape block\0\n'
    tape = b'CPTP:BLK ' + f'{len(body):06d}'.encode() + b'\n' + body + b'\n'
    tape += b'CPTP:MRK\nCPTP:BLK 000003\nxyz\nCPTP:EOT\n'
    add('copytape', 'tape.cptp', tape,
        {'file-0000-block-000000.bin': body, 'file-0000-filemark.cptp': b'CPTP:MRK\n',
         'file-0001-block-000000.bin': b'xyz'})

    footer = bytearray(415)
    footer[:51] = b'DiskImage 2.01 (C) Digital Research Inc'.ljust(51, b' ')
    for at, value in [(55, 1), (58, 512), (66, 4), (69, 2), (71, 2)]:
        footer[at:at+2] = P('<H', value)
    footer[233:] = footer[51:233]
    body = pattern(2048)
    add('dri_diskcopy', 'dri.dsk', body + footer,
        {'descriptor.dsk-footer': bytes(footer), 'sector-image.img': body})

    h = bytearray(84)
    h[:80] = b'Disk IMage VER 1.10 Copyright Ray Arachelian'.ljust(80, b'\0')
    h[80:84] = bytes([1, 1, 2, 0])
    first, second = pattern(1024), pattern(1024, 5)
    add('ray_dim', 'original.dim', h + first + b'\0\x01' + second + b'\x02\x03',
        {'sector-image.img': first + second, 'sector-status.bin': b'\0\x01\x02\x03',
         'descriptor.dim': bytes(h)})
    h[81:84] = bytes([2, 2, 1])
    body = pattern(2048)
    add('ray_dim', 'writer.dim', h + body,
        {'sector-image.img': body, 'descriptor.dim': bytes(h)})

    h = bytearray(32)
    h[:16] = b'WC DISK IMAGE\x1a\x1a\0'
    h[16:20] = bytes([1, 1, 2, 1])
    h[24] = 3
    body = pattern(512)
    records = bytes([0, 0, 1, 0]) + P('<H', crc16(body)) + body
    records += bytes([2, 0, 2, 0, 0x7A, 0])
    records += bytes([3, 0, 0, 0]) + P('<H', 5) + b'hello'
    records += bytes([4, 0, 0, 0]) + P('<H', 3) + b'dir'
    add('wc_disk_image', 'wc.d2f', h + records,
        {'descriptor.d2f': bytes(h), 'c000-h0-sectors.img': body + b'z' * 512,
         'comment.txt': b'hello', 'directory.txt': b'dir'})

    h = bytearray(256)
    h[:4] = b'FDX\x03'
    for at, value in [(68, 0), (72, 1), (76, 2), (80, 250000), (84, 300), (100, 32)]:
        h[at:at+4] = P('<I', value)
    tracks = [P('<IIII', 0, side, 7, 128) + pattern(16, side) for side in range(2)]
    expected = {'descriptor.fdx': bytes(h)}
    for side, track in enumerate(tracks):
        expected[f'c000-h{side}-encoded-cells.bin'] = track[16:]
        expected[f'c000-h{side}-original-track.fdx'] = track
    add('fdx68_fdx', 'fdx.fdx', h + b''.join(tracks), expected)

    table = bytearray(8 + 256 * 4)
    table[:8] = b'86BF' + bytes([12, 2]) + P('<H', 0x1081)
    table[8:12] = P('<I', len(table))
    t = P('<HiI', 0, 32, 3) + b'\xAA\x55\xA5\x5A' + bytes([0, 0, 1, 0])
    add('pc_86f', '86f.86f', table + t,
        {'descriptor.86f': bytes(table), 'track-000-h0-encoded-cells.bin': t[10:14],
         'track-000-original.86f': t, 'track-000-surface-mask.bin': t[14:]})

    def block(name, data):
        return name + P('>I', len(data)) + data
    header = b'H17D200\xFF'
    df = block(b'DskF', b'\x01\x28\0')
    pad = block(b'Parm', bytes(256 - len(header) - len(df) - 16))
    data = pattern(40 * 10 * 256)
    raw = block(b'H8DB', data)
    meta = b''.join(P('>I', 256 + i * 256) + bytes(8) + P('>H', 256) + bytes(2)
                    for i in range(400))
    sm = block(b'SecM', meta)
    add('heathkit_h17', 'h17.h17', header + df + pad + raw + sm,
        {'block-DskF.h17': df, 'block-Parm.h17': pad, 'block-H8DB.h17': raw,
         'block-SecM.h17': sm, 'sector-image.h8d': data})

    for version in [0x10000, 0x20000]:
        h = bytearray(512)
        h[:23] = b'Bochs Virtual HD Image\0'
        h[32:40], h[48:56] = b'Redolog\0', b'Growing\0'
        h[64:84] = P('<IIIII', version, 512, 2, 1, 4096)
        h[84 if version == 0x10000 else 88:92 if version == 0x10000 else 96] = P('<Q', 8192)
        cat = P('<II', 0, 0xFFFFFFFF)
        bitmap = b'\x05' + bytes(511)
        data = pattern(4096)
        add('bochs_growing', f'bochs-{version}.img', h + cat + bitmap + data,
            {'descriptor-and-catalog.bochs': bytes(h) + cat,
             'logical-disk.img': data[:512] + bytes(512) + data[1024:1536] + bytes(8192-1536)})

    samples = bytes([0, 9, 8, 0, 1, 0, 9, 1, 0])
    info = (b'Format: configured8-bit logic capture\nSample frequency: 16000000 Hz\n'
            b'Data signal bit: 0\nIndex signal bit: 3\nData pulses: 3\nIndex edges: 2\n'
            b'Units: sample ticks, LE32\n')
    add('hxc_logic_analyzer', 'capture.logicbin8bits', samples,
        {'original-samples.logicbin8bits': samples, 'flux-deltas-samples.le32': P('<III', 2, 3, 3),
         'index-positions-samples.le32': P('<II', 3, 7), 'container-info.txt': info})
    data = pattern(262144)
    info = (b'Format: Micral N explicit raw geometry\nCylinders: 64\nHeads: 1\nSectors per track: 32\n'
            b'Sector bytes: 128\nRepresentation: original declared raw-sector order; no filesystem extraction\n')
    add('micral_n_raw', 'micral.mic', data,
        {'sector-image.mic': data, 'container-info.txt': info})

    def var(data):
        return P('<I', len(data)) + data
    h = b'BLINDWRITE TOC FILE' + bytes(12)
    desc = h + var(b'VOLUME') + var(b'SYSTEM') + var(b'comment') + P('<I', 1)
    desc += var(b'track.bwi') + var(b'track.bws') + bytes(5)
    fixed = bytearray(59)
    fixed[13], fixed[17], fixed[19] = 1, 1, 1
    fixed[28:32] = P('<I', 150)
    fixed[38:42] = P('<I', 2)
    desc += var(b'') + fixed + var(b'') * 15
    raw, sub = pattern(4704), pattern(192)
    add('blindwrite4', 'disc.bwt', desc,
        {'descriptor.bwt': desc, 'session-1-track-01-raw.bin': raw,
         'session-1-track-01-user-sectors.img': raw[16:2064] + raw[2368:4416],
         'session-1-track-01-subchannel.bin': sub}, {'track.bwi': raw, 'track.bws': sub})
    return cases


def run(cmd, timeout=15):
    return subprocess.run([str(x) for x in cmd], capture_output=True, timeout=timeout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--unpacker', required=True)
    ap.add_argument('--probe')
    ap.add_argument('--lifecycle-probe')
    ap.add_argument('--root')
    ap.add_argument('--write-only', action='store_true')
    args = ap.parse_args()
    temporary = tempfile.TemporaryDirectory(prefix='xfu-disk-wrappers-') if not args.root else None
    root = Path(args.root or temporary.name)
    root.mkdir(parents=True, exist_ok=True)
    results = []
    try:
        for case in fixtures():
            folder = root / case['name'].replace('.', '_')
            folder.mkdir(exist_ok=True)
            path = folder / case['name']
            path.write_bytes(case['data'])
            for name, data in case['sidecars'].items():
                (folder / name).write_bytes(data)
            if args.write_only:
                continue
            before = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            out = folder / 'out'
            p = run([args.unpacker, 'x', path, '--reader', case['reader'], '-o' + str(out)])
            assert p.returncode == 0, (case['name'], p.returncode, p.stdout, p.stderr)
            actual = {p.name.split('-', 1)[1]: p.read_bytes() for p in out.rglob('*') if p.is_file()}
            assert actual == case['members'], (case['name'], list(actual),
                                             [(k, len(v)) for k, v in case['members'].items()])
            p = run([args.unpacker, 't', path, '--reader=' + case['reader']])
            assert p.returncode == 0, (case['name'], p.stdout, p.stderr)
            assert before == (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            if args.probe:
                p = run([args.probe, path, case['reader']])
                assert p.returncode == 0 and b'valid=1' in p.stdout, (case['name'], p.stdout, p.stderr)
            if args.lifecycle_probe:
                p = run([args.lifecycle_probe, path, case['reader']], 20)
                assert p.returncode == 0, (case['name'], p.stdout, p.stderr)
            results.append({'case': case['name'], 'reader': case['reader'], 'positive': True,
                            'members': len(actual), 'sha256': before[0]})
            # Exact declared bounds reject both appended and truncated bytes.
            # Logic samples intentionally have no framing; any bytes are valid.
            if case['reader'] != 'hxc_logic_analyzer':
                for kind, data in [('truncated', case['data'][:-1]), ('trailing', case['data'] + b'\0')]:
                    bad = folder / ('bad-' + kind)
                    bad.write_bytes(data)
                    p = run([args.unpacker, 't', bad, '--reader', case['reader']])
                    assert p.returncode != 0, (case['name'], kind, p.stdout, p.stderr)
                    results.append({'case': case['name'] + '-' + kind, 'positive': False})
        if not args.write_only:
            # Authenticated body damage must fail, not merely retain a signature.
            case = next(c for c in fixtures() if c['reader'] == 'wc_disk_image')
            data = bytearray(case['data']); data[40] ^= 1
            path = root / 'bad-wc-crc.d2f'; path.write_bytes(data)
            p = run([args.unpacker, 't', path, '--reader', 'wc_disk_image'])
            assert p.returncode != 0, (p.stdout, p.stderr)
            results.append({'case': 'wc-crc', 'positive': False})
            # A valid BWT descriptor with missing data is not a complete image.
            case = next(c for c in fixtures() if c['reader'] == 'blindwrite4')
            missing = root / 'missing' / 'disc.bwt'; missing.parent.mkdir(exist_ok=True)
            missing.write_bytes(case['data'])
            p = run([args.unpacker, 't', missing, '--reader', 'blindwrite4'])
            assert p.returncode != 0, (p.stdout, p.stderr)
            results.append({'case': 'bwt-missing-companions', 'positive': False})
            # Geometry, table offsets, duplicate catalog ownership and reserved
            # flag values are independent framing checks, beyond EOF length.
            controls = {c['reader']: c for c in fixtures()}
            mutations = [
                ('lisa_blu', 21, P('>H', 511)), ('maxi_disk', 5, b'\0'),
                ('rs_ide', 8, b'\x80'), ('t98_hdd', 5, b'\x01'),
                ('ciscopy', 81, b'\x01'), ('copytape', 9, b'x'),
                ('dri_diskcopy', len(controls['dri_diskcopy']['data']) - 415 + 233, b'X'),
                ('ray_dim', 80, b'\0'), ('wc_disk_image', 34, b'\x02'),
                ('fdx68_fdx', 256 + 12, P('<I', 129)),
                ('pc_86f', 8, P('<I', 1)), ('heathkit_h17', 16, b'\0'),
                ('bochs_growing', 516, P('<I', 0)),
                ('blindwrite4', 0, b'X'),
            ]
            for index, (reader, offset, value) in enumerate(mutations):
                data = bytearray(controls[reader]['data'])
                data[offset:offset+len(value)] = value
                path = root / f'bad-grammar-{index}'
                path.write_bytes(data)
                p = run([args.unpacker, 't', path, '--reader', reader])
                assert p.returncode != 0, (reader, offset, p.stdout, p.stderr)
                results.append({'case': f'{reader}-grammar', 'positive': False})
            (root / 'report.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
            print(f'{len(results)} disk-wrapper cases passed; 16 reader families, exact byte exports')
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == '__main__':
    main()
