# Archive formats and stream filters

XFileUnpacker reads archives through xxfclib and writes them through native
format adapters. `xfu --capabilities` is the runtime list of available
`format` and `filter` operations. A detected file type in `xfu --formats`
does not by itself mean that its payload can be extracted or created.

## Reading

Automatic detection is the default. `--reader native` requests the same
in-process detection explicitly. `--reader native:raw` treats an ordinary
file as one archive member and uses the native decoder for a recognized
compressed stream. `--reader native:<format>` selects a specific format
reader, such as `native:tar` or `native:zip`; the reader still validates the
input. Listing, testing, and extraction use the same reader path.
`--reader native:empty` accepts a zero-byte archive with no members. The
legacy CPIO read options `--options=cpio:hdrcharset=CP437` and
`--options=cpio:pwb=1` decode CP437 filenames and PWB binary modes,
respectively. Automatic reading also unwraps nested compression and
Base64/uuencode envelopes before opening the inner archive. Whether a
compressed stream holds an archive is decided from its first 4 MiB once
decoded: evenly spread (compressed or encrypted) data is read as one file
without a temporary copy, so a plain `.gz`, `.xz` or `.bz2` of such data
lists, tests and extracts as one member whatever its size. Text is decoded
whole like other structured data, because the text record formats that
xxfclib reads as archives (FASTA, SAM, Wavefront OBJ and others) check every
line. A layer that holds an archive but exceeds the layer limit, or the RAM
that `t` may use, is read as one file too. Only a first line of the form
`begin <octal mode> <name>` or `begin-base64 <octal mode> <name>` (with 1 to
6 octal digits) makes a file an envelope, and several Base64 envelopes in one
file are one member each, as uuencoded blocks are; a later line that starts
with `begin-base64 ` but is no envelope header is listed as a member that
fails, never skipped. A `begin-base64` header line may be up to 4096 bytes
long, and a `====` line may end in spaces or tabs. A Base64 envelope whose
`====` line is missing still decodes when only blank lines separate it from
the next envelope, from NUL or 0x1A padding or from the end of the file, and
the file then reads as incomplete (exit code 1), whichever envelope it is.
It fails when other text does, also a line in the Base64 alphabet after its
last, shorter line, and wherever that text is, inside the first 64 KiB or
past them; only a first envelope whose name can be a member name must keep
its `====` line, or the file is an envelope that cannot be decoded. A later
uuencoded block whose data lines are followed by other text, its zero-length
and `end` lines lost, is listed as a member that fails. Member
names of up to 255 bytes are kept. A TAR hard link takes the data of the
member that extracts to the path it names, and a XAR hard link that of the
file whose id it names, following links to links; a link to a
symbolic link, a folder or a special file, and a TAR, CPIO or mtree symbolic
link itself, whatever its target, extracts as an empty placeholder. Test
does not follow links, but fails a hard link that names no member, as
extraction does. A crc (`070702`) CPIO reads like newc; Test and extraction
check each member's checksum. An ISO 9660 name without an extension
(`README.;1`) is `README`. A ZIP after other data (a script or a
self-extractor stub) opens from its end records, and one whose central
directory stops before the count its end record gives reads as incomplete in
`l` and `x` as well as `t`. A layer or envelope payload of up to 4 MiB is
decoded in memory; when a larger one that holds an archive finds no space for
its temporary copy, that is said, and the stream is read as one file. zstd
and LZ4 streams are decoded in memory, up to 1 GiB; a larger one is reported
as too large to open, not as damaged.

```text
xfu l archive.tar
xfu t archive.zip --reader native --verbose
xfu x image.iso -ooutput
xfu x input.bin --reader native:raw -ooutput
```

## Writing

`--format=<name>` selects the container or wire variant. `--filter=<name>`
wraps its output in a compressed or encoded stream when that combination is
supported. The output suffix is used when no format is specified. For raw
streams, provide exactly one regular input file.

```text
xfu a backup.tar alpha.txt beta.txt
xfu a backup.tar.gz alpha.txt beta.txt --format=pax --filter=gzip
xfu a archive.zip alpha.txt --compression=deflate
xfu a data.gz alpha.txt --format=raw --filter=gzip
```

