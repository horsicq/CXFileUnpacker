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
    size_t i, length = 256, used, total;
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
