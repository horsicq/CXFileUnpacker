/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "metadata.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); exit(1); } } while (0)

static const char *property(const xfu_property *properties, size_t count, const char *name) {
    size_t i;
    for (i = 0; i < count; ++i) if (!strcmp(properties[i].name, name)) return properties[i].value;
    return NULL;
}

int main(void) {
    xx_archive_record record;
    xx_var var;
    xfu_property *properties;
    size_t count;
    static const unsigned char bytes[] = {0x00, 0x7f, 0x80, 0xff};
    static const char text[] = {'a', '\0', '\n', 'b'};
    static const wchar_t wide[] = {L'a', L'\0', 0x03a9};
    xx_archive_record_init(&record);
    xx_var_init(&var);
    record.header_offset = 42; record.header_size = 31;
    record.data_offset = 73; record.compressed_size = 7;
    CHECK(xx_archive_record_set_meta_u64(&record, XX_META_ID_COMPRESSION_METHOD, 8));
    CHECK(xx_archive_record_set_meta_u64(&record, XX_META_ID_FLAGS, 6));
    CHECK(xx_archive_record_set_meta_u64(&record, XX_META_ID_VERSION_MADE_BY, 20));
    CHECK(xx_archive_record_set_meta_u64(&record, XX_META_ID_CRC32, 0x75bcc38e));
    CHECK(xx_archive_record_set_meta_bool(&record, XX_META_ID_IS_ENCRYPTED, false));
    xx_var_set_bytes_view(&var, bytes, sizeof(bytes));
    CHECK(xx_archive_record_set_meta(&record, XX_META_ID_EXTRA_FIELD, &var));
    xx_var_set_str_view(&var, text, sizeof(text));
    CHECK(xx_archive_record_set_meta(&record, XX_META_ID_COMMENT, &var));
    xx_var_set_wstr_view(&var, wide, sizeof(wide) / sizeof(wide[0]));
    CHECK(xx_archive_record_set_meta(&record, XX_META_ID_ORIGINAL_NAME, &var));
    xx_var_set_i64(&var, INT64_MIN);
    CHECK(xx_archive_record_set_meta(&record, 1000, &var));
    xx_var_set_u64(&var, UINT64_MAX);
    CHECK(xx_archive_record_set_meta(&record, 1001, &var));
    xx_var_set_double(&var, 1.25);
    CHECK(xx_archive_record_set_meta(&record, 1002, &var));
    xx_var_set_double(&var, 2.5);
    CHECK(xx_archive_record_add_meta(&record, 1002, &var));
    CHECK(xfu_record_properties(&record, true, &properties, &count));
    CHECK(count == xx_list_count(&record.list_meta) + 6);
    /* Display properties survive the destruction of the original record. */
    xx_var_cleanup(&var);
    xx_archive_record_cleanup(&record);
    CHECK(!strcmp(property(properties, count, "Header offset"), "42"));
    CHECK(!strcmp(property(properties, count, "Header size"), "31"));
    CHECK(!strcmp(property(properties, count, "Data offset"), "73"));
    CHECK(!strcmp(property(properties, count, "Packed data size"), "7"));
    CHECK(!strcmp(property(properties, count, "CRC32"), "75BCC38E"));
    CHECK(!strcmp(property(properties, count, "Method"), "Deflate:Fastest"));
    CHECK(!strcmp(property(properties, count, "Host OS"), "FAT"));
    CHECK(!strcmp(property(properties, count, "Flags"), "0x6"));
    CHECK(!strcmp(property(properties, count, "Encrypted"), "No"));
    CHECK(!strcmp(property(properties, count, "Extra field (hex)"), "00 7F 80 FF"));
    CHECK(!strcmp(property(properties, count, "Comment"), "a\\x00\\x0Ab"));
    CHECK(!strcmp(property(properties, count, "Original name"), "a\\x00\xce\xa9"));
    CHECK(!strcmp(property(properties, count, "Metadata 1000"), "-9223372036854775808"));
    CHECK(!strcmp(property(properties, count, "Metadata 1001"), "18446744073709551615"));
    CHECK(!strcmp(property(properties, count, "Metadata 1002"), "1.25"));
    CHECK(!strcmp(property(properties, count, "Metadata 1002 #2"), "2.5"));
    xfu_free_properties(properties, count);
    puts("All record fields, metadata, variants and ZIP interpretations passed");
    return 0;
}
