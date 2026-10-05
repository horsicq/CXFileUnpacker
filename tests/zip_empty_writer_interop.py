#!/usr/bin/env python3
"""Plain, ZipCrypto and AES-256 empty ZIP interoperability, methods 8 and 9."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--sevenzip", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve() / ("run-" + time.strftime("%Y%m%d-%H%M%S") + "-" + str(os.getpid()))
    root.mkdir(parents=True)
    temp = root / "TEMP-is-a-file"
    temp.write_bytes(b"No compression or TEST spool files.\n")
    env = os.environ.copy()
    env.update({"TEMP": str(temp), "TMP": str(temp), "TMPDIR": str(temp)})
    report = []
    try:
        for method in (8, 9):
            for encryption in ("none", "crypto", "aes256"):
                archive = root / f"deflate-{method}-{encryption}.zip"
                command = [str(args.probe.resolve()), str(method), encryption, str(archive)]
                controls = subprocess.run(command, env=env, stdin=subprocess.DEVNULL,
                                          capture_output=True, timeout=60, check=True)
                properties = json.loads(controls.stdout)
                password = [] if encryption == "none" else ["-pempty ZIP writer password"]
                subprocess.run([str(args.sevenzip.resolve()), "t", "-bd", "-bb0", str(archive)] + password,
                               capture_output=True, stdin=subprocess.DEVNULL, timeout=60, check=True)
                decoded = subprocess.run([str(args.sevenzip.resolve()), "x", "-so", "-bd", str(archive)] + password,
                                         capture_output=True, stdin=subprocess.DEVNULL, timeout=60, check=True)
                if decoded.stdout != b"":
                    raise AssertionError("Empty ZIP decoded nonempty bytes")
                report.append({"method": method, "encryption": encryption,
                               "controls": properties["checks"], "official_test": "passed",
                               "exact_empty_payload": True, "archive_bytes": archive.stat().st_size})
    except (OSError, AssertionError, subprocess.SubprocessError) as error:
        (root / "zip-empty-writer-report.json").write_text(
            json.dumps({"passed": False, "error": str(error), "cases": report}, indent=2))
        print(str(root), flush=True)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stdout.decode("utf-8", "replace"), flush=True)
            print(error.stderr.decode("utf-8", "replace"), flush=True)
        raise
    output = root / "zip-empty-writer-report.json"
    output.write_text(json.dumps({"passed": True, "controls": sum(r["controls"] for r in report),
                                  "cases": report}, indent=2))
    print(f"Six empty ZIP cases passed plain/ZipCrypto/AES-256 Deflate/Deflate64 with {sum(r['controls'] for r in report)} controls.")
    print(str(output))


if __name__ == "__main__":
    main()
