# Supported formats

Updated 2026-10-01. **1,470 file types** from XFileUnpacker's xxfclib catalog,
including variants and the Binary fallback. This build excludes `die_engine`.
The catalog covers detection and inspection; listing and extraction depend on the
supported variant. Media readers may export encoded components. Flat list:
`xfu --formats --color=never`.
ZIP also covers OOXML, OpenDocument, EPUB and CBZ containers.
Extensions are conventional or documented filename suffixes; **—** means no suffix is established here.

## Archives (170)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `7ZIP` | `.7z` | 7-Zip archive with supported codecs and optional AES encryption. |
| `ACE` | `.ace` | ACE 1.x and ACE 2.x archive. |
| `AIAFF` | `.a` | AIX small archive used for classic static-library members. |
| `AIN` | `.ain` | AIN archive with a compressed directory and file members. |
| `ALZ` | `.alz` | ALZip ALZ archive with stored or compressed members. |
| `AMIGALZX` | `.lzx` | Amiga LZX archive containing compressed file members. |
| `AMPK` | `.ampk` | Amiga-Magazin AMPK versions 1-4 archive container. |
| `android ab` | `.ab` | Android backup archives carrying encoded application data and backup metadata. |
| `AppleSingle` | `.as` | AppleSingle (0x00051600) and AppleDouble (0x00051607) wrappers. |
| `AR` | `.a`, `.lib`, `.deb` | Unix static-library archive with System V, GNU and BSD names. |
| `ARCFS` | `.arc` | Acorn RISC OS ArcFS archive with a directory tree. |
| `ARJ` | `.arj` | ARJ archive supporting stored members and compression methods 1-4. |
| `ARQ` | `.arq` | An ARQ archive, as written by Crusher!. |
| `ARX` | `.arx` | ARX archive with LHA-style headers and stored or lh1 members. |
| `ASAR` | `.asar` | An ASAR archive, as produced by Electron. |
| `ASCEND` | `.in!` | Ascend compressed-file wrapper carrying one original member. |
| `ASCENDBACKUP` | `.000` | Ascend backup volume containing named backup-file records. |
| `BAGF` | `.xdc`, `.rpc` | Novell NetWare "BAGF" bag file (.XDC, .RPC). |
| `bga` | `.gza`, `.bza` | BGA32 archive reader (.gza / .bza). |
| `BIGAF` | `.a` | AIX big archive used for indexed static-library members. |
| `BinaryII` | `.bny`, `.bxy`, `.sdk` | Apple II Binary II records with 128-byte padded file payloads. |
| `BORLANDPACK` | `.arc` | Borland PACK distribution archive containing packed files. |
| `BVRP` | `.pac` | BVRP Software .PAC container; members use LZHUF (lh1). |
| `C64WRAPTOR` | `.wra` | Commodore 64 Wraptor (*.wra, *.wr3). |
| `CAB` | `.cab` | Microsoft Cabinet with Store, MSZIP, LZX and Quantum folders. |
| `CFL` | `.dat` | CFL container with stored or compressed resource members. |
| `CHIEFLZ` | — | ChiefLZ single-file wrapper carrying compressed member data. |
| `CHIEFLZMULTI` | `.clz` | ChiefLZ multi-file archive with compressed member records. |
| `CLAYLZ` | `.cmz` | Clay CMZ archive containing compressed file members. |
| `CMP` | `.cmp` | CMP archive containing stored or compressed member records. |
| `commodore pc64` | `.p00`, `.s00`, `.u00`, `.r00` | Commodore PC64 single-file wrappers preserving PETSCII descriptors and original payloads. |
| `COMPACTPRO` | `.cpt` | Macintosh Compact Pro archive containing compressed file members. |
| `CP/M LU LBR library` | `.lbr` | CP/M LU library containing indexed files in fixed-size blocks. |
| `CPIO` | `.cpio` | CPIO archive reader and newc writer. |
| `CRU` | `.cru` | CRUSH archive with individually stored or compressed member records. |
| `DFC` | `.dfc` | DFC disk archive with stored and PKWARE DCL members. |
| `DN` | `.138` | DOS Navigator 1.x archive with explicit data and directory records. |
| `DTPACKED` | `.dt` | Delrina DT packed-file container exposing one payload. |
| `EDC` | `.edc` | EDC Packed archive containing compressed file records. |
| `egg` | `.egg` | Single-volume EGG archives supporting nonsolid stored blocks with CRC32 checks. |
| `EPF` | `.epf` | East Point EPFS archive with a trailing member allocation table. |
| `esp archive` | `.esp` | ESP archives supporting stored members and decoded compressed directory tables. |
| `ewf2_lx01` | `.Lx01` | EnCase logical-evidence container preserving named stored evidence files. |
| `ewf_l01` | `.L01` | EnCase logical-evidence segment containing named evidence records. |
| `FIZ` | `.fiz` | Maximus FIZ archive with indexed stored file members. |
| `FLS` | `.fls` | IBM SaveRam FLS container holding compressed member files. |
| `FMC1` | `.cmp` | Form Master FMC1 archive containing named member records. |
| `FREEARC` | `.arc` | FreeArc archive; identification and listing depend on supported framing. |
| `FTCOMP` | `.ftc` | FTCOMP ("A5 96 FD FF") packed-file. |
| `GENIUS` | `.gpl` | Genius Library resource archive with indexed file members. |
| `GLU` | `.glu` | GLU BBS distribution container containing named file members. |
| `HA` | `.ha` | HA archive containing stored or compressed file members. |
| `HAP` | `.hap` | HAP archive containing stored or compressed member records. |
| `HLB` | `.hlb` | HLB resource library containing indexed named file members. |
| `HUF` | `.huf` | HUF archive with shared Huffman-coded member data. |
| `HZL` | `.hzl` | HZL compressed-file wrapper carrying one original payload. |
| `IBMPACK` | `.pak` | IBM/OS-2 PACK ("A5 96") packed-file. |
| `IBMZPAK` | `.zpk` | IBM ZPAK archive containing stored or compressed files. |
| `icu data package` | `.dat` | ICU common-data bundles exposing indexed named members and encoded DataHeaders. |
| `IMP` | `.imp` | IMP archive containing stored or compressed file members. |
| `INSA` | `.dat` | INSA version-1 concatenation of length-prefixed LH1 streams. |
| `INTEDUFT` | `.dat` | INTEDUFT resource pack containing named member payloads. |
| `IXA` | `.ixa` | IXALANCE container with indexed compressed member payloads. |
| `JBF` | `.jbf` | JBF archive with a headerless payload and trailing directory. |
| `JETBBS` | `.dat` | JetBBS archive using LHA headers and mg compression tags. |
| `JGPAK` | `.pak` | JGsoft JGPAK resource archive used by HelpScribble. |
| `JM93` | `.cmp` | JM93 wrapper containing one compressed file payload. |
| `KA` | `.arc` | KA Archive: absolute-offset table of stored members. |
| `KBOOM` | `.kbm` | K-BOOM archive containing stored or compressed file members. |
| `kgb_archiver` | `.kgb` | KGB Archiver 2 (.kgb) archive. |
| `KOLIBRIKPACK` | `.kpack` | KolibriOS kpack compressed executable or data container. |
| `LBRCOBOL` | `.lbr` | Micro Focus COBOL Library File. |
| `LHA` | `.lha` | ARX archive: LHA-style member headers, stored and -lh1- members. |
| `LIM` | `.lim` | LIM archive containing indexed compressed member records. |
| `lmd container` | `.dat` | LMD version-three resource containers holding counted string and bitmap lists. |
| `LSPack10` | `.lsp` | LSPack 1.0 archive with ZIP-like headers and raw Deflate streams. |
| `LSZ` | `.lsz` | Delrina WinFax LSZ library with named member records. |
| `LZWD` | `.lzw` | HP NewWave LZWD wrapper with LZW-compressed data. |
| `MacBinary` | `.bin` | MacBinary I-III wrapper preserving data, resource and comment forks. |
| `Macintosh PackIt` | `.pit` | Macintosh PackIt archive preserving file data, resources and metadata. |
| `MARC` | `.marc` | A MARC archive: a fixed-size directory of stored members, each named in a 56-byte field. |
| `MCC` | `.reg` | MCC registration container with consecutive named member records. |
| `MDCD` | `.mdcd` | MDCD archive (Mass Data CD builder); stored or Zoo-LZD members. |
| `MI10` | `.mi10` | Amiga MI10 archive containing a compressed block chain. |
| `MLB_FT` | `.mlb` | A stored MLB_FT archive with a 21-byte record directory. |
| `MS-DOS BACKUP (v2.0-3.2)` | `.bak` | One file written by MS-DOS 2.0-3.2 BACKUP.EXE / BACKUP.COM. |
| `ms_dos_backup2` | `.001` | MS-DOS 3.3-5.x BACKUP set (CONTROL.nnn + BACKUP.nnn). |
| `MXS` | `.mxs` | MXS archive containing packed named file members. |
| `nix nar` | `.nar` | Nix NAR filesystem archives containing padded directory, file, and symlink records. |
| `nufx` | `.shk` | NuFX archives supporting counted stored data, resource and disk threads. |
| `PACKIT` | `.pit` | A PackIt archive: a sixteen-byte banner, then a chain of tagged member records ending in a terminator tag. |
| `PAIN` | `.dat` | CRDATA00 ("PAIN" diskmag) data container. |
| `PAKLEO` | `.pll` | PAKLEO archive containing stored or compressed member files. |
| `PANORAMA` | `.dat` | Panorama archive using enciphered RAR member framing. |
| `PAX` | `.pax` | GEM-View PAX ("LZF0") member chain. |
| `PCSECURE` | — | Central Point PCSECURE protected file. |
| `PDP11AR` | `.a` | UNIX V7 / 2BSD PDP-11's binary ar pre-dates the ASCII !<arch> format. |
| `PEA` | `.pea` | PEA archive containing indexed file members and checksums. |
| `PMA` | `.pma` | PMarc archive using LHA-style headers and pm0, pm1 or pm2 methods. |
| `POVLABLZH` | `.lzh` | POVLAB resource archive using LHA-style compressed members. |
| `POWERARC` | `.pk` | PowerArc archive with indexed named file members. |
| `POWERBOARDBBS` | `.bbs` | Powerboard BBS library containing named stored member records. |
| `QDA` | `.qda` | QDA archive containing stored or compressed file members. |
| `Quantum archive` | `.pak` | Standalone Quantum archive (.pak / .001) container. |
| `RAR` | `.rar` | RAR 4.x and RAR 5.x archive reader and extractor. |
| `RIVERSOFT` | `.rdl` | RiverSoft data library containing named resource records. |
| `RNCA` | `.rnc` | Rob Northen "RNCA" multi-member archive. |
| `RSVK` | `.dat` | RSVKDATA/DLIBDATA resource library containing named member records. |
| `RTA` | `.rta` | Pocket Soft RTPatch archive containing compressed patch records. |
| `SAF` | `.saf` | Stac Electronics SAF archive containing compressed member records. |
| `SCI` | `.sxd` | SCI archive containing consecutive stored member records. |
| `SEAARC` | `.arc` | SEA ARC archive containing stored or compressed file members. |
| `SEADATA` | `.dat` | Sea Data asset bundle with named resource records. |
| `SECONDNATURE` | `.snx` | Second Nature archive containing named stored member records. |
| `SHAR` | `.shar` | A shell archive: a /bin/sh script whose members are the bodies of its cat/sed here-documents. |
| `Sinner` | `.res` | CCT resource container containing stored named member files. |
| `SLS` | `.sl$` | WinSense SLS wrapper holding one compressed file. |
| `SPK` | `.spk` | !Spark / SparkFS archive (Acorn RISC OS), the ARC-style variant. |
| `SQX` | `.sqx` | SQX archive containing indexed compressed file members. |
| `SQZ` | `.sqz` | Squeeze It HLSQZ archive containing compressed file records. |
| `StuffIt` | `.sit` | Original StuffIt 1.x-4.x archive and later compatible container tags. |
| `StuffIt 5 archive` | `.sit` | StuffIt version-five archive containing Macintosh file and resource data. |
| `StuffIt split file` | `.1` | StuffIt segment containing slices of Macintosh resource and data forks. |
| `stuffitx` | `.sitx` | A StuffIt X archive (StuffIt 7 and later, ".sitx"). |
| `SWAG` | `.swg` | SWAG collection containing indexed programming-snippet records. |
| `SWAGPACKET` | `.swg` | SWAG packet containing indexed stored snippet components. |
| `TAR` | `.tar` | TAR archive with sequential headers and padded file contents. |
| `TAR NEXTSTEP` | `.tar` | NeXTSTEP TAR variant with platform-specific member records. |
| `TAR.BZ2` | `.tar.bz2`, `.tbz`, `.tbz2` | TAR file archive wrapped in a bzip2 stream. |
| `TAR.GZ` | `.tar.gz`, `.tgz` | TAR file archive wrapped in a gzip stream. |
| `TAR.LZ` | `.tar.lz` | TAR file archive wrapped in a lzip stream. |
| `TAR.LZ4` | `.tar.lz4`, `.tlz4` | TAR file archive wrapped in an LZ4 stream. |
| `TAR.LZMA` | `.tar.lzma` | TAR file archive wrapped in an LZMA stream. |
| `TAR.LZO` | `.tar.lzo` | TAR file archive wrapped in an lzop stream. |
| `TAR.XZ` | `.tar.xz`, `.txz` | TAR file archive wrapped in an XZ stream. |
| `TAR.Z` | `.tar.Z` | TAR file archive wrapped in a Unix compress stream. |
| `TAR.ZST` | `.tar.zst`, `.tzst` | TAR file archive wrapped in a Zstandard stream. |
| `TARX1` | `.tarx` | QNX TARX version 1 archive with file records. |
| `TARX2` | `.tarx` | QNX TARX version 2 archive with file records. |
| `TERSE` | `.trs` | IBM TERSE archive with stored or compressed member data. |
| `TGCF` | `.tgcf` | TGCF archive containing stored or compressed file members. |
| `TI99ARC` | `.ark` | TI-99/4A ARC archive containing compressed file records. |
| `TIVOLI` | `.pkt` | Tivoli Filepack Block archive containing named member files. |
| `TPS` | `.tps` | Clarion/TopSpeed TPS archive containing sequential member records. |
| `TRC` | `.trc` | TRC archive containing stored or compressed file members. |
| `TRCPAK` | `.pak` | TRCPAK archive containing stored or compressed file members. |
| `TWS` | `.tws` | TWS archive containing stored or compressed file members. |
| `UHARC` | `.uha` | UHARC archive reader (identification only). |
| `ULEAD` | `.dsk` | A ULEAD container: a "U_LEAD CORP." header carrying a block table, then the blocks. |
| `VMARC` | `.vmarc` | IBM VMARC archive containing named stored or compressed members. |
| `VMSSaveset` | `.bck` | An OpenVMS BACKUP save set: fixed-size blocks, each holding a packed sequence of records. |
| `WARC` | `.warc` | WARC 1.0/1.1 web records; extracts resource and response content. |
| `WINTERSOFT` | `.wsa` | Wintersoft archive containing stored or compressed member records. |
| `XEDITPACK` | `.pak` | XEDIT PACK container holding one compressed file payload. |
| `XLAS` | `.xla` | XLAS container (Xtreme/DOS-era asset pack); LZSS members. |
| `XORArchive` | `.zip` | XOR-masked ZIP and ARJ containers. |
| `ZAP` | `.zap` | ZAP archive containing stored or compressed member records. |
| `ZCMP` | `.z` | Zcmp wrapper holding one compressed file payload. |
| `ZFSF` | `.zfsf` | ZFSF archive with indexed named resource members. |
| `ZIE` | `.zie` | Encrypted ZIP variant using ZIE-specific protected member framing. |
| `ZIP` | `.zip`, `.docx`, `.docm`, `.dotx`, `.dotm`, `.xlsx`, `.xlsm`, `.xltx`, `.xltm`, `.xlsb`, `.pptx`, `.pptm`, `.potx`, `.potm`, `.ppsx`, `.ppsm`, `.odt`, `.ott`, `.ods`, `.ots`, `.odp`, `.otp`, `.odg`, `.otg`, `.epub`, `.cbz` | ZIP archive with compressed members and optional encryption. |
| `ZIP64` | `.zip` | ZIP archive using 64-bit member sizes and offsets. |
| `ZLWB` | `.zlw` | ZLWB archive containing stored or compressed file members. |
| `ZOO` | `.zoo` | MDCD archive (Mass Data CD builder); stored or Zoo-LZD members. |
| `ZPAK` | `.zpk` | ZSoft ZPAK archive containing packed member files. |
| `ZPAQ` | `.zpaq` | ZPAQ archive reader (journaling and streaming). |
| `zx hobeta` | `.$b`, `.$c`, `.$d` | Hobeta TR-DOS single-file wrappers preserving bounded sectors and checked headers. |
| `ZXZIP` | `.$z` | ZXZIP (ZX Spectrum "ZIP" archiver) member. |
| `ZZ` | `.zz` | ZZ single-file wrapper holding a compressed data stream. |
| `ZZZ` | `.zzz` | A ".ZZZ" archive: a chain of 24-byte "ZZZ" headers each followed by a PKWARE DCL Implode stream. |

