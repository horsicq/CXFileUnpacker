/* SPDX-License-Identifier: MIT */
#include "core.h"
#include "native_writer_backend.h"
#include <xxfclib/formats/xx_format.h>
#include <xxfclib/io/xx_io.h>
#include <errno.h>
#include <locale.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <sys/stat.h>
#include <unistd.h>
#endif

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); return 1; \
} } while (0)

typedef struct capture {
    xx_file_type_t selected;
    bool selected_in_chain;
    bool stop;
    size_t entries;
    size_t type_count;
    xx_file_type_t types[4];
    char names[2][64];
    size_t not_archive_calls;
    xx_file_type_t not_archive;
    xx_handle_type_t selected_handle;
    xx_handle_type_t handles[16];
    size_t handle_count;
    bool selected_handle_available;
    bool actionable_handles;
} capture;

static void log_error(void *user, bool error, const char *line) {
    (void)user;
    if (error) fprintf(stderr, "%s\n", line);
}

static void file_types(void *user, const xx_file_type_t *types, size_t count,
                       xx_file_type_t selected) {
    capture *state = (capture *)user;
    size_t i;
    state->selected = selected;
    state->selected_in_chain = false;
    state->type_count = count;
    for (i = 0; i < count; ++i) {
        if (i < sizeof(state->types) / sizeof(state->types[0]))
            state->types[i] = types[i];
        if (types[i] == selected) state->selected_in_chain = true;
    }
}

static void entry(void *user, const xfu_entry *item) {
    capture *state = (capture *)user;
    if (state->entries < 2)
        snprintf(state->names[state->entries], sizeof(state->names[0]), "%s", item->name);
    ++state->entries;
}

static void unpack_handle_types(void *user, const xx_handle_type_t *types,
                                 size_t count, xx_handle_type_t selected) {
    capture *state = (capture *)user;
    size_t i;
    state->selected_handle = selected;
    state->handle_count = count;
    state->selected_handle_available = false;
    state->actionable_handles = true;
    for (i = 0; i < count; ++i) {
        xx_file_type_t file_type = xx_format_handle_type_file_type(types[i]);
        if (i < sizeof(state->handles) / sizeof(state->handles[0]))
            state->handles[i] = types[i];
        if (types[i] == selected) state->selected_handle_available = true;
        if (types[i] == XX_HANDLE_TYPE_UNKNOWN || file_type == XX_FILE_TYPE_UNKNOWN ||
            file_type == XX_FILE_TYPE_BINARY || file_type == XX_FILE_TYPE_ARCHIVE ||
            file_type == XX_FILE_TYPE_PE32 || file_type == XX_FILE_TYPE_PE64 ||
            file_type == XX_FILE_TYPE_MSDOS || file_type == XX_FILE_TYPE_COM)
            state->actionable_handles = false;
    }
}

static bool captured_handle(const capture *state, xx_handle_type_t type) {
    size_t i;
    for (i = 0; i < state->handle_count && i < sizeof(state->handles) / sizeof(state->handles[0]); ++i)
        if (state->handles[i] == type) return true;
    return false;
}

static void not_archive(void *user, xx_file_type_t type) {
    capture *state = (capture *)user;
    ++state->not_archive_calls;
    state->not_archive = type;
}

static bool cancelled(void *user) {
    return ((const capture *)user)->stop;
}

static void cancel_creation(void *user, uint64_t completed, uint64_t total,
                            const char *name) {
    (void)completed;
    (void)total;
    if (name) ((capture *)user)->stop = true;
}

static xfu_request request_for(capture *state, xfu_command command,
                               const char *archive) {
    xfu_request request = {0};
    request.command = command;
    request.archive_path = archive;
    request.callbacks.user = state;
    request.callbacks.log = log_error;
    request.callbacks.file_types = file_types;
    request.callbacks.entry = entry;
    request.callbacks.cancelled = cancelled;
    request.callbacks.not_archive = not_archive;
    request.callbacks.unpack_handle_types = unpack_handle_types;
    return request;
}

static bool make_path(char *output, size_t capacity, const char *root,
                       const char *name) {
    int size = snprintf(output, capacity, "%s/%s", root, name);
    return size >= 0 && (size_t)size < capacity;
}

static bool write_fixture(const char *path, const char *text) {
    xx_io_device *file = xx_io_file_open(path, "wb");
    bool result;
    if (!file) return false;
    result = xx_io_write(file, text, strlen(text)) == (ssize_t)strlen(text);
    return xx_io_close(file) == 0 && result;
}

static bool content_matches(const char *path, const char *expected) {
    char buffer[64];
    xx_io_device *file = xx_io_file_open(path, "rb");
    ssize_t size;
    bool result;
    if (!file) return false;
    size = xx_io_read(file, buffer, sizeof(buffer));
    result = size == (ssize_t)strlen(expected) &&
        memcmp(buffer, expected, strlen(expected)) == 0;
    return xx_io_close(file) == 0 && result;
}

/* Every log line and the progress steps of one run. */
typedef struct journal {
    char lines[24][2300];
    bool errors[24];
    size_t count;
    uint64_t stop_at; /* Cancel once progress reports this many steps done. */
    size_t moving; /* Progress calls between the first and the last step. */
    bool stop;
    const char *grow; /* A file that gets one more byte at step grow_at. */
    uint64_t grow_at;
    int percent; /* The highest test_progress value, or -1. */
} journal;

static void journal_log(void *user, bool error, const char *line) {
    journal *state = (journal *)user;
    if (state->count < sizeof(state->lines) / sizeof(state->lines[0])) {
        snprintf(state->lines[state->count], sizeof(state->lines[0]), "%s", line);
        state->errors[state->count++] = error;
    }
}

static void journal_progress(void *user, uint64_t completed, uint64_t total,
                             const char *name) {
    journal *state = (journal *)user;
    (void)name;
    if (total > 1U && completed > 0U && completed < total) ++state->moving;
    if (state->stop_at && completed >= state->stop_at) state->stop = true;
    if (state->grow && completed == state->grow_at) {
        /* Outside xxfclib's I/O, which TEST keeps from changing files. */
        FILE *file = fopen(state->grow, "ab");
        if (file) {
            (void)fputc('+', file);
            (void)fclose(file);
        }
        state->grow = NULL;
    }
}

static void journal_test_progress(void *user, unsigned percent) {
    journal *state = (journal *)user;
    if ((int)percent > state->percent) state->percent = (int)percent;
}

static bool journal_cancelled(void *user) {
    return ((const journal *)user)->stop;
}

static size_t journal_find(const journal *state, const char *line, bool error) {
    size_t i, found = 0;
    for (i = 0; i < state->count; ++i)
        if (state->errors[i] == error && strcmp(state->lines[i], line) == 0) ++found;
    return found;
}

static xfu_request journal_request(journal *state, xfu_command command,
                                   const char *archive) {
    xfu_request request = {0};
    memset(state, 0, sizeof(*state));
    request.command = command;
    request.archive_path = archive;
    request.callbacks.user = state;
    request.callbacks.log = journal_log;
    request.callbacks.progress = journal_progress;
    request.callbacks.cancelled = journal_cancelled;
    request.callbacks.test_progress = journal_test_progress;
    state->percent = -1;
    return request;
}

