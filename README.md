# XFileUnpacker

A C11 archive unpacker with three applications built from one CMake project:

| Application | Interface |
| --- | --- |
| `xfu` | Command line |
| `XFileUnpacker` | Native xxwidgets desktop interface |
| `xfut` | xxwidgets terminal interface |

Format handling comes from `../_mylibs/xxfclib/xxformats.cmake`, which builds
the formats and algorithms with their runtime support, without `die_engine`,
the JavaScript interpreter or `cdisasm`. The reader table is compiled
directly from its `samples/unpack/xxfc_readers.c`, so format updates do not
require copying the table into this project. The GUI and TUI use
`../_mylibs/xxwidgets`, including the reusable `XXWIDGETS_ARCHIVEBROWSER`
desktop widget and compact `XXWIDGETS_ARCHIVEVIEW` terminal view. The applications are written in C; they do not
use Qt or C++. On macOS, the native xxwidgets backend uses its existing
private AppKit bridge in Objective-C.

The GUI and TUI have a **File type** combobox populated from the detected
format chain. A `sample.tar.gz` file offers `Binary`, `gzip`, and `tar.gz`,
with `tar.gz` selected automatically. Selecting `gzip` shows the contained
TAR payload as one member; selecting `tar.gz` shows its files and folders.
Listing, extraction, and testing use the selected interpretation. `Binary`
clears the archive listing and disables extraction and testing. Opening a
different file detects its types and selects the most specific one again.

`xfu --formats` (or `xfu i`) lists every file type in xxfclib's format catalog.
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

## Command line

The commands, `-o<dir>` option, listing format, and diagnostic messages come
from `xxfclib/samples/unpack/main.c`. The application name in the help text
has been changed.

```text
xfu x <archive> [-o<dir>]     Extract with full paths
xfu l <archive>               List contents
xfu t <archive>               Test by extracting into a temporary directory
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
With no arguments, `--help`, or `-h`, the application prints help.

The `t` command actually decodes data into a unique temporary directory and
removes that directory afterward. The original sample left a fixed
`xxfc_unpack_test_tmp` directory behind. There is no `e` command because the
library's extraction API preserves stored paths.

The `a` command creates an archive and replaces an existing archive of a
supported format. Writable formats are `.tar`, `.tar.gz` / `.tgz`, `.tar.bz2`
/ `.tbz2`, `.tar.xz` / `.txz`, `.tar.zst`, `.tar.lz4`, `.zip`, and `.cpio`.
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

The **Advanced** checkbox adds columns for every property supplied by the
reader, plus record header/data offsets and sizes. It also shows a scrollable
details list for the selected member. ZIP entries include decoded method/level
and host OS alongside CRC32, flags, versions, encryption, comments and complete
extra-field bytes. **Info** opens a resizable dialog with selectable text.
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
public API is in `../_mylibs/xxwidgets/include/xxwidgets/xxwidgets.h`.

CTest checks creation, listing, extraction, and testing for ZIP, TAR, CPIO,
and TAR.GZ archives; compares file contents; and covers paths with spaces and
Unicode, argument errors, and preservation of files when the requested output
format is unsupported. Windows smoke tests create the GUI and TUI, populate
ArchiveBrowser or ArchiveView, and close the applications. The `windows` preset also includes
xxwidgets tests with real WinAPI controls and the console backend.
