# XFileUnpacker

A C11 archive unpacker with three applications built from one CMake project:

| Application | Interface |
| --- | --- |
| `xfu` | Command line |
| `XFileUnpacker` | Native xxwidgets desktop interface |
| `xfut` | xxwidgets terminal interface |

Format handling comes directly from the local xxfclib source tree selected by
`XFILEUNPACKER_XXFCLIB_DIR`. Its `xxfclib::xfileunpacker_core` component builds
the formats, algorithms, readers, writers and shared application engine needed
by all three frontends, without `die_engine`, the JavaScript interpreter or
`cdisasm`. Its reader bridge uses xxfclib's format-owned native factories, so
format updates do not require copying a reader table into this project. The GUI and TUI use
the local xxwidgets tree selected
by `XFILEUNPACKER_XXWIDGETS_DIR`, including the reusable `XXWIDGETS_ARCHIVEBROWSER`
desktop widget and compact `XXWIDGETS_ARCHIVEVIEW` terminal view. The applications are written in C; they do not
use Qt or C++. On macOS, the native xxwidgets backend uses its existing
private AppKit bridge in Objective-C.

Encrypted archives are marked explicitly in every frontend. GUI and TUI show
an encrypted archive status and member details; the desktop member table also
marks encrypted rows in Attributes. When a password is needed, one notice
explains the situation and moves focus to the Password field. Readable encrypted
listings also notify users who have not supplied a password. Dismissing a notice
does not retry the operation automatically. Cancellation and closing do not open
password notices.

The console marks encrypted listing entries and explains how to supply a password
with `-p<password>` or `--password-env=<name>` without reading stdin. JSON/XML
include an `encrypted` flag on entries and typed `encryption` events. Failed
decryption reports that the password may be incorrect or the encrypted data
damaged; ordinary parse errors do not imply encryption.

The native container readers cover 44 variants, including
compressed streams, game/resource packages, disk wrappers and installers.
The console, GUI and TUI use the same readers. See
[native container formats](docs/NATIVE_CONTAINER_FORMATS.md) for the format list and remaining limits.

HxC disk images have additional native container/track readers and explicit raw
geometry profiles. Use `xfu --raw-profiles` to list geometries and
`xfu x disk.img --reader hxc-raw:DOS_DD_720KB -orecovered` to select one.
`--reader` also selects validated named readers for listing and testing.
The [HxC format documentation](docs/HXC_FORMATS.md) records sector/track/flux
extraction scope, XML initialization semantics and compatibility limits.

The Universal Extractor 2 expansion adds native Chromium DataPack, Windows
thumbnail-cache, Enigma, BitRock, Smart Install Maker and MoleBox payload readers;
gettext/Qt catalogs, MIME messages,
Windows Help streams, SQLite SQL export and Microsoft Reader books; new game
resource readers; decoded multimedia outputs; and native PDF streams and attachments.
TEST sends decoded bytes to memory and quiet console testing reports percentages;
`--verbose` reports each member's result.

The native PDF reader follows cross-reference tables, cross-reference streams,
compressed object streams and incremental updates. It extracts ordinary streams
and embedded attachments, preferring Unicode attachment filenames. Ordered
Flate, LZW, ASCII85, ASCIIHex and RunLength filters and TIFF/PNG predictors are
decoded; JPEG and JPEG 2000 streams retain their encoded image bytes. PDF carving
uses the validated document extent. Encrypted documents and unsupported filters
refuse extraction. Page rendering and page-text interpretation are not provided.

The native `pyc` reader handles Python compiled modules with version-aware
headers and bounded marshal code-object parsing. The PYC extractor carves the
validated module extent and excludes trailing data. DIE uses the native readers'
inspection APIs for PE, ELF, Mach-O, DEX, JPEG, PNG, APK, ZIP, ISO and PYC, as
well as PDF. Their existing native extractors remain registered.

Additional readers unpack ExcelsiorII1 installers, classic/current SuperDAT LH1
packages, FEAD packages using the verified Adobe Reader 7.0 layout and DGCA
1.10 archives. FEAD restores cabinet members beneath each
container's directory name and labels preserved carrier bytes explicitly;
other optimizer layouts are rejected.
UHARC 0.6 remains detectable in the format catalog, but listing and extraction
are unavailable because this build disables the external UnUHARC process.
DGCA uses an independent native reader for stored, solid, non-solid and password
archives, including validated IARC versions 001/990/a90 and Unicode names and
passwords. Listing and TEST use borrowed
source IO and RAM only; no external DGCA executable is required. The decoder
cache/workspace limit defaults to 256 MiB; record-state metadata and extraction
buffers are separate. Inventory is capped at 65,535 members; caller decoder
memory/member limits and cancellation apply. Recovery archives, split volumes,
key files and other unverified variants
remain unsupported.

