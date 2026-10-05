#!/usr/bin/env python3
"""Independent FSB1..5 PCM producers and playable output byte proofs."""
import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess
import time
import uuid


def legacy(version, samples, basic=False):
    headers, data = bytearray(), bytearray()
    for index, (name, payload, count, rate, channels, mode) in enumerate(samples):
        if basic and index:
            header = struct.pack('<II', count, len(payload))
        else:
            header = bytearray(64)
            if version == 1:
                header[:len(name)] = name.encode()
                struct.pack_into('<IIiHHHhIII', header, 32, count, len(payload), rate, 0, channels, 255, 0, mode, 0, 0)
            else:
                struct.pack_into('<H', header, 0, 64)
                header[2:2 + len(name)] = name.encode()
                struct.pack_into('<IIIIIiHhHH', header, 32, count, len(payload), 0, 0, mode, rate, 255, 0, 0, channels)
        headers += header
        data += payload
    if version == 1:
        fixed = b'FSB1' + struct.pack('<III', len(samples), len(data), 0)
    else:
        fixed = ('FSB' + str(version)).encode() + struct.pack('<III', len(samples), len(headers), len(data))
        if version >= 3:
            fixed += struct.pack('<II', 0x30000 if version == 3 else 0x40000, 2 if basic else 0)
        if version == 4:
            fixed += bytes(24)
    return fixed + headers + data


