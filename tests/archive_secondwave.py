#!/usr/bin/env python3
"""Independent retained-author compressed fixtures and native archive lifecycle checks.

Fixture writer programs are trusted codec sources, never archived applications.
Normal regression uses checked-in compressed vectors and only the native probe.
"""
from __future__ import annotations
import argparse, base64, bz2, hashlib, json, lzma, pathlib, struct, subprocess, tempfile, zlib


def crc_raw(data: bytes) -> int:
    v = 0
    for c in data:
        v ^= c
        for _ in range(8):
            v = (v >> 1) ^ (0xedb88320 if v & 1 else 0)
    return v


def lrzip(payload: bytes, method=3, md5=False, match=False, corrupt_crc=False):
    width = 4
    props = bytes((93,)) + struct.pack('<I', 1 << 20)
    header = b'LRZI\0\6' + struct.pack('<Q', len(payload)) + b'\0\0' + props + bytes((md5, 0, 0))
    if match:
        assert payload == b'abcd' * 17
        codes = b'\0' + struct.pack('<H', 4) + b'\1' + struct.pack('<HI', 64, 4)
        literals = b'abcd'
    else:
        codes = b'\0' + struct.pack('<H', len(payload)) if payload else b''
        literals = payload
    codes += b'\0\0\0' + (b'' if md5 else struct.pack('<I', crc_raw(payload) ^ int(corrupt_crc)))
    def compress(p):
        if method == 3: return p
        if method == 4: return bz2.compress(p)
        if method == 5:
            if len(p) <= 238: return bytes((len(p) + 17,)) + p + b'\x11\0\0'
            left = len(p) - 18; prefix = bytearray((0,))
            while left > 255: prefix.append(0); left -= 255
            return bytes(prefix) + bytes((left,)) + p + b'\x11\0\0'
        if method == 6: return lzma.compress(p, format=lzma.FORMAT_RAW, filters=[{'id': lzma.FILTER_LZMA1, 'dict_size': 1 << 20, 'lc': 3, 'lp': 0, 'pb': 2}])
        if method == 7: return zlib.compress(p)
        raise ValueError(method)
    streams = [codes, literals]
    packed = [compress(p) for p in streams]
    hs = 13
    offsets = [2 * hs, 3 * hs + len(packed[0])]
    initial = b''.join(bytes((3,)) + struct.pack('<III', 0, 0, offsets[j] if streams[j] else 0) for j in range(2))
    blocks = b''.join(bytes((method,)) + struct.pack('<III', len(packed[j]), len(streams[j]), 0) + packed[j] for j in range(2) if streams[j])
    return header + bytes((width, 1)) + struct.pack('<I', len(payload)) + initial + blocks + (hashlib.md5(payload).digest() if md5 else b'')


def fixture(name, reader, data, outputs=(), accepted=True):
    return {'name': name, 'reader': reader, 'data': base64.b64encode(data).decode(),
            'outputs': [base64.b64encode(p).decode() for p in outputs], 'accepted': accepted,
            'sha256': hashlib.sha256(data).hexdigest()}