Recognized types and registered handlers do not imply complete extraction
or writing support.

ScummVM DXA video (`DEXA`) has a separate `SCUMMVM_DXA` handle from DxLib
resource archives. Extraction exports an embedded `audio.wav` and decoded
`frame-000001.bmp` images. Keyframes (method 2), XOR deltas (3), unchanged
frames and palette changes are supported; methods 12/13 and extended headers
are rejected. See the xxfclib `video/scummvm_dxa` reader documentation for bounds.

FreeArc reading supports password-protected AES-256/CTR footer, directory and
solid data blocks, including legacy and corrected `:f` encodings. Supply a
password with `-p<password>` or `--password-env=<name>`; encrypted metadata
requires the password even for listing. Other compression stages still need
native reader support. Controls are limited to 64 MiB and solid output to
256 MiB. Key files, other ciphers and custom AES rounds are unsupported.
The native archive backend provides selectable archive writers and independent
stream filters. `xfu --capabilities` reports the available read/create
operations; the same table is included in `--formats` and the GUI/TUI
supported-types dialog. See [archive formats](docs/ARCHIVE_FORMATS.md)
for selector names and format-specific limits.

The [PeaZip comparison](docs/PEAZIP_FORMATS.md) distinguishes available
in-process operations from helper-backed operations disabled in this build.
The xxfclib-only build creates plaintext PEA, FreeArc and numbered split
volumes; Windows builds can also create the XFU FreeArc self-extracting form.
Brotli, ZPAQ, BALZ and BCM remain readable where reported. QUAD, LPAQ, PAQ,
UPX and explicit external-engine reads report `read=no`. 7-Zip SFX reading
remains partial through the native 7z path. Detection alone is not full-format
support.

```sh
xfu a library.ar alpha.txt beta.txt
xfu a disk.iso alpha.txt beta.txt
xfu a records.warc.gz alpha.txt beta.txt
xfu a backup.bin alpha.txt --format=pax --filter=zstd
xfu a legacy.cpio alpha.txt --format=pwb
xfu a archive.zip alpha.txt --compression=bzip2
xfu t backup.bin --reader native --verbose
xfu a comics.cbz page01.png page02.png
xfu a archive.pea alpha.txt beta.txt
xfu a archive.arc alpha.txt beta.txt --compression=store
xfu a payload.001 alpha.txt --volume-size=10M
xfu a archive.exe alpha.txt beta.txt --format=freearc_sfx
```

The archive readers and writers run in process through the xxfclib engine
component. DEFLATE, CRC and LZMA support used by the PEA and FreeArc writers
also comes from xxfclib. CMake performs no package or network lookup for codec
or archive libraries.

GARbro selectors and automatic GARbro fallback are unavailable in the
xxfclib-only build. Native game and resource readers remain selectable.

The GUI and TUI have an **Unpack** combobox populated with unpack handles
(`XX_HANDLE_TYPE_*`), independently of physical `XX_FILE_TYPE_*` identification.
A `sample.tar.gz` offers `GZ` and `TAR_GZ`, with `TAR_GZ` selected automatically.
Selecting `GZ` shows its TAR payload as one member; selecting `TAR_GZ` shows
its files and folders. Listing, extraction, and testing use the selected handle.
A PE image containing a ZIP archive can offer `PE_ZIPSFX`. Files with no
supported unpack method show **No unpacker** and disable archive actions.
The number of offered handles is not limited by the file-type hierarchy length.

Nested archives retain actionable outer layers, so an envelope or outer stream
can be selected separately from an archive inside it. Opening a different file
redetects its handles and selects the preferred interpretation again. The CLI
accepts the same selection through `--handle GZ`, `--handle TAR_GZ`, or another
name/ID from the compiled handle catalog; `--handle auto` restores detection.
An explicit handle must match the file and never silently switches methods.

`xx_format_get_unpack_handle_types_device(device, deep)` checks magic rules and
native fixed anchors first, including all applicable executable SFX/installer
readers. If no unpack handles are found it validates extension hints. With
`deep=true`, it then tries structural readers if the earlier stages still
found none. Readers that require an explicit raw geometry/import profile are
not automatically guessed from arbitrary data.

Compatibility includes single-member LZIP version 0 streams, older PYZ tables
with little-endian offsets or dictionary entries, LOFI `gzip`/`gzip-6`/`gzip-9`
segments, Palm database names with unused bytes after the NUL, and BinHex
payloads placed directly after their banner. BVRP supports stored entries and
compressed entries with name trailers. Gzip payloads in packed executable
carriers retain full DEFLATE, CRC and size validation. A damaged DMS image can
expose later independently verified tracks while its complete-image extraction
continues to report failure.

