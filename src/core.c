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

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <dirent.h>
#include <errno.h>
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

static void member_metadata(const xx_archive_record *record, xfu_entry *entry) {
    uint64_t date = xx_archive_record_get_meta_u64(record, XX_META_ID_LAST_MOD_DATE, UINT64_MAX);
    uint64_t clock = xx_archive_record_get_meta_u64(record, XX_META_ID_LAST_MOD_TIME, UINT64_MAX);
    uint64_t stamp = xx_archive_record_get_meta_u64(record, XX_META_ID_TIMESTAMP, UINT64_MAX);
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
    xx_file_type_t types[XX_FILE_TYPE_CHAIN_MAX], detected, selected;
    size_t type_count, type_index;
    bool type_matches = false;
    bool extension_opened = false;

    if (cancelled(request, pd)) {
        emit(request, true, "operation cancelled");
        return 1;
    }
    device = xx_io_file_open(archive_path, "rb");
    if (!device) {
        emit(request, true, "cannot open %s", archive_path);
        return 2;
    }
    detected = xx_format_get_file_type_device_fast(device, archive_path);
    if (xx_format_get_file_type_extension(archive_path) != XX_FILE_TYPE_UNKNOWN) {
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
        emit(request, true, "%s: Binary cannot be opened as an archive", archive_path);
        if (extension_opened) xxfc_close(&opened);
        xx_io_close(device); return 2;
    }
    if (extension_opened && opened.type != selected) {
        xxfc_close(&opened);
        extension_opened = false;
    }
    if (!extension_opened && !xxfc_open_type(&opened, device, 0, selected)) {
        if (opened.type == XX_FILE_TYPE_UNKNOWN)
            emit(request, true, "%s: not a recognised format", archive_path);
        else
            emit(request, true, "%s: %s is recognised but no reader is built in",
                 archive_path, xx_format_file_type_to_string(opened.type));
        xx_io_close(device);
        return 2;
    }
    if (!extension_opened && !xx_format_is_valid(opened.format, pd)) {
        emit(request, true, "%s: %s header does not hold up", archive_path,
             opened.reader_name);
        status = xx_pd_is_stopped(pd) ? 1 : 2;
        goto done;
    }
    if (!extension_opened && !xx_format_handle_base_info(opened.format, pd)) {
        emit(request, true, "%s: %s could not be parsed", archive_path,
             opened.reader_name);
        status = xx_pd_is_stopped(pd) ? 1 : 2;
        goto done;
    }
    xxfc_attach_source_files(&opened, archive_path);
    if (xxfc_is_incomplete(&opened)) {
        emit(request, true, "%s: incomplete archive; showing recovered members",
             archive_path);
        status = 1;
    }
    emit(request, false, "%s: %s", archive_path,
         xx_format_file_type_to_string(opened.type));
    if (!opened.format->is_archive) {
        emit(request, true, "%s: %s holds no archive members", archive_path,
             xx_format_file_type_to_string(opened.type));
        status = 1;
        goto done;
    }
    xx_list_init(&options, sizeof(xx_meta), xx_meta_free_elem);
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
        emit(request, true, "%s: members could not be read", archive_path);
        xx_list_cleanup(&options);
        status = xx_pd_is_stopped(pd) ? 1 : 2;
        goto done;
    }
    if (state->total_records > 0) known_total = (uint64_t)state->total_records;
    if (request->extract_selected) known_total = (uint64_t)request->selected_record_count;
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
        member_metadata(record, &entry);
        if (!unpack_to)
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
        }
        progress(request, total, known_total, entry.name);
        ++total;
        if (unpack_to) {
            if (cancelled(request, pd)) {
                emit(request, true, "operation cancelled");
                status = 1;
                xx_str_free(owned);
                break;
            }
            if (xx_format_unpack_current_archive_record(opened.format, state, pd))
                emit(request, false, "  %s", entry.name);
            else {
                ++failed;
                emit(request, true, "  %s -- FAILED", entry.name);
            }
        }
        progress(request, total, known_total, entry.name);
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
        if (!xx_format_archive_record_move_to_next(opened.format, state, pd)) break;
    }
    xx_format_free_archive_records_reading(opened.format, state);
    xx_list_cleanup(&options);
    if (failed)
        emit(request, false, "%llu member(s), %llu failed",
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
        { ".tar", "tar" }, { ".zip", "zip" }, { ".cpio", "cpio" }
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
    if (!kind) {
        emit(request, true,
             "%s: xxfclib cannot write this container. Writable: .tar "
             ".tar.gz .tar.bz2 .tar.xz .tar.zst .tar.lz4 .zip .cpio", archive_path);
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
             ".tar.gz .tar.bz2 .tar.xz .tar.zst .tar.lz4 .zip .cpio", archive_path);
        return 2;
    }
    release(format);
    xx_io_close(probe);
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
    state = xx_format_create_archive_records_writing(format, NULL, pd);
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
        if (!name || !name[0] ||
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

#ifdef _WIN32
static bool remove_tree(const wchar_t *path) {
    size_t length = wcslen(path);
    wchar_t *pattern = (wchar_t *)malloc((length + 3) * sizeof(wchar_t));
    WIN32_FIND_DATAW data;
    HANDLE find;
    bool ok = true;
    DWORD find_error;
    DWORD attributes = GetFileAttributesW(path);
    if (attributes == INVALID_FILE_ATTRIBUTES) return false;
    if (!(attributes & FILE_ATTRIBUTE_DIRECTORY) ||
        (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) {
        if (attributes & FILE_ATTRIBUTE_READONLY)
            SetFileAttributesW(path, attributes & ~FILE_ATTRIBUTE_READONLY);
        return (attributes & FILE_ATTRIBUTE_DIRECTORY) ?
               RemoveDirectoryW(path) != 0 : DeleteFileW(path) != 0;
    }
    if (!pattern) return false;
    memcpy(pattern, path, length * sizeof(wchar_t));
    wcscpy(pattern + length, L"\\*");
    find = FindFirstFileW(pattern, &data);
    find_error = find == INVALID_HANDLE_VALUE ? GetLastError() : ERROR_SUCCESS;
    free(pattern);
    if (find != INVALID_HANDLE_VALUE) {
        do {
            size_t child_length;
            wchar_t *child;
            if (wcscmp(data.cFileName, L".") == 0 ||
                wcscmp(data.cFileName, L"..") == 0) continue;
            child_length = length + wcslen(data.cFileName) + 2;
            child = (wchar_t *)malloc(child_length * sizeof(wchar_t));
            if (!child) { ok = false; continue; }
            memcpy(child, path, length * sizeof(wchar_t));
            child[length] = L'\\';
            wcscpy(child + length + 1, data.cFileName);
            if (!remove_tree(child)) ok = false;
            free(child);
        } while (FindNextFileW(find, &data));
        if (GetLastError() != ERROR_NO_MORE_FILES) ok = false;
        FindClose(find);
    } else if (find_error != ERROR_FILE_NOT_FOUND) ok = false;
    if (attributes & FILE_ATTRIBUTE_READONLY)
        SetFileAttributesW(path, attributes & ~FILE_ATTRIBUTE_READONLY);
    if (!RemoveDirectoryW(path)) ok = false;
    return ok;
}

static char *create_scratch(void) {
    DWORD length = GetTempPathW(0, NULL), i;
    wchar_t *path;
    char *utf8 = NULL;
    if (!length) return NULL;
    path = (wchar_t *)malloc(((size_t)length + 100) * sizeof(wchar_t));
    if (!path || !GetTempPathW(length + 1, path)) { free(path); return NULL; }
    length = (DWORD)wcslen(path);
    for (i = 0; i < 1000; ++i) {
        swprintf(path + length, 100, L"XFileUnpacker_test_%lu_%llu_%lu",
                 (unsigned long)GetCurrentProcessId(),
                 (unsigned long long)GetTickCount64(), (unsigned long)i);
        if (CreateDirectoryW(path, NULL)) {
            utf8 = xx_str_unicode_to_utf8(path);
            if (!utf8) RemoveDirectoryW(path);
            break;
        }
        if (GetLastError() != ERROR_ALREADY_EXISTS) break;
    }
    free(path);
    return utf8;
}

static bool discard_scratch(const char *path) {
    wchar_t *wide = xx_str_utf8_to_unicode(path);
    bool ok = wide && remove_tree(wide);
    xx_str_wfree(wide);
    return ok;
}
#else
static bool remove_tree(const char *path) {
    struct stat info;
    DIR *directory;
    struct dirent *entry;
    bool ok = true;
    if (lstat(path, &info) != 0) return false;
    if (!S_ISDIR(info.st_mode)) return unlink(path) == 0;
    directory = opendir(path);
    if (!directory) return false;
    errno = 0;
    while ((entry = readdir(directory)) != NULL) {
        size_t length;
        char *child;
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
            continue;
        length = strlen(path) + strlen(entry->d_name) + 2;
        child = (char *)malloc(length);
        if (!child) { ok = false; continue; }
        snprintf(child, length, "%s/%s", path, entry->d_name);
        if (!remove_tree(child)) ok = false;
        free(child);
        errno = 0;
    }
    if (errno) ok = false;
    closedir(directory);
    if (rmdir(path) != 0) ok = false;
    return ok;
}

static char *create_scratch(void) {
    const char *temporary = getenv("TMPDIR");
    size_t length;
    char *path, *result;
    if (!temporary || !temporary[0] || temporary[0] != '/') temporary = "/tmp";
    length = strlen(temporary) + sizeof("/XFileUnpacker_test_XXXXXX");
    path = (char *)malloc(length);
    if (!path) return NULL;
    snprintf(path, length, "%s/XFileUnpacker_test_XXXXXX", temporary);
    if (!mkdtemp(path)) { free(path); return NULL; }
    result = xx_str_dup(path);
    if (!result) rmdir(path);
    free(path);
    return result;
}

static bool discard_scratch(const char *path) { return remove_tree(path); }
#endif

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
            char *scratch;
            int status;
            if (cancelled(request, pd)) {
                emit(request, true, "operation cancelled");
                return 1;
            }
            scratch = create_scratch();
            if (!scratch) {
                emit(request, true, "cannot create a scratch directory");
                return 2;
            }
            status = walk(request, scratch, pd);
            if (!discard_scratch(scratch)) {
                emit(request, true, "cannot remove %s", scratch);
                if (!status) status = 1;
            }
            xx_str_free(scratch);
            return status;
        }
        case XFU_COMMAND_ADD:
            return add(request, pd);
        default:
            return 2;
    }
}
