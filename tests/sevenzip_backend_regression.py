"""Windows backend progress, RAM TEST, and stalled pipe regression.

Generate the compressed fixture before TEST, then run the native controls in
an isolated runtime containing the supplied probe/helper and pinned DLL.
The 149 MiB decoded payload is generated in 64 KiB blocks and never saved.
"""
import argparse
import gzip
import hashlib
import json
import pathlib
import shutil
import subprocess
import time
import uuid
import zlib


PINNED_DLL_SHA256 = "65e4c1f855f9ef6e8f0f5df8e3f27d9eb5f07311408639da0a1ca0b8f4871b0d"
DECODED_SIZE = 149 * 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot(directory):
    return {str(path.relative_to(directory)): (path.stat().st_size, sha256(path))
            for path in directory.rglob("*") if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=pathlib.Path, required=True)
    parser.add_argument("--stalled-helper", type=pathlib.Path, required=True)
    parser.add_argument("--helper", type=pathlib.Path, required=True)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    checks = 0

    def require(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise RuntimeError(message)

    for path in (args.probe, args.stalled_helper, args.helper):
        require(path.is_file(), f"Missing executable: {path}")
    source_dll = args.helper.parent / "xfusevenzip2603.dll"
    require(source_dll.is_file(), f"Missing pinned runtime DLL: {source_dll}")
    require(sha256(source_dll) == PINNED_DLL_SHA256, "7-Zip 26.03 DLL checksum mismatch")
    args.root.mkdir(parents=True, exist_ok=True)
    run = args.root.resolve() / f"run-{uuid.uuid4().hex}"
    runtime = run / "runtime"
    runtime.mkdir(parents=True)
    probe = runtime / "backend_probe.exe"
    stalled = runtime / "stalled_helper.exe"
    helper = runtime / "xfu_sevenzip_helper.exe"
    dll = runtime / "xfusevenzip2603.dll"
    for original, copy in ((args.probe, probe), (args.stalled_helper, stalled),
                           (args.helper, helper), (source_dll, dll)):
        shutil.copyfile(original, copy)
        require(sha256(original) == sha256(copy), f"Runtime copy differs: {copy}")

    # No decoded fixture file exists: only a deterministic compressed input.
    fixture = run / "large149.bin.gz"
    block = bytes(range(256)) * 256
    payload_digest = hashlib.sha256()
    with fixture.open("wb") as output:
        with gzip.GzipFile(fileobj=output, filename="", mode="wb", mtime=0,
                           compresslevel=6) as archive:
            for _ in range(DECODED_SIZE // len(block)):
                archive.write(block)
                payload_digest.update(block)
    before = snapshot(run)
    start = time.monotonic()
    completed = subprocess.run([str(probe), str(stalled), str(helper), str(fixture),
                                str(DECODED_SIZE)], cwd=runtime, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=120)
    elapsed = time.monotonic() - start
    require(completed.returncode == 0,
            f"Backend controls failed ({completed.returncode}):\n{completed.stdout}\n{completed.stderr}")
    proof = json.loads(completed.stdout)
    require(proof.get("checks", 0) >= 68, "Native controls did not all execute")
    require(proof.get("decoded_size") == DECODED_SIZE, "Decoded size differs")
    for field in ("stalled_write_timeout", "stalled_write_cancel", "member_progress"):
        require(proof.get(field) is True, f"Missing passing control: {field}")
    require(snapshot(run) == before, "TEST created or changed runtime/input files")
    report = dict(runner_checks=checks, native=proof, elapsed_seconds=elapsed,
                  decoded_sha256=payload_digest.hexdigest(), decoded_size=DECODED_SIZE,
                  compressed_sha256=sha256(fixture), dll_sha256=PINNED_DLL_SHA256,
                  helper_sha256=sha256(helper), zlib_version=zlib.ZLIB_RUNTIME_VERSION,
                  test_created_or_changed_files=False, run=str(run))
    # Persist evidence only after all TEST operations have returned.
    (run / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
