"""Synthetic Demolition PE/import/code graphs; fixture executables are never run."""
import argparse
import hashlib
import io
from pathlib import Path
import struct
import subprocess
import tempfile
import zipfile
import zlib

from password_options import encrypt

OPEN = b'?OpenForRead@ZipUtils@Core@Demolition@@YA_NABV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@PAPAVZipFile@123@@Z'
DESTROY = b'??1ZipFile@ZipUtils@Core@Demolition@@QAE@XZ'
DELETE = b'?DeleteCache@ZipFile@ZipUtils@Core@Demolition@@QAEXXZ'
ASSIGN = b'??4?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@QAEAAV01@PBD@Z'
CONSTRUCT = b'??0?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@QAE@PBD@Z'
COPY = b'??4?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@QAEAAV01@ABV01@@Z'
INLINE_PREFIX = bytes.fromhex('53 8B 5C 24 08 56 8B F1 85 DB')
STUB_SIZE = 4096
BASE = 0x400000


def pe_stub(passwords, flow='direct', library=b'MSVCP90.dll'):
    """Independent PE32 with a real import graph and three observed call forms."""
    image = bytearray(STUB_SIZE)
    image[:2] = b'MZ'
    struct.pack_into('<HH', image, 2, 0, 1)
    struct.pack_into('<H', image, 8, 4)
    struct.pack_into('<I', image, 60, 128)
    image[128:132] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', image, 132, 0x14c, 3, 0, 0, 0, 224, 0x102)
    struct.pack_into('<H', image, 152, 0x10b)
    for offset, value in ((168, 0x1000), (180, BASE), (184, 4096), (188, 512),
                          (208, 0x4000), (212, 512), (244, 16)):
        struct.pack_into('<I', image, offset, value)
    struct.pack_into('<H', image, 220, 2)
    struct.pack_into('<II', image, 256, 0x3000, 60)
    for i, (name, size, rva, raw, flags) in enumerate((
        (b'.text', 512, 0x1000, 512, 0x60000020),
        (b'.rdata', 1536, 0x2000, 1024, 0x40000040),
        (b'.idata', 1536, 0x3000, 2560, 0xc0000040),
    )):
        at = 376 + i * 40
        image[at:at + 8] = name.ljust(8, b'\0')
        struct.pack_into('<IIII', image, at + 8, size, rva, size, raw)
        struct.pack_into('<I', image, at + 36, flags)
    # Two descriptors and an exact zero terminator; INT and IAT point to
    # bounded IMAGE_IMPORT_BY_NAME objects, never unstructured marker strings.
    symbols = ((b'Core.dll', [OPEN, DESTROY, DELETE]),
               (library, [ASSIGN, CONSTRUCT, COPY]))
    name_at = 384
    iats = []
    for i, (dll, imports) in enumerate(symbols):
        dll_at = 64 + i * 32
        image[2560 + dll_at:2560 + dll_at + len(dll) + 1] = dll + b'\0'
        int_at = 128 + i * 32
        iat_at = 256 + i * 32
        struct.pack_into('<5I', image, 2560 + i * 20, 0x3000 + int_at, 0, 0,
                         0x3000 + dll_at, 0x3000 + iat_at)
        addresses = []
        for j, symbol in enumerate(imports):
            named = b'\0\0' + symbol + b'\0'
            image[2560 + name_at:2560 + name_at + len(named)] = named
            for table in (int_at, iat_at):
                struct.pack_into('<I', image, 2560 + table + j * 4, 0x3000 + name_at)
            addresses.append(BASE + 0x3000 + iat_at + j * 4)
            name_at += len(named)
        iats.append(addresses)
    assert name_at < 1536
    image[1040:1053] = b'decoy-secret\0'
    code, rdata_at, pointers = bytearray(), 64, []
    for password in passwords:
        assert 0 < len(password) <= 127 and b'\0' not in password
        image[1024 + rdata_at:1024 + rdata_at + len(password) + 1] = password + b'\0'
        pointer = BASE + 0x2000 + rdata_at
        pointers.append((1024 + rdata_at, pointer))
        if flow == 'direct':
            code += b'\x8b\x0e\x68' + struct.pack('<I', pointer)
            code += b'\x83\xc1\x20\xff\x15' + struct.pack('<I', iats[1][0])
        elif flow == 'temporary':
            code += b'\x68' + struct.pack('<I', pointer) + b'\x8d\x4c\x24\x54\xff\x15'
            code += struct.pack('<I', iats[1][1])
            code += b'\x90' * 16
            code += b'\x8d\x44\x24\x50\x50\x83\xc1\x20\xff\x15'
            code += struct.pack('<I', iats[1][2])
        elif flow == 'owner':
            code += b'\x6a' + bytes([len(password)]) + b'\x68' + struct.pack('<I', pointer)
            code += b'\x8d\x8e\xc8\x01\x00\x00\xe8'
            next_rva = 0x1000 + len(code) + 4
            code += struct.pack('<i', 0x1180 - next_rva)
        else:
            raise ValueError(flow)
        code += b'\x90'
        rdata_at += len(password) + 1
    assert len(code) < 384 and rdata_at < 1536
    image[512:512 + len(code)] = code
    image[512 + 384:512 + 384 + len(INLINE_PREFIX)] = INLINE_PREFIX
    image[512 + 384 + len(INLINE_PREFIX)] = 0xc3
    return bytes(image), pointers


