/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "core.h"
#include <xxfclib/formats/xx_format.h>
#include <xxfclib/io/xx_io.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); exit(1); } } while (0)

typedef struct observed {
    xx_file_type_t types[XX_FILE_TYPE_CHAIN_MAX], selected;
    size_t type_count, type_calls, entries;
    char names[4][128];
    int64_t sizes[4];
} observed;

static void types(void *user, const xx_file_type_t *chain, size_t count, xx_file_type_t selected)
{
    observed *seen = user;
    CHECK(count <= XX_FILE_TYPE_CHAIN_MAX);
    if (count) memcpy(seen->types, chain, count * sizeof(*chain));
    seen->type_count = count; seen->selected = selected; ++seen->type_calls;
}

static void entry(void *user, const xfu_entry *record)
{
    observed *seen = user;
    CHECK(record && record->name && seen->entries < 4 && strlen(record->name) < 128);
    strcpy(seen->names[seen->entries], record->name);
    seen->sizes[seen->entries++] = record->unpacked_size;
}

static void write_file(const char *path, const char *text)
{
    FILE *file = fopen(path, "wb");
    CHECK(file && fwrite(text, 1, strlen(text), file) == strlen(text));
    CHECK(fclose(file) == 0);
}

static void write_bytes(const char *path, const unsigned char *bytes, size_t length)
{
    FILE *file = fopen(path, "wb");
    CHECK(file && fwrite(bytes, 1, length, file) == length);
    CHECK(fclose(file) == 0);
}

