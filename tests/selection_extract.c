/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "core.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <direct.h>
#include <xxfclib/strings/xx_string.h>
#define make_directory(path) _mkdir(path)
#else
#include <sys/stat.h>
#define make_directory(path) mkdir(path, 0755)
#endif

#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); exit(1); } } while (0)

typedef struct observed {
    size_t entries;
    uint64_t completed;
    int stop, cancel_first;
} observed;

static void entry(void *user, const xfu_entry *record) {
    observed *seen = (observed *)user;
    CHECK(!strcmp(record->name, "chosen/deep/b.txt") || !strcmp(record->name, "Unicode-\xe4\xbd\xa0\xe5\xa5\xbd.txt"));
    ++seen->entries;
}

static void progress(void *user, uint64_t done, uint64_t total, const char *name) {
    observed *seen = (observed *)user;
    (void)name;
    CHECK(total == 2 && done <= total);
    seen->completed = done;
    if (seen->cancel_first && done == 1) seen->stop = 1;
}

static bool cancelled(void *user) { return ((observed *)user)->stop != 0; }

static FILE *open_file(const char *path, const char *mode) {
#ifdef _WIN32
    wchar_t *wide = xx_str_utf8_to_unicode(path);
    FILE *file = wide ? _wfopen(wide, !strcmp(mode, "rb") ? L"rb" : L"wb") : NULL;
    xx_str_wfree(wide); return file;
#else
    return fopen(path, mode);
#endif
}

static int remove_file(const char *path) {
#ifdef _WIN32
    wchar_t *wide = xx_str_utf8_to_unicode(path);
    int result = wide ? _wremove(wide) : -1;
    xx_str_wfree(wide); return result;
#else
    return remove(path);
#endif
}

static void write_file(const char *path, const char *contents) {
    FILE *file = open_file(path, "wb");
    CHECK(file && fwrite(contents, 1, strlen(contents), file) == strlen(contents));
    CHECK(fclose(file) == 0);
}

static void equals(const char *path, const char *contents) {
    char buffer[64] = {0};
    FILE *file = open_file(path, "rb");
    size_t size;
    CHECK(file);
    size = fread(buffer, 1, sizeof(buffer), file);
    CHECK(size == strlen(contents) && !memcmp(buffer, contents, size));
    CHECK(fclose(file) == 0);
}

int main(void) {
    const char *files[] = {"chosen/a.txt", "chosen/deep/b.txt", "chosen-other/c.txt", "Unicode-\xe4\xbd\xa0\xe5\xa5\xbd.txt"};
    const char *archives[] = {"selection.zip", "selection.tar", "selection.tar.gz"};
    const size_t members[] = {1, 3}, missing[] = {99}, duplicates[] = {1, 1};
    size_t i, j;
    make_directory("chosen"); make_directory("chosen/deep"); make_directory("chosen-other");
    for (i = 0; i < 3; ++i) {
        xfu_request request = {0};
        observed seen = {0};
        for (j = 0; j < 4; ++j) write_file(files[j], "original payload");
        request.command = XFU_COMMAND_ADD; request.archive_path = archives[i];
        request.files = files; request.file_count = 4;
        CHECK(xfu_run(&request) == 0);
        for (j = 0; j < 4; ++j) write_file(files[j], "keep me");
        CHECK(remove_file(files[1]) == 0 && remove_file(files[3]) == 0);
        request.command = XFU_COMMAND_EXTRACT; request.files = NULL; request.file_count = 0;
        request.extract_selected = true; request.selected_records = members; request.selected_record_count = 2;
        request.callbacks.user = &seen; request.callbacks.entry = entry; request.callbacks.progress = progress;
        request.callbacks.cancelled = cancelled;
        CHECK(xfu_run(&request) == 0 && seen.entries == 2 && seen.completed == 2);
        equals(files[0], "keep me"); equals(files[1], "original payload");
        equals(files[2], "keep me"); equals(files[3], "original payload");
        /* Empty and invalid selections never overwrite any destination. */
        for (j = 0; j < 4; ++j) write_file(files[j], "keep me");
        memset(&request.callbacks, 0, sizeof(request.callbacks));
        request.selected_record_count = 0;
        CHECK(xfu_run(&request) == 2);
        request.selected_records = duplicates; request.selected_record_count = 2;
        CHECK(xfu_run(&request) == 2);
        request.selected_records = missing; request.selected_record_count = 1;
        CHECK(xfu_run(&request) == 1);
        for (j = 0; j < 4; ++j) equals(files[j], "keep me");
        /* Cancellation keeps completed files and leaves later selections alone. */
        CHECK(remove_file(files[1]) == 0 && remove_file(files[3]) == 0);
        memset(&seen, 0, sizeof(seen)); seen.cancel_first = 1;
        request.selected_records = members; request.selected_record_count = 2;
        request.callbacks.user = &seen; request.callbacks.entry = entry; request.callbacks.progress = progress;
        request.callbacks.cancelled = cancelled;
        CHECK(xfu_run(&request) == 1 && seen.entries == 1);
        equals(files[0], "keep me"); equals(files[1], "original payload");
        equals(files[2], "keep me"); CHECK(open_file(files[3], "rb") == NULL);
        write_file(files[3], "keep me");
        CHECK(remove(archives[i]) == 0);
    }
    for (j = 0; j < 4; ++j) CHECK(remove_file(files[j]) == 0);
    puts("Selected ZIP/TAR/TAR.GZ extraction preserves unselected files and handles cancellation");
    return 0;
}
