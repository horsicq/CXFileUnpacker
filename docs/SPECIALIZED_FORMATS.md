# Specialized Formats

XFU compiles its shared engine and codec/archive support from the local
`xxfclib::xfileunpacker_core` component. It does not download codec sources,
search for system codec packages, or launch
PeaZip, FreeArc, PAQ, LPAQ, QUAD, UPX or another compression executable.
`xfu --capabilities` reports the exact read and create operations in a built
executable; `read=partial` is not unrestricted compatibility.

| Selector | Creation | Reading |
| --- | --- | --- |
| `pea` | Multiple regular files; level 0 stored, levels 1/2/3 DEFLATE 3/6/9; default 2 | Native plaintext PEA reader; encrypted modes and unsupported algorithms remain unavailable. |
| `freearc`, `wrc` | Multiple regular files; stored by default; explicit LZMA levels 0..5 | Native FreeArc reader supports a limited compression-method set, not arbitrary chains or encryption. |
| `split` | One regular file, raw `.001`..`.999` volumes; default 10 MiB each | Library joining of a supported contiguous series; no header, checksum or recorded final count. |
| `freearc_sfx` | Windows XFU extraction-only stub with stored or LZMA FreeArc payload | Checked XFU overlay locator followed by the native FreeArc reader. |
| `brotli` | Unavailable | xxfclib stream decoder. |
| `zpaq` | Unavailable | xxfclib plaintext streaming and journaling reader. |
| `balz`, `bcm` | Unavailable | Bounded xxfclib readers. |
| `quad`, `lpaq1`, `lpaq5`, `lpaq8` | Unavailable | Their payload paths require a disabled helper process. |
| `paq8`, `paq8f`, `paq8jd`, `paq8l`, `paq8o` | Unavailable | Their payload paths require a disabled helper process. |
| `upx` | Unavailable | Its unpacking path requires a disabled helper process. |
| `7zip_sfx` | Unavailable | Existing 7-Zip SFX inputs remain readable through the available 7-Zip paths. |

An attempt to create a reader-only format fails explicitly. Keeping its selector
recognized provides a useful diagnostic instead of silently selecting another
format.

```text
xfu a files.pea first.txt second.txt --compression-level=2
xfu a files.arc first.txt second.txt --compression=lzma --compression-level=5
xfu a payload.001 input.bin --volume-size=10M
xfu a archive.exe first.txt second.txt --format=freearc_sfx
```

## Bounds And Safety

Creation validates regular inputs, rejects links and output self-aliases, and
streams through bounded callback IO. A completed PEA or FreeArc archive replaces
its destination from an exclusively opened sibling staging file; cancellation
and failure discard the stage and preserve an existing destination. Numbered
split creation refuses existing parts, stages the entire series and rolls back
its own newly published parts on failure. Multiple renames are not a single
filesystem transaction.

PEA uses 1 MiB member blocks with CRC-32 member, stream and volume checks.
FreeArc uses one independently compressed block per file and CRC-32 member and
control checks. Its limits are 100,000 files, 256 MiB per file and 64 MiB per
control block. The LZMA dictionary is at most 16 MiB (default level: 5),
with an estimated encoder-allocation cap of 256 MiB. DEFLATE, LZMA and CRC code
for these writers comes from xxfclib.

Formats without checksums cannot certify all damaged input. Raw split TEST
checks series structure and readability but cannot detect changed bytes or a
missing final volume. Input size and EOF are checked, but source contents are
not snapshotted: concurrent same-size modification has no point-in-time
consistency guarantee. CRC-32 detects accidental damage, not malicious change.

## Provenance And Distribution

The PEA and FreeArc framing and split backends are MIT C code. PEA follows the
official Pea format and uses xxfclib's DEFLATE encoder. FreeArc follows the
author's archive specification and uses xxfclib's raw LZMA1 encoder. See
[FreeArc Writer](FREEARC_WRITER.md) and
[Numbered Split Volumes](SPLIT_FORMAT.md) for format-specific contracts and
interoperability checks.

The current build does not compile the former BALZ/BCM, QUAD/LPAQ/PAQ, UPX or
7-Zip SFX creation adapters. Their source and license notices, if retained in
the tree for reference, do not describe code linked into this build.

## Verification

Focused CLI suites cover PEA, FreeArc and raw splitting. The core C API suite
checks cancellation after a stage exists, preservation of existing outputs,
split record selection, callback progress and multi-part publication rollback.
FreeArc stored and LZMA output has also been tested and byte-exactly extracted
by the original FreeArc 0.666 unpacker. Platform-specific verification is
recorded in the individual format documents.
