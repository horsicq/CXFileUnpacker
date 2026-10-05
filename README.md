# XFileUnpacker

A C11 archive unpacker with three applications built from one CMake project:

| Application | Interface |
| --- | --- |
| `xfu` | Command line |
| `XFileUnpacker` | Native xxwidgets desktop interface |
| `xfut` | xxwidgets terminal interface |

Format handling comes from `cmake/xxformats.cmake` in this project,
which builds the formats and algorithms with their runtime support, without
`die_engine`, the JavaScript interpreter or `cdisasm`. The reader table is compiled
directly from its `samples/unpack/xxfc_readers.c`, so format updates do not
require copying the table into this project. The GUI and TUI use
`dep/xxwidgets`, including the reusable `XXWIDGETS_ARCHIVEBROWSER`
desktop widget and compact `XXWIDGETS_ARCHIVEVIEW` terminal view. The applications are written in C; they do not
use Qt or C++. On macOS, the native xxwidgets backend uses its existing
private AppKit bridge in Objective-C.

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
resource readers; and decoded multimedia and PDF outputs. The Windows x64
bundle includes separate bounded helpers for 7-Zip, FFmpeg, PDFium, GARbro,
ConvertLIT, UPX and archive codecs, with their runtime dependencies and notices.
TEST sends decoded bytes to memory and quiet console testing reports percentages;
`--verbose` reports each member's result.

Additional readers unpack ExcelsiorII1 installers, classic/current SuperDAT LH1
packages, FEAD packages using the verified Adobe Reader 7.0 layout, UHARC 0.6
archives and DGCA 1.10 archives. FEAD restores cabinet members beneath each
container's directory name and labels preserved carrier bytes explicitly;
other optimizer layouts are rejected.
UHARC uses a bounded Windows RAM I/O bridge with the redistributable original
UnUHARC 0.6b, subject to its version, licensing and resource limits.
DGCA uses an independent native reader for stored, solid, non-solid and password
archives, including validated IARC versions 001/990/a90 and Unicode names and
passwords. Listing and TEST use borrowed
source IO and RAM only; no external DGCA executable is required. The decoder
cache/workspace limit defaults to 256 MiB; record-state metadata and extraction
buffers are separate. Inventory is capped at 65,535 members; caller decoder
memory/member limits and cancellation apply. Recovery archives, split volumes,
key files and other unverified variants
remain unsupported.

The installed `share/doc/xfileunpacker/UNIVERSAL_EXTRACTOR_FORMATS.md` and
`uniextract2-coverage.json` account for all 124 named families in the UE2 list.
Each row states available payload actions and missing variants. Recognized types
and registered handlers do not imply complete extraction or writing support.
`--reader garbro` or `--reader garbro:TAG` selects the game engine explicitly;
automatic fallback uses catalog signatures and extensions. Magicless game files
renamed to an unrelated suffix may need explicit reader selection.

The GUI and TUI have a **File type** combobox populated from the detected
format chain. A `sample.tar.gz` file offers `Binary`, `gzip`, and `tar.gz`,
with `tar.gz` selected automatically. Selecting `gzip` shows the contained
TAR payload as one member; selecting `tar.gz` shows its files and folders.
Listing, extraction, and testing use the selected interpretation. `Binary`
clears the archive listing and disables extraction and testing. Opening a
different file detects its types and selects the most specific one again.
Detection starts with xxfclib's separate extension-first fast detector,
`xx_format_get_file_type_device_fast()`. Its static suffix lookup performs no
file reads or reader construction and handles case and compound suffixes such
as `.tar.gz`. XFileUnpacker validates and parses the suggested reader before
accepting it. Unknown or ambiguous suffixes, and rejected extension hints, use
the content detector, `xx_format_get_file_type_device()`. Thus a valid `.gz`
stream opens as gzip first, while a
renamed file can still be recognized by content. If content remains Binary,
the existing validated extension fallback also tries signatureless formats.

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
creation continues to reject reparse points in every ancestor.
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

`tools/research_password_archives.py` inspects the classified password archives
and checks a bounded set of local hints. A matching encryption header is only a
candidate: complete member decoding and CRC validation are required before a
password is reported as recovered. `tools/verify_password_recoveries.py` verifies
every native extracted member against its archive size and CRC and records
SHA-256 hashes. `tools/research_ace_password.py` can independently check ACE
candidates using a separately supplied upstream `acefile.py`.