static bool write_pattern(const char *path, size_t size) {
    unsigned char block[4096];
    xx_io_device *file = xx_io_file_open(path, "wb");
    bool result = file != NULL;
    size_t i;
    for (i = 0; i < sizeof(block); ++i) block[i] = (unsigned char)(i * 7U + 3U);
    while (result && size) {
        size_t chunk = size < sizeof(block) ? size : sizeof(block);
        result = xx_io_write(file, block, chunk) == (ssize_t)chunk;
        size -= chunk;
    }
    return file && xx_io_close(file) == 0 && result;
}

/* Text like seq's (one number a line): its deflate stream takes a while to
 * decode, so that each pass over it is seen. */
static bool write_numbers(const char *path, size_t size) {
    char block[4096];
    unsigned long number = 1;
    xx_io_device *file = xx_io_file_open(path, "wb");
    bool result = file != NULL;
    while (result && size) {
        size_t used = 0;
        int written;
        while (used + 24 < sizeof(block) && used < size) {
            written = snprintf(block + used, sizeof(block) - used, "%lu\n", number++);
            used += (size_t)written;
        }
        if (used > size) used = size;
        result = xx_io_write(file, block, used) == (ssize_t)used;
        size -= used;
    }
    return file && xx_io_close(file) == 0 && result;
}

/* A numbered split logs like the native walk: the type, the member's result,
 * the summary; progress steps through the volumes. Cancel inside the member
 * reports it cancelled and counts it as not done. A Cancel while a native
 * writer copies logs "operation cancelled" once and keeps the destination. */
static int split_and_writer_checks(const char *root, const char *const *sources) {
    static journal log;
    char source[2048], first[2048], output[2048], member[2048], kept[2048];
    char grown[2048], absent[2048];
    char line[2300];
    static const char *const suffixes[] = {
        "kept.tar", "kept.tar.gz", "kept.tar.xz", "kept.zip", "kept.7z", "kept.cpio"
    };
    const char *series_sources[1], *missing[2];
    size_t index;
    xfu_request request;
    CHECK(make_path(source, sizeof(source), root, "series.bin"));
    CHECK(make_path(first, sizeof(first), root, "parts/series.bin.001"));
    CHECK(make_path(output, sizeof(output), root, "series-output"));
    CHECK(make_path(member, sizeof(member), output, "series.bin"));
    CHECK(make_path(kept, sizeof(kept), root, "kept.tar"));
    CHECK(make_path(absent, sizeof(absent), root, "missing.txt"));
    missing[0] = sources[0];
    missing[1] = absent;
    CHECK(write_pattern(source, 300000U));
    series_sources[0] = source;
    request = journal_request(&log, XFU_COMMAND_ADD, first);
    request.files = series_sources;
    request.file_count = 1;
    request.volume_size = 65536U;
    CHECK(xfu_run(&request) == 0);
    snprintf(line, sizeof(line), "  %s", source);
    CHECK(log.count == 2 && journal_find(&log, line, false) == 1);
    snprintf(line, sizeof(line), "%s: 1 file(s) as split in 5 volume(s)", first);
    CHECK(journal_find(&log, line, false) == 1);
    request = journal_request(&log, XFU_COMMAND_TEST, first);
    CHECK(xfu_run(&request) == 0);
    snprintf(line, sizeof(line), "%s: Numbered split file", first);
    CHECK(journal_find(&log, line, false) == 1);
    CHECK(journal_find(&log, "  series.bin -- OK", false) == 1);
    CHECK(journal_find(&log, "1 member(s)", false) == 1 && log.count == 3);
    CHECK(log.moving >= 3U);
    CHECK(log.percent == 100);
    request = journal_request(&log, XFU_COMMAND_EXTRACT, first);
    request.output_dir = output;
    CHECK(xfu_run(&request) == 0);
    CHECK(journal_find(&log, "  series.bin", false) == 1);
    CHECK(journal_find(&log, "1 member(s)", false) == 1 && log.count == 3);
    CHECK(xx_io_file_remove_a(member));
    request = journal_request(&log, XFU_COMMAND_EXTRACT, first);
    request.output_dir = output;
    log.stop_at = 2U;
    CHECK(xfu_run(&request) == 1);
    CHECK(journal_find(&log, "  series.bin -- cancelled", true) == 1);
    CHECK(journal_find(&log, "0 member(s)", false) == 1);
    CHECK(journal_find(&log, "operation cancelled", true) == 0 && log.count == 3);
    CHECK(!xx_io_file_exists_a(member));
    request = journal_request(&log, XFU_COMMAND_TEST, first);
    log.stop_at = 3U;
    CHECK(xfu_run(&request) == 1);
    CHECK(journal_find(&log, "  series.bin -- cancelled", true) == 1);
    CHECK(journal_find(&log, "0 member(s)", false) == 1 && log.count == 3);
    CHECK(log.percent < 100);
    /* A volume that grows before it is read fails the member: no 100%. */
    CHECK(make_path(grown, sizeof(grown), root, "parts/series.bin.003"));
    request = journal_request(&log, XFU_COMMAND_TEST, first);
    log.grow = grown;
    log.grow_at = 2U;
    CHECK(xfu_run(&request) == 1);
    CHECK(journal_find(&log, "  series.bin -- FAILED", true) == 1);
    snprintf(line, sizeof(line), "%s: split volume changed before reading", first);
    CHECK(journal_find(&log, line, true) == 1);
    CHECK(journal_find(&log, "1 member(s), 1 failed", true) == 1 && log.count == 4);
    CHECK(log.percent >= 0 && log.percent < 100);

    CHECK(write_fixture(kept, "kept archive\n"));
    request = journal_request(&log, XFU_COMMAND_ADD, kept);
    request.files = sources;
    request.file_count = 2;
    request.archive_format = "pax";
    log.stop_at = 1U;
    CHECK(xfu_run(&request) == 1);
    CHECK(journal_find(&log, "operation cancelled", true) == 1 && log.count == 1);
    CHECK(content_matches(kept, "kept archive\n"));
    /* The suffix-selected xxfclib writers write a stage, too: a Cancel after
     * the first member, or a missing input, keeps the destination. */
    for (index = 0; index < sizeof(suffixes) / sizeof(suffixes[0]); ++index) {
        CHECK(make_path(kept, sizeof(kept), root, suffixes[index]));
        CHECK(write_fixture(kept, "kept archive\n"));
        request = journal_request(&log, XFU_COMMAND_ADD, kept);
        request.files = sources;
        request.file_count = 2;
        log.stop_at = 1U;
        CHECK(xfu_run(&request) == 1);
        CHECK(journal_find(&log, "operation cancelled", true) == 1 && log.count == 1);
        CHECK(content_matches(kept, "kept archive\n"));
        request = journal_request(&log, XFU_COMMAND_ADD, kept);
        request.files = missing;
        request.file_count = 2;
        CHECK(xfu_run(&request) == 2);
        CHECK(log.count == 1 && log.errors[0] && strstr(log.lines[0], "missing.txt: ") != NULL);
        CHECK(content_matches(kept, "kept archive\n"));
    }
    return 0;
}

/* A watch on one run: its Cancel polls, the byte level of the archive file
 * (the first one shown; a layer decoded from it shows its own), and the log
 * lines that tell a Cancel from a decode failure. */
