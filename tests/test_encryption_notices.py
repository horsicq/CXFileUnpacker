"""Encryption visibility and noninteractive password failures in console output.

Usage: test_encryption_notices.py <xfu> <freearc-fixture-directory>
ZIP fixtures are assembled independently with Python's standard library;
FreeArc fixtures are checked-in independent cipher/container known answers.
"""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zlib

XFU = Path(sys.argv[1]).resolve()
FIXTURES = Path(sys.argv[2]).resolve()
FREEARC_PASSWORD = "FreeArc-fixture-password"
ZIP_PASSWORD = "notice-test-secret"


def crc_step(value, byte):
    value ^= byte
    for _ in range(8):
        value = (value >> 1) ^ (0xEDB88320 if value & 1 else 0)
    return value


def zipcrypto(data, password):
    keys = [0x12345678, 0x23456789, 0x34567890]

    def update(byte):
        keys[0] = crc_step(keys[0], byte)
        keys[1] = ((keys[1] + (keys[0] & 255)) * 134775813 + 1) & 0xFFFFFFFF
        keys[2] = crc_step(keys[2], keys[1] >> 24)

    for byte in password.encode("utf-8"):
        update(byte)
    result = bytearray()
    for byte in data:
        temp = keys[2] | 2
        result.append(byte ^ (((temp * (temp ^ 1)) >> 8) & 255))
        update(byte)
    return bytes(result)


def make_zip(path, encrypted):
    files = [("plain.txt", b"plain payload\n", False)]
    if encrypted:
        files.insert(0, ("secret&'.txt", b"encrypted ZIP payload\n", True))
    local, central = bytearray(), bytearray()
    for name, data, protected in files:
        encoded = name.encode("utf-8")
        checksum = zlib.crc32(data)
        packed = zipcrypto(bytes(range(11)) + bytes([checksum >> 24]) + data, ZIP_PASSWORD) if protected else data
        offset = len(local)
        flags = 1 if protected else 0
        local += struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, flags, 0, 0, 0,
                             checksum, len(packed), len(data), len(encoded), 0) + encoded + packed
        central += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, flags, 0, 0, 0,
                               checksum, len(packed), len(data), len(encoded), 0, 0, 0, 0, 0, offset) + encoded
    path.write_bytes(local + central + struct.pack("<IHHHHIIH", 0x06054B50, 0, 0,
                                                  len(files), len(files), len(central), len(local), 0))
    return {name: data for name, data, _ in files}


def run(command, archive, *options, env=None, leave_stdin_open=False):
    args = [str(XFU), command, str(archive), *options]
    if leave_stdin_open:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=env)
        try:
            process.wait(timeout=15)  # Keep stdin open: a prompt would block.
            out, err = process.communicate(timeout=5)
        except BaseException:
            process.kill()
            process.communicate()
            raise
        result = subprocess.CompletedProcess(args, process.returncode,
                                            out.decode("utf-8"), err.decode("utf-8"))
    else:
        result = subprocess.run(args, input="", capture_output=True, text=True,
                                encoding="utf-8", env=env, timeout=30)
    return result


def structured(command, archive, format, *options, expected_status=0):
    result = run(command, archive, *options, "--" + format)
    if format == "json":
        document = json.loads(result.stdout)  # Exactly one JSON value.
        entries = {event["name"]: event for event in document["events"] if event["type"] == "entry"}
        notices = [event for event in document["events"] if event["type"] == "encryption"]
        status = document["status"]
    else:
        document = ET.fromstring(result.stdout)
        entries = {element.attrib["name"]: element.attrib for element in document.findall("./events/entry")}
        notices = [dict(element.attrib, text=element.text or "")
                   for element in document.findall("./events/encryption")]
        status = int(document.findtext("status"))
    assert result.returncode == status, result
    assert (status == 0) == (expected_status == 0), (result, document)
    states = [notice["status"] for notice in notices]
    assert len(states) == len(set(states)), notices
    assert all(notice["encrypted"] in (True, "true") for notice in notices), notices
    return result, entries, notices


metadata = FIXTURES / "legacy_headers_and_members.arc"
members = FIXTURES / "legacy_members_only.arc"
plain_arc = FIXTURES / "plain.arc"