The writer validates all input files, options, and selectors before replacing
the destination. Failed creation leaves an existing destination in place.
Compression methods and levels depend on the chosen format or filter;
unsupported combinations return an error. Use `xfu --capabilities` to see
which named formats and filters are compiled into the current build.
These writers handle their inputs alike, whether `xfu a` chooses one by suffix
(the xxfclib writers for `.tar`, `.tar.gz` / `.tgz`, `.tar.bz2` / `.tbz2`,
`.tar.xz` / `.txz`, `.tar.zst`, `.tar.lz4`, `.zip`, `.cpio`, `.7z`, `.gz`,
`.bz2`, `.xz` and `.wim`, and the native writers for suffixes such as `.pax`,
`.iso`, `.xar` or `.mtree`) or by `--format`, `--filter` or `--options`. The
PEA, FreeArc (`.arc`, `.wrc`) and split (`.001`) writers are separate: they
take regular files only and refuse folders and links (see their own documents),
and they handle an existing destination more simply: the new archive gets the default
permissions, a destination that is a symbolic link is replaced by the archive,
and a destination below a linked folder is refused. For the other writers
(not those separate ones), the destination is checked before anything else:
a folder, a name longer than its folder takes
and an existing archive this account may not write (a write-protected one, as
`cp`, GNU tar and zip refuse it; root may write it) are refused at once
(`<archive>: cannot create the archive: <reason>`). The
inputs are walked and checked before anything is written, and the archive is
written to a staging file in the destination's folder (`.xfu-<8 hex
digits>-<n>.tmp`), which replaces it only when the archive is complete: a
refused input, a failure or a Cancel leaves an existing destination as it was.
The staging file is written through the descriptor of its exclusive create
and is published only if it is still that file, so a link put in its place is
never written through. Where there was no archive, it is published without
replacing anything (a hard link, then the staging name is removed; on Windows
a move that replaces nothing): a file that appeared at the archive's name
meanwhile is left as it is and the run fails (`... another file was created
at its name meanwhile, and is left as it is`). On a file system without hard
links the staging file is renamed once nothing is at the name, which leaves a
short window. A staging file that is no longer the file written when it is
checked, just before publication, is not published, and the run fails (`...
its staging file was replaced`). What is at the archive's name afterwards is
left alone: another writer that saved its own file there meanwhile (a second
run, a program that saves with rename) keeps it, as with a plain rename. Every write to the archive is checked, so a full disk or a file size limit
fails the run (`... the archive could not be written: No space left on
device`) and never publishes a cut archive. When the destination's folder takes
no new file but the archive there may be written, the archive is built in a
temporary file and then written over the existing one in place, which keeps
its permissions, owner and hard links; a failure during that last copy leaves
it incomplete, and the run says so. A destination that is a device or a FIFO
(or a link to one) is written as it is, as `cat >` would write it: a device
that can seek (such as `/dev/null`) directly, and a FIFO or another stream
that cannot seek with the complete archive at the end, since a writer may go
back to finish a header. When that destination is standard output itself
(`/dev/stdout`, or another name for the same file), the member lines and the
summary go to standard error, so the stream holds the archive alone.
A run that is killed or interrupted can leave its staging file behind; a
walked folder leaves out such files, and the staging files of an interrupted
extraction (the native reader's, and xxfclib's `.xxfclib.tmp.<n>` of ZIP,
RAR, ISO 9660 and uImage or `.xxfclib.tmp.<32 hex digits>` of 7z), so they
never become members (a staging file named as an input is stored).
The new archive takes the permissions of the archive it replaces (on POSIX
systems, with its owner and group where the account may set them). A
destination that is a symbolic link is followed: the file it names is
replaced, and the link stays a link. As when the kernel follows a link, a
link in a sticky folder that everyone may write (such as `/tmp`) is followed
only when it belongs to the user or to the folder's owner; another user's
link there is refused. On Windows such a destination is
refused; name the archive itself. Other hard links to a replaced archive keep
the previous archive (the stage is renamed over one name only). Missing folders
of the destination are created; folders that exist are used as they are,
through links too. The TAR, ZIP, 7-Zip, CPIO, WIM, ISO9660, XAR
and mtree writers store a folder given to them with everything it holds, each
folder followed by its members in name order, empty folders included. The ar,
shar and WARC formats have no folder members and refuse a folder; name its
files instead. A `.gz`, `.bz2` or `.xz` stream holds one regular file and
refuses a folder. A symbolic link named as an input is followed: the file or
folder it names is stored under the link's name. A link found in a walked
folder, and devices and other special files, are refused. Each file and folder
is opened as the walk found it (on POSIX systems by device and inode, and
without following a link found in a folder), so one that was replaced since,
by a link or by another file, is refused (`source changed or cannot be read`)
rather than read in its place. On Windows, links
are symbolic links and junctions; other reparse points (deduplicated or cloud
files, for example) are ordinary files and folders. An input named twice, or also found in a named
folder, is stored once; two different inputs with one member name are refused.
ar stores a member's file name only: `a/x` and `b/x` are both stored as `x`, as
GNU ar does for static libraries (`ar x` then keeps the last one; `xfu x`
keeps both). Each stored member is listed, then
`<archive>: N file(s) as <format>`, or `N file(s) and M folder(s)` when folders
were stored. A refusal is reported in one line, with its reason: a missing or
unreadable input (`<input>: cannot read the input: No such file or
directory`, or `Permission denied`), a folder for a one-file stream (`<input>: an xz stream holds one
file, not a folder; use .tar.xz`), a name or a field a header cannot hold. The
writers store each member's permissions and modification time: the TAR, CPIO,
ar and mtree writers as POSIX modes and times with the owner and group, ZIP
as made on Unix (on POSIX
systems) with the mode and the DOS date, 7-Zip as Windows attributes (with the
Unix mode on POSIX systems) and a FILETIME, and XAR with the mode, owner,
group and time (and the creation time and SHA-1 checksum of its table of
contents, which xar(1) requires); ISO9660 stores the time only, and WIM
neither. PAX headers (`--format=pax`, and `--format=tar` where it needs one)
store any time, before 1970 too. A format that cannot hold a member's time
stores the nearest one it can and says so in one line, for example `old.txt:
its modification time (1960-06-01) is earlier than tar can store; stored as
1970-01-01`: ustar headers (the `.tar` suffixes, `ustar`, `gnutar`, `v7tar`)
hold 1970 to 2242, CPIO 1970 to 2106 (`cpio_odc` to 2242), ZIP 1980 to 2107,
ISO9660 1900 to 2155 and XAR the years 1 to 9999; 7-Zip stores no time
before 1601. An owner or group id of more than seven octal digits is kept in
a PAX header (`--format=pax`, and `--format=tar`), refused by `ustar`,
`gnutar` and `v7tar`, and stored as 65534 (nobody) by the xxfclib TAR writers,
which say so in one line; none of them stores it as 0. The warnings are
printed once the archive is written. Names that
xxfclib's TAR and CPIO writers cannot store (with `:`, `<`, `>`, `"`, `|`, `?`,
`*` or a control character, a component ending in `.` or a space, or a
Windows device name such as `CON`, `NUL` or `COM1`, with or without an
extension) and that its 7-Zip and WIM writers cannot store (with `:`, an
empty or `..` component, or a trailing `\`) are refused before the archive is
written (missing folders of the destination may already exist by then), as
are files of 8 GiB or more for the
`.tar` suffixes and 4 GiB or more for `.cpio` and `--format=newc`. These
writers, and the ZIP writer, also take `\` for a folder separator: on Windows
it is one, and elsewhere, where it is part of a file name (`back\slash.txt`),
such a name is refused (`back\slash.txt: the name contains '\', which tar
cannot store; --format=pax stores it`). The native writers keep it, except
those of XAR, WARC and mtree, whose names xfu then could not read back, and of
ISO9660, whose Joliet names cannot hold it: they refuse such a name too
(`back\slash.txt: the name contains '\', which an xar archive cannot store`). ZIP,
7-Zip, WIM, XAR, WARC and mtree, and the xxfclib TAR writers behind the `.tar`
suffixes, store UTF-8 member names only and refuse other names; the native TAR
formats (`--format=pax`, `ustar`, `gnutar`, ...), CPIO, ar and ISO9660 keep a
name's bytes, which PAX headers mark `hdrcharset=BINARY`. A raw stream stores no
name. The xxfclib TAR writers write ustar headers, which hold a name of at most
100 bytes, or of at most 256 split at a `/` into 155 and 100 (as does
`--format=ustar`); `--format=pax` stores longer names. The
ISO9660 writer limits a file to 4 GiB and a path component to 175 bytes. XAR stores member payloads without per-member compression, and member
paths of at most 252 components and 4095 bytes, as the xxfclib XAR reader reads
them. The native TAR formats store files of less than 8 GiB. mtree writes
bytes outside printable ASCII, spaces and `#`, `=` and `\` as `\ooo`, as
mtree(5) requires. A shell archive (`shar`) recreates each file byte for byte
when `sh` runs it (every name in it is single-quoted, so spaces, `(`, `[`, `#`
and other shell characters in a name are taken as they are): missing folders
with `mkdir -p`, text (UTF-8 without NUL
bytes that ends in a newline, or an empty file) through `sed`, and any other
file through `uudecode -o`, which must then be installed; `shar_dump`
uuencodes every file. Its names are printable ASCII of at most 255 bytes
without quotes, `\` or any of ``<>|$`;&*?``: xfu reads a shell archive
without running it, and leaves out a file whose name has those characters
(it takes them for a misparse), so such a name is refused with its reason.
The zstd, LZ4 and lzop writers (`.zst`, `.lz4`, `.lzo`, `.tar.zst`,
`.tar.lz4`, `--filter`, and `--compression=zstd` in ZIP and 7-Zip) store
their data in uncompressed blocks: the streams are valid for every reader but
do not compress. compress (`.Z`, `.tar.Z`) writes what compress(1)
writes, byte for byte as ncompress does: LZW codes of 9 to 16 bits in block
mode, with a CLEAR when the compression ratio drops once the table is full,
which gzip, compress, libarchive (bsdtar) and 7-Zip read. As with compress,
data that does not compress (random bytes) comes out about 20% larger.
`--compression-level` changes none of these. Reading back what `xfu a` wrote gives the same files, except that
a WIM also lists its XML table as `wim.xml`, a TAR in lzop also lists the TAR
itself as `__raw_lzop__/payload.tar`, and a raw stream without a filter is
the input's bytes, read with `--reader native:raw`. Nested decoded layers are limited
to eight, with a 4 GiB decoded size limit per layer.

The compatibility and fixed feature-contract checks are in
`tests/test_archive_compat.py` and `tests/test_archive_feature_contract.py`.
They exercise format variants, stream filters, corruption, path safety, and
preservation of existing output files.