typedef struct decode_watch {
    xx_pd_struct progress;
    unsigned long polls;
    bool stop_while_reading; /* Cancel once the stream has been read into. */
    bool stop;
    uint64_t level_total, level_current;
    size_t cancelled_lines, decode_failures, damaged_lines;
    /* The labels of the stream's passes, in the order they were shown. */
    char passes[8][64];
    size_t pass_count;
    /* The reader's own levels (a decoder's byte count): what each showed
     * last, how often one started its figure again under the label it had,
     * and how often one was seen labelled with a later pass. */
    char level_status[XX_PD_LEVELS][64];
    uint64_t level_seen[XX_PD_LEVELS];
    size_t unlabelled_restarts, labelled_passes;
} decode_watch;

static void watch_log(void *user, bool error, const char *line) {
    decode_watch *state = (decode_watch *)user;
    (void)error;
    if (!strcmp(line, "operation cancelled")) ++state->cancelled_lines;
    if (strstr(line, "could not be decoded") || strstr(line, "could not be read;"))
        ++state->decode_failures;
    if (strstr(line, "compressed stream is damaged")) ++state->damaged_lines;
}

static bool watch_cancelled(void *user) {
    decode_watch *state = (decode_watch *)user;
    int i;
    ++state->polls;
    for (i = 0; i < XX_PD_LEVELS; ++i) {
        const xx_pd_record *record = &state->progress.records[i];
        if (record->is_busy && !strncmp(record->status, "Reading archive", 15) &&
            (!state->pass_count || strcmp(state->passes[state->pass_count - 1], record->status)) &&
            state->pass_count < sizeof(state->passes) / sizeof(state->passes[0]))
            snprintf(state->passes[state->pass_count++], sizeof(state->passes[0]), "%s", record->status);
        if (record->is_busy && strncmp(record->status, "Reading archive", 15)) {
            if (!strcmp(state->level_status[i], record->status) &&
                state->level_seen[i] > (UINT64_C(1) << 20) && record->current < state->level_seen[i] / 2U)
                ++state->unlabelled_restarts;
            if (strstr(record->status, ", pass ") && strcmp(state->level_status[i], record->status))
                ++state->labelled_passes;
            snprintf(state->level_status[i], sizeof(state->level_status[i]), "%s", record->status);
            state->level_seen[i] = record->current;
        }
        if (!record->is_busy || strcmp(record->status, "Reading archive")) continue;
        if (!state->level_total) state->level_total = record->total;
        if (record->total != state->level_total) continue;
        if (record->current > state->level_current) state->level_current = record->current;
        if (state->stop_while_reading && record->current) state->stop = true;
    }
    return state->stop;
}

static xfu_request watch_request(decode_watch *state, xfu_command command,
                                 const char *archive) {
    xfu_request request = {0};
    memset(state, 0, sizeof(*state));
    state->progress = xx_pd_init();
    request.command = command;
    request.archive_path = archive;
    request.progress_state = &state->progress;
    request.callbacks.user = state;
    request.callbacks.log = watch_log;
    request.callbacks.cancelled = watch_cancelled;
    return request;
}

static int64_t file_size(const char *path) {
    xx_io_device *file = xx_io_file_open(path, "rb");
    int64_t size = file ? xx_io_total_size(file) : -1;
    if (file) xx_io_close(file);
    return size;
}

/* A Base64 envelope and an outer stream (a gzip holding a cpio) show the
 * bytes their decoding has read as a progress level. A Cancel while they
 * are decoded is "operation cancelled" and 1, not a decode failure. Cancel
 * is polled about every 10 ms, not on each of the decoders' notifications. */
static int decode_progress_run(const char *source, const char *envelope,
                               const char *outer, const char *plain, const char *output) {
    static decode_watch watch;
    const char *sources[1];
    xfu_request request;
    clock_t started;
    double elapsed_ms;
    size_t index;
    unsigned previous;
    CHECK(write_pattern(source, 24U * 1024U * 1024U));
    sources[0] = source;
    request = watch_request(&watch, XFU_COMMAND_ADD, envelope);
    request.files = sources;
    request.file_count = 1;
    request.archive_format = "raw";
    request.archive_filter = "b64encode";
    CHECK(xfu_run(&request) == 0);
    request = watch_request(&watch, XFU_COMMAND_ADD, outer);
    request.files = sources;
    request.file_count = 1;
    request.archive_format = "newc";
    request.archive_filter = "gzip";
    CHECK(xfu_run(&request) == 0);

    request = watch_request(&watch, XFU_COMMAND_LIST, envelope);
    watch.stop_while_reading = true;
    CHECK(xfu_run(&request) == 1);
    CHECK(watch.stop && watch.cancelled_lines == 1 && watch.decode_failures == 0);
    CHECK(watch.level_total == (uint64_t)file_size(envelope));
    CHECK(watch.level_current < watch.level_total);

    request = watch_request(&watch, XFU_COMMAND_TEST, outer);
    watch.stop_while_reading = true;
    CHECK(xfu_run(&request) == 1);
    CHECK(watch.stop && watch.cancelled_lines == 1 && watch.decode_failures == 0);
    CHECK(watch.level_total == (uint64_t)file_size(outer));

    request = watch_request(&watch, XFU_COMMAND_TEST, outer);
    started = clock();
    CHECK(xfu_run(&request) == 0);
    elapsed_ms = (double)(clock() - started) * 1000.0 / CLOCKS_PER_SEC;
    CHECK(watch.level_total == (uint64_t)file_size(outer));
    CHECK(watch.level_current > 0 && watch.level_current <= watch.level_total);
    CHECK((double)watch.polls <= elapsed_ms / 5.0 + 100.0);

    /* A plain gzip stream is read more than once (a probe for an archive in
     * it, the reader that validates it, the read of its member): each pass
     * that starts the figure again is numbered, so the figure never starts
     * again under the same label. A pass too short to be seen has none. */
    CHECK(write_numbers(source, 32U * 1024U * 1024U));
    request = watch_request(&watch, XFU_COMMAND_ADD, plain);
    request.files = sources;
    request.file_count = 1;
    request.archive_format = "raw";
    request.archive_filter = "gzip";
    CHECK(xfu_run(&request) == 0);
    request = watch_request(&watch, XFU_COMMAND_LIST, plain);
    CHECK(xfu_run(&request) == 0);
    CHECK(watch.pass_count >= 2 && !strcmp(watch.passes[0], "Reading archive"));
    for (index = 1, previous = 1; index < watch.pass_count; ++index) {
        char rest = 0;
        unsigned pass = 0;
        CHECK(sscanf(watch.passes[index], "Reading archive, pass %u%c", &pass, &rest) == 1);
        CHECK(pass > previous);
        previous = pass;
    }
    /* The decoder's own figure ("Unpacking Deflate") starts again with each
     * pass too, and says which pass it is, as the Extract dialog shows it. */
    CHECK(watch.labelled_passes >= 1 && watch.unlabelled_restarts == 0);
    request = watch_request(&watch, XFU_COMMAND_EXTRACT, plain);
    request.output_dir = output;
    CHECK(xfu_run(&request) == 0);
    CHECK(watch.labelled_passes >= 1 && watch.unlabelled_restarts == 0);
    return 0;
}

#ifndef _WIN32
/* Extraction's filesystem policy (xx_io_extract_begin): the output folder
 * and the folders above it may be links; below it a link fails; a link or a
 * hard-linked file at a member's path is replaced, never written through; a
 * path longer than the system takes, or one that fails, leaves no folders. */
