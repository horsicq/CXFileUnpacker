/* SPDX-License-Identifier: MIT */
#include "xxfclib/formats/chromium_pak/xx_chromium_pak.h"
#include "xxfclib/formats/windows_thumbnail_cache/xx_windows_thumbnail_cache.h"
#include "xxfclib/formats/enigma_virtual_box/xx_enigma_virtual_box.h"
#include "xxfclib/formats/kgb_archiver/xx_kgb_archiver.h"
#include "xxfclib/formats/microsoft_lit/xx_microsoft_lit.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    xx_io_device *device;
    Abstractformat *format = NULL;
    xx_archive_record_state *state;
    xx_list_s options;
    xx_pd_struct pd;
    xx_io_memory_only_scope scope = {0};
    uint64_t count = 0;
    bool valid = true, memory = argc == 3 || (argc >= 4 && !strcmp(argv[3], "-"));
    if (argc < 3 || argc > 6) return 90;
    device = xx_io_file_open(argv[2], "rb");
    if (!device) return 91;
    if (!strcmp(argv[1], "chromium")) format = (Abstractformat *)xx_chromium_pak_create(device, 0);
    if (!strcmp(argv[1], "thumbnail")) format = (Abstractformat *)xx_windows_thumbnail_cache_create(device, 0);
    if (!strcmp(argv[1], "enigma")) format = (Abstractformat *)xx_enigma_virtual_box_create(device, 0);
    if (!strcmp(argv[1], "kgb")) format = (Abstractformat *)xx_kgb_archiver_create(device, 0);
    if (!strcmp(argv[1], "lit")) format = (Abstractformat *)xx_microsoft_lit_create(device, 0);
    pd = xx_pd_init();
    xx_list_init(&options, sizeof(xx_meta), xx_meta_free_elem);
    if (argc >= 4 && !memory) {
        xx_meta path;
        xx_meta_init(&path, XX_META_ID_OPT_UNPACK_PATH);
        xx_var_set_str(&path.var, argv[3]);
        if (!xx_list_append(&options, &path)) return 92;
    }
    if (argc >= 5) {
        xx_meta password;
        xx_meta_init(&password, XX_META_ID_OPT_PASSWORD);
        xx_var_set_str(&password.var, argv[4]);
        if (!xx_list_append(&options, &password)) return 92;
    }
    if (argc == 6) {
        xx_meta limit;
        xx_meta_init(&limit, XX_META_ID_OPT_MEMORY_LIMIT);
        xx_var_set_u64(&limit.var, strtoull(argv[5], NULL, 10));
        if (!xx_list_append(&options, &limit)) return 92;
    }
    if (memory && !xx_io_memory_only_begin(&scope, UINT64_C(256) * 1024 * 1024)) return 93;
    if (!format || !xx_format_is_valid(format, &pd) || !xx_format_handle_base_info(format, &pd)) { valid = false; goto done; }
    state = xx_format_create_archive_records_reading(format, &options, &pd);
    if (!state) { valid = false; goto done; }
    while (state->has_record) {
        const xx_archive_record *record = xx_format_get_current_archive_record(format, state);
        printf("%s|%lld\n", xx_archive_record_get_original_name(record), (long long)record->compressed_size);
        ++count;
        if (!xx_format_unpack_current_archive_record(format, state, &pd)) { valid = false; }
        if (!xx_format_archive_record_move_to_next(format, state, &pd)) break;
    }
    if (count != xx_format_get_number_of_archive_records(format, &pd)) valid = false;
    xx_format_free_archive_records_reading(format, state);
done:
    if (!valid && pd.last_error) fprintf(stderr, "%s\n", pd.error_string);
    if (memory && !xx_io_memory_only_end(&scope)) valid = false;
    if (format) {
        if (!strcmp(argv[1], "chromium")) xx_chromium_pak_free((xx_chromium_pak *)format);
        if (!strcmp(argv[1], "thumbnail")) xx_windows_thumbnail_cache_free((xx_windows_thumbnail_cache *)format);
        if (!strcmp(argv[1], "enigma")) xx_enigma_virtual_box_free((xx_enigma_virtual_box *)format);
        if (!strcmp(argv[1], "kgb")) xx_kgb_archiver_free((xx_kgb_archiver *)format);
        if (!strcmp(argv[1], "lit")) xx_microsoft_lit_free((xx_microsoft_lit *)format);
    }
    xx_list_cleanup(&options); xx_io_close(device);
    return valid ? 0 : 1;
}