Additional legacy readers handle AIX BFF file records and symlink extents,
IVT directory trees, indexed QIP generation 1 records, Infogrames resources with bounded gaps, FLS
attributes, GST signatures, Second Nature absent-resource sentinels, and
relative DOS paths in Corelltec and POVLAB members. Older Makeself wrappers,
signed GPInstall carriers, InstallUs PE payloads, and FlashJester 1.01 retain
their payload size and checksum checks. On Windows, long output paths use
absolute extended paths, including atomic staging and replacement; directory
creation continues to reject reparse points below the output folder.
VMS SaveSet readers accept volume and FID metadata records, documented
header-only reserved files, and NOBACKUP omissions. Missing ordinary file bodies
and partial bodies still report failure. HFE Amiga MFM tracks are decoded into
ADF images with sector header/data checksums; recovered prefixes use
`image.partial.adf` and return an incomplete status when tracks are unavailable.
INFTool self-extractors expose their validated CAB payloads, including their
historical size-dependent byte mask, and older ZIP local-record payloads ending
in RSFX. ZIP directory reconstruction preserves the encrypted member bytes and
forwards the supplied password. Installer code is never run.

The command line accepts `-p<password>` for extraction, listing and testing.
Use `--password-env=<name>` to read a password from an environment variable;
the value is not printed or added to the child command line. ZIP passwords are
forwarded through self-extracting wrappers, and decoded members retain their
size and CRC checks. Encryption support depends on the selected reader;
native ACE decryption is currently unavailable.

Active Delivery (SFX AD01) recovers its embedded passwords and validates all
members before exposing them as per-file `Password` metadata. Its two password
groups remain distinct; the metadata also preserves the original encryption
status and compression method. `xfu l installer.exe --advanced` displays them.
Listing, testing and extracting these installers work without `-p` or
`--password-env`: the reader uses the embedded password for each member.
Demolition-FX ZIP self-extractors also recover passwords from recognized
producer imports and code references. Each member is decoded with full size
and CRC checks before its recovered password is exposed as metadata. These
files can be opened and extracted without password options; an explicit
password remains an override for their ZIP reader.

Use `xfu --get-password installer.exe` (or `xfu p installer.exe`) to retrieve
verified embedded passwords without extracting files. The command reports
each distinct password and its member count. It returns `1` when no embedded
password is available; passwords supplied with `-p` are never reported as
recovered credentials. `xfu l installer.exe --get-password` produces the same
report. Control bytes and invalid UTF-8 bytes appear as `\xHH`, and literal
backslashes as `\\`, so the report preserves the recovered credential.

```powershell
xfu x archive.zip -ooutput --password-env=ARCHIVE_PASSWORD
xfu t archive.zip -pmy-password
```

`xfu --formats` (or `xfu i`) lists every file type in xxfclib's format catalog.
A compact grouped catalog is in [docs/CURRENT.md](docs/CURRENT.md).
The catalog includes new archive, disk, filesystem and partition readers.
Extraction depends on the selected native reader and its documented limits;
helper-backed handlers are unavailable in this build.
Terminal output uses colors automatically; `--color=always` or `--color=never`
overrides this, and `NO_COLOR` disables automatic colors. Redirected output is
plain text by default. The GUI's **Help → Supported file types...** menu opens
a scrollable, selectable dialog with **Copy all**. Other frontends expose a
**File types...** button. The catalog covers detection and inspection; extraction
and writing capabilities vary by format. The library API is
`xx_format_get_supported_file_types()` in `xx_format.h`; release its returned
list of `xx_file_type_t` with `xx_list_destroy()`.

Extraction, including selected members, runs on a worker thread. The GUI and
TUI use xxwidgets' modal process dialog only while work remains unfinished
after one second. Fast jobs finish without opening a progress window. Its five
bars display busy xxfclib records, including member counts and decoder progress.
A compressed stream that is being decoded shows how much of it has been read
(`Reading archive`), and a 7-Zip folder how much of it has been decoded
(`Decoding solid block`: it is decoded whole at its first file); while the
member count cannot move (one member, a compressed TAR decoded before its
walk, or a count that has not moved for half a second), the main window's
status line shows that percentage, for example
`Testing: 0/1 | Reading archive 45% | big.txt`, and `t` counts a solid
folder's share of the members as it is decoded.
Each pass over the stream (a probe for an archive inside it, a reader that
validates it, then one that decodes it) starts it again, so a later pass is
numbered: `Reading archive, pass 2 0%`, and so are the figures of the
decoders that pass runs (`Unpacking Deflate, pass 2`), in the dialog too. The
main bar counts members, so it never moves back.
The worker publishes snapshots under a mutex; the UI never reads its mutable
monitor directly. Cancel/Escape/close requests stop inside the decoder, and the
dialog waits for worker completion before restoring the main window. Completed
files are kept on cancellation.