def generated_fixtures(writers: pathlib.Path, work: pathlib.Path):
    work.mkdir(parents=True, exist_ok=True)
    cases = []
    binary = b'MZ\0\xff\x80' + bytes(range(256)) * 2 + b'\xe8\x08\0\0\0' + b'ABCD' * 64
    text = b'Independent codec fixture, exact output bytes.\n' * 32
    for reader in ['balz', 'quad', 'lpaq8', 'lpaq1', 'lpaq5', 'paq8', 'paq8f', 'paq8jd', 'paq8o']:
        for label, payload in [('binary', binary), ('text', text)]:
            source = work / (reader + '-' + label + '.dat')
            output = work / (reader + '-' + label + '.arc')
            source.write_bytes(payload)
            if reader == 'balz': args = [str(writers / 'balz_original.exe'), str(source), str(output)]
            elif reader == 'quad': args = [str(writers / 'quad_original.exe'), '-f', str(source), str(output)]
            elif reader.startswith('lpaq'): args = [str(writers / (reader + '_original.exe')), '0', str(source), str(output)]
            else:
                codec = 'paq8l' if reader == 'paq8' else reader
                args = [str(writers / (codec + '_original.exe')), '-1', str(output), str(source)]
                output = pathlib.Path(str(output) + '.' + codec)
            p = subprocess.run(args, capture_output=True, timeout=60)
            if p.returncode: raise RuntimeError((args, p.returncode, p.stdout, p.stderr))
            data = output.read_bytes()
            native = 'paq8' if reader.startswith('paq8') else reader
            cases += [fixture(reader + '-' + label, native, data, [payload]),
                      fixture(reader + '-' + label + '-truncated', native, data[:-6], accepted=False)]
    for mode, lzp in [(0, 0), (256, 0), (512, 0), (768, 0), (0, 0x77), (0x800, 0)]:
        source = work / 'grzip.dat'; source.write_bytes(text)
        output = work / ('grzip-%x-%x.grz' % (mode, lzp))
        args = [str(writers / 'grzip_original.exe'), str(source), str(output), str(mode), str(lzp)]
        p = subprocess.run(args, capture_output=True, timeout=60)
        if p.returncode: raise RuntimeError((args, p.returncode, p.stdout, p.stderr))
        data = output.read_bytes()
        cases += [fixture(output.stem, 'grzip', data, [text]),
                  fixture(output.stem + '-bad-payload-crc', 'grzip', data[:-1] + bytes((data[-1] ^ 1,)), accepted=False)]
    # Multiple members share one PAQ arithmetic context.
    output = work / 'paq-multiple'
    first = work / 'first.txt'; second = work / 'second.bin'
    first.write_bytes(text); second.write_bytes(binary)
    p = subprocess.run([str(writers / 'paq8l_original.exe'), '-1', str(output), str(first), str(second)], capture_output=True, timeout=60)
    if p.returncode: raise RuntimeError(p.stderr)
    cases.append(fixture('paq8-multiple', 'paq8', pathlib.Path(str(output) + '.paq8l').read_bytes(), [text, binary]))
    # LPAQ8 EXE filtering spans the fixed file-buffer boundary.
    payload = (binary * 50) + b'\0' * 32
    source = work / 'lpaq-long.dat'; output = work / 'lpaq-long.arc'; source.write_bytes(payload)
    p = subprocess.run([str(writers / 'lpaq8_original.exe'), '0', str(source), str(output)], capture_output=True, timeout=60)
    if p.returncode: raise RuntimeError(p.stderr)
    cases.append(fixture('lpaq8-buffer-crossing-exe', 'lpaq8', output.read_bytes(), [payload]))
    return cases


def independent_fixtures():
    cases = []
    plain = b'Independently framed LRZIP codec bytes.\n' * 13
    for method in [3, 4, 5, 6, 7]:
        for md5 in [False, True]:
            data = lrzip(plain, method, md5)
            tag = 'lrzip-%s-%s' % (method, 'md5' if md5 else 'crc')
            damaged = data[:-1] + bytes((data[-1] ^ 1,)) if md5 else lrzip(plain, method, corrupt_crc=True)
            cases += [fixture(tag, 'lrzip', data, [plain]),
                      fixture(tag + '-truncated', 'lrzip', data[:-1], accepted=False),
                      fixture(tag + '-bad-checksum', 'lrzip', damaged, accepted=False)]
    data = lrzip(b'abcd' * 17, match=True)
    cases += [fixture('lrzip-overlap-match', 'lrzip', data, [b'abcd' * 17])]
    for name, offset, value in [('encrypted', 22, 1), ('unsupported-revision', 5, 7), ('bad-width', 24, 0), ('bad-final-flag', 25, 2)]:
        bad = bytearray(data); bad[offset] = value
        cases.append(fixture('lrzip-' + name, 'lrzip', bad, accepted=False))
    # Both initial streams pointing at the same physical extent must not alias.
    bad = bytearray(data); bad[52:56] = bad[39:43]
    cases.append(fixture('lrzip-overlapping-chain', 'lrzip', bad, accepted=False))
    for name, offset, value in [('huge-plain', 60, 0x7f), ('self-chain', 65, 26), ('unknown-codec', 56, 255)]:
        bad = bytearray(data); bad[offset] = value
        cases.append(fixture('lrzip-' + name, 'lrzip', bad, accepted=False))
    # Level zero's typed stream makes filter and member boundaries independent
    # of the context-mixing implementation; overlapping E8 operands matter.
    original = bytearray(b'PAQ filter fixture\0\xe8\xe8\0\0\0\0\xe9\x10\0\0\xff' + bytes(range(64)))
    transformed = bytearray(original)
    for i in range(len(transformed) - 1, 3, -1):
        if transformed[i-4] in (0xe8, 0xe9) and transformed[i] in (0, 255):
            v = int.from_bytes(transformed[i-3:i+1], 'little') + i + 1
            v &= 0x01ffffff
            if v & 0x01000000: v |= 0xfe000000
            transformed[i-3:i+1] = v.to_bytes(4, 'little')
    directory = ('%d\tdecoded.bin\r\n' % len(original)).encode()
    stream = b'\2' + struct.pack('>III', len(original), len(original), 0) + transformed
    data = b'paq8l -0\r\n' + directory + b'\x1a' + stream
    cases.append(fixture('paq8-stored-overlapping-exe-filter', 'paq8', data, [original]))
    bad = bytearray(data); bad[len(b'paq8l -0\r\n' + directory + b'\x1a')] = 255
    cases.append(fixture('paq8-unknown-filter', 'paq8', bad, accepted=False))
    cases.append(fixture('paq8-unknown-revision', 'paq8', data.replace(b'paq8l', b'paq8z', 1), accepted=False))
    # A valid GRZip CRC authenticates even a stored block; falsified lengths do not.
    plain = bytes(range(128))
    header = struct.pack('<5I', len(plain), 0xffffffff, 0, 0, len(plain)) + struct.pack('<I', zlib.crc32(plain))
    stored = b'GRZipII\0\2\4:)' + header + struct.pack('<I', zlib.crc32(header)) + plain
    cases.append(fixture('grzip-independent-stored', 'grzip', stored, [plain]))
    for name, offset in [('bad-header-crc', 36), ('truncated', -1)]:
        bad = bytearray(stored)
        if offset < 0: bad.pop()
        else: bad[offset] ^= 1
        cases.append(fixture('grzip-' + name, 'grzip', bad, accepted=False))
    return cases


