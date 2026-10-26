# PeaZip Compatibility

This audit compares XFileUnpacker with PeaZip 11.3.0 and its `sources` branch
as inspected on 2026-10-10. PeaZip's current release uses Pea 1.33 and
7-Zip / p7zip 26.03. PeaZip is a frontend for several archivers, not one
all-format library. Its published extension count includes aliases, package
containers, split-volume names and optional external programs.

The XFU build remains library-only: it does not launch PeaZip or install its
command-line backends. The shared engine and codec/archive code are compiled
from the local `xxfclib::xfileunpacker_core` component selected by
`XFILEUNPACKER_XXFCLIB_DIR`. CMake does not fetch codec sources or search for
system codec packages.

Most named read families already exist in xxfclib; that does not establish
compatibility with every compression method, encrypted variant or volume
layout. The separate [archive matrix](ARCHIVE_FORMATS.md) describes the
available archive writers and stream filters.

## Capability Report

`xfu --capabilities` is the authoritative report for a built executable. It
lists the retained application operations separately from the ordinary format
and filter rows. Representative rows in the xxfclib-only build are:

```text
native brotli read=yes create=no
native zpaq read=partial create=no
native pea read=partial create=yes
native freearc read=partial create=yes
native split read=partial create=yes
native upx read=no create=no
native 7zip_sfx read=partial create=no
```

On Windows, a build with the local XFU FreeArc stub also reports:

```text
native freearc_sfx read=partial create=yes
```

`read=yes` identifies an available library reader, not a guarantee about every
possible file. `partial` identifies known format-level limitations. `no`
identifies an unavailable operation, including one whose only implementation
needs a disabled helper process. The broad `--formats` detection list
must not be used as an extraction or creation matrix.

## Creation Matrix

This table covers PeaZip's creation families rather than every filename suffix.

| Family | PeaZip Create | XFU Create | Notes |
| --- | --- | --- | --- |
| 7-Zip | Yes | Yes | Codec choices and solid/encryption options differ. |
| ZIP / ZIPX | Yes | Yes | ZIPX is a ZIP variant, not a separate container. |
| TAR and compressed TAR | Yes | Yes | Native writers; filter availability varies. |
| WIM | Yes | Yes | Stored output only; XPRESS, LZX and LZMS creation is rejected. |
| GZIP, BZIP2, XZ | Yes | Yes | Single-file streams; use TAR for multiple files. |
| Zstandard | Yes | Yes | Native stream writer. |
| Brotli | Yes | No | The xxfclib build supplies a decoder, but no encoder. |
| PEA | Yes | Yes, limited | Plaintext stored/DEFLATE PEA, levels 0..3; no encryption or volumes. |
| FreeArc ARC / WRC | Yes | Yes, limited | Stored or LZMA output; see the writer notes. |
| ZPAQ | Yes | No | Existing xxfclib reader retained. |
| PAQ8F / JD / L / O | Yes | No | Helper-backed reading is disabled (`read=no`). |
| LPAQ1 / 5 / 8 | Yes | No | Helper-backed reading is disabled (`read=no`). |
| QUAD / BALZ / BCM | Yes | No | QUAD helper reading is disabled; native BALZ and BCM readers remain. |
| Numbered split output | Yes | Yes | Raw `.001`..`.999` parts, not archive compression. |
| UPX packing | Yes | No | Helper-backed unpacking is disabled (`read=no`). |
| 7-Zip self-extracting output | Yes | No | Ordinary 7-Zip SFX files remain readable where reported. |
| FreeArc self-extracting output | Yes | Yes, Windows | XFU extraction-only stub with a genuine FreeArc payload. |
| RAR | External Rar.exe | No | PeaZip's creation is conditional, not a bundled writer. |

PeaZip can use additional 7-Zip-ZS codecs, including Brotli, FLZMA2, Lizard,
LZ4 and LZ5, as well as Deflate64. XFU's 7-Zip writer does not promise those
method choices. Current ZIP / 7-Zip choices are described in the archive
matrix, and rejected methods return an error. Repair, update-in-place, recovery
records, keyfile conventions and arbitrary custom backends are separate
features, not new container formats.

## Reader Gaps

The following are confirmed gaps, not missing suffixes:

