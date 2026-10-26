/* SPDX-License-Identifier: MIT */
#include "core.h"
#include <xxfclib/io/xx_io.h>
#include <xxfclib/strings/xx_string.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <dirent.h>
#endif

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); return 1; \
} } while (0)

typedef struct capture {
    const char *directory;
    const char *inject_path;
    const char *published_path;
    bool cancel_progress;
    bool cancel_published;
    bool stop;
    bool stage_seen;
    bool injected;
    bool published_seen;
    bool progress_complete;
    bool walk_complete;
    bool percent_monotonic;
    size_t entries;
    size_t test_results;
    size_t test_success;
    size_t type_count;
    unsigned percent;
    xx_file_type_t types[2];
    xx_file_type_t selected;
    char name[128];
} capture;

static bool make_path(char *output, size_t capacity, const char *root, const char *name) {
    int length = snprintf(output, capacity, "%s/%s", root, name);
    return length >= 0 && (size_t)length < capacity;
}

static bool write_text(const char *path, const char *text) {
    xx_io_device *file = xx_io_file_open(path, "wb");
    bool success;
    if (!file) return false;
    success = xx_io_write(file, text, strlen(text)) == (ssize_t)strlen(text);
    return xx_io_close(file) == 0 && success;
}

static bool matches_text(const char *path, const char *text) {
    unsigned char buffer[64];
    xx_io_device *file = xx_io_file_open(path, "rb");
    ssize_t size;
    bool success;
    if (!file) return false;
    size = xx_io_read(file, buffer, sizeof(buffer));
    success = size == (ssize_t)strlen(text) && !memcmp(buffer, text, strlen(text));
    return xx_io_close(file) == 0 && success;
}

static bool write_payload(const char *path) {
    unsigned char *buffer = (unsigned char *)malloc(65536);
    xx_io_device *file;
    size_t i;
    bool success = true;
    if (!buffer) return false;
    for (i = 0; i < 65536; ++i) buffer[i] = (unsigned char)i;
    file = xx_io_file_open(path, "wb");
    if (!file) { free(buffer); return false; }
    for (i = 0; i < 4; ++i)
        if (xx_io_write(file, buffer, 65536) != 65536) success = false;
    if (xx_io_write(file, "last seven", 7) != 7) success = false;
    free(buffer);
    return xx_io_close(file) == 0 && success;
}

static bool files_match(const char *a, const char *b) {
    unsigned char left[4096], right[4096];
    xx_io_device *af = xx_io_file_open(a, "rb"), *bf = xx_io_file_open(b, "rb");
    bool success = af && bf;
    while (success) {
        ssize_t ac = xx_io_read(af, left, sizeof(left)), bc = xx_io_read(bf, right, sizeof(right));
        if (ac < 0 || bc < 0 || ac != bc || (ac && memcmp(left, right, (size_t)ac))) { success = false; break; }
        if (!ac) break;
    }
    if (af && xx_io_close(af) != 0) success = false;
    if (bf && xx_io_close(bf) != 0) success = false;
    return success;
}

static size_t inspect_directory(const char *directory, bool *stage) {
    size_t count = 0;
    *stage = false;
#ifdef _WIN32
    char pattern[2300];
    wchar_t *wide;
    WIN32_FIND_DATAW data;
    HANDLE found;
    if (!make_path(pattern, sizeof(pattern), directory, "*")) return SIZE_MAX;
    wide = xx_str_utf8_to_unicode(pattern);
    found = wide ? FindFirstFileW(wide, &data) : INVALID_HANDLE_VALUE;
    xx_str_wfree(wide);
    if (found == INVALID_HANDLE_VALUE) return SIZE_MAX;
    do {
        if (!wcscmp(data.cFileName, L".") || !wcscmp(data.cFileName, L"..")) continue;
        ++count;
        if (wcsstr(data.cFileName, L".xfu-")) *stage = true;
    } while (FindNextFileW(found, &data));
    FindClose(found);
#else
    DIR *dir = opendir(directory);
    struct dirent *item;
    if (!dir) return SIZE_MAX;
    while ((item = readdir(dir)) != NULL) {
        if (!strcmp(item->d_name, ".") || !strcmp(item->d_name, "..")) continue;
        ++count;
        if (strstr(item->d_name, ".xfu-")) *stage = true;
    }
    closedir(dir);
#endif
    return count;
}

static void log_line(void *user, bool error, const char *line) {
    (void)user;
    if (error) fprintf(stderr, "%s\n", line);
}

static bool cancelled(void *user) {
    capture *state = (capture *)user;
    if (state->cancel_published && state->published_path && xx_io_file_exists_a(state->published_path)) {
        state->published_seen = true; state->stop = true;
    }
    return state->stop;
}