int main(void)
{
    const char *files[] = {"alpha.txt", "beta.txt"};
    xfu_request request = {0};
    observed seen = {0};
    xx_io_device *device;
    char payload[128];
    write_file(files[0], "first payload\n"); write_file(files[1], "second payload\n");
    request.command = XFU_COMMAND_ADD; request.archive_path = "sample.tar.gz";
    request.files = files; request.file_count = 2;
    CHECK(xfu_run(&request) == 0);
    request.command = XFU_COMMAND_LIST; request.files = NULL; request.file_count = 0;
    request.callbacks.user = &seen; request.callbacks.entry = entry; request.callbacks.file_types = types;
    CHECK(xfu_run(&request) == 0);
    CHECK(seen.type_calls == 1 && seen.type_count == 3 && seen.selected == XX_FILE_TYPE_TAR_GZ);
    CHECK(seen.types[0] == XX_FILE_TYPE_BINARY && seen.types[1] == XX_FILE_TYPE_GZ && seen.types[2] == XX_FILE_TYPE_TAR_GZ);
    CHECK(seen.entries == 2 && !strcmp(seen.names[0], files[0]) && !strcmp(seen.names[1], files[1]));

    memset(&seen, 0, sizeof(seen)); request.file_type = XX_FILE_TYPE_GZ;
    CHECK(xfu_run(&request) == 0);
    CHECK(seen.selected == XX_FILE_TYPE_GZ && seen.type_count == 3 && seen.entries == 1 && seen.sizes[0] >= 2048);
    strcpy(payload, seen.names[0]);
    request.command = XFU_COMMAND_TEST;
    CHECK(xfu_run(&request) == 0);
    memset(&seen, 0, sizeof(seen)); request.command = XFU_COMMAND_EXTRACT;
    CHECK(xfu_run(&request) == 0 && seen.entries == 1 && !strcmp(seen.names[0], payload));
    /* Selecting gzip extracts the entire TAR payload, not its member files. */
    device = xx_io_file_open(payload, "rb");
    CHECK(device && xx_format_get_file_type_device(device) == XX_FILE_TYPE_TAR);
    xx_io_close(device);
    request.archive_path = payload; request.file_type = XX_FILE_TYPE_UNKNOWN; request.command = XFU_COMMAND_LIST;
    memset(&seen, 0, sizeof(seen)); CHECK(xfu_run(&request) == 0 && seen.entries == 2);

    request.archive_path = "sample.tar.gz"; request.file_type = XX_FILE_TYPE_BINARY;
    memset(&seen, 0, sizeof(seen)); CHECK(xfu_run(&request) == 2 && seen.entries == 0);
    CHECK(seen.selected == XX_FILE_TYPE_BINARY && seen.type_count == 3);
    request.command = XFU_COMMAND_EXTRACT; request.output_dir = "binary-output";
    memset(&seen, 0, sizeof(seen)); CHECK(xfu_run(&request) == 2 && seen.entries == 0);
    request.command = XFU_COMMAND_LIST; request.output_dir = NULL; request.file_type = XX_FILE_TYPE_ZIP;
    memset(&seen, 0, sizeof(seen)); CHECK(xfu_run(&request) == 2 && seen.entries == 0);
    request.file_type = XX_FILE_TYPE_TAR_GZ;
    memset(&seen, 0, sizeof(seen)); CHECK(xfu_run(&request) == 0 && seen.entries == 2);

    write_file("renamed.data", "ordinary bytes");
    request.archive_path = "renamed.data"; request.file_type = XX_FILE_TYPE_UNKNOWN;
    memset(&seen, 0, sizeof(seen)); CHECK(xfu_run(&request) == 2);
    CHECK(seen.type_count == 1 && seen.types[0] == XX_FILE_TYPE_BINARY && !seen.entries);
    {
        static const unsigned char anadisk[] = {
            0, 0, 0, 0, 1, 2, 1, 0, 'A',
            0, 0, 0, 0, 2, 2, 1, 0, 'B'
        };
        write_bytes("two-sectors.ANA", anadisk, sizeof(anadisk));
        device = xx_io_file_open("two-sectors.ANA", "rb");
        CHECK(device && xx_format_get_file_type_device(device) == XX_FILE_TYPE_BINARY);
        xx_io_close(device);
        request.archive_path = "two-sectors.ANA";
        memset(&seen, 0, sizeof(seen));
        CHECK(xfu_run(&request) == 0);
        CHECK(seen.selected == XX_FILE_TYPE_PCE_ANADISK && seen.entries == 2);
        CHECK(seen.type_count >= 1 && seen.types[seen.type_count - 1] == XX_FILE_TYPE_PCE_ANADISK);
        request.file_type = XX_FILE_TYPE_ZIP;
        memset(&seen, 0, sizeof(seen)); CHECK(xfu_run(&request) == 2);
        request.file_type = XX_FILE_TYPE_UNKNOWN;
        write_file("fake.ANA", "ordinary bytes");
        request.archive_path = "fake.ANA";
        memset(&seen, 0, sizeof(seen)); CHECK(xfu_run(&request) == 2);
        CHECK(seen.selected == XX_FILE_TYPE_BINARY && !seen.entries);
        CHECK(remove("two-sectors.ANA") == 0 && remove("fake.ANA") == 0);
    }
    CHECK(rename("sample.tar.gz", "signature.ANA") == 0);
    request.archive_path = "signature.ANA";
    memset(&seen, 0, sizeof(seen)); CHECK(xfu_run(&request) == 0);
    CHECK(seen.selected == XX_FILE_TYPE_TAR_GZ && seen.entries == 2);
    CHECK(rename("signature.ANA", "sample.tar.gz") == 0);
    /* The fast path uses a valid .gz interpretation before sniffing TAR. */
    CHECK(rename("sample.tar.gz", "extension-first.GZ") == 0);
    device = xx_io_file_open("extension-first.GZ", "rb");
    CHECK(device && xx_format_get_file_type_device(device) == XX_FILE_TYPE_TAR_GZ);
    CHECK(xx_format_get_file_type_device_fast(device, NULL) == XX_FILE_TYPE_GZ);
    xx_io_close(device);
    request.archive_path = "extension-first.GZ";
    memset(&seen, 0, sizeof(seen)); CHECK(xfu_run(&request) == 0);
    CHECK(seen.selected == XX_FILE_TYPE_GZ && seen.entries == 1);
    CHECK(rename("extension-first.GZ", "sample.tar.gz") == 0);
    write_file("fake.ZIP", "ordinary bytes");
    request.archive_path = "fake.ZIP";
    memset(&seen, 0, sizeof(seen)); CHECK(xfu_run(&request) == 2);
    CHECK(seen.selected == XX_FILE_TYPE_BINARY && !seen.entries);
    CHECK(remove("fake.ZIP") == 0);
    CHECK(remove(payload) == 0 && remove("sample.tar.gz") == 0 && remove("renamed.data") == 0);
    CHECK(remove(files[0]) == 0 && remove(files[1]) == 0);
    puts("Detected types, exact gzip/TAR readers and Binary archive refusal passed");
    return 0;
}
