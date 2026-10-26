# Native container formats (0.1.7)

All three frontends share these native readers through xxfclib. Each format
owns its source and public-header folders (`src/formats/<format>/` and
`include/xxfclib/formats/<format>/`) and is registered through the ordinary
`samples/unpack/xxfc_readers.c` reader table. They enumerate and decode actual contents. TEST decompresses in RAM and uses the usual percent
progress; verbose mode retains member results. Input installers and extracted
programs are never executed by these readers.

| Family | Formats |
| --- | --- |
| Compressed/resource streams | ZXML, ZISOFS, NVP, SQZE, PSC ZIP, Chromium CRX2/3 |
| Compression and skins | DCS, MSKN1/2/3, CSQ, Zoot1, RDFZ, ZBEOS, Solaris compressed packages |
| Games and resource packages | GTA IMG v2, PBO, PIRS/LIVE/CON STFS, PAM PAK, PFPK, PX, SBPAK, Titan Quest ARC, CGJP, Birdies, XUIZ |
| Vendor containers | Shell-prefixed Starkit, EVD, DeskSoft, MetaProducts, VisualWare, Lyme SFX, Audials CMP, PSA diagnostic disk, WebExe |
| Legacy compression | ASD, CFD, RDC, Fox SQZ, SKF, OSL2000, LDS |
| Disk wrappers | DCP, Sony TCJN zlib images |

This registers 44 reader entries, including a native replacement for the
previously registered CRX type. All are read/extract support; this expansion
does not add writers for proprietary formats.

Existing readers also receive compatibility fixes for DiskDoubler folder-end
records, empty and multipart Smart Install Maker cabinets, Excelsior installer
layouts, SuperDAT manifest variants, compressed PSARC, Safari WebArchive's
three-byte plist offsets, empty Starkit archives, default no-overwrite extraction
for FAT and Starkit, compressed AIN carriers, and
Japanese CAB names selected from an unambiguous PE resource locale.

DCS uses the Windows system Cabinet LZMS API and is currently Windows-specific.
The added readers require no vendor extraction executable. Compression checks
verify available CRCs, Adler32 or hashes. Some original formats have no payload
checksum; successful decoding of those formats cannot prove authenticity.

RDC has no content signature. Automatic detection uses its `.??_` filename and
a structural check; callers with an unnamed memory device can select RDC explicitly.

WebExe exports every declared ZIP payload under unique numbered leaves. The
original document names in its opaque vendor index are not recovered. PX
exports all named resource values and intact resource envelopes. DCP emits the
complete logical disk image, which can then be opened with a filesystem reader.

Two extended Atools Lyme SFX variants, the older DATAFILE.SQZ variant, the tested
OSL2000 file with a checksum mismatch, and the unsupported LDS variant remain
rejected. A file containing RSS mislabeled CFD is not interpreted as CFD.
Other unsupported families are listed in the accompanying ARC9 scan report;
an unsupported result alone is not a corruption diagnosis.

The tested Sony `.I02` continuation volume requires its missing initial volume;
it is not a standalone decoded image. Two empty Sony samples lack a zlib payload.

Encrypted Fox SQZ records expose their recovered binary key as
`embedded-key:HEX` credential metadata. This is a recovered key, not a claim to
know the original user-entered password. Automatic decoding needs no password
switch; the existing info, password retrieval and GUI/TUI controls can display it.

The implementation notes and parser validation evidence are documented in
xxfclib's `docs/NATIVE_CONTAINER_FORMATS.md` and `docs/STREAM_READERS_PROVENANCE.md`.
