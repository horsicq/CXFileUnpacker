/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "core.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <io.h>
#define test_dup _dup
#define test_dup2 _dup2
#define test_close _close
#define test_fileno _fileno
#else
#include <unistd.h>
#define test_dup dup
#define test_dup2 dup2
#define test_close close
#define test_fileno fileno
#endif

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
        return 1; \
    } \
} while (0)

typedef struct observations {
    size_t entry_count;
    char names[2][64];
    int64_t packed[2];
    int64_t unpacked[2];
    bool directories[2];
    bool invalid_entry;
    size_t logs;
    size_t errors;
    bool saw_archive_info;
    bool saw_summary;
    char last_error[256];
    size_t progress_calls;
    size_t named_progress;
    uint64_t max_completed;
    bool invalid_progress;
    bool cancel_requested;
    bool cancel_after_first;
} observations;

static void observe_entry(void *user, const xfu_entry *entry) {
    observations *seen = (observations *)user;
    size_t index = seen->entry_count++;
    if (!entry || !entry->name || !entry->name[0] || index >= 2) {
        seen->invalid_entry = true;
        return;
    }
    /* Callback values are borrowed. Retain only a copy made during the call. */
    if (strlen(entry->name) >= sizeof(seen->names[index]))
        seen->invalid_entry = true;
    snprintf(seen->names[index], sizeof(seen->names[index]), "%s", entry->name);
    seen->packed[index] = entry->packed_size;
    seen->unpacked[index] = entry->unpacked_size;
    seen->directories[index] = entry->is_directory;
}

static void observe_log(void *user, bool error, const char *line) {
    observations *seen = (observations *)user;
    ++seen->logs;
    if (error) {
        ++seen->errors;
        snprintf(seen->last_error, sizeof(seen->last_error), "%s", line);
    }
    if (strstr(line, "test.tar:")) seen->saw_archive_info = true;
    if (strcmp(line, "2 member(s)") == 0) seen->saw_summary = true;
}

static void observe_progress(void *user, uint64_t completed, uint64_t total,
                             const char *name) {
    observations *seen = (observations *)user;
    ++seen->progress_calls;
    if (completed > seen->max_completed) seen->max_completed = completed;
    if (total && (total != 2 || completed > total)) seen->invalid_progress = true;
    if (name) {
        ++seen->named_progress;
        if (strcmp(name, "first.txt") != 0 && strcmp(name, "second.txt") != 0)
            seen->invalid_progress = true;
    }
    if (seen->cancel_after_first && completed == 1) seen->cancel_requested = true;
}

static bool requested_cancel(void *user) {
    return ((observations *)user)->cancel_requested;
}

static xfu_callbacks callbacks(observations *seen) {
    xfu_callbacks result = {0};
    result.user = seen;
    result.log = observe_log;
    result.entry = observe_entry;
    result.progress = observe_progress;
    result.cancelled = requested_cancel;
    return result;
}

static bool write_source(const char *path, const char *contents, size_t length) {
    FILE *file = fopen(path, "wb");
    bool ok;
    if (!file) return false;
    ok = fwrite(contents, 1, length, file) == length;
    if (fclose(file) != 0) ok = false;
    return ok;
}

static bool file_equals(const char *path, const char *expected, size_t length) {
    unsigned char buffer[128];
    FILE *file;
    size_t read;
    int next;
    if (length > sizeof(buffer)) return false;
    file = fopen(path, "rb");
    if (!file) return false;
    read = fread(buffer, 1, length, file);
    next = fgetc(file);
    if (fclose(file) != 0) return false;
    return read == length && next == EOF && memcmp(buffer, expected, length) == 0;
}

/* Verify the library-style API does not write either process stream when no
 * callback is attached, so GUI and TUI frontends can own their output. */
static bool silent_list(void) {
    FILE *output = tmpfile(), *error = tmpfile();
    int saved_output = -1, saved_error = -1;
    int output_fd = test_fileno(stdout), error_fd = test_fileno(stderr);
    bool redirected = false, ok = false;
    xfu_request request = {0};
    if (!output || !error || fflush(stdout) != 0 || fflush(stderr) != 0) goto done;
    saved_output = test_dup(output_fd);
    saved_error = test_dup(error_fd);
    if (saved_output < 0 || saved_error < 0) goto done;
    if (test_dup2(test_fileno(output), output_fd) < 0) goto done;
    redirected = true;
    if (test_dup2(test_fileno(error), error_fd) < 0) goto done;
    request.command = XFU_COMMAND_LIST;
    request.archive_path = "test.tar";
    ok = xfu_run(&request) == 0;
    if (fflush(stdout) != 0 || fflush(stderr) != 0) ok = false;
    if (fseek(output, 0, SEEK_END) != 0 || ftell(output) != 0 ||
        fseek(error, 0, SEEK_END) != 0 || ftell(error) != 0) ok = false;
done:
    if (redirected) {
        if (test_dup2(saved_output, output_fd) < 0) ok = false;
        if (test_dup2(saved_error, error_fd) < 0) ok = false;
    }
    if (saved_output >= 0) test_close(saved_output);
    if (saved_error >= 0) test_close(saved_error);
    if (output) fclose(output);
    if (error) fclose(error);
    return ok;
}