For a repeatable corpus audit, `tools/verify_arc_corpus.py` selects the smallest
direct file in every nonempty subfolder, recursively. It keeps extraction logs,
output SHA-256 hashes and CSV/JSON results in a new report directory. Empty
container folders are recorded separately. Samples are only read as data.

```powershell
python tools/verify_arc_corpus.py --root F:\ARC\ARC1_err `
  --unpacker build/Release/xfu.exe --report-dir build/arc-audit `
  --timeout 120 --jobs 4
```

Use `--replay <earlier-report.json>` to repeat the exact sample selection.
Add `--snapshot` to keep input copies in the report directory, and `--relocate`
to resolve moved replay inputs by unique filename and size. An interrupted run
can continue with `--resume` and the same report directory and unpacker binary;
completed results are kept and remaining samples use their saved snapshots.
Timeouts, failed extractions and successful empty archives have separate statuses.
The offline `xfileunpacker_probe_readers` build target can validate named readers
against a sample when investigating a detection or parser failure.

To inspect every file and copy only categories supported by evidence, build
`xfileunpacker_probe_metadata` and run the all-file tools:

```powershell
cmake --build build --config Release --target xfileunpacker_probe_metadata
python tools/inventory_all_arc.py --root F:\ARC\ARC1_err --report-dir build/arc-all-audit
python tools/scan_all_arc_files.py --report-dir build/arc-all-audit `
  --unpacker build/Release/xfu.exe --probe build/Release/xfileunpacker_probe_metadata.exe `
  --research <research-report.json> --jobs 8
python tools/verify_all_arc_scan.py --report-dir build/arc-all-audit
```

The inventory reads and hashes every original file. The scanner creates
`corrupted`, `new file format`, and `password` under the input folder, preserving
each original relative path and verifying every copy's SHA-256 independently.
These output folders are excluded from later inventories. Originals remain in
place. A reader failure alone does not establish damage: unresolved layouts,
possible missing split volumes, and resource limits remain uncategorized in
`report.csv` and `report.json`. The research report supplies earlier findings
only for identical SHA-256 contents. Use `--resume` after an interrupted scan.

Metadata probing can decode audited readers without creating extracted files.
Its JSON reports the integrity contract and limitations: ZIP and GST check
CRC32; IVT and Silmarils check framing and size; LHA checks decoded size and
payload CRC16. A passing test therefore means
the selected reader completed the checks it implements. Other readers use the
native archive test in isolated temporary folders, with time, memory, and output
limits. Inputs are never executed. The final verifier independently checks every
original and categorized copy against the inventory and reports missing or
unexpected output files.

`xfu --formats` (or `xfu i`) lists every file type in xxfclib's format catalog.
A compact grouped catalog is in [docs/CURRENT.md](docs/CURRENT.md).
The catalog includes new archive, disk, filesystem and partition readers.
Extraction capabilities depend on required profiles and available helpers.
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
The worker publishes snapshots under a mutex; the UI never reads its mutable
monitor directly. Cancel/Escape/close requests stop inside the decoder, and the
dialog waits for worker completion before restoring the main window. Completed
files are kept on cancellation.

## Source dependencies

After cloning the repository, initialize its submodules from the project root:

```sh
git submodule update --init --recursive
```

This populates `dep/xxfclib`, `dep/xxwidgets`, and `dep/cdisasm`. The current
build uses `xxwidgets` but does not use `cdisasm`. The format and settings
source lists live in this project's `cmake/` directory, while CMake uses the
initialized `dep/xxfclib` and `dep/xxwidgets` by default. Set
`XFILEUNPACKER_XXFCLIB_DIR` or `XFILEUNPACKER_XXWIDGETS_DIR` to another
compatible source directory if needed.

## Build on Windows

You need CMake 3.21+ and Visual Studio 2022 with the C/C++ development tools.
The recommended build uses MSVC with Ninja. Open the **x64 Native Tools Command
Prompt for VS 2022**, change to the project directory, and run:

```bat
cmake --preset windows-ninja
cmake --build --preset windows-ninja --parallel 10
ctest --preset windows-ninja
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
ctest --preset windows
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
ctest --test-dir build -C Release --output-on-failure
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
ctest --test-dir build --output-on-failure
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
There is no `e` command because the library's extraction API preserves stored
paths.

The `a` command creates an archive and replaces an existing archive of a
supported format. Writable formats are `.7z`, `.zip`, `.tar`, `.gz`, `.bz2`,
`.xz`, `.wim`, `.tar.gz` / `.tgz`, `.tar.bz2` / `.tbz2`, `.tar.xz` / `.txz`,
`.tar.zst`, `.tar.lz4`, and `.cpio`. Raw GZIP, BZIP2 and XZ streams require one
input file. The password control and `-p` also protect newly created 7z/ZIP archives.
WIM creation defaults to XPRESS compression. Select `--compression=stored`,
`--compression=xpress`, `--compression=lzx` or `--compression=lzms`; optional
`--compression-level=0..100` uses the compressor default at zero. GUI/TUI users
select the method and level in **WIM create** controls before adding files.
XPRESS/LZX produce WIM 1.13 and LZMS produces non-solid WIM 0.14. The separate
wimlib compression runtime
uses RAM chunks without temporary files. Stored creation and native reading
work without that runtime; unavailable compression fails before an existing
destination is truncated. These compression switches are console options;
GUI/TUI startup uses their controls.
The bundled Windows x64 7-Zip engine
provides all 60 readers in 7-Zip 26.03. Use `--reader sevenzip` for automatic
engine selection, including embedded SFX archives, or select a named handler such
as `--reader sevenzip_apfs`. `--reader sevenzip_pe`, `sevenzip_elf` and
`sevenzip_macho` expose executable sections. Native readers stay available.
Automatic fallback stays with the detected or requested container and requires
the archive at its start. Failed installer validation remains a failure; fallback
does not scan for an inner archive or expose the executable carrier's sections.
The seven upstream writable formats are all enabled;
upstream read-only disk/filesystem and archive handlers remain read-only.

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
stored archive records, so their extra metadata remains blank.

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
checks decoding without keeping output. **File > Create archive** chooses source files and a
destination for a new archive; the save dialog confirms replacement of an
existing file. **Copy path** copies the selected member name, **Info** shows
metadata, and **View > Operation log** toggles the operation log. A double-click
on a file shows its information. **Tools > Cancel operation** requests
cancellation of the active operation.

The TUI and other desktop backends retain path fields: enter `Archive` and
select `Open (l)`, then enter `Output` for `Extract (x)`. To create an archive,
enter its future path, add files through `Add file` and `Queue`, and select
`Add (a)`. `Remove` takes a selected file out of the queue. As with the original
sample's `a` command, archive creation replaces an existing file.

In the TUI, use Tab / Shift+Tab to move between controls, Enter to activate
buttons, and the arrow keys or PageUp / PageDown to navigate archive entries.
Left / Right scroll long ArchiveView rows. Escape exits. The recommended
minimum terminal size is 80×25. `Cancel` requests a safe stop, including while
decoding a member. Escape cancels an active progress dialog. Files already
extracted remain.
Operation messages appear in the log. Invalid UTF-8 bytes in archive names
are displayed as visible `[NN]` escapes in member names and `\xNN` escapes in
log messages, without changing the names used by
readers during extraction.

You can launch the GUI or TUI with an archive path to browse, or pass the same
`x`, `l`, `t`, or `a` command and arguments accepted by the console version.

## Keyboard shortcuts

On Windows, the GUI loads `shortcuts.ini` beside `XFileUnpacker.exe` at startup.
Edit its `[shortcuts]` entries and restart the application to apply them. Missing
entries use defaults; an empty value disables that action's shortcut. Builds
copy the default file only when none exists, preserving local overrides. An
invalid file or conflicting bindings falls back to the defaults.

Default shortcuts include Ctrl+O (open), Ctrl+N (create archive), Ctrl+E
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

`src/core.c` implements the shared operations and callbacks for messages,
members, progress, and cancellation. `src/cli.c` implements the command-line
interface. `src/ui.c` is shared by the GUI and TUI, whose entry points are in
`src/gui.c` and `src/tui.c`. Operations run on a worker thread; all xxwidgets
calls stay on the UI thread.

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