def fsb5(codec, samples, big_endian=False, revision=1):
    rates = [4000,8000,11000,11025,16000,22050,24000,32000,44100,48000,96000]
    channels_ = [1,2,6,8]
    headers, names, data = bytearray(), bytearray(4 * len(samples)), bytearray()
    for index, (name, payload, count, rate, channels) in enumerate(samples):
        data += bytes(-len(data) % 32)
        chunks = []
        if channels not in channels_:
            chunks.append((1, bytes([channels])))
        if rate not in rates:
            chunks.append((2, struct.pack('<I', rate)))
        raw = (count << 34) | ((len(data) // 32) << 7) | ((channels_.index(channels) if channels in channels_ else 0) << 5)
        raw |= (rates.index(rate) if rate in rates else 0) << 1
        raw |= bool(chunks)
        headers += struct.pack('<Q', raw)
        for i, (kind, payload_) in enumerate(chunks):
            headers += struct.pack('<I', (kind << 25) | (len(payload_) << 1) | (i + 1 < len(chunks))) + payload_
        struct.pack_into('<I', names, index * 4, len(names))
        names += name.encode() + b'\0'
        data += payload
    data += bytes(-len(data) % 32)
    fixed = bytearray(64 if revision == 0 else 60)
    fixed[:4] = b'FSB5'
    struct.pack_into('<IIIIII', fixed, 4, revision, len(samples), len(headers), len(names), len(data), codec)
    if revision:
        struct.pack_into('<I', fixed, 32, int(big_endian))
    return fixed + headers + names + data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', required=True, type=pathlib.Path)
    parser.add_argument('--root', required=True, type=pathlib.Path)
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    args = parser.parse_args()
    assert args.ffmpeg
    folder = args.root / ('run-' + time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    pcm = struct.pack('<17h', *range(-8, 9))
    cases = []
    for version in (1,2,3,4):
        sample = ('tone', pcm, 17, 8000, 1, 0x130)
        cases.append((f'pcm16-fsb{version}', legacy(version, [sample]), [('tone.wav', pcm, 's16le', 'pcm_s16le')]))
    for version in (3,4):
        sample = ('tone', pcm, 17, 8000, 1, 0x130)
        cases.append((f'basic-fsb{version}', legacy(version, [sample, sample], basic=True),
                      [('tone.wav', pcm, 's16le', 'pcm_s16le'), ('00000001.dat.wav', pcm, 's16le', 'pcm_s16le')]))
    cases.append(('signed8', legacy(1, [('eight', bytes([0,127,128,255,1]), 5, 8000, 1, 0x128)]),
                  [('eight.wav', bytes([128,255,0,127,129]), 'u8', 'pcm_u8')]))
    cases.append(('unsigned16', legacy(2, [('sixteen', bytes([0,0,255,255,0,128]), 3, 8000, 1, 0xb0)]),
                  [('sixteen.wav', bytes([0,128,255,127,0,0]), 's16le', 'pcm_s16le')]))
    for codec, width, raw_format, encoder in [(1,1,'u8','pcm_u8'), (2,2,'s16le','pcm_s16le'),
                                             (3,3,'s24le','pcm_s24le'), (4,4,'s32le','pcm_s32le'),
                                             (5,4,'f32le','pcm_f32le')]:
        payload = b''.join((struct.pack('<f', i / 16) if codec == 5 else int(i).to_bytes(width, 'little', signed=codec != 1))
                           for i in range(5))
        for revision in (0,1):
            name = f'fsb5-r{revision}-codec{codec}'
            cases.append((name, fsb5(codec, [('tone', payload, 5, 8000, 1)], revision=revision),
                          [('tone.wav', payload, raw_format, encoder)]))
    cases.append(('big-endian', fsb5(2, [('be', b''.join(pcm[i:i+2][::-1] for i in range(0,len(pcm),2)), 17, 8000, 1)], True),
                  [('be.wav', pcm, 's16le', 'pcm_s16le')]))
    multichannel = struct.pack('<24h', *range(24))
    cases.append(('multichannel-rate-chunks', fsb5(2, [('quad', multichannel, 6, 12345, 4)]),
                  [('quad.wav', multichannel, 's16le', 'pcm_s16le')]))
    cases.append(('six-channels', fsb5(2, [('surround', multichannel, 4, 44100, 6)]),
                  [('surround.wav', multichannel, 's16le', 'pcm_s16le')]))
    cases.append(('unique-names', fsb5(2, [('same', pcm, 17, 8000, 1), ('same', pcm, 17, 8000, 1)]),
                  [('same.wav', pcm, 's16le', 'pcm_s16le'), ('same_1.wav', pcm, 's16le', 'pcm_s16le')]))
    raw = b'platform-specific sample payload'
    cases.append(('opaque-codec', fsb5(10, [('xma', raw, 17, 8000, 1)]), [('xma', raw + bytes(-len(raw) % 32), None, None)]))
    checks, proofs = 0, []
    for name, bank, members in cases:
        source, output = folder / (name + '.fsb'), folder / (name + '-output')
        source.write_bytes(bank)
        result = subprocess.run([str(args.probe), str(source), str(output)], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, name + ': ' + result.stderr
        checks += json.loads(result.stdout)['checks']
        assert sorted(p.name for p in output.iterdir()) == sorted(item[0] for item in members)
        checks += 1
        for filename, payload, format_, codec in members:
            data = (output / filename).read_bytes()
            if format_:
                decoded = subprocess.run([str(args.ffmpeg), '-hide_banner', '-loglevel', 'error', '-i', 'pipe:0',
                                          '-c:a', codec, '-f', format_, 'pipe:1'], input=data,
                                         capture_output=True, check=True).stdout
                assert decoded == payload, name + ' playable decoded bytes differ'
                assert data[:4] == b'RIFF' and data[8:12] == b'WAVE'
                checks += 2
            else:
                assert data == payload
                checks += 1
        assert source.read_bytes() == bank
        checks += 1
        proofs.append({'name': name, 'sha256': hashlib.sha256(bank).hexdigest(), 'members': [item[0] for item in members]})
    report = {'checks': checks, 'fixtures': proofs, 'test_payload_files': 0}
    (folder / 'verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'checks': checks, 'fixtures': len(cases), 'report': str(folder / 'verification.json')}))


if __name__ == '__main__':
    main()
