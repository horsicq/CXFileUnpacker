/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "supported_types.h"
#include <xxfclib/formats/xx_format.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

char *xfu_supported_types_text(size_t *count)
{
    xx_list_t *types = xx_format_get_supported_file_types();
    size_t i, length = 4096, used, total;
    char *text = NULL;
    if (count) *count = 0;
    if (!types) return NULL;
    total = xx_list_count(types);
    for (i = 0; i < total; ++i) {
        xx_file_type_t type = *(const xx_file_type_t *)xx_list_at(types, i);
        size_t add = strlen(xx_format_file_type_to_string(type)) + 32;
        if (length > SIZE_MAX - add) goto finish;
        length += add;
    }
    text = (char *)malloc(length);
    if (!text) goto finish;
    used = (size_t)snprintf(text, length,
        "Supported file types (xxfclib): %zu\n"
        "Detection/inspection formats. Extraction and writing depend on the format.\n"
        "\nArchive creation: 7z, ZIP, TAR, GZIP, BZIP2, XZ, WIM; CPIO and compressed TAR.\n"
        "GZIP, BZIP2 and XZ streams hold one input file.\n"
        "7-Zip 26.03 readers (Windows x64 bundled engine): 60 handlers.\n"
        "Use --reader sevenzip for automatic selection or sevenzip_<handler>:\n"
        "7z APFS APM Ar Arj Base64 bzip2 Cab Chm COFF Compound Cpio CramFS Dmg\n"
        "ELF Ext FAT FLV GPT gzip HFS Hxs IHex Iso LP Lzh lzma lzma86 MachO MBR\n"
        "MsLZ Mub Nsis NTFS PE Ppmd QCOW Rar Rar5 Rpm Sparse Split SquashFS\n"
        "SWF SWFc tar TE Udf UEFIc UEFIf VDI VHD VHDX VMDK wim Xar xz Z zip zstd\n"
        "Named handler suffixes are lowercase; examples: sevenzip_apfs, sevenzip_rar5.\n"
        "\nMedia extraction: composited PNG frames, decoded WAV audio, playable video tracks.\n"
        "Use --reader media, media_frames, media_audio or media_video (Windows x64).\n"
        "Documents: PDF attachments/text/page bitmaps; MIME bodies and attachments;\n"
        "gettext MO to PO; Qt QM to TS; SQLite SQL export (sqlite3 keeps raw pages).\n"
        "Game archive fallback: --reader garbro (bundled RAM-only GARbro engine).\n"
        "\n"
        "   ID  File type\n", total);
    for (i = 0; i < total; ++i) {
        xx_file_type_t type = *(const xx_file_type_t *)xx_list_at(types, i);
        used += (size_t)snprintf(text + used, length - used, "%5u  %s\n",
            (unsigned int)type, xx_format_file_type_to_string(type));
    }
    if (count) *count = total;
finish:
    xx_list_destroy(types);
    return text;
}
