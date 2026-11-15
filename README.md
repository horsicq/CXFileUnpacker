# XFileUnpacker

XFileUnpacker lists, tests, extracts and creates archives. It handles common
archives, compressed streams, installers, disk images and game resource packages.
It is written in C11 and does not need Qt or any external helper programs.

It comes as three applications:

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
xfu p <archive>               Show embedded passwords found in an installer
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
- `--json` or `--xml`: machine-readable output.
- `--handle <name>`: choose how to unpack the file, for example
  `--handle GZ` or `--handle TAR_GZ` for a `.tar.gz`.
- `--formats`: list every supported file type.
- `--capabilities`: show which formats can be read and created.

Exit codes: `0` success, `1` partial failure or cancelled, `2` error.

Extraction never writes outside the output folder. Unsafe member paths are
refused.

## GUI and terminal UI

Open an archive with **Open**, by dropping it on the window, or by passing its path
on the command line. Browse the folders in the archive, then use **Extract**,
**Extract only selected** or **Test**. Enter a password in the **Password** field
when needed. **Advanced** shows all the metadata stored for each member.

On Windows, shortcuts can be changed in `shortcuts.ini` next to the executable.

## Build

You need CMake 3.21 or newer. The build expects the xxfclib and xxwidgets source
trees in `dep/`. To use other locations, set `XFILEUNPACKER_XXFCLIB_DIR` and
`XFILEUNPACKER_XXWIDGETS_DIR`. The build downloads nothing.

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

The GUI needs GTK 3.16+ on Linux, or Xcode on macOS. Add
`-DXFILEUNPACKER_BUILD_GUI=OFF` to build without it.

## More documentation

- [Detailed behaviour](docs/DETAILS.md): passwords, progress, limits, nested
  archives, extraction rules, GUI details.
- [Archive formats](docs/ARCHIVE_FORMATS.md): writable formats and their limits.
- [Native container formats](docs/NATIVE_CONTAINER_FORMATS.md)
- [Supported types catalog](docs/CURRENT.md)
- [HxC disk images](docs/HXC_FORMATS.md)
- [PeaZip comparison](docs/PEAZIP_FORMATS.md)
