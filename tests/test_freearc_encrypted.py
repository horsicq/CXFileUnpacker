"""Verify encrypted native FreeArc through the public console interface."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

xfu = Path(sys.argv[1]).resolve()
fixtures = Path(sys.argv[2]).resolve()
password = "FreeArc-fixture-password"
payloads = {"first.txt": b"FreeArc encrypted first member.\n" * 3,
            "second.bin": bytes(range(256)) + b"\x00\xfftail"}


def run(command, archive, *options):
    process = subprocess.run([str(xfu), command, str(archive), *options, "--json"],
                             capture_output=True, text=True, timeout=30)
    document = json.loads(process.stdout)
    assert process.returncode == document["status"], (process.returncode, document)
    return process.returncode, document


for name in ("legacy_headers_and_members.arc", "fixed_headers_and_members.arc",
             "legacy_members_only.arc", "plain.arc"):
    archive = fixtures / name
    if "headers" in name:
        for options in ((), ("-pincorrect",)):
            status, result = run("l", archive, *options)
            assert status != 0 and any("password" in event.get("text", "").lower()
                                      for event in result["events"]), result
    status, result = run("l", archive, "-p" + password, "--handle", "FREEARC")
    assert status == 0, result
    status, result = run("t", archive, "-p" + password)
    assert status == 0, result
    with tempfile.TemporaryDirectory(prefix="xfu-encrypted-") as temporary:
        output = Path(temporary)
        status, result = run("x", archive, "-p" + password, "-o" + str(output))
        assert status == 0, result
        assert {path.name: path.read_bytes() for path in output.iterdir()} == payloads

# A modified encrypted solid block must fail checksum/stream validation before
# a member is published. The metadata and password verifier remain intact.
with tempfile.TemporaryDirectory(prefix="xfu-encrypted-corrupt-") as temporary:
    root = Path(temporary)
    damaged = bytearray((fixtures / "legacy_headers_and_members.arc").read_bytes())
    damaged[51] ^= 0x80
    archive = root / "damaged.arc"
    archive.write_bytes(damaged)
    output = root / "output"
    output.mkdir()
    status, result = run("x", archive, "-p" + password, "-o" + str(output))
    assert status != 0, result
    assert not list(output.iterdir()), list(output.iterdir())

print("Encrypted FreeArc console listing, test, extraction and failure cases passed")