static void progress(void *user, uint64_t done, uint64_t total, const char *name) {
    capture *state = (capture *)user;
    bool stage;
    if (!name) { if (done == total) state->progress_complete = true; return; }
    if (state->directory && inspect_directory(state->directory, &stage) != SIZE_MAX && stage)
        state->stage_seen = true;
    if (state->inject_path && !state->injected)
        state->injected = write_text(state->inject_path, "foreign existing part");
    if (state->cancel_progress) state->stop = true;
}

static void entry(void *user, const xfu_entry *item) {
    capture *state = (capture *)user;
    ++state->entries;
    snprintf(state->name, sizeof(state->name), "%s", item->name);
}

static void file_types(void *user, const xx_file_type_t *types, size_t count, xx_file_type_t selected) {
    capture *state = (capture *)user;
    size_t i;
    state->type_count = count; state->selected = selected;
    for (i = 0; i < count && i < 2; ++i) state->types[i] = types[i];
}

static void test_result(void *user, const xfu_entry *item, bool success) {
    capture *state = (capture *)user;
    (void)item;
    ++state->test_results;
    if (success) ++state->test_success;
}

static void test_progress(void *user, unsigned percent) {
    capture *state = (capture *)user;
    if (percent < state->percent || percent > 100) state->percent_monotonic = false;
    state->percent = percent;
}

static void walk_end(void *user, bool complete) {
    ((capture *)user)->walk_complete = complete;
}

static xfu_request request_for(capture *state, xfu_command command, const char *path) {
    xfu_request request = {0};
    state->percent_monotonic = true;
    request.command = command; request.archive_path = path;
    request.callbacks.user = state; request.callbacks.log = log_line;
    request.callbacks.cancelled = cancelled; request.callbacks.progress = progress;
    request.callbacks.entry = entry; request.callbacks.file_types = file_types;
    request.callbacks.test_result = test_result; request.callbacks.test_progress = test_progress;
    request.callbacks.walk_end = walk_end;
    return request;
}

