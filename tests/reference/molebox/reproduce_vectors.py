#!/usr/bin/env python3
"""Rebuild frozen valid fixtures with the original GPL test writer (Win32)."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    reference = Path(__file__).parent
    provenance = json.loads((reference / 'PROVENANCE.json').read_text(encoding='utf8'))
    work = args.work / ('producer-' + str(time.time_ns()))
    work.mkdir(parents=True)
    for name, expected in provenance['sha256'].items():
        data = (reference / (name + '.txt')).read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected, name
        destination = work / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    writer = work / 'molebox_fixture_writer.exe'
    subprocess.run([str(args.compiler), '-m32', '-std=c++17', '-D_CRT_SECURE_NO_WARNINGS',
                    str(work / 'main.cpp'), str(work / 'libhash/src/blowfish.c'),
                    '-o', str(writer), '-ladvapi32'], check=True)
    multi_writer = work / 'molebox_multi_writer.exe'
    subprocess.run([str(args.compiler), '-m32', '-std=c++17', '-D_CRT_SECURE_NO_WARNINGS',
                    str(work / 'multi_main.cpp'), str(work / 'libhash/src/blowfish.c'),
                    '-o', str(multi_writer), '-ladvapi32'], check=True)
    vectors = json.loads((reference.parent.parent / 'uniextract_molebox_vectors.json').read_text(encoding='utf8'))
    for case in vectors['cases']:
        expected = base64.b64decode(case['archive'])
        password = 'secret' if case['embedded_catalog'] else case.get('password') or 'password'
        destination = work / (case['name'] + '.svfs')
        command = ([str(multi_writer), str(destination)] if case.get('producer_kind') == 'two_packages' else
                   [str(writer), str(destination), str(case['flags']), password,
                    str(int(expected.startswith(b'MZ'))), str(int(case['embedded_catalog']))])
        result = subprocess.run(command,
                                check=True, capture_output=True)
        headers = [int(x) for x in result.stdout.split()] if case.get('producer_kind') == 'two_packages' else [int(result.stdout.split()[0])]
        actual = destination.read_bytes()
        # Original Finish leaves the four-byte reserved header field
        # uninitialized. Its CBC block and subsequent two blocks can vary;
        # all payload, tree, prior header blocks and catalog must be identical.
        assert len(actual) == len(expected), case['name']
        assert all(a == b or any(header + 24 <= i < header + 48 for header in headers)
                   for i, (a, b) in enumerate(zip(actual, expected))), case['name']
    report = {'original_writer_payload_tree_catalog_cases': len(vectors['cases']),
              'upstream_uninitialized_reserved_header_bytes': 'Ciphertext header offsets 24..47 excluded from byte comparison',
              'work': str(work)}
    (work / 'molebox-writer-proof.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
