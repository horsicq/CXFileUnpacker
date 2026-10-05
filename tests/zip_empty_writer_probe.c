/* SPDX-License-Identifier: MIT. Empty Deflate/Deflate64 ZIP writer regression. */
#include "xxfclib/formats/zip/xx_zip.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;
#define REQUIRE(expression) do { ++checks; if (!(expression)) { \
    fprintf(stderr, "check %u failed at line %u: %s\n", checks, \
            (unsigned)__LINE__, #expression); goto done; } } while (0)

typedef struct borrowed {
    xx_io_device device;
    xx_io_device *inner;
    unsigned closes;
} borrowed;
static ssize_t read_proxy(xx_io_device *d, void *data, size_t size) {
    return xx_io_read(((borrowed *)d->priv)->inner, data, size);
}
static ssize_t write_proxy(xx_io_device *d, const void *data, size_t size) {
    return xx_io_write(((borrowed *)d->priv)->inner, data, size);
}
static int seek_proxy(xx_io_device *d, int64_t offset, int origin) {
    return xx_io_seek64(((borrowed *)d->priv)->inner, offset, origin);
}
static int seek_long_proxy(xx_io_device *d, long offset, int origin) {
    return seek_proxy(d, offset, origin);
}
static int64_t tell_proxy(xx_io_device *d) {
    return xx_io_tell(((borrowed *)d->priv)->inner);
}
static int64_t size_proxy(xx_io_device *d) {
    return xx_io_size(((borrowed *)d->priv)->inner);
}
static int close_proxy(xx_io_device *d) {
    ++((borrowed *)d->priv)->closes;
    return 0;
}
static void init_proxy(borrowed *proxy, xx_io_device *device) {
    memset(proxy, 0, sizeof(*proxy));
    proxy->inner = device;
    proxy->device.priv = proxy;
    proxy->device.read = read_proxy;
    proxy->device.write = write_proxy;
    proxy->device.seek = seek_long_proxy;
    proxy->device.seek64 = seek_proxy;
    proxy->device.tell = tell_proxy;
    proxy->device.size = proxy->device.get_total_size = proxy->device.total_size = size_proxy;
    proxy->device.close = close_proxy;
}
static bool option(xx_list_s *options, uint32_t id, uint64_t value) {
    xx_meta meta;
    xx_meta_init(&meta, id);
    xx_var_set_u64(&meta.var, value);
    if (!xx_list_append(options, &meta)) {
        xx_meta_cleanup(&meta);
        return false;
    }
    return true;
}

int main(int argc, char **argv) {
    static const char password[] = "empty ZIP writer password";
    xx_io_device *source = NULL, *output = NULL;
    borrowed input = {0}, target = {0};
    xx_zip *writer = NULL, *reader = NULL;
    xx_archive_write_state *writing = NULL;
    xx_archive_record_state *reading = NULL;
    xx_archive_record record;
    xx_list_s options;
    xx_pd_struct pd = xx_pd_init();
    xx_io_memory_only_scope scope = {0};
    bool scoped = false;
    uint32_t method, encryption;
    unsigned char *bytes = NULL;
    int64_t size;
    FILE *file = NULL;
    int result = 1;
    xx_archive_record_init(&record);
    xx_list_init(&options, sizeof(xx_meta), xx_meta_free_elem);
    REQUIRE(argc == 4);
    method = (uint32_t)atoi(argv[1]);
    REQUIRE(method == 8 || method == 9);
    if (!strcmp(argv[2], "none")) encryption = XX_ZIP_ENCRYPTION_NONE;
    else if (!strcmp(argv[2], "crypto")) encryption = XX_ZIP_ENCRYPTION_ZIPCRYPTO;
    else if (!strcmp(argv[2], "aes256")) encryption = XX_ZIP_ENCRYPTION_AES_256;
    else goto done;
    REQUIRE((source = xx_io_mem_open(NULL, 0)) != NULL);
    REQUIRE(xx_io_memory_only_begin(&scope, 8U * 1024U * 1024U)); scoped = true;
    REQUIRE((output = xx_io_temp_open()) != NULL);
    init_proxy(&input, source); init_proxy(&target, output);
    REQUIRE((writer = xx_zip_create(&target.device, 0)) != NULL);
    if (encryption != XX_ZIP_ENCRYPTION_NONE)
        REQUIRE(xx_format_set_password(&writer->format, password));
    REQUIRE(option(&options, XX_META_ID_COMPRESSION_METHOD, method));
    REQUIRE(option(&options, XX_META_ID_ENCRYPTION_METHOD, encryption));
    REQUIRE(xx_archive_record_set_original_name(&record, "empty.bin"));
    REQUIRE((writing = xx_format_create_archive_records_writing(&writer->format, &options, &pd)) != NULL);
    REQUIRE(xx_format_pack_archive_record(&writer->format, writing, &record, &input.device, &pd));
    REQUIRE(xx_io_tell(source) == 0);
    REQUIRE(xx_format_finalize_archive_records_writing(&writer->format, writing, &pd));
    REQUIRE((size = xx_io_size(output)) >= 22 && size < 1024);
    REQUIRE(input.closes == 0 && target.closes == 0);
    xx_format_free_archive_records_writing(&writer->format, writing); writing = NULL;
    xx_zip_free(writer); writer = NULL;
    REQUIRE(input.closes == 0 && target.closes == 0);
    REQUIRE((reader = xx_zip_create(&target.device, 0)) != NULL);
    if (encryption != XX_ZIP_ENCRYPTION_NONE)
        REQUIRE(xx_format_set_password(&reader->format, password));
    REQUIRE(xx_format_handle_base_info(&reader->format, &pd));
    REQUIRE((reading = xx_format_create_archive_records_reading(&reader->format, NULL, &pd)) != NULL);
    REQUIRE(reading->has_record && reading->total_records == 1);
    REQUIRE(xx_format_unpack_current_archive_record(&reader->format, reading, &pd));
    REQUIRE(!xx_format_archive_record_move_to_next(&reader->format, reading, &pd));
    xx_format_free_archive_records_reading(&reader->format, reading); reading = NULL;
    xx_zip_free(reader); reader = NULL;
    REQUIRE(input.closes == 0 && target.closes == 0);
    REQUIRE(xx_io_memory_only_error(&scope) == XX_IO_MEMORY_ONLY_OK);
    REQUIRE((bytes = (unsigned char *)malloc((size_t)size)) != NULL);
    REQUIRE(xx_io_seek64(output, 0, SEEK_SET) == 0);
    REQUIRE(xx_io_read(output, bytes, (size_t)size) == size);
    xx_io_close(output); output = NULL;
    REQUIRE(xx_io_memory_only_used() == 0);
    REQUIRE(xx_io_memory_only_end(&scope)); scoped = false;
    REQUIRE((file = fopen(argv[3], "wb")) != NULL);
    REQUIRE(fwrite(bytes, 1, (size_t)size, file) == (size_t)size);
    REQUIRE(fclose(file) == 0); file = NULL;
    printf("{\"checks\":%u,\"method\":%u,\"encryption\":%u,\"bytes\":%lld}\n",
           checks, method, encryption, (long long)size);
    result = 0;
done:
    if (file) fclose(file);
    if (reading) xx_format_free_archive_records_reading(&reader->format, reading);
    if (writing) xx_format_free_archive_records_writing(&writer->format, writing);
    xx_zip_free(reader); xx_zip_free(writer);
    xx_archive_record_cleanup(&record); xx_list_cleanup(&options);
    if (source) xx_io_close(source);
    if (output) xx_io_close(output);
    if (scoped) (void)xx_io_memory_only_end(&scope);
    free(bytes);
    return result;
}
