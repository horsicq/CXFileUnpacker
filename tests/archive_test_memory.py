"""Independent TEST fixtures, CLI output contracts and operation I/O guards.

Fixture files are written before testing. TEST itself runs with unusable TEMP
paths and an unchanged-directory/source-byte check. The C probe additionally
uses the library's scoped mutation guard, which catches attempted transient
disk writes that an after-the-fact directory snapshot cannot see.
"""
import argparse
import hashlib
import io
import lzma
import os
from pathlib import Path
import re
import struct
import subprocess
import tarfile
import tempfile
import zipfile
import zlib

from password_options import archive as password_zip


MEMBERS = {"unique-first-memory.bin": bytes(range(256)) * 9,
           "deep/unique-second-memory.txt": b"Independent payload and CRC!\n" * 300,
           "unique-empty-memory.txt": b""}


def zip_fixture(corrupt=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        for i, (name, data) in enumerate(MEMBERS.items()):
            z.writestr(name, data, compress_type=zipfile.ZIP_STORED if i == 0
                       else zipfile.ZIP_DEFLATED)
    data = bytearray(stream.getvalue())
    if corrupt is True:
        # Change one stored byte while retaining the original local/central CRC.
        at = 30 + len(next(iter(MEMBERS)).encode())
        data[at + 71] ^= 0x80
    elif corrupt == "deflate-crc":
        central = data.index(b"PK\x01\x02", data.index(b"PK\x01\x02") + 4)
        local = struct.unpack_from("<I", data, central + 42)[0]
        crc = struct.unpack_from("<I", data, central + 16)[0] ^ 1
        struct.pack_into("<I", data, central + 16, crc)
        struct.pack_into("<I", data, local + 14, crc)
    return bytes(data)


def number(n):
    for extra in range(8):
        if n < 1 << (7 + 7 * extra):
            return bytes((((0xff << (8 - extra)) & 0xff) | (n >> (8 * extra)),)) + \
                   n.to_bytes(8, "little")[:extra]
    return b"\xff" + n.to_bytes(8, "little")


def seven_fixture(codec=False, chain=False, corrupt=False):
    # One solid folder, three substreams, per-member CRCs. The Copy -> Copy
    # graph creates an intermediate seekable stream independently of 7z tools.
    members = dict(MEMBERS)
    members[next(reversed(members))] = b"small final substream\n"
    plain = b"".join(members.values())
    packed = lzma.compress(plain, format=lzma.FORMAT_RAW,
                          filters=[{"id": lzma.FILTER_LZMA2, "dict_size": 1 << 20}]) \
             if codec else plain
    coders = b"\x21\x21\x01\x10" if codec else b"\x01\0"
    if chain:
        coders += b"\x01\0"
    folder = number(2 if chain else 1) + coders + (b"\x01\0" if chain else b"")
    packinfo = b"\x06\0\x01\x09" + number(len(packed)) + b"\0"
    unpackinfo = b"\x07\x0b\x01\0" + folder + b"\x0c" + \
                 number(len(plain)) * (2 if chain else 1) + b"\0"
    subs = b"\x08\x0d" + number(len(members)) + b"\x09" + \
           b"".join(number(len(v)) for v in list(members.values())[:-1]) + b"\x0a\x01" + \
           b"".join(struct.pack("<I", zlib.crc32(v)) for v in members.values()) + b"\0"
    names = b"\0" + b"".join(n.encode("utf-16le") + b"\0\0" for n in members)
    header = b"\x01\x04" + packinfo + unpackinfo + subs + b"\0\x05" + \
             number(len(members)) + b"\x11" + number(len(names)) + names + b"\0\0"
    if corrupt:
        # Corrupt only the first member's recorded checksum. Header checksums
        # are rebuilt; the intact codec must still fail content verification.
        wanted = struct.pack("<I", zlib.crc32(next(iter(members.values()))))
        at = header.index(wanted)
        header = header[:at] + bytes((header[at] ^ 1,)) + header[at + 1:]
    start = struct.pack("<QQI", len(packed), len(header), zlib.crc32(header))
    return b"7z\xbc\xaf\x27\x1c\0\x04" + struct.pack("<I", zlib.crc32(start)) + \
           start + packed + header, members


def ace_fixture(corrupt=False):
    def header(body):
        return struct.pack("<HH", (zlib.crc32(body) ^ 0xffffffff) & 0xffff,
                           len(body)) + body
    main = bytearray(27)
    main[3:10] = b"**ACE**"
    main[10:12] = b"\x14\x14"
    parts = [header(main)]
    for i, (name, plain) in enumerate(MEMBERS.items()):
        encoded = name.encode()
        h = bytearray(31 + len(encoded))
        struct.pack_into("<BHII", h, 0, 1, 1, len(plain), len(plain))
        struct.pack_into("<I", h, 19, zlib.crc32(plain) ^ 0xffffffff)
        struct.pack_into("<H", h, 29, len(encoded))
        h[31:] = encoded
        parts += [header(h), bytes((plain[0] ^ 1,)) + plain[1:]
                  if corrupt and i == 0 else plain]
    return b"".join(parts)


def izpack_fixture():
    # Java serialization stream for the original two-field PackFile version.
    # Two block-data frames force actual de-framing rather than a stored view.
    def utf(s):
        b = s.encode(); return struct.pack(">H", len(b)) + b
    name, plain = "unique-izpack-memory.txt", b"bounded framed IzPack payload"
    descriptor = b"\x73\x72" + utf("com.izforge.izpack.PackFile") + \
        struct.pack(">QBH", 0x76a523b293a5e5c3, 2, 2) + \
        b"J" + utf("length") + b"L" + utf("targetPath") + \
        b"\x74" + utf("Ljava/lang/String;") + b"\x78\x70"
    return b"\xac\xed\0\x05\x77\x04" + struct.pack(">I", 1) + descriptor + \
        struct.pack(">q", len(plain)) + b"\x74" + utf(name) + \
        b"\x77\x03" + plain[:3] + b"\x77" + bytes((len(plain) - 3,)) + plain[3:], \
        {name: plain}


def tar_fixture(unsafe_link=False):
    out = io.BytesIO()
    names = ["unique-tar-payload.bin", "unique-hard-link", "nested/unique-symbolic-link"]
    with tarfile.open(fileobj=out, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        first = tarfile.TarInfo(names[0]); first.size = 4
        tar.addfile(first, io.BytesIO(b"data"))
        for i, name in enumerate(names[1:]):
            link = tarfile.TarInfo(name)
            link.type = tarfile.LNKTYPE if i == 0 else tarfile.SYMTYPE
            link.linkname = "../unsafe-target" if unsafe_link and i == 0 else names[0]
            tar.addfile(link)
    return out.getvalue(), {n: b"" for n in names}


def snapshot(root):
    return {str(p.relative_to(root)): (("file", p.stat().st_size, p.stat().st_mtime_ns,
            hashlib.sha256(p.read_bytes()).hexdigest()) if p.is_file() else ("directory",))
            for p in root.rglob("*")}


def run(command, root, env):
    before = snapshot(root)
    p = subprocess.run([str(a) for a in command], cwd=root, env=env,
                       capture_output=True, timeout=30)
    assert snapshot(root) == before, (command, "TEST changed source/output files")
    assert not (root / "forbidden-test-directory").exists()
    assert not (root / "forbidden-test-output.bin").exists()
    return p, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("unpacker", type=Path)
    parser.add_argument("--probe", type=Path, required=True)
    args = parser.parse_args()
    exe, probe = args.unpacker.resolve(), args.probe.resolve()
    count = 0
    with tempfile.TemporaryDirectory(prefix="xfu_memory_test_") as folder:
        root = Path(folder)
        blocker = root / "temp-is-a-file"; blocker.write_bytes(b"not a directory")
        env = os.environ.copy()
        env.update(TEMP=str(blocker), TMP=str(blocker), TMPDIR=str(blocker))
        cases = [("stored-deflate.zip", zip_fixture(), MEMBERS, set(), None),
                 ("stored-crc.zip", zip_fixture(True), MEMBERS, {next(iter(MEMBERS))}, None),
                 ("deflate-crc.zip", zip_fixture("deflate-crc"), MEMBERS,
                  {list(MEMBERS)[1]}, None),
                 ("stored.ace", ace_fixture(), MEMBERS, set(), None),
                 ("stored-crc.ace", ace_fixture(True), MEMBERS, {next(iter(MEMBERS))}, None)]
        izpack, iz_names = izpack_fixture()
        cases.append(("framed.pack", izpack, iz_names, set(), None))
        for codec in (False, True):
            for chain in (False, True):
                for bad in (False, True):
                    data, names = seven_fixture(codec, chain, bad)
                    cases.append((f"solid-{codec}-{chain}-{bad}.7z", data, names,
                                  {next(iter(names))} if bad else set(), None))
        for unsafe in (False, True):
            data, names = tar_fixture(unsafe)
            cases.append((f"links-{unsafe}.tar", data, names,
                          {"unique-hard-link"} if unsafe else set(), None))
        for descriptor in (False, True):
            data, names = password_zip(b"memory password #7", descriptor=descriptor)
            for password in (None, "wrong", "memory password #7"):
                cases.append((f"encrypted-{descriptor}-{password is None}-{password == 'wrong'}.zip",
                              data, names, set(names) if password != "memory password #7" else set(),
                              password))
        for name, data, names, failed, password in cases:
            source = root / name; source.write_bytes(data)
            expected_status = 1 if failed else 0
            switch = [] if password is None else ["-p" + password]
            for verbose in (False, True):
                command = [exe, "t", source, *switch, *( ["--verbose"] if verbose else [])]
                p, out, err = run(command, root, env)
                assert p.returncode == expected_status, (name, verbose, p.returncode, out, err)
                if verbose:
                    wanted = [n + " -- " + ("FAILED" if n in failed else "OK") for n in names]
                    assert out.splitlines() == wanted, (name, out, wanted, err)
                else:
                    lines = out.splitlines()
                    assert lines and all(re.fullmatch(r"\d+%", s) for s in lines), (name, out, err)
                    values = [int(s[:-1]) for s in lines]
                    assert values == sorted(set(values)) and values[-1] == 100 and values[0] >= 0
                    assert all(n not in out + err for n in names), (name, "member name leaked", out, err)
                count += 1
            p, out, err = run([probe, source, expected_status, len(names), len(failed),
                               "normal", *([] if password is None else [password])], root, env)
            assert p.returncode == 0, (name, "probe", out, err)
            count += 1

        p, out, err = run([probe, root / "framed.pack", 0, 0, 0, "izpack-read-error"], root, env)
        assert p.returncode == 0, ("IzPack injected payload read failure", out, err)
        count += 1

        # A large stored member makes cancellation polling occur inside a body,
        # independently of codec speed and scheduling.
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as z:
            z.writestr("large-cancel-body.bin", bytes(range(256)) * 32768)
            z.writestr("not-reached-after-cancel.txt", b"later")
        large = root / "cancel.zip"; large.write_bytes(stream.getvalue())
        for mode, results, failures in (("cancel-before", 0, 0), ("cancel-after", 1, 0),
                                        ("cancel-inside", 1, 1), ("mutate", 2, 0)):
            p, out, err = run([probe, large, 1, results, failures, mode], root, env)
            assert p.returncode == 0, (mode, out, err)
            count += 1
        # Truncated containers fail before a success percentage; an empty ZIP
        # is a valid zero-member archive and must complete in memory.
        empty = root / "empty.zip"
        with zipfile.ZipFile(empty, "w"): pass
        p, out, err = run([exe, "t", empty], root, env)
        assert p.returncode == 0 and out.splitlines()[-1] == "100%", (out, err)
        count += 1
        truncated = root / "truncated.zip"; truncated.write_bytes(zip_fixture()[:28])
        p, out, err = run([exe, "t", truncated], root, env)
        assert p.returncode != 0 and "100%" not in out, (out, err)
        count += 1
    print(f"{count} memory TEST, disk guard, CRC, password, cancellation and CLI output checks passed")


if __name__ == "__main__":
    main()
