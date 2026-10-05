"""Byte-exact exports and independent gettext/Qt/SQLite/MIME interoperability."""
import argparse
import ast
import base64
import email.policy
from email.message import EmailMessage
import gettext
import io
import json
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import uuid
import xml.etree.ElementTree as ET


def mo(items, endian):
    ordered = sorted(items.items())
    count = len(ordered)
    offset = 28 + count * 16
    original, translated, payload = [], [], bytearray()
    for key, value in ordered:
        original.append((len(key), offset + len(payload)))
        payload += key + b'\0'
    for key, value in ordered:
        translated.append((len(value), offset + len(payload)))
        payload += value + b'\0'
    pack = lambda *v: struct.pack(endian + 'I' * len(v), *v)
    return pack(0x950412de, 0, count, 28, 28 + count * 8, 0, 0) + b''.join(pack(*x) for x in original + translated) + payload


def po_entries(data):
    entries, current = [], {}
    for line in data.decode('utf8').splitlines() + ['']:
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        label, value = line.split(' ', 1)
        current[label] = ast.literal_eval(value)
    return entries


def qm():
    magic = bytes.fromhex('3cb86418caef9c95cd211cbf60a1bddd')
    be = lambda n: struct.pack('>I', n)
    tag = lambda kind, data: bytes([kind]) + be(len(data)) + data
    records = (tag(3, 'Hallo 🌍'.encode('utf-16be')) + tag(8, b'comment') + tag(6, b'Hello') + tag(7, b'Window') + b'\1'
               + tag(3, '%n Datei'.encode('utf-16be')) + tag(3, '%n Dateien'.encode('utf-16be')) + tag(6, b'%n files') + tag(7, b'Files') + b'\1')
    second = records.index(tag(3, '%n Datei'.encode('utf-16be')))
    return magic + tag(0xa7, b'de_DE') + tag(0x42, be(123) + be(0) + be(456) + be(second)) + tag(0x69, records)


