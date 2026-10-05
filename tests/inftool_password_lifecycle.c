/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 * Persistent-reader password lifecycle using an independently encoded MRI
 * fixture supplied by inftool_legacy_zip_regression.py. No output files.
 */
#include "xxfclib/formats/sfx_inftool/xx_sfx_inftool.h"
#include "xxfclib/io/xx_io.h"
#include <stdio.h>

int main(int argc, char **argv) {
    const char *passwords[] = {"fixture-secret", NULL, "wrong", "fixture-secret", NULL};
    const bool expected[] = {true, false, false, true, false};
    xx_io_device *device = NULL;
    xx_sfx_inftool *archive = NULL;
    unsigned round;
    int result = 1;
    if (argc != 2) { fprintf(stderr, "usage: inftool_password_lifecycle FIXTURE\n"); return 2; }
    device = xx_io_file_open(argv[1], "rb");
    if (!device || !(archive = xx_sfx_inftool_create(device, 0)) ||
        !xx_sfx_inftool_handle_base_info(&archive->format, NULL) ||
        archive->format.number_of_archive_records != 2 || !archive->zip_ready) goto done;
    for (round = 0; round < sizeof(expected) / sizeof(expected[0]); ++round) {
        xx_archive_record_state *state;
        unsigned count = 0;
        bool failed = false;
        if (!xx_format_set_password(&archive->format, passwords[round]) ||
            !(state = xx_format_create_archive_records_reading(&archive->format, NULL, NULL))) goto done;
        if (!archive->format.is_valid || !archive->format.base_info_handled ||
            !xx_format_is_valid(&archive->format, NULL)) {
            xx_format_free_archive_records_reading(&archive->format, state);
            fprintf(stderr, "password lifecycle round %u left invalid base flags\n", round);
            goto done;
        }
        while (state->has_record) {
            const xx_archive_record *record = xx_format_get_current_archive_record(&archive->format, state);
            bool decoded;
            if (!record || !xx_archive_record_get_meta_bool(record, XX_META_ID_IS_ENCRYPTED, false)) {
                failed = true; break;
            }
            decoded = xx_format_unpack_current_archive_record(&archive->format, state, NULL);
            if (decoded != expected[round]) { failed = true; break; }
            ++count;
            if (!xx_format_archive_record_move_to_next(&archive->format, state, NULL)) break;
        }
        xx_format_free_archive_records_reading(&archive->format, state);
        if (failed || count != 2) {
            fprintf(stderr, "password lifecycle round %u failed (%u members)\n", round, count);
            goto done;
        }
    }
    puts("INFTool persistent reader: correct, cleared, wrong, correct, cleared password passed");
    result = 0;
done:
    xx_sfx_inftool_free(archive);
    if (device) xx_io_close(device);
    return result;
}