static int extract_policy_checks(const char *root) {
    char real[2048], linked[2048], out[2048], outside[2048], target[2048], path[8192];
    xx_io_extract_scope scope = {0}, inner = {0};
    xx_io_device *file;
    struct stat info;
    size_t length;
    CHECK(make_path(real, sizeof(real), root, "policy-real"));
    CHECK(make_path(linked, sizeof(linked), root, "policy-link"));
    CHECK(make_path(outside, sizeof(outside), root, "policy-outside.txt"));
    CHECK(xx_io_create_dirs_a(real, true));
    CHECK(symlink(real, linked) == 0);
    CHECK(write_fixture(outside, "outside\n"));
    CHECK(make_path(out, sizeof(out), linked, "out"));
    CHECK(make_path(path, sizeof(path), out, "a/b.txt"));
    /* Outside a scope a link in the path is refused, as it always was. */
    CHECK(!xx_io_create_dirs_a(path, false));
    CHECK(xx_io_extract_errno() == 0);
    CHECK(xx_io_extract_begin(&scope, out));
    CHECK(xx_io_create_dirs_a(path, false));
    CHECK(xx_io_extract_errno() == 0);
    /* Below the output folder a link, or a file, is in the way. */
    CHECK(make_path(target, sizeof(target), out, "sub"));
    CHECK(symlink(real, target) == 0);
    CHECK(make_path(path, sizeof(path), out, "sub/c.txt"));
    CHECK(!xx_io_create_dirs_a(path, false));
    CHECK(xx_io_extract_errno() == ELOOP);
    xx_io_extract_clear();
    CHECK(make_path(target, sizeof(target), out, "file"));
    CHECK(write_fixture(target, "file\n"));
    CHECK(make_path(path, sizeof(path), out, "file/c.txt"));
    CHECK(!xx_io_create_dirs_a(path, false));
    CHECK(xx_io_extract_errno() == ENOTDIR);
    xx_io_extract_clear();
    /* A link at a member's path is replaced, and so is a hard link. */
    CHECK(make_path(path, sizeof(path), out, "pre"));
    CHECK(symlink(outside, path) == 0);
    file = xx_io_file_open(path, "wb");
    CHECK(file && xx_io_write(file, "member\n", 7) == 7);
    CHECK(xx_io_close(file) == 0);
    CHECK(lstat(path, &info) == 0 && S_ISREG(info.st_mode));
    CHECK(content_matches(outside, "outside\n") && content_matches(path, "member\n"));
    CHECK(make_path(path, sizeof(path), out, "hard"));
    CHECK(link(outside, path) == 0);
    file = xx_io_file_open(path, "wb");
    CHECK(file && xx_io_write(file, "member\n", 7) == 7);
    CHECK(xx_io_close(file) == 0);
    CHECK(content_matches(outside, "outside\n") && content_matches(path, "member\n"));
    CHECK(xx_io_extract_errno() == 0);
    /* Longer than the system takes: refused before any folder is made. */
    CHECK(make_path(path, sizeof(path), out, "long"));
    for (length = strlen(path); length + 201 < 4400; length += 201) {
        path[length] = '/';
        memset(path + length + 1, 'd', 200);
    }
    memcpy(path + length, "/f.txt", 7);
    CHECK(!xx_io_create_dirs_a(path, false));
    CHECK(xx_io_extract_errno() == ENAMETOOLONG);
    CHECK(make_path(target, sizeof(target), out, "long"));
    CHECK(!xx_io_file_exists_a(target));
    xx_io_extract_clear();
    /* A path that fails after folders were made for it: they go again. */
    CHECK(make_path(path, sizeof(path), out, "new/../file/x/y.txt"));
    CHECK(!xx_io_create_dirs_a(path, false));
    CHECK(xx_io_extract_errno() == ENOTDIR);
    CHECK(make_path(target, sizeof(target), out, "new"));
    CHECK(!xx_io_file_exists_a(target));
    /* Scopes nest; only the innermost ends, and the kept failure is its. */
    CHECK(xx_io_extract_begin(&inner, real));
    CHECK(xx_io_extract_errno() == 0);
    CHECK(!xx_io_extract_end(&scope));
    CHECK(xx_io_extract_end(&inner));
    CHECK(xx_io_extract_errno() == ENOTDIR);
    CHECK(xx_io_extract_end(&scope));
    CHECK(xx_io_extract_errno() == 0);
    return 0;
}
#endif

static int decode_progress_checks(const char *root) {
    char source[2048], envelope[2048], outer[2048], plain[2048], output[2048], extracted[2100];
    int result;
    CHECK(make_path(source, sizeof(source), root, "stream.bin"));
    CHECK(make_path(envelope, sizeof(envelope), root, "stream.b64"));
    CHECK(make_path(outer, sizeof(outer), root, "stream.cpio.gz"));
    CHECK(make_path(plain, sizeof(plain), root, "stream.bin.gz"));
    CHECK(make_path(output, sizeof(output), root, "stream-out"));
    CHECK(make_path(extracted, sizeof(extracted), output, "stream.bin"));
    result = decode_progress_run(source, envelope, outer, plain, output);
    /* About 90 MB: not left behind in the test directory. */
    (void)xx_io_file_remove_a(source);
    (void)xx_io_file_remove_a(envelope);
    (void)xx_io_file_remove_a(outer);
    (void)xx_io_file_remove_a(plain);
    (void)xx_io_file_remove_a(extracted);
    return result;
}

/* A decoder's notifications can come thousands a millisecond and then a
 * few a second (bzip2 between its blocks). After such a burst, Cancel is
 * still seen on the first sparse one: the watch counts the sparse calls
 * made before the run stopped. The calls are the xx_pd_is_stopped polls of
 * an entry callback, which reach the core's observer as a decoder's do. */
typedef struct sparse_watch {
    xx_pd_struct progress;
    bool stop, ran;
    unsigned long sparse_calls;
} sparse_watch;

static void sleep_ms(unsigned milliseconds) {
#ifdef _WIN32
    Sleep(milliseconds);
#else
    struct timespec delay;
    delay.tv_sec = 0;
    delay.tv_nsec = (long)milliseconds * 1000000L;
    (void)nanosleep(&delay, NULL);
#endif
}

static bool sparse_cancelled(void *user) {
    return ((const sparse_watch *)user)->stop;
}

static void sparse_entry(void *user, const xfu_entry *item) {
    sparse_watch *state = (sparse_watch *)user;
    unsigned long i;
    (void)item;
    if (state->ran) return;
    state->ran = true;
    for (i = 0; i < 200000UL && !xx_pd_is_stopped(&state->progress); ++i) {}
    state->stop = true;
    while (state->sparse_calls < 200UL) {
        sleep_ms(15U);
        ++state->sparse_calls;
        if (xx_pd_is_stopped(&state->progress)) break;
    }
}

static int sparse_cancel_checks(const char *archive) {
    static sparse_watch watch;
    static const xfu_command commands[] = { XFU_COMMAND_LIST, XFU_COMMAND_TEST };
    size_t index;
    for (index = 0; index < sizeof(commands) / sizeof(commands[0]); ++index) {
        xfu_request request = {0};
        memset(&watch, 0, sizeof(watch));
        watch.progress = xx_pd_init();
        request.command = commands[index];
        request.archive_path = archive;
        request.progress_state = &watch.progress;
        request.callbacks.user = &watch;
        request.callbacks.entry = sparse_entry;
        request.callbacks.cancelled = sparse_cancelled;
        CHECK(xfu_run(&request) == 1);
        CHECK(watch.ran && watch.stop);
        CHECK(watch.sparse_calls >= 1UL && watch.sparse_calls <= 3UL);
    }
    return 0;
}

