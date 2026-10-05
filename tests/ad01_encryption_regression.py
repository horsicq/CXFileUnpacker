"""Independent AD01 mode-2 layouts; fixture PE stubs are never executed."""
import argparse
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import zipfile
import zlib

from password_options import encrypt
from inftool_regression import cabinet

STUB_PASSWORD = b'fixture-stub-password!'
PAYLOAD_PASSWORD = b'fixture payload password #2'
START = 1536
ZIP_START = START + 12


def encoded_adx(mode=b'2', password=PAYLOAD_PASSWORD, missing=None, duplicate=False,
                seed=2719):
    digits = f'{42 * seed:04d}{seed:04d}{24 * seed:04d}{33 * seed:04d}'.encode()
    mask = bytes((a ^ b) & 15 for a, b in zip(b'[cvyxtrWZiho}~l]', digits[:16]))
    def encode(value):
        result = bytearray()
        for i, byte in enumerate(value):
            if byte in (13, 10, 61):
                result.append({13:16, 10:17, 61:18}[byte])
            else:
                byte ^= mask[i & 15]
                result.append(19 if byte == 61 else byte)
        return bytes(result)
    lines = [b'[ADX]', b'ADXVersion=1.00.00', b'<=>' + str(seed).encode()]
    if missing != 'mode':
        lines.append(encode(b'ADK_00000401') + b'=' + encode(mode))
    if duplicate:
        lines.append(encode(b'ADK_00000401') + b'=' + encode(mode))
    if missing != 'password':
        lines.append(encode(b'ADK_00000402') + b'=' + encode(password))
    return b'\r\n'.join(lines) + b'\r\n'


def entries(stored=3, adx=None):
    cab, _ = cabinet()
    payloads = [('data.cab', cab)]
    if stored >= 2:
        payloads.append(('install.exe', b'MZ' + b'Independent saved executable bytes; never run.' * 8))
    if stored >= 3:
        payloads.append(('setup.tmp', bytes(range(251)) * 3))
    support = [('_Active Delivery_', b'Fixture control UI strings.\0' * 40),
               ('_ad103.dll', b'MZ' + b'Independent support library bytes; never run.' * 20),
               ('_ad103.adx', encoded_adx() if adx is None else adx)]
    while len(payloads) + len(support) < 6:
        support.append((f'support{len(support)}.txt', b'Additional saved support text.\n' * 5))
    return [(name, data, 0, PAYLOAD_PASSWORD) for name, data in payloads] + [
        (name, data, 8, STUB_PASSWORD) for name, data in support]


