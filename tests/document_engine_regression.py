"""Independent PDF syntax fixtures, embedded bytes, passwords and RAM TEST."""
import argparse
import json
import os
from pathlib import Path
import struct
import shutil
import subprocess
import uuid
import zlib

ATTACHMENT = bytes(range(256)) * 3 + b'PDF attachment\x00\xff'


def pdf():
    objects = [b'<< /Type /Catalog /Pages 2 0 R /Names << /EmbeddedFiles << /Names [(payload.bin) 9 0 R] >> >> >>',
               b'<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 144 72] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    def stream(content, extra=b''):
        data = zlib.compress(content)
        return b'<< /Length %d /Filter /FlateDecode ' % len(data) + extra + b'>>\nstream\n' + data + b'\nendstream'
    objects += [stream(b'BT /F1 12 Tf 12 36 Td (Hello PDF) Tj ET'),
                b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] /Resources << /Font << /F1 4 0 R >> >> /Contents 7 0 R >>',
                stream(b'BT /F1 12 Tf 6 36 Td (Page Two) Tj ET'),
                stream(ATTACHMENT, b'/Type /EmbeddedFile '),
                b'<< /Type /Filespec /F (payload.bin) /EF << /F 8 0 R >> >>']
    output = bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += b'%d 0 obj\n' % index + obj + b'\nendobj\n'
    xref = len(output)
    output += b'xref\n0 %d\n0000000000 65535 f \n' % len(offsets)
    output += b''.join(b'%010d 00000 n \n' % pos for pos in offsets[1:])
    output += b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(offsets), xref)
    return bytes(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', required=True)
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    root = Path(args.root) / ('run-' + uuid.uuid4().hex)
    root.mkdir(parents=True)
    blocked_temp = root / 'temporary-file'
    blocked_temp.write_bytes(b'not a directory')
    env = dict(os.environ, TEMP=str(blocked_temp), TMP=str(blocked_temp))
    reports = []
    checks = 0
    def run(path, mode='test', password='-', extract=None):
        nonlocal checks
        before = set(root.rglob('*'))
        command = [args.probe, str(path), mode, password]
        if extract:
            command.append(str(extract))
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, (command, result.stdout, result.stderr)
        report = json.loads(result.stdout)
        checks += report['checks']
        if extract is None:
            assert set(root.rglob('*')) == before, 'RAM TEST created files'
            checks += 1
        reports.append(dict(file=path.name, mode=mode, **report))
    valid = root / 'attachment-and-pages.pdf'
    valid.write_bytes(pdf())
    run(valid)
    out = root / 'decoded'
    run(valid, extract=out)
    assert (out / 'attachments/0-payload.bin').read_bytes() == ATTACHMENT
    for page, expected, size in [(1, b'Hello PDF', (192, 96)), (2, b'Page Two', (96, 96))]:
        assert expected in (out / f'pages/page-{page}.txt').read_bytes()
        image = (out / f'pages/page-{page}.bmp').read_bytes()
        assert image[:2] == b'BM' and struct.unpack_from('<I', image, 2)[0] == len(image)
        assert struct.unpack_from('<ii', image, 18) == (size[0], -size[1])
        pixels = struct.unpack_from('<I', image, 10)[0]
        assert pixels >= 54 and any(image[at:at+3] != b'\xff\xff\xff' for at in range(pixels, len(image), 4))
        checks += 5
    checks += 1
    invalid = root / 'invalid.pdf'
    invalid.write_bytes(b'%PDF-1.7\nnot a PDF structure')
    run(invalid, 'reject')
    protected = Path(__file__).parent / 'fixtures/pdf-password-rc4.pdf'
    run(protected, 'reject')
    run(protected, 'reject', 'wrong-password')
    encrypted_out = root / 'password-decoded'
    run(protected, password='xfu-pdf-secret', extract=encrypted_out)
    assert (encrypted_out / 'attachments/0-payload.bin').read_bytes() == ATTACHMENT
    assert b'Hello PDF' in (encrypted_out / 'pages/page-1.txt').read_bytes()
    checks += 2
    # A modified runtime is rejected before PDFium is loaded.
    runtime = root / 'bad-runtime'
    runtime.mkdir()
    original_probe = args.probe
    probe_path = Path(args.probe)
    for name in (probe_path.name, 'xfu_document_helper.exe', 'xfupdfium.dll'):
        shutil.copy2(probe_path.parent / name, runtime / name)
    dll = runtime / 'xfupdfium.dll'
    with dll.open('r+b') as stream:
        stream.seek(-1, 2)
        last = stream.read(1)
        stream.seek(-1, 2)
        stream.write(bytes([last[0] ^ 1]))
    args.probe = str(runtime / probe_path.name)
    run(valid, 'reject')
    args.probe = original_probe
    report = dict(passed=True, checks=checks, cases=reports, fixture_origin='Independent PDF syntax; encrypted fixture produced by pypdf 6.1.3 RC4-128')
    (root / 'document-engine-report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(dict(passed=True, checks=checks, report=str(root / 'document-engine-report.json'))))


if __name__ == '__main__':
    main()
