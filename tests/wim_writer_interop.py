"""Verify native WIM creation with the official independent 7-Zip decoder."""
import argparse
import hashlib
import json
import pathlib
import subprocess


def run(argv):
    completed = subprocess.run(list(map(str, argv)), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=120)
    if completed.returncode:
        raise RuntimeError(f"{argv}: {completed.returncode}\n{completed.stdout}\n{completed.stderr}")
    return completed.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=pathlib.Path, required=True)
    parser.add_argument("--sevenzip", type=pathlib.Path, required=True)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    cases = []
    for mode in ("full", "short", "base", "empty", "invalid"):
        image = args.root / f"{mode}.wim"
        native = json.loads(run([args.probe, image, mode]))
        item = {"mode": mode, "native": native}
        if mode != "invalid":
            independent_image = image
            if mode == "base":
                independent_image = args.root / "base-without-prefix.wim"
                independent_image.write_bytes(image.read_bytes()[17:])
                assert image.read_bytes()[:17] == b"XFU-prefix-17BYTE"
            item["independent_test"] = run([args.sevenzip, "t", "-sccUTF-8", independent_image])
            if mode == "full":
                output = args.root / "independent-extraction"
                run([args.sevenzip, "x", "-y", "-sccUTF-8", image, f"-o{output}"])
                payload = bytes((i * 29 + (i >> 8)) & 255 for i in range(131071))
                expected = {"deep/path/payload.bin": payload, "copy.bin": payload,
                            "empty.bin": b"", "unicode-\u2603-\U0001f30d.txt": b"unicode\n",
                            "wide-\u03a9.txt": b"wide\n"}
                for name, data in expected.items():
                    assert (output / name).read_bytes() == data, name
                assert (output / "empty-directory").is_dir()
                assert {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()} == set(expected)
                item["exact_payload_sha256"] = {name: hashlib.sha256(data).hexdigest()
                                                   for name, data in expected.items()}
        cases.append(item)
    report = {"cases": cases, "native_checks": sum(case["native"]["checks"] for case in cases),
              "sevenzip_sha256": hashlib.sha256(args.sevenzip.read_bytes()).hexdigest()}
    (args.root / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{report['native_checks']} native checks, four official 7-Zip archive tests and five exact payload matches passed")


if __name__ == "__main__":
    main()