def package(items, stub=STUB_PASSWORD, encrypted=True, extra_flags=0,
            relative_offsets=False):
    local, central, extents = [], [], []
    at = ZIP_START
    origin = ZIP_START if relative_offsets else 0
    for name, plain, method, password in items:
        name = name.encode('ascii')
        encoder = zlib.compressobj(9, zlib.DEFLATED, -15)
        packed = plain if method == 0 else encoder.compress(plain) + encoder.flush()
        crc = zlib.crc32(plain)
        flags = (1 if encrypted else 0) | (2 if method == 8 else 0) | extra_flags
        if encrypted:
            check = 0x5c if flags & 8 else crc >> 24
            packed = encrypt(bytes(range(11)) + bytes([check]) + packed, password)
        header = struct.pack('<I5H3I2H', 0x04034b50, 20, flags, method, 0x5c20, 0,
                             0 if flags & 8 else crc, 0 if flags & 8 else len(packed),
                             0 if flags & 8 else len(plain), len(name), 0)
        body = header + name + packed
        if flags & 8:
            body += struct.pack('<4I', 0x08074b50, crc, len(packed), len(plain))
        extents.append((at + 30 + len(name), len(packed)))
        central.append(struct.pack('<I6H3I5H2I', 0x02014b50, 20, 20, flags, method,
                                   0x5c20, 0, crc, len(packed), len(plain), len(name),
                                   0, 0, 0, 0, 0, at - origin) + name)
        local.append(body)
        at += len(body)
    directory = b''.join(central)
    stream = b''.join(local) + directory + struct.pack('<I4H2IH', 0x06054b50, 0, 0,
        len(items), len(items), len(directory), at - origin, 0)
    carrier = b'AD01' + struct.pack('<II', 0, len(stream)) + stream
    raw = (len(carrier) + 511) & ~511
    image = bytearray(START + raw)
    image[:2] = b'MZ'
    struct.pack_into('<I', image, 60, 128)
    image[128:132] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', image, 132, 0x14c, 3, 0, 0, 0, 224, 0x102)
    struct.pack_into('<H', image, 152, 0x10b)
    struct.pack_into('<I', image, 212, 512)
    for i, (name, size, offset) in enumerate([(b'.data', 512, 512),
                                             (b'.text', 512, 1024),
                                             (b'actdlvry', raw, START)]):
        section = 376 + i * 40
        image[section:section + 8] = name.ljust(8, b'\0')
        struct.pack_into('<IIII', image, section + 8, size, 0x1000 * (i + 1), size, offset)
        struct.pack_into('<I', image, section + 36, 0x60000020)
    image[520:533] = b'decoy-secret\0'
    image[560:560 + len(stub) + 1] = stub + b'\0'
    image[START:START + len(carrier)] = carrier
    return bytes(image), extents


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--unpacker', type=Path, required=True)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--metadata-probe', type=Path)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='ad01-encryption-', dir=args.root) as temporary:
        root = Path(temporary)
        good = entries()
        data, extents = package(good)
        cases = {'three-stored': (data, good),
                 'one-stored': (package(entries(1))[0], entries(1)),
                 'unencrypted-mixed': (package(good, encrypted=False)[0], good)}
        relative, _ = package(good, relative_offsets=True)
        cases['three-stored-relative'] = (relative, good)
        cases['one-stored-relative'] = (package(entries(1), relative_offsets=True)[0], entries(1))
        cases['unencrypted-relative'] = (package(good, encrypted=False, relative_offsets=True)[0], good)
        zip_end = ZIP_START + struct.unpack_from('<I', relative, START + 8)[0]
        eocd = zip_end - 22
        directory = ZIP_START + struct.unpack_from('<I', relative, eocd + 16)[0]
        damaged = bytearray(relative)
        struct.pack_into('<I', damaged, eocd + 16, directory)
        cases['relative-locals-absolute-directory'] = (bytes(damaged), None)
        damaged = bytearray(relative)
        struct.pack_into('<I', damaged, directory + 42, ZIP_START)
        cases['absolute-first-local-relative-directory'] = (bytes(damaged), None)
        second = directory + 46 + len(good[0][0])
        damaged = bytearray(relative)
        struct.pack_into('<I', damaged, second + 42,
                         ZIP_START + struct.unpack_from('<I', damaged, second + 42)[0])
        cases['mixed-local-origins'] = (bytes(damaged), None)
        damaged = bytearray(relative)
        struct.pack_into('<I', damaged, eocd + 12, 0xffffffff)
        cases['oversized-directory-extent'] = (bytes(damaged), None)
        damaged = bytearray(relative)
        struct.pack_into('<I', damaged, directory + 42, 0xffffffff)
        cases['oversized-local-offset'] = (bytes(damaged), None)
        for field in ('mode', 'password'):
            cases['missing-' + field] = (package(entries(adx=encoded_adx(missing=field)))[0], None)
        for label, adx in [('wrong-mode', encoded_adx(mode=b'1')),
                           ('duplicate-mode', encoded_adx(duplicate=True)),
                           ('wrong-payload-password', encoded_adx(password=b'incorrect')),
                           ('long-password', encoded_adx(password=b'x' * 65)),
                           ('empty-password', encoded_adx(password=b'')),
                           ('wrong-ADX-signature', b'[NOTADX]\r\n' + encoded_adx())]:
            cases[label] = (package(entries(adx=adx))[0], None)
        cases['missing-stub-password'] = (package(good, stub=b'not-the-secret')[0], None)
        cases['unsupported-two-stored'] = (package(entries(2))[0], None)
        interleaved = good[:1] + good[3:4] + good[1:3] + good[4:]
        cases['interleaved-stored'] = (package(interleaved)[0], None)
        no_control = [(('other.txt' if name == '_Active Delivery_' else name), plain, method, password)
                      for name, plain, method, password in good]
        cases['missing-control'] = (package(no_control)[0], None)
        no_adx = [(('other.cfg' if name.endswith('.adx') else name), plain, method, password)
                  for name, plain, method, password in good]
        cases['missing-ADX'] = (package(no_adx)[0], None)
        bad_magic = [('data.cab', b'XXXX' + good[0][1][4:], 0, PAYLOAD_PASSWORD)] + good[1:]
        opaque, opaque_extents = package(bad_magic)
        cases['opaque-CAB-payload'] = (opaque, bad_magic)
        installshield = [('data.cab', b'IC60' + good[0][1][4:], 0, PAYLOAD_PASSWORD)] + good[1:]
        cases['IC60-CAB-payload'] = (package(installshield)[0], installshield)
        small = [('data.cab', b'\x00', 0, PAYLOAD_PASSWORD)] + good[1:]
        cases['small-opaque-CAB-payload'] = (package(small)[0], small)
        damaged = bytearray(opaque)
        # Authentication of an opaque payload still covers its first byte:
        # changing the encrypted body without a new CRC must fail.
        damaged[opaque_extents[0][0] + 12] ^= 0x55
        cases['opaque-CAB-body-CRC-corruption'] = (bytes(damaged), None)
        unsafe = [('..\\data.cab', *good[0][1:])] + good[1:]
        cases['unsafe-member-path'] = (package(unsafe)[0], None)
        cases['unsupported-descriptor-flags'] = (package(good, extra_flags=8)[0], None)
        for i, (at, size) in enumerate(extents):
            damaged = bytearray(data)
            # Leave the encrypted authentication header intact: full decoded
            # CRC/stream integrity must reject corruption in every member.
            damaged[at + 12] ^= 0x55
            cases[f'corrupt-member-{i}'] = (bytes(damaged), None)
        damaged = bytearray(data)
        struct.pack_into('<I', damaged, extents[0][0] - len('data.cab') - 30 + 18, 1)
        cases['local-packed-size-mismatch'] = (bytes(damaged), None)
        cases['truncated-carrier'] = (data[:-512], None)
        for name, (image, expected_items) in cases.items():
            source = root / (name + '.exe')
            source.write_bytes(image)
            valid = expected_items is not None
            if valid:
                # Independent standard ZIP implementation verifies both
                # member password groups and every fixture size/CRC.
                with zipfile.ZipFile(source) as archive:
                    encrypted = bool(archive.infolist()[0].flag_bits & 1)
                    for member, plain, method, password in expected_items:
                        assert archive.read(member, pwd=password) == plain
            probe = subprocess.run([str(args.probe), str(source), 'sfx_ad01'],
                                   capture_output=True, text=True, timeout=30)
            parses = 'sfx_ad01 type=SFX AD01 valid=1 parsed=1' in probe.stdout
            if probe.returncode or parses != valid:
                raise AssertionError(f'{name}: validity differs\n{probe.stdout}\n{probe.stderr}')
            listing = subprocess.run([str(args.unpacker), 'l', str(source), '--advanced'],
                                     capture_output=True, text=True, timeout=30)
            if valid:
                metadata, current = {}, None
                for line in listing.stdout.splitlines():
                    member = re.match(r'^  +[0-9]+  (.+)$', line)
                    if member:
                        current = member[1]
                        metadata[current] = {}
                    elif current is not None and line.startswith('    '):
                        field = line[4:].partition(': ')
                        if field[1]:
                            metadata[current][field[0]] = field[2]
                if listing.returncode or set(metadata) != {item[0] for item in expected_items}:
                    raise AssertionError(f'{name}: advanced listing differs\n{listing.stdout}\n{listing.stderr}')
                for member, plain, method, password in expected_items:
                    fields = metadata[member]
                    assert fields['Encrypted'] == ('Yes' if encrypted else 'No'), (name, member, fields)
                    assert fields['Method ID'] == str(method), (name, member, fields)
                    if encrypted:
                        assert fields['Password'] == password.decode('ascii'), (name, member, fields)
                    else:
                        assert 'Password' not in fields, (name, member, fields)
                if name == 'three-stored':
                    supplied = 'not-a-recovered-password'
                    overridden = subprocess.run([str(args.unpacker), 'l', str(source),
                        '--advanced', '-p' + supplied], capture_output=True, text=True, timeout=30)
                    assert overridden.returncode == 0 and supplied not in overridden.stdout + overridden.stderr
                    for password in (STUB_PASSWORD, PAYLOAD_PASSWORD):
                        expected_count = sum(item[3] == password for item in expected_items)
                        assert overridden.stdout.count('    Password: ' + password.decode() + '\n') == expected_count
                if args.metadata_probe:
                    stored = sum(item[2] == 0 for item in expected_items)
                    lifecycle = subprocess.run([str(args.metadata_probe), str(source), str(stored),
                        STUB_PASSWORD.decode(), PAYLOAD_PASSWORD.decode(), str(int(encrypted))],
                        capture_output=True, text=True, timeout=30)
                    if lifecycle.returncode:
                        raise AssertionError(f'{name}: metadata lifecycle failed\n{lifecycle.stdout}\n{lifecycle.stderr}')
            elif listing.returncode == 0 or '    Password: ' in listing.stdout:
                raise AssertionError(f'{name}: invalid wrapper exposed successful metadata\n{listing.stdout}')
            # Both embedded password groups must also work through the public
            # test command, with no caller password or password-env flags.
            before_test = {p.relative_to(root).as_posix(): p.read_bytes()
                           for p in root.rglob('*') if p.is_file()}
            tested = subprocess.run([str(args.unpacker), 't', str(source)], cwd=root,
                                    capture_output=True, text=True, timeout=30)
            after_test = {p.relative_to(root).as_posix(): p.read_bytes()
                          for p in root.rglob('*') if p.is_file()}
            if (tested.returncode == 0) != valid or before_test != after_test:
                raise AssertionError(f'{name}: no-password test command differs or wrote files\n'
                                     f'{tested.stdout}\n{tested.stderr}')
            output = root / (name + '-output')
            result = subprocess.run([str(args.unpacker), 'x', str(source), '-o' + str(output)],
                                    capture_output=True, text=True, timeout=30)
            actual = {p.relative_to(output).as_posix(): p.read_bytes()
                      for p in output.rglob('*') if p.is_file()} if output.exists() else {}
            if valid:
                expected = {item[0]: item[1] for item in expected_items}
                if result.returncode or actual != expected:
                    raise AssertionError(f'{name}: output differs\n{result.stdout}\n{result.stderr}')
            elif result.returncode == 0 or actual:
                raise AssertionError(f'{name}: invalid wrapper produced success or files')
    print(f'AD01 encryption regression: {len(cases)} cases passed')


if __name__ == '__main__':
    main()
