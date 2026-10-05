/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 *
 * Read-only corpus metadata probe. Metadata-only by default; --verify invokes
 * audited member callbacks without output paths and reports their limitations.
 * Some readers decode directory/runtime data as part of validation; use an
 * external process time/memory limit when probing untrusted files.
 * Exit 0 means that a JSON report was emitted, including failed probes.
 */
#include "xxfc_readers.h"
#include <xxfclib/strings/xx_string.h>
#include <xxfclib/global/xx_global.h>
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#include <shellapi.h>
#endif

#define MAX_RECORD_LIMIT UINT64_C(1000000)
#define SAMPLE_COUNT 3U
#define SAMPLE_BYTES 1024U
#define DEFAULT_MEMBER_LIMIT UINT64_C(1073741824)
#define DEFAULT_MEMORY_LIMIT UINT64_C(268435456)
#define IVT_BUFFER_LIMIT UINT64_C(268435456)

typedef struct {
    const char *path;
    const char *status;
    const char *selection;
    const char *reader;
    xx_file_type_t detected;
    xx_file_type_t selected;
    int64_t file_size;
    int valid, parsed, archive, crypted, incomplete;
    int iteration_exhausted, iteration_complete;
    int64_t declared_count;
    uint64_t format_count, members, directories;
    uint64_t encrypted_members, encryption_metadata;
    uint64_t known_unpacked, max_unpacked, unknown_sizes;
    uint64_t record_limit;
    bool record_limit_hit, size_overflow, names_truncated;
    bool verify_requested, verify_supported, verify_attempted;
    const char *verification_integrity;
    const char *verification_limitation;
    uint64_t verified_members, failed_members, skipped_encrypted, limited_members;
    uint64_t member_size_limit, memory_limit;
    int first_error_code;
    char first_error_text[128];
    int64_t first_failed_member;
    size_t names_count;
    char names[SAMPLE_COUNT][SAMPLE_BYTES + 1U];
} probe_report;

static void json_bool(int value) {
    fputs(value < 0 ? "null" : value ? "true" : "false", stdout);
}

/* Preserve valid UTF-8; byte-escape malformed legacy names so every report
 * remains JSON even when an old reader returns a non-UTF-8 narrow string. */
static void json_string(const char *value) {
    const unsigned char *at = (const unsigned char *)(value ? value : "");
    putchar('"');
    while (*at) {
        size_t count = 0U, i;
        unsigned char c = *at;
        if (c == '"' || c == '\\') {
            putchar('\\'); putchar(c); ++at;
        } else if (c < 0x20U) {
            printf("\\u%04x", (unsigned)c); ++at;
        } else if (c < 0x80U) {
            putchar(c); ++at;
        } else {
            if (c >= 0xc2U && c <= 0xdfU) count = 2U;
            else if (c >= 0xe0U && c <= 0xefU) count = 3U;
            else if (c >= 0xf0U && c <= 0xf4U) count = 4U;
            for (i = 1U; i < count; ++i)
                if (at[i] < 0x80U || at[i] > 0xbfU) break;
            if (count && i == count &&
                !(c == 0xe0U && at[1] < 0xa0U) &&
                !(c == 0xedU && at[1] > 0x9fU) &&
                !(c == 0xf0U && at[1] < 0x90U) &&
                !(c == 0xf4U && at[1] > 0x8fU)) {
                fwrite(at, 1U, count, stdout); at += count;
            } else {
                printf("\\u%04x", (unsigned)c); ++at;
            }
        }
    }
    putchar('"');
}

