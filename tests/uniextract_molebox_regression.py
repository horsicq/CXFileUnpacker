#!/usr/bin/env python3
"""Frozen original MoleBox writer vectors; no producer or Crypto install needed."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def tree_state(root):
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
            for p in root.rglob('*')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--cli', type=Path)
    args = parser.parse_args()
    vectors = json.loads(Path(__file__).with_name('uniextract_molebox_vectors.json').read_text(encoding='utf8'))
    work = args.work / ('run-' + str(time.time_ns()))
    work.mkdir(parents=True)
    blocker = work / 'not-a-temp-directory'
    blocker.write_bytes(b'TEMP and TMP are files')
    environment = dict(os.environ, TEMP=str(blocker), TMP=str(blocker))
    payload = bytes((i * 17 + 3) & 255 for i in range(100003))
    checks = 0
    fixtures = []

    def expected_files(case):
        return {**{name: payload for name in case.get('expected_payload_names', [case['expected_payload_name']])},
                **{name: b'' for name in case.get('expected_empty_names', ['empty'])}}

    def check(condition, message):
        nonlocal checks
        assert condition, message
        checks += 1

    def run(command, success=True):
        result = subprocess.run([str(x) for x in command], env=environment,
                                capture_output=True, timeout=60)
        check((result.returncode == 0) == success,
              f'{command}: exit {result.returncode}\n{result.stdout!r}\n{result.stderr!r}')
        return result.stdout.decode('utf8', 'replace').replace('\r\n', '\n')

    def probe(source, password=None, output=None, memory=None, maximum=None, cancelled=None, success=True):
        command = [args.probe, source, output or '-', password or '-']
        if memory is not None or maximum is not None or cancelled is not None:
            command.append(memory if memory is not None else 128 * 1024 * 1024)
        if maximum is not None or cancelled is not None:
            command.append(maximum if maximum is not None else 1 << 40)
        if cancelled is not None:
            command.append(int(cancelled))
        return run(command, success)

    valid = []
    for case in vectors['cases']:
        source = work / (case['name'] + '.svfs')
        source.write_bytes(base64.b64decode(case['archive']))
        fixtures.append(source.name)
        before = tree_state(work)
        stdout = probe(source, case.get('password'))
        check('type=2766\n' in stdout, case['name'] + ': reader type')
        check('password=' + case['current_password'] + '\n' in stdout, case['name'] + ': effective credential')
        check('password_state_checks=1\n' in stdout, case['name'] + ': live password/iterator options')
        check(tree_state(work) == before, case['name'] + ': RAM TEST changed filesystem')
        if case.get('password'):
            check('password_detect=2766\n' in stdout, case['name'] + ': password-aware detection')
        output = work / (case['name'] + '-out')
        probe(source, case.get('password'), output)
        actual = {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob('*') if p.is_file()}
        check(actual == expected_files(case), case['name'] + ': exact extracted bytes')
        check(all((output / name).is_dir() for name in case.get('expected_directories', ['folder'])), case['name'] + ': directory')
        valid.append((case, source))

    embedded_case, embedded_source = next((c, s) for c, s in valid if c['embedded_catalog'] and c['flags'] == 6)
    standalone_case, standalone_source = next((c, s) for c, s in valid if c.get('password') == 'secret')
    credential = embedded_case['current_password']
    check(credential == 'molebox-md5:' + hashlib.md5(b'secret').hexdigest(), 'colon-prefixed exact credential')
    before = tree_state(work)
    stdout = probe(standalone_source, credential)
    check('password_detect=2766\n' in stdout and 'password=' + credential + '\n' in stdout, 'credential reuse standalone')
    stdout = probe(embedded_source, 'wrong explicit password')
    check('password=' + credential + '\n' in stdout, 'embedded fallback publishes actual key')
    probe(standalone_source, 'wrong password', success=False)
    for invalid in ('molebox-md5:1234', 'molebox-md5:' + 'z' * 32, 'molebox-md5' + credential[12:]):
        probe(standalone_source, invalid, success=False)
    check(tree_state(work) == before, 'credential tests wrote to disk')
    probe(embedded_source, memory=32768, success=False)
    probe(embedded_source, maximum=1024, success=False)
    probe(embedded_source, cancelled=True, success=False)

    for case in vectors['malformed']:
        source = work / ('bad-' + case['name'] + '.svfs')
        source.write_bytes(base64.b64decode(case['archive']))
        fixtures.append(source.name)
        before = tree_state(work)
        probe(source, case.get('password'), success=False)
        check(tree_state(work) == before, case['name'] + ': malformed RAM TEST wrote files')
        if case.get('reject_writes'):
            output = work / ('bad-' + case['name'] + '-out')
            probe(source, case.get('password'), output, success=False)
            check(not any(p.is_file() for p in output.rglob('*')), case['name'] + ': corrupt member opened output')

    archive = embedded_source.read_bytes()
    for length in (0, 1, 7, 31, 47, 63, len(archive) - 1, len(archive) - 8, len(archive) - 48):
        source = work / ('truncated-' + str(length) + '.svfs')
        source.write_bytes(archive[:length])
        fixtures.append(source.name)
        probe(source, success=False)

    if args.cli:
        for case, source in valid:
            for name in (source, source.with_suffix('.xfu-renamed')):
                if name != source:
                    name.write_bytes(source.read_bytes())
                    fixtures.append(name.name)
                extra = ['-p' + case['password']] if case.get('password') else []
                before = tree_state(work)
                stdout = run([args.cli, 't', name, *extra])
                percentages = [int(x) for x in re.findall(r'^\s*(\d+)%\s*$', stdout, re.M)]
                check(percentages and percentages[-1] == 100 and percentages == sorted(set(percentages)), 'CLI total progress')
                check(all(re.fullmatch(r'\s*\d+%\s*', line) for line in stdout.splitlines() if line.strip()), 'quiet CLI percentages only')
                check(tree_state(work) == before, 'CLI RAM TEST changed files')
                output = work / (name.name + '-cli-out')
                run([args.cli, 'x', name, '-o' + str(output), *extra])
                actual = {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob('*') if p.is_file()}
                check(actual == expected_files(case), 'CLI exact extraction')
        before = tree_state(work)
        stdout = run([args.cli, '--get-password', embedded_source])
        check('Password: ' + credential in stdout, 'CLI recovered current key')
        run([args.cli, 't', standalone_source, '-p' + credential])
        check(tree_state(work) == before, 'CLI credential retrieval/reuse writes')
        for case in vectors['malformed']:
            run([args.cli, 't', work / ('bad-' + case['name'] + '.svfs'), '--reader=molebox'], False)

    report = {'checks': checks, 'fixtures': len(fixtures), 'cli_checked': bool(args.cli),
              'fixture_names': fixtures, 'producer': vectors.get('producer'),
              'coverage': ['stored/zlib', 'Blowfish CBC', 'default/supplied/embedded MD5 keys',
                           'public/hidden names', 'cursor-preserving password detection',
                           'password options and stale iterators', 'RAM TEST', 'malformed trees/blocks',
                           'memory/member limits', 'cancellation', 'byte-exact original writer vectors']}
    report_path = work / 'uniextract-molebox-report.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'checks': checks, 'fixtures': len(fixtures), 'report': str(report_path)}))


if __name__ == '__main__':
    main()
