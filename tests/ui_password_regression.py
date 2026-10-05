"""Real GUI/TUI password controls; independent data-only fixtures are never run."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile
import zipfile

from ad01_encryption_regression import (
    entries, package, encoded_adx, STUB_PASSWORD, PAYLOAD_PASSWORD,
)
from password_options import archive


def files_under(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in folder.rglob('*') if p.is_file()} if folder.exists() else {}


def run(command, cwd, expected=0):
    result = subprocess.run([str(value) for value in command], cwd=cwd,
                            capture_output=True, timeout=30)
    if result.returncode != expected:
        raise AssertionError(f'{command[0].name}: exit {result.returncode}, expected {expected}\n'
                             f'{result.stdout!r}\n{result.stderr!r}')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gui', type=Path)
    parser.add_argument('--tui', type=Path)
    parser.add_argument('--callback-probe', type=Path, required=True)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    frontends = [path.resolve() for path in (args.gui, args.tui) if path]
    if not frontends:
        parser.error('at least one of --gui and --tui is required')
    probe = args.callback_probe.resolve()
    checks = 0
    with tempfile.TemporaryDirectory(prefix='xfu-ui-password-', dir=args.root) as temporary:
        root = Path(temporary)
        hashes = {}
        fixtures = []
        # ADX control bytes and literal backslash notation must reach callback
        # users as different credentials, despite both needing escaped labels.
        for label, stored, encrypted, payload_password in (
            ('embedded-three-stored', 3, True, PAYLOAD_PASSWORD),
            ('embedded-one-stored', 1, True, PAYLOAD_PASSWORD),
            ('embedded-controls', 3, True, b'UI raw\npassword\t#2'),
            ('embedded-literal-slashes', 3, True, b'UI raw\\x0Apassword\\t#2'),
            ('embedded-non-UTF8', 3, True, b'UI raw\xff\x80password#2'),
            ('unencrypted-no-autofill', 3, False, PAYLOAD_PASSWORD),
        ):
            items = entries(stored, adx=encoded_adx(password=payload_password))
            items = [(name, plain, method, payload_password if method == 0 else password)
                     for name, plain, method, password in items]
            image, _ = package(items, encrypted=encrypted)
            source = root / (label + '.exe')
            source.write_bytes(image)
            hashes[source] = hashlib.sha256(image).hexdigest()
            expected = {name: plain for name, plain, _, _ in items}
            # Independent standard ZIP decoder proves each ciphertext/CRC and
            # both expected group credentials, before any frontend is started.
            with zipfile.ZipFile(source) as z:
                for name, plain, _, password in items:
                    assert z.read(name, pwd=password) == plain
            run([probe, source, stored, STUB_PASSWORD.hex(), payload_password.hex(),
                 int(encrypted)], root)
            checks += 1
            fixtures.append((label, source, expected))
        for frontend in frontends:
            for label, source, expected in fixtures:
                output = root / (frontend.stem + '-' + label)
                # Hook drives the real editable control, selection events,
                # manual override, source-change clearing, and normal job path.
                run([frontend, '--smoke-password-embedded', source, '-o' + str(output)], root)
                assert files_under(output) == expected, (frontend.name, label)
                checks += 1
            for label, password, descriptor in (
                ('manual-ascii', b'UI literal spaces #7 \\x0A', False),
                ('manual-unicode', 'UI p\u00e4ss\u03bb #7'.encode(), False),
                ('manual-newline', b'UI raw\npassword#7', False),
                ('manual-descriptor', b'UI descriptor password', True),
                ('manual-empty', b'', False),
            ):
                source = root / (label + '.zip')
                image, expected = archive(password, descriptor=descriptor)
                source.write_bytes(image)
                hashes[source] = hashlib.sha256(image).hexdigest()
                if password:
                    with zipfile.ZipFile(source) as z:
                        assert {name: z.read(name, pwd=password) for name in z.namelist()} == expected
                output = root / (frontend.stem + '-' + label)
                run([frontend, '--smoke-password-manual', source,
                     '-p' + password.decode(), '-o' + str(output)], root)
                assert files_under(output) == expected, (frontend.name, label)
                checks += 1
            # Missing and wrong values cannot publish decrypted bodies. Use a
            # preserved existing destination to exercise ordinary UI safety.
            source = root / 'manual-ascii.zip'
            for label, option in (('missing', None), ('wrong', '-pwrong UI value')):
                output = root / (frontend.stem + '-manual-' + label)
                output.mkdir()
                (output / 'existing.bin').write_bytes(b'preserve existing output')
                command = [frontend, '--smoke-password-manual', source, '-o' + str(output)]
                if option is not None:
                    command.append(option)
                run(command, root, expected=1)
                assert files_under(output) == {'existing.bin': b'preserve existing output'}
                checks += 1
        # Frontend selection/editing/extraction must leave every input intact.
        for source, expected_hash in hashes.items():
            assert hashlib.sha256(source.read_bytes()).hexdigest() == expected_hash, source
    print(f'GUI/TUI password integration: {checks} checks passed; source hashes unchanged')


if __name__ == '__main__':
    main()
