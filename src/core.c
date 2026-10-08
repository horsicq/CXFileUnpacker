/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif

#include "core.h"
#include "metadata.h"
#include "xxfc_readers.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wchar.h>
#include <xxfclib/strings/xx_string.h>
#include <xxfclib/formats/upx_engine/xx_upx_engine.h>
#include <xxfclib/formats/molebox/xx_molebox.h>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <sys/stat.h>
#include <unistd.h>
#endif

#define RECORD_LIMIT 1000000

static void emit(const xfu_request *request, bool error, const char *format, ...) {
    va_list args, copy;
    char local[1024] = {0};
    char *line = local;
    int count;
    if (!request->callbacks.log) return;
    va_start(args, format);
    va_copy(copy, args);
    count = vsnprintf(local, sizeof(local), format, args);
    va_end(args);
    if (count >= (int)sizeof(local)) {
        line = (char *)malloc((size_t)count + 1);
        if (line) vsnprintf(line, (size_t)count + 1, format, copy);
        else line = local;
    }
    va_end(copy);
    request->callbacks.log(request->callbacks.user, error, line);
    if (line != local) free(line);
}

xfu_command xfu_parse_command(const char *text) {
    if (!text || !text[0] || text[1]) return XFU_COMMAND_NONE;
    switch (text[0]) {
        case 'x': case 'X': return XFU_COMMAND_EXTRACT;
        case 'l': case 'L': return XFU_COMMAND_LIST;
        case 't': case 'T': return XFU_COMMAND_TEST;
        case 'a': case 'A': return XFU_COMMAND_ADD;
        default: return XFU_COMMAND_NONE;
    }
}

static bool cancelled(const xfu_request *request, xx_pd_struct *pd) {
    if (request->callbacks.cancelled &&
        request->callbacks.cancelled(request->callbacks.user)) xx_pd_stop(pd);
    return xx_pd_is_stopped(pd);
}

static void progress(const xfu_request *request, uint64_t completed,
                     uint64_t total, const char *name) {
    if (request->callbacks.progress)
        request->callbacks.progress(request->callbacks.user, completed, total, name);
}

typedef struct test_monitor {
    const xfu_request *request;
    xx_pd_observer previous;
    uint64_t completed, total;
    unsigned percent;
    bool active;
    bool busy_before[XX_PD_LEVELS];
} test_monitor;

static void test_percent(test_monitor *monitor, unsigned percent) {
    if (percent > 100) percent = 100;
    if (percent <= monitor->percent) return;
    monitor->percent = percent;
    if (monitor->request->callbacks.test_progress)
        monitor->request->callbacks.test_progress(
            monitor->request->callbacks.user, percent);
}

/* Keep the caller's observer (GUI/TUI cancellation and progress) intact.
 * The first new decoder level measures work inside the current member;
 * existing levels belong to the caller's whole-archive monitor. */
static bool test_observe(const xx_pd_struct *pd, void *user) {
    test_monitor *monitor = (test_monitor *)user;
    bool stop = false;
    int i;
    if (monitor->previous.progress == pd && monitor->previous.callback)
        stop = monitor->previous.callback(pd, monitor->previous.user_data);
    if (monitor->request->callbacks.cancelled &&
        monitor->request->callbacks.cancelled(monitor->request->callbacks.user))
        stop = true;
    if (!stop && !pd->is_stop && monitor->active && monitor->total) {
        for (i = 0; i < XX_PD_LEVELS; ++i) {
            const xx_pd_record *record = &pd->records[i];
            if (!monitor->busy_before[i] && record->is_busy && record->total) {
                uint64_t current = record->current < record->total ?
                    record->current : record->total;
                uint64_t fraction = (uint64_t)(
                    (long double)current * 1000.0L / (long double)record->total);
                unsigned percent = (unsigned)((monitor->completed * 1000U +
                    fraction) * 100U / (monitor->total * 1000U));
                /* Member completion and end-of-archive validation publish 100. */
                test_percent(monitor, percent < 100 ? percent : 99);
                break;
            }
        }
    }
    return stop;
}

static bool test_count_records(const xfu_request *request, Abstractformat *format,
                               xx_archive_record_state *state, xx_pd_struct *pd,
                               uint64_t *count) {
    *count = 0;
    while (xx_format_get_current_archive_record(format, state)) {
        if (cancelled(request, pd) || *count >= RECORD_LIMIT) return false;
        ++*count;
        if (!xx_format_archive_record_move_to_next(format, state, pd)) break;
    }
    return !cancelled(request, pd) && !pd->last_error;
}

static const char *record_name(const xx_archive_record *record, char **owned) {
    const char *name = xx_archive_record_get_original_name(record);
    const wchar_t *wide;
    *owned = NULL;
    if (name && name[0]) return name;
    wide = xx_archive_record_get_original_name_w(record);
    if (wide && wide[0]) {
        char *utf8 = xx_str_unicode_to_utf8(wide);
        if (utf8 && utf8[0]) {
            *owned = utf8;
            return utf8;
        }
        xx_str_free(utf8);
    }
    return "<unnamed>";
}

