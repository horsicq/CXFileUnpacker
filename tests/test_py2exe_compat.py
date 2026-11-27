"""Exercise both py2exe launcher layouts without running a Windows program."""

import io
import marshal
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zipfile

from create_unpack_handle_fixtures import pe32, put16, put32


SCRIPT = marshal.dumps([compile("print('entry script')", "probe.py", "exec")])
MODULE = b"synthetic Python module bytes"


def launcher(library, *, damaged=False):
    image = bytearray(pe32())
    resource = memoryview(image)[512:]
    resource[:] = bytes(len(resource))
    struct.pack_into("<II", image, 152 + 112, 0x1000, 512)
    image[152 + 224:152 + 224 + 8] = b".rsrc\0\0\0"
    put32(image, 152 + 224 + 8, 512)
    put32(image, 152 + 224 + 36, 0x40000040)
    put16(resource, 12, 1)
    struct.pack_into("<II", resource, 16, 0x80000000 | 88, 0x80000000 | 24)
    put16(resource, 38, 1)
    struct.pack_into("<II", resource, 40, 1, 0x80000000 | 48)
    put16(resource, 62, 1)
    struct.pack_into("<II", resource, 64, 1033, 72)
    type_name = "PYTHONSCRIPT".encode("utf-16le")
    put16(resource, 88, len(type_name) // 2)
    resource[90:90 + len(type_name)] = type_name
    data = struct.pack("<IIII", 0x78563412, 0, 0, len(SCRIPT) + damaged) + library + b"\0" + SCRIPT + b"\0"
    struct.pack_into("<IIII", resource, 72, 0x1000 + 128, len(data), 0, 0)
    resource[128:128 + len(data)] = data
    return bytes(image)


def with_zip(prefix=b""):
    stream = io.BytesIO(prefix)
    with zipfile.ZipFile(stream, "a") as archive:
        archive.writestr("probe_helper.pyc", MODULE)
    return stream.getvalue()


def main():
    executable = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="xfu-py2exe-") as temp:
        root = Path(temp)

        def run(*args, success=True):
            proc = subprocess.run([str(executable), *map(str, args)], cwd=root,
                                  capture_output=True, text=True, timeout=60)
            assert (proc.returncode == 0) == success, (args, proc.stdout, proc.stderr)
            return proc.stdout + proc.stderr

        for name, data, embedded in [
            ("external.exe", launcher(b"library.zip"), False),
            ("embedded.exe", with_zip(launcher(b"")), True),
        ]:
            (root / name).write_bytes(data)
            assert f"{name}: py2exe" in run("l", name)
            assert "entry-scripts.pyc.marshal" in run("l", name, "--reader", "py2exe")
            run("t", name)
            output = root / (name + "-out")
            run("x", name, "-o" + str(output))
            assert (output / "0000-entry-scripts.pyc.marshal").read_bytes() == SCRIPT
            recovered = output / "0001-payload.zip"
            assert recovered.exists() == embedded
            if embedded:
                assert recovered.read_bytes()[:4] == b"PK\x03\x04"
                run("x", recovered, "--reader", "native:zip", "-o" + str(output))
                assert (output / "probe_helper.pyc").read_bytes() == MODULE

        (root / "library.zip").write_bytes(with_zip())
        assert "library.zip: ZIP" in run("l", "library.zip", "--reader", "native:zip")
        (root / "invalid.exe").write_bytes(launcher(b"library.zip", damaged=True))
        assert "header does not hold up" in run("l", "invalid.exe", "--reader", "py2exe", success=False)

    print("py2exe launcher identification, exact script recovery and ZIP round trip passed")


if __name__ == "__main__":
    main()
