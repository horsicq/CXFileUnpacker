"""Verify automatic reader selection, payload bytes and TEST's console contract."""
import argparse
import base64
from collections import Counter
from email.message import EmailMessage
import json
import os
from pathlib import Path
import re
import sqlite3
import struct
import subprocess
import uuid
from document_engine_regression import pdf, ATTACHMENT
from ue2_documents_regression import mo, qm, hlp
import ue2_games_regression as game
import uniextract_archive_regression as archive
import uniextract_bitrock_regression as bitrock
import smart_install_maker_regression as sim


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--xfu', required=True)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    root = args.root / ('run-' + uuid.uuid4().hex)
    root.mkdir(parents=True)
    blocked = root / 'blocked-temp'
    blocked.write_bytes(b'not a directory')
    env = dict(os.environ, TEMP=str(blocked), TMP=str(blocked))
    cases, checks = [], 0

    def verify(name, data, expected=None, password=None):
        nonlocal checks
        for suffix in (Path(name).suffix, '.xfuunknown'):
            source = root / (name if suffix == Path(name).suffix else name + suffix)
            source.write_bytes(data)
            extra = ['-p' + password] if password else []
            before = {str(p): p.stat().st_size for p in root.rglob('*') if p.is_file()}
            quiet = subprocess.run([args.xfu, 't', str(source), *extra], env=env, capture_output=True, text=True, timeout=180)
            assert quiet.returncode == 0, (source, quiet.stdout, quiet.stderr)
            lines = quiet.stdout.splitlines()
            assert lines and all(re.fullmatch(r'\s*\d+%\s*', line) for line in lines), (source, lines)
            values = [int(line.strip()[:-1]) for line in lines]
            assert values == sorted(set(values)) and values[-1] == 100
            verbose = subprocess.run([args.xfu, 't', str(source), '--verbose', *extra], env=env, capture_output=True, text=True, timeout=180)
            assert verbose.returncode == 0 and ' -- OK' in verbose.stdout, (source, verbose.stdout, verbose.stderr)
            assert not any(re.fullmatch(r'\s*\d+%\s*', line) for line in verbose.stdout.splitlines())
            assert before == {str(p): p.stat().st_size for p in root.rglob('*') if p.is_file()}, 'TEST wrote files'
            assert source.read_bytes() == data
            out = root / (source.name + '-out')
            extracted = subprocess.run([args.xfu, 'x', str(source), '-o' + str(out), *extra], env=env, capture_output=True, text=True, timeout=180)
            assert extracted.returncode == 0, (source, extracted.stdout, extracted.stderr)
            actual = [p.read_bytes() for p in out.rglob('*') if p.is_file()]
            assert actual
            if expected is not None:
                assert Counter(actual) == Counter(expected), (source, [len(v) for v in actual], [len(v) for v in expected])
            cases.append(dict(source=source.name, members=len(actual), automatic=True, ram_test=True))
            checks += 10
        return out

    payload = bytes(range(256)) * 3
    verify('resources.pak', archive.pak(5, 0, {1: payload, 7: b''}), [payload, b''])
    image = game.png()
    verify('thumbcache.db', archive.thumbnail(32, image), [image])
    verify('package.evb', archive.enigma(False, [('payload.bin', payload, len(payload))]), [payload])
    verify('bruns.png', game.bruns(image, True), [image])
    verify('resource.rpgmvp', game.rpg(image, bytes(range(16))), [image])
    verify('image.utage', game.utage(image), [image])
    encoded, bmp = game.ycg(bytes(range(16)))
    verify('image.ycg', encoded, [bmp])
    items = [('folder/a.bin', payload, True), ('b.txt', b'game payload', False)]
    verify('unreal.pak', game.pak(7, items), [payload, b'game payload'])
    verify('fallout.dat', game.fallout(items), [payload, b'game payload'])
    verify('smile.sgbpack', game.smile(items), [payload, b'game payload'])
    encoded, bmp = game.gal(107, True, True)
    verify('image.gal', encoded, [bmp])
    verify('messages.mo', mo({b'Hello': b'Hallo'}, '<'))
    verify('translation.qm', qm())
    encoded, members = hlp()
    verify('help.hlp', encoded, list(members.values()))
    message = EmailMessage()
    message['From'] = 'source@example.org'
    message.set_content('MIME body')
    message.add_attachment(payload, maintype='application', subtype='octet-stream', filename='payload.bin')
    verify('message.eml', message.as_bytes(), [b'MIME body\n', payload])
    db = root / 'database.sqlite'
    conn = sqlite3.connect(db)
    conn.execute('CREATE TABLE data(value BLOB)')
    conn.execute('INSERT INTO data VALUES(?)', (payload,))
    conn.commit()
    conn.close()
    out = verify('dump.sqlite', db.read_bytes())
    conn = sqlite3.connect(':memory:')
    conn.executescript(next(out.rglob('*.sql')).read_text(encoding='utf8'))
    assert conn.execute('SELECT value FROM data').fetchone()[0] == payload
    conn.close()
    out = verify('document.pdf', pdf())
    assert (out / 'attachments/0-payload.bin').read_bytes() == ATTACHMENT
    assert b'Hello PDF' in (out / 'pages/page-1.txt').read_bytes()
    # Majiro is selected by the new GARbro fallback, without a --reader key.
    expected = {'a.txt': b'new archive payload', 'folder/b.bin': payload}
    names = b''.join(n.encode() + b'\0' for n in expected)
    names_at = 28 + 12 * len(expected)
    data_at = names_at + len(names)
    table, offset = b'', 0
    for content in expected.values():
        table += struct.pack('<III', 0, data_at + offset, len(content))
        offset += len(content)
    verify('majiro.arc', b'MajiroArcV2.000\0' + struct.pack('<III', len(expected), names_at, data_at) + table + names + b''.join(expected.values()) + b'\0', list(expected.values()))
    vectors = json.loads(Path(__file__).with_name('uniextract_lit_vectors.json').read_text())
    for case in vectors['cases']:
        verify(case['name'] + '.lit', base64.b64decode(case['archive']), [base64.b64decode(value) for value in case['expected_files'].values()])
    for method in (0, 1, 2, 255):
        entries = [('folder', [('payload.bin', ((0, 0, len(payload)),)), ('empty', ())])]
        encoded, _ = bitrock.build([payload], entries, method, method)
        verify('bitrock-' + str(method) + '.exe', encoded, [payload, b''])
    for mode, method in [('stored', 0), ('cab', 1), ('cab', 3)]:
        encoded, expected = sim.fixture([('@$&%04\\payload.bin', payload), ('C:\\folder\\empty', b'')], mode, method)
        verify('sim-' + mode + '-' + str(method) + '.exe', encoded, list(expected.values()))
    formats = subprocess.run([args.xfu, 'i'], capture_output=True, text=True, timeout=30)
    assert formats.returncode == 0 and all(word in formats.stdout for word in ['Chromium DataPack', 'Microsoft Reader LIT', 'MIME email', 'GARbro game archive'])
    report = dict(passed=True, checks=checks + 5, cases=cases)
    path = root / 'uniextract-cli-report.json'
    path.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(dict(passed=True, checks=report['checks'], fixtures=len(cases), report=str(path))))


if __name__ == '__main__':
    main()