static void member_metadata(const xx_archive_record *record, xfu_entry *entry,
                            bool sevenzip_engine) {
    uint64_t date = xx_archive_record_get_meta_u64(record, XX_META_ID_LAST_MOD_DATE, UINT64_MAX);
    uint64_t clock = xx_archive_record_get_meta_u64(record, XX_META_ID_LAST_MOD_TIME, UINT64_MAX);
    uint64_t stamp = xx_archive_record_get_meta_u64(record, XX_META_ID_TIMESTAMP, UINT64_MAX);
    /* Engine records use the library's FILETIME timestamp convention. */
    if (sevenzip_engine && stamp != UINT64_MAX) {
        stamp = stamp >= UINT64_C(116444736000000000)
            ? stamp / UINT64_C(10000000) - UINT64_C(11644473600) : UINT64_MAX;
    }
    uint64_t attributes = xx_archive_record_get_meta_u64(record, XX_META_ID_ATTRIBUTES, UINT64_MAX);
    if (attributes == UINT64_MAX)
        attributes = xx_archive_record_get_meta_u64(record, XX_META_ID_EXTERNAL_ATTRS, UINT64_MAX);
    if (date <= UINT16_MAX && clock <= UINT16_MAX &&
        (date & 31) && ((date >> 5) & 15) >= 1 && ((date >> 5) & 15) <= 12 &&
        ((clock >> 11) & 31) < 24 && ((clock >> 5) & 63) < 60 && (clock & 31) < 30) {
        snprintf(entry->modified, sizeof(entry->modified), "%04u-%02u-%02u %02u:%02u:%02u",
            1980u + (unsigned)(date >> 9), (unsigned)((date >> 5) & 15), (unsigned)(date & 31),
            (unsigned)((clock >> 11) & 31), (unsigned)((clock >> 5) & 63), (unsigned)(clock & 31) * 2u);
    } else if (stamp <= INT64_MAX) {
        time_t value = (time_t)stamp;
        struct tm decoded;
        int valid = 0;
        if (value >= 0 && (uint64_t)value == stamp) {
#ifdef _WIN32
            valid = localtime_s(&decoded, &value) == 0;
#else
            valid = localtime_r(&value, &decoded) != NULL;
#endif
        }
        if (valid) strftime(entry->modified, sizeof(entry->modified), "%Y-%m-%d %H:%M:%S", &decoded);
    }
    if (attributes != UINT64_MAX)
        snprintf(entry->attributes, sizeof(entry->attributes), "0x%llX", (unsigned long long)attributes);
    else if (entry->is_directory) strcpy(entry->attributes, "D");
}