## Compressed streams and encodings (88)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `age encrypted` | `.age` | Binary age v1 X25519 envelopes preserving unauthenticated encoded ciphertext chunks. |
| `ALDUS` | — | Aldus compressed file supporting LZW, LZSH and DCL methods. |
| `ASH0` | `.ash` | Nintendo ASH0 compressed stream using adaptive Huffman coding. |
| `base16` | `.hex` | Hexadecimal text encoding decoded into original binary byte sequences. |
| `Base64` | `.b64` | Base64 text encoding decoded into its original binary payload. |
| `BCM` | `.bcm` | BCM (BWT + context mixing) compressed stream. |
| `BinHex` | `.hqx` | BinHex text encoding with RLE compression and Macintosh file forks. |
| `binscii` | `.bsc` | BinSCII (Apple II text transport). |
| `BOO` | `.boo` | Printable BOO transport encoding for binary file contents. |
| `BROTLI` | `.br` | Decode the complete Brotli stream to a caller-provided device. |
| `btoa / Ascii85` | `.btoa` | btoa or Adobe Ascii85 text encoding carrying a binary payload. |
| `ByteKiller` | `.bk` | The eight supported wire layouts, all with exact native C decoding. |
| `BZ2` | `.bz2` | Bzip2 compressed stream containing one original file. |
| `BZIP1` | `.bz` | Original bzip 0.15/0.21 stream with whole-file CRC verification. |
| `CAZIP` | `.caz` | Computer Associates CAZIP / CAZIPXP. |
| `CompaqLZH` | — | Compaq driver or firmware wrapper containing one LHA-compressed file. |
| `DCLStream` | `.dcl` | Raw PKWARE DCL (implode) stream. |
| `DebugScript` | `.scr` | DOS DEBUG script with ASCII commands encoding binary payload bytes. |
| `diet_compression` | `.dlz` | A data file compressed by Teddy Matsumoto's DIET (not the COM/EXE variants, which are executable packers). |
| `DISKDOUBLER` | `.dd` | DiskDoubler compressed file and DDA2/DDAR archive. |
| `DMA PACKED` | `.pk$` | DMA Packed single-file container with compressed payload data. |
| `EDILZSS` | `.lzs` | EDI Install LZSS packed file. |
| `fastlz sixpack` | `.6pk` | FastLZ 6PACK file entries with decoded Adler32-checked data chunks. |
| `Freeze` | `.frz` | Freeze/Melt 1.x and 2.x adaptive-Huffman compressed streams. |
| `GAS HUFF` | `.huf` | GAS single-file compression using static Huffman coding. |
| `GPFPACK` | `.gpf` | Number of packed blocks in the payload chain. |
| `GZ` | `.gz` | Gzip stream with compressed data and CRC-protected framing. |
| `hp3000 wrq` | `.wrq` | WRQ labelled transfers exposing declared fixed-record HP 3000 host-file bytes. |
| `KPCK` | `.kpck` | KolibriOS kpack wrapper holding one compressed payload. |
| `LIF` | `.cmp` | The single-member "DC"/"DL" compressed-file container U3 calls LIF. |
| `LIZARD` | `.lizard` | Decode every standard Lizard frame in the stream to a caller device. |
| `LOGITECH COMPRESS` | — | Logitech Compress wrapper holding one compressed file. |
| `LPAK` | `.cmp` | LPAK single-file LZSS stream with a declared plaintext size. |
| `LPAQ8` | — | LPAQ8 compressed stream; header identification without payload decoding. |
| `LZ4` | `.lz4` | Decode every standard LZ4 frame in the stream to a caller-provided device. |
| `LZ4Demo` | `.lz4` | Legacy LZ4 framing from the lz4demo compression utility. |
| `LZ5` | `.lz5` | Decode every standard LZ5 frame in the stream to a caller-provided device. |
| `LZDIET` | `.pad` | lZdIeT single-file compressed container with one payload. |
| `lzf stream` | `.lzf` | LZF ZV block streams decoding stored or compressed payloads. |
| `LZFSE / LZVN stream` | `.lzfse` | Apple LZFSE or LZVN compressed stream producing one decoded payload. |
| `LZHCXP` | `.lz` | Single-file container holding length-prefixed LZW-compressed blocks. |
| `LZIP` | `.lz` | Decode every consecutive Lzip member into a caller-provided device. |
| `LZK00` | `.lzk` | "LZK00" + four reserved zero bytes, then the byte aligned LZ77 stream. |
| `LZMA` | `.lzma` | LZMA-alone (.lzma) reader and writer: one "payload" record. |
| `lzma86` | `.lzma86` | LZMA86 compressed stream with optional x86 branch filtering. |
| `LZOP` | `.lzo` | lzop (.lzo) container reader, one record per stream. |
| `LZPIS2` | — | LZPIS2 compressed container exposing a single member. |
| `LZV1` | `.lzv` | LZV1 single-file container holding a compressed data stream. |
| `MathCAD` | `.mcd` | MathSoft MathCAD packed worksheet (".MCDCOMPRESSION"). |
| `Microsoft KWAJ stream` | — | Microsoft KWAJ installation compression streams supporting stored and documented compressed methods. |
| `MRNZ` | `.mrnz` | MRNZ (PC DOS installer) wrapped file. |
| `MS COMPRESS` | — | Microsoft SZDD and single-volume SZ. |
| `Mwave` | `.z` | IBM Mwave distribution wrapper around a Unix compress stream. |
| `NETWAREPACKED` | `.bin` | NetWare packed-file stream exposing one decoded payload. |
| `NPACK` | `.$` | Symantec NPack wrapper holding one compressed file. |
| `OpenPGP ZIP-compressed packet` | `.gpg` | OpenPGP compressed packets exposing one decoded stream without signature authenticity verification. |
| `ORACLE SQUEEZE` | `.sq` | Oracle/R:BASE Squeeze wrapper holding one compressed file. |
| `pem` | `.pem` | PEM text envelopes containing validated Base64-encoded certificate or key data. |
| `PP20` | `.pp`, `.pp20` | PowerPacker (PP20 / PP11 / PPLS) single-stream. |
| `ppmd` | `.pmd` | PPMd H/I single-file stream with compressed payload and source metadata. |
| `PSDC` | `.ps$` | PSDC packed-file reader (Print Shop Deluxe media). |
| `PSNCompress` | — | 3M Post-it Software Notes "PSNcompress" packed file. |
| `quoted_printable_encoded_fil` | `.qp` | Quoted-Printable (RFC 2045) encoded file. |
| `Raw Deflate` | `.deflate` | Bare Deflate stream without zlib, gzip or ZIP framing. |
| `RAW_LZW15V` | — | Raw LZW15V single-member compressed file. |
| `RawStac` | — | Stac Electronics LZS stream with NO container header at all. |
| `RNC` | `.rnc` | Rob Northen Compression (RNC ProPack). |
| `SCO` | `.Z` | SCO UNIX "compress -H" (LZH) stream. |
| `snappy framed` | `.sz` | Snappy framed streams decoding stored or compressed CRC32C-checked chunks. |
| `SOFTRONICS` | — | Softronics version 2.00 container holding one compressed file. |
| `SQ` | `.sq` | SQ (0x53 0x51 0xAC 0xAE) single-file squeezed container. |
| `Squeeze1` | `.sq` | Classic CP/M "Squeeze" (SQ, 0xFF76). |
| `Squeeze2` | `.sq2` | Squeeze II (0xFFFA) single-file squeezed container. |
| `Stac` | `.bin` | Stac Electronics LZS single-stream container ("sTaC"). |
| `TPWM` | `.tpwm` | Turbo Packer (TPWM) packed file. |
| `UNIX COMPRESS` | `.Z` | Decode the complete .Z stream to a caller-provided device. |
| `UNIX PACK` | `.z` | Decode the complete Unix pack stream to a caller-provided device. |
| `UnixCompact` | `.C` | Offset of the coded stream (just past the two magic bytes). |
| `uue` | `.uue` | UUencode or XXencode text streams carrying a named binary payload. |
| `WII LZ77` | `.lz77` | Nintendo LZ10/LZ11 compressed data with back-reference coding. |
| `WinLink` | — | WinLink packed-file ("02 00 00"). |
| `WRZL` | `.bml` | WRZL carries Kurt Haenen's LZRW1/KH blocks (published in SWAG ARCHIVES/0041.PAS). |
| `XPAK` | `.xpak` | An XPAK container: one 25-byte header and one packed stream. |
| `xpk_compressed_file` | `.xpk` | Amiga XPK ("XPKF") packed file. |
| `XZ` | `.xz` | XZ container holding an LZMA2-compressed data stream. |
| `yenc_encoded_file` | `.yenc` | yEnc text transport encoding with checksummed binary payload blocks. |
| `ZLIB` | `.zlib` | Standalone RFC 1950 zlib stream. |
| `ZSTD` | `.zst` | Decode every standard frame in the stream to a caller-provided device. |