static void report_json(const probe_report *r) {
    size_t i;
    int encrypted = r->encrypted_members ? 1 :
        r->iteration_complete == 1 && r->encryption_metadata == r->members ? 0 : -1;
    int verified = r->failed_members ? 0 :
        r->verify_attempted && r->iteration_complete == 1 &&
        !r->skipped_encrypted && !r->limited_members ? 1 : -1;
    printf("{\"schema_version\":1,\"path\":"); json_string(r->path);
    printf(",\"status\":"); json_string(r->status);
    printf(",\"file_size\":%" PRId64, r->file_size);
    printf(",\"detected_type_id\":%d,\"detected_type_name\":", (int)r->detected);
    json_string(xx_format_file_type_to_string(r->detected));
    printf(",\"selected_type_id\":%d,\"selected_type_name\":", (int)r->selected);
    json_string(xx_format_file_type_to_string(r->selected));
    printf(",\"selection_method\":"); json_string(r->selection);
    printf(",\"reader\":");
    if (r->reader) json_string(r->reader); else fputs("null", stdout);
    printf(",\"valid\":"); json_bool(r->valid);
    printf(",\"parsed\":"); json_bool(r->parsed);
    printf(",\"is_archive\":"); json_bool(r->archive);
    printf(",\"format_encrypted\":"); json_bool(r->crypted);
    printf(",\"incomplete\":"); json_bool(r->incomplete);
    printf(",\"format_member_count\":");
    if (r->parsed == 1) printf("%" PRIu64, r->format_count); else fputs("null", stdout);
    printf(",\"declared_member_count\":");
    if (r->declared_count >= 0) printf("%" PRId64, r->declared_count); else fputs("null", stdout);
    printf(",\"member_count\":%" PRIu64, r->members);
    printf(",\"directory_count\":%" PRIu64, r->directories);
    printf(",\"record_iterator_exhausted\":"); json_bool(r->iteration_exhausted);
    printf(",\"member_iteration_complete\":"); json_bool(r->iteration_complete);
    printf(",\"record_limit\":%" PRIu64, r->record_limit);
    printf(",\"record_limit_hit\":"); json_bool(r->record_limit_hit);
    printf(",\"encrypted_member_count\":%" PRIu64, r->encrypted_members);
    printf(",\"members_with_encryption_metadata\":%" PRIu64, r->encryption_metadata);
    printf(",\"any_encrypted_members\":"); json_bool(encrypted);
    printf(",\"declared_unpacked_bytes\":");
    if (r->iteration_complete == 1 && !r->unknown_sizes && !r->size_overflow)
        printf("%" PRIu64, r->known_unpacked);
    else fputs("null", stdout);
    printf(",\"known_unpacked_bytes\":%" PRIu64, r->known_unpacked);
    printf(",\"max_unpacked_member\":");
    if (r->members > r->unknown_sizes || r->iteration_complete == 1)
        printf("%" PRIu64, r->max_unpacked);
    else fputs("null", stdout);
    printf(",\"members_with_unknown_unpacked_size\":%" PRIu64, r->unknown_sizes);
    printf(",\"unpacked_size_overflow\":"); json_bool(r->size_overflow);
    printf(",\"names_sample\":[");
    for (i = 0U; i < r->names_count; ++i) {
        if (i) putchar(',');
        json_string(r->names[i]);
    }
    printf("],\"names_sample_truncated\":"); json_bool(r->names_truncated);
    printf(",\"verification_requested\":"); json_bool(r->verify_requested);
    printf(",\"verification_supported\":"); json_bool(r->verify_supported);
    printf(",\"verification_attempted\":"); json_bool(r->verify_attempted);
    printf(",\"verification_passed\":"); json_bool(verified);
    printf(",\"verification_integrity\":"); json_string(r->verification_integrity);
    printf(",\"verification_limitations\":[");
    if (r->verification_limitation) json_string(r->verification_limitation);
    putchar(']');
    printf(",\"verified_members\":%" PRIu64, r->verified_members);
    printf(",\"failed_members\":%" PRIu64, r->failed_members);
    printf(",\"verification_skipped_encrypted_members\":%" PRIu64, r->skipped_encrypted);
    printf(",\"verification_limited_members\":%" PRIu64, r->limited_members);
    printf(",\"maximum_member_size\":%" PRIu64, r->member_size_limit);
    printf(",\"memory_limit\":%" PRIu64, r->memory_limit);
    printf(",\"first_error_code\":%d,\"first_error_text\":", r->first_error_code);
    if (r->first_error_code) json_string(r->first_error_text); else fputs("null", stdout);
    printf(",\"first_failed_member_index\":");
    if (r->first_failed_member >= 0) printf("%" PRId64, r->first_failed_member);
    else fputs("null", stdout);
    fputs("}\n", stdout);
}