static int walk(const xfu_request *request, const char *unpack_to,
                xx_pd_struct *pd) {
    const char *archive_path = request->archive_path;
    xx_io_device *device;
    xxfc_opened opened = {0};
    xx_archive_record_state *state;
    xx_list_t options;
    uint64_t total = 0, failed = 0, known_total = 0;
    uint64_t visited = 0;
    size_t selected_cursor = 0;
    int status = 0;
    xx_file_type_t types[XX_FILE_TYPE_CHAIN_MAX], detected, selected, extension_hint;
    size_t type_count, type_index;
    bool type_matches = false;
    bool extension_opened = false;
    bool engine_attempted = false;
    bool testing = request->command == XFU_COMMAND_TEST;
    bool reached_end = false;
    test_monitor monitor = {0};

    if (testing && request->callbacks.test_progress)
        request->callbacks.test_progress(request->callbacks.user, 0);

    if (cancelled(request, pd)) {
        emit(request, true, "operation cancelled");
        return 1;
    }
    device = xx_io_file_open(archive_path, "rb");
    if (!device) {
        emit(request, true, "cannot open %s", archive_path);
        return 2;
    }
    if (request->reader_name) {
        if (!request->reader_name[0] || request->file_type != XX_FILE_TYPE_UNKNOWN ||
            !xxfc_open_named(&opened, device, 0, request->reader_name)) {
            emit(request, true, "%s: invalid explicit reader selection", archive_path);
            xx_io_close(device); return 2;
        }
        selected = opened.type;
        type_count = xx_format_get_file_type_chain(selected, types, XX_FILE_TYPE_CHAIN_MAX);
        if (request->callbacks.file_types)
            request->callbacks.file_types(request->callbacks.user, types, type_count, selected);
        if (cancelled(request, pd)) {
            emit(request, true, "operation cancelled"); xxfc_close(&opened); xx_io_close(device); return 1;
        }
        goto reader_opened;
    }
    /* Probe packed carriers before extension/content detection. In particular,
     * renamed DOS COM inputs must reach the bounded UPX reader without nesting
     * its helper protocol beneath the broad content detector's reader stack. */
    detected = xx_upx_has_marker_device(device,pd)
                   ? XX_FILE_TYPE_UPX
                   : xx_format_get_file_type_device_fast(device, archive_path);
    extension_hint=xx_format_get_file_type_extension(archive_path);
    switch (detected) {
    case XX_FILE_TYPE_PE32: case XX_FILE_TYPE_PE64:
    case XX_FILE_TYPE_ELF32: case XX_FILE_TYPE_ELF64:
    case XX_FILE_TYPE_MACHO32: case XX_FILE_TYPE_MACHO64:
        detected=xx_format_get_file_type_device(device);
        break;
    default: break;
    }
    if (request->password) {
        xx_file_type_t password_type=xx_molebox_detect_device(device,request->password,pd);
        if (password_type!=XX_FILE_TYPE_UNKNOWN) detected=password_type;
    }
    if (extension_hint != XX_FILE_TYPE_UNKNOWN && detected == extension_hint) {
        extension_opened = xxfc_open_extension_fast(&opened, device, 0,
                                                    archive_path, pd);
        if (extension_opened) detected = opened.type;
        else if (!xx_pd_is_stopped(pd))
            detected = xx_format_get_file_type_device(device);
    }
    if (!extension_opened && !xx_pd_is_stopped(pd) &&
        (detected == XX_FILE_TYPE_BINARY || detected == XX_FILE_TYPE_UNKNOWN)) {
        extension_opened = xxfc_open_extension(&opened, device, 0,
                                               archive_path, pd);
        if (extension_opened) detected = opened.type;
    }
    type_count = xx_format_get_file_type_chain(detected, types, XX_FILE_TYPE_CHAIN_MAX);
    selected = request->file_type == XX_FILE_TYPE_UNKNOWN ? detected : request->file_type;
    if (request->callbacks.file_types)
        request->callbacks.file_types(request->callbacks.user, types, type_count, selected);
    if (cancelled(request, pd)) {
        emit(request, true, "operation cancelled");
        if (extension_opened) xxfc_close(&opened);
        xx_io_close(device); return 1;
    }
    for (type_index = 0; type_index < type_count; ++type_index)
        if (types[type_index] == selected) type_matches = true;
    if (request->file_type != XX_FILE_TYPE_UNKNOWN && !type_matches) {
        emit(request, true, "%s: selected type %s does not match this file", archive_path,
             xx_format_file_type_to_string(selected));
        if (extension_opened) xxfc_close(&opened);
        xx_io_close(device); return 2;
    }
    if (selected == XX_FILE_TYPE_BINARY) {
        engine_attempted = true;
        if (request->file_type == XX_FILE_TYPE_UNKNOWN &&
            xxfc_open_fallback(&opened, device, 0, archive_path, request->password, selected, pd)) {
            extension_opened = true;
            goto reader_opened;
        }
        emit(request, true, "%s: Binary cannot be opened as an archive", archive_path);
        if (extension_opened) xxfc_close(&opened);
        xx_io_close(device); return 2;
    }
    if (extension_opened && opened.type != selected) {
        xxfc_close(&opened);
        extension_opened = false;
    }
    if (!extension_opened && !xxfc_open_type(&opened, device, 0, selected)) {
        if (!engine_attempted && request->file_type == XX_FILE_TYPE_UNKNOWN && !xx_pd_is_stopped(pd)) {
            engine_attempted = true;
            if (xxfc_open_fallback(&opened, device, 0, archive_path, request->password, selected, pd)) {
                extension_opened = true; goto reader_opened;
            }
        }
        if (opened.type == XX_FILE_TYPE_UNKNOWN)
            emit(request, true, "%s: not a recognised format", archive_path);
        else
            emit(request, true, "%s: %s is recognised but no reader is built in",
                 archive_path, xx_format_file_type_to_string(opened.type));
        xx_io_close(device);
        return 2;
    }
reader_opened:
    xxfc_attach_source_files(&opened, archive_path);
    if (request->password) {
        if (!xx_format_set_password(opened.format, request->password)) {
            emit(request, true, "cannot set archive password");
            status = 2;
            goto done;
        }
        /* Password assignment invalidates the reader's cached validation and
         * base information, including readers opened by the extension hint. */
        extension_opened = false;
    }
    if (!extension_opened && !xx_format_is_valid(opened.format, pd)) {
        if (!engine_attempted && !request->reader_name && !xxfc_reader_uses_helper(&opened) && !xx_pd_is_stopped(pd)) {
            engine_attempted = true;
            if (xxfc_open_fallback(&opened, device, 0, archive_path, request->password, selected, pd)) {
                extension_opened = true; goto reader_opened;
            }
        }
        emit(request, true, "%s: %s header does not hold up", archive_path,
             opened.reader_name);
        status = xx_pd_is_stopped(pd) ? 1 : 2;
        goto done;
    }
    if (!extension_opened && !xx_format_handle_base_info(opened.format, pd)) {
        if (!engine_attempted && !request->reader_name && !xxfc_reader_uses_helper(&opened) && !xx_pd_is_stopped(pd)) {
            engine_attempted = true;
            if (xxfc_open_fallback(&opened, device, 0, archive_path, request->password, selected, pd)) {
                extension_opened = true; goto reader_opened;
            }
        }
        emit(request, true, "%s: %s could not be parsed", archive_path,
             opened.reader_name);
        status = xx_pd_is_stopped(pd) ? 1 : 2;
        goto done;
    }
    xxfc_attach_source_files(&opened, archive_path);
    xxfc_refresh_sevenzip_type(&opened);
    if (opened.reader_name && !strncmp(opened.reader_name, "sevenzip", 8) && request->callbacks.file_types) {
        type_count = xx_format_get_file_type_chain(opened.type, types, XX_FILE_TYPE_CHAIN_MAX);
        request->callbacks.file_types(request->callbacks.user, types, type_count, opened.type);
    }
    /* Prefer upstream decoding for native readers with narrower payload
     * coverage, after validating the engine against the actual input. */
    if (!engine_attempted && !request->reader_name && (selected == XX_FILE_TYPE_APFS ||
        selected == XX_FILE_TYPE_CHM || selected == XX_FILE_TYPE_HXS)) {
        engine_attempted = true;
        if (xxfc_open_fallback(&opened, device, 0, archive_path, request->password, selected, pd)) {
            extension_opened = true; goto reader_opened;
        }
        xx_pd_clear_error(pd);
    }
    emit(request, false, "%s: %s", archive_path,
         xx_format_file_type_to_string(opened.type));
    if (!opened.format->is_archive) {
        if (!engine_attempted && !request->reader_name && !xxfc_reader_uses_helper(&opened) && !xx_pd_is_stopped(pd)) {
            engine_attempted = true;
            if (xxfc_open_fallback(&opened, device, 0, archive_path, request->password, selected, pd)) {
                extension_opened = true; goto reader_opened;
            }
        }
        emit(request, true, "%s: %s holds no archive members", archive_path,
             xx_format_file_type_to_string(opened.type));
        status = 1;
        goto done;
    }
    xx_list_init(&options, sizeof(xx_meta), xx_meta_free_elem);
    if (request->password) {
        xx_meta meta;
        xx_meta_init(&meta, XX_META_ID_OPT_PASSWORD);
        if (!xx_var_set_str(&meta.var, request->password) ||
            !xx_list_append(&options, &meta)) {
            xx_meta_cleanup(&meta);
            xx_list_cleanup(&options);
            emit(request, true, "cannot set archive password");
            status = 2;
            goto done;
        }
    }
    if (unpack_to) {
        xx_meta meta;
        xx_meta_init(&meta, XX_META_ID_OPT_UNPACK_PATH);
        if (!xx_var_set_str(&meta.var, unpack_to) ||
            !xx_list_append(&options, &meta)) {
            xx_meta_cleanup(&meta);
            xx_list_cleanup(&options);
            emit(request, true, "%s: members could not be read", archive_path);
            status = 2;
            goto done;
        }
    }
    state = xx_format_create_archive_records_reading(
        opened.format, (const xx_list_s *)&options, pd);
    if (!state) {
        if (!engine_attempted && !request->reader_name && !xxfc_reader_uses_helper(&opened) && !xx_pd_is_stopped(pd)) {
            engine_attempted = true;
            if (xxfc_open_fallback(&opened, device, 0, archive_path, request->password, selected, pd)) {
                xx_list_cleanup(&options); extension_opened = true; goto reader_opened;
            }
        }
        emit(request, true, "%s: members could not be read", archive_path);
        xx_list_cleanup(&options);
        status = xx_pd_is_stopped(pd) ? 1 : 2;
        goto done;
    }
    if (state->total_records > 0) known_total = (uint64_t)state->total_records;
    if (request->extract_selected) known_total = (uint64_t)request->selected_record_count;
    if (testing && known_total > RECORD_LIMIT) {
        emit(request, true, "archive has too many members to test");
        xx_format_free_archive_records_reading(opened.format, state);
        xx_list_cleanup(&options); status = 1; goto done;
    }
    if (testing && request->callbacks.test_progress &&
        (state->total_records < 0 ||
         (!known_total && xx_format_get_current_archive_record(opened.format, state)))) {
        /* Streaming readers need a metadata pass to give an honest percentage.
         * Neither pass has an extraction path or writes decoded output. */
        bool counted = test_count_records(request, opened.format, state, pd, &known_total);
        xx_format_free_archive_records_reading(opened.format, state);
        state = NULL;
        if (!counted) {
            emit(request, true, xx_pd_is_stopped(pd) ? "operation cancelled" :
                 "cannot determine archive member count");
            xx_list_cleanup(&options); status = 1; goto done;
        }
        state = xx_format_create_archive_records_reading(
            opened.format, (const xx_list_s *)&options, pd);
        if (!state) {
            emit(request, true, "members could not be read");
            xx_list_cleanup(&options); status = 2; goto done;
        }
    }
    /* Companions attached after detection can complete a disk descriptor.
     * Use the iterator's fresh parse to assess completeness. */
    if (xxfc_is_incomplete(&opened)) {
        emit(request, true, "%s: incomplete archive; showing recovered members", archive_path);
        status = 1;
    }
    if (testing) {
        monitor.request = request;
        monitor.total = known_total;
        monitor.previous = xx_pd_set_observer(pd, test_observe, &monitor);
    }
    progress(request, 0, known_total, NULL);
    for (;;) {
        const xx_archive_record *record;
        char *owned = NULL;
        xfu_entry entry;
        xfu_property *properties = NULL;
        if (cancelled(request, pd)) {
            emit(request, true, "operation cancelled");
            status = 1;
            break;
        }
        record = xx_format_get_current_archive_record(opened.format, state);
        if (!record) break;
        if (request->extract_selected) {
            if (visited != request->selected_records[selected_cursor]) goto next_record;
            ++selected_cursor;
        }
        memset(&entry, 0, sizeof(entry));
        entry.name = record_name(record, &owned);
        entry.packed_size = record->compressed_size;
        entry.unpacked_size = xx_archive_record_get_meta_i64(
            record, XX_META_ID_UNCOMPRESSED_SIZE, -1);
        entry.is_directory = xx_archive_record_get_meta_bool(
            record, XX_META_ID_IS_FOLDER, false);
        entry.embedded_password = xx_archive_record_get_meta_str(
            record, XX_META_ID_PASSWORD);
        member_metadata(record, &entry, xxfc_reader_uses_helper(&opened));
        if (!unpack_to && !testing)
            emit(request, false, "  %12lld  %s",
                 (long long)entry.packed_size, entry.name);
        if (request->callbacks.entry) {
            if (!xfu_record_properties(record, opened.type == XX_FILE_TYPE_ZIP || opened.type == XX_FILE_TYPE_ZIP64,
                                       &properties, &entry.property_count)) {
                emit(request, true, "cannot allocate member metadata");
                xx_str_free(owned); status = 2; break;
            }
            entry.properties = properties;
            request->callbacks.entry(request->callbacks.user, &entry);
            xfu_free_properties(properties, entry.property_count);
            entry.properties = NULL;
            entry.property_count = 0;
        }
        progress(request, total, known_total, entry.name);
        ++total;
        if (unpack_to || testing) {
            bool success;
            int level;
            if (cancelled(request, pd)) {
                emit(request, true, "operation cancelled");
                status = 1;
                xx_str_free(owned);
                break;
            }
            if (testing) {
                monitor.completed = total - 1;
                for (level = 0; level < XX_PD_LEVELS; ++level)
                    monitor.busy_before[level] = pd->records[level].is_busy;
                monitor.active = true;
            }
            success = xx_format_unpack_current_archive_record(opened.format, state, pd);
            monitor.active = false;
            if (testing && cancelled(request, pd)) success = false;
            if (testing && request->callbacks.test_result)
                request->callbacks.test_result(request->callbacks.user, &entry, success);
            else if (success)
                emit(request, false, testing ? "  %s -- OK" : "  %s", entry.name);
            else
                emit(request, true, "  %s -- FAILED", entry.name);
            if (!success) {
                ++failed;
            }
        }
        progress(request, total, known_total, entry.name);
        if (testing && known_total && !cancelled(request, pd)) {
            unsigned percent = (unsigned)(total * 100U / known_total);
            test_percent(&monitor, percent < 100 ? percent : 99);
        }
        xx_str_free(owned);
        if (request->extract_selected && selected_cursor == request->selected_record_count) break;
next_record:
        ++visited;
        if (visited >= RECORD_LIMIT) {
            emit(request, true, "%s: stopping after %d members", archive_path,
                 RECORD_LIMIT);
            status = 1;
            break;
        }
        if (testing) {
            bool next;
            /* A decoder error belongs to that member. Detect a fresh iterator
             * error even when it occurs after the advertised final member. */
            xx_pd_clear_error(pd);
            next = xx_format_archive_record_move_to_next(opened.format, state, pd);
            if (pd->last_error) {
                emit(request, true, "archive iteration failed");
                status = 1; break;
            }
            if (!next) { reached_end = true; break; }
        } else if (!xx_format_archive_record_move_to_next(opened.format, state, pd)) {
            reached_end = true; break;
        }
    }
    xx_format_free_archive_records_reading(opened.format, state);
    xx_list_cleanup(&options);
    if (testing) {
        xx_pd_set_observer(monitor.previous.progress, monitor.previous.callback,
                           monitor.previous.user_data);
        if (known_total && total != known_total) {
            emit(request, true, "archive iteration ended before all members were tested");
            status = 1;
        }
        if (!xx_pd_is_stopped(pd) && !status && !xxfc_is_incomplete(&opened) &&
            (!known_total || total == known_total)) test_percent(&monitor, 100);
    }
    if (failed)
        emit(request, testing, "%llu member(s), %llu failed",
             (unsigned long long)total, (unsigned long long)failed);
    else
        emit(request, false, "%llu member(s)", (unsigned long long)total);
    if (failed || xx_pd_is_stopped(pd)) status = 1;
    if (!status && request->extract_selected && selected_cursor != request->selected_record_count) {
        emit(request, true, "selected members are no longer present in the archive");
        status = 1;
    }
    if (!status && xxfc_is_incomplete(&opened)) {
        emit(request, true, "%s: incomplete archive; showing recovered members",
             archive_path);
        status = 1;
    }
    if (request->callbacks.walk_end)
        request->callbacks.walk_end(request->callbacks.user,
            reached_end && !request->extract_selected && !xx_pd_is_stopped(pd) &&
            (!known_total || total == known_total) && !xxfc_is_incomplete(&opened));
done:
    xxfc_close(&opened);
    xx_io_close(device);
    return status;
}

