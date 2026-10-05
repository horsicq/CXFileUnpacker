/* SPDX-License-Identifier: MIT. Public engine adapter lifecycle tests. */
#include "xxfclib/formats/sevenzip_engine/xx_sevenzip_engine.h"
#include "xxfclib/io/xx_io.h"
#include "xxfclib/memory/xx_memory.h"
#include <stdio.h>
#include <string.h>

static unsigned checks;
#define REQUIRE(expression) do { ++checks; if (!(expression)) { fprintf(stderr, "check %u failed at line %u: %s\n", checks, __LINE__, #expression); goto done; } } while (0)
typedef struct proxy { xx_io_device device; xx_io_device *source; size_t reads; } proxy;
static ssize_t proxy_read(xx_io_device *device, void *buffer, size_t size) {
    proxy *p = (proxy *)device->priv;
    ++p->reads;
    return xx_io_read(p->source, buffer, size > 7U ? 7U : size);
}
static int proxy_seek64(xx_io_device *d, int64_t a, int w) { return xx_io_seek64(((proxy *)d->priv)->source, a, w); }
static int64_t proxy_tell(xx_io_device *d) { return xx_io_tell(((proxy *)d->priv)->source); }
static int64_t proxy_size(xx_io_device *d) { return xx_io_size(((proxy *)d->priv)->source); }
int main(int argc, char **argv) {
    xx_io_device *source = NULL;
    Abstractformat *format = NULL;
    xx_archive_record_state *state = NULL;
    xx_io_memory_only_scope scope = {0};
    bool scoped = false;
    proxy p = {0};
    xx_var limit;
    xx_var password;
    char *password_view = NULL;
    xx_pd_struct pd = xx_pd_init();
    unsigned members = 0;
    int result = 1;
    xx_var_init(&limit);
    xx_var_init(&password);
    REQUIRE(argc >= 3);
    REQUIRE((source = xx_io_file_open(argv[1], "rb")) != NULL);
    p.source = source; p.device.read = proxy_read; p.device.seek64 = proxy_seek64;
    p.device.tell = proxy_tell; p.device.total_size = proxy_size; p.device.priv = &p;
    REQUIRE((format = xx_sevenzip_engine_create(&p.device, 0, strcmp(argv[2], "auto") ? argv[2] : NULL)) != NULL);
    REQUIRE(xx_sevenzip_engine_set_source_path(format, argv[1]));
    if (argc > 3) {
        size_t size = strlen(argv[3]);
        password_view = (char *)xx_mem_alloc(size ? size : 1U);
        REQUIRE(password_view != NULL);
        if (size) memcpy(password_view, argv[3], size);
        xx_var_set_str_view(&password, password_view, size); /* Exact, nonterminated credential. */
        REQUIRE(xx_format_set_extra_parameter(format, XX_META_ID_OPT_PASSWORD, &password));
    }
    REQUIRE(xx_io_seek64(source, 11, SEEK_SET) == 0);
    REQUIRE(xx_io_memory_only_begin(&scope, 8U * 1024U * 1024U)); scoped = true;
    REQUIRE(xx_format_handle_base_info(format, &pd));
    REQUIRE(xx_io_tell(source) == 11);
    REQUIRE(xx_sevenzip_engine_get_handler(format) != NULL);
    REQUIRE((state = xx_format_create_archive_records_reading(format, NULL, &pd)) != NULL);
    REQUIRE(xx_io_tell(source) == 11);
    while (state->has_record) {
        size_t before;
        const xx_archive_record *record = xx_format_get_current_archive_record(format, state);
        REQUIRE(record && xx_archive_record_get_original_name(record));
        /* A newly lowered live limit must fail before reading even for a
         * directory or an empty member, then a cleared limit must retry. */
        xx_var_set_u64(&limit, 1);
        REQUIRE(xx_format_set_extra_parameter(format, XX_META_ID_OPT_MEMORY_LIMIT, &limit));
        before = p.reads;
        REQUIRE(!xx_format_unpack_current_archive_record(format, state, &pd));
        REQUIRE(p.reads == before && xx_io_tell(source) == 11);
        REQUIRE(xx_format_remove_extra_parameter(format, XX_META_ID_OPT_MEMORY_LIMIT));
        pd = xx_pd_init();
        REQUIRE(xx_format_unpack_current_archive_record(format, state, &pd));
        REQUIRE(xx_io_tell(source) == 11);
        ++members;
        if (!xx_format_archive_record_move_to_next(format, state, &pd)) break;
    }
    REQUIRE(members == state->total_records);
    REQUIRE(xx_io_memory_only_used() == 0);
    REQUIRE(xx_io_memory_only_end(&scope)); scoped = false;
    if (argc > 4) {
        xx_list_s options;
        xx_meta output_path;
        char *borrowed;
        size_t size = strlen(argv[4]);
        xx_format_free_archive_records_reading(format, state); state = NULL;
        REQUIRE(xx_list_init(&options, sizeof(xx_meta), xx_meta_free_elem));
        borrowed = (char *)xx_mem_alloc(size ? size : 1U);
        REQUIRE(borrowed != NULL);
        if (size) memcpy(borrowed, argv[4], size);
        xx_meta_init(&output_path, XX_META_ID_OPT_UNPACK_PATH);
        xx_var_set_str_view(&output_path.var, borrowed, size); /* No terminating NUL. */
        REQUIRE(xx_list_append(&options, &output_path));
        state = xx_format_create_archive_records_reading(format, &options, &pd);
        xx_list_cleanup(&options); xx_mem_free(borrowed);
        REQUIRE(state != NULL);
        while (state->has_record) {
            REQUIRE(xx_format_unpack_current_archive_record(format, state, &pd));
            REQUIRE(xx_io_tell(source) == 11);
            if (!xx_format_archive_record_move_to_next(format, state, &pd)) break;
        }
    }
    printf("{\"checks\":%u,\"members\":%u,\"handler\":\"%s\"}\n", checks, members, xx_sevenzip_engine_get_handler(format));
    result = 0;
done:
    if (state) xx_format_free_archive_records_reading(format, state);
    xx_sevenzip_engine_free(format);
    xx_var_cleanup(&limit);
    xx_var_cleanup(&password); xx_mem_free(password_view);
    if (source) xx_io_close(source);
    if (scoped) (void)xx_io_memory_only_end(&scope);
    return result;
}