def run(probe: pathlib.Path, fixtures, work: pathlib.Path):
    work.mkdir(parents=True, exist_ok=True)
    # Native extraction correctly refuses to overwrite an existing member.
    # Give every invocation fresh retained inputs/outputs, including CTest
    # reruns; do not delete prior evidence or weaken the production policy.
    run_dir = pathlib.Path(tempfile.mkdtemp(prefix='run-', dir=work))
    results = []
    for case in fixtures:
        archive = run_dir / (case['name'] + '.arc')
        archive.write_bytes(base64.b64decode(case['data']))
        output = run_dir / (case['name'] + '-out')
        p = subprocess.run([str(probe), case['reader'], str(archive), str(output)], capture_output=True, timeout=90)
        actual = sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file()) if output.exists() else []
        expected = sorted(hashlib.sha256(base64.b64decode(v)).hexdigest() for v in case['outputs'])
        passed = (p.returncode == 0 and actual == expected) if case['accepted'] else (p.returncode != 0 and not actual)
        row = {'name': case['name'], 'reader': case['reader'], 'passed': passed, 'exit_code': p.returncode,
               'stdout': p.stdout.decode(errors='replace'), 'stderr': p.stderr.decode(errors='replace'),
               'expected_sha256': expected, 'actual_sha256': actual,
               'source': str(archive), 'output': str(output)}
        results.append(row)
        print(('PASS ' if passed else 'FAIL ') + case['name'], flush=True)
    report = {'cases': len(results), 'passed': sum(v['passed'] for v in results),
              'run_directory': str(run_dir), 'results': results}
    (work / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return all(v['passed'] for v in results)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', type=pathlib.Path)
    parser.add_argument('--work-dir', type=pathlib.Path, required=True)
    parser.add_argument('--writers', type=pathlib.Path)
    parser.add_argument('--fixture-file', type=pathlib.Path, default=pathlib.Path(__file__).with_name('archive_secondwave_fixtures.json'))
    args = parser.parse_args()
    if args.writers:
        fixtures = generated_fixtures(args.writers, args.work_dir / 'writer-inputs')
        args.fixture_file.write_text(json.dumps({'provenance': 'Retained author BALZ1.20, QUAD1.12, PAQ8l, LPAQ8, GRZip0.3.1 compressors; source/licensing in format-additions audit.', 'fixtures': fixtures}, indent=2), encoding='utf-8')
    else:
        fixtures = json.loads(args.fixture_file.read_text(encoding='utf-8'))['fixtures']
    if not args.probe: return 0
    return 0 if run(args.probe, fixtures + independent_fixtures(), args.work_dir / 'native') else 1


if __name__ == '__main__':
    raise SystemExit(main())