static bool ends_with(const char *text, const char *suffix) {
    size_t n = strlen(text), m = strlen(suffix), i;
    if (m > n) return false;
    text += n - m;
    for (i = 0; i < m; ++i) {
        char a = text[i];
        if (a >= 'A' && a <= 'Z') a = (char)(a - 'A' + 'a');
        if (a != suffix[i]) return false;
    }
    return true;
}

static const char *writer_kind(const char *path) {
    static const struct { const char *suffix; const char *kind; } table[] = {
        { ".tar.gz", "tar.gz" }, { ".tgz", "tar.gz" },
        { ".tar.bz2", "tar.bz2" }, { ".tbz2", "tar.bz2" },
        { ".tar.xz", "tar.xz" }, { ".txz", "tar.xz" },
        { ".tar.zst", "tar.zst" }, { ".tar.lz4", "tar.lz4" },
        { ".tar", "tar" }, { ".zip", "zip" }, { ".cpio", "cpio" },
        { ".7z", "7z" }, { ".gz", "gz" }, { ".gzip", "gz" },
        { ".bz2", "bz2" }, { ".bzip2", "bz2" },
        { ".xz", "xz" }, { ".wim", "wim" }
    };
    size_t i;
    for (i = 0; i < sizeof(table) / sizeof(table[0]); ++i)
        if (ends_with(path, table[i].suffix)) return table[i].kind;
    return NULL;
}

