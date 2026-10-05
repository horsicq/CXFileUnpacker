#!/usr/bin/env python3
"""Independent native UE2 game fixtures: exact bytes, corruptions and RAM TEST."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import uuid
import zlib
import io
import zipfile

U32 = lambda n: struct.pack('<I', n)
U64 = lambda n: struct.pack('<Q', n)

def png():
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\0' + b'\x12\x34\x56\xff' * 2 + b'\0' + b'\x65\x43\x21\xff' * 2)) + chunk(b'IEND', b'')

def bruns(data, compressed):
    key = U32(0x12345678)
    payload = zlib.compress(data) if compressed else data
    return (b'EENZ' if compressed else b'EENC') + U32(0x12345678 ^ 0xdeadbeef) + bytes(v ^ key[i % 4] for i, v in enumerate(payload))

def rpg(data, key):
    return bytes.fromhex('5250474d560000000003010000000000') + bytes(v ^ key[i] if i < 16 else v for i, v in enumerate(data))

def utage(data, key=b'InputOriginalKey'):
    return bytes(v ^ key[i % len(key)] if v not in (0, key[i % len(key)]) else v for i, v in enumerate(data))

def ycg(pixels):
    a, b = zlib.compress(pixels[:8]), zlib.compress(pixels[8:])
    h = bytearray(56)
    h[:20] = b'YCG\0' + U32(2) + U32(2) + U32(32) + U32(1)
    h[32:40], h[48:56] = U32(8) + U32(len(a)), U32(8) + U32(len(b))
    bmp = bytearray(54)
    bmp[:2] = b'BM'
    bmp[2:6], bmp[10:14], bmp[14:18] = U32(70), U32(54), U32(40)
    bmp[18:22], bmp[22:26] = U32(2), U32(0xfffffffe)
    bmp[26:30], bmp[34:38] = struct.pack('<HH', 1, 32), U32(16)
    return bytes(h) + a + b, bytes(bmp) + pixels

def fallout(items):
    body, entries = bytearray(), bytearray(U32(len(items)))
    for name, plain, compressed in items:
        payload = zlib.compress(plain) if compressed else plain
        raw = name.encode()
        entries += U32(len(raw)) + raw + bytes([compressed]) + U32(len(plain)) + U32(len(payload)) + U32(len(body))
        body += payload
    total = len(body) + len(entries) + 8
    return bytes(body + entries + U32(len(entries)) + U32(total))

def pak(version, items, mount='../../../Project/Content/'):
    def string(s):
        b = s.encode() + b'\0'
        return U32(len(b)) + b
    data, rows = bytearray(), []
    for name, plain, compressed in items:
        blocks = [zlib.compress(plain[i:i+64]) for i in range(0, len(plain), 64)] if compressed and version >= 3 else []
        payload = b''.join(blocks) if blocks else zlib.compress(plain) if compressed else plain
        at = len(data)
        size = (56 if version == 1 else 48) + (5 + (4 + len(blocks)*16 if compressed else 0) if version >= 3 else 0)
        def entry(offset):
            b = U64(offset) + U64(len(payload)) + U64(len(plain)) + U32(compressed)
            if version == 1:
                b += U64(1234)
            b += hashlib.sha1(payload).digest()
            if version >= 3:
                if compressed:
                    position = size + (at if version < 5 else 0)
                    b += U32(len(blocks))
                    for block in blocks:
                        b += U64(position) + U64(position + len(block))
                        position += len(block)
                b += b'\0' + U32(64 if compressed else 0)
            return b
        data += entry(0) + payload
        rows.append(string(name) + entry(at))
    index = string(mount) + U32(len(rows)) + b''.join(rows)
    footer = (b'\0' * 16 if version >= 7 else b'') + (b'\0' if version >= 4 else b'') + U32(0x5a6f12e1) + U32(version) + U64(len(data)) + U64(len(index)) + hashlib.sha1(index).digest()
    return bytes(data) + index + footer

def smile(items):
    inner = bytes([0,14,8,30,24,55,18,0,72,135,70,11,156,104,168,75])
    outer = bytes([72,9,20,154,48,169,84,225,0,8,14,9,20,60,66,70])
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, plain, compressed in items:
            encoded = bytes((v - inner[i % 16]) & 255 for i, v in enumerate(plain))
            archive.writestr(name, encoded, compress_type=zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED)
    data = stream.getvalue()
    return b'SGBDAT\0\1' + bytes((v + outer[i % 16]) & 255 for i, v in enumerate(data[8:]))

def gal(version, compressed, alpha):
    h = bytearray(40)
    h[:20] = U32(version) + U32(2) + U32(2) + U32(24) + U32(1)
    h[22] = 0 if compressed else 1
    frame = U32(0) + U32(0) + b'\0' * 9 + U32(1) + U32(2) + U32(2) + U32(24)
    pixels = bytes([10,20,30,40,50,60,0,0,70,80,90,100,110,120,0,0])
    opacity = bytes([2,3,0,0,4,5,0,0]) if alpha else b''
    p = zlib.compress(pixels) if compressed else pixels
    a = zlib.compress(opacity) if compressed and alpha else opacity
    layer = U32(0) * 2 + b'\1' + U32(0xffffffff) + U32(255) + bytes([alpha]) + U32(0) + (b'\0' if version >= 107 else b'') + U32(len(p)) + p + U32(len(a)) + a
    bmp = bytearray(54)
    bmp[:2] = b'BM'
    bmp[2:6], bmp[10:14], bmp[14:18] = U32(70), U32(54), U32(40)
    bmp[18:22], bmp[22:26], bmp[26:30], bmp[34:38] = U32(2), U32(0xfffffffe), struct.pack('<HH', 1, 32), U32(16)
    for row in range(2):
        for col in range(2):
            bmp += pixels[row * 8 + col * 3:row * 8 + col * 3 + 3] + bytes([opacity[row * 4 + col] if alpha else 255])
    return b'Gale' + str(version).encode() + U32(40) + h + frame + layer, bytes(bmp)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--probe', required=True, type=Path)
    p.add_argument('--root', required=True, type=Path)
    args = p.parse_args()
    root = args.root / ('run-' + uuid.uuid4().hex)
    root.mkdir(parents=True)
    blocked_temp = root / 'not-a-directory'
    blocked_temp.write_bytes(b'TEMP cannot hold output')
    env = dict(os.environ, TEMP=str(blocked_temp), TMP=str(blocked_temp))
    reports = []
    def run(label, data, kind, expected=None, password='', memory=None):
        source = root / label
        source.write_bytes(data)
        output = root / (label + '-out')
        before = sorted(str(x.relative_to(root)) for x in root.rglob('*'))
        command = [str(args.probe), str(source), str(kind), password, str(output) if expected is not None else '']
        if memory is not None:
            command.append(str(memory))
        checked = subprocess.run(command, capture_output=True, text=True, env=env, timeout=60)
        if expected is None:
            assert checked.returncode != 0, (label, checked.stdout, checked.stderr)
            assert before == sorted(str(x.relative_to(root)) for x in root.rglob('*')), label
            proof = {'rejected': True}
        else:
            assert checked.returncode == 0, (label, checked.stdout, checked.stderr)
            actual = {str(x.relative_to(output)).replace('\\', '/'): x.read_bytes() for x in output.rglob('*') if x.is_file()}
            assert actual == expected, (label, actual.keys(), expected.keys())
            proof = json.loads(checked.stdout)
            assert source.read_bytes() == data
            assert not any('.tmp' in x.name for x in root.rglob('*'))
        reports.append({'name': label, 'type': kind, **proof})
    image = png()
    for compressed in (False, True):
        packed = bruns(image, compressed)
        run('bruns-%d.png' % compressed, packed, 2700, {'payload.png': image})
        run('bruns-%d-bad.png' % compressed, packed[:-1] if compressed else b'FAKE' + packed[4:], 2700)
    ogg = b'OggS\0' + bytes(range(255)) * 20
    um3 = bytes(x ^ 255 if i < 0x800 else x for i, x in enumerate(ogg))
    run('ultramarine.um3', um3, 2700, {'payload.ogg': ogg})
    key = bytes(range(16))
    run('resource.rpgmvp', rpg(image, key), 2701, {'payload.png': image})
    run('resource-wrong-key.rpgmvp', rpg(image, key), 2701, password='11' * 16)
    run('resource.rpgmvo', rpg(ogg, key), 2701, {'payload.ogg': ogg}, key.hex())
    run('resource-without-key.rpgmvo', rpg(ogg, key), 2701)
    m4a = struct.pack('>I', 24) + b'ftypM4A ' + b'\0\0\0\0isommp42' + struct.pack('>I', 36) + b'mdat' + bytes(range(28))
    run('resource.rpgmvm', rpg(m4a, key), 2701, {'payload.m4a': m4a}, key.hex())
    run('image.utage', utage(image), 2702, {'payload.png': image})
    run('image-custom.utage', utage(image, b'custom_key'), 2702, {'payload.png': image}, 'custom_key')
    run('image-custom-bad.utage', utage(image, b'custom_key'), 2702)
    pixels = bytes(range(16))
    packed, bmp = ycg(pixels)
    run('image.ycg', packed, 2703, {'image.bmp': bmp})
    run('image-truncated.ycg', packed[:-1], 2703)
    run('image-limited.ycg', packed, 2703, memory=4)
    resources = [('folder/readme.txt', b'plain\n', False), ('compressed.bin', b'packed\n' * 80, True), ('empty.bin', b'', False)]
    expected = {name: plain for name, plain, _ in resources}
    packed = fallout(resources)
    run('fallout2.dat', packed, 2705, expected)
    run('fallout2-unsafe.dat', fallout([('../escape', b'no', False)]), 2705)
    changed = dict(expected)
    changed['folder/readme.txt'] = bytes([expected['folder/readme.txt'][0] ^ 1]) + expected['folder/readme.txt'][1:]
    run('fallout2-corrupted.dat', bytes([packed[0] ^ 1]) + packed[1:], 2705, changed)  # Stored members carry no checksum.
    run('fallout2-truncated.dat', packed[:-1], 2705)
    for version in range(1, 8):
        packed = pak(version, resources)
        run('unreal-v%d.pak' % version, packed, 2704, expected)
        bad = bytearray(packed)
        bad[-1] ^= 1
        run('unreal-v%d-index-corrupt.pak' % version, bad, 2704)
        bad = bytearray(packed)
        bad[(56 if version == 1 else 48) + (5 if version >= 3 else 0)] ^= 1
        run('unreal-v%d-payload-corrupt.pak' % version, bad, 2704)
    run('unreal-unsafe.pak', pak(7, [('../escape', b'no', False)]), 2704)
    run('smile.sgbpack', smile(resources), 2707, expected)
    run('smile-unsafe.sgbpack', smile([('../escape', b'no', False)]), 2707)
    run('smile-truncated.sgbpack', smile(resources)[:-1], 2707)
    for version in range(103, 108):
        for compressed in (False, True):
            for alpha in (False, True):
                data, bmp = gal(version, compressed, alpha)
                label = 'gale-v%d-z%d-a%d.gal' % (version, compressed, alpha)
                run(label, data, 2706, {'frame-0000-layer-0000.bmp': bmp})
    data, bmp = gal(107, True, True)
    run('gale-truncated.gal', data[:-1], 2706)
    broken = bytearray(data)
    broken[11 + 21] = 1
    run('gale-shuffled.gal', broken, 2706)
    report = {'cases': len(reports), 'checks': sum(x.get('checks', 0) for x in reports), 'exact_bytes': True, 'test_no_disk': True, 'results': reports}
    (root / 'ue2-games-regression.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'cases': report['cases'], 'checks': report['checks'], 'report': str(root / 'ue2-games-regression.json')}))

if __name__ == '__main__':
    main()
