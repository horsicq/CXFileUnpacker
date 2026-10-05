"""Exercise named filesystem readers through the shipped console interface.

Independent wire builders provide expected names and SHA-256 payloads. LIST
and both TEST modes must leave the input/output tree unchanged. Extraction is
the only operation permitted to create files. Authentic producer controls are
kept separately so this regression requires neither downloads nor disk tools.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import classic_filesystems_regression as classic
import hpfs_filesystems_regression as hpfs
import legacy_filesystems_regression as legacy
import modern_filesystem_additions as modern


def sha(data):
    return hashlib.sha256(data).hexdigest()


def files_expected(files):
    result = {name: (0, sha(data)) for name, data in files.items()}
    for name in files:
        for parent in Path(name).parents:
            if parent.as_posix() != '.':
                result[parent.as_posix()] = (1, sha(b''))
    return result


def fixtures():
    names = {'coherent': 'coherent_fs', 'ext': 'linux_ext', 'sysv': 'sysv_fs',
             'v7': 'unix_v7', 'xenix': 'xenix_fs', 'xia': 'xia_fs'}
    for kind, reader in names.items():
        order = 'pdp' if kind == 'coherent' else 'le'
        block_size = 1024 if kind in ('ext', 'xenix', 'xia') else 512
        image = classic.unix_image(kind, order, block_size)
        yield kind, reader, image.b, image.expected
    for name, reader, builder in [('bfs', 'unix_bfs', classic.bfs_image),
                                  ('qnx4', 'qnx4', classic.qnx_image),
                                  ('efs', 'sgi_efs', classic.efs_image)]:
        image = builder()
        yield name, reader, image.b, image.expected
    for name, reader, builder in [('rt11', 'rt11_fs', legacy.rt11),
                                  ('lif', 'hp_lif', legacy.lif),
                                  ('ecma67', 'ecma67_fs', legacy.ecma),
                                  ('locus', 'locus_fs', legacy.locus),
                                  ('pfs', 'amiga_pfs', legacy.pfs),
                                  ('hpofs', 'hpofs', legacy.hpofs),
                                  ('ods2', 'ods2_fs', legacy.ods),
                                  ('unicos', 'unicos_fs', legacy.unicos)]:
        image, files = builder()
        yield name, reader, image, files_expected(files)
    image, expected = hpfs.fixture()
    yield 'hpfs', 'hpfs', image, expected
    for name, reader, value in [('vxfs-le', 'vxfs', modern.vxfs()),
                                ('vxfs-be', 'vxfs', modern.vxfs(True)),
                                ('vmfs3', 'vmfs', modern.vmfs()),
                                ('vmfs5-inline', 'vmfs', modern.vmfs(True)),
                                ('fossil', 'fossil_fs', modern.fossil()),
                                ('hammer6', 'hammer_fs', modern.hammer()),
                                ('hammer7', 'hammer_fs', modern.hammer(7)),
                                ('reiser4', 'reiserfs', modern.reiser4())]:
        image, files = value
        yield name, reader, image, files_expected(files)


def snapshot(root):
    return {path.relative_to(root).as_posix():
            ('directory',) if path.is_dir() else
            (path.stat().st_size, path.stat().st_mtime_ns, sha(path.read_bytes()))
            for path in root.rglob('*')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xfu', required=True)
    parser.add_argument('--work')
    args = parser.parse_args()
    executable = Path(args.xfu).resolve()
    root = Path(args.work or tempfile.mkdtemp(prefix='xfu-filesystem-cli-')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, reader, image, expected in fixtures():
        folder = root / name
        folder.mkdir(exist_ok=True)
        source = folder / 'input.img'
        source.write_bytes(image)
        tmp = folder / 'temporary'
        tmp.mkdir(exist_ok=True)
        environment = dict(os.environ, TEMP=str(tmp), TMP=str(tmp), TMPDIR=str(tmp))
        before = snapshot(folder)
        operations = []
        for command, extra in [('l', []), ('t', []), ('t', ['--verbose'])]:
            process = subprocess.run([str(executable), command, str(source),
                                      '--reader', reader, *extra], cwd=folder,
                                     env=environment, capture_output=True,
                                     text=True, encoding='utf-8', errors='replace', timeout=120)
            assert process.returncode == 0, (name, command, extra, process.stdout, process.stderr)
            assert snapshot(folder) == before, (name, command, 'unexpected filesystem mutation')
            if command == 't' and not extra:
                lines = process.stdout.splitlines()
                assert lines and all(re.fullmatch(r'\d{1,3}%', line) for line in lines), (name, lines)
                values = [int(line[:-1]) for line in lines]
                assert values == sorted(set(values)) and values[-1] == 100, (name, values)
                assert not any(path in process.stdout for path in expected), (name, 'member names in quiet TEST')
            else:
                assert all(path in process.stdout for path in expected), (name, command, process.stdout)
                if command == 't':
                    assert all(line.endswith(' -- OK') for line in process.stdout.splitlines()), (name, process.stdout)
            operations.append({'command': command, 'verbose': bool(extra), 'exit_code': process.returncode})
        output = folder / 'extracted'
        # A fresh destination avoids both stale-output acceptance and overwrite prompts.
        assert not output.exists(), (name, 'choose a fresh work directory')
        process = subprocess.run([str(executable), 'x', str(source), '--reader', reader,
                                  '-o' + str(output)], cwd=folder, env=environment,
                                 capture_output=True, text=True, timeout=120)
        assert process.returncode == 0, (name, 'x', process.stdout, process.stderr)
        actual = {}
        for path in output.rglob('*'):
            relative = path.relative_to(output).as_posix()
            if 'volume-info.txt' in relative:
                continue
            actual[relative] = (1, sha(b'')) if path.is_dir() else (0, sha(path.read_bytes()))
        assert actual == expected, (name, actual, expected)
        assert sha(source.read_bytes()) == sha(image), (name, 'source changed')
        assert not any(tmp.iterdir()), (name, 'temporary files')
        rows.append({'name': name, 'reader': reader, 'source_sha256': sha(image),
                     'members': len(expected), 'operations': operations,
                     'extraction_sha256_matches': True, 'test_disk_writes': 0})
        print(name, 'LIST, quiet/verbose RAM TEST and exact extraction passed', flush=True)
    report = {'passed': len(rows), 'operations': len(rows) * 4,
              'executable_sha256': sha(executable.read_bytes()), 'cases': rows}
    (root / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'{len(rows)} filesystem CLI cases, {len(rows) * 4} operations passed')


if __name__ == '__main__':
    main()
