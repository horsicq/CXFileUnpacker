"""Public engine adapter: RAM testing, live limits, owned options and extraction."""
import argparse
import bz2
import gzip
import hashlib
import io
import json
import lzma
import pathlib
import subprocess
import tarfile
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=pathlib.Path, required=True)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    payload = bytes(range(256)) * 1573 + b"\x00end\xff"
    expected = {"directory/hello.bin": payload, "empty.txt": b"", "unicode-\u03a9.txt": b"utf8 name\n"}
    fixtures = []
    for method in (0, 8, 12, 14):
        packed = io.BytesIO()
        with zipfile.ZipFile(packed, "w", compression=method) as archive:
            archive.writestr("directory/", b"")
            for name, data in expected.items():
                archive.writestr(name, data)
        fixtures.append((f"zip-{method}.zip", "zip", packed.getvalue(), expected))
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w") as archive:
        directory = tarfile.TarInfo("directory/")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        for name, data in expected.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    fixtures.append(("archive.tar", "tar", packed.getvalue(), expected))
    fixtures.extend((name, handler, encoder(payload), None) for name, handler, encoder in (
        ("payload.gz", "gzip", gzip.compress), ("payload.bz2", "bzip2", bz2.compress),
        ("payload.xz", "xz", lzma.compress),
        ("payload.lzma", "lzma", lambda data: lzma.compress(data, format=lzma.FORMAT_ALONE))))
    (args.root / "pieces.002").write_bytes(payload[111111:333333])
    (args.root / "pieces.003").write_bytes(payload[333333:])
    fixtures.append(("pieces.001", "Split", payload[:111111], None))
    report = []
    for filename, handler, source, members in fixtures:
        image = args.root / filename
        image.write_bytes(source)
        for selected in (handler, "auto"):
            # A fresh path makes successful atomic extraction reviewable and
            # permits repeat runs without an overwrite option.
            import uuid
            output = args.root / f"output-{filename}-{selected}-{uuid.uuid4().hex[:8]}"
            completed = subprocess.run([str(args.probe), str(image), selected, "", str(output)],
                                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
            assert completed.returncode == 0, (filename, selected, completed.stdout, completed.stderr)
            proof = json.loads(completed.stdout)
            actual = {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob("*") if p.is_file()}
            if members is None:
                assert len(actual) == 1 and next(iter(actual.values())) == payload, (filename, actual.keys())
            else:
                assert actual == members, filename
                assert (output / "directory").is_dir()
            report.append(dict(name=filename, selected=selected, proof=proof,
                               source_sha256=hashlib.sha256(source).hexdigest(),
                               output_sha256={name: hashlib.sha256(data).hexdigest() for name, data in actual.items()}))
    # Names from a different filesystem remain available for LIST and TEST.
    # A traversal name must never be concatenated into an output path.
    unsafe_names = ["../escape.bin", "host:invalid.txt", "CON.foo", "nested/NUL.txt", "PrN.bin",
                    "AUX", "COM1.log", "COM9", "LPT1.bin", "LPT9", "CONIN$.txt", "CONOUT$",
                    "COM\u00b9.txt", "LPT\u00b2.txt", "COM\u00b3.txt"]
    for number, unsafe_name in enumerate(unsafe_names):
        unsafe = args.root / f"unsafe-path-{number}.zip"
        packed = io.BytesIO()
        with zipfile.ZipFile(packed, "w") as archive:
            archive.writestr(unsafe_name, b"foreign filesystem name\n")
        unsafe.write_bytes(packed.getvalue())
        checked = subprocess.run([str(args.probe), str(unsafe), "zip"], capture_output=True, text=True, timeout=180)
        assert checked.returncode == 0, (checked.stdout, checked.stderr)
        output = args.root / f"unsafe-extraction-{number}"
        denied = subprocess.run([str(args.probe), str(unsafe), "zip", "", str(output)], capture_output=True, text=True, timeout=180)
        assert denied.returncode != 0 and not (args.root / "escape.bin").exists() and not output.exists(), unsafe_name
        report.append(dict(name=unsafe.name, member_name=unsafe_name, selected="zip", proof=json.loads(checked.stdout), denied_unsafe_extraction=True))
    (args.root / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{sum(item['proof']['checks'] for item in report)} checks across {len(report)} public adapter runs, all extracted bytes match")


if __name__ == "__main__":
    main()