def zip_payload(passwords, prefix=b'', relative=False, descriptor=False, encrypted=True):
    expected = {'stored.txt': b'Independent Demolition stored fixture.\n' * 5,
                'nested/deflated.txt': b'Independent full DEFLATE and CRC proof.\n' * 400}
    locals_, directory, extents = [], [], []
    position = len(prefix)
    for i, (name, plain) in enumerate(expected.items()):
        filename = name.encode()
        method = 0 if i == 0 else 8
        flags = (1 if encrypted else 0) | (8 if descriptor else 0)
        compressor = zlib.compressobj(wbits=-15)
        packed = plain if method == 0 else compressor.compress(plain) + compressor.flush()
        crc, time = zlib.crc32(plain), 0x5c20
        if encrypted:
            packed = encrypt(bytes(range(11)) + bytes([time >> 8 if descriptor else crc >> 24])
                             + packed, passwords[i])
        local_at = position
        locals_.append(struct.pack('<I5H3I2H', 0x04034b50, 20, flags, method, time, 0,
            0 if descriptor else crc, 0 if descriptor else len(packed),
            0 if descriptor else len(plain), len(filename), 0) + filename + packed)
        if descriptor:
            locals_[-1] += struct.pack('<4I', 0x08074b50, crc, len(packed), len(plain))
        extents.append((position + 30 + len(filename), len(packed)))
        position += len(locals_[-1])
        origin = len(prefix) if relative else 0
        directory.append(struct.pack('<I6H3I5H2I', 0x02014b50, 20, 20, flags, method,
            time, 0, crc, len(packed), len(plain), len(filename), 0, 0, 0, 0, 0,
            local_at - origin) + filename)
    central = b''.join(directory)
    return prefix + b''.join(locals_) + central + struct.pack('<I4H2IH', 0x06054b50,
        0, 0, 2, 2, len(central), position - (len(prefix) if relative else 0), 0), expected, extents


def outputs(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in folder.rglob('*') if p.is_file()} if folder.exists() else {}