## Source dependencies

The build expects compatible xxfclib and xxwidgets source trees to exist
locally. CMake uses `dep/xxfclib` and `dep/xxwidgets` by default; set
`XFILEUNPACKER_XXFCLIB_DIR` and `XFILEUNPACKER_XXWIDGETS_DIR` when the prepared
trees live elsewhere. Codec and archive implementation code is compiled from
that xxfclib tree through `cmake/xxfclib_xfileunpacker.cmake`; the
CXFileUnpacker tree supplies only frontends, shell integration, packaging and
tests. Configuration does not use `FetchContent`, download codec sources, or
search for system ZLIB, LibLZMA, Brotli, ZPAQ, UPX or related codec packages.

## Build on Windows

You need CMake 3.21+ and Visual Studio 2022 with the C/C++ development tools.
The recommended build uses MSVC with Ninja. Open the **x64 Native Tools Command
Prompt for VS 2022**, change to the project directory, and run:

```bat
cmake --preset windows-ninja
cmake --build --preset windows-ninja --parallel 10
```

The executables are in `build-ninja/`:

```bat
build-ninja\xfu.exe l archive.zip
build-ninja\xfu.exe x archive.zip -ooutput
build-ninja\XFileUnpacker.exe archive.zip
build-ninja\xfut.exe archive.zip
```

You can also use the Visual Studio generator from a regular PowerShell window:

```powershell
cmake --preset windows
cmake --build --preset windows --parallel
```

With this generator, the executables are in `build/Release/`:

```powershell
.\build\Release\xfu.exe l archive.zip
.\build\Release\xfu.exe x archive.zip -ooutput
.\build\Release\XFileUnpacker.exe archive.zip
.\build\Release\xfut.exe archive.zip
```

The GUI uses the Windows subsystem and starts without a console. Run the TUI
in an interactive terminal; its terminal backend does not support redirected
input or output.

You can configure the project without presets:

```powershell
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release --parallel
```

## Portable Windows package

The Windows packaging script follows the neighboring projects' convention:
it builds and stages under `%TEMP%`, then writes a versioned portable folder
and ZIP to `release/`. It packages all three applications and the README and
license. No Qt installation is required. From the project directory, run:

```bat
packaging\Windows\build_portable_windows.cmd x64 win64
```

The default generator is Visual Studio 2022. To use Ninja instead, open the
x64 Native Tools Command Prompt for VS 2022 first and set
`CMAKE_GENERATOR_NAME=Ninja` before running the same command. The version is
read from `release_version.txt`. A successful x64 build produces
`release/xfileunpacker_win64_portable_0.1.4/` and
`release/xfileunpacker_win64_portable_0.1.4.zip`; the executables are in the
package's `bin/` directory.

## Build on Linux and macOS

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```

The GUI requires GTK 3.16+ and pkg-config on Linux, or AppKit and Xcode tools
on macOS. To build the command-line application and TUI without a native
graphical toolkit:

```sh
cmake -S . -B build-tui -DCMAKE_BUILD_TYPE=Release \
  -DXFILEUNPACKER_BUILD_GUI=OFF -DXXWIDGETS_NATIVE_BACKEND=none