int main(int argc, char **argv) {
    static const struct {
        const char *format;
        const char *compression;
    } formats[] = {
        {"pea", NULL}, {"freearc", NULL},
#ifdef XFU_HAVE_FREEARC_SFX
        {"freearc_sfx", NULL},
#endif
        {"freearc", "lzma"}
    };
    static const char *unavailable[] = {
        "brotli", "zpaq", "balz", "bcm", "quad", "lpaq1", "lpaq5", "lpaq8",
        "paq8", "paq8f", "paq8jd", "paq8l", "paq8o", "upx", "7zip_sfx"
    };
    char root[2048], source[2048], archive[2048], name[128];
    char first[2048], second[2048], third[2048], output[2048], member[2048];
    const char *sources[1];
    const size_t selected[] = {0}, invalid[] = {1};
    size_t i, before, after;
    int length;
    bool stage;
    capture state = {0};
    xfu_request request;
    CHECK(argc == 2);
    CHECK(xx_io_create_dirs_a(argv[1], true));
    length = snprintf(root, sizeof(root), "%s/run-%lu-%p", argv[1], (unsigned long)time(NULL), (void *)&state);
    CHECK(length >= 0 && (size_t)length < sizeof(root));
    CHECK(xx_io_create_dirs_a(root, true));
    CHECK(make_path(source, sizeof(source), root, "source.bin"));
    CHECK(write_payload(source)); sources[0] = source;

    for (i = 0; i < sizeof(formats) / sizeof(formats[0]); ++i) {
        snprintf(name, sizeof(name), "cancel-%s-%u.bin", formats[i].format, (unsigned)i);
        CHECK(make_path(archive, sizeof(archive), root, name));
        CHECK(write_text(archive, "original destination"));
        memset(&state, 0, sizeof(state)); state.cancel_progress = true; state.directory = root;
        request = request_for(&state, XFU_COMMAND_ADD, archive);
        request.archive_format = formats[i].format; request.files = sources; request.file_count = 1;
        request.compression_method = formats[i].compression;
        CHECK(xfu_run(&request) == 1);
        CHECK(state.stop && state.stage_seen && !state.progress_complete);
        CHECK(matches_text(archive, "original destination"));
        CHECK(inspect_directory(root, &stage) != SIZE_MAX && !stage);
    }

    CHECK(make_path(first, sizeof(first), root, "split.001"));
    memset(&state, 0, sizeof(state)); request = request_for(&state, XFU_COMMAND_ADD, first);
    request.files = sources; request.file_count = 1; request.volume_size = 65536;
    CHECK(xfu_run(&request) == 0 && state.progress_complete);

    memset(&state, 0, sizeof(state)); request = request_for(&state, XFU_COMMAND_LIST, first);
    request.reader_name = "split";
    CHECK(xfu_run(&request) == 0 && state.entries == 1 && state.walk_complete);
    CHECK(!strcmp(state.name, "split") && state.type_count == 2);
    CHECK(state.types[0] == XX_FILE_TYPE_BINARY && state.types[1] == XX_FILE_TYPE_NUMBERED_SPLIT);
    CHECK(state.selected == XX_FILE_TYPE_NUMBERED_SPLIT);

    before = inspect_directory(root, &stage); CHECK(before != SIZE_MAX && !stage);
    memset(&state, 0, sizeof(state)); request = request_for(&state, XFU_COMMAND_TEST, first);
    CHECK(xfu_run(&request) == 0 && state.entries == 1 && state.walk_complete);
    CHECK(state.test_results == 1 && state.test_success == 1 && state.percent == 100 && state.percent_monotonic);
    after = inspect_directory(root, &stage); CHECK(before == after && !stage);

    CHECK(make_path(output, sizeof(output), root, "selected"));
    CHECK(make_path(member, sizeof(member), output, "split"));
    memset(&state, 0, sizeof(state)); request = request_for(&state, XFU_COMMAND_EXTRACT, first);
    request.output_dir = output; request.file_type = XX_FILE_TYPE_NUMBERED_SPLIT;
    request.extract_selected = true; request.selected_records = selected; request.selected_record_count = 1;
    CHECK(xfu_run(&request) == 0 && state.entries == 1 && state.walk_complete);
    CHECK(files_match(source, member));

    CHECK(make_path(output, sizeof(output), root, "invalid-selected"));
    memset(&state, 0, sizeof(state)); request = request_for(&state, XFU_COMMAND_EXTRACT, first);
    request.output_dir = output; request.extract_selected = true;
    request.selected_records = invalid; request.selected_record_count = 1;
    CHECK(xfu_run(&request) == 2 && state.entries == 0 && !state.walk_complete);
    CHECK(!xx_io_file_exists_a(output));

    CHECK(make_path(output, sizeof(output), root, "cancel-extract"));
    CHECK(xx_io_create_dirs_a(output, true));
    CHECK(make_path(member, sizeof(member), output, "split")); CHECK(write_text(member, "original member"));
    memset(&state, 0, sizeof(state)); state.directory = output; state.cancel_progress = true;
    request = request_for(&state, XFU_COMMAND_EXTRACT, first); request.output_dir = output;
    CHECK(xfu_run(&request) == 1 && state.stage_seen && !state.walk_complete);
    CHECK(matches_text(member, "original member"));
    CHECK(inspect_directory(output, &stage) != SIZE_MAX && !stage);

    CHECK(make_path(first, sizeof(first), root, "conflict.001"));
    CHECK(make_path(second, sizeof(second), root, "conflict.002"));
    CHECK(make_path(third, sizeof(third), root, "conflict.003"));
    memset(&state, 0, sizeof(state)); state.directory = root; state.inject_path = second;
    request = request_for(&state, XFU_COMMAND_ADD, first);
    request.files = sources; request.file_count = 1; request.volume_size = 100000;
    CHECK(xfu_run(&request) != 0 && state.injected && state.stage_seen && !state.progress_complete);
    CHECK(!xx_io_file_exists_a(first) && !xx_io_file_exists_a(third));
    CHECK(matches_text(second, "foreign existing part"));
    CHECK(inspect_directory(root, &stage) != SIZE_MAX && !stage);

    CHECK(make_path(first, sizeof(first), root, "cancel-publish.001"));
    CHECK(make_path(second, sizeof(second), root, "cancel-publish.002"));
    CHECK(make_path(third, sizeof(third), root, "cancel-publish.003"));
    memset(&state, 0, sizeof(state)); state.directory = root;
    state.cancel_published = true; state.published_path = first;
    request = request_for(&state, XFU_COMMAND_ADD, first);
    request.files = sources; request.file_count = 1; request.volume_size = 100000;
    CHECK(xfu_run(&request) == 1 && state.published_seen && !state.progress_complete);
    CHECK(!xx_io_file_exists_a(first) && !xx_io_file_exists_a(second) && !xx_io_file_exists_a(third));
    CHECK(inspect_directory(root, &stage) != SIZE_MAX && !stage);

    for (i = 0; i < sizeof(unavailable) / sizeof(unavailable[0]); ++i) {
        snprintf(name, sizeof(name), "unavailable-%s-%u.bin", unavailable[i], (unsigned)i);
        CHECK(make_path(archive, sizeof(archive), root, name));
        CHECK(write_text(archive, "original destination"));
        memset(&state, 0, sizeof(state)); state.directory = root;
        request = request_for(&state, XFU_COMMAND_ADD, archive);
        request.archive_format = unavailable[i]; request.files = sources; request.file_count = 1;
        CHECK(xfu_run(&request) == 2);
        CHECK(!state.stage_seen && !state.progress_complete);
        CHECK(matches_text(archive, "original destination"));
        CHECK(inspect_directory(root, &stage) != SIZE_MAX && !stage);
    }
    return 0;
}