static bool same_file(const char *left, const char *right) {
#ifdef _WIN32
    wchar_t *a = xx_str_utf8_to_unicode(left);
    wchar_t *b = xx_str_utf8_to_unicode(right);
    HANDLE ah = INVALID_HANDLE_VALUE, bh = INVALID_HANDLE_VALUE;
    BY_HANDLE_FILE_INFORMATION ai, bi;
    bool same = false;
    if (a && b) {
        ah = CreateFileW(a, 0, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                         NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        bh = CreateFileW(b, 0, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                         NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (ah != INVALID_HANDLE_VALUE && bh != INVALID_HANDLE_VALUE &&
            GetFileInformationByHandle(ah, &ai) &&
            GetFileInformationByHandle(bh, &bi))
            same = ai.dwVolumeSerialNumber == bi.dwVolumeSerialNumber &&
                   ai.nFileIndexHigh == bi.nFileIndexHigh &&
                   ai.nFileIndexLow == bi.nFileIndexLow;
        if (!same) {
            DWORD an = GetFullPathNameW(a, 0, NULL, NULL);
            DWORD bn = GetFullPathNameW(b, 0, NULL, NULL);
            wchar_t *af = (wchar_t *)malloc((size_t)an * sizeof(wchar_t));
            wchar_t *bf = (wchar_t *)malloc((size_t)bn * sizeof(wchar_t));
            if (an && bn && af && bf && GetFullPathNameW(a, an, af, NULL) &&
                GetFullPathNameW(b, bn, bf, NULL))
                same = CompareStringOrdinal(af, -1, bf, -1, TRUE) == CSTR_EQUAL;
            free(af);
            free(bf);
        }
    }
    if (ah != INVALID_HANDLE_VALUE) CloseHandle(ah);
    if (bh != INVALID_HANDLE_VALUE) CloseHandle(bh);
    xx_str_wfree(a);
    xx_str_wfree(b);
    return same;
#else
    struct stat a, b;
    if (stat(left, &a) == 0 && stat(right, &b) == 0)
        return a.st_dev == b.st_dev && a.st_ino == b.st_ino;
    return strcmp(left, right) == 0;
#endif
}

/* Keep relative subdirectories, but do not embed drive/root or parent paths
 * when a GUI file picker supplies absolute source names. */
static char *member_name(const char *path) {
    const char *start = path, *last = path, *p;
    char *result;
    bool basename = path[0] == '/' || path[0] == '\\' ||
                    (path[0] && path[1] == ':');
    for (p = path; *p; ++p) {
        if (*p == '/' || *p == '\\') last = p + 1;
        if (*p == '.' && p[1] == '.' &&
            (p == path || p[-1] == '/' || p[-1] == '\\') &&
            (p[2] == '\0' || p[2] == '/' || p[2] == '\\')) basename = true;
    }
    if (basename) start = last;
    else while (start[0] == '.' && (start[1] == '/' || start[1] == '\\')) start += 2;
    result = (char *)malloc(strlen(start) + 1);
    if (!result) return NULL;
    strcpy(result, start);
    for (p = result; *p; ++p)
        if (*p == '\\') result[p - result] = '/';
    return result;
}

static int add(const xfu_request *request, xx_pd_struct *pd) {
    const char *archive_path = request->archive_path;
    const char *kind = writer_kind(archive_path);
    xx_io_device *device, *probe;
    Abstractformat *format;
    xxfc_release_fn release = NULL;
    xx_archive_write_state *state;
    size_t i;
    int status = 0;
    xx_meta compression_meta[2];
    xx_list_s compression_options = {0};
    const xx_list_s *write_options = NULL;
    if (!kind) {
        emit(request, true,
             "%s: xxfclib cannot write this container. Writable: .tar "
             ".tar.gz .tar.bz2 .tar.xz .tar.zst .tar.lz4 .zip .cpio .7z .gz .bz2 .xz .wim", archive_path);
        return 2;
    }
    if ((!strcmp(kind, "gz") || !strcmp(kind, "bz2") || !strcmp(kind, "xz")) &&
        request->file_count != 1) {
        emit(request, true, "%s: a compressed stream requires exactly one input file; use .tar.%s for multiple files", archive_path, kind);
        return 2;
    }
    if (request->compression_method || request->compression_level_set) {
        if (strcmp(kind, "wim")) {
            emit(request, true, "compression options require a .wim destination");
            return 2;
        }
    }
    if (!strcmp(kind, "wim")) {
        const char *method = request->compression_method ? request->compression_method : "xpress";
        uint64_t value;
        if (!strcmp(method, "stored")) value = 0;
        else if (!strcmp(method, "xpress")) value = 1;
        else if (!strcmp(method, "lzx")) value = 2;
        else if (!strcmp(method, "lzms")) value = 3;
        else { emit(request, true, "unknown WIM compression method: %s", method); return 2; }
        if (request->compression_level_set &&
            (request->compression_level < 0 || request->compression_level > 100 ||
             (!value && request->compression_level != 0))) {
            emit(request, true, "WIM compression level must be 0..100; stored permits only 0"); return 2;
        }
        xx_meta_init(&compression_meta[0], XX_META_ID_COMPRESSION_METHOD);
        xx_var_set_u64(&compression_meta[0].var, value);
        compression_options.data = (uint8_t *)compression_meta;
        compression_options.elem_size = sizeof(xx_meta);
        compression_options.capacity = 2;
        compression_options.count = 1;
        if (request->compression_level_set) {
            xx_meta_init(&compression_meta[1], XX_META_ID_COMPRESSION_LEVEL);
            xx_var_set_u64(&compression_meta[1].var, (uint64_t)request->compression_level);
            compression_options.count = 2;
        }
        write_options = &compression_options;
    }
    if (request->password && strcmp(kind, "7z") && strcmp(kind, "zip")) {
        emit(request, true, "%s: password protection is supported for .7z and .zip", archive_path);
        return 2;
    }
    for (i = 0; i < request->file_count; ++i) {
        if (same_file(archive_path, request->files[i])) {
            emit(request, true, "%s: cannot add the archive to itself", archive_path);
            return 2;
        }
    }
    if (cancelled(request, pd)) {
        emit(request, true, "operation cancelled");
        return 1;
    }
    /* Resolve the built-in writer before opening the target in truncate mode. */
    probe = xx_io_mem_open(NULL, 0);
    format = probe ? xxfc_make_writer(kind, probe, &release) : NULL;
    if (!format) {
        if (probe) xx_io_close(probe);
        emit(request, true,
             "%s: xxfclib cannot write this container. Writable: .tar "
             ".tar.gz .tar.bz2 .tar.xz .tar.zst .tar.lz4 .zip .cpio .7z .gz .bz2 .xz .wim", archive_path);
        return 2;
    }
    release(format);
    xx_io_close(probe);
    if (write_options) {
        uint8_t header[208];
        bool ready;
        probe = xx_io_mem_open(header, sizeof(header));
        format = probe ? xxfc_make_writer(kind, probe, &release) : NULL;
        state = format ? xx_format_create_archive_records_writing(format, write_options, pd) : NULL;
        ready = state != NULL;
        if (state) xx_format_free_archive_records_writing(format, state);
        if (format) release(format);
        if (probe) xx_io_close(probe);
        if (!ready) {
            emit(request, true, "%s: cannot initialize WIM compression: %s", archive_path,
                 pd && pd->error_string[0] ? pd->error_string : "compression helper unavailable");
            return xx_pd_is_stopped(pd) ? 1 : 2;
        }
    }
    device = xx_io_file_open(archive_path, "wb");
    if (!device) {
        emit(request, true, "cannot create %s", archive_path);
        return 2;
    }
    format = xxfc_make_writer(kind, device, &release);
    if (!format) {
        emit(request, true, "%s: cannot start writing", archive_path);
        xx_io_close(device);
        return 2;
    }
    if (request->password && !xx_format_set_password(format, request->password)) {
        emit(request, true, "cannot set archive password");
        release(format); xx_io_close(device); return 2;
    }
    state = xx_format_create_archive_records_writing(format, write_options, pd);
    if (!state) {
        emit(request, true, "%s: cannot start writing", archive_path);
        release(format);
        xx_io_close(device);
        return xx_pd_is_stopped(pd) ? 1 : 2;
    }
    progress(request, 0, (uint64_t)request->file_count, NULL);
    for (i = 0; i < request->file_count; ++i) {
        xx_io_device *source;
        xx_archive_record record;
        char *name;
        bool encrypted_metadata = true;
        if (cancelled(request, pd)) {
            emit(request, true, "operation cancelled");
            status = 1;
            break;
        }
        progress(request, (uint64_t)i, (uint64_t)request->file_count, request->files[i]);
        source = xx_io_file_open(request->files[i], "rb");
        if (!source) {
            emit(request, true, "  %s -- cannot read", request->files[i]);
            status = 1;
            progress(request, (uint64_t)i + 1, (uint64_t)request->file_count,
                     request->files[i]);
            continue;
        }
        name = member_name(request->files[i]);
        xx_archive_record_init(&record);
        if (request->password && request->password[0] && !strcmp(kind, "zip"))
            encrypted_metadata = xx_archive_record_set_meta_bool(&record, XX_META_ID_IS_ENCRYPTED, true);
        if (!encrypted_metadata || !name || !name[0] ||
            !xx_archive_record_set_original_name(&record, name) ||
            !xx_format_pack_archive_record(format, state, &record, source, pd)) {
            emit(request, true, "  %s -- FAILED", request->files[i]);
            status = 1;
        } else {
            emit(request, false, "  %s", request->files[i]);
        }
        free(name);
        xx_archive_record_cleanup(&record);
        xx_io_close(source);
        progress(request, (uint64_t)i + 1, (uint64_t)request->file_count, request->files[i]);
    }
    if (!xx_format_finalize_archive_records_writing(format, state, pd)) {
        emit(request, true, "%s: could not be finished", archive_path);
        status = xx_pd_is_stopped(pd) ? 1 : 2;
    } else {
        emit(request, false, "%s: %llu file(s) as %s", archive_path,
             (unsigned long long)request->file_count, kind);
    }
    xx_format_free_archive_records_writing(format, state);
    release(format);
    xx_io_close(device);
    return status;
}

int xfu_run(const xfu_request *request) {
    xx_pd_struct local = xx_pd_init();
    xx_pd_struct *pd;
    size_t i;
    if (!request) return 2;
    if (!request->archive_path || !request->archive_path[0] ||
        request->command < XFU_COMMAND_EXTRACT || request->command > XFU_COMMAND_ADD) {
        emit(request, true, "invalid archive operation");
        return 2;
    }
    if (request->command == XFU_COMMAND_ADD) {
        if (!request->files || !request->file_count) {
            emit(request, true, "a: name at least one file to add");
            return 2;
        }
        for (i = 0; i < request->file_count; ++i)
            if (!request->files[i] || !request->files[i][0]) {
                emit(request, true, "a: name at least one file to add");
                return 2;
            }
    }
    if (request->extract_selected) {
        if (request->command != XFU_COMMAND_EXTRACT || !request->selected_records ||
            !request->selected_record_count) {
            emit(request, true, "select at least one member to extract"); return 2;
        }
        for (i = 0; i < request->selected_record_count; ++i)
            if (request->selected_records[i] >= RECORD_LIMIT ||
                (i && request->selected_records[i] <= request->selected_records[i - 1])) {
                emit(request, true, "invalid member selection"); return 2;
            }
    }
    if (request->command == XFU_COMMAND_EXTRACT && request->output_dir &&
        !request->output_dir[0]) {
        emit(request, true, "-o: name an output directory");
        return 2;
    }
    pd = request->progress_state ? request->progress_state : &local;
    switch (request->command) {
        case XFU_COMMAND_EXTRACT:
            return walk(request, request->output_dir ? request->output_dir : ".", pd);
        case XFU_COMMAND_LIST:
            return walk(request, NULL, pd);
        case XFU_COMMAND_TEST: {
            xx_io_memory_only_scope scope = {0};
            int status;
            if (cancelled(request, pd)) {
                emit(request, true, "operation cancelled");
                return 1;
            }
            /* All reader setup, decoding and cleanup run under this policy.
             * Seekable decoder workspaces live in RAM; disk fallback is forbidden. */
            if (!xx_io_memory_only_begin(&scope, UINT64_C(256) * 1024U * 1024U)) {
                emit(request, true, "cannot start in-memory archive verification");
                return 2;
            }
            xx_pd_clear_error(pd);
            status = walk(request, NULL, pd);
            if (!xx_io_memory_only_end(&scope)) {
                const char *reason = "invalid temporary workspace state";
                switch (xx_io_memory_only_error(&scope)) {
                    case XX_IO_MEMORY_ONLY_DISK_WRITE:
                        reason = "reader attempted a filesystem mutation"; break;
                    case XX_IO_MEMORY_ONLY_LIMIT:
                        reason = "temporary workspace exceeds the 256 MiB RAM limit"; break;
                    case XX_IO_MEMORY_ONLY_ALLOCATION:
                        reason = "cannot allocate temporary workspace in RAM"; break;
                    default: break;
                }
                emit(request, true, "in-memory verification failed: %s", reason);
                if (!status) status = 1;
            }
            return status;
        }
        case XFU_COMMAND_ADD:
            return add(request, pd);
        default:
            return 2;
    }
}