## Packages, installers and self-extractors (182)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `ABBYY FineObjects` | `.exe` | ABBYY "Fine Objects" setup / patch executables (Lingvo 5, 1999). |
| `Advanced Installer bootstrapper` | `.exe` | Windows installer bootstrapper supporting stored embedded packages with XOR masking. |
| `AnalogX FFS` | `.exe` | AnalogX installers: a Watcom PE stub carrying an EmuCore "FFS" (Flat/Fast File System) payload. |
| `APK` | `.apk` | Android application package using a ZIP container. |
| `ARCV` | `.arv` | true = stock F=60 variant, false = compact F=32 variant. |
| `ARCV2` | `.arv` | Eschalon Setup version 2 archive with compact LZHUF members. |
| `ARCV4` | `.arv` | Eschalon Setup version 4 archive with alternating file and data chunks. |
| `ARDI diskette image` | `.exe` | ARDI self-extracting floppy image in a DOS/Windows executable. |
| `ARDI OS/2 installer` | `.exe` | OS/2 installer executable containing bounded file tables and payloads. |
| `ARNI installer container` | `.exe` | Installer executable container holding counted installation files and metadata. |
| `ARTIPACK` | `.pak` | Artisoft installation archive with LZHUF members and trailing directory. |
| `ASYMETRIX` | `.001` | Asymetrix ToolBook installation archive with packed member files. |
| `BCW` | `.bcw` | BCW container (SmartBoard-era installer payload); identification only. |
| `BeOSPackage` | `.pkg` | BeOS SoftwareValet installer package (.pkg). |
| `BFF` | `.bff` | IBM AIX backup and installation package with named file records. |
| `BND` | `.bnd` | PC-Install .BND disk-set volume; members use PKWARE DCL. |
| `BWCF` | `.set` | Beame and Whiteside distribution set containing compressed files. |
| `BWF` | `.bwf` | Beame & Whiteside distribution file. |
| `Clickteam Install Creator` | `.exe` | Clickteam Install Creator installers (1.x and 2.x). |
| `Clickteam Multimedia Fusion` | `.exe` | Clickteam Multimedia Fusion 2 / Fusion 2.5 stand-alone application (runtime pack in the PE overlay). |
| `Compaq SoftPaq 4` | `.exe` | The DOS executable ends in a 64-byte "!3PS" descriptor followed by length-prefixed stored members. |
| `Compaq SoftPaq v1` | `.exe` | A first-generation Compaq SoftPaq (SPnnnn.EXE, 1993..1995). |
| `CORELLTEC` | `.lta` | Corel / LEAD "LTEC" install archive (*.lta). |
| `CPOINT` | `.ins` | cPoint .INS installer with stored type-3 file records. |
| `CPX` | `.cpx` | CPX software distribution container with LZW-compressed members. |
| `CPX4` | `.cpx` | CPX version 4 distribution container with sectioned LZW-compressed members. |
| `CreateInstall` | `.exe` | CreateInstall "instcrin" self-extractor (pre-Gentee CreateInstall). |
| `crx` | `.crx` | CRX3 browser extension packages exposing protobuf headers and validated embedded ZIPs. |
| `DCLMultiStream` | `.dcl` | Consecutive raw PKWARE DCL streams from an installer data volume. |
| `DSL2` | `.d00` | DS L installation archive with obfuscated member directory. |
| `eBook Creator / SBook Builder` | `.exe` | eBook viewer executable containing appended page and resource stores. |
| `ECMPACKED` | `.ecm` | EmmaSetup packed installation member with compressed payload. |
| `ej-technologies install4j / exe4j` | `.exe` | Java application launcher containing install4j or exe4j embedded resources. |
| `Eschalon EPSF` | `.exe` | Eschalon Setup 3 "EPSF" self-extractor. |
| `F Install disk data` | — | F Install disk files containing tables of uncompressed installation members. |
| `FinEAR` | — | "FINEAR" installer transport: a 17-byte header followed by a single LZHUF (LHA -lh1-) stream. |
| `FlashJester Jugglor` | `.exe` | FlashJester Jugglor 2.x projector bundles (and "Exe Attachment"). |
| `FLD` | `.fld` | CodeBase installation file group with sequential compressed records. |
| `FPAK` | `.pak` | FoxPro Distribution Kit (.pak) archive. |
| `FRONTPAGETHEME` | `.elm` | Microsoft FrontPage theme package containing stored resource members. |
| `gemdos lha` | `.prg`, `.ttp`, `.tos` | Atari GEMDOS self-extractors exposing complete validated embedded LHA archive components. |
| `Gentee installer` | `.exe` | Gentee installer (gentee.com setup builder). |
| `Ghost Installer` | `.gip`, `.exe` | Ghost Installer packages containing XOR-obfuscated Microsoft Cabinet segments. |
| `GkSetup` | `.dat` | GkSetup installer data file (SETUP.DAT). |
| `GST` | `.gst` | GST Software installer container (Timeworks Publisher and friends). |
| `GTU` | `.csd` | IBM OS2 GTU distribution kit with indexed compressed files. |
| `HCI Instalit` | `.exe` | HCI Instalit / "Shadow" installer: the Win16 SFX and its data volumes (*.001). |
| `IBM ZPAK installer` | `.exe` | IBM installer executable carrying a compressed ZPAK package. |
| `IBMSPACK` | `.#` | IBM installation-diskette packed file with an adaptive-phrase stream. |
| `IFAH installer package` | `.exe` | Installer package containing bounded member records and installation metadata. |
| `IGF1` | — | IGF installation wrapper containing one compressed file. |
| `IGF2` | `.igf` | IGF installation archive containing LHA-compressed file records. |
| `Inno Setup` | `.exe` | Inno Setup executables exposing installation members; encrypted or external data unavailable. |
| `installanywhere unix` | `.bin` | InstallAnywhere Unix wrappers exposing bounded VM, installer and resource components. |
| `Installer VISE for Windows` | `.exe` | Windows Installer VISE executables supporting PE overlays and SIVM sections. |
| `InstallShield 12-2012 Setup` | `.exe` | InstallShield setup executable containing embedded installation data and resources. |
| `InstallShield 3.x/5.x SFX` | `.exe` | InstallShield self-extracting executable carrying version-specific installation file records. |
| `InstallShield 7 All-in-One Setup` | `.exe` | InstallShield all-in-one executable containing engine and installation payloads. |
| `InstallShield 7 setup.boot` | `.boot` | InstallShield setup.boot engine bundle containing chained SZDD-compressed records. |
| `InstallShield Developer 7` | `.exe` | InstallShield Developer executable carrying installation engine files and resources. |
| `InstallShield ISSetupStream` | `.exe` | InstallShield ISSetupStream containers supporting filters two and six for file records. |
| `InstallShield MultiPlatform` | `.exe` | InstallShield MultiPlatform installer carrying embedded engine and package resources. |
| `InstallShield skin` | `.skin` | Obfuscated InstallShield setup.skin resource archive containing named dialog assets. |
| `IPA` | `.ipa` | Apple iOS application package using a ZIP container. |
| `IRIXSA` | `.sa` | IRIX standalone-tools distribution volume containing named file members. |
| `IRWINPAC` | `.bin` | IrwinPac installation wrapper with independent compressed blocks. |
| `IS11` | `.ex$` | InstallShield 11/13-era compressed install file (*.EX$, *.CMP). |
| `IS3` | `.z` | InstallShield 3 installer data files. |
| `IS5` | `.cab` | InstallShield 5 and later cabinets ("ISc("). |
| `IS7INX` | `.inx` | InstallShield compiled InstallScript (".inx", also the compiled script embedded in a setup's Script Files). |
| `IzPack` | `.pack` | IzPack installer pack file ("packN"). |
| `JAR` | `.jar` | Java application archive using a ZIP container. |
| `JASC` | `.cmp` | Jasc Software installer archive (.CMP, and the SETUP.INF that ships beside it). |
| `java jmod` | `.jmod` | Java JMOD version-one packages exposing the complete validated embedded ZIP component. |
| `JGsoft DeployMaster` | `.exe` | JGsoft DeployMaster 2.x setup package (Delphi PE stub with the installation data in its overlay). |
| `KRZIP self-extractor` | `.exe` | KRZIP setups (Kryloff Technologies, Delphi installer stub). |
| `LIFKD` | `.lif` | Knowledge Dynamics LIF installation library with compressed members. |
| `LingvoArc` | `.lva` | The two ABBYY Lingvo / FineReader distribution-disk formats. |
| `makeself` | `.run` | Makeself shell installers exposing embedded encoded TAR or compressed TAR components. |
| `MicroFox PUT` | `.put`, `.ins` | MicroFox PUT archives using LHA member chains and proprietary methods. |
| `MIZ` | `.miz` | MIZ compressed-file wrapper carrying one original payload. |
| `Mozilla MAR` | `.mar` | Mozilla ARchive (Firefox update MAR). |
| `MVA` | `.mva` | MVA installation archive with stored or zlib-compressed files. |
| `NetWare2` | `.bin` | NetWare installation-disk container holding named packed file records. |
| `NID` | `.nid` | An "NI" install-set volume (DISK001.NID, RAID001.DAT, Z.PAC). |
| `NPM` | `.tgz` | npm package stored as a gzip-compressed TAR archive. |
| `Nullsoft PiMP` | `.exe` | Nullsoft PiMP (Plug-in Mini Packager, 1999-2000) installers. |
| `O'Setup` | `.exe` | O'Setup MZ installers supporting stored or SZDD-compressed installation members. |
| `Oberon` | `.z` | Oberon installation archive containing packed member files. |
| `OPC` | `.opc` | OS2Point software package containing a byte-obfuscated ZIP archive. |
| `PC-Install` | `.exe` | PC-Install executables supporting DCL-compressed groups and plain staging records. |
| `PCInstall` | `.shr` | PC-Install installer data file (*.SHR). |
| `PCOMMOS2` | — | IBM PCOMM installation file with a bare LZ77 stream. |
| `Phar` | `.phar` | PHP PHAR application archive with supported container variants. |
| `pmarc sfx` | `.com` | PMarc self-extracting COM carriers exposing complete validated embedded archive components. |
| `PyInstaller CArchive` | `.exe` | PyInstaller CArchive containing Python resources, scripts and embedded archives. |
| `PYZ` | `.pyz` | PyInstaller archive containing compressed Python modules and marshalled index. |
| `QIP1` | `.qip` | Quarterdeck QIP installation archive with DCL-compressed records. |
| `QIP2` | `.qip` | Quarterdeck install archive, version 2 (.QIP / .QIF). |
| `QSetup` | `.exe` | QSetup executables exposing complete checked zlib installation members. |
| `QUALITAS` | `.1` | Qualitas installation volume with compressed member records. |
| `QUARTERDECKQP` | `.qip` | Quarterdeck QP package with indexed DCL-compressed file records. |
| `RCF` | `.rcf` | RCF installation archive with a trailing member directory. |
| `Recognita` | `.cmp` | Recognita OCR distribution archive using PKWARE DCL compression. |
| `RED` | `.red` | Knowledge Dynamics RED installer archive with stored or LHA members. |
| `RID` | `.rid` | OS2 RID installation package with framed member data. |
| `RPM package` | `.rpm` | RPM software package containing metadata and an embedded installation payload. |
| `RTPATCH` | `.rtp` | Pocket Soft RTPatch installation package with compressed members. |
| `RTPatch Setup volume` | `.001` | RTPatch installer volumes containing update records and encoded patch data. |
| `SBX self-extractor` | `.exe` | SBX self-extractor (SBSETUP installer, "SB1" record chain). |
| `SCF` | `.scf` | Hijaak/PrintPartner .SCF setup container; members use PKWARE DCL. |
| `Setup Factory` | `.exe` | Setup Factory versions five or six executables exposing installation payload records. |
| `sfx 7zip` | `.exe` | Self-extracting 7ZIP carrier exporting the validated embedded payload component. |
| `sfx ace` | `.exe` | Self-extracting ACE carrier exporting the validated embedded payload component. |
| `SFX AD01` | `.exe` | Active Delivery self-extractor containing a protected embedded ZIP archive. |
| `sfx ain` | `.exe` | Self-extracting AIN carrier exporting the validated embedded payload component. |
| `sfx alz` | `.exe` | Self-extracting ALZ carrier exporting the validated embedded payload component. |
| `sfx arc` | `.exe` | Self-extracting ARC carrier exporting the validated embedded payload component. |
| `sfx arcv2` | `.exe` | Self-extracting ARCV2 carrier exporting the validated embedded payload component. |
| `sfx arj` | `.exe` | Self-extracting ARJ carrier exporting the validated embedded payload component. |
| `sfx arq` | `.exe` | Self-extracting ARQ carrier exporting the validated embedded payload component. |
| `sfx asymetrix` | `.exe` | Self-extracting ASYMETRIX carrier exporting the validated embedded payload component. |
| `sfx bsn` | `.exe` | Self-extracting BSN carrier exporting the validated embedded payload component. |
| `sfx bzip2` | `.exe` | Self-extracting BZIP2 carrier exporting the validated embedded payload component. |
| `sfx cab` | `.exe` | Self-extracting CAB carrier exporting the validated embedded payload component. |
| `sfx cazip` | `.exe` | Self-extracting CAZIP carrier exporting the validated embedded payload component. |
| `sfx chm` | `.exe` | Self-extracting CHM carrier exporting the validated embedded payload component. |
| `sfx chz` | `.exe` | Self-extracting CHZ carrier exporting the validated embedded payload component. |
| `sfx diskexpress` | `.exe` | Self-extracting DISKEXPRESS carrier exporting the validated embedded payload component. |
| `SFX embedded archive` | `.exe` | Validated embedded SFX archive records. |
| `sfx gxl` | `.exe` | Self-extracting GXL carrier exporting the validated embedded payload component. |
| `sfx gzip` | `.exe` | Self-extracting GZIP carrier exporting the validated embedded payload component. |
| `sfx ha` | `.exe` | Self-extracting HA carrier exporting the validated embedded payload component. |
| `sfx hap` | `.exe` | Self-extracting HAP carrier exporting the validated embedded payload component. |
| `sfx imp` | `.exe` | Self-extracting IMP carrier exporting the validated embedded payload component. |
| `sfx kwaj` | `.exe` | Self-extracting KWAJ carrier exporting the validated embedded payload component. |
| `sfx lha` | `.exe`, `.com` | LHarc or LArc self-extractors exposing the complete validated embedded archive. |
| `sfx lzx` | `.exe` | Self-extracting LZX carrier exporting the validated embedded payload component. |
| `sfx mpq` | `.exe` | Self-extracting MPQ carrier exporting the validated embedded payload component. |
| `SFX NSS` | `.exe` | Norton Secret Stuff 1.0 DOS SFX. |
| `sfx packagefortheweb` | `.exe` | PackageForTheWeb executables exposing decoded settings and validated Microsoft Cabinet components. |
| `sfx red` | `.exe` | Self-extracting RED carrier exporting the validated embedded payload component. |
| `SFX RSFX` | `.exe` | OS/2 LX self-extractor containing a complete RAR 1.5 archive. |
| `sfx rta` | `.exe` | Self-extracting RTA carrier exporting the validated embedded payload component. |
| `sfx rtpatch` | `.exe` | Self-extracting RTPATCH carrier exporting the validated embedded payload component. |
| `sfx spis` | `.exe` | GP-Install or InstallUs executable carriers exposing bounded SPIS installation components. |
| `sfx sqx` | `.exe` | Self-extracting SQX carrier exporting the validated embedded payload component. |
| `sfx sqz` | `.exe` | Self-extracting SQZ carrier exporting the validated embedded payload component. |
| `sfx starkit` | `.exe` | Self-extracting STARKIT carrier exporting the validated embedded payload component. |
| `sfx swag` | `.exe` | Self-extracting SWAG carrier exporting the validated embedded payload component. |
| `sfx szdd` | `.exe` | Self-extracting SZDD carrier exporting the validated embedded payload component. |
| `sfx tar` | `.exe` | Self-extracting TAR carrier exporting the validated embedded payload component. |
| `sfx tgcf` | `.exe` | Self-extracting TGCF carrier exporting the validated embedded payload component. |
| `SFX VMS DCX` | `.exe` | VMS DCX self-extractor preserving file-description and saveset streams. |
| `sfx zipcentral` | `.exe` | Self-extracting ZIPCENTRAL carrier exporting the validated embedded payload component. |
| `sfx zoo` | `.exe` | Self-extracting ZOO carrier exporting the validated embedded payload component. |
| `sfx zpak` | `.exe` | Self-extracting ZPAK carrier exporting the validated embedded payload component. |
| `SFXSTART` | `.exe` | "SFXSTART" self-extracting executable (stored setup-kit container). |
| `sis` | `.sis`, `.sisx` | Symbian / EPOC installation package (SIS, SISX). |
| `SMSIPAK` | `.pak` | SMSIPAK distribution volume with stored or DCL-compressed files. |
| `SoftPaq2` | `.exe` | Compaq/HP SoftPaq distribution executable with appended file directories. |
| `SolarisPackage` | `.pkg` | SVR4 / Solaris package datastream (pkgtrans, pkgadd). |
| `Solitaire Deluxe` | `.1` | Solitaire Deluxe installation volume containing named member files. |
| `SPIS` | `.spis` | GP-Install SPIS container with independently compressed members. |
| `Spoon Installer` | `.exe` | Spoon Installer MZ executables exposing checked bzip2 installation members. |
| `Starkit` | `.kit` | Tcl Starkit application stored in a Metakit virtual-filesystem database. |
| `STORK` | `.stk` | Stork DOS installation archive with DCL-compressed members. |
| `sun java binsh` | `.sh` | Sun Java shell installers exposing appended TAR archives or compressed streams. |
| `SW` | `.sw` | IRIX software distribution image containing sequential stored files. |
| `Sydex diskette image` | `.exe` | Sydex self-extracting floppy image stored behind a DOS/Windows stub. |
| `Tarma Installer` | `.exe` | Tarma version-five installers exposing numbered package blocks and partial-container flags. |
| `TopSpeed` | `.dsk` | TopSpeed installation wrapper exposing one original file. |
| `TWRX` | `.tzf` | The TWRX installer container (*.TZF). |
| `VMSDatabase` | `.pcsi` | OpenVMS PCSI product kit represented as a BER-like record tree. |
| `VMSPCSI` | `.pcsi$compressed` | OpenVMS compressed PCSI installation kit using DCX context tables. |
| `WarpIN package` | `.wpi` | A WarpIN package: the archive of the OS/2 / eComStation / ArcaOS "WarpIN" installer. |
| `WASP installer` | `.exe` | WASP (Windows Auto Setup Package, Cerious Software 1994). |
| `winimage zip` | `.exe` | WinImage self-extracting ZIP carriers supporting stored validated member data. |
| `Wise Installation System` | `.exe` | Wise Installation System installers (Wise16 NE / Wise32 PE). |
| `WPK` | `.wpk` | Memo of the archive-wide sorter probe. |
| `XAR` | `.xar` | XAR archive with a compressed XML member directory. |
| `ZTC` | `.ztc` | Zortech/Symantec distribution archive with LZHUF-compressed member pages. |

## Game archives and ROMs (122)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `AGIS` | `.ags` | AGIS archive with stored or PKWARE DCL-compressed members. |
| `amstrad cpc sna` | `.sna` | Amstrad CPC SNA v1-3 snapshots with stored RAM dumps. |
| `atari 7800 a78` | `.a78` | Atari7800 A78 v1-3 ROM containers exporting descriptor and stored program. |
| `BattleIsle` | `.lib` | Battle Isle LIB game-resource container with indexed members. |
| `BeatTheHouse` | `.pak` | Beat The House "PAK?" packed-stream. |
| `bethesda ba2` | `.ba2` | Bethesda BA2 version-one GNRL archives supporting stored file records. |
| `bethesda bsa` | `.bsa` | Bethesda BSA versions 103–105 archives supporting stored members only. |
| `bgi` | `.arc` | BGI / Ethornell version 1 "PackFile" archive. |
| `bgi2` | `.arc` | BGI / Ethornell "BURIKO ARC20" archive. |
| `BIGF` | `.big` | Electronic Arts BIG/VIV game archive with indexed file members. |
| `bioware biff` | `.bif` | BioWare BIFF variable-resource archives excluding fixed or compressed resources. |
| `bioware erf` | `.erf`, `.mod`, `.hak`, `.sav` | BioWare ERF, MOD, HAK and SAV archives supporting unencrypted resources. |
| `bioware rim` | `.rim` | BioWare RIM version-one archives containing indexed stored resource payloads. |
| `BSN` | `.bsn` | BSA BSN archive with CRC-protected member headers and payloads. |
| `build grp` | `.grp` | Build engine GRP archives containing indexed stored game resources. |
| `CAT` | `.cat` | Software Creations / Bullfrog-era .CAT catalogue: a flat stored directory. |
| `CatSystem KIF` | `.int` | Copy a member to a caller-owned device; NULL verifies it only. |
| `CKP game archive` | `.ckp` | CKP game archive with validated named member records. |
| `commodore crt` | `.crt` | Commodore cartridge images containing hardware headers and stored chip packets. |
| `cpk` | `.cpk` | CRI Middleware CPK resource archive. |
| `cri afs` | `.afs` | CRI AFS archives containing indexed game files and optional filename tables. |
| `crt` | `.crt` | A VICE cartridge image for any of the five Commodore machines. |
| `doom wad` | `.wad` | Doom IWAD or PWAD archives containing indexed game resource lumps. |
| `DPK` | `.dpk` | DPK game-resource archive containing named file members. |
| `dxa` | `.dxa` | DxLib DXA resource archive reader (incl. .wolf). |
| `EA` | `.pea` | Electronic Arts DOS resource archive containing named members. |
| `EALIB` | `.lib` | Electronic Arts resource library containing named file records. |
| `EAREFPACK` | `.qfs` | Electronic Arts RefPack wrapper holding compressed resource data. |
| `EdgeDataPak archive` | `.edp` | EdgeDataPak game archive with validated named member records. |
| `fromsoftware binder` | `.bnd` | FromSoftware BND3 or BND4 binders supporting indexed stored game resources. |
| `GAMOS` | `.gpf` | GAMOS PACKED FILE (.gpf) archive. |
| `GOB` | `.gob` | LucasArts GOB game archive with an indexed member directory. |
| `Godot PCK resource pack` | `.pck` | Godot resource pack containing indexed game files and asset payloads. |
| `halflife wad3` | `.wad` | Half-Life WAD3 archives exposing stored texture and resource lumps. |
| `HOG` | `.hog` | Descent 1/2 HOG archive containing sequential stored members. |
| `HOG2` | `.hog` | Descent 3 HOG2 game archive with an indexed directory. |
| `idtech bsp` | `.bsp` | Quake II or III BSP maps exposing stored encoded map lumps. |
| `Infogrames PAK` | `.pak` | Infogrames / AITD engine .PAK. |
| `JAM` | `.jam` | JAM game resource archive with stored directory-tree members. |
| `kirikiri xp3` | `.xp3` | KiriKiri XP3 archives supporting unprotected single-segment stored files and raw indices. |
| `KRML` | `.eng` | A KRML game resource archive: a 6-byte header, a flat fixed-width directory, and stored member data. |
| `larian lspk` | `.pak` | Larian LSPK version-ten archives supporting stored members and uncompressed indices. |
| `lithtech rez` | `.rez` | LithTech RezMgr version-one archives containing bounded stored resource trees. |
| `livemaker` | `.dat` | LiveMaker resource archive (game.dat, or appended to the game EXE). |
| `lucas bun` | `.bun` | LucasArts LB83 or LB23 bundles preserving encoded iMUSE resources. |
| `lucas lab` | `.lab` | Grim Fandango LABN archives supporting stored files and plain names. |
| `lynx lnx` | `.lnx` | Atari Lynx cartridge images containing LNX headers and ROM banks. |
| `Majiro` | `.arc` | MajiroArcV1.000, V2.000 and V3.000 game-resource archives (.arc). |
| `Malie LIB` | `.lib` | Unencrypted Malie LIB resource archives: "LIB\0", 16-byte header and a positive signed 16-bit count at 8. |
| `maxis_far_archive` | `.far` | Maxis FAR archive reader (The Sims). |
| `MegatechVol` | `.vol` | Megatech Software .VOL resource volume. |
| `mohawk mhk` | `.mhk` | Mohawk resource archives exposing encoded members from validated resource tables. |
| `MPQ` | `.mpq` | Blizzard MoPaQ (MPQ) game archive. |
| `mythic myp` | `.uop` | Mythic MYP or UOP versions four or five archives supporting stored members. |
| `nes rom` | `.nes` | NES ROM containers exposing cartridge headers and program or character banks. |
| `NeXAS PAC` | `.pac` | NeXAS PAC archives: 12-byte header with positive LE count and mode 0..4. |
| `nintendo bfres` | `.bfres` | Wii U FRES resource archives supporting external attachments without model decoding. |
| `nintendo brres` | `.brres` | Nintendo BRRES resource containers exposing big-endian encoded dictionary sections. |
| `nintendo cia` | `.cia` | Nintendo CIA version-zero packages exposing unencrypted content with SHA-256 checks. |
| `nintendo gb rom` | `.gb` | Game Boy cartridge images validating stored banks, boot logos and checksums. |
| `nintendo gba rom` | `.gba` | Game Boy Advance ROM images validating cartridge headers and entry framing. |
| `nintendo hfs0` | `.hfs0` | Nintendo HFS0 partitions containing stored files with verified hashed prefixes. |
| `nintendo n64 rom` | `.z64` | Native big-endian N64 ROM images validating supported cartridge headers and checksums. |
| `nintendo narc` | `.narc` | Nintendo DS NARC version-one archives containing stored numbered files. |
| `nintendo ncch` | `.cxi`, `.cfa` | Nintendo NCCH versions zero through two containers supporting unencrypted components. |
| `nintendo ncsd` | `.3ds` | Nintendo NCSD gamecard images exposing bounded unencrypted NCCH partitions. |
| `nintendo nds` | `.nds` | Nintendo DS ROM images exposing checked executable, banner and indexed files. |
| `nintendo pfs0` | `.pfs0`, `.nsp` | Nintendo PFS0 partition archives containing stored files and string tables. |
| `nintendo rarc` | `.arc` | Nintendo RARC archives containing hierarchical game resources and file tables. |
| `nintendo sarc` | `.sarc` | Nintendo SARC version-one archives supporting stored files in either endian. |
| `nintendo u8` | `.arc`, `.u8` | Nintendo U8 archives containing hierarchical stored game resource files. |
| `nintendo unif` | `.unf`, `.unif` | Nintendo UNIF v1-7 ROM containers preserving PRG/CHR banks. |
| `Nitroplus NPA` | `.npa` | NPA01 archives with a 41-byte header and variable CP932 filename records. |
| `Nitroplus NPK2` | `.npk` | NPK2 encrypted resource archive, with UTF-8 names and stored/raw-Deflate segments. |
| `noa` | `.noa` | Entis GLS / ERISA NOA resource archive. |
| `NScripter NS2 archive` | `.ns2` | An NScripter2 (NS2) resource archive, unencrypted. |
| `NScripter NSA archive` | `.nsa` | An NScripter / ONScripter NSA resource archive (arc.nsa, arc1.nsa, ...; some games name it *.dat). |
| `Parsec resource archive` | `.dat` | Parsec's unnamed offset/size table containing contiguous RIB or SM8 files. |
| `Parsec RIB compressed resource` | `.rib` | RIB\0 reverse-decoded Parsec resource stream. |
| `Ptero-Engine BIGF/ZBL archive` | `.cbf`, `.zbl` | Distinct from Electronic Arts BIGF/BIG4 archives. |
| `Qlie PACK` | `.pack` | Reader-local operation/format selector, values above, for1.0 archives. |
| `quake pak` | `.pak` | Quake PAK archives containing indexed uncompressed game resource files. |
| `quake wad2` | `.wad` | Quake WAD2 archives exposing stored resource lumps and compression metadata. |
| `ravensoft rff` | `.rff` | Blood RFF versions two or three archives supporting stored transformed resources. |
| `relic chunky` | — | Relic Chunky version-3.1 resources exposing bounded hierarchical encoded DATA chunks. |
| `relic sga` | `.sga` | Relic SGA archives exposing supported indexed stored game resource members. |
| `renpy rpa` | `.rpa` | Ren'Py RPA3 archives decoding restricted indices while preserving stored file payloads. |
| `RES` | `.res` | Game resource container with a fixed directory of stored members. |
| `rpg_maker_rgssad` | `.rgssad`, `.rgss2a`, `.rgss3a` | An RPG Maker (RGSS) resource archive: Game.rgssad (XP), Game.rgss2a (VX) and Game.rgss3a (VX Ace). |
| `RSC` | `.rsc` | Resource container with a fixed directory of stored payloads. |
| `sar ns` | `.sar` | NScripter SAR archives with stored members and big-endian indices. |
| `sega megadrive rom` | `.md`, `.bin` | Unwrapped big-endian Mega Drive ROMs validating headers and stored cartridge data. |
| `Settlers` | `.pa` | Settlers game resource file with indexed size and offset records. |
| `Silmarils` | `.io` | A Silmarils ALIS script container (.IO / .CO / .DO). |
| `sony psarc` | `.psarc` | Sony PSARC version-1.4 archives supporting unencrypted tables and stored blocks. |
| `sony psp pbp` | `.pbp` | PSP PBP version-one homebrew packages exposing validated metadata and executable sections. |
| `STK` | `.stk` | Coktel Vision STK/ITK game archive with indexed resource files. |
| `stos_memory_bank` | `.mbk` | STOS BASIC memory-bank container for Atari ST resources. |
| `Stunts` | `.pes` | Stunts / 4D Sports Driving DSI compressed resource. |
| `Teacy` | `.dat` | A Teacy ".DAT" archive: a 16-bit member count followed by a directory of 24-byte records and stored payloads. |
| `telltale_ttarch` | `.ttarch2` | A Telltale Tool ".ttarch2" archive (2012 and later games). |
| `terminalreality pod` | `.pod` | Terminal Reality POD2 archives containing stored resources with verified CRCs. |
| `tiled tmx` | `.tmx` | Tiled TMX1.x finite orthogonal maps with embedded tilesets and uncompressed layers. |
| `totalannihilation hpi` | `.hpi` | Total Annihilation HPI version-one archives supporting unencrypted stored members. |
| `unity serialized` | `.assets` | Unity SerializedFile version-22 containers exposing stored objects without type trees. |
| `unityfs` | `.bundle`, `.unity3d` | UnityFS versions six through eight bundles supporting stored data blocks. |
| `unreal package` | `.u`, `.unr`, `.utx`, `.uax` | Unreal Engine-one packages supporting uncompressed export objects from versions 61–63. |
| `valve bsp` | `.bsp` | Source BSP versions 19–21 maps exposing uncompressed lumps and embedded ZIPs. |
| `valve hpak` | `.hpk` | GoldSrc HPAK version-one archives supporting stored resources with verified MD5 checksums. |
| `valve vpk` | `.vpk` | Valve VPK archives containing indexed game files and archive references. |
| `valve_gcf_cache` | `.gcf` | Valve Steam game cache file (.gcf), versions 1.3, 1.5 and 1.6. |
| `valve_xzp` | `.xzp` | Valve XZP (Xbox Half-Life 2 pack). |
| `vice snapshot` | `.vsf` | VICE v1.0/v1.1 snapshots exporting original emulator state modules. |
| `Visionaire Studio VIS` | `.vis` | Visionaire Studio 3.x+ game data archive (".vis", "VIS3"). 0x00 char[4] "VIS3" 0x04 u32 member count N. |
| `volition vpp` | `.vpp` | Volition VPP version-three archives supporting stored uncompressed game resources. |
| `VolitionVP` | `.vp` | Volition "VP" package (Descent: FreeSpace / FreeSpace 2 .vp). |
| `Westwood PAK` | `.pak` | Westwood PAK game archive with an indexed stored-member directory. |
| `WintermuteDCP` | `.dcp` | Wintermute game archive with a trailing named member directory. |
| `Wolf` | `.wl1` | Wolfenstein/Blake Stone VSWAP resource container with stored chunks. |
| `xna xnb` | `.xnb` | Uncompressed XNB version-five content containers supporting a limited resource-reader subset. |
| `ypf` | `.ypf` | YU-RIS engine YPF resource archive. |
| `zx spectrum szx` | `.szx` | Spectrum SZX v1.0-v1.5 snapshots with uncompressed RAM pages. |

## Disk, disc and tape images (162)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `2IMG` | `.2mg` | Apple II 2IMG disk image: a 64-byte header with image, comment and creator extents. |
| `AaruFormat` | `.aif` | AaruFormat version 2 block-media image with bounded component records. |
| `acorn uef` | `.uef` | Uncompressed Acorn UEF v0.10 tape subset with original data blocks. |
| `acorn_atom_disk` | `.40t` | Acorn Atom DOS disk image. |
| `act apricot pc xi raw` | `.img` | Apricot raw FAT12 disk images with validated geometry and allocation tables. |
| `adam` | `.dsk` | Coleco Adam disk images containing EOS filesystem directory members. |
| `Alcohol 120% MDS/MDF` | `.mds` | Alcohol 120% MDS v1.4 / companion MDF. |
| `Amiga ADF` | `.adf` | Amiga floppy disk images exposing supported filesystem directory members. |
| `amiga ipf` | `.ipf` | IPF disk images preserving CRC-checked encoded tracks without weak cells. |
| `amstrad cpc dsk` | `.dsk` | Standard and extended CPC DSK images exporting stored sectors. |
| `AnaDisk sector disk image` | `.ana` | AnaDisk sequential sector records; conservative probing requires two populated sectors. |
| `Android sparse image` | `.img` | Android sparse disk image with raw, fill and skip chunks. |
| `Anex86 HDI` | `.hdi` | Stream the zero-based member to a borrowed device at its current cursor. |
| `apollo_afd` | `.afd` | Apollo floppy disk image (.afd). |
| `apple a2r` | `.a2r` | Apple A2R2 captures preserving timing streams or normalized bit captures. |
| `Apple Disk Copy 6 NDIF image` | `.img` | Apple Disk Copy 6 NDIF disk image reader (MacBinary-wrapped). |
| `Apple DiskCopy 4.2` | `.dc42` | Apple DiskCopy 4.2 floppy image. |
| `Apple sparse bundle` | `.sparsebundle` | Apple sparse-bundle image with band-organized disk data. |
| `apple woz` | `.woz` | Apple WOZ1/WOZ2 5.25-inch images preserving original track bitstreams. |
| `Apricot` | `.dsk` | ACT Apricot disk image with tagged literal and run-length records. |
| `ApriDisk` | `.apr` | ApriDisk floppy image storing typed compressed sector records. |
| `atari atr` | `.atr` | Atari ATR images exporting raw 128/256-byte sectors without filesystem recovery. |
| `atari cas` | `.cas` | Atari FUJI cassette images containing framed data and FSK pulse words. |
| `atari pasti stx` | `.stx` | Pasti STX v3 simple tracks exporting original error-checked sector records. |
| `atari st msa` | `.msa` | Atari ST MSA disk images with decoded E5 RLE tracks. |
| `blindwrite_5_6_image` | `.b5t`, `.b6t` | BlindWrite 5/6 disc descriptor referencing companion track-data files. |
| `bondwell 2 disk` | `.dsk` | Bondwell raw CP/M disk images with validated live directory entries. |
| `camputers_lynx_ldf` | `.ldf` | Camputers Lynx .LDF floppy image. |
| `casio fz 1 disk` | `.img` | Casio FZ-1 sampler disks with fixed geometry and allocation structures. |
| `CDRDAO TOC` | `.toc` | CDRDAO TOC descriptor referencing companion disc-track data files. |
| `CDRWIN CUE sheet` | `.cue` | CDRWIN text descriptors identifying disc tracks and backing image files. |
| `CISO` | `.cso` | Compressed ISO disc image supporting CISO, ZISO and DAX layouts. |
| `CISO v2` | `.cso` | CISO version 2 compressed ISO image with block indexing. |
| `CloneCD CCD/IMG/SUB` | `.ccd` | CloneCD disc descriptor with companion image and subchannel data. |
| `cloop / geom_uzip` | `.cloop` | Compressed disk image with indexed cloop or geom_uzip blocks. |
| `Commodore 2040 DOS 1 D67` | `.d67` | Commodore 2040 DOS 1 floppy image with file records. |
| `Commodore 8050/8250 D80/D82` | `.d80`, `.d82` | Commodore D80/D82 floppy images with filesystem directory entries. |
| `Commodore CMD D1M disk image` | `.d1m` | Commodore CMD D1M disk image with file records. |
| `Commodore CMD D2M disk image` | `.d2m` | Commodore CMD D2M disk image with file records. |
| `Commodore CMD D4M disk image` | `.d4m` | Commodore CMD D4M disk image with file records. |
| `Commodore D64` | `.d64` | Commodore D64 floppy image, including supported extended-track variants. |
| `Commodore D71` | `.d71` | Commodore D71 double-sided floppy image with filesystem entries. |
| `Commodore D81` | `.d81` | Commodore D81 floppy image with directories and file sectors. |
| `Commodore D9060/D9090 D90` | `.d90` | Commodore D9060/D9090 hard-disk image with file-directory records. |
| `commodore g64` | `.g64` | G64 v0 disk images preserving encoded GCR half-tracks and speed maps. |
| `commodore p64` | `.p64` | P64 v0 disk images preserving CRC-checked encoded flux streams. |
| `commodore tap` | `.tap` | Commodore TAP v0/v1 cassette images containing framed pulse trains. |
| `CopyDisk` | `.dsk` | A COPYDISK image: a 0x20-byte header and then the raw sector image. |
| `CopyQM` | `.cqm` | Sydex CopyQM floppy image with a run-length-compressed sector dump. |
| `daemon_tools_mdx` | `.mdx`, `.mds` | DAEMON Tools single-file MDX or MDS-v2 disc image. |
| `dart` | `.dart` | Apple DART (Disk Archival/Retrieval Tool) image. |
| `DAX compressed ISO` | `.dax` | DAX compressed ISO disc image with indexed compressed blocks. |
| `ddd` | `.ddd` | DDD / DDD Pro (Dalton's Disk Disintegrator). |
| `DiskDupe` | `.ddi` | DiskDupe DDI floppy image with sector data. |
| `DiskExpress` | `.dxp` | Disk eXPress floppy image with stored or independently compressed tracks. |
| `DiskJuggler` | `.cdi` | DiscJuggler CDI image with disc sessions and track data. |
| `DMG` | `.dmg` | Apple UDIF disk image (DMG). |
| `DMK` | `.dmk` | healthy-sector reconstruction of DMK images. |
| `DMS` | `.dms` | DMS is the archiver Amiga bulletin boards used to ship floppy images. |
| `Dolphin RVZ GameCube image` | `.rvz` | Dolphin RVZ v1 GameCube images, exposed as a reconstructed ISO member. |
| `dragon cas` | `.cas` | Dragon/CoCo CAS tape blocks with mandatory EOF and checked checksums. |
| `dragon vdk` | `.vdk` | Dragon VDK v0x10 disk images exporting stored sectors and descriptors. |
| `Dreamcast GDI` | `.gdi` | Copy an exact track to a device; NULL destination verifies/read-checks it. |
| `EMT` | `.emt` | "EMT" compressed diskette image (EMT4OS2 / EMT4PM / EMT4PMW). |
| `Encrypted Apple disk image` | `.dmg` | Encrypted Apple disk image preserving headers and encrypted regions. |
| `ewf2_ex01` | `.Ex01` | Expert Witness Compression Format 2 (EnCase 7+ .Ex01). |
| `Expert Witness / EnCase EWF v1` | `.E01` | EnCase EWF version-one forensic image with segmented evidence data. |
| `FDCOPY CFI` | `.cfi` | FDCOPY CFI floppy image with compressed sector data. |
| `FDI` | `.fdi` | FDI floppy image describing tracks and sector contents. |
| `gbi` | `.gbi` | gBurner GBI compressed disc image. |
| `Gotek disk collection` | — | Gotek disk collection containing fixed-geometry floppy images. |
| `HDCopy` | `.img` | HD-COPY floppy image with stored or compressed track data. |
| `HFE` | `.hfe` | HxC HFE floppy image preserving encoded track-bit data. |
| `hsf` | `.iso` | High Sierra (pre-ISO 9660) CD-ROM image. |
| `hxc mfm` | `.mfm` | HxC MFM captures preserving indexed raw bitcell tracks without decoding. |
| `HxC Stream HFE` | `.hfe` | HxC "Stream HFE" flux image. |
| `hxc_hfe_extended` | `.hfe` | HxC Floppy Emulator "extended" HFE (format revision 1, hxcfe HXC_EXTHFE). |
| `hxc_hfe_hddd_a2_variant` | `.hfe` | HxC HFE Apple II variant with doubled-rate bit-cell encoding. |
| `hxc_hfe_v3` | `.hfe` | HxC Floppy Emulator HFE v3 image ("HXCHFEV3"). |
| `IMD` | `.imd` | Dunfield ImageDisk track records with expanded sector encodings. |
| `ISO9660` | `.iso` | ISO 9660 disc filesystem with directory and file records. |
| `isz` | `.isz` | Chunked compressed disc image supporting stored, zlib, bzip2 and zero blocks. |
| `jvc` | `.jvc` | JVC floppy image containing a Dragon DOS or OS-9 volume. |
| `kryoflux_stream` | `.raw` | KryoFlux stream file (trackNN.S.raw): the flux transitions of one side of one track. |
| `LibDsk LDBS disk image` | `.ldbs` | LibDsk LDBS floppy image with a typed block store. |
| `LibDsk LDBST text disk image` | `.ldbst` | Bounded native parser for LibDsk's [LDBS] text disc-image form. |
| `LOFI` | — | Solaris lofi disk image with individually compressed LZMA segments. |
| `LUKS` | — | LUKS encrypted-volume headers and stored encrypted payload components. |
| `MAME CHD` | `.chd` | MAME compressed hard disk images exposing supported hunk data. |
| `mame floppy image mfi` | `.mfi` | MAME floppy images containing compressed flux tracks and recoverable sector data. |
| `mgt` | `.mgt` | MGT disk image (+D / DISCiPLE / SAM Coupe). |
| `moof` | `.moof` | Applesauce MOOF (Macintosh 3.5" floppy). |
| `msx cas` | `.cas` | MSX CAS binary tape files with checked load ranges. |
| `MYZ80 disk image` | — | MYZ80 emulator disk image exposing its configured sector layout. |
| `NanoWasp Microbee disk image` | — | NanoWasp Microbee emulator disk image with sector records. |
| `NEC PC-98 FDI` | `.fdi` | Anex86 NEC PC-98 floppy image with a header and stored sectors. |
| `Nero NRG disc image` | `.nrg` | Nero disc image containing track data and footer metadata. |
| `NeXTSTEP disk image` | `.diskimage` | NeXTSTEP diskimage and bounded legacy FFS traversal. |
| `NHD` | `.nhd` | Stream a zero-based member to a borrowed output device. |
| `nintendo fds` | `.fds` | Headered FDS disk images containing stored Nintendo file records. |
| `nintendo gcm` | `.gcm`, `.iso` | GameCube disc images exposing bounded DOL executables and filesystem files. |
| `nintendo wbfs` | `.wbfs` | Single-disc Wii WBFS images exposing mapped stored disc-cluster components. |
| `North Star NSI disk image` | `.nsi` | Headerless North Star NSI sector dumps. |
| `oric tap` | `.tap` | Oric TAP ordinary BASIC/machine-code records with bounded filenames and payloads. |
| `parallels hdd` | `.hdd`, `.hds` | Parallels sparse hard disk images with mapped guest disk sectors. |
| `partclone_image` | `.img` | Partclone version 0002 image with preserved allocated-block data. |
| `Partimage` | `.partimg` | NULL destination verifies data and checksums without writing. |
| `pc magazine flp` | `.flp` | PC Magazine floppy images containing geometry headers and stored sectors. |
| `pc98 d88` | `.d88` | Single classic D88 disk images exporting error-free FM/MFM sectors. |
| `PCE PBI block disk image` | `.pbi` | PCE Block Image version 0. |
| `PCE PBIT bitstream disk image` | `.pbit` | PCE PBIT v0 bitstream disk images, the predecessor of PRI. |
| `PCE PFDC v0 sector disk image` | `.pfdc` | PCE PFDC version 0 floppy image with sector records. |
| `PCE PFDC v1 sector disk image` | `.pfdc` | PCE PFDC version 1 floppy image with sector records. |
| `PCE PFDC v2 sector disk image` | `.pfdc` | PCE PFDC version 2 floppy image with sector records. |
| `PCE PFDC v4 sector disk image` | `.pfdc` | PCE PFDC version 4 floppy image with sector records. |
| `PCE PFI flux disk image` | `.pfi` | PCE PFI version-0 flux images. |
| `PCE PRI bitstream disk image` | `.pri` | PCE PRI version-0 bitstream disk images. |
| `pce psi` | `.psi` | PCE PSI v0 images with checked sectors and CRC32C chunks. |
| `PCE TransCopy TC bitstream disk image` | `.tc` | TransCopy track-bitstream disk images via the PCE TC layout. |
| `PCE XDF 1.84 MB sector disk image` | `.xdf` | PCE/IBM XDF 1.84 MB physical sector layout. |
| `PMDiskcopy` | `.img` | PM Diskcopy image: an 11-byte signature, a DOS BPB copy, then the stored sectors. |
| `QCOW` | `.qcow2` | QEMU QCOW2 / QCOW3 disk image. |
| `QCOW1` | `.qcow` | QEMU QCOW version 1 disk image. |
| `qemu enhanced disk` | `.qed` | QEMU QED sparse disk images with guest block allocation tables. |
| `QRST` | — | Compaq QRST diskette set with run-length-compressed floppy tracks. |
| `rawcd` | `.bin` | Raw CD sector images exposing validated cooked user-data sectors. |
| `SABDU` | `.sdu` | SAB Diskette Utility image with geometry and raw sectors. |
| `SaveDskF` | `.dsk` | IBM SaveDskF diskette image with stored or compressed sectors. |
| `SCL` | `.scl` | ZX Spectrum SCL disk catalogue followed by concatenated file sectors. |
| `SDI` | `.sdi` | Stream a zero-based member to a borrowed output device. |
| `ShrinkWrap` | `.image` | Apple Disk Copy 4.2 floppy image with optional GCR tag data. |
| `SIMH CP/M disk image` | — | SIMH CP/M disk image with 137-byte physical sector records. |
| `Snatch-it CP2 disk image` | `.cp2` | Snatch-it CP2 version 3.02 floppy image containing sector data. |
| `SOS` | `.adf` | Bootable Amiga disk image with a fixed member directory. |
| `spectrum_udi` | `.udi` | ZX Spectrum UDI ("Ultra Disk Image", Alex Makeev) raw-track floppy image. |
| `supercard scp` | `.scp` | SuperCard floppy captures preserving 16-bit flux records without sector decoding. |
| `t64` | `.t64` | Commodore T64 tape archives preserving PRG load addresses and entries. |
| `T98-Next NFD` | `.nfd` | T98-Next NFD floppy image (NEC PC-98), revisions r0 ("T98FDDIMAGE.R0") and r1 ("T98FDDIMAGE.R1"). |
| `TeleDisk` | `.td0` | Sydex TeleDisk floppy image with stored or compressed tracks. |
| `Thomson FD disk image` | `.fd` | Headerless Thomson double-sided FD dumps. |
| `Thomson SAP` | `.sap` | Stream the zero-based member to a borrowed device at its current cursor. |
| `TRDOS` | `.trd` | TR-DOS (.TRD) ZX Spectrum Beta Disk image. |
| `TRS-80 JV1` | `.jv1` | TRS-80 JV1 disk image reader (TRSDOS/LDOS). |
| `TRS-80 JV3` | `.jv3` | TRS-80 JV3 floppy image (Jeff Vavasour's format, as used by xtrs). |
| `uif` | `.uif` | MagicISO UIF ("Universal Image Format") disc image. |
| `vdi` | `.vdi` | VirtualBox disk images exposing stored or sparse guest sectors. |
| `VHDDynamic` | `.vhd` | Microsoft VHD disk image (fixed, dynamic, differencing). |
| `VHDX` | `.vhdx` | Virtual hard disk container with metadata and mapped guest sectors. |
| `vice x64` | `.x64` | VICE X64 v1.02 disk images with closed PRG/SEQ sector chains. |
| `Virtual98` | `.vhd` | Stream a zero-based member to a borrowed output device. |
| `VMDK` | `.vmdk` | VMware sparse extent (VMDK) disk image. |
| `vmdk_cowd_sparse` | `.vmdk` | VMware COWD sparse extent (ESX/GSX vmfsSparse) disk image. |
| `vmdk_sesparse` | `.vmdk` | VMware seSparse (space-efficient sparse) VMDK extent. |
| `WIM` | `.wim` | Windows Imaging container with metadata and compressed file resources. |
| `WUX` | `.wux` | Stream a zero-based member to a borrowed output device. |
| `X68000 DIM floppy image` | `.dim` | Sharp X68000 floppy image with a fixed-position track map. |
| `Xen XVA` | `.xva` | NULL destination verifies every stored chunk, including keepalive/padding. |
| `yaze ydsk` | `.dsk` | YAZE disk images exporting sectors from checked CP/M disk descriptors. |
| `ZISO` | `.zso`, `.cso` | ZISO compressed ISO disc image using LZ4 blocks. |
| `Zoom disk image` | `.zom` | Zoom (Amiga floppy imager, "ZOM5"). |
| `zx spectrum pzx` | `.pzx` | Spectrum PZX v1.0 tape images preserving framed pulse/data chunks. |
| `zx spectrum tzx` | `.tzx` | Spectrum TZX v1.00-1.20 straight-line tape blocks without control flow. |

## Filesystems and partitions (47)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `Acorn ADFS` | `.adf` | Acorn ADFS S/M/L filesystem with contiguous file allocation. |
| `Acorn DFS` | `.ssd`, `.dsd` | Acorn DFS filesystem with supported single- and double-sided geometries. |
| `Amiga Rigid Disk Block (RDB) hard disk` | `.hdf` | Amiga hard disk containing linked partition and filesystem-handler records. |
| `AODOS` | `.img` | AO-DOS and MicroDOS filesystem images for Elektronika BK machines. |
| `APFS` | — | Apple File System (APFS) container. |
| `Apple DOS 3.2` | `.d13` | Apple DOS 3.2 filesystem with 13-sector disk ordering. |
| `Apple DOS 3.3 32-sector` | `.do` | Apple DOS 3.3 filesystem using a 32-sector track layout. |
| `Apple DOS3.3` | `.do`, `.po` | Apple DOS 3.3 filesystem using DOS or ProDOS sector ordering. |
| `Apple Partition Map` | `.img` | Apple partition tables describing bounded partition regions within disk images. |
| `Apple Pascal` | `.po`, `.dsk` | Apple II UCSD Pascal filesystem. |
| `Atari DOS 2.x filesystem` | `.atr` | Atari DOS 2.x filesystem with supported floppy geometries. |
| `BSD UFS1` | `.img` | NULL destination verifies all stored bytes; sparse holes need no reads. |
| `Btrfs` | — | "_BHRfS_M" read as a little-endian 64-bit value. |
| `CP/M` | `.img` | CP/M filesystem with explicit disk geometry and sector-order presets. |
| `CRAMFS` | `.cramfs` | Superblock flag bits, as defined by include/uapi/linux/cramfs_fs.h. |
| `CSIDOS` | `.img` | CSI-DOS floppy images for the Soviet Elektronika BK-0011M (.IMG/.BKD). |
| `EROFS filesystem image` | `.img` | EROFS compressed read-only filesystem with directories and file data. |
| `exFAT` | `.img` | Native, read-only exFAT volume listing and extraction. |
| `ext2/3/4` | — | Linux ext2/ext3/ext4 volume exposing directories and file data. |
| `FAT` | `.img` | Which of the three FAT variants a volume turned out to be. |
| `GPT` | `.img` | GUID Partition Table reader (UEFI spec, chapter 5). |
| `HFS+/HFSX` | `.img` | HFS+/HFSX filesystem with Unicode names and data/resource forks. |
| `JFFS2` | `.jffs2` | JFFS2 - the journalling flash filesystem, version 2. |
| `jffs2_old` | `.jffs2` | JFFS2 (old 0x1984 node magic) journalling flash filesystem. |
| `LogFS` | — | LogFS log-structured flash filesystem identifier. |
| `Macintosh HFS` | `.img` | Macintosh HFS volume exposing folders, data forks and resource forks. |
| `Macintosh MFS` | `.img` | Macintosh MFS volume with file data and resource forks. |
| `MBR` | `.img` | MBR (Master Boot Record) partition table. |
| `Microware OS-9 RBF filesystem` | `.dsk` | Microware OS-9 RBF filesystem with declared disk geometry. |
| `minix` | `.img` | MINIX filesystem (v1, v2, v3). |
| `NTFS` | — | NTFS volume archive reader (MFT walker, read-only). |
| `prodos` | `.po`, `.dsk` | ProDOS or SOS disk volumes exposing supported filesystem members. |
| `QNX6` | — | QNX6 (QNX Neutrino "power-safe") filesystem. |
| `ROMFS` | `.romfs` | romfs - the read-only Linux filesystem, also used as an initrd payload. |
| `rsdos fs` | `.dsk` | RS-DOS disk filesystem with directory entries and granule allocation chains. |
| `SquashFS` | `.squashfs` | SquashFS filesystem archive reader (v1..v4). |
| `squashfs_sqlz` | `.squashfs` | SquashFS v2/v3 images carrying the vendor magic 'sqlz' / 'zlqs'. |
| `sufs` | `.img` | Solaris UFS1 filesystem with directories and file contents. |
| `sunvtoc` | `.img` | Sun disk label / VTOC reader (SunOS and Solaris SPARC labels, Solaris x86 VTOC). |
| `TI-99/4A DSK filesystem` | `.dsk` | TI-99/4A filesystem with supported single- and double-sided geometries. |
| `UBI` | `.ubi` | UBI (Unsorted Block Images) volume. |
| `UBIFS` | `.ubifs` | UBIFS is the filesystem that normally lives inside a UBI volume. |
| `UDF` | `.udf` | UDF (ECMA-167 / OSTA UDF) filesystem archive. |
| `ufs2` | `.img` | UFS2 (FreeBSD / NetBSD FFSv2) filesystem. |
| `Xbox FATX filesystem` | — | Xbox FATX filesystem image with directories and file data. |
| `xbox xdvdfs` | `.iso` | Xbox XDVDFS images exposing supported stored files from flat root directories. |
| `YAFFS` | `.yaffs` | YAFFS1 / YAFFS2 flash filesystem. |

## Firmware and hardware (49)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `Android boot image` | `.img` | Android boot image containing kernel, ramdisk and component regions. |
| `android dtbo` | `.dtbo`, `.img` | Android DTBO version-zero tables containing stored device-tree overlay entries. |
| `android vbmeta` | `.img` | Android Verified Boot metadata exposing authentication fields and descriptors without verification. |
| `android vendor boot` | `.img` | Android vendor boot versions three or four containers exposing firmware components. |
| `Arcadyan obfuscated LZMA` | `.bin` | Offset of the four signature bytes inside the obfuscated image. |
| `AUTEL` | `.bin` | The obfuscation table repeats every this many payload bytes. |
| `BIN firmware header` | `.bin` | U2ND BINHDR firmware wrapper containing embedded image data. |
| `cfe` | `.bin` | CFE firmware images exposing validated header and encoded body components. |
| `CHK` | `.chk` | CHK is the flash image wrapper NETGEAR wraps around an OpenWrt style kernel + rootfs pair. |
| `CSman DAT file` | `.dat` | Firmware configuration store with raw or zlib-compressed key/value entries. |
| `D-Link encfw encrypted firmware` | `.bin` | Known D-Link encrypted firmware images. |
| `D-Link encrpted_img` | `.bin` | The vendor's misspelling is the magic; do not "fix" it. |
| `D-Link MH01` | `.bin` | MH01 is the wrapper D-Link puts around recent encrypted firmware images. |
| `D-Link SHRS` | `.bin` | D-Link SHRS encrypted firmware container. |
| `D-Link TLV firmware` | `.bin` | This is the header D-Link puts on the newer (post-SEAMA) images for its consumer routers and cameras. |
| `d_link_alpha_encimg_v2` | `.bin` | D-Link/Alpha Networks firmware wrapper with AES-encrypted payload. |
| `d_link_fpkg_cpkg` | `.bin` | D-Link FPKG / CPKG firmware package. |
| `Dahua ZIP firmware` | `.bin` | Dahua firmware container carrying ZIP archive data and firmware metadata. |
| `Device Tree Blob` | `.dtb` | Flattened Device Tree (DTB / FDT). |
| `DKBS` | `.bin` | Byte offset of the "_dkbs_" literal inside the header. |
| `DLKE` | `.bin` | D-Link DLKE signed-and-encrypted firmware wrapper. |
| `DLOB` | `.bin` | "DLOB" is the name binwalk gives to the two-header arrangement D-Link ships on its SEAMA based routers. |
| `DMS swapped firmware` | `.bin` | Byte-swapped DMS firmware image exposing validated encoded structural components. |
| `eCos kernel` | `.bin` | eCos MIPS kernel image, found by its exception handler. |
| `espressif image` | `.bin` | ESP32 firmware images validating segments and XOR checksums without execution. |
| `htc_nbh_rom_image` | `.nbh` | HTC NBH (signed ROM update). |
| `Intel HEX image` | `.hex`, `.ihex` | Intel HEX records encoding addressed firmware bytes and checksums. |
| `JBOOT` | `.bin` | JBOOT firmware headers: SCH2, STAG and ARM. |
| `jedec fuse` | `.jed` | JEDEC fuse streams exporting decoded fuse bits and checked checksums. |
| `Matter OTA image` | `.ota` | Matter OTA software image container. |
| `Motorola S-record` | `.srec` | Motorola S-record (SREC) text image. |
| `PACKIMG` | `.bin` | PACKIMG is the thinnest wrapper of the five router containers handled here. |
| `pchrom` | `.rom` | PC firmware images exposing validated Intel flash descriptor regions. |
| `QNAP NAS firmware` | `.img` | QNAP NAS (QTS) firmware image. |
| `QNXBASE` | `.ifs` | QNX Neutrino boot image with a compressed image filesystem. |
| `ROMPAQ` | `.rom` | Compaq ROMPAQ image containing stored or DCL-compressed firmware. |
| `RTK firmware header` | `.bin` | Realtek RTK firmware wrapper containing embedded image data. |
| `SEAMA` | `.seama` | SEAMA (Seattle Image Archive) firmware. |
| `TP-Link firmware` | `.bin` | TP-Link ships two unrelated firmware wrappers under the same brand, and binwalk treats them as two signatures. |
| `TRX` | `.trx` | Broadcom/OpenWrt TRX firmware container holding component partitions. |
| `U-Boot environment` | `.env` | The CRC32 field, always present. |
| `U-Boot uImage` | `.uimg` | The legacy U-Boot image is a fixed 64-byte header followed by its payload. |
| `UEFI capsule` | `.cap` | A capsule is the container the UEFI firmware update mechanism takes its payload in. |
| `UEFI firmware volume` | `.fv` | A firmware volume is the container a PI-conformant platform stores its boot firmware in. |
| `uf2` | `.uf2` | UF2 firmware containers carrying addressed binary blocks and family metadata. |
| `VxWorks symbol table` | `.bin` | VxWorks symbol table locator and enumerator. |
| `Windows CE binary image` | `.bin` | Windows CE ROM image (.bin). |
| `xiaomi_hdr1` | `.bin` | Xiaomi "HDR1" router firmware container. |
| `xiaomi_hdr2` | `.bin` | Xiaomi "HDR2" router firmware container. |

## Executables and bytecode (41)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `AMIGAHUNK` | — | Amiga executable containing hunk-structured code, data and relocation records. |
| `ATARIST` | `.prg`, `.tos`, `.ttp` | Atari ST GEMDOS executable with text, data and relocation information. |
| `COM` | `.com` | Load address of the image: the byte right after the 256-byte PSP. |
| `CopyQMOverlay` | `.exe` | CopyQM DOS tool overlay containing Huffman-compressed help screens. |
| `DEX` | `.dex` | Android Dalvik executable containing bytecode and typed data tables. |
| `DOS16M` | `.exe` | DOS/16M and DOS/4G extender image readers. |
| `DOS4G` | `.exe` | DOS/4G protected-mode executable structures for DOS applications. |
| `dotnet metadata` | `.pdb` | Standalone CLI metadata roots exposing encoded streams, including portable PDB metadata. |
| `dxbc` | `.cso` | DirectX shader container exposing encoded bytecode and metadata chunks. |
| `ELF32` | `.elf`, `.o`, `.so` | 32-bit ELF executable, object and shared-library structures. |
| `ELF64` | `.elf`, `.o`, `.so` | 64-bit ELF executable, object and shared-library structures. |
| `erlang beam` | `.beam` | Erlang BEAM containers exposing validated uncompressed chunks and atom tables. |
| `idtech qvm` | `.qvm` | Quake QVM version-one bytecode containers exposing code and initialized data. |
| `java class` | `.class` | Java class files exposing validated constant pools, members and encoded attributes. |
| `LE` | `.exe` | Linear Executable with object, page and relocation records. |
| `linux btf` | `.btf` | Little-endian BTF1 type metadata exporting descriptors and string pools. |
| `linuxarm64` | — | ARM64 Linux kernel images exposing validated headers and stored image components. |
| `linuxboot` | — | Linux boot protocol images preserving encoded protected-mode kernel components. |
| `linuxzimage` | — | Linux compressed kernel images exposing encoded structural components. |
| `llvm bitcode wrapper` | `.bc` | LLVM version-zero bitcode wrappers exposing the declared raw bitcode stream. |
| `lua bytecode51` | `.luac` | Lua version-5.1 bytecode exposing checked little-endian prototypes without execution. |
| `LX` | `.exe` | OS2 Linear Executable with page-based program structures. |
| `MACH-O32` | — | 32-bit Mach-O executable structures and load commands. |
| `MACH-O64` | — | 64-bit Mach-O executable structures and load commands. |
| `MACHOFAT` | — | Universal Mach-O binary containing multiple executable architecture slices. |
| `MINIDUMP` | `.dmp` | Windows crash dump containing a directory of stored diagnostic streams. |
| `MSDOS` | `.exe` | MS-DOS MZ executable with a DOS program header. |
| `mub` | — | Mach-O universal binary containing multiple architecture slices. |
| `NE` | `.exe` | Windows/OS2 New Executable with segmented program structures. |
| `nintendo 3dsx` | `.3dsx` | Nintendo 3DSX version-zero executables exposing encoded sections and relocation tables. |
| `nintendo bfsha` | `.bfsha` | Wii U FSHA version-two archives exposing stored vertex and pixel shader programs. |
| `nintendo dol` | `.dol` | Nintendo DOL executables exposing stored text, data and declared BSS metadata. |
| `PE32` | `.exe`, `.dll`, `.sys` | 32-bit Windows Portable Executable headers, sections and resources. |
| `PE64` | `.exe`, `.dll`, `.sys` | 64-bit Windows Portable Executable headers, sections and resources. |
| `sony psx exe` | `.exe` | PlayStation executables exposing sector-aligned stored code and data sections. |
| `spirv` | `.spv` | SPIR-V shader modules exposing framed encoded instructions without semantic execution. |
| `SSM` | `.ssm` | Pegasus/Accusoft PICTools opcode module and stored components. |
| `vtech vz` | `.vz` | VTech VZF0/VZF1 program snapshots containing BASIC or machine-code payloads. |
| `wasm` | `.wasm` | WebAssembly core version-one modules exposing framed encoded sections without execution. |
| `Xamarin compressed assembly (XALZ)` | `.dll` | Xamarin Android assembly wrapped in an LZ4-compressed XALZ container. |
| `xbox xbe` | `.xbe` | Original Xbox executable containers exposing stored raw code and data sections. |

## Images and graphics (173)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `ac3d model` | `.ac` | AC3Db text models with materials, transforms, and indexed UV surfaces. |
| `adobe acb` | `.acb` | Adobe Color Book v1 palettes preserving typed color records. |
| `adobe aco` | `.aco` | Adobe ACO palettes exposing matching version-one and version-two color records. |
| `adobe act` | `.act` | Adobe Color Tables containing RGB256 palettes and optional transparency metadata. |
| `adobe acv` | `.acv` | Adobe curve v1/v4 files with counted sorted control points. |
| `adobe ase` | `.ase` | Adobe ASE palettes exposing validated color swatches and balanced groups. |
| `alias pix` | `.pix` | Alias PIX8/24-bit images containing complete row-RLE packets. |
| `amiga diskobject` | `.info` | Classic Amiga DiskObject v1 icons exporting planar imagery and tool metadata. |
| `apple pict` | `.pict`, `.pct` | QuickDraw PICTv2 bitmap subset decoding RGB32 PackBits rows. |
| `aseprite` | `.aseprite`, `.ase` | Aseprite sprite files exposing validated frames, layers and encoded cel data. |
| `astc texture` | `.astc` | ASTC 2D textures preserving complete encoded compressed block arrays. |
| `autodesk 3ds` | `.3ds` | 3DS static triangular meshes exposing vertices, faces and optional texture coordinates. |
| `autodesk ase` | `.ase` | Autodesk ASE200 static triangle meshes with checked materials and transforms. |
| `autodesk fbx` | `.fbx` | Binary FBX versions 7400 or 7500 exposing checked node and property components. |
| `avs image` | `.avs` | AVS X images containing exact big-endian geometry and ARGB8 raster. |
| `basis texture` | `.basis` | Basis v16-19 ETC1S/UASTC 2D textures preserving encoded mip slices. |
| `blender blend` | `.blend` | Uncompressed Blender files exposing bounded encoded datablocks and SDNA metadata. |
| `blitz3d b3d` | `.b3d` | Blitz3D version-one static models exposing bounded mesh and material components. |
| `bmp` | `.bmp` | Windows bitmap images exposing encoded headers, palettes and pixel components. |
| `bpg image` | `.bpg` | BPG still images preserving reduced HEVC headers and framed encoded pictures. |
| `bvh motion` | `.bvh` | Biovision BVH motion data with single-root hierarchies and complete frames. |
| `cal3d skeleton` | `.csf` | Cal3D CSF700 skeletons containing checked reciprocal bone hierarchies and transforms. |
| `cineon` | `.cin` | Cineon images exposing film image metadata and stored pixel components. |
| `collada dae` | `.dae` | COLLADA1.4.1 static geometry/scenes with checked indexed triangles and local references. |
| `dds` | `.dds` | DDS texture containers preserving supported encoded surfaces and mip levels. |
| `dec sixel` | `.six`, `.sixel` | DEC SIXEL RGB images with bounded commands and decoded rasters. |
| `directx x` | `.x` | DirectX X text0303 meshes with checked materials and skin-weight records. |
| `dpx` | `.dpx` | DPX images exposing validated image descriptors and stored pixel components. |
| `ea_fsh` | `.fsh` | Electronic Arts FSH/SHPI shape pack containing image components. |
| `ELM` | `.elm` | Microsoft theme ELM bundle containing stored resource files. |
| `emf` | `.emf` | Enhanced metafiles exposing a validated subset of geometry and state records. |
| `farbfeld` | `.ff`, `.farbfeld` | Farbfeld images exposing dimensions and stored sixteen-bit RGBA raster bytes. |
| `font afm` | `.afm` | Adobe AFM3/4.1 font metrics with checked kerning and composite references. |
| `font bdf` | `.bdf` | BDF2.1/2.2 horizontal bitmap fonts exporting glyphs and metadata. |
| `font bmfont` | `.fnt` | Binary BMFont3 font descriptors with atlas and kerning tables. |
| `font gem fnt` | `.fnt` | Classic GEM/GDOS bitmap fonts with checked metrics and raster tables. |
| `font pcf` | `.pcf` | X11 PCF bitmap fonts exporting typed glyph and metrics tables. |
| `font psf` | `.psf` | PSF1/PSF2 console bitmap fonts with optional Unicode mappings. |
| `font type1 pfb` | `.pfb` | Type1 PFB fonts preserving framed ASCII and encrypted program segments. |
| `font windows fnt` | `.fnt` | Windows FNT2/3 raster fonts exporting standalone glyph bitmaps. |
| `fontforge sfd` | `.sfd` | FontForge SFD1.0 outline fonts with counted checked glyph contours. |
| `fujifilm raf` | `.raf` | Fujifilm RAF images exposing indexed metadata, JPEG previews and encoded sensor components. |
| `gif` | `.gif` | GIF images exposing encoded frames, palettes and extension blocks. |
| `gimp gbr` | `.gbr` | GIMP version-two brushes exposing stored grayscale or RGBA pixels. |
| `gimp ggr` | `.ggr` | GIMP GGR gradients containing complete ordered finite color segments. |
| `gimp gih` | `.gih` | GIMP image hoses supporting one-dimensional sequences of encoded brush components. |
| `gimp gpl` | `.gpl` | GIMP GPL palettes containing named RGB8 color rows and metadata. |
| `gimp pat` | `.pat` | GIMP version-one patterns exposing stored one-channel through four-channel pixels. |
| `gimp xcf` | `.xcf` | GIMP XCF0-3 8-bit layers/channels with stored or RLE tiles. |
| `glb` | `.glb` | GLB version-two assets exposing validated JSON and encoded binary chunks. |
| `godot ctex` | `.ctex` | Godot version-four CTEX textures supporting stored uncompressed raw mip levels. |
| `goldsrc_bsp` | `.bsp` | GoldSrc Half-Life BSP map with exported texture components. |
| `grub pff2` | `.pf2` | GRUB PFF2 fonts containing sorted Unicode indexes and uncompressed glyph bitmaps. |
| `gts surface` | `.gts` | GNU GTS ASCII surfaces with checked vertex, edge, and triangle tables. |
| `hpgl plot` | `.hpgl`, `.plt` | HPGL vector-command subset with bounded drawing operands and labels. |
| `icc` | `.icc`, `.icm` | ICC version-two or version-four profiles exposing validated color metadata tags. |
| `icns` | `.icns` | Macintosh icon containers preserving encoded image elements and mask components. |
| `ico` | `.ico` | Windows icon containers exposing encoded image entries and mask components. |
| `idtech iqm` | `.iqm` | IQM version-two static meshes exposing supported geometry arrays and triangle tables. |
| `idtech md2` | `.md2` | Quake MD2 version-eight models exposing encoded geometry and animation components. |
| `idtech md3` | `.md3` | Quake MD3 version-fifteen models exposing encoded frames, tags and surfaces. |
| `idtech md5anim` | `.md5anim` | MD5Version10 skeletal animation text with complete hierarchy and frame grammar. |
| `idtech mdl` | `.mdl` | Quake MDL version-six models supporting single skins and animation frames. |
| `iff ilbm` | `.ilbm` | IFF ILBM images preserving validated encoded bitmap chunks and palette data. |
| `imagemagick miff` | `.miff` | Uncompressed MIFF1.0 direct-color images with checked descriptors and raster rows. |
| `imagemagick mvg` | `.mvg` | ImageMagick MVG drawing subset with bounded shapes and SVG path commands. |
| `iridas cube lut` | `.cube` | IRIDAS CUBE 1D/3D color tables with finite domains and samples. |
| `jasc palette` | `.pal` | JASC-PAL0100 palettes containing exact counted RGB8 color rows. |
| `jbig2` | `.jb2`, `.jbig2` | Standalone sequential JBIG2 images exposing explicit-length encoded segment components. |
| `jpeg` | `.jpg`, `.jpeg`, `.jpe` | JPEG images exposing encoded markers, metadata and compressed scan data. |
| `jpeg2000 jp2` | `.jp2`, `.j2k`, `.j2c`, `.jpc` | JP2 images or raw JPEG2000 codestreams exposing encoded structural components. |
| `jpeg2000 pgx` | `.pgx` | PGX grayscale planes containing bounded signed/unsigned 1-16-bit samples. |
| `khoros viff` | `.viff`, `.xv` | Khoros VIFFv1 images with typed multiband planes and optional colormaps. |
| `ktx` | `.ktx` | KTX1 texture containers preserving encoded mip levels and key-value metadata. |
| `ktx2` | `.ktx2` | KTX2 texture containers supporting encoded mip levels without supercompression. |
| `lightwave lwo2` | `.lwo` | LightWave LWO2 single-layer meshes preserving checked polygon and tag components. |
| `lightwave mdd` | `.mdd` | LightWave MDD vertex caches exposing validated stored frame times and coordinates. |
| `lightwave scene` | `.lws` | LightWave LWSC2 scenes exporting typed settings and counted motion channels. |
| `lut cinespace csp` | `.csp` | Cinespace CSP100 lookup tables with pre-LUT curves and finite samples. |
| `lut spi1d` | `.spi1d` | SPI1D v1 lookup curves with finite domains and counted samples. |
| `lut spi3d` | `.spi3d` | SPI3D1 RGB lookup tables containing complete ordered three-axis grids. |
| `magicavoxel vox` | `.vox` | MagicaVoxel version-150 scenes exposing stored voxel models and palette components. |
| `metasequoia mqo` | `.mqo` | Metasequoia MQO1.0/1.1 ASCII meshes with materials and typed scene metadata. |
| `milkshape ms3d` | `.ms3d` | MilkShape3D version-four static models excluding joints and optional extension blocks. |
| `minolta mrw` | `.mrw` | Minolta MRW images exposing sensor descriptors and stored packed raw pixel data. |
| `mmd pmx` | `.pmx` | PMX2.0 models with checked geometry, bones, materials, and local references. |
| `mng animation` | `.mng` | Simple MNG1 PNG-frame animations with checked chunk ordering and CRC32. |
| `motif uil` | `.uil` | Motif UIL static icons exporting checked color tables and decoded RGBA8 pixels. |
| `mtv image` | `.mtv` | MTV raytracing images containing ASCII dimensions and exact RGB24 rows. |
| `nasa vicar` | `.vic`, `.vicar` | NASA VICAR images with counted labels and typed BSQ/BIL/BIP samples. |
| `netpbm pfm` | `.pfm` | Portable FloatMap images containing finite floating-point grayscale or RGB rasters. |
| `nintendo bcfnt` | `.bcfnt` | Nintendo 3DS CFNT fonts exposing encoded glyph tables and texture sheets. |
| `nintendo bch` | `.bch` | Nintendo 3DS BCH graphics containers exposing encoded sections and relocation entries. |
| `nintendo bclyt` | `.bclyt` | Nintendo CLYT layouts exposing bounded pane, group and resource sections. |
| `nintendo bflyt` | `.bflyt` | Nintendo FLYT layouts exposing bounded pane, group and resource sections. |
| `nintendo bfnt` | `.bffnt` | Wii U FFNT fonts exposing encoded glyph tables and texture sheets. |
| `nintendo bntx` | `.bntx` | Nintendo BNTX containers supporting single-layer two-dimensional NX textures and mip slices. |
| `nintendo brlan` | `.brlan` | Nintendo RLAN version-eight containers supporting encoded RLPA Hermite animation tracks. |
| `nintendo brlyt` | `.brlyt` | Nintendo RLYT version-eight layouts exposing bounded pane hierarchies and resources. |
| `nintendo cgfx` | `.bcres`, `.bcmdl`, `.bctex` | Nintendo 3DS CGFX containers exposing encoded DATA and optional IMAG blocks. |
| `nintendo j3d bmd` | `.bmd` | Nintendo J3D2 BMD3 models exposing eight ordered encoded resource sections. |
| `nintendo j3d btk` | `.btk` | Nintendo J3D1 BTK1 animations exposing encoded texture-matrix animation components. |
| `nintendo tpl` | `.tpl` | Nintendo TPL textures preserving encoded GX texture and palette components. |
| `nokia ota bitmap` | `.otb` | Nokia OTA depth1 bitmaps with checked dimensions and packed rows. |
| `off mesh` | `.off` | ASCII OFF polygon meshes with bounded indexes and optional face colors. |
| `ogre mesh` | `.mesh` | Ogre version-1.100 static meshes supporting position-only geometry and triangle indices. |
| `ogre skeleton` | `.skeleton` | OGRE v1.10/v1.80 skeletons with checked bones, hierarchy, and animation chunks. |
| `openctm mesh` | `.ctm` | OpenCTM v5 RAW triangular meshes with stored attribute arrays. |
| `openexr` | `.exr` | OpenEXR version-two single-part scanline images preserving encoded chunks and attributes. |
| `opengex model` | `.ogex` | OpenGEX static geometry with checked objects, materials, transforms, and triangles. |
| `openusd usda` | `.usda` | OpenUSD USDA1.0 static meshes/transforms with checked scene metadata and references. |
| `paintshop psp` | `.psp` | PaintShop Pro3 raster layers with stored or RLE channel planes. |
| `palm bitmap` | `.palm` | PalmOS v0-v2 indexed bitmaps with stored or byte-RLE rasters. |
| `pcx` | `.pcx` | PCX images preserving encoded raster data, headers and palette components. |
| `PCXLib` | `.pcl` | Genus PCX image-library container with indexed image members. |
| `photoshop abr` | `.abr` | Photoshop ABR1/2 sampled 8-bit brushes with stored or PackBits pixels. |
| `photoshop pat` | `.pat` | Photoshop PAT1 sampled patterns with stored or PackBits 8-bit planes. |
| `photoshop psd` | `.psd`, `.psb` | Photoshop PSD or PSB images preserving encoded resources, layers and pixels. |
| `pkm texture` | `.pkm` | PKM1/PKM2 ETC/EAC textures preserving supported encoded block arrays. |
| `png` | `.png` | PNG images exposing checksum-validated encoded chunks without pixel decoding. |
| `pnm` | `.pnm`, `.pbm`, `.pgm`, `.ppm`, `.pam` | Netpbm images preserving validated headers and ASCII or binary raster arrays. |
| `polygon ply` | `.ply` | Binary PLY version-one geometry preserving original scalar and list-property elements. |
| `processing vlw` | `.vlw` | Processing VLW11 fonts exporting grayscale glyph bitmaps and metrics. |
| `pvr` | `.pvr` | PVR3 textures preserving supported encoded mip groups and metadata. |
| `qoi` | `.qoi` | QOI images exposing validated descriptors and encoded pixel opcode streams. |
| `qt qpicture` | `.qpic` | Qt QPicture v9 drawing streams with checked bounded painter commands. |
| `quake md5mesh` | `.md5mesh` | Quake MD5 version-ten skeletal meshes exposing checked text geometry and weights. |
| `quake sprite` | `.spr` | Quake IDSP version-one sprites preserving indexed frames and group intervals. |
| `qubicle qb` | `.qb` | Qubicle QB1.1 voxel matrices with stored or slice-RLE color arrays. |
| `radiance hdr` | `.hdr`, `.pic` | Radiance HDR images preserving encoded RGBE pixel rows and descriptors. |
| `renderman rib` | `.rib` | RenderMan ASCII static commands with bounded geometry and balanced scopes. |
| `risc_os_sprite` | — | RISC OS (Acorn) sprite file. |
| `scanalytics iplab` | `.ipl` | Scanalytics IPLab100f image stacks with checked channel/Z/T sample planes. |
| `sega gvr` | `.gvr` | Sega GVR textures preserving encoded pixel data and optional palette components. |
| `sega pvr2` | `.pvr` | Dreamcast PVRT textures preserving supported encoded direct-color pixel data. |
| `sfnt` | `.ttf`, `.otf` | TrueType or OpenType fonts exposing directory tables with verified checksums. |
| `sfnt collection` | `.ttc`, `.otc` | TrueType or OpenType collections exposing shared tables with verified checksums. |
| `sgi rgb` | `.rgb`, `.rgba`, `.sgi`, `.bw` | SGI RGB images preserving stored or RLE-encoded channels and descriptors. |
| `sigma x3f` | `.x3f` | Sigma X3F images exposing validated directories and encoded image or metadata sections. |
| `softimage pic` | `.pic` | Softimage PIC1.0/1.6 images preserving stored or RLE RGB/RGBA scanlines. |
| `sony tim` | `.tim` | PlayStation TIM version-zero images preserving encoded palettes and pixel data. |
| `sony tim2` | `.tm2` | PlayStation 2 TIM2 images preserving bounded encoded picture and palette components. |
| `spring s3o` | `.s3o` | Spring S3O version-zero models exposing bounded indexed triangle or quad pieces. |
| `sun raster` | `.ras`, `.sun` | Sun raster images preserving colormaps and encoded raw or byte-compressed pixels. |
| `svg` | `.svg` | SVG documents exposing validated XML markup and vector image components. |
| `terragen ter` | `.ter` | Classic Terragen terrain containing checked signed16 heightfields and geometry metadata. |
| `tex gf` | `.gf` | TeX GF131 bitmap-font programs with checked glyph and postamble framing. |
| `tex pk` | `.pk` | TeX PK89 packed bitmap fonts exporting encoded glyph packets. |
| `tex tfm` | `.tfm` | TeX TFM font metrics with checked character and table references. |
| `tex vf` | `.vf` | TeX VF202 virtual fonts preserving checked DVI character programs. |
| `tga` | `.tga` | TGA2 images supporting encoded raw or RLE rasters with canonical footers. |
| `tiff` | `.tif`, `.tiff` | Classic TIFF or BigTIFF images exposing encoded strips, tiles and metadata. |
| `torque dts` | `.dts` | Torque DTS version-24 shapes supporting static nodes without mesh objects. |
| `ufo glif` | `.glif` | UFO GLIF2 glyphs with checked contours, components, and Unicode metadata. |
| `unifont hex` | `.hex` | GNU Unifont HEX glyphs containing sorted monochrome bitmap records. |
| `unreal psa` | `.psa` | Classic ActorX PSA animations exposing encoded bone, sequence and transform keys. |
| `unreal psk` | `.psk` | Classic ActorX PSK models exposing ordered geometry, skeleton and weight tables. |
| `utah rle` | `.rle` | Utah RLE images preserving validated encoded scanlines and color metadata. |
| `valve studio mdl` | `.mdl` | GoldSrc studio version-ten texture companions exposing encoded indexed textures. |
| `valve vtf` | `.vtf` | Valve VTF versions 7.0–7.2 textures preserving encoded surfaces and thumbnails. |
| `vrml scene` | `.wrl` | VRML97 static scene subset with checked geometry, materials, and transforms. |
| `wavefront obj` | `.obj` | Wavefront OBJ polygon meshes with checked finite vertices and face references. |
| `wbmp image` | `.wbmp` | WBMP type0 images containing exact packed one-bit raster rows. |
| `Windows animated cursor (ANI)` | `.ani` | Windows RIFF/ACON animated cursor frames. |
| `wmf` | `.wmf` | Placeable Windows metafiles exposing bounded geometry, state and drawing records. |
| `woff` | `.woff` | WOFF version-one fonts supporting stored or zlib-compressed checked tables. |
| `woff2` | `.woff2` | WOFF2 fonts supporting null-transformed tables and encoded metadata components. |
| `wordperfect wpg` | `.wpg` | WordPerfect WPGv1 bitmap subset decoding checked packed raster RLE. |
| `x11 xbm` | `.xbm` | X11 XBM byte-array icons with checked dimensions and decoded row bytes. |
| `xcursor` | `.xcursor` | Xcursor files exposing bounded image descriptors, ARGB pixels and comments. |
| `xfig` | `.fig` | XFig version-3.2 drawings supporting complete ellipse and arrow-free polyline objects. |
| `xpm` | `.xpm` | XPM text images exposing validated color tables and indexed pixel rows. |
| `xwd` | `.xwd` | X Window dump images exposing descriptors, colormaps and stored pixel bytes. |

## Audio and music (132)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `Abylight 3DS STRM audio` | `.strm` | Abylight 3DS wrapper containing a complete ADTS AAC stream. |
| `adlib amd` | `.amd` | AMUSIC AMD/XMS modules preserving stored or packed track components. |
| `adlib bam` | `.bam` | CBMF AdLib music with bounded command runs and OPL instruments. |
| `adlib bmf` | `.bmf` | Standalone BMF1.1 music files preserving instruments and terminated channel streams. |
| `adlib bnk` | `.bnk` | AdLib BNK1.0 instrument banks with checked names and OPL records. |
| `adlib d00` | `.d00` | EdLib D00v4 modules with bounded orders, sequences, and OPL instruments. |
| `adlib dfm` | `.dfm` | Digital-FM major0 modules preserving typed instruments and pattern components. |
| `adlib hsc` | `.hsc` | HSC modules with 128 instruments and complete nine-channel pattern tables. |
| `adlib jbm` | `.jbm` | JBMv2 music preserving checked order, sequence, voice, and instrument tables. |
| `adlib lds` | `.lds` | Loudness LDS modules with 46-byte MIDI patches and bounded patterns. |
| `adlib mkj` | `.mkj` | MKJamz1.0 music with register instruments and counted channel-event grids. |
| `adlib mtr` | `.mtr` | MTRACK NCv2 music containing typed instruments and counted pattern events. |
| `adlib rad` | `.rad` | Reality Adlib Tracker1.0 modules with checked instruments and packed patterns. |
| `adlib rol` | `.rol` | AdLib Visual Composer ROL0.4 music with typed voice events. |
| `adlib sa2` | `.sa2` | Surprise! AdLib Tracker SA2v9 modules with checked instruments and tracks. |
| `adlib sop` | `.sop` | SOP1.0/2.0 music containing counted instruments and typed event tracks. |
| `adlib xsm` | `.xsm` | XSM music containing nine instruments and counted bounded note streams. |
| `aiff` | `.aiff`, `.aif`, `.aifc` | AIFF or AIFC containers preserving metadata and encoded sound data. |
| `amiga ahx` | `.ahx`, `.thx` | AHX/THX v0-v1 four-channel modules preserving instruments and synthesis commands. |
| `amos music bank` | `.abk` | AMOS Music banks exporting one four-channel song and stored samples. |
| `AP4` | `.ap4` | Hardware reading-pen container with indexed MPEG audio members. |
| `asylum amf` | `.amf` | Asylum v1.0 eight-channel modules with unpacked patterns and PCM8 samples. |
| `atari sap` | `.sap` | Atari SAP TYPE B music with bounded XEX load segments. |
| `audio aac adts` | `.aac` | MPEG4 AAC-LC ADTS streams with unprotected single-block frames. |
| `audio adx` | `.adx` | Unencrypted CRI ADX version-three streams preserving framed encoded ADPCM audio. |
| `audio ast` | `.ast` | Nintendo AST streams supporting bounded big-endian PCM sixteen-bit audio blocks. |
| `audio au` | `.au` | AU audio containers supporting explicit-length PCM, floating-point and companded samples. |
| `audio dff` | `.dff` | DSDIFF version-one containers supporting uncompressed encoded DSD audio chunks. |
| `audio dolby ac3` | `.ac3` | Classic AC3 frames with verified independent CRC16 regions. |
| `audio dsf` | `.dsf` | DSF version-one containers exposing bounded planar encoded DSD audio blocks. |
| `audio hca` | `.hca` | Unencrypted CRI HCA version-two streams preserving checksum-validated encoded audio frames. |
| `audio monkeys ape` | `.ape` | Monkey's Audio v3980/v3990 files exporting encoded frames and metadata. |
| `audio mpeg mp3` | `.mp3` | Unprotected MPEG1 Layer III frames with bounded side information. |
| `audio wave64` | `.w64` | Sony Wave64 containers exposing supported PCM samples and checked metadata chunks. |
| `audio wavpack` | `.wv` | WavPack lossless integer streams supporting validated mono or stereo block components. |
| `caf` | `.caf` | CAF version-one audio containers exposing metadata and encoded sound bytes. |
| `ceres msc` | `.msc` | Ceres MSCplay v0 music preserving structurally checked compressed command blocks. |
| `creative cmf` | `.cmf` | Creative CMF1.0/1.1 music containing instrument tables and framed MIDI events. |
| `creative voc` | `.voc` | Creative VOC streams preserving complete supported PCM and control blocks. |
| `CRI AHX` | `.ahx` | CRI AHX audio container preserving encoded or encrypted payloads. |
| `cri awb` | `.awb` | CRI AWB audio banks containing indexed encoded sound streams. |
| `cudfm cff` | `.cff` | Stored CUD-FM/BoomTracker CFFv1 modules with fixed instruments and patterns. |
| `dosbox dro` | `.dro` | DOSBox DRO2.0 uncompressed register logs with checked maps and duration. |
| `EA EXA/SCHl audio` | `.exa` | Electronic Arts SCHl audio stream exporting original encoded blocks. |
| `Ensoniq PAF audio` | `.paf` | Ensoniq PAF audio preserving stored PCM or packed 24-bit samples. |
| `faust fmc` | `.fmc` | Faust Music Creator modules containing counted channel-major patterns and instruments. |
| `flac` | `.flac` | Native FLAC streams preserving metadata and checksum-validated encoded audio frames. |
| `fmod_sample_bank` | `.fsb` | An FMOD Sample Bank: a table of sample headers followed by the raw (codec-specific) data of every sample. |
| `gameboy gbs` | `.gbs` | Game Boy GBS v1 sound programs exported without emulation. |
| `hes sound` | `.hes` | HES v0 sound files exporting bounded DATA program chunks. |
| `HMI MIDI song` | `.hmi` | HMI song container exporting original headers and track regions. |
| `iff 8svx` | `.8svx`, `.iff` | Amiga IFF 8SVX containers supporting uncompressed mono audio and metadata. |
| `implay music` | `.mus`, `.ims` | IMPLAY1.0 music containing counted MIDI-like events and optional timbre names. |
| `Interplay ACM` | `.acm` | Interplay ACM container exporting encoded subband-audio data. |
| `ircam sdif` | `.sdif` | SDIF3 audio analysis files containing known typed numeric matrices. |
| `ken ksm` | `.ksm` | Ken Silverman KSM music with timestamp-sorted bit-packed note tables. |
| `LEGO Racers ALP/TUN audio` | `.alp`, `.tun` | LEGO Racers ALP/TUN container preserving encoded IMA-ADPCM audio. |
| `mad tracker` | `.mad` | MAD+ MadTracker modules with nine instruments and counted nine-channel patterns. |
| `microsoft xsb` | `.xsb` | Microsoft XSB sound banks exposing bounded encoded cue and sound metadata. |
| `microsoft xwb` | `.xwb` | Microsoft XWB wave banks exposing metadata and encoded sound entries. |
| `midi` | `.mid`, `.midi` | MIDI files exposing track chunks and encoded musical event streams. |
| `nintendo bcsar` | `.bcsar` | Nintendo BCSAR sound archives preserving encoded string, information and file blocks. |
| `nintendo bcstm` | `.bcstm` | Nintendo BCSTM audio containers preserving encoded INFO, SEEK and DATA sections. |
| `nintendo bcwav` | `.bcwav` | Nintendo CWAV audio containers supporting one-channel or two-channel PCM sample bytes. |
| `nintendo bfsar` | `.bfsar` | Nintendo BFSAR sound archives preserving encoded string, information and file blocks. |
| `nintendo bfstm` | `.bfstm` | Nintendo FSTM audio containers preserving encoded information, seek and data blocks. |
| `nintendo bfwav` | `.bfwav` | Nintendo FWAV audio containers supporting one-channel or two-channel PCM sample bytes. |
| `nintendo brstm` | `.brstm` | Nintendo RSTM version-one streams supporting single-block mono or stereo PCM audio. |
| `nintendo brwav` | `.brwav` | Nintendo RWAV version-1.2 containers supporting encoded multichannel PCM sample bytes. |
| `Nintendo DS STRM audio` | `.strm` | Nintendo DS STRM audio preserving original framed stream data. |
| `nintendo nsf` | `.nsf` | Nintendo NSF v1 sound programs exported without emulation. |
| `nintendo sdat` | `.sdat` | Nintendo SDAT v1 sound archives exporting encoded Nitro sound components. |
| `ogg` | `.ogg`, `.oga`, `.ogv` | Ogg containers exposing checksum-validated encoded page bodies and packet framing. |
| `Olympus DSS/DS2` | `.dss`, `.ds2` | Olympus DSS/DS2 voice container preserving encoded audio blocks. |
| `Parsec PSM 2.00 music module` | `.pmm` | MTCVTS PSM 2.00 music module with MDH/PLX/SM8 components. |
| `Portable Voice Format audio` | `.pvf` | Portable Voice Format container preserving framed audio sample data. |
| `psid sid` | `.sid` | Single-SID PSID v1/v2 and RSID v2 sound programs. |
| `rdos raw` | `.raw` | Rdos RAWADATA music preserving framed OPL commands and optional metadata tags. |
| `RIFF IMA audio` | `.strm` | RIFF IMA audio container preserving encoded ADPCM sample data. |
| `RIFX big-endian WAVE audio` | `.wav` | Big-endian RIFX WAVE container preserving encoded audio sample data. |
| `s98 log` | `.s98` | Uncompressed S98 v3 chip-register logs with complete command framing. |
| `sc68 music` | `.sc68` | SC68 v1 music containers preserving original track-data chunks. |
| `SCUMM SOU voice` | `.sou` | SCUMM SOU voice container preserving sound records and encoded samples. |
| `sega sgc` | `.sgc` | SGC v1 sound programs for SMS, Game Gear, or Coleco. |
| `sfark_compressed_soundfont` | `.sfArk` | sfArk version 2 compressed SoundFont sample-bank container. |
| `SFPack` | `.sfpack` | Compressed SoundFont 2 container reconstructing one sample-bank file. |
| `Shockwave Audio (SWA)` | `.swa` | Shockwave Audio container preserving original encoded audio payloads. |
| `snes spc` | `.spc` | SPC v0.30 sound snapshots with RAM, DSP, and optional xid6 metadata. |
| `softstar rix` | `.rix` | Softstar RIX music containing OPL instruments and framed channel events. |
| `sony psf` | `.psf` | PSF1 music wrappers preserving checksum-validated compressed program data and tags. |
| `sony vab` | `.vab` | Combined PlayStation VAB v5-7 banks preserving encoded SPU sample frames. |
| `sony vag` | `.vag` | PlayStation mono VAGp version-0x20 streams preserving encoded ADPCM audio frames. |
| `SoundFont 2` | `.sf2` | SoundFont 2 RIFF bank exporting original PCM sample data. |
| `steinberg fxb` | `.fxb`, `.fxp` | VST2 presets or banks exposing parameters and opaque plugin-state components. |
| `steinberg vst3preset` | `.vstpreset` | VST3 preset v1 containers exporting opaque plugin-state chunks. |
| `tracker 669` | `.669` | Composer 669 modules preserving eight-channel fixed patterns and stored samples. |
| `tracker amf` | `.amf` | DSMI AMF version-1.4 modules exposing bounded mapped tracks and stored samples. |
| `tracker ams` | `.ams` | Extreme's Tracker AMS version-one modules supporting stored samples and encoded patterns. |
| `tracker archimedes` | `.musx` | Archimedes MUSX modules preserving nested instruments and VIDC samples. |
| `tracker coconizer` | `.coc` | Coconizer four/eight-channel modules preserving checked pattern tables and VIDC samples. |
| `tracker dbm` | `.dbm` | DigiBooster Pro version-two modules exposing complete song, pattern and sample chunks. |
| `tracker digi` | `.digi` | DIGI Booster modules preserving complete plain or packed patterns and samples. |
| `tracker dmf` | `.dmf` | X-Tracker DMF version-eight modules exposing encoded pattern and sample chunks. |
| `tracker dsm` | `.liq` | Liquid Tracker LIQ modules preserving encoded patterns; legacy DSM catalog label. |
| `tracker dtm` | `.dtm` | Digital Tracker modules exporting original Protracker/2.04 pattern and sample chunks. |
| `tracker dtt` | `.dtt` | DesktopTracker DskT modules preserving packed events and VIDC samples. |
| `tracker emod` | `.emod` | Quadra Composer EMOD version-one modules exposing complete pattern and sample chunks. |
| `tracker far` | `.far` | Farandole Composer version-one modules exposing stored patterns and samples. |
| `tracker funk` | `.fnk` | FunkTracker Fk/Fv modules preserving typed pattern events and 8-bit samples. |
| `tracker gdm` | `.gdm` | General Digital Music version-one modules exposing bounded patterns and sample components. |
| `tracker imf` | `.imf` | Imago Orpheus IMF version-one modules exposing checked instrument and sample components. |
| `tracker it` | `.it` | Impulse Tracker sample-mode modules preserving packed patterns and uncompressed samples. |
| `tracker mdl` | `.mdl` | DigiTrakker MDL version-one modules preserving validated typed pattern and sample chunks. |
| `tracker med` | `.med` | OctaMED MMD0 or MMD1 modules supporting one song and stored mono samples. |
| `tracker megatracker` | `.mgt` | Megatracker1.1 song tables with checked packed tracks and PCM8 samples. |
| `tracker mod` | `.mod` | Four-channel ProTracker-compatible MOD files preserving original pattern and sample components. |
| `tracker mt2` | `.mt2` | MadTracker version-two modules supporting stored patterns without instrument sample data. |
| `tracker mtm` | `.mtm` | MultiTracker MTM version-one modules exposing track streams and stored samples. |
| `tracker okt` | `.okt` | Oktalyzer modules exposing complete encoded pattern, sample and metadata chunks. |
| `tracker psm` | `.psm` | Epic MASI PSM containers exposing one song with checked patterns and samples. |
| `tracker ptm` | `.ptm` | PolyTracker PTM version-two modules preserving checked patterns and sample components. |
| `tracker real` | `.rtm` | Real Tracker1.10/1.12 modules preserving packed events and delta PCM samples. |
| `tracker s3m` | `.s3m` | Scream Tracker S3M modules preserving packed patterns and stored PCM samples. |
| `tracker soundfx` | `.sfx` | SoundFX 15/31-instrument modules preserving four-channel patterns and PCM8 samples. |
| `tracker stm` | `.stm` | Scream Tracker STM version-2.21 modules exposing complete patterns and samples. |
| `tracker stx` | `.stx` | STMIK/STM2STX modules preserving packed patterns and pointer-addressed PCM8 samples. |
| `tracker ult` | `.ult` | UltraTracker version-four modules preserving RLE event streams and encoded samples. |
| `tracker xm` | `.xm` | FastTracker XM version-1.04 modules preserving packed patterns and delta-encoded samples. |
| `vgm log` | `.vgm` | VGM v1.00-1.60 register logs containing waits and raw PCM blocks. |
| `Wwise WEM audio` | `.wem` | Wwise WEM audio container preserving original encoded payload data. |
| `yamaha ym` | `.ym` | Uncompressed YM5/YM6 music logs with register data and digidrums. |
| `zx ayemul` | `.ay` | ZXAYEMUL v0-v2 sound containers exporting referenced Z80 memory blocks. |

## Video and multimedia (20)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `Adobe Director CXT` | `.cxt` | Adobe Director container exposing stored cast and sound chunks. |
| `autodesk flic` | `.fli`, `.flc` | Autodesk FLI/FLC 8-bit indexed animations exporting encoded frames. |
| `cri usm` | `.usm` | CRI USM containers preserving framed encoded audio and video chunk payloads. |
| `flash video flv` | `.flv` | Classic FLV version-one containers preserving framed encoded audio and video packets. |
| `FSS` | `.fss` | SSBOB slideshow container exposing original stored image components. |
| `GRASP` | `.gl` | GRASP GL animation library with indexed stored resource components. |
| `idtech roq` | `.roq` | RoQ video containers exporting VQ and optional DPCM chunks. |
| `interplay mve` | `.mve` | Interplay MVE containers exporting typed encoded multimedia chunks. |
| `IVF video` | `.ivf` | IVF video container exporting coded frame packets without decoding. |
| `matroska` | `.mkv`, `.mka`, `.webm` | Matroska or WebM containers exposing metadata and encoded laced media frames. |
| `mp4` | `.mp4`, `.m4a`, `.m4v`, `.mov` | MP4 or ISO BMFF containers exposing encoded leaf boxes and media data. |
| `mpeg program stream` | `.mpg`, `.mpeg` | MPEG1/2 program streams exporting framed packs and encoded PES packets. |
| `mpeg transport stream` | `.ts` | 188-byte single-program MPEG transport packets with checked PAT/PMT tables. |
| `rad bink` | `.bik` | Bink1 b/f/g/h/i containers exporting indexed encoded audio/video frames. |
| `rad smacker` | `.smk` | Smacker2/4 containers exporting encoded trees and audio/video frame packets. |
| `realmedia rm` | `.rm` | RealMedia v0 containers exporting typed metadata and encoded packets. |
| `riff` | `.riff`, `.avi`, `.wav` | RIFF containers exposing bounded chunks and encoded multimedia payloads. |
| `sony pamf` | `.pamf` | Sony PAMF containers exposing metadata and encoded multimedia stream bytes. |
| `swf` | `.swf` | Flash movie container exposing embedded encoded media and binary resources. |
| `westwood vqa` | `.vqa` | Westwood VQA v1/v2 containers exporting indexed encoded frame chunks. |

## Documents and compound files (21)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `Binder` | `.obd`, `.obt`, `.obz` | OLE2 / CFBF (Compound File Binary Format) compound files. |
| `CFBF` | `.doc`, `.xls`, `.ppt`, `.msi` | OLE Compound File container with storages and document streams. |
| `CLP` | `.clp` | Windows Clipboard file containing indexed clipboard-data formats. |
| `DBZ` | `.dbz` | Compressed Unix manual-page database with an indexed page collection. |
| `djvu` | `.djvu`, `.djv` | Single-page DjVu documents preserving encoded INFO and bounded leaf chunks. |
| `GXL` | `.gxl` | GX Library / Genus Graphics Library (.GXL) container. |
| `hxs` | `.hxs` | Microsoft Help 2 (.HxS) / Microsoft Reader (.lit) "ITOLITLS" storage. |
| `IVT` | `.ivt` | MediaView title with indexed stored or MSZIP-compressed internal files. |
| `Microsoft CHM` | `.chm` | Compiled HTML Help container holding directory entries and compressed resources. |
| `NoteTab` | `.clb`, `.otl`, `.clh` | NoteTab (Fookes Software) Clipbook Library / Outline document (.clb / .otl / .clh). |
| `openzim` | `.zim` | ZIM5/6 offline article archives with stored, XZ, or Zstandard clusters. |
| `outlook_express_dbx_mailbox` | `.dbx` | Outlook Express 5/6 DBX message store. |
| `PaperPort` | `.max` | PaperPort desktop document with a chunk tree of page images. |
| `PDF` | `.pdf` | PDF document containing objects, streams and cross-reference structures. |
| `PerFORM` | `.frp` | Delrina PerFORM/FormFlow compressed database document container. |
| `pjl` | `.pjl` | Printer Job Language text containing validated command runs and framing. |
| `PPD` | `.ppd` | Paranoid Productions PPD resource archive. |
| `STYLUS` | `.sdc` | Stylus dictionary containing an XOR-obfuscated LZSS data stream. |
| `tex dvi` | `.dvi` | TeX DVI2 page programs with checked font references and stacks. |
| `The Bat! MSB` | `.msb` | The Bat MSB mailbox containing individual message records. |
| `TNEF` | `.dat` | Microsoft Transport Neutral Encapsulation Format (winmail.dat). |

## Databases and storage (24)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `apache arrow file` | `.arrow`, `.feather` | Apache Arrow files exposing validated metadata and encoded columnar record batches. |
| `apache orc` | `.orc` | Uncompressed ORCv1 columnar files exporting encoded stripes and metadata. |
| `apache parquet` | `.parquet` | Apache Parquet files exposing validated metadata and encoded columnar data pages. |
| `btrfs_stream` | — | Btrfs send stream containing serialized filesystem change commands. |
| `cdb database` | `.cdb` | DJB CDB databases containing checked hashed key/value records. |
| `dbase dbf` | `.dbf` | dBASE databases exposing field descriptors and stored fixed-length record bytes. |
| `gdbm dump` | — | GDBM1.1 ASCII dumps decoding complete base64 key/value records. |
| `GIT OBJECT` | — | Git loose object with a zlib-compressed type, size and payload. |
| `hadoop sequencefile` | `.seq` | Uncompressed Hadoop SequenceFile6 records exporting serialized keys and values. |
| `kafka record batch` | — | Kafka magic2 uncompressed batches exporting keys, values, and record headers. |
| `leveldb log` | `.log` | LevelDB FULL WAL records containing checked WriteBatch operations and CRC32C. |
| `leveldb sstable` | `.sst`, `.ldb` | Classic LevelDB SSTables with stored checksum-checked data blocks. |
| `lmdb data` | `.mdb` | Native64 little-endian LMDB databases with checked committed page graphs. |
| `microsoft msf` | `.pdb` | Microsoft MSF7 containers reassembling user streams from 4096-byte blocks. |
| `mysql binlog` | `.binlog` | MySQL v4 binary logs supporting typed query/control events and checksums. |
| `Palm PDB` | `.pdb`, `.prc` | Palm OS database container with records or resource entries. |
| `postgres custom` | `.dump` | PostgreSQL custom1.13-1.15 uncompressed dumps with TOC and table-data blocks. |
| `redis rdb` | `.rdb` | Redis RDB6-11 snapshots exporting classic encoded values and metadata. |
| `rocksdb blob` | `.blob` | RocksDB BlobLog v1 uncompressed files exporting checksum-checked keys and values. |
| `sqlite rollback journal` | — | SQLite hot rollback journals with checked page records and checksums. |
| `sqlite wal` | `.wal` | SQLite write-ahead logs exposing checksum-validated frames without replaying database commits. |
| `sqlite3` | `.sqlite`, `.sqlite3`, `.db` | SQLite databases exposing validated header and complete raw database pages. |
| `windows evtx` | `.evtx` | EVTX3.1 event logs exporting checksum-checked encoded BinXML records. |
| `windows registry hive` | `.hive` | Closed REGF1.2-1.6 registry hives exporting allocated cells without transaction replay. |

## Structured data and serialization (38)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `amazon ion binary` | `.ion` | Ion1.0 binary values with local symbol tables and annotations. |
| `android binary xml` | `.axml`, `.xml` | Android binary XML with string pools and balanced typed chunks. |
| `android resources arsc` | `.arsc` | Android resource tables with dense entries and unstyled string pools. |
| `avro object` | `.avro` | Avro object containers supporting uncompressed blocks and validated schema metadata. |
| `binary plist` | `.plist` | Binary plist00 object tables preserving encoded objects and raw data. |
| `capnproto message` | — | Unpacked single-segment Cap'n Proto messages with checked near-pointer graphs. |
| `cbor` | `.cbor` | Self-described CBOR definite map/array roots exporting encoded entries. |
| `cri utf` | `.utf` | CRI UTF tables exposing supported scalar, string and binary-reference values. |
| `erlang external term` | `.etf` | Erlang External Term131 stored values without compressed or function terms. |
| `ethereum rlp` | — | Canonical Ethereum RLP long root lists preserving typed framing and leaves. |
| `java serialization` | `.ser` | Java serialization protocol5 strings and primitive/String arrays without instantiation. |
| `jks keystore` | `.jks` | JKSv2 keystores supporting empty store passwords and preserved protected keys. |
| `jose jws` | `.jwt` | Compact HS256 JWS records exporting decoded header/payload and unverified signatures. |
| `kerberos ccache` | — | Kerberos credential cache v4 files exporting typed principals and encoded tickets. |
| `kerberos keytab` | `.keytab` | MIT FILE keytab2 credentials containing bounded principal and key records. |
| `larian lsf` | `.lsf` | Larian LSOF version-two resources exposing stored string, node and attribute streams. |
| `minecraft nbt` | `.nbt` | Uncompressed big-endian Minecraft NBT compound roots preserving typed tags. |
| `mongodb bson` | `.bson` | MongoDB BSON documents or dumps exporting bounded typed fields. |
| `msgpack` | `.msgpack` | MessagePack map/array roots preserving complete encoded typed values. |
| `MTREE` | `.mtree` | BSD mtree manifest describing filesystem paths and metadata. |
| `nintendo byaml` | `.byml` | Nintendo BYAML version-two resources exposing supported structured maps and arrays. |
| `ocsp response` | — | DER successful OCSP BasicOCSPResponse records preserving typed status and signature fields. |
| `openssh certificate` | — | OpenSSH binary Ed25519 certificates preserving typed principals and signatures. |
| `openssh private key` | — | Raw unencrypted OpenSSH Ed25519 private keys with checked fields and padding. |
| `pkcs10 csr` | `.csr` | DER PKCS10 certificate requests preserving typed names, keys, and signatures. |
| `pkcs12 pfx` | `.pfx`, `.p12` | PKCS12 PFXv3 containers with typed bags and limited empty-password MAC checks. |
| `pkcs7 cms` | `.p7b`, `.p7c`, `.p7m`, `.p7s` | DER CMS Data/SignedData containers preserving certificates, content, and signer fields. |
| `pkcs8 private key` | `.p8`, `.key`, `.der` | DER PKCS8 unencrypted Ed25519 keys with typed algorithms and seeds. |
| `putty ppk` | `.ppk` | PuTTY PPKv2/v3 unencrypted Ed25519 keys with verified Private-MAC values. |
| `python marshal` | — | Python marshal3/4 primitive collections with checked references; code objects declined. |
| `python pickle` | `.pkl`, `.pickle` | Python pickle protocols2-5 primitive collections without object execution. |
| `ResourceFork` | `.rsrc` | Classic Macintosh resource fork exposing typed and named resources. |
| `tensorflow tfrecord` | `.tfrecord`, `.tfrecords` | TFRecord sequences exposing uncompressed records with verified masked CRC32C checksums. |
| `thrift compact` | — | Thrift Compact protocol1 RPC messages preserving typed fields and method names. |
| `ubjson` | `.ubj` | UBJSON array/object roots supporting typed and count-optimized containers. |
| `windows shell link` | `.lnk` | Windows Shell Links exporting bounded target components without path resolution. |
| `x509 certificate` | `.crt`, `.cer`, `.der` | DER X509 certificates with complete typed fields; signatures remain unverified. |
| `x509 crl` | `.crl` | DER X509v2 revocation lists with typed entries; signatures remain unverified. |

## Network captures and protocols (55)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `amqp frames` | — | AMQP0-9-1 publish transcripts with framed headers and encoded message bodies. |
| `arp packet` | — | Ethernet/IPv4 ARP requests or replies with complete typed address fields. |
| `bgp messages` | — | BGP4 OPEN/KEEPALIVE transcripts with bounded typed capability attributes. |
| `bittorrent metainfo` | `.torrent` | BitTorrent v1 bencoded metainfo with checked file bounds and piece hashes. |
| `btsnoop` | `.btsnoop` | BTSnoop version-one captures exposing framed encoded Bluetooth packet bytes. |
| `coap message` | — | CoAPv1 UDP messages with typed options and original application payloads. |
| `dbus message` | — | D-Bus protocol1 messages exporting typed body arguments without UNIX_FD values. |
| `dcerpc pdu` | — | DCE/RPC v5 unauthenticated Bind/Request/Response PDUs preserving encoded stubs. |
| `dds rtps` | — | DDSI RTPS2.1-2.5 datagrams containing supported typed submessages and encoded DATA. |
| `dhcp message` | — | DHCP Ethernet BOOTP messages with typed options and exact terminal padding. |
| `diameter message` | — | Diameter1 capability-exchange requests containing supported mandatory typed AVPs. |
| `dns message` | — | DNS packets with one question and supported typed resource records. |
| `ethernet frame` | — | Ethernet II frames carrying complete unfragmented IPv4/IPv6 UDP datagrams. |
| `gre packet` | — | GREv0 tunnels carrying checksum-checked unfragmented IPv4/IPv6 UDP payloads. |
| `gtp message` | — | GTPv1-U G-PDU tunnels carrying complete unfragmented UDP datagrams. |
| `http1 message` | — | HTTP1.1 messages with explicit-length or chunked bodies and typed headers. |
| `icmp message` | — | ICMPv4 Echo requests/replies containing checked checksums and nonempty payloads. |
| `igmp message` | — | IGMPv3 membership reports with checked multicast groups and typed sources. |
| `ip packet` | — | Unfragmented IPv4/IPv6 UDP packets with verified header and transport checksums. |
| `isakmp message` | — | ISAKMPv1 unencrypted Main Mode offers with typed IPSEC proposals. |
| `l2tp packet` | — | L2TPv2 clear SCCRQ control messages with mandatory typed AVPs. |
| `ldap message` | — | LDAPv3 search-result transcripts with typed entries and matching completion records. |
| `ldp message` | — | LDPv1 Hello PDUs with complete lengths and supported typed TLVs. |
| `lldp message` | — | Bare LLDP PDUs with ordered mandatory fields and supported optional TLVs. |
| `modbus tcp` | — | MODBUS TCP messages with checked MBAP headers and supported typed functions. |
| `mongodb wire` | — | MongoDB OP_MSG wire messages containing complete BSON document sections. |
| `mqtt packets` | — | MQTT3.1.1 client transcripts containing CONNECT, PUBLISH, and terminal DISCONNECT. |
| `netflow datagram` | — | NetFlowv5 datagrams containing counted fixed-size flow records and checked metadata. |
| `ntlm message` | — | NTLMSSP Type1 negotiation records with checked flags and bounded OEM names. |
| `ntp message` | — | NTPv4 client/server datagrams containing fixed 48-byte timestamp records. |
| `ospf packet` | — | OSPFv2 unauthenticated Hello packets with checked neighbor lists and checksums. |
| `pcap` | `.pcap` | PCAP version-2.4 captures exposing raw packet bytes and timestamp metadata. |
| `pcapng` | `.pcapng` | PCAPNG network captures exposing framed packet bytes and metadata blocks. |
| `pfcp message` | — | PFCP1 node association requests with Node ID and recovery timestamp. |
| `pim message` | — | PIMv2 IPv4 Hello messages with supported options and checked checksums. |
| `PKT` | `.pkt` | FidoNet type-2 mail packet containing individually exported messages. |
| `pptp message` | — | PPTP1 initial control requests with typed capability and host metadata. |
| `radius packet` | — | RADIUS packets with typed attributes; authenticators remain encoded and unverified. |
| `redis resp` | — | RESP2 known-command streams exporting bounded arrays and bulk-string arguments. |
| `rip message` | — | Unauthenticated RIPv2 response datagrams containing checked IPv4 route entries. |
| `rsvp message` | — | RSVP1 Hello request/ack objects with checked fields and Internet checksums. |
| `rtp rtcp` | — | RTPv2 media datagrams or supported compound RTCP control packets. |
| `rtsp message` | — | RTSP1.0 OPTIONS/DESCRIBE requests with typed headers and complete bodies. |
| `sctp packet` | — | SCTP datagrams containing CRC32C-checked DATA chunks and encoded payloads. |
| `sip message` | — | SIP2.0 MESSAGE/OPTIONS requests with mandatory headers and explicit body lengths. |
| `smtp transcript` | — | SMTP client transcripts exporting dot-decoded DATA and original commands. |
| `snmp message` | — | SNMPv1/v2c messages with definite BER and supported typed VarBind PDUs. |
| `someip message` | — | SOME/IP protocol1 messages preserving typed headers and encoded application payloads. |
| `ssh transport` | — | SSH2 clear key-exchange transcripts ending at NEWKEYS without protected traffic. |
| `stomp frames` | — | STOMP1.2 client transcripts with typed headers and complete message payloads. |
| `stun message` | — | STUN Binding messages with typed attributes and optional checked fingerprints. |
| `tacacs packet` | — | Unencrypted TACACS+ Authentication START records with bounded typed fields. |
| `tls records` | — | TLS1.2/1.3 records preserving clear hello handshakes and protected application bytes. |
| `vrrp message` | — | Unauthenticated VRRPv2 IPv4 advertisements with checked addresses and checksums. |
| `websocket frames` | — | Nonfragmented WebSocket streams with validated payloads and terminal close frames. |

## Science and engineering (145)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `abaqus input` | `.inp` | Abaqus mesh input subsets with checked nodes, elements, and sets. |
| `abinit input` | `.abi`, `.in` | ABINIT single-dataset inputs containing explicit lattice and atomic structure. |
| `aims geometry` | `.in` | FHI-aims geometry inputs with finite atoms and optional lattice vectors. |
| `alignment clustal` | `.aln` | Clustal W/X block alignments with consistent order and residue positions. |
| `alignment maf` | `.maf` | MAF1 a/s alignment blocks with checked sequence coordinates and widths. |
| `alignment mauve` | `.xmfa` | Mauve XMFA alignments with checked headers and complete sequence blocks. |
| `alignment phylip` | `.phy`, `.phylip` | Strict PHYLIP interleaved alignments with ten-column identifiers and checked block widths. |
| `alignment stockholm` | `.sto`, `.stk` | Stockholm1.0 alignments preserving sequences and bounded typed annotations. |
| `amber prmtop` | `.prmtop`, `.parm7` | AMBER formatted topologies with checked POINTERS and core atom/residue arrays. |
| `amber restart` | `.rst`, `.rst7`, `.inpcrd` | ASCII AMBER restarts preserving coordinates and optional velocity/box arrays. |
| `amira mesh` | `.am` | AmiraMesh2.1 little-endian uniform float lattices with scalar/vector fields. |
| `assembly gfa` | `.gfa` | GFA1 assembly graphs with checked segments, links, and M-only overlaps. |
| `astronomy ser` | `.ser` | SER astronomical recordings exposing stored image planes and optional timestamp arrays. |
| `autocad dxf` | `.dxf` | R14+ binary DXF drawings with typed balanced sections. |
| `axona tetrode` | — | Axona four-channel tetrode recordings exporting timestamped spike waveforms. |
| `biomedical bdf` | `.bdf` | Original BDF recordings exposing declared raw twenty-four-bit physiological signal bytes. |
| `blackrock nev` | `.nev` | Blackrock NEV2.2/2.3 recordings exporting fixed-width event packets and headers. |
| `blackrock nsx` | `.ns1`, `.ns2`, `.ns3`, `.ns4`, `.ns5`, `.ns6` | Blackrock NSx2.2/2.3 continuous recordings containing stored 16-bit channel packets. |
| `calma gdsii` | `.gds`, `.gdsii` | Calma GDSII layout records with typed libraries, structures, and geometry. |
| `castep cell` | `.cell` | CASTEP cell files containing explicit lattices and ABS/FRAC atomic positions. |
| `charmm crd` | `.crd`, `.cor` | CHARMM ASCII coordinate cards with explicit counts and checked atom records. |
| `charmm dcd` | `.dcd` | CHARMM DCD trajectories supporting framed coordinate arrays without fixed atoms. |
| `cp2k input` | `.inp` | CP2K input subset with inline Cartesian geometry and explicit cell settings. |
| `crystal fort34` | `.34` | CRYSTAL fort.34 geometries with counted coordinates and identity symmetry. |
| `crystallography mtz` | `.mtz` | Little-endian CCP4 MTZ reflection tables with checked column metadata. |
| `demon input` | `.inp` | deMon2k inputs with typed settings and checked Cartesian atomic coordinates. |
| `dicom` | `.dcm`, `.dicom` | DICOM Part10 files exposing validated data elements and encoded image fragments. |
| `dl poly config` | — | DL_POLY4 CONFIG structures with explicit counts and typed molecular vectors. |
| `dsn6 density` | `.dsn6`, `.brix` | DSN6/BRIX density maps preserving complete encoded 8x8x8 bricks. |
| `dted elevation` | `.dt0`, `.dt1`, `.dt2` | DTED level0-2 elevation columns with checked identities and additive checksums. |
| `edf` | `.edf` | Original EDF recordings exposing declared raw sixteen-bit physiological signal records. |
| `ensight gold geometry` | `.geo` | EnSight Gold little-endian unstructured geometry with checked typed connectivity. |
| `esri ascii grid` | `.asc` | Esri ASCII grids with complete georeference headers and finite samples. |
| `esri shp` | `.shp` | ESRI shapefiles exposing supported XY geometry records and checked part tables. |
| `excellon drill` | `.drl` | Excellon drill files with typed tools and integer-position records. |
| `fcs` | `.fcs` | FCS version-three datasets exposing validated metadata and floating-point event bytes. |
| `fits` | `.fits`, `.fit`, `.fts` | FITS image arrays exposing original header blocks and big-endian array bytes. |
| `flatgeobuf` | `.fgb` | FlatGeobuf3 geospatial features with typed properties and bounded indexes. |
| `freesurfer mgh` | `.mgh` | FreeSurfer MGH version-one volumes exposing big-endian stored voxels and frames. |
| `freesurfer surface` | `.surf` | FreeSurfer binary triangle surfaces with finite vertices and optional volume metadata. |
| `gamess input` | `.inp` | GAMESS-US inputs with CONTRL/BASIS settings and C1 Cartesian geometry. |
| `garmin fit` | `.fit` | Garmin FIT activity records with CRC16 and complete message framing. |
| `gaussian cube` | `.cube`, `.cub` | Scalar Gaussian Cube grids with finite geometry and exact voxel counts. |
| `gaussian fchk` | `.fchk`, `.fch` | Gaussian formatted checkpoints containing checked typed numeric fields. |
| `gaussian input` | `.gjf`, `.com` | Gaussian single-job inputs with checked route fields and Cartesian coordinates. |
| `genomics agp` | `.agp` | AGP assembly layouts with contiguous components and typed gap records. |
| `genomics bed` | `.bed` | BED3-12 genomic intervals with typed optional fields and checked blocks. |
| `genomics bgen` | `.bgen` | BGEN Layout1 uncompressed biallelic genotype records with probability checks. |
| `genomics embl` | `.embl`, `.dat` | EMBL nucleotide records with checked sequence positions and base counters. |
| `genomics fasta` | `.fa`, `.fasta`, `.fna`, `.faa` | Uncompressed FASTA records containing checked nucleotide or protein sequences. |
| `genomics fastq` | `.fq`, `.fastq` | Four-line Sanger FASTQ records with matched PHRED+33 qualities. |
| `genomics genbank` | `.gb`, `.gbk` | GenBank nucleotide records exporting counted sequences and original annotations. |
| `genomics gff3` | `.gff`, `.gff3` | GFF3 annotation records with checked coordinates and percent-escaped attributes. |
| `genomics gtf` | `.gtf` | GTF2 gene annotations with typed coordinates and quoted attributes. |
| `genomics sam` | `.sam` | SAM1.0-1.6 text alignments with checked references, CIGARs, and typed tags. |
| `genomics sff` | `.sff` | SFF1 flowgrams containing aligned read records and bounded Roche indexes. |
| `genomics swissprot` | `.dat` | Swiss-Prot protein records with counted sequences and verified CRC64. |
| `genomics vcf` | `.vcf` | Uncompressed VCF4.1-4.3 sites-only variants without genotype columns. |
| `genomics wiggle` | `.wig` | Wiggle fixedStep/variableStep signal tracks with ascending coordinates and finite values. |
| `gerber rs274x` | `.gbr` | Gerber RS274X linear artwork with basic apertures and checked regions. |
| `gguf` | `.gguf` | Little-endian GGUFv3 models containing stored nonquantized tensor arrays. |
| `gipl` | `.gipl` | Uncompressed GIPL images exposing primitive voxel arrays and fixed headers. |
| `gmsh msh` | `.msh` | Gmsh MSH2.2 ASCII meshes with checked nodes, elements, and tags. |
| `gmv mesh` | `.gmv` | GMV ASCII/IEEE32 unstructured meshes with typed geometry and variable records. |
| `gocad model` | `.ts` | GOCAD TSurf1 triangulated surfaces with checked properties and local references. |
| `gromacs gro` | `.gro` | Single-frame GROMACS GRO coordinates with optional velocities and box vectors. |
| `gromacs trr` | `.trr` | GROMACS TRR trajectories exposing checked XDR frames and stored array components. |
| `gxf grid` | `.gxf` | GXF3 uncompressed grids with complete headers and counted numeric samples. |
| `harwell boeing` | `.hb`, `.rua` | Harwell-Boeing RUA matrices with checked one-based sparse column storage. |
| `hdf4` | `.hdf` | HDF4 files exposing validated descriptor tables and encoded scientific data components. |
| `iges model` | `.igs`, `.iges` | IGES ASCII CAD subset with checked entities and fixed-record framing. |
| `igor ibw` | `.ibw` | Igor IBW5 real numeric waves with metadata and header checksums. |
| `inivation aedat` | `.aedat` | AEDAT2.0 event-camera recordings containing monotonic address/timestamp pairs. |
| `jcamp dx` | `.jdx`, `.dx` | JCAMP-DX4/5 AFFN spectra containing single XYPOINTS or XYDATA blocks. |
| `lammps data` | `.data` | LAMMPS atomic-style data with checked masses, positions, and optional velocities. |
| `lammps dump` | `.dump`, `.lammpstrj` | LAMMPS atom/custom dump frames with checked cells and typed columns. |
| `lecroy trc` | `.trc` | LeCroy WAVEDESC traces exporting stored samples and declared waveform blocks. |
| `lidar las` | `.las` | LAS version-1.2 point clouds exposing uncompressed points and bounded metadata. |
| `mapinfo mif` | `.mif` | MapInfo MIF vector geometry with typed styling and bounded coordinates. |
| `matlab mat4` | `.mat` | MATLAB version-four files exposing stored numeric or text matrix planes. |
| `matlab mat5` | `.mat` | MATLAB version-five files exposing bounded encoded matrix and data elements. |
| `matrix market` | `.mtx` | MatrixMarket coordinate/array matrices with typed values and symmetry checks. |
| `mcap` | `.mcap` | Unindexed, unchunked MCAP recordings exporting schemas, messages, and attachments. |
| `mdl molfile` | `.mol` | Single V2000 MOL structures with checked atoms, bonds, and properties. |
| `medit mesh` | `.mesh` | MEDIT ASCII mesh v1/v2 sections containing checked vertices and connectivity. |
| `metaimage` | `.mha` | Attached MetaImage volumes exposing LOCAL raw multichannel binary image arrays. |
| `microscopy ics` | `.ics` | ICS version-two microscopy images supporting attached uncompressed integer or real arrays. |
| `microscopy spider` | `.spi` | SPIDER real 2D images or 3D volumes without stacks. |
| `molecule xyz` | `.xyz` | Plain XYZ molecular frames with counted atoms and finite coordinates. |
| `mountainsort mda` | `.mda` | MountainSort little-endian numeric arrays with checked dimensions and element counts. |
| `mrc` | `.mrc` | MRC2014 volumes exposing supported raw array modes and extended metadata. |
| `nastran bulk` | `.bdf`, `.nas` | NASTRAN small/free-field mesh cards with checked nodes and connectivity. |
| `netcdf classic` | `.nc` | Classic NetCDF datasets preserving checked dimensions, variables and stored arrays. |
| `netgen vol` | `.vol` | Netgen VOL ASCII meshes with finite coordinates and checked connectivity. |
| `neuroscan cnt` | `.cnt` | Neuroscan CNT recordings exporting continuous integer samples and event tables. |
| `nifti1` | `.nii` | Single-file NIfTI-1 volumes exposing uncompressed voxel arrays and validated extensions. |
| `nifti2` | `.nii` | Single-file NIfTI-2 volumes exposing uncompressed arrays and validated extension metadata. |
| `nrrd` | `.nrrd` | Attached NRRD datasets supporting stored raw primitive image arrays. |
| `numpy npy` | `.npy` | NumPy arrays preserving validated dtype metadata and stored array bytes. |
| `nwchem input` | `.nw` | NWChem inputs with Cartesian geometry, bounded settings, and supported tasks. |
| `ogc wkt` | `.wkt` | OGC 2D WKT geometries with finite coordinates and closed polygon rings. |
| `opendx field` | `.dx` | ASCII OpenDX axis-aligned scalar grids with checked counts and references. |
| `openephys continuous` | `.continuous` | Open Ephys 0.4 continuous recordings with fixed-size sample records. |
| `openfoam points` | — | OpenFOAM ASCII points files containing counted finite mesh vectors. |
| `orca input` | `.inp` | ORCA input subset with simple routes and inline Cartesian geometry. |
| `photontiming phu` | `.phu` | PHU photon-timing datasets exposing typed metadata and stored histogram curves. |
| `photontiming ptu` | `.ptu` | PTU photon-timing datasets exposing typed metadata and supported encoded TTTR records. |
| `phylo newick` | `.nwk`, `.newick` | Newick phylogenetic trees with bounded clades and finite branch lengths. |
| `phylo nexus` | `.nex`, `.nexus` | NEXUS TREES blocks with optional TAXA metadata and checked taxa. |
| `pointcloud pcd` | `.pcd` | PCD version-0.7 point clouds supporting stored binary little-endian point arrays. |
| `princeton spe` | `.spe` | Princeton SPE2.0/2.5 image files containing complete monochrome primitive frames. |
| `protein mmcif` | `.cif`, `.mmcif` | Single-block mmCIF structures with complete atom_site loops and finite coordinates. |
| `protein pdb` | `.pdb` | Single-model PDB coordinates with checked atom records and terminal END. |
| `qchem input` | `.in`, `.inp` | Q-Chem molecule/rem input subset with checked settings and Cartesian geometry. |
| `quantum espresso input` | `.in` | Quantum Espresso PWscf inputs with explicit cells, species, and positions. |
| `rosbag1` | `.bag` | Indexed ROSbag 2.0 recordings containing one uncompressed message chunk. |
| `safetensors` | `.safetensors` | SafeTensors models containing JSON tensor metadata and contiguous stored arrays. |
| `sas xport` | `.xpt` | SAS XPORT datasets exposing validated metadata and encoded transport records. |
| `seismic sac` | `.sac` | SAC v6 evenly sampled seismic waveforms containing real float32 samples. |
| `seismic seg2` | `.seg2`, `.sg2` | SEG-2 revision1 seismic traces with stored numeric samples and metadata. |
| `seismic segy` | `.sgy`, `.segy` | SEG-Y revision-zero or revision-one files preserving checked encoded seismic traces. |
| `sequencing abif` | `.ab1`, `.fsa` | ABIF1 sequencing files containing typed directory tags and inline/external values. |
| `sequencing scf` | `.scf` | SCF3 chromatograms preserving delta-coded channels and checked base tables. |
| `shelx res` | `.res` | SHELX RES/AIRSS geometries with typed fractional atoms and identity symmetry. |
| `siesta xv` | `.xv` | SIESTA XV structures containing cell matrices, coordinates, and velocities. |
| `spss sav` | `.sav` | SPSS SAV datasets exposing supported encoded dictionary and case-data components. |
| `stata dta` | `.dta` | Stata datasets exposing checked metadata and stored observation data components. |
| `step part21` | `.step`, `.stp` | STEP Part21 cleartext entities with complete framing and resolved references. |
| `stereolithography stl` | `.stl` | Binary STL triangular meshes with finite facets and zero attributes. |
| `surfer grid` | `.grd` | Surfer DSAA ASCII grids with checked dimensions and elevation extrema. |
| `tecplot plt` | `.plt` | Tecplot TDV112 datasets exposing stored ordered nodal zones and variable arrays. |
| `tektronix isf` | `.isf` | Tektronix TDS traces with WFMPRE metadata and definite-length CURVE samples. |
| `tetgen mesh` | `.node`, `.ele` | Standalone TetGen node/element sections with checked IDs and typed rows. |
| `tripos mol2` | `.mol2` | Single MOL2 SMALL molecules with checked atom/bond and substructure records. |
| `turbomole coord` | — | TURBOMOLE coord structures with finite Cartesian atoms and terminal end markers. |
| `ucsc bigbed` | `.bb`, `.bigbed` | UCSC bigBed BBI4 annotation tracks with stored or zlib sections. |
| `ucsc bigwig` | `.bw`, `.bigwig` | UCSC bigWig BBI4 signal tracks with stored or zlib sections. |
| `ucsc nib` | `.nib` | UCSC NIB nucleotide sequences decoding packed bases while preserving mask case. |
| `ucsc twobit` | `.2bit` | UCSC twoBit v0 sequence archives preserving packed bases and masks. |
| `usgs dem` | `.dem` | USGS ASCII DEM files containing checked fixed-record elevation profiles. |
| `vasp poscar` | — | VASP5 POSCAR/CONTCAR geometry with named species and explicit lattice positions. |
| `vtk legacy` | `.vtk` | Legacy VTK binary structured points supporting a single stored scalar array. |
| `wmo bufr` | `.bufr` | BUFR4 observation messages exporting encoded sections without descriptor expansion. |
| `wmo grib` | `.grib`, `.grb`, `.grib2` | Single-field GRIB2 messages exporting encoded sections without meteorological field decoding. |
| `xcrysden xsf` | `.xsf` | XCrySDen molecular or periodic structures with optional force vectors. |

## Other (1)

| Format | Extension(s) | Description |
| --- | --- | --- |
| `BINARY` | — | Unclassified raw data. |
