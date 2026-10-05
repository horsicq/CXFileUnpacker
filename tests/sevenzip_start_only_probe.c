/* SPDX-License-Identifier: MIT. Start-only policy and cache lifecycle controls. */
#include <xxfclib/formats/sevenzip_engine/xx_sevenzip_engine.h>
#include <xxfclib/io/xx_io.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define REQUIRE(expression) do { ++checks; if (!(expression)) { fprintf(stderr, "check %u failed at line %u: %s\n", checks, __LINE__, #expression); goto done; } } while (0)
int main(int argc, char **argv) {
    xx_io_device *source = NULL;
    Abstractformat *format = NULL;
    xx_archive_record_state *state = NULL;
    xx_io_memory_only_scope scope = {0};
    xx_pd_struct pd = xx_pd_init();
    const char *handler;
    int64_t base;
    int result = 1;
    bool scoped = false;
    REQUIRE(argc == 4);
    handler = strcmp(argv[2], "auto") ? argv[2] : NULL;
    base = (int64_t)strtoll(argv[3], NULL, 10);
    REQUIRE(base > 11);
    REQUIRE((source = xx_io_file_open(argv[1], "rb")) != NULL);
    REQUIRE(xx_io_seek64(source, 11, SEEK_SET) == 0);
    REQUIRE(xx_io_memory_only_begin(&scope, 8U * 1024U * 1024U)); scoped = true;
    REQUIRE((format = xx_sevenzip_engine_create(source, 0, handler)) != NULL);
    REQUIRE(xx_sevenzip_engine_set_source_path(format, argv[1]));
    REQUIRE(xx_format_handle_base_info(format, &pd));
    REQUIRE(format->base_info_handled && format->is_valid);
    REQUIRE(xx_sevenzip_engine_get_handler(format) != NULL);
    REQUIRE(xx_io_tell(source) == 11);
    REQUIRE((state = xx_format_create_archive_records_reading(format, NULL, &pd)) != NULL);
    REQUIRE(state->has_record);
    REQUIRE(xx_format_unpack_current_archive_record(format, state, &pd));
    REQUIRE(xx_io_tell(source) == 11);
    REQUIRE(xx_sevenzip_engine_set_start_only(format, false));
    REQUIRE(format->base_info_handled && format->is_valid);
    REQUIRE(xx_sevenzip_engine_set_start_only(format, true));
    REQUIRE(!format->base_info_handled && !format->is_valid && format->format_size == -1);
    REQUIRE(handler ? !strcmp(xx_sevenzip_engine_get_handler(format), handler) :
                      xx_sevenzip_engine_get_handler(format) == NULL);
    /* An existing iterator must also pass the new policy to READ. */
    REQUIRE(!xx_format_unpack_current_archive_record(format, state, &pd));
    REQUIRE(xx_sevenzip_engine_get_status(format) == XX_SEVENZIP_BACKEND_FORMAT);
    REQUIRE(xx_io_tell(source) == 11);
    pd = xx_pd_init();
    REQUIRE(!xx_format_is_valid(format, &pd));
    REQUIRE(!xx_format_handle_base_info(format, &pd));
    REQUIRE(!format->base_info_handled && !format->is_valid);
    REQUIRE(xx_io_tell(source) == 11);
    REQUIRE(xx_sevenzip_engine_set_start_only(format, false));
    pd = xx_pd_init();
    REQUIRE(xx_format_handle_base_info(format, &pd));
    REQUIRE(format->base_info_handled && format->is_valid);
    REQUIRE(xx_format_unpack_current_archive_record(format, state, &pd));
    REQUIRE(xx_io_tell(source) == 11);
    xx_format_free_archive_records_reading(format, state); state = NULL;
    xx_sevenzip_engine_free(format); format = NULL;
    /* "Start" means the borrowed base address, not physical device byte 0. */
    REQUIRE((format = xx_sevenzip_engine_create(source, base, handler)) != NULL);
    REQUIRE(xx_sevenzip_engine_set_source_path(format, argv[1]));
    REQUIRE(xx_sevenzip_engine_set_start_only(format, true));
    pd = xx_pd_init();
    REQUIRE(xx_format_handle_base_info(format, &pd));
    REQUIRE((state = xx_format_create_archive_records_reading(format, NULL, &pd)) != NULL);
    REQUIRE(state->has_record);
    REQUIRE(xx_format_unpack_current_archive_record(format, state, &pd));
    REQUIRE(xx_io_tell(source) == 11);
    REQUIRE(xx_sevenzip_engine_set_start_only(format, true));
    REQUIRE(format->base_info_handled && format->is_valid);
    REQUIRE(xx_io_memory_only_used() == 0);
    REQUIRE(xx_io_memory_only_end(&scope)); scoped = false;
    printf("{\"checks\":%u,\"start_only\":true,\"cache_invalidated\":true,\"retained_iterator_read\":true,\"nonzero_base\":true}\n", checks);
    result = 0;
done:
    if (state) xx_format_free_archive_records_reading(format, state);
    xx_sevenzip_engine_free(format);
    if (source) xx_io_close(source);
    if (scoped) (void)xx_io_memory_only_end(&scope);
    return result;
}
