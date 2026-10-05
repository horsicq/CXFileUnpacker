/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "supported_types.h"
#include <xxfclib/formats/xx_format.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); exit(1); } } while (0)

int main(void)
{
    xx_list_t *first = xx_format_get_supported_file_types();
    xx_list_t *second = xx_format_get_supported_file_types();
    size_t count, i, matched = 0, lines = 0;
    xx_file_type_t previous = XX_FILE_TYPE_UNKNOWN;
    char *text, *cursor;
    CHECK(first && second && first != second);
    CHECK(xx_list_elem_size(first) == sizeof(xx_file_type_t));
    count = xx_list_count(first);
    CHECK(count > 1200 && count == xx_list_count(second));
    for (i = 0; i < count; ++i) {
        xx_file_type_t type = *(const xx_file_type_t *)xx_list_at(first, i);
        CHECK(type > previous);
        CHECK(strcmp(xx_format_file_type_to_string(type), "UNKNOWN"));
        CHECK(type == *(const xx_file_type_t *)xx_list_at(second, i));
        previous = type;
    }
    for (i = 1; i <= (size_t)previous; ++i) {
        /* This application links the formats-only library. Music IDs remain
         * ABI-stable below the newly added HxC IDs, but are not enabled here. */
        if (i >= 1600U && i <= (size_t)XX_FILE_TYPE_DIE_MUSIC_YM3812OPL2REGLOG) continue;
        if (!strcmp(xx_format_file_type_to_string((xx_file_type_t)i), "UNKNOWN")) continue;
        CHECK(matched < count && *(const xx_file_type_t *)xx_list_at(first, matched) == (xx_file_type_t)i);
        ++matched;
    }
    CHECK(matched == count);
    CHECK(!strcmp(xx_format_file_type_to_string(XX_FILE_TYPE_CPX4), "CPX4"));
    CHECK(!strcmp(xx_format_file_type_to_string(XX_FILE_TYPE_TAR_GZ), "TAR.GZ"));
    CHECK(previous >= XX_FILE_TYPE_SFX_INFTOOL);
    CHECK(!strcmp(xx_format_file_type_to_string(XX_FILE_TYPE_SFX_INFTOOL), "sfx inftool"));
    text = xfu_supported_types_text(&matched);
    CHECK(text && matched == count && strstr(text, "Supported file types (xxfclib): "));
    cursor = strstr(text, "   ID  File type\n");
    CHECK(cursor);
    cursor += strlen("   ID  File type\n");
    while (*cursor) {
        unsigned int type;
        char *end = strchr(cursor, '\n');
        int used = 0;
        CHECK(end && lines < count && sscanf(cursor, "%u  %n", &type, &used) == 1 && used > 0);
        CHECK(type == (unsigned int)*(const xx_file_type_t *)xx_list_at(first, lines));
        CHECK((size_t)(end - cursor - used) == strlen(xx_format_file_type_to_string((xx_file_type_t)type)));
        CHECK(!strncmp(cursor + used, xx_format_file_type_to_string((xx_file_type_t)type), (size_t)(end - cursor - used)));
        cursor = end + 1; ++lines;
    }
    CHECK(lines == count);
    *(xx_file_type_t *)xx_list_at(first, 0) = XX_FILE_TYPE_UNKNOWN;
    CHECK(*(const xx_file_type_t *)xx_list_at(second, 0) == XX_FILE_TYPE_BINARY);
    xx_list_destroy(first);
    CHECK(xx_list_count(second) == count);
    xx_list_destroy(second); free(text);
    return 0;
}