int main(void) {
    static const char first[] = "first payload\n";
    static const char second[] = {'S', 'e', 'c', 'o', 'n', 'd', '\0', (char)0x80, (char)0xff, '\n'};
    const char *files[] = { "first.txt", "second.txt" };
    observations seen = {0};
    xfu_request request = {0};
    xx_pd_struct monitor;

    CHECK(write_source(files[0], first, sizeof(first) - 1));
    CHECK(write_source(files[1], second, sizeof(second)));
    request.command = XFU_COMMAND_ADD;
    request.archive_path = "test.tar";
    request.files = files;
    request.file_count = 2;
    request.callbacks = callbacks(&seen);
    CHECK(xfu_run(&request) == 0);
    CHECK(seen.errors == 0 && seen.logs >= 3);
    CHECK(seen.max_completed == 2 && !seen.invalid_progress);

    memset(&seen, 0, sizeof(seen));
    request.command = XFU_COMMAND_LIST;
    request.files = NULL;
    request.file_count = 0;
    CHECK(xfu_run(&request) == 0);
    CHECK(seen.entry_count == 2 && !seen.invalid_entry);
    CHECK(strcmp(seen.names[0], files[0]) == 0);
    CHECK(strcmp(seen.names[1], files[1]) == 0);
    CHECK(seen.packed[0] == (int64_t)(sizeof(first) - 1));
    CHECK(seen.packed[1] == (int64_t)sizeof(second));
    CHECK(seen.unpacked[0] == (int64_t)(sizeof(first) - 1));
    CHECK(seen.unpacked[1] == (int64_t)sizeof(second));
    CHECK(!seen.directories[0] && !seen.directories[1]);
    CHECK(seen.errors == 0 && seen.logs >= 4);
    CHECK(seen.saw_archive_info && seen.saw_summary);
    CHECK(seen.progress_calls >= 3 && seen.named_progress >= 2);
    CHECK(seen.max_completed == 2 && !seen.invalid_progress);

    /* Remove the sources so a successful extract must recreate the bytes.
     * The second payload includes NUL and high bytes, not just UTF-8 text. */
    CHECK(remove(files[0]) == 0 && remove(files[1]) == 0);
    memset(&seen, 0, sizeof(seen));
    request.command = XFU_COMMAND_EXTRACT;
    CHECK(xfu_run(&request) == 0);
    CHECK(file_equals(files[0], first, sizeof(first) - 1));
    CHECK(file_equals(files[1], second, sizeof(second)));
    request.command = XFU_COMMAND_LIST;

    /* Cancellation takes priority over opening and detecting the input. */
    memset(&seen, 0, sizeof(seen));
    seen.cancel_requested = true;
    request.archive_path = "not-created-before-cancel.tar";
    CHECK(xfu_run(&request) == 1);
    CHECK(seen.entry_count == 0 && seen.progress_calls == 0);
    CHECK(seen.errors == 1 && strcmp(seen.last_error, "operation cancelled") == 0);

    /* Progress can request a stop after one completed member. The second
     * member must never be handed to the entry callback. */
    memset(&seen, 0, sizeof(seen));
    seen.cancel_after_first = true;
    request.archive_path = "test.tar";
    CHECK(xfu_run(&request) == 1);
    CHECK(seen.entry_count == 1 && strcmp(seen.names[0], files[0]) == 0);
    CHECK(seen.max_completed == 1 && !seen.invalid_progress);
    CHECK(seen.errors == 1 && strcmp(seen.last_error, "operation cancelled") == 0);

    /* Frontends can also request cancellation directly through xxfclib's
     * monitor, without installing a cancelled callback. */
    memset(&seen, 0, sizeof(seen));
    monitor = xx_pd_init();
    xx_pd_stop(&monitor);
    request.progress_state = &monitor;
    request.callbacks.cancelled = NULL;
    CHECK(xfu_run(&request) == 1);
    CHECK(seen.entry_count == 0 && seen.progress_calls == 0);
    CHECK(seen.errors == 1 && strcmp(seen.last_error, "operation cancelled") == 0);
    CHECK(silent_list());

    CHECK(remove(files[0]) == 0);
    CHECK(remove(files[1]) == 0);
    CHECK(remove("test.tar") == 0);
    puts("Shared core callbacks, metadata, silence and cancellation passed");
    return 0;
}