| Family | Existing XFU Reader | Remaining Difference |
| --- | --- | --- |
| PEA | Unencrypted stored and DEFLATE streams | Password/HMAC/EAX streams expose no members; members continuing into another PEA volume cannot be extracted. |
| FreeArc | Selected method chains | Supports storing, LZMA, rep, exe, delta and bounded LZP. Other chains such as tor, PPMd, GRZIP, dict and encryption are not unpacked. |
| FreeArc SFX | Checked XFU PE-overlay locator plus native FreeArc reader | Generated XFU stubs are supported; unrelated third-party SFX layouts are not universally recognized. |
| Brotli | Complete stream decoder | The stream has no embedded filename; decoder workspace and size limits apply. |
| ZPAQ | Plaintext streaming and journaling | Encrypted archives without a plaintext signature are not recognized. |
| PAQ8 | Detection/catalog entry only | Helper-backed payload decoding is disabled. |
| QUAD / LPAQ1 / LPAQ5 / LPAQ8 | Detection/catalog entries only | Helper-backed payload decoding is disabled. |
| BALZ / BCM | Native xxfclib readers | Bounded input, output and workspace limits remain. |
| UPX | Detection/catalog entry only | Helper-backed unpacking is disabled. |
| Numbered split | In-process raw-volume reader | `.001` first volume required; no checksum or final-count metadata exists. |
| Explicit 7-Zip engine handlers | Disabled | These are helper operations, not in-process library coverage. |
| ZIM | Bounded primary-layout reader | At most 2,048 entries, 1,024 clusters and 1 MiB decoded per cluster; stored, XZ and Zstd clusters only. Typical large Wikipedia dumps are outside these limits. |
| Other archive/image families | Native handlers only | Helper-backed handlers are disabled; native per-reader limits remain. |

The ZIM parser also limits total decoded content to 64 MiB and shortens exported
names to its fixed-size name buffer. An `OPENZIM` detection entry must therefore
not be represented as unrestricted compatibility with PeaZip's ZIM operation.
This build reports helper-only operations as `read=no` and never launches them.

PeaZip routes CAB, ARJ, LHA, CHM/HXS, CPIO, ISO/UDF, XAR, RPM, DMG/HFS,
filesystem and disk-image containers through 7-Zip. XFU has corresponding
reader families, but this audit does not certify every image variant. Office
and application packages are usually archive containers, not document
rendering or package installation. ACE support in PeaZip may require the
optional proprietary UnACE component; it is not an unconditional capability.

## Suffix Aliases

XFU recognizes these creation aliases without inventing new formats:

| Suffixes | Archive / Stream |
| --- | --- |
| `.cb7` | 7-Zip |
| `.cbz`, `.smzip`, `.jar`, `.ear`, `.war`, `.apk`, `.xpi`, `.kmz`, `.epub` | ZIP |
| Selected OOXML and ODF archive suffixes | ZIP |
| `.cbt` | TAR |
| `.tpz` | TAR + GZIP |
| `.tbz`, `.tbz2`, `.tbzip`, `.tbzip2`, `.tb2` | TAR + BZIP2 |
| `.tzst` | TAR + Zstandard |
| `.taz`, `.tz` | TAR + Unix compress |

These create generic archive payloads only. They do not generate application
manifests, sign APKs, author EPUB metadata, or make valid office documents from
arbitrary input files. Ambiguous suffixes such as `.pak`, `.sar` and `.ppmd`
are not forced to ZIP merely because PeaZip dispatches them to a common backend.
Existing content-based reading remains available independently of the suffix.

## Reader-Only PeaZip Families

The xxfclib-only build keeps the Brotli, ZPAQ, BALZ and BCM in-process read
paths without compiling their former application-side writers. QUAD, LPAQ,
PAQ and UPX require helpers and therefore report `read=no create=no`. For
example:

```text
xfu t input.br --reader brotli
xfu x archive.zpaq --reader zpaq -ooutput
xfu t data.balz --reader balz
```

An `a` request for one of these formats fails explicitly as unavailable in the
xxfclib-only build. The same applies to `--format=7zip_sfx`; the build does not
download or compile a 7-Zip SFX stub.

## Retained Specialized Writers

```text
xfu a archive.pea first.bin second.bin --compression-level=2
xfu a archive.arc first.bin second.bin --compression=store
xfu a data.001 input.bin --volume-size=10M
xfu a archive.exe first.bin second.bin --format=freearc_sfx --compression=lzma
```

PEA accepts individual regular files and levels 0 (stored), 1, 2 (default)
and 3 (DEFLATE presets 3, 6 and 9). It writes standard plaintext PEA with
CRC-32 integrity metadata. Directory recursion, encryption and multivolume PEA
are unavailable. Its DEFLATE and CRC implementation comes from xxfclib.

FreeArc accepts individual regular files, stored output by default, or explicit
LZMA levels 0 through 5. Its LZMA and CRC implementation also comes from
xxfclib. See [FreeArc writer](FREEARC_WRITER.md) for the format, bounds and
Windows SFX contract. See [split volumes](SPLIT_FORMAT.md) for raw volume
creation and joining.

## Verification

Run the focused checks against a built executable:

```text
python tests/test_peazip_compat.py path/to/xfu
ctest --test-dir path/to/build -C Release --output-on-failure
```

The capability report should show `create=no` for every reader-only family and
`create=yes` for PEA, FreeArc and split. Windows builds with the local FreeArc
stub additionally report `freearc_sfx create=yes`. These checks do not certify
unrestricted reader parity; the documented gaps remain visible.
