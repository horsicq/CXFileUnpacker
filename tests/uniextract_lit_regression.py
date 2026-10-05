#!/usr/bin/env python3
"""Independent ConvertLIT interoperability fixtures, RAM TEST and hostile inputs."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    fixtures = json.loads(Path(__file__).with_name('uniextract_lit_vectors.json').read_text())
    work = args.work / ('run-' + str(time.time_ns()))
    work.mkdir(parents=True)
    blocker = work / 'not-a-temp-directory'
    blocker.write_bytes(b'TEMP and TMP deliberately point to a regular file.')
    env = dict(os.environ, TEMP=str(blocker), TMP=str(blocker))
    evidence = []
    checks = 0

    def run(name, data, valid, expected=None, limit=None):
        nonlocal checks
        path = work / (name + '.lit')
        path.write_bytes(data)
        before = hashlib.sha256(data).hexdigest()
        command = [str(args.probe), 'lit', str(path), '-']
        if limit is not None:
            command += ['', str(limit)]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
        assert (result.returncode == 0) == valid, (name, result.returncode, result.stdout, result.stderr)
        checks += 1
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
        checks += 1
        if expected is not None:
            out = work / (name + '-extracted')
            command[3] = str(out)
            extracted = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
            assert extracted.returncode == 0, (name, extracted.stdout, extracted.stderr)
            checks += 1
            actual = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob('*') if p.is_file()}
            assert actual == expected, (name, actual.keys(), expected.keys())
            checks += 1
        evidence.append({'name': name, 'valid': valid, 'returncode': result.returncode,
                         'source_sha256': before, 'error': result.stderr.strip()})

    for case in fixtures['cases']:
        data = base64.b64decode(case['archive'])
        expected = {n: base64.b64decode(v) for n, v in case['expected_files'].items()}
        run(case['name'], data, True, expected)
        run(case['name'] + '-budget', data, False, limit=32768)
    clear = base64.b64decode(fixtures['cases'][0]['archive'])
    for n in [0, 7, 39, 40, 119, 351, len(clear)-1]:
        run('truncated-' + str(n), clear[:n], False)
    for name, at, value in [('bad-version',8,2), ('bad-piece-count',16,0),
                             ('bad-secondary-size',20,0), ('bad-high-offset',44,1),
                             ('huge-piece-size',48,0xffffffff), ('zero-secondary-block',124,0)]:
        bad = bytearray(clear)
        struct.pack_into('<I',bad,at,value)
        run(name,bytes(bad),False)
    directory = struct.unpack_from('<Q',clear,56)[0]
    bad = bytearray(clear)
    struct.pack_into('<I',bad,directory+8,0)
    run('zero-directory-chunk',bytes(bad),False)
    run('traversal-name',clear.replace(b'text/chapter.html',b'../x/chapter.html'),False)
    run('bad-content-utf8',clear.replace(b'Test & payload',b'\xffest & payload'),False)
    manifest_at = clear.index(b'\x01/\x01\x00\x00\x00')
    bad = bytearray(clear)
    struct.pack_into('<I',bad,manifest_at+2,0x7fffffff)
    run('huge-manifest-count',bytes(bad),False)
    run('owner-key-drm5',base64.b64decode(fixtures['unsupported_drm5_archive']),False)
    assert blocker.read_bytes() == b'TEMP and TMP deliberately point to a regular file.'
    checks += 1
    report = {'checks':checks,'fixtures':len(evidence),'failed':0,
              'reference':'ConvertLIT 1.8 independent command-line extraction; stored, DES and LZX books',
              'memory_only_test':True,'temporary_paths_blocked':True,'cases':evidence}
    target = work / 'uniextract-lit-report.json'
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'checks':checks,'fixtures':len(evidence),'failed':0,'report':str(target)}))

if __name__ == '__main__':
    main()
