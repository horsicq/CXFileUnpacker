"""Byte-exact native Chromium, thumbnail-cache and Enigma VFS regressions."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import time

U32 = lambda n: struct.pack('<I', n)
U16 = lambda n: struct.pack('<H', n)
POLY = 0x92C64265D32139A4

def crc64(data, crc=0):
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (POLY if crc & 1 else 0)
    return crc

def sampled_crc(data):
    if len(data) <= 1024:
        return crc64(data)
    return crc64(data[:1024]) ^ crc64(b''.join(data[i:i+4] for i in range(1024, len(data), 400)))

def pak(version, encoding, resources, aliases=()):
    resources = sorted(resources.items())
    header = U32(4) + U32(len(resources)) + bytes([encoding]) if version == 4 else struct.pack('<IBxxxHH', 5, encoding, len(resources), len(aliases))
    offset = len(header) + 6 * (len(resources) + 1) + 4 * len(aliases)
    table, data = bytearray(), bytearray()
    for resource, content in resources:
        table += struct.pack('<HI', resource, offset)
        data += content
        offset += len(content)
    table += struct.pack('<HI', 0, offset)
    for resource, slot in aliases:
        table += struct.pack('<HH', resource, slot)
    return header + table + data

def thumbnail(version, data, hash_value=0x0123456789abcdef):
    entry_size = 48 if version == 21 else 56
    fields = 24 if version == 20 else 16
    name = 'identifier'.encode('utf-16le')
    entry = bytearray(entry_size)
    entry[:4] = b'CMMM'
    struct.pack_into('<IQ', entry, 4, entry_size + len(name) + len(data), hash_value)
    struct.pack_into('<III', entry, fields, len(name), 0, len(data))
    struct.pack_into('<Q', entry, entry_size - 16, sampled_crc(data))
    struct.pack_into('<Q', entry, entry_size - 8, crc64(entry[:-8], (1 << 64) - 1))
    size = 28 if version == 28 else 24
    header = bytearray(size)
    header[:4] = b'CMMM'
    struct.pack_into('<II', header, 4, version, 0)
    struct.pack_into('<II', header, 12 if version in (20, 21, 26) else 16, size, size + len(entry) + len(name) + len(data))
    return bytes(header) + entry + name + data

def enigma(legacy, files):
    header = bytearray(64)
    header[:8] = b'EVB\0' + U32(64)
    if legacy:
        result = bytes(header) + U32(15) + bytes(8) + U32(len(files)) + b'\0\0\0'
        for name, content, original in files:
            optional = bytearray(49)
            struct.pack_into('<I', optional, 2, original)
            struct.pack_into('<I', optional, 41, len(content))
            record = bytes(16) + name.encode('utf-16le') + b'\0\0\x02' + optional
            record = U32(len(record) - 4) + record[4:]
            result += record + content
        return result
    table = bytearray(80)
    table[:64] = header
    struct.pack_into('<I', table, 76, len(files))
    del table[79]
    payload = bytearray()
    for name, content, original in files:
        optional = bytearray(53)
        struct.pack_into('<I', optional, 2, original)
        struct.pack_into('<I', optional, 49, len(content))
        table += bytes(16) + name.encode('utf-16le') + b'\0\0\x02' + optional
        payload += content
    table += bytes(4)
    struct.pack_into('<I', table, 64, len(table) - 68)
    return bytes(table) + payload

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', required=True)
    parser.add_argument('--work', required=True)
    args = parser.parse_args()
    work = Path(args.work) / ('run-' + str(time.time_ns()))
    work.mkdir(parents=True)
    checks = 0
    cases = []
    env = os.environ.copy()
    blocker = work / 'blocked-temp'
    blocker.write_bytes(b'Temporary output is forbidden')
    env['TEMP'] = env['TMP'] = str(blocker)

    def check(condition, detail):
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(detail)

    def run(kind, name, content, expected=None, valid=True, password=None, memory=None):
        source = work / name
        source.write_bytes(content)
        before = hashlib.sha256(content).hexdigest()
        test_args = [args.probe, kind, str(source)]
        extra = ([] if password is None and memory is None else [password or '']) + ([] if memory is None else [str(memory)])
        process = subprocess.run(test_args + (['-'] + extra if extra else []), capture_output=True, text=True, env=env, timeout=60)
        check((process.returncode == 0) == valid, (kind, name, process.returncode, process.stdout, process.stderr))
        check(hashlib.sha256(source.read_bytes()).hexdigest() == before, name + ' source modified')
        if valid and expected is not None:
            out = work / (name + '-out')
            process = subprocess.run(test_args + [str(out)] + extra, capture_output=True, text=True, env=env, timeout=60)
            check(process.returncode == 0, (name, 'extract', process.stdout, process.stderr))
            actual = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob('*') if p.is_file()}
            check(actual == expected, (name, 'payload mismatch', list(actual), list(expected)))
        cases.append({'kind': kind, 'fixture': name, 'valid': valid})

    for version in (4, 5):
        for encoding in range(3):
            resources = {1: b'', 17: b'Exact\0payload\xff\xfe', 65534: b'x' * 70000}
            aliases = [(23, 1)] if version == 5 else []
            expected = {str(k) + ('.txt' if encoding else '.bin'): v for k, v in resources.items()}
            if aliases:
                expected['23' + ('.txt' if encoding else '.bin')] = resources[17]
            content = pak(version, encoding, resources, aliases)
            run('chromium', f'chromium-{version}-{encoding}.pak', content, expected)
            run('chromium', f'chromium-truncated-{version}-{encoding}.pak', content[:-1], valid=False)
    bad_alias = bytearray(pak(5, 0, {1: b'a'}, [(2, 0)]))
    struct.pack_into('<H', bad_alias, 26, 1)
    run('chromium', 'chromium-invalid-alias.pak', bad_alias, valid=False)
    for version in (20, 21, 26, 28, 30, 31, 32):
        for payload, extension in ((b'\x89PNG\r\n\x1a\n' + b'A' * 66600, 'png'), (b'\xff\xd8\xff\xe0' + b'J' * 1025, 'jpg'), (b'BM' + b'B' * 20, 'bmp')):
            content = thumbnail(version, payload)
            offset = 28 if version == 28 else 24
            filename = f'0123456789abcdef_{offset:08x}.{extension}'
            run('thumbnail', f'thumbnail-{version}-{extension}.db', content, {filename: payload})
            corrupt = bytearray(content)
            corrupt[-len(payload)] ^= 1
            run('thumbnail', f'thumbnail-bad-data-{version}-{extension}.db', corrupt, valid=False)
        corrupt = bytearray(thumbnail(version, b'BMpayload'))
        corrupt[offset + 8] ^= 1
        run('thumbnail', f'thumbnail-bad-header-{version}.db', corrupt, valid=False)
    fox = b'The quick brown fox jumps over the lazy dog'
    compressed = b'T\x00he quick\xecb\x0erown\xcef\xaex\x80jumps\xed\xe4veur`t?lazy\xead\xfeg\xc0\x00'
    packet = U32(12) + U32(0) + U32(len(compressed)) + compressed
    for legacy in (False, True):
        name = 'enigma-' + ('legacy' if legacy else 'modern')
        content = enigma(legacy, [('payload.bin', b'abc\0\xff', 5), ('compressed.txt', packet, len(fox))])
        run('enigma', name + '.evb', content, {'payload.bin': b'abc\0\xff', 'compressed.txt': fox})
        run('enigma', name + '-cut.evb', content[:-1], valid=False)
        bad = enigma(legacy, [('CON.txt', b'x', 1)])
        run('enigma', name + '-bad-name.evb', bad, valid=False)
        broken = enigma(legacy, [('broken.txt', packet[:-1] + b'\x08', len(fox))])
        run('enigma', name + '-bad-code.evb', broken, valid=False)
    vectors = json.loads(Path(__file__).with_name('uniextract_kgb_vectors.json').read_text())
    expected = {'one.txt': b'KGB archive payload native RAM-only extraction.\n' * 4, 'two.bin': bytes(range(256)) * 2}
    for case in vectors['cases']:
        content = base64.b64decode(case['archive'])
        password = case['password']
        run('kgb', case['name'], content, expected, password=password)
        bad_sum = bytearray(content)
        bad_sum[579] ^= 1
        run('kgb', case['name'] + '-bad-sum', bad_sum, valid=False, password=password)
        if password:
            run('kgb', case['name'] + '-wrong-password', content, valid=False, password='incorrect')
            run('kgb', case['name'] + '-missing-password', content, valid=False)
            corrupted = bytearray(content); corrupted[-1] ^= 1
            run('kgb', case['name'] + '-bad-ciphertext', corrupted, valid=False, password=password)
        if case['algorithm']:
            run('kgb', case['name'] + '-memory-limit', content, valid=False, password=password, memory=16*1024*1024)
    check(blocker.read_bytes() == b'Temporary output is forbidden', 'TEMP blocker changed')
    report = {'checks': checks, 'cases': cases, 'work': str(work)}
    (work / 'uniextract-archive-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'checks': checks, 'cases': len(cases), 'report': str(work / 'uniextract-archive-report.json')}))

if __name__ == '__main__':
    main()