/* A file member is read only as the walk found it: replaced since by a link,
 * by another file or by more data, it is refused, so the writers never read a
 * swapped-in file in its place. A named input's link may lead to it. */
static int member_open_checks(const char *root) {
#ifdef _WIN32
    (void)root;
    return 0;
#else
    char path[2048], other[2048], fresh[2048], named[2048], buffer[32];
    struct stat info;
    xfu_native_member member;
    xx_io_device *file;
    CHECK(make_path(path, sizeof(path), root, "member.txt"));
    CHECK(make_path(other, sizeof(other), root, "secret.txt"));
    CHECK(make_path(fresh, sizeof(fresh), root, "fresh.txt"));
    CHECK(make_path(named, sizeof(named), root, "named-link.txt"));
    CHECK(write_fixture(path, "walked member\n"));
    CHECK(write_fixture(other, "private data!\n"));
    CHECK(stat(path, &info) == 0);
    memset(&member, 0, sizeof(member));
    member.path = path;
    member.name = "member.txt";
    member.size = (int64_t)info.st_size;
    member.device = (uint64_t)info.st_dev;
    member.inode = (uint64_t)info.st_ino;
    member.walked = true;
    CHECK((file = xfu_native_open_member(&member)) != NULL);
    CHECK(xx_io_total_size(file) == 14);
    CHECK(xx_io_read(file, buffer, sizeof(buffer)) == 14 && !memcmp(buffer, "walked member\n", 14));
    CHECK(xx_io_close(file) == 0);
    /* A named link to the walked file is followed. */
    CHECK(symlink(path, named) == 0);
    member.path = named;
    member.walked = false;
    CHECK((file = xfu_native_open_member(&member)) != NULL && xx_io_close(file) == 0);
    member.path = path;
    member.walked = true;
    /* Swapped for a link to a file of the same size: refused as a walked
     * member, and as a named one (the link leads elsewhere). */
    CHECK(rename(path, fresh) == 0 && symlink(other, path) == 0);
    CHECK(xfu_native_open_member(&member) == NULL);
    member.walked = false;
    CHECK(xfu_native_open_member(&member) == NULL);
    member.walked = true;
    /* Replaced by another file of the same size, then grown in place. */
    CHECK(unlink(path) == 0 && write_fixture(path, "walked member\n"));
    CHECK(xfu_native_open_member(&member) == NULL);
    CHECK(unlink(path) == 0 && rename(fresh, path) == 0);
    CHECK((file = xfu_native_open_member(&member)) != NULL && xx_io_close(file) == 0);
    CHECK(write_fixture(path, "walked member, grown\n"));
    CHECK(xfu_native_open_member(&member) == NULL);
    /* A FIFO put in its place does not block the open. */
    CHECK(unlink(path) == 0 && mkfifo(path, 0600) == 0);
    CHECK(xfu_native_open_member(&member) == NULL);
    CHECK(unlink(path) == 0 && unlink(named) == 0 && unlink(other) == 0);
    return 0;
#endif
}

static bool has_tar_header(const char *path) {
    char buffer[512];
    xx_io_device *file = xx_io_file_open(path, "rb");
    bool result;
    if (!file) return false;
    result = xx_io_read(file, buffer, sizeof(buffer)) == (ssize_t)sizeof(buffer) &&
        memcmp(buffer + 257, "ustar", 5) == 0;
    return xx_io_close(file) == 0 && result;
}

/* A cut .tar.xz or .tar.zst is no Binary file: the File type list names it
 * as the log does, so that Test and Extract can run on it. List, Test and a
 * pick of the compressed TAR read the members of its decoded prefix, an
 * incomplete archive whose cut member fails (1); a pick of the stream type
 * reads one stream, which is damaged (2). */
static int damaged_type_checks(const char *root) {
    static const char *const names[] = {"cut.tar.xz", "cut.tar.zst"};
    static const xx_file_type_t streams[] = {XX_FILE_TYPE_XZ, XX_FILE_TYPE_ZSTD};
    static const xx_file_type_t tars[] = {XX_FILE_TYPE_TAR_XZ, XX_FILE_TYPE_TAR_ZSTD};
    static char text[65536], data[1 << 18];
    char source[2048], cut[2048];
    const char *sources[1];
    capture probed;
    xfu_request request;
    xx_io_device *file;
    ssize_t size;
    size_t i, kind, run;
    unsigned seed = 1;
    for (i = 0; i + 1 < sizeof(text); ++i) {
        seed = seed * 1103515245U + 12345U;
        text[i] = (char)('a' + (seed >> 16) % 26);
    }
    CHECK(make_path(source, sizeof(source), root, "damaged-source.txt"));
    CHECK(write_fixture(source, text));
    sources[0] = source;
    for (kind = 0; kind < 2; ++kind) {
        CHECK(make_path(cut, sizeof(cut), root, names[kind]));
        memset(&probed, 0, sizeof(probed));
        request = request_for(&probed, XFU_COMMAND_ADD, cut);
        request.files = sources;
        request.file_count = 1;
        CHECK(xfu_run(&request) == 0);
        CHECK((file = xx_io_file_open(cut, "rb")) != NULL);
        size = xx_io_read(file, data, sizeof(data));
        CHECK(xx_io_close(file) == 0 && size > 64 && size < (ssize_t)sizeof(data));
        CHECK((file = xx_io_file_open(cut, "wb")) != NULL);
        CHECK(xx_io_write(file, data, (size_t)size / 2) == size / 2);
        CHECK(xx_io_close(file) == 0);
        for (run = 0; run < 4; ++run) {
            memset(&probed, 0, sizeof(probed));
            request = request_for(&probed, run ? XFU_COMMAND_TEST : XFU_COMMAND_LIST, cut);
            if (run >= 2) request.file_type = run == 2 ? tars[kind] : streams[kind];
            CHECK(xfu_run(&request) == (run == 3 ? 2 : 1));
            CHECK(probed.selected == (run == 3 ? streams[kind] : tars[kind]));
            CHECK(probed.selected_in_chain && probed.not_archive_calls == 0);
            CHECK(probed.type_count >= 2 && probed.types[0] == XX_FILE_TYPE_BINARY);
        }
    }
    return 0;
}

/* Extract of one member of a cut .tar.gz, which no check covers: the line
 * of the archive says that members were read without a checksum when the
 * member picked is one of them, and not when it is the member the cut goes
 * through, which fails and is not read. */