static void remember_name(probe_report *r, const xx_archive_record *record) {
    const char *name;
    const wchar_t *wide;
    char *owned = NULL;
    size_t i = 0U;
    if (r->names_count == SAMPLE_COUNT) return;
    name = xx_archive_record_get_original_name(record);
    if (!name || !*name) {
        wide = xx_archive_record_get_original_name_w(record);
        if (wide && *wide) {
            wchar_t bounded[257];
            while (i < 256U && wide[i]) { bounded[i] = wide[i]; ++i; }
            bounded[i] = 0;
            if (i == 256U && wide[i]) r->names_truncated = true;
            owned = xx_str_unicode_to_utf8(bounded);
            name = owned;
        }
    }
    if (!name || !*name) name = "<unnamed>";
    i = 0U;
    while (i < SAMPLE_BYTES && name[i]) {
        r->names[r->names_count][i] = name[i]; ++i;
    }
    r->names[r->names_count][i] = 0;
    if (i == SAMPLE_BYTES && name[i]) r->names_truncated = true;
    ++r->names_count;
    xx_str_free(owned);
}

static void record_metadata(probe_report *r, const xx_archive_record *record) {
    uint64_t size = xx_archive_record_get_meta_u64(record,
        XX_META_ID_UNCOMPRESSED_SIZE, UINT64_MAX);
    ++r->members;
    if (xx_archive_record_get_meta_bool(record, XX_META_ID_IS_FOLDER, false))
        ++r->directories;
    if (xx_archive_record_find_meta(record, XX_META_ID_IS_ENCRYPTED)) {
        ++r->encryption_metadata;
        if (xx_archive_record_get_meta_bool(record, XX_META_ID_IS_ENCRYPTED, false))
            ++r->encrypted_members;
    }
    if (size == UINT64_MAX) ++r->unknown_sizes;
    else {
        if (UINT64_MAX - r->known_unpacked < size) {
            r->size_overflow = true;
            r->known_unpacked = UINT64_MAX;
        }
        else r->known_unpacked += size;
        if (size > r->max_unpacked) r->max_unpacked = size;
    }
    remember_name(r, record);
}

static bool limit_option(xx_list_t *options, xx_meta_id_t id, uint64_t value) {
    xx_meta meta;
    xx_meta_init(&meta, id);
    xx_var_set_u64(&meta.var, value);
    if (!xx_list_append(options, &meta)) {
        xx_meta_cleanup(&meta);
        return false;
    }
    return true;
}

static void first_error(probe_report *r, int code, const char *text) {
    if (r->first_error_code) return;
    r->first_error_code = code ? code : XXFC_ERR_GENERIC;
    snprintf(r->first_error_text, sizeof(r->first_error_text), "%s",
        text && *text ? text : "Member verification returned false without a detailed reader error");
    r->first_failed_member = (int64_t)r->members - 1;
}