def hlp():
    payloads = {'|SYSTEM': b'\x6c\x03' + bytes(range(20)), '|TOPIC': b'Help topic payload\0\xff'}
    data = bytearray(16)
    offsets = {}
    for name, content in payloads.items():
        offsets[name] = len(data)
        data += struct.pack('<IIB', 9 + len(content), len(content), 0) + content
    directory = len(data)
    entries = b''.join(name.encode() + b'\0' + struct.pack('<I', offset) for name, offset in offsets.items())
    page = struct.pack('<HHHH', 256 - 8 - len(entries), len(payloads), 0xffff, 0xffff) + entries
    page += b'\0' * (256 - len(page))
    header = bytearray(38)
    struct.pack_into('<HHH', header, 0, 0x293b, 0x0402, 256)
    header[6:9] = b'z4\0'
    struct.pack_into('<HHHHI', header, 26, 0, 0xffff, 1, 1, len(payloads))
    body = header + page
    data += struct.pack('<IIB', 9 + len(body), len(body), 0) + body
    struct.pack_into('<IIII', data, 0, 0x00035f3f, directory, 0xffffffff, len(data))
    return bytes(data), payloads


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--lconvert', type=Path)
    args = parser.parse_args()
    root = args.root / ('run-' + uuid.uuid4().hex)
    root.mkdir(parents=True)
    blocked = root / 'blocked-temp'
    blocked.write_bytes(b'not a directory')
    env = dict(os.environ, TEMP=str(blocked), TMP=str(blocked))
    cases = []

    def run(name, data, kind, valid=True, memory=None):
        source = root / name
        source.write_bytes(data)
        before = sorted(str(p.relative_to(root)) for p in root.rglob('*'))
        command = [str(args.probe), str(source), str(kind)]
        if memory is not None:
            command += ['', str(memory)]
        checked = subprocess.run(command, capture_output=True, text=True, env=env, timeout=60)
        assert (checked.returncode == 0) == valid, (name, checked.stdout, checked.stderr)
        assert before == sorted(str(p.relative_to(root)) for p in root.rglob('*')), name
        assert source.read_bytes() == data
        result = {'name': name, 'accepted': valid, 'test_created_no_files': True}
        actual = {}
        if valid:
            result.update(json.loads(checked.stdout))
            output = root / (name + '-out')
            extracted = subprocess.run([str(args.probe), str(source), str(kind), str(output)], capture_output=True, text=True, env=env, timeout=60)
            assert extracted.returncode == 0, (name, extracted.stdout, extracted.stderr)
            actual = {p.name.split('-', 1)[1]: p.read_bytes() for p in output.rglob('*') if p.is_file()}
        cases.append(result)
        return actual

    items = {b'': b'Content-Type: text/plain; charset=UTF-8\nPlural-Forms: nplurals=2; plural=(n != 1);\n',
             b'Hello': 'Hallo 🌍'.encode(), b'Window\x04Open': b'Offnen', b'file\0files': b'Datei\0Dateien', b'escaped': b'line\n\t\\"value'}
    for endian in ('<', '>'):
        data = mo(items, endian)
        original = gettext.GNUTranslations(io.BytesIO(data))
        actual = run('messages-%s.mo' % ('le' if endian == '<' else 'be'), data, 2740)
        entries = po_entries(actual['messages.po'])
        for item in entries:
            msgid = item['msgid']
            if not msgid:
                continue
            if 'msgctxt' in item:
                assert item['msgstr'] == original.pgettext(item['msgctxt'], msgid)
            elif 'msgid_plural' in item:
                assert item['msgstr[0]'] == original.ngettext(msgid, item['msgid_plural'], 1)
                assert item['msgstr[1]'] == original.ngettext(msgid, item['msgid_plural'], 2)
            else:
                assert item['msgstr'] == original.gettext(msgid)
        run('mo-truncated-%s.mo' % endian.replace('>', 'be').replace('<', 'le'), data[:-1], 2740, False)
    run('mo-memory.mo', mo(items, '<'), 2740, False, 128)

    q = qm()
    actual = run('translation.qm', q, 2741)
    ts = ET.fromstring(actual['messages.ts'])
    assert ts.attrib['language'] == 'de_DE'
    assert ts.find('context/message/translation').text == 'Hallo 🌍'
    assert [x.text for x in ts.findall('context/message/translation/numerusform')] == ['%n Datei', '%n Dateien']
    run('qm-truncated.qm', q[:-1], 2741, False)
    if args.lconvert:
        source_ts = root / 'original.ts'
        source_ts.write_text('<?xml version="1.0" encoding="utf-8"?><TS version="2.1" language="de_DE"><context><name>Window</name><message><source>Hello</source><translation>Hallo 🌍</translation></message></context></TS>', encoding='utf8')
        source_qm = root / 'official.qm'
        subprocess.run([str(args.lconvert), '-i', str(source_ts), '-o', str(source_qm)], check=True, capture_output=True)
        actual = run('official-copy.qm', source_qm.read_bytes(), 2741)
        tree = ET.fromstring(actual['messages.ts'])
        assert tree.find('context/message/translation').text == 'Hallo 🌍'

    msg = EmailMessage(policy=email.policy.SMTP)
    msg['From'] = 'source@example.org'
    msg['To'] = 'destination@example.org'
    msg['Subject'] = 'MIME extraction'
    msg.set_content('message body')
    msg.add_alternative('<html><body>HTML 🌍</body></html>', subtype='html')
    attachment = bytes(range(256)) * 5
    msg.add_attachment(attachment, maintype='application', subtype='octet-stream', filename='payload.bin')
    actual = run('multipart.eml', msg.as_bytes(), 2742)
    assert actual['payload.bin'] == attachment
    assert b'message body' in actual['body.txt']
    assert 'HTML 🌍' in actual['body.html'].decode()
    run('mime-bad-boundary.eml', msg.as_bytes()[:-60], 2742, False)
    actual = run('quoted-printable.mht', b'Content-Type: text/html\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\nhello=20world=0A', 2742)
    assert actual['body.html'] == b'hello world\n'
    run('mime-bad-base64.eml', b'Content-Type: application/octet-stream\nContent-Transfer-Encoding: base64\n\nQQ=A', 2742, False)
    run('mime-unknown-encoding.eml', b'Content-Type: text/plain\nContent-Transfer-Encoding: invented\n\nA', 2742, False)
    help_data, help_payloads = hlp()
    actual = run('help.hlp', help_data, 2743)
    assert actual == {name.replace('|', '_'): payload for name, payload in help_payloads.items()}
    run('help-truncated.hlp', help_data[:-1], 2743, False)
    bad = bytearray(help_data)
    directory = struct.unpack_from('<I', bad, 4)[0]
    struct.pack_into('<H', bad, directory + 47 + 6, 0)
    run('help-loop.hlp', bad, 2743, False)

    for encoding in ('UTF-8', 'UTF-16le'):
        dbpath = root / ('original-' + encoding + '.sqlite')
        conn = sqlite3.connect(dbpath)
        conn.execute("PRAGMA encoding='%s'" % encoding)
        conn.executescript('CREATE TABLE data(id INTEGER PRIMARY KEY, txt TEXT, b BLOB, r REAL, generated INTEGER GENERATED ALWAYS AS (id+1));CREATE INDEX idx ON data(txt);CREATE VIEW view_data AS SELECT id FROM data;')
        conn.execute('INSERT INTO data(id,txt,b,r) VALUES(?,?,?,?)', (1, 'Hello 🌍\0tail', bytes(range(256)), 1.2345678901234567))
        conn.execute('INSERT INTO data(id,txt,b,r) VALUES(?,?,?,?)', (2, "quote'", b'', -1.0e-30))
        conn.executescript('CREATE TABLE sequence_test(id INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT);INSERT INTO sequence_test(id,value) VALUES(100,\'past maximum\');DELETE FROM sequence_test;CREATE TABLE sqliteX(\"VIRTUAL\" TEXT DEFAULT \'VIRTUAL\');INSERT INTO sqliteX DEFAULT VALUES;')
        conn.commit()
        original = conn.execute('SELECT * FROM data ORDER BY id').fetchall()
        conn.close()
        actual = run('dump-' + encoding + '.sqlite', dbpath.read_bytes(), 650)
        restored = sqlite3.connect(':memory:')
        restored.executescript(actual['database.sql'].decode())
        assert original == restored.execute('SELECT * FROM data ORDER BY id').fetchall()
        assert restored.execute('SELECT * FROM view_data ORDER BY id').fetchall() == [(1,), (2,)]
        assert restored.execute('SELECT * FROM sqliteX').fetchall() == [('VIRTUAL',)]
        restored.execute('INSERT INTO sequence_test(value) VALUES(\'after restore\')')
        assert restored.execute('SELECT id FROM sequence_test').fetchone()[0] == 101
        restored.close()
        run('sqlite-truncated-' + encoding + '.db', dbpath.read_bytes()[:-1], 650, False)
    run('sqlite-memory.db', dbpath.read_bytes(), 650, False, 2048)
    report = {'cases': cases, 'fixtures': len(cases), 'all_passed': True, 'independent_interoperability': ['Python gettext', 'Qt lconvert' if args.lconvert else 'Qt documented wire grammar', 'Python email', 'Python SQLite SQL restore']}
    target = root / 'ue2-documents-report.json'
    target.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({'report': str(target), 'fixtures': len(cases), 'all_passed': True}))


if __name__ == '__main__':
    main()
