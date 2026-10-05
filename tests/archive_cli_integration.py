#!/usr/bin/env python3
"""End-to-end registration/decoding checks for the 26 archive additions.

Fixtures are independent wire builders or retained author-compressed vectors.
Only the unpacker and its codec helper run; no archived program is executed.
TEST runs with every conventional temporary-directory variable pointing at a
regular file and its complete working tree is compared before/after each run.
The native companion suite additionally enforces the library's RAM-only guard.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
import os
import pathlib
import re
import subprocess
import time

import archive_additions
import archive_secondwave
import archive_wrappers


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree(path: pathlib.Path) -> dict:
    result = {}
    for item in sorted(path.rglob('*')):
        if item.is_symlink():
            raise AssertionError('unexpected symlink in controlled working tree')
        name = item.relative_to(path).as_posix()
        stat = item.stat()
        result[name] = ('directory',) if item.is_dir() else (
            'file', stat.st_size, stat.st_mtime_ns, sha(item.read_bytes()))
    return result


def fixture_cases() -> tuple[list[dict], list[dict]]:
    first = [archive_secondwave.fixture(name, reader, data, payloads, valid)
             for reader, name, data, payloads, valid in archive_additions.fixtures()
             if reader not in ('lha', 'dms')]
    retained = json.loads(pathlib.Path(__file__).with_name(
        'archive_secondwave_fixtures.json').read_text(encoding='utf-8'))['fixtures']
    second = retained + archive_secondwave.independent_fixtures()
    wrappers = archive_wrappers.cases()
    positives = [case for case in first + wrappers if case['accepted'] is True]
    # All matching PAQ revisions, all GRZip modes, each LRZIP codec/checksum
    # contract, plus one binary fixture for each remaining second-wave reader.
    positives += [case for case in second if case['accepted'] is True and (
        case['reader'] in ('lrzip', 'grzip') or
        case['name'].endswith('-binary') or
        case['name'] in ('paq8-multiple', 'paq8-stored-overlapping-exe-filter',
                         'lpaq8-buffer-crossing-exe'))]
    negatives = []
    for reader in sorted({case['reader'] for case in positives}):
        choices = [case for case in first + second + wrappers
                   if case['reader'] == reader and case['accepted'] is False]
        if not choices:
            raise AssertionError('missing malformed fixture for ' + reader)
        # Keep framing valid where an independently defined checksum exists.
        negatives.append(next((case for case in choices
                               if 'checksum' in case['name'] or 'crc' in case['name']),
                              choices[0]))
    return positives, negatives


def invoke(command: list[str], cwd: pathlib.Path, environment: dict) -> dict:
    began = time.monotonic()
    try:
        process = subprocess.run(command, cwd=cwd, env=environment,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=120, check=False)
        return {'command': command, 'returncode': process.returncode,
                'stdout': process.stdout.decode('utf-8', 'replace').replace('\r\n', '\n'),
                'stderr': process.stderr.decode('utf-8', 'replace').replace('\r\n', '\n'),
                'seconds': round(time.monotonic() - began, 3)}
    except subprocess.TimeoutExpired as error:
        return {'command': command, 'returncode': None, 'timeout': True,
                'stdout': (error.stdout or b'').decode('utf-8', 'replace'),
                'stderr': (error.stderr or b'').decode('utf-8', 'replace'),
                'seconds': round(time.monotonic() - began, 3)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xfu', type=pathlib.Path, required=True)
    parser.add_argument('--probe-readers', type=pathlib.Path, required=True)
    parser.add_argument('--manifest', type=pathlib.Path, required=True)
    parser.add_argument('--work-dir', type=pathlib.Path, required=True)
    args = parser.parse_args()
    xfu, probe = args.xfu.resolve(), args.probe_readers.resolve()
    work = args.work_dir.resolve()
    if work.exists() and any(work.iterdir()):
        parser.error('--work-dir must be absent or empty; existing data is never removed')
    work.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    readers = {item['stem']: item for item in manifest['readers']}
    assert len(readers) == 26, 'expected the frozen 26-reader batch'
    positives, negatives = fixture_cases()
    assert set(readers) <= {case['reader'] for case in positives}
    rows = []
    issues = []
    report = {'xfu': str(xfu), 'xfu_sha256': sha(xfu.read_bytes()),
              'probe': str(probe), 'probe_sha256': sha(probe.read_bytes()),
              'helper_sha256': sha(xfu.with_name('xfu_archive_codec_helper.exe').read_bytes()),
              'registered_readers': sorted(readers), 'cases': rows, 'issues': issues,
              'contract': 'TEST fully decodes without output/temp artifacts; exact payload SHA comparison; no archived programs run'}

    def checkpoint():
        report['case_count'] = len(rows)
        report['passed_cases'] = sum(bool(row['passed']) for row in rows)
        (work / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

    catalog = invoke([str(xfu), 'i', '--color=never'], work, os.environ.copy())
    missing = [item['type_string'] for item in readers.values()
               if not re.search(r'\b' + re.escape(item['type_string']) + r'\b', catalog['stdout'])]
    catalog_ok = catalog['returncode'] == 0 and not missing
    rows.append({'kind': 'catalog', 'passed': catalog_ok, 'missing': missing, 'result': catalog})
    if not catalog_ok:
        issues.append('catalog does not register all 26 additions')
    checkpoint()

    for number, case in enumerate(positives + negatives, 1):
        reader = case['reader']
        folder = work / ('%03d-%s-%s' % (number, reader, case['name']))
        folder.mkdir()
        source = folder / 'archive.unknown'  # Avoid extension-based identification.
        data = base64.b64decode(case['data'])
        source.write_bytes(data)
        temp_guard = folder / 'temp-is-a-file'
        temp_guard.write_bytes(b'No archive testing temporary directories.\n')
        environment = os.environ.copy()
        for key in ('TEMP', 'TMP', 'TMPDIR'):
            environment[key] = str(temp_guard)
        before = tree(folder)
        operations = []
        failures = []
        accepted = case['accepted'] is True
        partial = accepted and reader == 'lhwarp'
        expected_code = 1 if partial else 0

        def checked(command):
            result = invoke(command, folder, environment)
            operations.append(result)
            if tree(folder) != before:
                failures.append('read/list/TEST mutated the working tree')
            return result

        if accepted:
            expected_type = readers[reader]['type_string'] if reader in readers else 'LPAQ8'
            diagnostic = checked([str(probe), str(source), reader])
            valid_line = r'^' + re.escape(reader) + r' type=' + re.escape(expected_type) + r' valid=1 parsed=1 archive=1 incomplete=' + ('1' if partial else '0') + r'$'
            if diagnostic['returncode'] != 0 or not re.search(valid_line, diagnostic['stdout'], re.M):
                failures.append('named registry validation/type/completeness mismatch')
            if reader != 'quad':
                # QUAD has no unique signature; it requires explicit selection.
                if not re.search(r'^detected=' + re.escape(expected_type) + r'$', diagnostic['stdout'], re.M):
                    failures.append('strong-signature automatic detection mismatch')
                automatic = checked([str(xfu), 't', str(source)])
                if automatic['returncode'] != expected_code:
                    failures.append('automatic TEST exit status mismatch')

            result = checked([str(xfu), 't', str(source), '--reader', reader])
            percentages = result['stdout'].splitlines()
            values = [int(line[:-1]) for line in percentages if re.fullmatch(r'\d{1,3}%', line)]
            if result['returncode'] != expected_code:
                failures.append('named TEST exit status mismatch')
            if len(values) != len(percentages) or not values or values != sorted(set(values)) or any(value > 100 for value in values):
                failures.append('default TEST did not emit monotone percentage-only output')
            if partial:
                if 100 in values or 'incomplete archive' not in result['stderr']:
                    failures.append('partial image presented as complete')
            elif not values or values[-1] != 100:
                failures.append('complete TEST omitted final 100 percent')

            verbose = checked([str(xfu), 't', str(source), '--reader', reader, '--verbose'])
            lines = verbose['stdout'].splitlines()
            if verbose['returncode'] != expected_code or len(lines) != len(case['outputs']) or any(not line.endswith(' -- OK') for line in lines):
                failures.append('verbose TEST member results mismatch')
            output = folder / 'extracted'
            extracted = invoke([str(xfu), 'x', str(source), '--reader', reader, '-o' + str(output)], folder, environment)
            operations.append(extracted)
            hashes = Counter(sha(path.read_bytes()) for path in output.rglob('*') if path.is_file())
            expected_hashes = Counter(sha(base64.b64decode(payload)) for payload in case['outputs'])
            if extracted['returncode'] != expected_code or hashes != expected_hashes:
                failures.append('extraction status or exact member payloads differ')
        else:
            result = checked([str(xfu), 't', str(source), '--reader', reader])
            if result['returncode'] not in (1, 2) or re.search(r'^100%$', result['stdout'], re.M):
                failures.append('malformed/checksum fixture reported TEST success')

        stat = source.stat()
        if sha(source.read_bytes()) != sha(data) or stat.st_size != len(data) or stat.st_mtime_ns != before['archive.unknown'][2]:
            failures.append('input bytes/size/mtime changed')
        row = {'kind': 'valid' if accepted else 'malformed', 'name': case['name'],
               'reader': reader, 'partial': partial, 'passed': not failures,
               'source_sha256': sha(data),
               'expected_payload_sha256': [sha(base64.b64decode(payload)) for payload in case['outputs']],
               'failures': failures, 'operations': operations}
        rows.append(row)
        issues.extend('%s/%s: %s' % (reader, case['name'], failure) for failure in failures)
        checkpoint()
        print(('%s %s/%s' % ('PASS' if not failures else 'FAIL', reader, case['name'])), flush=True)
    report['complete'] = True
    checkpoint()
    print('%d/%d CLI integration cases passed' % (report['passed_cases'], report['case_count']), flush=True)
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
