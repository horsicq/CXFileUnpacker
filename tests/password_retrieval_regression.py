"""Password retrieval uses proved metadata and never publishes archive bodies.

The small synthetic AD01 executable files are parsed as data, never executed.
Python's independent ZIP implementation verifies their ciphertext and CRCs.
"""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

from ad01_encryption_regression import (
    entries, package, encoded_adx, STUB_PASSWORD, PAYLOAD_PASSWORD,
)
from password_options import archive


def tree_state(root):
    """Include directories as well as file hashes to catch empty output trees."""
    result = {}
    for path in root.rglob('*'):
        name = path.relative_to(root).as_posix()
        result[name] = ('directory',) if path.is_dir() else (
            'file', path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
    return result


def display_password(password):
    """Specification: preserve UTF-8 text; quote slashes and control bytes."""
    display = []
    for character in password.decode('utf-8', errors='surrogateescape'):
        value = ord(character)
        if character == '\\':
            display.append('\\\\')
        elif 0xdc80 <= value <= 0xdcff:
            display.append(f'\\x{value - 0xdc00:02X}')
        elif value < 32 or 0x7f <= value <= 0x9f:
            display.extend(f'\\x{byte:02X}' for byte in character.encode('utf-8'))
        else:
            display.append(character)
    return ''.join(display).encode('utf-8')


def summary(items, encrypted=True):
    if not encrypted:
        return b'No embedded password found.\n'
    groups = {}
    for _, _, _, password in items:
        groups[password] = groups.get(password, 0) + 1
    return b'\n'.join(
        b'Password: ' + display_password(password) +
        f'\nMembers: {count}\n'.encode('ascii')
        for password, count in groups.items())


def make_fixtures(root):
    fixtures = []
    for label, stored, encrypted, payload_password, stub_password in (
        ('mixed-groups', 3, True, PAYLOAD_PASSWORD, STUB_PASSWORD),
        ('one-stored-group', 1, True, PAYLOAD_PASSWORD, STUB_PASSWORD),
        ('raw-controls', 3, True, b'UI raw\npassword\t#2', STUB_PASSWORD),
        ('literal-backslashes', 3, True, b'UI raw\\x0Apassword\\t#2', STUB_PASSWORD),
        ('raw-non-UTF8', 3, True, b'UI raw\xff\x80password#2', STUB_PASSWORD),
        ('raw-whitespace', 3, True, b'  raw leading and trailing space  ', STUB_PASSWORD),
        ('UTF8-and-C1', 3, True, 'raw p\u00e4ss\u03bb\u0085#2'.encode(), STUB_PASSWORD),
        ('one-distinct-password', 3, True, PAYLOAD_PASSWORD, PAYLOAD_PASSWORD),
        ('unencrypted-no-recovery', 3, False, PAYLOAD_PASSWORD, STUB_PASSWORD),
    ):
        items = entries(stored, adx=encoded_adx(password=payload_password))
        items = [(name, plain, method, payload_password if method == 0 else stub_password)
                 for name, plain, method, _ in items]
        image, _ = package(items, stub=stub_password, encrypted=encrypted)
        source = root / (label + '.exe')
        source.write_bytes(image)
        with zipfile.ZipFile(source) as reference:
            for name, plain, _, password in items:
                assert reference.read(name, pwd=password) == plain, label
        fixtures.append((label, source, summary(items, encrypted), 0 if encrypted else 1))
    return fixtures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--unpacker', type=Path, required=True)
    parser.add_argument('--gui', type=Path)
    parser.add_argument('--tui', type=Path)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    unpacker = args.unpacker.resolve()
    frontends = [path.resolve() for path in (args.gui, args.tui) if path]
    checks = 0
    with tempfile.TemporaryDirectory(prefix='xfu-password-retrieval-', dir=args.root) as temporary:
        root = Path(temporary)
        fixtures = make_fixtures(root)
        caller_password = b'only a caller knows this password'
        caller_source = root / 'ordinary-encrypted.zip'
        image, expected = archive(caller_password)
        caller_source.write_bytes(image)
        with zipfile.ZipFile(caller_source) as reference:
            assert {name: reference.read(name, pwd=caller_password)
                    for name in reference.namelist()} == expected
        clear_source = root / 'ordinary-clear.zip'
        clear_source.write_bytes(archive(b'', encrypted=False)[0])
        unsupported_source = root / 'unknown.bin'
        unsupported_source.write_bytes(b'Independent unrecognized input; no password metadata.\n')
        corrupt_source = root / 'corrupted-AD01.exe'
        corrupt, extents = package(entries())
        corrupt = bytearray(corrupt)
        # Keep the ZipCrypto authentication header intact: the full decoded
        # member CRC, rather than the header check byte, must reject recovery.
        corrupt[extents[0][0] + 12] ^= 0x55
        corrupt_source.write_bytes(corrupt)
        with zipfile.ZipFile(corrupt_source) as reference:
            try:
                reference.read('data.cab', pwd=PAYLOAD_PASSWORD)
            except zipfile.BadZipFile:
                pass
            else:
                raise AssertionError('independent ZIP decoder accepted the corrupted CRC')
        output = root / 'existing-output'
        output.mkdir()
        (output / 'preserve.bin').write_bytes(b'Retrieval must preserve existing output.\n')
        expected_tree = tree_state(root)

        def run(command, expected_exit, expected_stdout=None, env=None):
            nonlocal checks
            result = subprocess.run([str(value) for value in command], cwd=root,
                                    env=env, capture_output=True, timeout=20)
            accepted_exits = (expected_exit,) if isinstance(expected_exit, int) else expected_exit
            if result.returncode not in accepted_exits:
                raise AssertionError(f'{Path(command[0]).name}: exit {result.returncode}, '
                                     f'expected {expected_exit}\n'
                                     f'{result.stdout!r}\n{result.stderr!r}')
            if expected_stdout is not None:
                # The MSVC console uses CRLF; password escapes themselves are
                # literal ASCII and cannot be changed by this normalization.
                assert result.stdout.replace(b'\r\n', b'\n') == expected_stdout, (
                    Path(command[0]).name, result.stdout, expected_stdout)
            assert tree_state(root) == expected_tree, 'retrieval changed files or directories'
            checks += 1
            return result

        # All aliases produce only the password summary, in first-member order.
        # Mixed groups have three members each; a shared raw value is one group
        # with six members, regardless of the different compression methods.
        for _, source, expected_stdout, expected_exit in fixtures:
            for spelling in ([unpacker, '--get-password', source],
                             [unpacker, 'p', source],
                             [unpacker, 'P', source],
                             [unpacker, 'l', source, '--get-password']):
                run(spelling, expected_exit, expected_stdout)
        mixed_source = fixtures[0][1]
        mixed_summary = fixtures[0][2]
        run([unpacker, 'p', mixed_source, '-pwrong caller value'], 0, mixed_summary)
        environment = dict(os.environ, XFU_RETRIEVAL_TEST_PASSWORD='wrong caller environment value')
        run([unpacker, '--get-password', mixed_source,
             '--password-env=XFU_RETRIEVAL_TEST_PASSWORD'], 0, mixed_summary, environment)

        # Even a correct caller credential is not discovered source metadata.
        none = b'No embedded password found.\n'
        for option in (None, '-p' + caller_password.decode(), '-pwrong caller value', '-p'):
            command = [unpacker, 'p', caller_source]
            if option is not None:
                command.append(option)
            result = run(command, 1, none)
            assert caller_password not in result.stderr
        run([unpacker, '--get-password', clear_source], 1, none)

        # Invalid invocations cannot emit an apparently successful summary.
        for command in (
            [unpacker, 'p'],
            [unpacker, '--get-password'],
            [unpacker, 'p', root / 'missing.exe'],
            [unpacker, 'p', unsupported_source],
            [unpacker, 'p', mixed_source, '--unknown-option'],
            [unpacker, 'p', mixed_source, '--get-password'],
            [unpacker, '--get-password', mixed_source, '--get-password'],
            [unpacker, 'l', mixed_source, '--get-password', '--get-password'],
            [unpacker, 'l', mixed_source, '--advanced', '--get-password'],
            [unpacker, 'l', mixed_source, '--get-password', '--advanced'],
            [unpacker, 'p', mixed_source, '-slt'],
            [unpacker, 't', mixed_source, '--get-password'],
            [unpacker, 'p', mixed_source, '-o' + str(output)],
            [unpacker, 'p', mixed_source, '-pfirst caller', '-psecond caller'],
        ):
            result = run(command, 2, b'')
            assert STUB_PASSWORD not in result.stderr and PAYLOAD_PASSWORD not in result.stderr

        # A rejected AD01 may be recognized only as its outer PE carrier or as
        # an ordinary encrypted ZIP. Neither path may publish recovered values.
        result = run([unpacker, 'p', corrupt_source], (1, 2))
        assert result.stdout.replace(b'\r\n', b'\n') == (none if result.returncode == 1 else b'')
        assert STUB_PASSWORD not in result.stderr and PAYLOAD_PASSWORD not in result.stderr

        for frontend in frontends:
            # The hook clicks the actual Get password button before LIST,
            # preserving/replacing raw field state according to proven metadata.
            # Its selected-member rounds cover both groups and escaped captions.
            for _, source, _, expected_exit in fixtures:
                run([frontend, '--smoke-password-retrieve', source,
                     '-pwrong manual value', '-o' + str(output)], expected_exit)
            for source, password in ((caller_source, caller_password.decode()),
                                     (caller_source, 'wrong manual value'),
                                     (clear_source, 'preserve this manual value')):
                run([frontend, '--smoke-password-retrieve', source,
                     '-p' + password, '-o' + str(output)], 1)
            run([frontend, '--smoke-password-retrieve', root / 'missing.exe',
                 '-ppreserve this manual value', '-o' + str(output)], 2)

        assert tree_state(root) == expected_tree
    print(f'Password retrieval: {checks} checks passed; inputs and output tree unchanged')


if __name__ == '__main__':
    main()
