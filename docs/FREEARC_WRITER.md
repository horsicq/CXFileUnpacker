# FreeArc Writer

XFU creates real plaintext FreeArc archives through a C library backend, without
launching FreeArc or another helper. This is the `ArC\x01` FreeArc container,
not the older SEA ARC format. The implementation follows the archive author's
[format description](https://github.com/Bulat-Ziganshin/FA/blob/master/FreeArc-archive-format.md)
and the original
[directory](https://github.com/mirror/freearc/blob/master/ArhiveDirectory.hs) and
[control-block serialization](https://github.com/mirror/freearc/blob/master/ArhiveStructure.hs).

```text
xfu a output.arc first.txt second.txt
xfu a output.wrc first.txt --compression=storing
xfu a output.bin first.txt --format=freearc --compression-level=0
xfu a compressed.arc first.txt second.txt --compression=lzma --compression-level=5
xfu l output.arc --reader freearc
xfu t output.arc --reader freearc
xfu x output.arc --reader freearc -ooutput
```

## Supported Output

The writer accepts multiple individual regular files, including empty files.
It writes an independent stored or raw LZMA data block for each file, UTF-8 names,
PKZIP-compatible CRC-32 member checksums, and checksummed header, directory and
footer blocks. Relative subdirectories are retained; absolute inputs and inputs
containing a parent-directory component use their basename. Duplicate normalized
member names and unsafe or oversized names are rejected.

Stored compression is the default. The aliases `store`, `stored` and `storing`,
and compression level `0`, are accepted. Explicit `--compression=lzma` selects
xxfclib's raw LZMA1 encoder, with levels `0` through `5` and default
level `5`. Level `0` in LZMA mode is fast compression, not stored output.
Other methods and levels return an error instead of being silently ignored.
Directory recursion, links, encryption, custom options, outer filters, recovery
records and update-in-place are not supported. The ordinary container writer
does not add a self-extracting stub; the separate Windows selector below does.
Timestamps
are recorded as the FreeArc minimum value, the Unix epoch; permissions and other
filesystem metadata are not preserved. CRC-32 is an integrity check, not
cryptographic authentication.

The current limits are 100,000 files, 256 MiB per file, a name shorter than
32,767 UTF-8 bytes, and 64 MiB per control block. Data is processed in 64 KiB chunks
with cancellation checks; the writer does not buffer complete file contents.
LZMA dictionaries are capped at 16 MiB (the default level requests up to 16 MiB), and the
encoder's estimated allocation must not exceed 256 MiB. High presets therefore
do not request their usual larger dictionaries. This encoder workspace is
separate from the native reader's decoding-workspace budget.
Native reader allocation and decoding limits still apply during subsequent
reading. `native freearc read=partial create=yes` describes this limited writer
and the existing native reader, not every compression/encryption option offered
by FreeArc.

## Output Safety

All inputs are validated before a staging file is created. Source links,
directories, missing files and the destination itself, including hard-link
aliases, are rejected. Creation writes an exclusively opened sibling staging
file and replaces the destination only after successful finalization. Errors or
cancellation discard staging output and preserve an existing destination.

Source size and EOF are checked, but input contents are not snapshotted.
Concurrent same-size modification is not detected and does not provide a
point-in-time consistency guarantee.

## Windows Self-Extracting Output

```text
xfu a archive.exe first.txt second.txt --format=freearc_sfx
xfu a compressed.exe first.txt --format=freearc_sfx --compression=lzma --compression-level=5
archive.exe t
archive.exe x -oextracted
```

`--format=freearc_sfx` explicitly embeds XFU's source-built MIT extraction-only
Windows stub, followed by a genuine FreeArc payload and an XFU locator. An
arbitrary `.exe` destination does not select SFX creation. The stub uses the
existing native FreeArc reader, not the original GPL Unarc executable. Stored
output is the default; explicit LZMA levels 0..5 and the ordinary writer's
input/compression limits apply. Passwords, custom options and outer filters are
rejected. `XFILEUNPACKER_BUILD_FREEARC_SFX=OFF` omits this optional Windows stub.

When deliberately launched, the generated executable supports `l`, `t` and `x`,
`-oDIR`, and explicit `-y` overwrite opt-in. It never executes archived members.
It validates names and checks CRCs before publication, extracts into a private
staging directory and publishes individual files atomically. Publication of
multiple members is not one filesystem transaction. Windows-unsafe names,
Unicode case-fold collisions, file/directory ancestor aliases, paths exceeding
128 directory levels and more than 64 MiB of names are rejected.

The original FreeArc 0.666 unpacker successfully tested the complete generated
self-extracting file as a FreeArc archive. This interoperability check does not
make the XFU stub an original FreeArc program or add unsupported FreeArc codecs.

## Verification

```text
python tests/test_freearc_compat.py path/to/xfu
python tests/test_freearc_compat.py path/to/xfu --upstream-unarc=path/to/unarc.exe
```

The focused suite independently parses descriptors, variable-length integers,
directory arrays and member/control CRCs, independently decodes raw LZMA with
Python's standard library, then lists, tests and extracts with
the native reader. It covers empty and Unicode files, subdirectories, aliases,
invalid inputs/options, preservation on failure and corrupted/truncated input.
The optional upstream executable is used only for interoperability tests, never
by the application backend. FreeArc's original 0.666 unpacker successfully
tested and byte-exactly extracted generated stored and LZMA archives, including
levels 0, 1 and 5, multiple, empty, Unicode and nested members, on Windows x64.
All 14 focused CLI tests passed in the Windows MSVC Release build. Linux and
32-bit builds have not been run.