def command(exe, *arguments, cwd, expect=None):
    result = subprocess.run([str(exe), *map(str, arguments)], cwd=cwd,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    if expect is not None and result.returncode != expect:
        raise AssertionError(f'{exe.name}: exit{result.returncode}, expected{expect}\n'
                             f'{result.stdout}\n{result.stderr}')
    return result


def password_fields(text):
    fields, current = {}, None
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if line.startswith('  ') and len(parts) == 2 and parts[0].isdigit():
            current = parts[1]
        elif current and line.startswith('    Password: '):
            fields[current] = line[len('    Password: '):]
    return fields


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--unpacker', type=Path, required=True)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--lifecycle-probe', type=Path)
    parser.add_argument('--gui', type=Path)
    parser.add_argument('--tui', type=Path)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    exe, probe = args.unpacker.resolve(), args.probe.resolve()
    with tempfile.TemporaryDirectory(prefix='demolition-password-', dir=args.root) as temporary:
        root = Path(temporary)
        first, second = b'fixture Demo password #7', b'separate fixture password!'
        cases = []
        for flow, library, relative in (
            ('direct', b'MSVCP71.dll', False), ('direct', b'MSVCP90.dll', True),
            ('temporary', b'MSVCP90.dll', False), ('owner', b'MSVCP90.dll', True),
        ):
            stub, _ = pe_stub([first], flow, library)
            image, expected, extents = zip_payload([first, first], stub, relative)
            cases.append((flow + library.decode() + str(int(relative)), image, expected,
                          {name: first.decode() for name in expected}, extents))
        for label, candidates, secrets in (
            ('decoy-before-secret', [b'wrong candidate', first], [first, first]),
            ('independent-member-secrets', [first, second], [first, second]),
            ('one-byte-secret', [b'Q'], [b'Q', b'Q']),
            ('maximum-secret', [b'A' * 64], [b'A' * 64, b'A' * 64]),
        ):
            stub, _ = pe_stub(candidates)
            image, expected, extents = zip_payload(secrets, stub)
            cases.append((label, image, expected,
                          {name: secrets[i].decode() for i, name in enumerate(expected)}, extents))
        stub, pointers = pe_stub([first])
        image, expected, extents = zip_payload([first, first], stub, descriptor=True)
        cases.append(('descriptor', image, expected, {name: first.decode() for name in expected}, extents))
        plain, plain_expected, plain_extents = zip_payload([first, first], stub, encrypted=False)
        cases.append(('unencrypted-no-password-metadata', plain, plain_expected, {}, plain_extents))
        # Recognized code and import structure do not excuse an unverified key.
        wrong_stub, _ = pe_stub([b'not the archive password'])
        wrong, expected, wrong_extents = zip_payload([first, first], wrong_stub)
        cases.append(('no-matching-key', wrong, {}, {}, wrong_extents))
        long_stub, _ = pe_stub([b'A' * 65])
        long_image, _, long_extents = zip_payload([b'A' * 65, b'A' * 65], long_stub)
        cases.append(('candidate-exceeds-byte-bound', long_image, {}, {}, long_extents))
        base, expected, base_extents = zip_payload([first, first], stub)
        for label, mutate in (
            ('marker-only-no-import-directory', lambda b: struct.pack_into('<II', b, 256, 0, 0)),
            ('wrong-core-dll', lambda b: b.__setitem__(slice(2624, 2632), b'Fake.dll')),
            ('missing-Core-import', lambda b: b.__setitem__(2560 + 384 + 2, ord('!'))),
            ('missing-ZipFile-destructor', lambda b: b.__setitem__(stub.index(DESTROY), ord('!'))),
            ('missing-DeleteCache-import', lambda b: b.__setitem__(stub.index(DELETE), ord('!'))),
            ('wrong-stdlib-dll', lambda b: b.__setitem__(2656, ord('!'))),
            ('code-reference-absent', lambda b: b.__setitem__(slice(512, 544), b'\x90' * 32)),
            ('import-directory-RVA-OOB', lambda b: struct.pack_into('<I', b, 256, 0xfffffff0)),
            ('import-thunk-RVA-OOB', lambda b: struct.pack_into('<I', b, 2688, 0xfffffff0)),
            ('writable-rdata', lambda b: struct.pack_into('<I', b, 452, 0xc0000040)),
            ('executable-rdata', lambda b: struct.pack_into('<I', b, 452, 0x60000040)),
            ('candidate-pointer-OOB', lambda b: struct.pack_into('<I', b, 515, BASE + 0xffff0)),
            ('wrong-ZipFile-field', lambda b: b.__setitem__(521, 0x24)),
        ):
            changed = bytearray(base)
            mutate(changed)
            cases.append((label, bytes(changed), {}, {}, base_extents))
        for flow, label, at in (('temporary', 'temporary-without-ZipFile-copy', 512 + 32),
                                ('owner', 'owner-wrong-inline-prefix', 512 + 384)):
            carrier, _ = pe_stub([first], flow)
            changed = bytearray(carrier)
            changed[at] ^= 0x55
            image, _, extent = zip_payload([first, first], bytes(changed))
            cases.append((label, image, {}, {}, extent))
        owner, _ = pe_stub([first], 'owner')
        for label, mutate in (
            ('owner-wrong-explicit-length', lambda b: b.__setitem__(513, len(first) + 1)),
            ('owner-callee-outside-text', lambda b: struct.pack_into('<i', b, 526, 0x2080 - 0x1012)),
        ):
            changed = bytearray(owner)
            mutate(changed)
            image, _, extent = zip_payload([first, first], bytes(changed))
            cases.append((label, image, {}, {}, extent))
        for i, (at, _) in enumerate(base_extents):
            changed = bytearray(base)
            changed[at + 12] ^= 0x55  # Keep the ZipCrypto authentication header intact.
            good_name = list(expected)[1 - i]
            cases.append((f'corrupt-member-{i}', bytes(changed), {good_name: expected[good_name]},
                          {good_name: first.decode()}, base_extents))
        for label, image, wanted, recovered, extent in cases:
            source = root / (label + '.exe')
            source.write_bytes(image)
            before = hashlib.sha256(image).hexdigest()
            listing = command(exe, 'l', source, '--advanced', cwd=root)
            if listing.returncode == 0:
                assert password_fields(listing.stdout) == recovered, (label, listing.stdout)
            else:
                assert not recovered and not password_fields(listing.stdout), (label, listing.stdout)
            successful = len(wanted) == 2
            tested = command(exe, 't', source, cwd=root)
            assert (tested.returncode == 0) == successful, (label, tested.stdout, tested.stderr)
            output = root / (label + '-output')
            extracted = command(exe, 'x', source, '-o' + str(output), cwd=root)
            assert (extracted.returncode == 0) == successful, (label, extracted.stdout, extracted.stderr)
            assert outputs(output) == wanted, (label, outputs(output).keys())
            if successful and recovered:
                check = command(probe, source, 'sfx_zipcentral', cwd=root, expect=0)
                assert 'valid=1 parsed=1' in check.stdout, (label, check.stdout)
                # Explicit caller credentials retain ordinary ZIP precedence;
                # listing metadata still contains only proven embedded values.
                wrong_listing = command(exe, 'l', source, '--advanced', '-pwrong caller', cwd=root, expect=0)
                assert password_fields(wrong_listing.stdout) == recovered
                bad_out = root / (label + '-wrong-caller')
                wrong_decode = command(exe, 'x', source, '-o' + str(bad_out), '-pwrong caller', cwd=root)
                assert wrong_decode.returncode != 0 and not outputs(bad_out)
                assert command(exe, 't', source, '-pwrong caller', cwd=root).returncode != 0
                if args.lifecycle_probe and len(set(recovered.values())) == 1:
                    secret = next(iter(recovered.values())).encode()
                    command(args.lifecycle_probe.resolve(), source, secret.hex(), extent[0][0], cwd=root, expect=0)
                if label.startswith(('directMSVCP', 'temporaryMSVCP', 'ownerMSVCP')) or label == 'independent-member-secrets':
                    for frontend in (args.gui, args.tui):
                        if frontend:
                            ui_output = root / (label + '-' + frontend.stem)
                            command(frontend.resolve(), '--smoke-password-embedded', source,
                                    '-o' + str(ui_output), cwd=root, expect=0)
                            assert outputs(ui_output) == wanted, (label, frontend.name)
                with zipfile.ZipFile(io.BytesIO(image)) as z:
                    for name, plain in wanted.items():
                        assert z.read(name, pwd=recovered[name].encode()) == plain
            assert hashlib.sha256(source.read_bytes()).hexdigest() == before, source
    print(f'Demolition embedded password regression: {len(cases)} cases passed; source hashes unchanged')


if __name__ == '__main__':
    main()
