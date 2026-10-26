"""Pin the archive features available before the compatibility backend changed.

Run with ``python3 test_archive_feature_contract.py /path/to/xfu``. The larger
archive integration suite exercises the advertised operations; this test stops
its capability-based skips from hiding a removed operation.
"""

import re
import subprocess
import sys
import unittest
from pathlib import Path


XFU = None

FORMAT_READ = frozenset(
    "tar pax pax_restricted gnutar ustar v7tar tar_solaris "
    "cpio cpio_newc cpio_odc cpio_bin cpio_bin_le cpio_bin_be "
    "cpio_crc cpio_afio cpio_pwb ar ar_bsd ar_svr4 mtree "
    "mtree_classic iso9660 zip 7zip warc xar raw cab lha rar "
    "rar5 rpm empty".split()
)
FORMAT_CREATE = frozenset(
    "tar pax pax_restricted gnutar ustar v7tar "
    "cpio cpio_newc cpio_odc cpio_bin cpio_bin_le cpio_pwb "
    "ar ar_bsd ar_svr4 mtree mtree_classic iso9660 shar "
    "shar_dump zip 7zip warc xar raw".split()
)
FILTER_READ = frozenset(
    "none gzip bzip2 compress lzma xz lzip lz4 lzop zstd "
    "uuencode b64encode rpm".split()
)
FILTER_CREATE = frozenset(
    "none gzip bzip2 compress lzma xz lzip lz4 lzop zstd "
    "uuencode b64encode".split()
)


class ArchiveFeatureContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XFU is None or not XFU.is_file():
            raise RuntimeError("Usage: python3 test_archive_feature_contract.py /path/to/xfu")
        result = subprocess.run(
            [str(XFU), "--capabilities"], capture_output=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.capabilities = {}
        for kind, name, read, create in re.findall(
            r"^\s*(format|filter)\s+(\S+)\s+read=(yes|no)\s+create=(yes|no)",
            result.stdout, re.MULTILINE,
        ):
            cls.capabilities[(kind, name)] = (read == "yes", create == "yes")

    def test_readers(self):
        for kind, names in (("format", FORMAT_READ), ("filter", FILTER_READ)):
            with self.subTest(kind=kind):
                missing = sorted(name for name in names if not self.capabilities.get((kind, name), (False, False))[0])
                self.assertFalse(missing, f"Missing {kind} readers: {', '.join(missing)}")

    def test_writers(self):
        for kind, names in (("format", FORMAT_CREATE), ("filter", FILTER_CREATE)):
            with self.subTest(kind=kind):
                missing = sorted(name for name in names if not self.capabilities.get((kind, name), (False, False))[1])
                self.assertFalse(missing, f"Missing {kind} writers: {', '.join(missing)}")


if __name__ == "__main__":
    XFU = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None
    unittest.main(verbosity=2)