cmake --build build-tui --parallel
```

To build only the command-line application:

```sh
cmake -S . -B build-cli -DXFILEUNPACKER_BUILD_GUI=OFF -DXFILEUNPACKER_BUILD_TUI=OFF
cmake --build build-cli --parallel
```

Override the library paths with the CMake options `XFILEUNPACKER_XXFCLIB_DIR`
and `XFILEUNPACKER_XXWIDGETS_DIR`.

## GitHub Actions and Beta

The build workflow packages Windows x64 and Ubuntu 24.04 on pushes and pull
requests to `master`. It saves both ZIP files as workflow artifacts. Run the
workflow manually from `master` to upload the packages to the existing `Beta`
prerelease; that run also advances the `Beta` tag to the packaged commit.
The hosted builds initialize the pinned dependency submodules recursively.

## Command line

The commands, `-o<dir>` option, listing format, and diagnostic messages come
from `xxfclib/samples/unpack/main.c`. The application name in the help text
has been changed.

```text
xfu x <archive> [-o<dir>]     Extract with full paths
xfu l <archive> [--advanced]  List contents, optionally with all metadata
xfu t <archive> [--verbose]  Test in memory; percentage or member results
xfu p <archive>               Retrieve verified embedded passwords
xfu a <archive> <file>...     Add files to a new archive
```

Add `--json` (`-j`) or `--xml` (`-x`) after an archive or information
command to write one machine-readable document. The formats are mutually
exclusive and may be selected only once. Structured output covers archive
creation, listing, testing, extraction and password retrieval, plus
`--version`, `--formats`, `--capabilities` and `--raw-profiles`. Diagnostics,
member metadata and the final process status stay inside that document.

Command letters are case-insensitive. The default output directory is the
current directory. Quote paths with spaces, including the entire `-o`
argument:

```powershell
.\build\Release\xfu.exe x "my archive.zip" "-oC:\Unpacked files"
.\build\Release\xfu.exe a backup.tar notes.txt images/photo.jpg
```

Listings retain the sample format: `archive: FORMAT`, followed by each
member's packed size and name, and finally `N member(s)`. Errors go to stderr.
Pass `--advanced` (or 7-Zip-style `-slt`) after the archive path to print each
member's type, sizes, modified time, attributes, and every available reader
property beneath its normal listing row. Missing values are shown as `unknown`.
With no arguments, `--help`, or `-h`, the application prints help.

The `t` command verifies members in memory without creating extracted files.
By default it prints only aggregate percentage progress. Add `--verbose` or
`-v` after the archive path to show each member's `OK` or `FAILED` result
instead. Errors go to stderr, and a failed test returns a nonzero exit code.
An archive inside a compressed stream or an encoded envelope (a `.cpio.gz`, a
`.tar.lz4`, an ISO in `.xz`) is decoded into that memory first. When it is
larger than the 256 MiB Test may use, `t` says so (`the CPIO inside is larger
than the 256 MiB that Test keeps in memory; it was not tested`), tests only the
stream around it, and returns `1`. `l` and `x` decode up to 4 GiB of such a
layer; a larger one is noted the same way and read as the stream's one file.
A 7-Zip folder is checked as it is decoded, so its members pass `t` whatever
their size, unless a filter (BCJ, BCJ2, Delta and the like) or its encryption
(7zAES) needs its decoded intermediate stream in that memory; such a member
fails with `(too large to test in memory)`.
A compressed TAR (`.tar.gz`, `.tar.bz2`, `.tar.xz`, `.tar.lzma`, or a
`.tar.zst` or `.tar.lz4` that records its size) is decoded once, into memory
and beyond 256 MiB into a temporary file (in `TMPDIR` when it is set), so `l`
and `x` read one of any size the disk takes; where the disk fills or a file
size limit (`ulimit -f`) stops the file, one of at most 1 GiB is decoded again
into memory, and a larger one says so (`no space for a temporary copy of the
TAR inside; it was not opened`, exit code `2`). Past 1 GiB the TAR may be at
most 4096 times the size of its compressed stream: more is what a
decompression bomb holds (a few hundred KB of bzip2 can decode to 50 GiB of
zeros), and decoding stops there (`the TAR inside is larger than 1 GiB and
more than 4096 times the size of its compressed stream, as a decompression
bomb is; it was not opened`, exit code `2`). `t` keeps it in memory and says
when it is larger than 1 GiB (`the TAR inside is larger than the 1 GiB that
Test keeps in memory; it was not tested`, exit code `2`). A cut one, such as
a download that stopped,
is read as far as it goes, as GNU tar does: `<path>: incomplete archive;
showing recovered members`, the members before the cut are listed, tested
and extracted, the one the cut goes through fails (`-- FAILED (cut)`, a
sparse one too) and nothing is written for it (nor for a hard link to it), so
a file already at its path stays as it was, and the exit code is `1`; a
member before it that fails for a reason of its own (a FIFO, a device) gives
that reason, as in a whole archive. A cut `.tar.zst` or `.tar.lz4` is read so
whether or not it records its size (`tar --zstd` and `tar -I lz4` do not),
and so is a whole stream whose TAR is cut: one cut where a gzip member, an xz
or bzip2 stream, or a zstd or LZ4 frame ends, or a TAR cut before it was
compressed. A stream of one zstd or LZ4 frame that does not record its size
is not: its TAR is read inside it as a nested layer, which, cut, is read as
the stream's one file. What the stream holds after its last check before the
cut has no check to vouch for it, and is read without one, as GNU tar reads
it: in a `.tar.lzma` (which has no check at all) that is every
member; in a `.tar.gz` those after the last whole gzip member (each has a
CRC), in a `.tar.zst` or `.tar.lz4` those after the last frame (or LZ4 block)
whose checksum was verified, in a `.tar.xz` or `.tar.bz2` those after the
last whole Block. When `t` or `x` reads such a member, the archive's line
says so instead: `<path>: incomplete archive; members before the cut were
read without a checksum`. A stream that fails a check, or that its decoder
finds invalid, before the cut is damaged, not cut, and is not read.
There is no `e` command because the library's extraction API preserves stored
paths.
`x` writes below the output folder, which, like the folders above it, may be a
symbolic link (as `/tmp` is on macOS) or, on Windows, a junction. A link that
extraction meets below it is refused. A file already at a member's path is
replaced by the member, whatever the archive's format (on Linux and macOS a
read-only one too, as `tar` replaces it), and the member's line says so
(`name -- replaced an existing file`); a link or a file with other hard
links there is replaced too, never written through, but not the archive
being read (`name -- FAILED (it would replace the archive)`), whether the
name separates its folders with `/` or `\`. The GUI and TUI
extract the same way, and their log shows the same lines. A member path or
name longer than the system takes fails, leaving
no folders made for it. A member that fails says why when that is known, for
example `name -- FAILED (a folder is in the way)`, `(permission
denied)`, `(path too long)`, `(a link is in the way)`, `(unsafe member path)`,
`(no room for a temporary copy)` (a 7-Zip folder is decoded into one first)
or `(encrypted; a password is needed)`. A member path is unsafe when it is
absolute or has a `..` component or a control character. A TAR or CPIO
member that holds data is a file even when its name ends in `\`: it fails
(`name -- FAILED (the name ends in a separator)`) and no folder is made for
it (a trailing `/` makes a folder, as old `tar` writers stored one). `:` is
an ordinary character of a name on Linux and macOS (`9:00-notes.txt`, `a:b`),
where such
a member is extracted as it is named; on Windows, where `:` names a drive or
a file's stream, it makes the path unsafe (Base64 and uuencoded envelopes
name their member after the part of the stored name that follows its last
`/`, `\` or `:`).

The `a` command creates an archive and replaces an existing archive of a
supported format. Writable formats are `.7z`, `.zip`, `.tar`, `.gz`, `.bz2`,
`.xz`, `.wim`, `.tar.gz` / `.tgz`, `.tar.bz2` / `.tbz2`, `.tar.xz` / `.txz`,
`.tar.zst`, `.tar.lz4`, and `.cpio`. Raw GZIP, BZIP2 and XZ streams require one
input file. `-p` also protects newly created 7z/ZIP archives; an empty password
(`-p` alone, or an empty `--password-env`) means none, for every format.
A folder is added with everything it holds, an input named twice is stored
once, and the new archive replaces the destination only when it is complete,
so a refused input, a failure (a full disk too) or a Cancel leaves an existing
archive as it was (see `docs/ARCHIVE_FORMATS.md`). A symbolic link named as an
input is stored as the file or folder it names; a link inside an added folder,
or a file replaced after the folder was read, is refused. The new
archive keeps the permissions of the one it replaces, and a destination that is
a symbolic link is followed, so the link stays a link (Windows refuses it).
Other hard links to the replaced archive keep the previous one. A new archive
never replaces a file that appeared at its name meanwhile. Each member keeps
its permissions and modification time where the format holds them (TAR also
its owner and group); a time the format cannot hold (before 1970 in ustar, for
example) is stored as the nearest one it can, with a warning line, and
`--format=pax` stores any time. A destination
that is a folder, or a write-protected archive, is refused before anything is
written. In a folder that takes no new file, an existing writable archive is
written over in place: the complete archive is built aside first, but a
failure during that copy (a full disk, for example) leaves the archive there
damaged, and the run says so. A device or FIFO is written directly; when that
is standard output itself (`/dev/stdout`), the log goes to standard error.
WIM creation defaults to stored data. The xxfclib-only build rejects XPRESS,
LZX and LZMS because those methods require a separate compressor process.
External 7-Zip, media, GARbro, UPX, UHARC, filesystem and codec helper
processes are disabled; native xxfclib readers and writers stay available.

xxfclib determines which formats can be read and the limitations of each
reader.

Exit codes are `0` for success, `1` for partial failure or cancellation, and
`2` for argument, open, or format errors.

## GUI and TUI

The Windows GUI uses a file-manager layout with a menu, command toolbar,
archive address bar, and a folder-aware table. Select **Open** or drop an
archive onto the window. Double-click a folder or press Enter to enter it;
**Up** or Backspace returns to its parent. Click a column heading to sort.
The table shows names, sizes, packed sizes, modification dates, and stored
attributes when the archive format provides them. Unknown values remain blank.

Both the GUI and TUI have an editable **Password** field for listing, testing
and extraction. A successfully opened archive autofills it when its reader
recovers an embedded password. Selecting a member shows that member's password
group. Manual edits are passed literally to the reader and take precedence
over autofill. Autofill keeps the reader's per-member recovery active, so files
with different embedded password groups can be extracted together.
Automatically filled values are cleared when switching archives.
Passwords are kept for the current session and are not saved in preferences.

Select **Get password** beside the field to retrieve the selected member's
embedded password, or the first recovered password when no member is selected.
This action reads the current archive again and replaces a manual override only
when recovery succeeds. If no password is found, the field retains its current
value and the status explains the result. Retrieving a password restores
automatic handling of archives with different password groups.

An embedded password containing control bytes appears under **Password
(escaped)**: `\\` represents a backslash and `\xHH` a control byte. Operations
use the original recovered value. Editing the field switches to literal input.

The **Advanced** checkbox adds columns for every property supplied by the
reader, plus record header/data offsets and sizes. It also shows a scrollable
details list for the selected member. ZIP entries include decoded method/level
and host OS alongside CRC32, flags, versions, encryption, comments and complete
extra-field bytes. **Info** opens a resizable dialog with selectable text.
Recovered passwords appear in **Info** even when Advanced is disabled. With
no member selected, Info lists the available passwords and their member counts.
In password display text, `\\` represents a literal backslash and `\xHH`
represents a control byte; the stored metadata retains the original value.
Inferred folders have no stored record metadata.

**Tools > Options...** opens xxwidgets' modal application options dialog with
**Advanced archive metadata** and **Show operation log**. The dialog uses
xxfclib's `xx_settings` through `xxwidgets::settings`. OK saves typed boolean
settings; Cancel or Escape leaves them unchanged. The Advanced checkbox and
log toggle use the same store. Preferences are restored at startup from the
native per-user `horsicq` / `XFileUnpacker` settings (on Windows,
`HKCU\Software\horsicq\XFileUnpacker`). The keys are `UI/Advanced` and
`UI/OperationLog`. Other frontends expose an **Options...** button. Smoke tests
use an isolated memory store.

**Help > About XFileUnpacker...** opens xxwidgets' reusable About dialog.
The application supplies its icon, build version, description, copyright,
website, license, and credits through public methods. Other frontends expose
an **About...** button; the terminal dialog shows text. Close, Enter, or Escape
dismisses it.

Check **Advanced** to add a column for every property supplied by the archive
reader and to show the selected member's full record in a scrollable details
pane. This includes header and data offsets, CRC, compression method,
encryption, flags, versions, host OS, comments and complete extra-field bytes,
when present. Unknown metadata IDs are retained. Toggle it without changing
the current folder or selection. **Info** provides selectable, scrollable text.
The TUI shows the selected record's properties when Advanced is checked.

Folder views show immediate children. For example, a DOCX file opens at the
ZIP root; enter `word/` to see its contents, then `_rels/` or `theme/` for their
files. Folders inferred from member paths are navigation rows rather than
stored archive records, so their extra metadata remains blank. A member whose
path has a `..` component is left out of the folder view, with one log line
naming it; extraction refuses such members.

Use Ctrl-click to select individual rows, Shift-click for a range, and Ctrl+A
to select all rows in the current folder. Sorting and toggling Advanced retain
the selection. Right-clicking a selected row keeps the entire selection;
right-clicking an unselected row selects that row.

Right-click a member or press Shift+F10 to open its context menu. The menu
offers information, path copying, folder navigation, extraction, testing, and
refresh. **Extract only selected** chooses a destination and extracts only the
selected files and folders, with their full archive paths. Selected folders
include all descendants. A right-click in empty space opens the archive menu.
**Extract entire archive** and **Test archive** apply to all members. Archive
operations are disabled while another operation is running.

**Extract** chooses a destination and extracts the entire archive. **Test**
checks decoding without keeping output. **Copy path** copies the selected member
name, **Info** shows
metadata, and **View > Operation log** toggles the operation log. A double-click
on a file shows its information. **Tools > Cancel operation** requests
cancellation of the active operation.

The TUI and other desktop backends retain path fields: enter `Archive` (or pick
it with `Browse...` in the Linux GUI) and select `Open (l)`, then enter `Output`
for `Extract (x)`. The GUI and TUI open existing archives only; create archives
with the console `xfu a` command.

In the TUI, use Tab / Shift+Tab to move between controls, Enter to activate
buttons, and the arrow keys or PageUp / PageDown to navigate archive entries.
Left / Right scroll long ArchiveView rows. Escape exits. The recommended
minimum terminal size is 80×25. `Cancel` requests a safe stop, including while
decoding a member. Escape cancels an active progress dialog. Files already
extracted remain.
Operation messages appear in the log. Invalid UTF-8 bytes in archive names
are displayed as visible `[NN]` escapes in member names and `\xNN` escapes in
log messages, without changing the names used by
readers during extraction. Control characters and the invisible characters
that can show a name reversed, split it or hide a difference are escaped the
same way, one escape per byte: every Unicode format character (Cf, such as
U+00AD, U+061C, U+200B, U+200E, U+200F, U+202A-U+202E, U+2066-U+2069, U+FEFF
and the tags U+E0001 and U+E0020-U+E007F, those of an emoji flag that starts
with U+1F3F4 too), U+2028, U+2029, and the other code
points that draw nothing (U+034F, the Hangul fillers U+115F, U+1160, U+3164
and U+FFA0, U+17B4, U+17B5 and the unassigned default-ignorable ones).
A variation selector (U+FE00-U+FE0F, U+E0100-U+E01EF, the Mongolian U+180B-U+180D
and U+180F) is escaped too unless it follows a base it applies to: U+FE0E or
U+FE0F after an emoji or a symbol with an emoji form (U+00A9, U+00AE, arrows,
U+2600-U+27BF, U+1F000-U+1FAFF, ...) or between a keycap's 0-9, # or * and
U+20E3, U+FE00-U+FE02 or U+E0100-U+E01EF after a CJK ideograph, and the
Mongolian ones after a Mongolian letter. U+200C and U+200D stay as they are;
`xfu` prints the others as `\xNN`. In the terminal UI's own fields (a typed or
program-set path, the status line) the same characters, and control
characters, take a cell each as U+FFFD instead.

You can launch the GUI or TUI with an archive path to browse, or pass the same
`x`, `l`, or `t` command and arguments accepted by the console version.

## Keyboard shortcuts

On Windows, the GUI loads `shortcuts.ini` beside `XFileUnpacker.exe` at startup.
Edit its `[shortcuts]` entries and restart the application to apply them. Missing
entries use defaults; an empty value disables that action's shortcut. Builds
copy the default file only when none exists, preserving local overrides. An
invalid file or conflicting bindings falls back to the defaults.

Default shortcuts include Ctrl+O (open), Ctrl+E
(extract), Ctrl+Shift+E (extract selected), Ctrl+T (test), Ctrl+Shift+C (copy
path), Alt+Enter (information), Ctrl+L (log), Escape (cancel), Ctrl+Q (quit),
Ctrl+Home (root), F5 (refresh), F1 (about), and Ctrl+Comma (options).

## Project structure

Application icons are in `assets/icons/`. Windows embeds the multi-resolution
ICO in all three executables and uses it in the GUI and information window.
Linux installs the desktop launcher and PNG/SVG icons into the standard
application and hicolor directories. macOS builds `XFileUnpacker.app` with its
ICNS icon in `Contents/Resources` and a bundle manifest for Finder and the Dock.
The CLI and TUI remain standalone executables on macOS.

The checked-in assets require no image tools to build. To regenerate all sizes
from their shared vector geometry, run `python packaging/generate_icons.py`
with Pillow installed.

`xxfclib/src/xfileunpacker/core.c` implements the shared operations and
callbacks for messages, members, progress, and cancellation. `src/cli.c`
implements the command-line interface. `src/ui.c` is shared by the GUI and
TUI, whose entry points are in `src/gui.c` and `src/tui.c`. Operations run on a
worker thread; all xxwidgets calls stay on the UI thread.

ArchiveBrowser owns its metadata, infers folders from member paths, tracks
the current directory, sorts columns, and maps selections to original members.
Its native backends provide report tables; its terminal backend supports the
same navigation. ArchiveView remains available for compact flat lists. Neither
widget depends on xxfclib, so other applications can reuse them. Their
public API is in `dep/xxwidgets/include/xxwidgets/xxwidgets.h`.

CTest checks creation, listing, extraction, and testing for ZIP, TAR, CPIO,
and TAR.GZ archives; compares file contents; and covers paths with spaces and
Unicode, argument errors, and preservation of files when the requested output
format is unsupported. Windows smoke tests create the GUI and TUI, populate
ArchiveBrowser or ArchiveView, and close the applications. The `windows` preset also includes
xxwidgets tests with real WinAPI controls and the console backend.