static int cut_selection_checks(const char *root) {
    static char text[65536], data[1 << 17];
    static const size_t first_only[] = {0}, cut_only[] = {1};
    char first[2048], second[2048], cut[2048], output[2048], member[2048];
    char recovered[2400], unverified[2400];
    const char *sources[2];
    journal log;
    xfu_request request;
    xx_io_device *file;
    ssize_t size;
    size_t i, run;
    unsigned seed = 7;
    for (i = 0; i + 1 < sizeof(text); ++i) {
        seed = seed * 1103515245U + 12345U;
        text[i] = (char)('a' + (seed >> 16) % 26);
    }
    CHECK(make_path(first, sizeof(first), root, "selection-first.txt"));
    CHECK(make_path(second, sizeof(second), root, "selection-second.txt"));
    CHECK(make_path(cut, sizeof(cut), root, "selection.tar.gz"));
    CHECK(write_fixture(first, "before the cut\n"));
    CHECK(write_fixture(second, text));
    sources[0] = first;
    sources[1] = second;
    request = journal_request(&log, XFU_COMMAND_ADD, cut);
    request.files = sources;
    request.file_count = 2;
    CHECK(xfu_run(&request) == 0);
    /* Half of the stream: the cut goes through the second member. */
    CHECK((file = xx_io_file_open(cut, "rb")) != NULL);
    size = xx_io_read(file, data, sizeof(data));
    CHECK(xx_io_close(file) == 0 && size > 64 && size < (ssize_t)sizeof(data));
    CHECK((file = xx_io_file_open(cut, "wb")) != NULL);
    CHECK(xx_io_write(file, data, (size_t)size / 2) == size / 2);
    CHECK(xx_io_close(file) == 0);
    snprintf(recovered, sizeof(recovered), "%s: incomplete archive; showing recovered members", cut);
    snprintf(unverified, sizeof(unverified),
             "%s: incomplete archive; members before the cut were read without a checksum", cut);
    for (run = 0; run < 2; ++run) {
        CHECK(make_path(output, sizeof(output), root, run ? "selection-first" : "selection-cut"));
        request = journal_request(&log, XFU_COMMAND_EXTRACT, cut);
        request.output_dir = output;
        request.extract_selected = true;
        request.selected_records = run ? first_only : cut_only;
        request.selected_record_count = 1;
        CHECK(xfu_run(&request) == 1);
        CHECK(journal_find(&log, run ? unverified : recovered, true) == 1);
        CHECK(journal_find(&log, run ? recovered : unverified, true) == 0);
    }
    CHECK(make_path(member, sizeof(member), output, "selection-first.txt"));
    CHECK(content_matches(member, "before the cut\n"));
    return 0;
}

