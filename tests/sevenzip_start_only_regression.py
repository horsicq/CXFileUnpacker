"""Verify start-only LIST/READ policy, cache invalidation, and nonzero bases."""
import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess
import uuid

PINNED_DLL_SHA256 = "65e4c1f855f9ef6e8f0f5df8e3f27d9eb5f07311408639da0a1ca0b8f4871b0d"
BASE = 65535


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot(directory):
    return {str(path.relative_to(directory)): (path.stat().st_size, sha256(path))
            for path in directory.rglob("*") if path.is_file()}


def stored_lha(payload):
    # Independent LHA level-0 header with stored data and CRC16/IBM.
    crc = 0
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    name = b"hello.bin"
    body = (b"-lh0-" + struct.pack("<III", len(payload), len(payload), 0) +
            bytes((0x20, 0, len(name))) + name + struct.pack("<H", crc))
    return bytes((len(body), sum(body) & 255)) + body + payload + b"\0"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=pathlib.Path, required=True)
    parser.add_argument("--helper", type=pathlib.Path, required=True)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    checks = 0

    def require(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise RuntimeError(message)

    dll_source = args.helper.parent / "xfusevenzip2603.dll"
    for path in (args.probe, args.helper, dll_source):
        require(path.is_file(), f"Missing runtime file: {path}")
    require(sha256(dll_source) == PINNED_DLL_SHA256, "7-Zip 26.03 DLL checksum mismatch")
    args.root.mkdir(parents=True, exist_ok=True)
    run = args.root.resolve() / f"run-{uuid.uuid4().hex}"
    runtime = run / "runtime"
    runtime.mkdir(parents=True)
    probe = runtime / "start_only_probe.exe"
    helper = runtime / "xfu_sevenzip_helper.exe"
    for original, copy in ((args.probe, probe), (args.helper, helper),
                           (dll_source, runtime / "xfusevenzip2603.dll")):
        shutil.copyfile(original, copy)
        require(sha256(original) == sha256(copy), f"Runtime copy differs: {copy}")
    payload = bytes(range(256)) * 1573 + b"\0end\xff"
    fixture = run / "embedded.lzh"
    fixture.write_bytes(b"MZ" + bytes(BASE - 2) + stored_lha(payload))
    before = snapshot(run)
    controls = []
    for handler in ("Lzh", "auto"):
        completed = subprocess.run([str(probe), str(fixture), handler, str(BASE)],
                                   cwd=runtime, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=120)
        require(completed.returncode == 0,
                f"{handler} lifecycle failed ({completed.returncode}):\n{completed.stdout}\n{completed.stderr}")
        proof = json.loads(completed.stdout)
        require(proof.get("checks", 0) >= 44, f"{handler} controls did not all execute")
        for field in ("start_only", "cache_invalidated", "retained_iterator_read", "nonzero_base"):
            require(proof.get(field) is True, f"{handler} missing passing control: {field}")
        controls.append(dict(handler=handler, proof=proof))
    require(snapshot(run) == before, "TEST created or changed runtime/input files")
    report = dict(runner_checks=checks, native_checks=sum(c["proof"]["checks"] for c in controls),
                  controls=controls, base_address=BASE, fixture_sha256=sha256(fixture),
                  payload_sha256=hashlib.sha256(payload).hexdigest(),
                  dll_sha256=PINNED_DLL_SHA256, helper_sha256=sha256(helper),
                  test_created_or_changed_files=False, run=str(run))
    # Evidence is saved after TEST has finished; the probe never sets an output path.
    (run / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