static void verification_contract(probe_report *r) {
    r->verification_integrity = "no_audited_no_output_contract";
    r->verification_limitation = "No member unpack callback is invoked for this reader.";
    if (!r->reader) return;
    if (!strcmp(r->reader, "zip")) {
        r->verify_supported = true;
        r->verification_integrity = "decode_size_crc32";
        r->verification_limitation = NULL;
    } else if (!strcmp(r->reader, "ivt")) {
        r->verify_supported = true;
        r->verification_integrity = "decode_size_mszip_framing_no_format_checksum";
        r->verification_limitation = "IVT has no member checksum; stored reads or complete MSZIP block framing and sizes are checked.";
    } else if (!strcmp(r->reader, "lha")) {
        r->verify_supported = true;
        r->verification_integrity = "decode_size_only_crc_unverified";
        r->verification_limitation = "The current LHA reader checks header integrity and decoded size but ignores payload CRC16, including in native extraction.";
    } else if (!strcmp(r->reader, "silmarilsft")) {
        r->verify_supported = true;
        r->verification_integrity = "decode_size_token_framing_no_format_checksum";
        r->verification_limitation = "No payload checksum; existing bitstream rules permit a zero final byte, token clamping, and at most four missing or unread stream bytes.";
    } else if (!strcmp(r->reader, "gst")) {
        r->verify_supported = true;
        r->verification_integrity = "decode_size_crc32";
        r->verification_limitation = NULL;
    }
}

/* Strict allowlist: these implementations were inspected and their no-path
 * branches decode/validate, then discard. Other readers may return success
 * without decoding when no output path is supplied. Do not call them here. */
static void verify_record(probe_report *r, xxfc_opened *opened,
                          xx_archive_record_state *state,
                          const xx_archive_record *record, xx_pd_struct *pd) {
    uint64_t plain = xx_archive_record_get_meta_u64(record,
        XX_META_ID_UNCOMPRESSED_SIZE, UINT64_MAX);
    if (!r->verify_requested || !r->verify_supported) return;
    if (xx_archive_record_get_meta_bool(record, XX_META_ID_IS_ENCRYPTED, false)) {
        ++r->skipped_encrypted;
        return;
    }
    if (plain != UINT64_MAX && plain > r->member_size_limit) {
        ++r->limited_members;
        first_error(r, XXFC_ERR_OUT_OF_BOUNDS, "Declared member size exceeds the probe verification limit");
        return;
    }
    /* These readers do not read the shared limit options. They hold packed
     * and decoded buffers simultaneously. Plaintext is capped at 256 MiB;
     * packed allocation is additionally bounded here by the memory budget. */
    if ((!strcmp(opened->reader_name, "ivt") ||
         !strcmp(opened->reader_name, "lha") ||
         !strcmp(opened->reader_name, "gst")) &&
        (plain == UINT64_MAX || record->compressed_size < 0 ||
         plain > IVT_BUFFER_LIMIT ||
         (!strcmp(opened->reader_name, "ivt") &&
          (uint64_t)record->compressed_size > IVT_BUFFER_LIMIT) ||
         plain > r->memory_limit ||
         (uint64_t)record->compressed_size > r->memory_limit - plain)) {
        ++r->limited_members;
        first_error(r, XXFC_ERR_OUT_OF_BOUNDS, "Member exceeds the probe memory or intrinsic decoder buffer limit");
        return;
    }
    /* Silmarils reads packed bytes in one configured I/O chunk and allocates
     * only its plaintext, limited by the format's 24-bit size field. */
    if (!strcmp(opened->reader_name, "silmarilsft") &&
        (plain == UINT64_MAX || plain > UINT64_C(0xffffff) ||
         plain > r->memory_limit ||
         (uint64_t)xx_get_file_buffer_size() > r->memory_limit - plain)) {
        ++r->limited_members;
        first_error(r, XXFC_ERR_OUT_OF_BOUNDS, "Silmarils plaintext and I/O chunk exceed the probe memory or intrinsic size limit");
        return;
    }
    xx_pd_clear_error(pd);
    r->verify_attempted = true;
    if (xx_format_unpack_current_archive_record(opened->format, state, pd))
        ++r->verified_members;
    else {
        ++r->failed_members;
        first_error(r, pd->last_error, pd->error_string);
    }
}

