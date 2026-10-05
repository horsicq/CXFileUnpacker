# HxC input coverage

Audited [https://hxc2001.com/docs/gotek-floppy-emulator-hxc-firmware/pages/emulation-from-images.html](https://hxc2001.com/docs/gotek-floppy-emulator-hxc-firmware/pages/emulation-from-images.html) on 2026-10-03. Upstream commit `3c9ab41127991797f0a9563f529f602fdb177e36`.

Source/catalog integration and every compiled explicit raw profile are checked by hxc_coverage.py. Structured payload fixtures are separate tests. Mapping does not promise filesystem decoding for tracks/flux or support for every unrecognized variant.

The210 rows comprise50 direct firmware rows,91 software-module rows and69 XML presets. Aliases, shared raw geometries, host filesystem generators and output generators are kept separate.

| Row | Page name | Extension | Reader/profile | Payload level and limits |
| --- | --- | --- | --- | --- |
| direct-01 | Universal support : All machines are supported by the native HxC Floppy Emulator (HFE) file format | *.HFE | hfe | sector_image: HFEv1 IBM MFM/FM and Amiga MFM sector recovery; raw tracks retained/incomplete flag where needed. |
| direct-02 | Copy protected HFE images (HFEv3 converted from ipf & stream files) | *.HFE (v3) | hxc_hfe_v3 | sector_image: HFEv3 opcode interpretation and supported IBM sectors; not arbitrary protected-track semantics. |
| direct-03 | PC and compatibles (Computers, Synth and CNC machinesâ€¦) | *.IMG | fat | filesystem_files: FAT filesystem when valid; arbitrary IBM raw sector images need explicit geometry profile. |
| direct-04 | PC and compatibles (Computers, Synth and CNC machinesâ€¦) | *.IMA | fat | filesystem_files: FAT filesystem when valid; arbitrary IBM raw sector images need explicit geometry profile. |
| direct-05 | Amiga | *.ADF | adf | filesystem_files: AmigaDOS OFS/FFS files; arbitrary non-filesystem ADF bytes require explicit raw profile. |
| direct-06 | Atari ST | *.ST | fat | filesystem_files: Headerless ST disk commonly FAT12; AtariST executable reader is not an ST disk reader. |
| direct-07 | Microbee | *.DSK | hxc_raw_floppy | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-08 | MSX | *.DSK | fat | filesystem_files: MSX FAT12 images when valid; arbitrary raw geometry needs explicit selection. |
| direct-09 | MSX | *.IMG | fat | filesystem_files: MSX FAT12 images when valid; arbitrary raw geometry needs explicit selection. |
| direct-10 | Amstrad CPC/ZX Spectrum/Tatung Einstein | *.DSK (Normal) | amstrad_cpc_dsk | sector_image: Normal and extended CPC DSK track/sector framing. |
| direct-11 | Amstrad CPC/ZX Spectrum/Tatung Einstein | *.DSK (Extended) | amstrad_cpc_dsk | sector_image: Normal and extended CPC DSK track/sector framing. |
| direct-12 | Acorn | *.ADL | acorn_adfs | filesystem_files: ADFS filesystem with selected side ordering; raw geometry also needs explicit profile. |
| direct-13 | Acorn | *.ADM | acorn_adfs | filesystem_files: Acorn ADFS, unrelated to Amiga ADF despite suffix. |
| direct-14 | Acorn | *.SSD | acorn_dfs | filesystem_files: DFS filesystem supports SSD and interleaved DSD sides. |
| direct-15 | Acorn | *.DSD | acorn_dfs | filesystem_files: DFS filesystem supports SSD and interleaved DSD sides. |
| direct-16 | Acorn | *.ADF | acorn_adfs | filesystem_files: Acorn ADFS, unrelated to Amiga ADF despite suffix. |
| direct-17 | Apple II | *.dsk | apple_dos33 | filesystem_files: DOS-order raw Apple disk; ProDOS/Pascal volume readers also available with matching order. |
| direct-18 | Apple II | *.do | apple_dos33 | filesystem_files: DOS-order raw Apple disk; ProDOS/Pascal volume readers also available with matching order. |
| direct-19 | Apple II | *.po | prodos | filesystem_files: ProDOS-order raw sectors; .dsk itself is ambiguous. |
| direct-20 | Camputer Lynx | *.LDF | camputers_lynx_ldf | filesystem_files: Lynx LDF named files; generic raw images require explicit profile. |
| direct-21 | Commodore C64 | *.D81 | cbm_d81 | filesystem_files: CBM files from D81 sector image. |
| direct-22 | Thomson machines (MO5, TO7â€¦) | *.FD | thomson_fd | sector_image: Stored side-sequential sectors normalized to thomson.img; no filesystem extraction. Explicit HxC80cylinder/1side ordering added while historical40cylinder/2side remains. |
| direct-23 | TI99/4A | *.DSK | ti99_dsk | filesystem_files: V9T9 raw sector order and TI directory/files; suffix alias .dsk. |
| direct-24 | TI99/4A | *.V9T9 | ti99_dsk | filesystem_files: V9T9 raw sector order and TI directory/files; suffix alias .dsk. |
| direct-25 | Sam CoupÃ© | *.SAD | samcoupe_sad | sector_image: Geometry-declared stored sectors normalized to disk.img. |
| direct-26 | Sam CoupÃ© | *.MGT | mgt | filesystem_files: MGT SAM/+D filesystem gate; raw geometry also explicit. |
| direct-27 | ZX Spectrum | *.TRD | trdos | filesystem_files: TR-DOS directory and file payloads. |
| direct-28 | ZX Spectrum | *.SDD | speccydos_sdd | sector_image: Canonical stored sectors normalized to disk.img. |
| direct-29 | ZX Spectrum | *.DSK | amstrad_cpc_dsk | sector_image: Normal and extended CPC DSK track/sector framing. |
| direct-30 | ZX Spectrum Opus Discovery | *.OPD | hxc_raw_floppy, profile:OPUS_DISCOVERY | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-31 | Akai (S900 / S950 / S01 / S20 / MPCâ€¦) | *.IMG | hxc_raw_floppy, profile:AKAIS950_DD_800KB, profile:AKAIS950_HD_1600KB | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-32 | Akai (S900 / S950 / S01 / S20 / MPCâ€¦) | *.AKAI | hxc_raw_floppy, profile:AKAIS3000_HD | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-33 | Casio | *.FZ1 | casio_fz_1_disk | filesystem_files: Existing FZ1 sampler file filesystem; FZF is a separate host-file format. |
| direct-34 | Emax | *.IMG | hxc_raw_floppy, profile:EMAX_DD_800KB, profile:EMAX_II_DD_800KB | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-35 | E-mu EOS / ESI | *.IMG | hxc_raw_floppy | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-36 | Ensoniq | *.IMG | hxc_raw_floppy, profile:ENSONIQ_DD_800KB, profile:ENSONIQ_HD_1600KB | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-37 | General Music | *.IMG | hxc_raw_floppy, profile:GENERALMUSIC_GEM_S3_1600KB, profile:GENERALMUSIC_GEM_WX_EXPANDER | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-38 | Korg | *.IMG | hxc_raw_floppy, profile:KORGDSS1_DD_800KB, profile:KORGT3_HD_1M6 | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-39 | Roland | *.OUT | hxc_raw_floppy, profile:ROLAND_DD_S330_W50_S50_S550 | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-40 | Roland | *.W30 | hxc_raw_floppy, profile:ROLAND_W30 | explicit_raw_sectors: Explicit primary-source geometry profile; no guessed magic from extension. |
| direct-41 | Roland | *.S50 | hxc_raw_floppy, profile:ROLAND_DD_S330_W50_S50_S550 | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-42 | Roland | *.S33 | hxc_raw_floppy, profile:ROLAND_DD_S330_W50_S50_S550 | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-43 | Roland | *.S55 | hxc_raw_floppy, profile:ROLAND_DD_S330_W50_S50_S550 | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-44 | Robox RC9400 | *.IMG | hxc_raw_floppy, profile:ROBOX_RC9400 | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-45 | Robox RC9400 | *.DSK | hxc_raw_floppy, profile:ROBOX_RC9400 | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-46 | Kawai | *.IMG | hxc_raw_floppy | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-47 | Kawai | *.DSK | hxc_raw_floppy | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-48 | Yamaha QX3 | *.IMG | hxc_raw_floppy | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| direct-49 | NEC PC98 | *.FDI | nec_pc_98_fdi | sector_image: NEC FDI geometry header and raw sector data. |
| direct-50 | User defined file image. See the custom firmware build page | . | hxc_raw_floppy | explicit_raw_sectors: Ambiguous raw-sector family. Named profiles cover documented examples; other sizes/orders require explicit caller-declared extents/geometry. Extension is not magic. |
| software-001 | KRYOFLUXSTREAM | *.raw | kryoflux_stream | flux_frames: Structured flux/control members; no sector or filesystem recovery. |
| software-002 | AMIGA_DMS | *.dms | dms | sector_image: Decompresses an Amiga sector image; not every DMS mode is promised here. |
| software-003 | AMIGA_ADZ | *.adz | gz | compressed_container: ADZ is gzip-compressed ADF; gzip decode then ADF parsing. |
| software-004 | AMIGA_EXTADF | *.adf | amiga_ext_adf | track_frames: UAE-1ADF descriptor and original DOS or raw MFM track bytes; revolution metadata retained. |
| software-005 | AMIGA_OLDEXTADF | *.adf | amiga_old_ext_adf | track_frames: 160 sync/length entries, sector bytes or restored sync plus raw MFM; no full filesystem guarantee. |
| software-006 | ZXSPECTRUM_FDI | *.fdi | fdi | sector_image: Spectrum FDI framing and sector-data output; distinct from NEC FDI. |
| software-007 | NEC_FDI | *.fdi | nec_pc_98_fdi | sector_image: NEC FDI geometry header and raw sector data. |
| software-008 | AMIGA_ADF | *.adf | adf | filesystem_files: AmigaDOS OFS/FFS files; arbitrary non-filesystem ADF bytes require explicit raw profile. |
| software-009 | BBC_ADL | *.adl | acorn_adfs | filesystem_files: ADFS filesystem with selected side ordering; raw geometry also needs explicit profile. |
| software-010 | ACORN_ADF | *.adf | acorn_adfs | filesystem_files: Acorn ADFS, unrelated to Amiga ADF despite suffix. |
| software-011 | AMSTRADCPC_DSK | *.dsk | amstrad_cpc_dsk | sector_image: Normal and extended CPC DSK track/sector framing. |
| software-012 | ATARIST_DIM | *.dim | atari_dim | sector_or_partial: Full-sector image, or header plus bounded sparse bytes marked incomplete; FAT-based sparse reconstruction unavailable. |
| software-013 | ATARIST_STX | *.stx | atari_pasti_stx | track_frames: Pasti STX framed data; no full copy-protection interpretation. |
| software-014 | ATARIST_STT | *.stt | atari_stt | track_frames: Stored sector/raw sections and complete track sections; intentional bad ID CRC retained. |
| software-015 | COPYQM | *.dsk | copyqm | sector_image: CopyQM decompression; .dsk suffix also used by unrelated formats. |
| software-016 | TELEDISK_TD0 | *.td0 | teledisk | sector_image: TeleDisk decompression and sector image. |
| software-017 | ATARIST_MSA | *.msa | atari_st_msa | sector_image: MSA track decompression. |
| software-018 | ATARIST_STW | *.stw | atari_stw | track_frames: Original big-endian clock/data MFM words, not filesystem recovery. |
| software-019 | RAW_IMZ | *.imz | winimage_zip | compressed_container: IMZ is a ZIP wrapper; generic ZIP additionally supports normal encrypted input. |
| software-020 | HXCMFM_IMG | *.mfm | hxc_mfm | track_frames: HxC MFM descriptor, index, and bounded track bitcell payloads; not decoded filesystem files. |
| software-021 | ORIC_DSK | *.dsk | oric_dsk | sector_or_track: ORICDISK sector tracks or MFM_DISK clock-stripped original track bytes, both geometry orders. |
| software-022 | ATARIST_ST | *.st | fat | filesystem_files: Headerless ST disk commonly FAT12; AtariST executable reader is not an ST disk reader. |
| software-023 | ROLAND_W30 | *.w30 | hxc_raw_floppy, profile:ROLAND_W30 | explicit_raw_sectors: Explicit primary-source geometry profile; no guessed magic from extension. |
| software-024 | SPS_IPF | *.ipf | amiga_ipf | track_frames: IPF framed records/payload components; no claim of arbitrary flux or filesystem recovery. |
| software-025 | TI994A_V9T9 | *.v9t9 | ti99_dsk | filesystem_files: V9T9 raw sector order and TI directory/files; suffix alias .dsk. |
| software-026 | AMIGA_FS | *.amigados | generator operation | host_input_or_output_generator: Host .amigados directory to generated Amiga filesystem; generated ADF is supported separately. |
| software-027 | PROPHET2000 | *.img | hxc_raw_floppy, profile:PROPHET2000_SS, profile:PROPHET2000_DS | explicit_raw_sectors: Fixed profiles use a common80cylinder shape; upstream derives cylinders from exact track-size divisor. Explicit geometry API covers other declared cylinder counts. |
| software-028 | RAW_IMG | *.img | fat | filesystem_files: FAT filesystem when valid; arbitrary IBM raw sector images need explicit geometry profile. |
| software-029 | FLP_IMG | *.flp | pc_magazine_flp | sector_image: PCM header validates geometry and exposes raw disk image. Primary PCM13-byte geometry wrapper matches existing reader. |
| software-030 | MSX_DSK | *.dsk | fat | filesystem_files: MSX FAT12 images when valid; arbitrary raw geometry needs explicit selection. |
| software-031 | FAT12FLOPPY | *.fat | generator operation | host_input_or_output_generator: Host files/directories copied into generated FAT floppy; generated FAT image is supported separately. |
| software-032 | HXC_HFE | *.hfe | hfe | sector_image: HFEv1 IBM MFM/FM and Amiga MFM sector recovery; raw tracks retained/incomplete flag where needed. |
| software-033 | HXC_HFEV3 | *.hfe | hxc_hfe_v3 | sector_image: HFEv3 opcode interpretation and supported IBM sectors; not arbitrary protected-track semantics. |
| software-034 | HXC_EXTHFE | *.hfe | hxc_hfe_extended | sector_image: Revision1 HXCPICFE; supported IBM MFM sector image. |
| software-035 | HXC_HDDD_A2_HFE | *.hfe | hxc_hfe_hddd_a2_variant | sector_image: HDDD A2-specific HFE variant; separate from ordinary revision0. |
| software-036 | HXC_STREAMHFE | *.hfe | hxc_stream_hfe | flux_frames: HxC_Stream_Image descriptor/track table; stored or LZ4 flux/stream payloads. |
| software-037 | VTR_IMG | *.vtr | vtr_disk | track_frames: Revision0 declared cells deinterleaved and bit-reversed per track/side; no filesystem recovery. |
| software-038 | IMD_IMG | *.imd | imd | sector_image: ImageDisk sector reconstruction; status data is distinct from filesystem content. |
| software-039 | SDU_IMG | *.sdu | sdu | sector_image: Header-declared geometry and complete sector image. |
| software-040 | HXC_AFI | *.afi | hxc_afi | component_preservation: CRC16 checked, stored/zlib decoded with exact Adler/size; reserved RLE/LZW retained as opaque components. |
| software-041 | C64_D64 | *.d64 | cbm_d64 | filesystem_files: CBM files from D64 sector image; not all low-level disk variants. |
| software-042 | C64_D81 | *.d81 | cbm_d81 | filesystem_files: CBM files from D81 sector image. |
| software-043 | ZXSPECTRUM_TRD | *.trd | trdos | filesystem_files: TR-DOS directory and file payloads. |
| software-044 | ZXSPECTRUM_SCL | *.scl | scl | filesystem_files: SINCLAIR SCL archive files. |
| software-045 | THOMSONTO8D_SAP | *.sap | thomson_sap | sector_image: SAP sector framing/data transform and integrity checks. |
| software-046 | TRS80_JV1 | *.jv1 | trs_80_jv1 | filesystem_files: TRSDOS/LDOS ModelI filesystem only; generic JV1 raw geometry still explicit. |
| software-047 | TRS80_JV3 | *.jv3 | trs_80_jv3 | sector_image: JV3 track/sector payloads; existing native parser. |
| software-048 | TRS80_JVC | *.jvc | jvc | filesystem_files: DragonDOS or OS9 filesystem gate; generic JVC sector content beyond those needs profile/container support. |
| software-049 | SVD | *.svd | svd | track_frames: Author formats1.2/1.5/2.0 descriptors and rotated blocks; WD-only tracks additionally unrotated; Apple GCR remains preserved components. |
| software-050 | NEC_D88 | *.d88 | pc98_d88 | sector_payloads: D88 framed sectors/track metadata; source audit should retain concatenated-disk and deleted/bad flags. |
| software-051 | X68000_HDM | *.hdm | hxc_raw_floppy, profile:X68000_HDM | explicit_raw_sectors: Explicit primary-source geometry profile; no guessed magic from extension. |
| software-052 | RAW_LOADER | *.img | hxc_raw_floppy | explicit_raw_sectors: Infinitegeometry family requires caller-supplied profile; no single file magic or finite canonical geometry. |
| software-053 | SNES_SMC | *.smc | generator operation | host_input_or_output_generator: Host copier ROM/SRAM input transformed into FAT floppy; not a separate floppy byte container. |
| software-054 | VEGAS6809 | *.veg | hxc_raw_floppy, profile:VEGAS6809_40T_1S_10SPT, profile:VEGAS6809_40T_1S_18SPT, profile:VEGAS6809_40T_2S_10SPT, profile:VEGAS6809_40T_2S_18SPT | explicit_raw_sectors: Track0 always10sectors/head; later tracks10or18;40cylinder presets are explicit choices, not inferred magic. |
| software-055 | TRS80_DMK | *.dmk | dmk | sector_image: DMK IBM sector decode; raw track fidelity distinct from filesystem decode. |
| software-056 | TI994A_PC99 | *.pc99 | ti99_pc99 | track_frames: FM/MFM token tracks with sector-set/real CRC or F7-placeholder checks; no filesystem recovery. |
| software-057 | APRIDISK | *.dsk | apridisk | sector_image: ApriDisk stored/RLE records normalized to sector image. |
| software-058 | ENSONIQ_EDE | *.ede | ensoniq_ede | sector_image: Stored sector blocks normalized to disk.img; no filesystem conversion. |
| software-059 | FAT12FLOPPY | *.fat | generator operation | host_input_or_output_generator: Host files/directories copied into generated FAT floppy; generated FAT image is supported separately. |
| software-060 | ENSONIQ_GKH | *.gkh | ensoniq_gkh | sector_image: Tag-declared raw sector image, bounded author/subject; no filesystem conversion. |
| software-061 | THOMSON_FD | *.fd | thomson_fd | sector_image: Stored side-sequential sectors normalized to thomson.img; no filesystem extraction. Explicit HxC80cylinder/1side ordering added while historical40cylinder/2side remains. |
| software-062 | CASIO_FZF | *.fzf | casio_fzf | sampler_components: Declared complete full/bank dumps with up to8 banks, validated voice parameters and complete PCM; strict canonical single-bank fallback. Split/continuation and unsupported wrappers remain rejected. |
| software-063 | DRAGON3264_VDK | *.vdk | dragon_vdk | sector_image: VDK header plus raw sector payload; JVC may provide supported filesystem parsing. |
| software-064 | OBERHEIM_DPX | *.dpx | hxc_raw_floppy, profile:OBERHEIM_DPX | explicit_raw_sectors: Fixed profiles use a common80cylinder shape; upstream derives cylinders from exact track-size divisor. Explicit geometry API covers other declared cylinder counts. |
| software-065 | ENSONIQ_EDM | *.edm | hxc_raw_floppy, profile:ENSONIQ_EDM | explicit_raw_sectors: Fixed profiles use a common80cylinder shape; upstream derives cylinders from exact track-size divisor. Explicit geometry API covers other declared cylinder counts. |
| software-066 | EMAX_EM | *.em1 | emax_disk | sampler_components: Exact EM1/EM2 bank and sample-bank extents; missing520 OS blocks marked incomplete. |
| software-067 | SAMCOUPE_MGT | *.mgt | mgt | filesystem_files: MGT SAM/+D filesystem gate; raw geometry also explicit. |
| software-068 | SAMCOUPE_SAD | *.sad | samcoupe_sad | sector_image: Geometry-declared stored sectors normalized to disk.img. |
| software-069 | EMULATORII | *.emuiifd | hxc_raw_floppy, profile:EMULATORII | explicit_raw_sectors: Explicit primary-source geometry profile; no guessed magic from extension. |
| software-070 | EMULATORII_EMUII | *.eii | emulatorii_eii | sampler_components: 136 stored tracks; missing24 OS tracks marked incomplete; explicit reader selection. |
| software-071 | EMULATORI | *.emufd | hxc_raw_floppy, profile:EMULATORI | explicit_raw_sectors: Explicit primary-source geometry profile; no guessed magic from extension. |
| software-072 | CAMPUTERSLYNX | *.ldf | camputers_lynx_ldf | filesystem_files: Lynx LDF named files; generic raw images require explicit profile. |
| software-073 | BBC_SSD_DSD | *.dsd | acorn_dfs | filesystem_files: DFS filesystem supports SSD and interleaved DSD sides. |
| software-074 | FEI | *.fei | fei | track_frames: Side-major LSB raw MFM; recognition requires four matching IBM ID CRC boundary headers; non-IBM remains undetected. |
| software-075 | SYSTEM_24 | *.s24 | hxc_raw_floppy, profile:SYSTEM_24_7SECTOR, profile:SYSTEM_24_6SECTOR | explicit_raw_sectors: Fixed profiles use a common80cylinder shape; upstream derives cylinders from exact track-size divisor. Explicit geometry API covers other declared cylinder counts. Upstream generates4additional fill-onlycylinders; not recovered source bytes and not included in these rawpresets. |
| software-076 | SCP_FLUX_STREAM | *.scp | supercard_scp | flux_frames: SCP revolution flux payloads and metadata; no full filesystem/sector decode. |
| software-077 | DFI_FLUX_STREAM | *.dfi | discferret_dfi | flux_frames: DFER/DFE2 flux/index delta captures and descriptors retained. |
| software-078 | A2R_FLUX_STREAM | *.a2r | apple_a2r | flux_frames: A2R2 STRM/A2R3 RWCP captures and metadata; A2R3 SLVD solved flux descriptors, mirrors and index framing, including sole-SLVD and empty tracks; no GCR filesystem recovery. |
| software-079 | APPLE2_NIB | *.nib | apple_nib | track_frames: Original tracks; at least one coherent DOS3.3 address and GCR-checksummed sector per track; no full sector recovery. |
| software-080 | APPLE2_DO | *.do | apple_dos33 | filesystem_files: DOS-order raw Apple disk; ProDOS/Pascal volume readers also available with matching order. |
| software-081 | SPECCYDOS_SDD | *.sdd | speccydos_sdd | sector_image: Canonical stored sectors normalized to disk.img. |
| software-082 | BMP_IMAGE | *.bmp | generator operation | host_input_or_output_generator: Output-only visualization generator; ordinary BMP input reader does not perform disk recovery. |
| software-083 | BMP_DISK_IMAGE | *.bmp | generator operation | host_input_or_output_generator: Output-only disk visualization generator; ordinary BMP input reader does not perform disk recovery. |
| software-084 | ARBURG | *.arburgfd | hxc_raw_floppy, profile:ARBURG_DATA, profile:ARBURG_SYSTEM | explicit_raw_sectors: Explicit primary-source geometry profile; no guessed magic from extension. |
| software-085 | GENERIC_XML | *.xml | hxc_xml_disk_layout | layout_descriptor: One XML layout schema, original descriptor and initialized sectors; raw companion must be explicitly supplied by API. |
| software-086 | ANA_IMG | *.ana | pce_anadisk | sector_payloads: AnaDisk framed sector payloads, conservative detection. |
| software-087 | ATARI_ATR | *.atr | atari_atr | sector_image: ATR sector-image framing; atari_dos2 may recover supported filesystem. |
| software-088 | NORTHSTAR | *.nsi | northstar_nsi | sector_image: Exact-size named NSI selection; reverses side1 wire order to logical image. |
| software-089 | HEATHKIT | *.h8d | hxc_raw_floppy, profile:HEATHKIT_40T_SS, profile:HEATHKIT_40T_DS | explicit_raw_sectors: Upstream loader confirms40tracks,10x256sectors/head; its j*i offset expression appears erroneous for dualside, so these profiles preserve canonical CHS source order rather than reproducing overlap.35track H8D is separate historical geometry, available through explicit API. |
| software-090 | HXC_QD | *.qd | hxc_qd | track_frames: LSB cell bytes with switch-position index; no filesystem recovery. |
| software-091 | HXCSTREAM | *.hxcstream | hxc_stream | flux_frames: Pauline packet CRC32 and exact LZ4/pulse-count decode; original authenticated padding retained. |
| software-092 | ABB_320KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ABB_320KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-093 | ABB_328KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ABB_328KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-094 | ABB_640KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ABB_640KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-095 | ACORN_ADFS_160K | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ACORN_ADFS_160K | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-096 | ACORN_ADFM_320K | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ACORN_ADFM_320K | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-097 | ACORN_ADFL_640K | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ACORN_ADFL_640K | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-098 | AED 6200P Disk Layout | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:AED_6200P | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-099 | AKAIS950_HD_1600KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:AKAIS950_HD_1600KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-100 | AKAIS950_DD_800KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:AKAIS950_DD_800KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-101 | AKAIS3000_HD | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:AKAIS3000_HD | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-102 | AMSTRADCPC_DD | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:AMSTRADCPC_DD | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-103 | AUTOMATIX_RAIL_DD_400KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:AUTOMATIX_RAIL_DD_400KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-104 | ATARIST_DD_720KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ATARIST_DD_720KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-105 | BUNG_MGD2 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:BUNG_MGD2 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-106 | CASIOFZ1_HD_1M25 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:CASIOFZ1_HD_1M25 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-107 | ROBOX_RC9400 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ROBOX_RC9400 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-108 | COMX35_SS_70KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:COMX35_SS_70KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-109 | COMX35_DS_140KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:COMX35_DS_140KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-110 | COMX35_SS_140KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:COMX35_SS_140KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-111 | DEC_RX55 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:DEC_RX55 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-112 | Didaktik_Spectrum_DD_720KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:Didaktik_Spectrum_DD_720KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-113 | DOS_DD_720KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:DOS_DD_720KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-114 | DOS_HD_1M44 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:DOS_HD_1M44 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-115 | DOS_ED_2M88 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:DOS_ED_2M88 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-116 | DOS_EXDD_2M5 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:DOS_EXDD_2M5 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-117 | DOS_EXHD_4M5 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:DOS_EXHD_4M5 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-118 | DOS_EXHD_6M78 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:DOS_EXHD_6M78 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-119 | DYNACORD_ADD_ONE | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:DYNACORD_ADD_ONE | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-120 | DYNACORD_HD | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:DYNACORD_HD | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-121 | ENSONIQ_DD_800KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ENSONIQ_DD_800KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-122 | ENSONIQ_HD_1600KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ENSONIQ_HD_1600KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-123 | ENSONIQ_MIRAGE_440KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ENSONIQ_MIRAGE_440KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-124 | EXCELLON_CNC6 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:EXCELLON_CNC6 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-125 | EMAX_DD_800KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:EMAX_DD_800KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-126 | EMAX_II_DD_800KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:EMAX_II_DD_800KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-127 | FLEX_SSDD_80T_358KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:FLEX_SSDD_80T_358KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-128 | FLEX_DSDD_80T_716KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:FLEX_DSDD_80T_716KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-129 | FLEX_DSDD_80T_716KB_PADDED | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:FLEX_DSDD_80T_716KB_PADDED | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-130 | FLEX_DSDD_40T_356KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:FLEX_DSDD_40T_356KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-131 | FLEX_DSDD_40T_356KB_PADDED | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:FLEX_DSDD_40T_356KB_PADDED | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-132 | GENERALMUSIC_GEM_S3_1600KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:GENERALMUSIC_GEM_S3_1600KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-133 | GENERALMUSIC_GEM_WX_EXPANDER | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:GENERALMUSIC_GEM_WX_EXPANDER | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-134 | GRAVOGRAPH_ISIS_640KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:GRAVOGRAPH_ISIS_640KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-135 | KORGDSS1_DD_800KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:KORGDSS1_DD_800KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-136 | KORGT3_HD_1M6 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:KORGT3_HD_1M6 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-137 | LIF_3_50_264KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:LIF_3_50_264KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-138 | LIF_3_50_616KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:LIF_3_50_616KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-139 | LIF_3_5O_1232KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:LIF_3_5O_1232KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-140 | LIF_5_25_264KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:LIF_5_25_264KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-141 | LINNFORAT9K_720KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:LINNFORAT9K_720KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-142 | MEMOTECH_80T | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:MEMOTECH_80T | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-143 | MEMOTECH_40T | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:MEMOTECH_40T | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-144 | Microtan 65 TANDOS Floppy Disk | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:MICROTAN_65_TANDOS | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-145 | BALZERS_250KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:BALZERS_250KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-146 | OPUS_DISCOVERY | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:OPUS_DISCOVERY | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-147 | OS9_640KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:OS9_640KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-148 | OS9_1280KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:OS9_1280KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-149 | ORIC_JASMIN_357KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ORIC_JASMIN_357KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-150 | PUMA_ROBOT_DD_640KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:PUMA_ROBOT_DD_640KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-151 | QD_TRIUMPH_ADLER | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:QD_TRIUMPH_ADLER | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-152 | ROLAND_DD_W30_S330_W50_S50_S550 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:ROLAND_DD_S330_W50_S50_S550 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-153 | SORD_M68_HD_998KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:SORD_M68_HD_998KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-154 | TATUNG_EINSTEIN_DD_200KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:TATUNG_EINSTEIN_DD_200KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-155 | TATUNG_EINSTEIN_DD_400KB | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:TATUNG_EINSTEIN_DD_400KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-156 | TIMEX_FDD3000_80T2S | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:TIMEX_FDD3000_80T2S | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-157 | TIMEX_FDD3000_40T1S | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:TIMEX_FDD3000_40T1S | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-158 | TRS80_JV1 | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:TRS80_JV1 | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-159 | UKNC MFM 800KB Disk Layout | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:UKNC_MFM_800KB | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
| software-160 | Unitel Videotex Floppy Disk | *.xml | hxc_xml_disk_layout, hxc_raw_floppy, profile:UNITEL_VIDEOTEX_FLOPPY_DISK | layout_preset: Preset for the common XML schema, with an explicit raw geometry profile; no independent69 container claim. |
