/* SPDX-License-Identifier: MIT. Native FSB playable audio and RAM-only tests. */
#include <xxfclib/formats/fmod_sample_bank/xx_fmod_sample_bank.h>
#include <xxfclib/io/xx_io.h>
#include <xxfclib/memory/xx_memory.h>
#include <stdio.h>
#include <string.h>
static unsigned checks;
#define REQUIRE(expression) do { ++checks; if (!(expression)) { fprintf(stderr, "check %u failed at line %u: %s\n", checks, __LINE__, #expression); goto done; } } while (0)
int main(int argc, char **argv) {
    xx_io_device *source = NULL; xx_fmod_sample_bank *bank = NULL; Abstractformat *format = NULL;
    xx_archive_record_state *state = NULL; xx_io_memory_only_scope scope = {0};
    xx_var limit; xx_pd_struct pd = xx_pd_init(); bool scoped = false;
    unsigned members = 0; int result = 1;
    xx_var_init(&limit);
    REQUIRE(argc == 3);
    REQUIRE((source = xx_io_file_open(argv[1], "rb")) != NULL);
    REQUIRE(xx_io_seek64(source, 11, SEEK_SET) == 0);
    REQUIRE(xx_io_memory_only_begin(&scope, 512U * 1024U)); scoped = true;
    REQUIRE((bank = xx_fmod_sample_bank_create(source, 0)) != NULL); format = &bank->format;
    REQUIRE(xx_format_handle_base_info(format, &pd));
    REQUIRE(xx_io_tell(source) == 11);
    REQUIRE((state = xx_format_create_archive_records_reading(format, NULL, &pd)) != NULL);
    REQUIRE(xx_io_tell(source) == 11);
    while (state->has_record) {
        const xx_archive_record *record = xx_format_get_current_archive_record(format, state);
        REQUIRE(record && xx_archive_record_get_original_name(record));
        xx_var_set_u64(&limit, 1);
        REQUIRE(xx_format_set_extra_parameter(format, XX_META_ID_OPT_MEMORY_LIMIT, &limit));
        REQUIRE(!xx_format_unpack_current_archive_record(format, state, &pd));
        REQUIRE(xx_io_tell(source) == 11);
        REQUIRE(xx_format_remove_extra_parameter(format, XX_META_ID_OPT_MEMORY_LIMIT));
        REQUIRE(xx_format_set_extra_parameter(format, XX_META_ID_OPT_MAX_MEMBER_SIZE, &limit));
        REQUIRE(!xx_format_unpack_current_archive_record(format, state, &pd));
        REQUIRE(xx_io_tell(source) == 11);
        REQUIRE(xx_format_remove_extra_parameter(format, XX_META_ID_OPT_MAX_MEMBER_SIZE));
        REQUIRE(xx_format_unpack_current_archive_record(format, state, &pd));
        REQUIRE(xx_io_tell(source) == 11);
        ++members;
        if (!xx_format_archive_record_move_to_next(format, state, &pd)) break;
    }
    REQUIRE(members == state->total_records);
    REQUIRE(xx_io_memory_only_used() == 0);
    REQUIRE(xx_io_memory_only_end(&scope)); scoped = false;
    xx_format_free_archive_records_reading(format, state); state = NULL;
    {
        xx_list_s options; xx_meta path; size_t length = strlen(argv[2]);
        char *borrowed = (char *)xx_mem_alloc(length ? length : 1U);
        REQUIRE(borrowed != NULL);
        if (length) memcpy(borrowed, argv[2], length);
        REQUIRE(xx_list_init(&options, sizeof(xx_meta), xx_meta_free_elem));
        xx_meta_init(&path, XX_META_ID_OPT_UNPACK_PATH); xx_var_set_str_view(&path.var, borrowed, length);
        REQUIRE(xx_list_append(&options, &path));
        state = xx_format_create_archive_records_reading(format, &options, &pd);
        xx_list_cleanup(&options); xx_mem_free(borrowed);
        REQUIRE(state != NULL);
        while (state->has_record) {
            REQUIRE(xx_format_unpack_current_archive_record(format, state, &pd));
            REQUIRE(xx_io_tell(source) == 11);
            if (!xx_format_archive_record_move_to_next(format, state, &pd)) break;
        }
    }
    printf("{\"checks\":%u,\"members\":%u}\n", checks, members); result = 0;
done:
    if (state) xx_format_free_archive_records_reading(format, state);
    xx_fmod_sample_bank_free(bank); xx_var_cleanup(&limit);
    if (source) xx_io_close(source);
    if (scoped) (void)xx_io_memory_only_end(&scope);
    return result;
}
