#!/usr/bin/env python3
"""Verify public raw-stream writers against an independent official 7-Zip."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--sevenzip", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    args.probe = args.probe.resolve(strict=True)
    args.sevenzip = args.sevenzip.resolve(strict=True)
    root = args.root.resolve() / ("run-" + time.strftime("%Y%m%d-%H%M%S") + "-" + str(os.getpid()))
    root.mkdir(parents=True)
    temp = root / "TEMP-is-a-file"
    temp.write_bytes(b"Native device writers must not spool to temporary files.\n")
    env = os.environ.copy()
    env.update({"TEMP": str(temp), "TMP": str(temp), "TMPDIR": str(temp)})
    report = []
    cases = {"binary": bytes(range(256)) * 257 + b"Native writer streaming\0proof\xff" * 20,
             "empty": b""}
    try:
        for name, payload in cases.items():
            source = root / (name + ".bin")
            source.write_bytes(payload)
            for kind in ("gz", "bz2", "xz"):
                archive = root / (name + "." + kind)
                controls = subprocess.run([str(args.probe), kind, str(source), str(archive)],
                                          env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                          timeout=60, check=True)
                matches = re.search(rb"\b(\d+)\s*controls passed", controls.stdout)
                if not matches:
                    raise AssertionError("Probe did not report completed API controls")
                subprocess.run([str(args.sevenzip), "t", "-bd", "-bb0", str(archive)],
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=60, check=True)
                decoded = subprocess.run([str(args.sevenzip), "x", "-so", "-bd", str(archive)],
                                         stdin=subprocess.DEVNULL, capture_output=True,
                                         timeout=60, check=True).stdout
                if decoded != payload:
                    raise AssertionError(kind + " official decoded bytes differ from original")
                report.append({"case": name, "format": kind, "controls": int(matches[1]),
                               "official_test": "passed", "payload_bytes": len(payload),
                               "payload_sha256": sha256(payload),
                               "archive_sha256": sha256(archive.read_bytes())})
    except (AssertionError, OSError, subprocess.SubprocessError) as error:
        (root / "single-stream-writer-report.json").write_text(
            json.dumps({"passed": False, "error": str(error), "cases": report}, indent=2), encoding="utf-8")
        print(str(root), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stdout.decode("utf-8", "replace"), file=sys.stderr)
            print(error.stderr.decode("utf-8", "replace"), file=sys.stderr)
        print(str(error), file=sys.stderr)
        return 1
    checks = sum(case["controls"] for case in report)
    output = root / "single-stream-writer-report.json"
    output.write_text(json.dumps({"passed": True, "controls": checks, "cases": report}, indent=2), encoding="utf-8")
    print(f"Passed {checks} public API controls and six independent 7-Zip tests and exact decoded matches.")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