static void run_probe(probe_report *r, const char *reader_name) {
    xx_io_device *device = xx_io_file_open(r->path, "rb");
    xxfc_opened opened = {0};
    xx_pd_struct pd = xx_pd_init();
    xx_archive_record_state *state = NULL;
    xx_list_t options;
    bool extension_opened = false;
    if (!device) { r->status = "open_failed"; return; }
    r->file_size = xx_io_size(device);
    r->detected = xx_format_get_file_type_device_fast(device, r->path);
    if (reader_name) {
        r->selection = "named_reader";
        if (!xxfc_open_named(&opened, device, 0, reader_name)) {
            r->status = "unknown_reader"; goto cleanup;
        }
    } else {
        r->selection = "content";
        if (xx_format_get_file_type_extension(r->path) != XX_FILE_TYPE_UNKNOWN) {
            extension_opened = xxfc_open_extension_fast(&opened, device, 0, r->path, &pd);
            if (extension_opened) r->selection = "validated_extension";
            else r->detected = xx_format_get_file_type_device(device);
        }
        if (!extension_opened &&
            (r->detected == XX_FILE_TYPE_BINARY || r->detected == XX_FILE_TYPE_UNKNOWN)) {
            extension_opened = xxfc_open_extension(&opened, device, 0, r->path, &pd);
            if (extension_opened) r->selection = "validated_extension_fallback";
        }
        if (!extension_opened && !xxfc_open_type(&opened, device, 0, r->detected)) {
            r->status = r->detected == XX_FILE_TYPE_UNKNOWN ||
                r->detected == XX_FILE_TYPE_BINARY ? "unrecognized" : "reader_unavailable";
            goto cleanup;
        }
    }
    r->reader = opened.reader_name;
    verification_contract(r);
    r->selected = opened.type;
    r->valid = extension_opened || xx_format_is_valid(opened.format, &pd);
    r->crypted = opened.format->is_crypted;
    if (!r->valid) { r->status = "invalid"; goto cleanup; }
    r->archive = opened.format->is_archive;
    r->parsed = extension_opened || xx_format_handle_base_info(opened.format, &pd);
    r->crypted = opened.format->is_crypted;
    r->archive = opened.format->is_archive;
    if (!r->parsed) { r->status = "parse_failed"; goto cleanup; }
    {
        xx_file_type_t actual = xx_format_get_file_type(opened.format);
        if (actual != XX_FILE_TYPE_UNKNOWN && actual != XX_FILE_TYPE_BINARY)
            r->selected = actual;
    }
    r->format_count = opened.format->number_of_archive_records;
    r->incomplete = xxfc_is_incomplete(&opened);
    if (!r->archive) { r->status = "not_archive"; goto cleanup; }
    xx_list_init(&options, sizeof(xx_meta), xx_meta_free_elem);
    if (r->verify_requested && r->verify_supported &&
        (!limit_option(&options, XX_META_ID_OPT_MAX_MEMBER_SIZE, r->member_size_limit) ||
         !limit_option(&options, XX_META_ID_OPT_MEMORY_LIMIT, r->memory_limit))) {
        xx_list_cleanup(&options);
        r->status = "option_allocation_failed";
        goto cleanup;
    }
    state = xx_format_create_archive_records_reading(opened.format,
        (const xx_list_s *)&options, &pd);
    xx_list_cleanup(&options);
    if (!state) { r->status = "records_unavailable"; goto cleanup; }
    r->declared_count = state->total_records;
    r->iteration_exhausted = 0;
    r->iteration_complete = 0;
    for (;;) {
        const xx_archive_record *record = xx_format_get_current_archive_record(opened.format, state);
        if (!record) { r->iteration_exhausted = 1; break; }
        if (r->members == r->record_limit) { r->record_limit_hit = true; break; }
        record_metadata(r, record);
        verify_record(r, &opened, state, record, &pd);
        if (!xx_format_archive_record_move_to_next(opened.format, state, &pd)) {
            r->iteration_exhausted = 1; break;
        }
    }
    r->incomplete = xxfc_is_incomplete(&opened);
    r->iteration_complete = r->iteration_exhausted && !r->incomplete &&
        !xx_pd_is_stopped(&pd) &&
        (r->declared_count < 0 || (uint64_t)r->declared_count == r->members);
    if (r->record_limit_hit) r->status = "record_limit";
    else if (r->incomplete) r->status = "incomplete";
    else if (!r->iteration_complete) r->status = "record_count_mismatch";
    else if (r->failed_members) r->status = "verification_failed";
    else if (r->limited_members) r->status = "verification_limited";
    else if (r->skipped_encrypted) r->status = "verification_skipped_encrypted";
    else r->status = "ok";
cleanup:
    if (state) xx_format_free_archive_records_reading(opened.format, state);
    xxfc_close(&opened);
    xx_io_close(device);
}

