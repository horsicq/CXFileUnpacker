"""Verify original DGCA archives with only the application executable present."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def tree(path):
    return {p.relative_to(path).as_posix(): digest(p) for p in path.rglob('*') if p.is_file()}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cli', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--standalone', action='store_true')
    args = parser.parse_args()
    root = args.root / ('run-' + uuid.uuid4().hex)
    root.mkdir(parents=True)
    runtime = root / 'runtime'
    runtime.mkdir()
    exe = runtime / args.cli.name
    shutil.copy2(args.cli, exe)
    blocker = root / 'blocked-temp'
    blocker.write_bytes(b'TEST must not create temporary files')
    env = dict(os.environ, TEMP=str(blocker), TMP=str(blocker), TMPDIR=str(blocker),
               PATH=str(Path(os.environ['SystemRoot']) / 'System32'),
               XFU_DGCAC_PATH=str(root / 'missing-original-decoder.exe'))
    fixtures = [c for c in json.loads((args.fixtures / 'manifest.json').read_text(encoding='utf8'))['cases'] if c['handler'] == 'DGCA']
    report = {'passed': False, 'checks': 0, 'fixtures': len(fixtures), 'runtime': str(runtime),
              'only_runtime_file': exe.name, 'cli_sha256': digest(exe), 'operations': [],
              'external_decoder_available': False, 'TEMP_blocked': True}

    def check(condition, message):
        report['checks'] += 1
        if not condition:
            raise AssertionError(message)

    def invoke(command, archive, extra, success=True):
        before = tree(root)
        proc = subprocess.run([str(exe), command, str(archive), *extra], cwd=root,
                              env=env, capture_output=True, timeout=45)
        output = proc.stdout.decode('utf8', 'replace')
        report['operations'].append({'archive': archive.name, 'command': command,
                                     'options': extra, 'returncode': proc.returncode,
                                     'stdout': output, 'stderr': proc.stderr.decode('utf8', 'replace')})
        check((proc.returncode == 0) == success, f'{archive.name} {command}: {report["operations"][-1]}')
        if command in ('l', 't'):
            check(before == tree(root), f'{archive.name} {command} changed files')
        if command == 't' and success:
            percentages = [int(m) for m in re.findall(r'(?m)^(\d+)%\s*$', output)]
            check(percentages and percentages[-1] == 100 and percentages == sorted(percentages), 'invalid progress')
            check(all(re.fullmatch(r'\d+%', line) for line in output.splitlines() if line), 'quiet TEST contains per-file output')
        return output

    try:
        check(len(fixtures) == 6, 'not all original DGCA fixture variants found')
        for case in fixtures:
            archive = args.fixtures / case['archive']
            check(digest(archive) == case['sha256'], 'original fixture changed')
            expected = {m['name']: bytes.fromhex(m['hex']) for m in case['members']}
            password = [('--password=' if args.standalone else '-p') + case['password']] if case.get('password') else []
            named = (['--format=dgca'] if args.standalone else ['--reader', 'dgca']) + password
            for label, extra in [('automatic', password), ('selected', named)]:
                listing = invoke('l', archive, extra)
                for name in expected:
                    check(name in listing, f'missing listed member {name}')
                invoke('t', archive, extra)
                destination = root / (archive.stem + '-' + label)
                invoke('x', archive, ['-o' + str(destination), *extra])
                actual = {p.relative_to(destination).as_posix(): p.read_bytes()
                          for p in destination.rglob('*') if p.is_file()}
                check(actual == expected, f'extracted paths or bytes differ: {archive.name} {label}')
            if password:
                for bad in ([], ['--password=incorrect-native-password'] if args.standalone else ['-pincorrect-native-password']):
                    option = ['--format=dgca'] if args.standalone else ['--reader', 'dgca']
                    invoke('t', archive, option + bad, False)
            check(digest(archive) == case['sha256'], 'original fixture changed after decoding')
        check(list(runtime.iterdir()) == [exe], 'extra executable or library appeared')
        check(digest(exe) == digest(args.cli), 'executable changed')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        path = root / 'dependency-free-dgca-report.json'
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
        print(path)
        print(f'passed={report["passed"]}, checks={report["checks"]}')

if __name__ == '__main__':
    main()