missing = run("l", metadata, leave_stdin_open=True)
assert missing.returncode != 0 and "Encrypted" in missing.stderr, missing
assert "Password required" in missing.stderr and "--password-env" in missing.stderr, missing
assert missing.stderr.count("Password required for encrypted data.") == 1, missing.stderr

wrong_value = "private-wrong-password-value"
wrong = run("l", metadata, "-p" + wrong_value)
assert wrong.returncode != 0 and "Check the password or archive integrity" in wrong.stderr, wrong
assert wrong_value not in wrong.stdout + wrong.stderr, wrong

listed = run("l", members)
assert listed.returncode == 0 and listed.stdout.count("[encrypted]") == 2, listed
assert "Encrypted" in listed.stderr and "--password-env" in listed.stderr, listed
advanced = run("l", members, "-slt")
assert advanced.returncode == 0 and advanced.stdout.count("Encrypted: yes") == 2, advanced

for format in ("json", "xml"):
    for archive, options in ((metadata, ("-p" + FREEARC_PASSWORD,)), (members, ())):
        result, entries, notices = structured("l", archive, format, *options)
        assert len(entries) == 2 and all(item["encrypted"] in (True, "true") for item in entries.values()), entries
        assert [notice["status"] for notice in notices] == ["detected"], notices
        assert FREEARC_PASSWORD not in result.stdout + result.stderr, result
    result, entries, notices = structured("l", metadata, format, expected_status=2)
    assert not entries and any(item["status"] == "password_required" for item in notices), notices
    result, entries, notices = structured("l", plain_arc, format)
    assert len(entries) == 2 and all(item["encrypted"] in (False, "false") for item in entries.values()), entries
    assert not notices, notices

with tempfile.TemporaryDirectory(prefix="xfu-encryption-notices-") as temporary:
    root = Path(temporary)
    mixed = root / "mixed.zip"
    plain = root / "plain.zip"
    payloads = make_zip(mixed, True)
    make_zip(plain, False)
    listed = run("l", mixed)
    assert listed.returncode == 0 and listed.stdout.count("[encrypted]") == 1, listed
    assert "Encrypted" in listed.stderr, listed
    listed_plain = run("l", plain)
    assert listed_plain.returncode == 0 and "[encrypted]" not in listed_plain.stdout, listed_plain
    assert "Encrypted" not in listed_plain.stderr, listed_plain
    advanced = run("l", mixed, "-slt")
    assert "Encrypted: yes" in advanced.stdout and "Encrypted: no" in advanced.stdout, advanced
    blocked = run("t", mixed, leave_stdin_open=True)
    assert blocked.returncode != 0 and "Password required" in blocked.stderr, blocked
    assert blocked.stderr.count("Password required for encrypted data.") == 1, blocked
    wrong = run("t", mixed, "-p" + wrong_value)
    assert wrong.returncode != 0 and "Check the password or archive integrity" in wrong.stderr, wrong
    assert wrong_value not in wrong.stdout + wrong.stderr, wrong
    success = run("t", mixed, "-p" + ZIP_PASSWORD, "-v")
    assert success.returncode == 0 and "[encrypted]" in success.stdout, success
    for format in ("json", "xml"):
        result, entries, notices = structured("l", mixed, format)
        assert entries["secret&'.txt"]["encrypted"] in (True, "true"), entries
        assert entries["plain.txt"]["encrypted"] in (False, "false"), entries
        assert [item["status"] for item in notices] == ["detected"], notices
        result, entries, notices = structured("t", mixed, format, expected_status=1)
        assert any(item["status"] == "password_required" for item in notices), notices
        result, entries, notices = structured("t", mixed, format, "-p" + wrong_value, expected_status=1)
        assert any(item["status"] == "password_rejected" for item in notices), notices
        assert wrong_value not in result.stdout + result.stderr, result
    output = root / "output"
    environment = dict(os.environ, XFU_NOTICE_PASSWORD=ZIP_PASSWORD)
    extracted = run("x", mixed, "-o" + str(output), "--password-env=XFU_NOTICE_PASSWORD", "--json", env=environment)
    document = json.loads(extracted.stdout)
    assert extracted.returncode == document["status"] == 0, extracted
    assert ZIP_PASSWORD not in extracted.stdout + extracted.stderr, extracted
    assert {item.name: item.read_bytes() for item in output.iterdir()} == payloads

print("CLI encryption markers, notices, JSON/XML and noninteractive failures passed")
