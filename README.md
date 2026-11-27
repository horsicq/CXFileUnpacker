# XFileUnpacker

XFileUnpacker lists, tests, extracts and creates archives. It handles common
archives, compressed streams, installers, disk images and game resource packages.
It is written in C11 and does not need Qt or any external helper programs.

The CXFileUnpacker source project builds three applications:

| Application | Interface |
| --- | --- |
| `xfu` | Command line |
| `XFileUnpacker` | Desktop GUI |
| `xfut` | Terminal UI |

All format support comes from the xxfclib library. The GUI and terminal UI are
built with xxwidgets.

## Command line

```text
xfu l <archive>               List contents (--advanced for all metadata)
xfu t <archive>               Test in memory (--verbose for each member)
xfu x <archive> [-o<dir>]     Extract with full paths
xfu a <archive> <file>...     Create an archive
xfu p <archive>               Retrieve verified embedded passwords
```

Examples:

```sh
xfu l archive.zip
xfu x archive.zip -ooutput
xfu t archive.7z -pmy-password
xfu x archive.zip -ooutput --password-env=ARCHIVE_PASSWORD
xfu a backup.tar.gz notes.txt photos/
xfu a archive.zip notes.txt --compression=bzip2
```

Useful options:

- `-p<password>` or `--password-env=<name>`: supply a password.
- `--force`: on `x`, keep the readable part of a member whose stream is
  damaged; the run still returns `1`.
- `--json` or `--xml`: machine-readable output; each extracted member gets
  a `result` event with `success` and `partial`.
- `--handle <name>`: choose how to unpack the file, for example
  `--handle GZ` or `--handle TAR_GZ` for a `.tar.gz`.
- `--reader <name>`: select a validated reader, such as `native:zip`.
  Run `xfu --raw-profiles` for raw disk image profiles.
- `--formats`: list file types the build can detect or inspect.
- `--capabilities`: report read and creation support for the installed build.
- `--format=<name>` and `--filter=<name>`: choose the output container and
  its compression or encoding. See the [archive matrix](docs/ARCHIVE_FORMATS.md)
  for supported combinations.

Exit codes: `0` success, `1` partial failure or cancelled, `2` error.

Extraction refuses unsafe member paths. Existing files at accepted paths can
be replaced, so use a dedicated output folder. See the
[extraction rules](docs/DETAILS.md#command-line) for details.

## GUI and terminal UI

Open an archive with **Open**, by dropping it on the window, or by passing its path
on the command line. Browse the folders in the archive, then use **Extract**,
**Extract only selected** or **Test**. Enter a password in the **Password** field
when needed. **Advanced** shows all the metadata stored for each member.

On Windows, shortcuts can be changed in `shortcuts.ini` next to the executable.

## Build

You need CMake 3.21 or newer and a C11 compiler. The default dependency paths
are `dep/xxfclib` and `dep/xxwidgets`. For a Git checkout, initialize its
submodules with `git submodule update --init --recursive`. For a prepared source
tree with dependencies elsewhere, set `XFILEUNPACKER_XXFCLIB_DIR` and
`XFILEUNPACKER_XXWIDGETS_DIR` when configuring. CMake uses local sources.

**Windows.** Use Visual Studio 2022 and run these commands in the
x64 Native Tools Command Prompt:

```bat
cmake --preset windows-ninja
cmake --build --preset windows-ninja --parallel
```

The executables are placed in `build-ninja/`. To make a portable ZIP in `release/`:

```bat
packaging\Windows\build_portable_windows.cmd x64 win64
```

**Linux and macOS:**

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```

The GUI needs GTK 3.16+ and `pkg-config` on Linux, or the Xcode tools and
AppKit on macOS. Use `cmake --preset tui` and `cmake --build --preset tui`
for a build with `xfu` and `xfut` that needs no GUI toolkit. For `xfu` alone,
configure with both `-DXFILEUNPACKER_BUILD_GUI=OFF` and
`-DXFILEUNPACKER_BUILD_TUI=OFF`. The CLI-only build requires only xxfclib.
See the [build reference](docs/DETAILS.md#source-dependencies) for variants
and a local dependency layout example.

## More documentation

- [Detailed behaviour](docs/DETAILS.md): passwords, progress, limits, nested
  archives, extraction rules, GUI details.
- [Archive formats](docs/ARCHIVE_FORMATS.md): writable formats and their limits.
- [Native container formats](docs/NATIVE_CONTAINER_FORMATS.md)
- [Format catalog and how to query your build](docs/CURRENT.md)
- [HxC disk images](docs/HXC_FORMATS.md)
- [PeaZip comparison](docs/PEAZIP_FORMATS.md)
- [FreeArc creation](docs/FREEARC_WRITER.md) and [numbered split volumes](docs/SPLIT_FORMAT.md)
