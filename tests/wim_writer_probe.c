/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 * Native WIM public writer API and failure controls. External interoperability
 * is checked by wim_writer_interop.py using the official 7-Zip executable.
 */
#include "xxfclib/formats/wim/xx_wim.h"
#include "xxfclib/io/xx_io.h"
#include "xxfclib/memory/xx_memory.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static unsigned checks;
#define REQUIRE(expression) do { ++checks; if (!(expression)) { fprintf(stderr, "check %u failed at line %u: %s\n", checks, __LINE__, #expression); goto fail; } } while (0)

typedef struct short_device { xx_io_device device; xx_io_device *target; } short_device;
static ssize_t short_read(xx_io_device *d, void *p, size_t n) { return xx_io_read(((short_device *)d->priv)->target, p, n > 7 ? 7 : n); }
static ssize_t short_write(xx_io_device *d, const void *p, size_t n) { return xx_io_write(((short_device *)d->priv)->target, p, n > 7 ? 7 : n); }
static int short_seek(xx_io_device *d, int64_t at, int origin) { return xx_io_seek64(((short_device *)d->priv)->target, at, origin); }
static int64_t short_tell(xx_io_device *d) { return xx_io_tell(((short_device *)d->priv)->target); }
static int64_t short_size(xx_io_device *d) { return xx_io_size(((short_device *)d->priv)->target); }

static bool add(Abstractformat *format, xx_archive_write_state *writer,
                const char *name, const void *data, size_t size, bool directory) {
    xx_archive_record record;
    xx_io_device *source = data ? xx_io_mem_open_ro(data, size) : NULL;
    bool okay;
    xx_archive_record_init(&record);
    okay = xx_archive_record_set_original_name(&record, name) &&
        xx_archive_record_set_meta_bool(&record, XX_META_ID_IS_FOLDER, directory) &&
        xx_archive_record_set_meta_u64(&record, XX_META_ID_UNCOMPRESSED_SIZE, size) &&
        xx_archive_record_set_meta_u64(&record, XX_META_ID_TIMESTAMP, UINT64_C(133485408000000000)) &&
        xx_format_pack_archive_record(format, writer, &record, source, NULL);
    xx_archive_record_cleanup(&record);
    if (source) xx_io_close(source);
    return okay;
}

static bool add_wide_view(Abstractformat *format, xx_archive_write_state *writer) {
    const wchar_t name[] = {'w','i','d','e','-',0x03a9,'.','t','x','t'};
    xx_archive_record record;
    xx_var value;
    xx_io_device *source = xx_io_mem_open_ro("wide\n", 5);
    bool okay;
    xx_archive_record_init(&record); xx_var_init(&value);
    xx_var_set_wstr_view(&value, name, sizeof(name) / sizeof(name[0]));
    okay = source && xx_archive_record_set_meta(&record, XX_META_ID_ORIGINAL_NAME, &value) &&
        xx_archive_record_set_meta_u64(&record, XX_META_ID_UNCOMPRESSED_SIZE, 5) &&
        xx_format_pack_archive_record(format, writer, &record, source, NULL);
    xx_archive_record_cleanup(&record); xx_var_cleanup(&value);
    if (source) xx_io_close(source);
    return okay;
}

int main(int argc, char **argv) {
    xx_io_device *device = NULL;
    xx_wim *archive = NULL;
    xx_archive_write_state *writer = NULL;
    xx_archive_record_state *reader = NULL;
    uint8_t payload[131071];
    short_device short_io = {0};
    int64_t base;
    unsigned i, count = 0;
    int result = 1;
    if (argc != 3 && argc != 4 && argc != 5) { fprintf(stderr, "usage: wim_writer_probe OUTPUT.wim MODE [METHOD [LEVEL]]\n"); return 2; }
    for (i = 0; i < sizeof(payload); ++i) payload[i] = (uint8_t)(i * 29U + (i >> 8U));
    REQUIRE((device = xx_io_file_open(argv[1], "w+b")) != NULL);
    base = !strcmp(argv[2], "base") ? 17 : 0;
    if (base) REQUIRE(xx_io_write(device, "XFU-prefix-17BYTE", 17) == 17);
    short_io.target = device; short_io.device.priv = &short_io;
    short_io.device.read = short_read; short_io.device.write = short_write;
    short_io.device.seek64 = short_seek; short_io.device.tell = short_tell; short_io.device.total_size = short_size;
    REQUIRE((archive = xx_wim_create(!strcmp(argv[2], "short") ? &short_io.device : device, base)) != NULL);
    if (argc > 3) {xx_var value;xx_var_init(&value);xx_var_set_u64(&value,(uint64_t)strtoul(argv[3],NULL,10));REQUIRE(xx_format_set_extra_parameter(&archive->format,XX_META_ID_COMPRESSION_METHOD,&value));
        if(argc>4){xx_var_set_u64(&value,(uint64_t)strtoul(argv[4],NULL,10));REQUIRE(xx_format_set_extra_parameter(&archive->format,XX_META_ID_COMPRESSION_LEVEL,&value));}xx_var_cleanup(&value);}
    REQUIRE((writer = xx_format_create_archive_records_writing(&archive->format, NULL, NULL)) != NULL);
    if (!strcmp(argv[2], "invalid")) {
        REQUIRE(!add(&archive->format, writer, "../outside", payload, 1, false));
        REQUIRE(!xx_format_finalize_archive_records_writing(&archive->format, writer, NULL));
    } else {
        if (strcmp(argv[2], "empty")) {
            REQUIRE(add(&archive->format, writer, "deep/path/payload.bin", payload, sizeof(payload), false));
            REQUIRE(add(&archive->format, writer, "copy.bin", payload, sizeof(payload), false));
            REQUIRE(add(&archive->format, writer, "empty.bin", NULL, 0, false));
            REQUIRE(add(&archive->format, writer, "empty-directory", NULL, 0, true));
            REQUIRE(add(&archive->format, writer, "unicode-\xe2\x98\x83-\xf0\x9f\x8c\x8d.txt", "unicode\n", 8, false));
            REQUIRE(add(&archive->format, writer, "deep", NULL, 0, true));
            REQUIRE(add_wide_view(&archive->format, writer));
        }
        REQUIRE(xx_format_finalize_archive_records_writing(&archive->format, writer, NULL));
        REQUIRE(xx_format_finalize_archive_records_writing(&archive->format, writer, NULL));
        REQUIRE(!add(&archive->format, writer, "after-finalize", NULL, 0, false));
        xx_format_free_archive_records_writing(&archive->format, writer); writer = NULL;
        REQUIRE(xx_wim_check_is_valid(&archive->format, NULL));
        REQUIRE((reader = xx_format_create_archive_records_reading(&archive->format, NULL, NULL)) != NULL);
        while (reader->has_record) {
            REQUIRE(xx_format_get_current_archive_record(&archive->format, reader) != NULL);
            REQUIRE(xx_format_unpack_current_archive_record(&archive->format, reader, NULL));
            ++count;
            if (!xx_format_archive_record_move_to_next(&archive->format, reader, NULL)) break;
        }
        REQUIRE(count == (!strcmp(argv[2], "empty") ? 1U : 9U));
    }
    printf("{\"checks\":%u,\"members\":%u}\n", checks, count);
    result = 0;
fail:
    if (reader) xx_format_free_archive_records_reading(&archive->format, reader);
    if (writer) xx_format_free_archive_records_writing(&archive->format, writer);
    xx_wim_free(archive);
    if (device) xx_io_close(device);
    return result;
}