int main(int argc, char **argv) {
    char root[2048], first[2048], second[2048], archive[2048];
    char output[2048], output_first[2048], output_second[2048];
    char rejected[2048], cancelled_archive[2048], cancelled_output[2048];
    char outer_output[2048], outer_member[2048];
    char ar_archive[2048], ar_source[2048], ar_output[2048], ar_member[2048];
    char notes[2048], blob[2048], notes_output[2048], parts[2048], parts_output[2048];
    char wrapped[2048], wrapped_raw[2048], wrapped_output[2048];
    char locale_before[256];
    const char *sources[2];
    const char *ar_sources[1];
    const size_t selection[] = {1};
    const size_t first_selection[] = {0};
    capture listed = {0}, extracted = {0}, rejected_state = {0}, stopped = {0};
    capture outer_listed = {0}, outer_extracted = {0}, writing = {0};
    capture ar_listed = {0}, ar_extracted = {0};
    capture probed = {0};
    static const char *const passwords[] = {NULL, "", "typed for another archive"};
    static const xx_file_type_t layer_picks[] = {
        XX_FILE_TYPE_UNKNOWN, XX_FILE_TYPE_TAR, XX_FILE_TYPE_UUE, XX_FILE_TYPE_BINARY
    };
    size_t index;
    xfu_request request;
    const char *locale_name;
    int size;
#ifdef _WIN32
    int locale_mode = _configthreadlocale(0);
#endif
    CHECK(argc == 2);
    locale_name = setlocale(LC_CTYPE, NULL);
    CHECK(locale_name != NULL);
    CHECK(strlen(locale_name) < sizeof(locale_before));
    strcpy(locale_before, locale_name);
    CHECK(xx_io_create_dirs_a(argv[1], true));
    size = snprintf(root, sizeof(root), "%s/run-%lu-%p", argv[1],
        (unsigned long)time(NULL), (void *)&listed);
    CHECK(size >= 0 && (size_t)size < sizeof(root));
    CHECK(xx_io_create_dirs_a(root, true));
    CHECK(make_path(first, sizeof(first), root, "first.txt"));
    CHECK(make_path(second, sizeof(second), root, "second.txt"));
    CHECK(make_path(archive, sizeof(archive), root, "selection.tar.gz"));
    CHECK(make_path(output, sizeof(output), root, "selected"));
    CHECK(make_path(rejected, sizeof(rejected), root, "rejected"));
    CHECK(make_path(cancelled_archive, sizeof(cancelled_archive), root, "cancelled.tar"));
    CHECK(make_path(cancelled_output, sizeof(cancelled_output), root, "cancelled-output"));
    CHECK(make_path(outer_output, sizeof(outer_output), root, "outer-stream"));
    CHECK(make_path(ar_archive, sizeof(ar_archive), root, "long.ar"));
    CHECK(make_path(ar_source, sizeof(ar_source), root, "a-long-static-library-object-name.o"));
    CHECK(make_path(ar_output, sizeof(ar_output), root, "ar-selected"));
    CHECK(write_fixture(first, "first member\n"));
    CHECK(write_fixture(second, "second member\n"));
    sources[0] = first;
    sources[1] = second;

    request = request_for(&listed, XFU_COMMAND_ADD, archive);
    request.files = sources;
    request.file_count = 2;
    request.archive_format = "pax";
    request.archive_filter = "gzip";
    CHECK(xfu_run(&request) == 0);

    request = request_for(&listed, XFU_COMMAND_LIST, archive);
    CHECK(xfu_run(&request) == 0);
    CHECK(listed.entries == 2);
    CHECK(listed.selected == XX_FILE_TYPE_TAR_GZ);
    CHECK(listed.selected_in_chain);
    CHECK(listed.type_count == 4);
    CHECK(listed.types[0] == XX_FILE_TYPE_BINARY);
    CHECK(listed.types[1] == XX_FILE_TYPE_ARCHIVE);
    CHECK(listed.types[2] == XX_FILE_TYPE_GZ);
    CHECK(listed.types[3] == XX_FILE_TYPE_TAR_GZ);
    CHECK(strcmp(listed.names[0], "first.txt") == 0);
    CHECK(strcmp(listed.names[1], "second.txt") == 0);
    CHECK(listed.actionable_handles && listed.selected_handle_available);
    CHECK(listed.selected_handle == XX_HANDLE_TYPE_TAR_GZ);
    CHECK(captured_handle(&listed, XX_HANDLE_TYPE_GZ));
    CHECK(captured_handle(&listed, XX_HANDLE_TYPE_TAR_GZ));

    /* Both unpack methods apply to the same input. The independent handle
     * selection controls whether its TAR is a single member or is opened. */
    memset(&probed, 0, sizeof(probed));
    request = request_for(&probed, XFU_COMMAND_LIST, archive);
    request.handle_type = XX_HANDLE_TYPE_GZ;
    CHECK(xfu_run(&request) == 0);
    CHECK(probed.entries == 1 && probed.selected_handle == XX_HANDLE_TYPE_GZ);
    CHECK(probed.actionable_handles && probed.selected_handle_available);
    CHECK(captured_handle(&probed, XX_HANDLE_TYPE_TAR_GZ));
    memset(&probed, 0, sizeof(probed));
    request = request_for(&probed, XFU_COMMAND_LIST, archive);
    request.handle_type = XX_HANDLE_TYPE_TAR_GZ;
    CHECK(xfu_run(&request) == 0);
    CHECK(probed.entries == 2 && probed.selected_handle == XX_HANDLE_TYPE_TAR_GZ);
    CHECK(strcmp(probed.names[0], "first.txt") == 0);
    CHECK(probed.actionable_handles && probed.selected_handle_available);

    memset(&probed, 0, sizeof(probed));
    request = request_for(&probed, XFU_COMMAND_LIST, archive);
    request.handle_type = XX_HANDLE_TYPE_ZIP;
    CHECK(xfu_run(&request) == 2);
    CHECK(probed.entries == 0);
    request.handle_type = (xx_handle_type_t)XX_FILE_TYPE_TAR_GZ;
    CHECK(xfu_run(&request) == 2);
    CHECK(probed.entries == 0);
    request.handle_type = XX_HANDLE_TYPE_TAR_GZ;
    request.file_type = XX_FILE_TYPE_GZ;
    CHECK(xfu_run(&request) == 2);
    request.file_type = XX_FILE_TYPE_UNKNOWN;
    request.reader_name = "native";
    CHECK(xfu_run(&request) == 2);
    CHECK(probed.entries == 0);

    request = request_for(&extracted, XFU_COMMAND_EXTRACT, archive);
    request.file_type = listed.selected;
    request.output_dir = output;
    request.extract_selected = true;
    request.selected_records = selection;
    request.selected_record_count = 1;
    CHECK(xfu_run(&request) == 0);
    CHECK(extracted.selected == listed.selected);
    CHECK(extracted.selected_in_chain);
    CHECK(extracted.type_count == listed.type_count);
    CHECK(memcmp(extracted.types, listed.types, listed.type_count * sizeof(listed.types[0])) == 0);
    CHECK(extracted.entries == 1);
    CHECK(strcmp(extracted.names[0], listed.names[1]) == 0);
    CHECK(make_path(output_first, sizeof(output_first), output, "first.txt"));
    CHECK(make_path(output_second, sizeof(output_second), output, "second.txt"));
    CHECK(!xx_io_file_exists_a(output_first));
    CHECK(content_matches(output_second, "second member\n"));

    request = request_for(&outer_listed, XFU_COMMAND_LIST, archive);
    request.file_type = XX_FILE_TYPE_GZ;
    CHECK(xfu_run(&request) == 0);
    CHECK(outer_listed.entries == 1);
    CHECK(outer_listed.selected == XX_FILE_TYPE_GZ);
    CHECK(outer_listed.selected_in_chain);
    CHECK(outer_listed.type_count == 4);
    CHECK(outer_listed.types[0] == XX_FILE_TYPE_BINARY);
    CHECK(outer_listed.types[1] == XX_FILE_TYPE_ARCHIVE);
    CHECK(outer_listed.types[2] == XX_FILE_TYPE_GZ);
    CHECK(outer_listed.types[3] == XX_FILE_TYPE_TAR_GZ);
    request = request_for(&outer_extracted, XFU_COMMAND_EXTRACT, archive);
    request.file_type = outer_listed.selected;
    request.output_dir = outer_output;
    CHECK(xfu_run(&request) == 0);
    CHECK(outer_extracted.entries == 1);
    CHECK(strcmp(outer_extracted.names[0], outer_listed.names[0]) == 0);
    CHECK(make_path(outer_member, sizeof(outer_member), outer_output, outer_listed.names[0]));
    CHECK(has_tar_header(outer_member));

    CHECK(write_fixture(ar_source, "ar member\n"));
    ar_sources[0] = ar_source;
    request = request_for(&ar_listed, XFU_COMMAND_ADD, ar_archive);
    request.files = ar_sources;
    request.file_count = 1;
    request.archive_format = "ar_svr4";
    CHECK(xfu_run(&request) == 0);
    request = request_for(&ar_listed, XFU_COMMAND_LIST, ar_archive);
    CHECK(xfu_run(&request) == 0);
    CHECK(ar_listed.entries == 1);
    CHECK(ar_listed.selected == XX_FILE_TYPE_AR);
    CHECK(ar_listed.selected_in_chain);
    CHECK(ar_listed.type_count == 2);
    CHECK(ar_listed.types[0] == XX_FILE_TYPE_BINARY);
    CHECK(ar_listed.types[1] == XX_FILE_TYPE_AR);
    request = request_for(&ar_extracted, XFU_COMMAND_EXTRACT, ar_archive);
    request.file_type = ar_listed.selected;
    request.output_dir = ar_output;
    request.extract_selected = true;
    request.selected_records = first_selection;
    request.selected_record_count = 1;
    CHECK(xfu_run(&request) == 0);
    CHECK(ar_extracted.entries == 1);
    CHECK(strcmp(ar_extracted.names[0], ar_listed.names[0]) == 0);
    CHECK(make_path(ar_member, sizeof(ar_member), ar_output, ar_listed.names[0]));
    CHECK(content_matches(ar_member, "ar member\n"));
    CHECK(split_and_writer_checks(root, sources) == 0);

    request = request_for(&rejected_state, XFU_COMMAND_EXTRACT, archive);
    request.file_type = XX_FILE_TYPE_ZIP;
    request.output_dir = rejected;
    CHECK(xfu_run(&request) == 2);
    CHECK(!xx_io_file_exists_a(rejected));
    CHECK(rejected_state.entries == 0);
    request.file_type = XX_FILE_TYPE_TAR;
    CHECK(xfu_run(&request) == 2);
    CHECK(!xx_io_file_exists_a(rejected));
    CHECK(rejected_state.entries == 0);
    request.command = XFU_COMMAND_LIST;
    request.file_type = XX_FILE_TYPE_BINARY;
    CHECK(xfu_run(&request) == 2);
    request.reader_name = "native";
    CHECK(xfu_run(&request) == 2);
    request.file_type = XX_FILE_TYPE_ZIP;
    CHECK(xfu_run(&request) == 2);
    CHECK(rejected_state.entries == 0);

    stopped.stop = true;
    request = request_for(&stopped, XFU_COMMAND_ADD, cancelled_archive);
    request.files = sources;
    request.file_count = 2;
    request.archive_format = "pax";
    CHECK(xfu_run(&request) == 1);
    CHECK(!xx_io_file_exists_a(cancelled_archive));
    request = request_for(&stopped, XFU_COMMAND_EXTRACT, archive);
    request.output_dir = cancelled_output;
    CHECK(xfu_run(&request) == 1);
    CHECK(!xx_io_file_exists_a(cancelled_output));
    CHECK(stopped.entries == 0);
    CHECK(write_fixture(cancelled_archive, "preserve cancelled output\n"));
    request = request_for(&writing, XFU_COMMAND_ADD, cancelled_archive);
    request.callbacks.progress = cancel_creation;
    request.files = sources;
    request.file_count = 1;
    request.archive_format = "brotli";
    CHECK(xfu_run(&request) == 2);
    CHECK(!writing.stop);
    CHECK(content_matches(cancelled_archive, "preserve cancelled output\n"));
    request.file_count = 2;
    request.archive_format = "zpaq";
    CHECK(xfu_run(&request) == 2);
    CHECK(!writing.stop);
    CHECK(content_matches(cancelled_archive, "preserve cancelled output\n"));

    /* Like Binary, a recognised type without members (Text, by its
     * extension) is no archive: 2 through the not_archive call, nothing
     * listed or written. An archive makes no such call. */
    CHECK(listed.not_archive_calls == 0 && extracted.not_archive_calls == 0);
    CHECK(make_path(notes, sizeof(notes), root, "notes.txt"));
    CHECK(make_path(notes_output, sizeof(notes_output), root, "notes-output"));
    CHECK(make_path(blob, sizeof(blob), root, "blob.bin"));
    CHECK(write_fixture(notes, "hello\nworld\nid,name,qty\n"));
    CHECK(write_fixture(blob, "\x01\x02\x03\x04 plain bytes\x05"));
    for (index = 0; index < 3; ++index) {
        static const xfu_command commands[] = {
            XFU_COMMAND_LIST, XFU_COMMAND_TEST, XFU_COMMAND_EXTRACT
        };
        memset(&probed, 0, sizeof(probed));
        request = request_for(&probed, commands[index], notes);
        request.output_dir = commands[index] == XFU_COMMAND_EXTRACT ? notes_output : NULL;
        CHECK(xfu_run(&request) == 2);
        CHECK(probed.entries == 0 && probed.selected == XX_FILE_TYPE_TEXT);
        CHECK(probed.not_archive_calls == 1 && probed.not_archive == XX_FILE_TYPE_TEXT);
        CHECK(probed.handle_count == 0 && probed.selected_handle == XX_HANDLE_TYPE_UNKNOWN);
        CHECK(!xx_io_file_exists_a(notes_output));
    }
    memset(&probed, 0, sizeof(probed));
    request = request_for(&probed, XFU_COMMAND_LIST, blob);
    CHECK(xfu_run(&request) == 2);
    CHECK(probed.not_archive_calls == 1 && probed.not_archive == XX_FILE_TYPE_BINARY);
    CHECK(probed.handle_count == 0 && probed.selected_handle == XX_HANDLE_TYPE_UNKNOWN);

    /* A split series has no password: an explicitly empty one, or one typed
     * for another archive, reads it as no password does. */
    CHECK(make_path(parts, sizeof(parts), root, "parts.001"));
    CHECK(make_path(parts_output, sizeof(parts_output), root, "parts-output"));
    sources[0] = first;
    memset(&probed, 0, sizeof(probed));
    request = request_for(&probed, XFU_COMMAND_ADD, parts);
    request.files = sources;
    request.file_count = 1;
    request.volume_size = 8;
    CHECK(xfu_run(&request) == 0);
    for (index = 0; index < sizeof(passwords) / sizeof(passwords[0]); ++index) {
        memset(&probed, 0, sizeof(probed));
        request = request_for(&probed, XFU_COMMAND_LIST, parts);
        request.password = passwords[index];
        CHECK(xfu_run(&request) == 0);
        CHECK(probed.entries == 1 && probed.selected == XX_FILE_TYPE_NUMBERED_SPLIT);
        memset(&probed, 0, sizeof(probed));
        request = request_for(&probed, XFU_COMMAND_TEST, parts);
        request.password = passwords[index];
        CHECK(xfu_run(&request) == 0);
    }
    request = request_for(&probed, XFU_COMMAND_EXTRACT, parts);
    request.password = "";
    request.output_dir = parts_output;
    CHECK(xfu_run(&request) == 0);

    /* A read inside an envelope lists the envelope's types first, and every
     * type listed can be picked: the TAR read inside it, the envelope's one
     * member, or Binary (no archive). */
    CHECK(make_path(wrapped, sizeof(wrapped), root, "wrapped.bin"));
    CHECK(make_path(wrapped_raw, sizeof(wrapped_raw), root, "wrapped-raw.bin"));
    CHECK(make_path(wrapped_output, sizeof(wrapped_output), root, "wrapped-output"));
    sources[0] = first;
    sources[1] = second;
    memset(&probed, 0, sizeof(probed));
    request = request_for(&probed, XFU_COMMAND_ADD, wrapped);
    request.files = sources;
    request.file_count = 2;
    request.archive_format = "pax";
    request.archive_filter = "uuencode";
    CHECK(xfu_run(&request) == 0);
    for (index = 0; index < sizeof(layer_picks) / sizeof(layer_picks[0]); ++index) {
        xx_file_type_t pick = layer_picks[index];
        memset(&probed, 0, sizeof(probed));
        request = request_for(&probed, XFU_COMMAND_LIST, wrapped);
        request.file_type = pick;
        CHECK(xfu_run(&request) == (pick == XX_FILE_TYPE_BINARY ? 2 : 0));
        CHECK(probed.selected == (pick == XX_FILE_TYPE_UNKNOWN ? XX_FILE_TYPE_TAR : pick));
        CHECK(probed.selected_in_chain);
        CHECK(probed.types[0] == XX_FILE_TYPE_BINARY && probed.types[1] == XX_FILE_TYPE_UUE);
        CHECK(probed.entries == (pick == XX_FILE_TYPE_BINARY ? 0U : pick == XX_FILE_TYPE_UUE ? 1U : 2U));
        if (pick != XX_FILE_TYPE_UUE && pick != XX_FILE_TYPE_BINARY) {
            CHECK(probed.type_count == 3 && probed.types[2] == XX_FILE_TYPE_TAR);
            CHECK(strcmp(probed.names[0], "first.txt") == 0);
        }
    }
    memset(&probed, 0, sizeof(probed));
    request = request_for(&probed, XFU_COMMAND_EXTRACT, wrapped);
    request.handle_type = XX_HANDLE_TYPE_TAR;
    request.output_dir = wrapped_output;
    CHECK(xfu_run(&request) == 0);
    CHECK(make_path(output_second, sizeof(output_second), wrapped_output, "second.txt"));
    CHECK(content_matches(output_second, "second member\n"));
    CHECK(probed.selected_handle == XX_HANDLE_TYPE_TAR && probed.selected_handle_available);
    CHECK(captured_handle(&probed, XX_HANDLE_TYPE_UUE));
    CHECK(captured_handle(&probed, XX_HANDLE_TYPE_TAR));
    memset(&probed, 0, sizeof(probed));
    request = request_for(&probed, XFU_COMMAND_LIST, wrapped);
    request.handle_type = XX_HANDLE_TYPE_UUE;
    CHECK(xfu_run(&request) == 0);
    CHECK(probed.entries == 1 && probed.selected_handle == XX_HANDLE_TYPE_UUE);
    CHECK(probed.actionable_handles && probed.selected_handle_available);
    memset(&probed, 0, sizeof(probed));
    request = request_for(&probed, XFU_COMMAND_ADD, wrapped_raw);
    request.files = sources;
    request.file_count = 1;
    request.archive_format = "raw";
    request.archive_filter = "uuencode";
    CHECK(xfu_run(&request) == 0);
    memset(&probed, 0, sizeof(probed));
    request = request_for(&probed, XFU_COMMAND_LIST, wrapped_raw);
    CHECK(xfu_run(&request) == 0);
    CHECK(probed.entries == 1 && probed.selected == XX_FILE_TYPE_UUE && probed.selected_in_chain);
    CHECK(probed.type_count == 2 && probed.types[0] == XX_FILE_TYPE_BINARY);
    CHECK(decode_progress_checks(root) == 0);
    CHECK(sparse_cancel_checks(archive) == 0);
    CHECK(member_open_checks(root) == 0);
    CHECK(damaged_type_checks(root) == 0);
    CHECK(cut_selection_checks(root) == 0);
#ifndef _WIN32
    CHECK(extract_policy_checks(root) == 0);
#endif
    CHECK(strcmp(setlocale(LC_CTYPE, NULL), locale_before) == 0);
#ifdef _WIN32
    CHECK(_configthreadlocale(0) == locale_mode);
#endif
    puts("native core selection and cancellation checks passed");
    return 0;
}