static int run_cli(int argc, char **argv) {
    probe_report report = {0};
    const char *reader = NULL;
    int i;
    report.status = "unrecognized";
    report.selection = "none";
    report.detected = report.selected = XX_FILE_TYPE_UNKNOWN;
    report.file_size = report.declared_count = -1;
    report.valid = report.parsed = report.archive = report.crypted = report.incomplete = -1;
    report.iteration_exhausted = report.iteration_complete = -1;
    report.record_limit = MAX_RECORD_LIMIT;
    report.member_size_limit = DEFAULT_MEMBER_LIMIT;
    report.memory_limit = DEFAULT_MEMORY_LIMIT;
    report.first_failed_member = -1;
    verification_contract(&report);
    if (argc < 2) goto usage;
    report.path = argv[1];
    for (i = 2; i < argc; ++i) {
        if (!strcmp(argv[i], "--reader") && i + 1 < argc && !reader) reader = argv[++i];
        else if (!strcmp(argv[i], "--verify")) report.verify_requested = true;
        else if ((!strcmp(argv[i], "--record-limit") ||
                  !strcmp(argv[i], "--max-member-size") ||
                  !strcmp(argv[i], "--memory-limit")) && i + 1 < argc) {
            char *end;
            unsigned long long value;
            const char *option = argv[i];
            const char *argument = argv[++i];
            if (*argument < '0' || *argument > '9') goto usage;
            errno = 0;
            value = strtoull(argument, &end, 10);
            if (errno || *end || !value) goto usage;
            if (!strcmp(option, "--record-limit")) {
                if (value > MAX_RECORD_LIMIT) goto usage;
                report.record_limit = (uint64_t)value;
            } else if (!strcmp(option, "--max-member-size")) report.member_size_limit = (uint64_t)value;
            else report.memory_limit = (uint64_t)value;
        } else goto usage;
    }
    run_probe(&report, reader);
    report_json(&report);
    return ferror(stdout) ? 2 : 0;
usage:
    fprintf(stderr, "Usage: probe_metadata <file> [--reader NAME] [--record-limit 1..1000000]\n"
        "       [--verify] [--max-member-size BYTES] [--memory-limit BYTES]\n"
        "No-output verification: ZIP/ZIP64, IVT, LHA, Silmarils and GST.\n"
        "LHA verifies decoded size only; payload CRC16 remains unchecked by its reader.\n");
    return 2;
}

int main(int argc, char **argv) {
#ifdef _WIN32
    wchar_t **wide;
    char **utf8;
    int count = 0, i, result;
    (void)argc; (void)argv;
    SetConsoleOutputCP(CP_UTF8);
    wide = CommandLineToArgvW(GetCommandLineW(), &count);
    if (!wide) return 2;
    utf8 = (char **)calloc((size_t)count + 1U, sizeof(*utf8));
    if (!utf8) { LocalFree(wide); return 2; }
    for (i = 0; i < count; ++i) {
        utf8[i] = xx_str_unicode_to_utf8(wide[i]);
        if (!utf8[i]) break;
    }
    LocalFree(wide);
    result = i == count ? run_cli(count, utf8) : 2;
    for (i = 0; i < count; ++i) xx_str_free(utf8[i]);
    free(utf8);
    return result;
#else
    return run_cli(argc, argv);
#endif
}
