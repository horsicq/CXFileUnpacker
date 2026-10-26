/* SPDX-License-Identifier: MIT */
#include "native_reader_backend.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <xxfclib/algo/crc/xx_crc.h>
#include <xxfclib/formats/other/base64/xx_base64.h>
#include <xxfclib/formats/archive/bz2/xx_bz2.h>
#include <xxfclib/formats/archive/gz/xx_gz.h>
#include <xxfclib/formats/xx_format.h>
#include <xxfclib/io/xx_io.h>
#include <xxfclib/algo/zstd/xx_zstd.h>
#ifndef _WIN32
#include <signal.h>
#include <sys/resource.h>
#endif

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); return 1; \
} } while (0)

typedef struct capture {
    unsigned entries;
    unsigned tests;
    unsigned complete;
    unsigned percent;
    bool test_success;
    bool cancel;
    unsigned polls;
    unsigned cancel_after;
    xx_file_type_t type;
    char name[128];
    char log[1024];
} capture;

static void entry_cb(void *user, const xfu_entry *entry) {
    capture *state = (capture *)user;
    ++state->entries;
    snprintf(state->name, sizeof(state->name), "%s", entry->name);
}

static void types_cb(void *user, const xx_file_type_t *types, size_t count,
                     xx_file_type_t selected) {
    capture *state = (capture *)user;
    if (count == 1 && types[0] == selected) state->type = selected;
}

static void test_cb(void *user, const xfu_entry *entry, bool success) {
    capture *state = (capture *)user;
    (void)entry;
    ++state->tests;
    state->test_success = success;
}

static void percent_cb(void *user, unsigned percent) {
    ((capture *)user)->percent = percent;
}

static void walk_cb(void *user, bool complete) {
    if (complete) ++((capture *)user)->complete;
}

static bool cancel_cb(void *user) {
    capture *state = (capture *)user;
    return state->cancel ||
        (state->cancel_after && ++state->polls >= state->cancel_after);
}

static void log_cb(void *user, bool error, const char *line) {
    capture *state = (capture *)user;
    size_t used = strlen(state->log);
    snprintf(state->log + used, sizeof(state->log) - used, "%s%s\n",
             error ? "!" : "", line);
}

static bool write_file(const char *path, const char *content) {
    xx_io_device *file = xx_io_file_open(path, "wb");
    size_t size = strlen(content);
    bool okay;
    if (!file) return false;
    okay = xx_io_write(file, content, size) == (ssize_t)size;
    return xx_io_close(file) == 0 && okay;
}

static bool write_bytes(const char *path, const unsigned char *content,
                        size_t size) {
    xx_io_device *file = xx_io_file_open(path, "wb");
    bool okay;
    if (!file) return false;
    okay = xx_io_write(file, content, size) == (ssize_t)size;
    return xx_io_close(file) == 0 && okay;
}

static bool file_matches(const char *path, const char *content) {
    xx_io_device *file = xx_io_file_open(path, "rb");
    char buffer[128];
    ssize_t got;
    bool okay;
    if (!file) return false;
    got = xx_io_read(file, buffer, sizeof(buffer));
    okay = got == (ssize_t)strlen(content) && !memcmp(buffer, content, (size_t)got);
    return xx_io_close(file) == 0 && okay;
}

static bool device_matches(xx_io_device *device, const unsigned char *content,
                           size_t size) {
    unsigned char buffer[256];
    if (!device || size > sizeof(buffer) || xx_io_total_size(device) != (int64_t)size ||
        xx_io_seek64(device, 0, SEEK_SET) != 0) return false;
    return xx_io_read(device, buffer, size) == (ssize_t)size &&
        !memcmp(buffer, content, size);
}

static xfu_request request_for(const char *path, xfu_command command,
                               capture *state) {
    xfu_request request = {0};
    request.archive_path = path;
    request.command = command;
    request.callbacks.user = state;
    request.callbacks.entry = entry_cb;
    request.callbacks.file_types = types_cb;
    request.callbacks.test_result = test_cb;
    request.callbacks.test_progress = percent_cb;
    request.callbacks.walk_end = walk_cb;
    request.callbacks.cancelled = cancel_cb;
    return request;
}

/* The raw reader logs like the member walk: no reader-specific wording. */
static int check_raw_log_lines(const char *root) {
    static const char text[] = "logged raw member\n";
    char path[2048], output[2048], extracted[2100];
    unsigned char *big;
    capture state = {0};
    xfu_request request;
    xx_pd_struct pd;
    CHECK(snprintf(path, sizeof(path), "%s/member.txt", root) > 0);
    CHECK(snprintf(output, sizeof(output), "%s/logged", root) > 0);
    CHECK(write_file(path, text));
    request = request_for(path, XFU_COMMAND_LIST, &state);
    request.callbacks.log = log_cb;
    request.callbacks.test_result = NULL;
    pd = xx_pd_init();
    CHECK(xfu_native_raw_read(&request, NULL, &pd) == 0);
    CHECK(strstr(state.log, "  member.txt\n") && strstr(state.log, "\n1 member(s)\n"));
    memset(&state, 0, sizeof(state));
    request.command = XFU_COMMAND_TEST;
    pd = xx_pd_init();
    CHECK(xfu_native_raw_read(&request, NULL, &pd) == 0);
    CHECK(strstr(state.log, "\n  member.txt -- OK\n1 member(s)\n"));
    CHECK(!strstr(state.log, "raw input"));
    memset(&state, 0, sizeof(state));
    request.command = XFU_COMMAND_EXTRACT;
    CHECK(snprintf(extracted, sizeof(extracted), "%s/member.txt", output) > 0);
    (void)xx_io_file_remove_a(extracted); /* left by an earlier run */
    pd = xx_pd_init();
    CHECK(xfu_native_raw_read(&request, output, &pd) == 0);
    CHECK(strstr(state.log, "\n  member.txt\n1 member(s)\n"));
    /* A file already there is replaced, and the line says so (core.h). */
    CHECK(write_file(extracted, "old\n"));
    memset(&state, 0, sizeof(state));
    pd = xx_pd_init();
    CHECK(xfu_native_raw_read(&request, output, &pd) == 0);
    CHECK(strstr(state.log, "\n  member.txt -- replaced an existing file\n1 member(s)\n"));
    CHECK(file_matches(extracted, text));
    /* Cancel inside the data: one "-- cancelled" line, nothing counted,
     * and no failure claimed for the input. */
    big = (unsigned char *)calloc(1, 300000);
    CHECK(big);
    CHECK(snprintf(path, sizeof(path), "%s/big.bin", root) > 0);
    CHECK(write_bytes(path, big, 300000));
    free(big);
    memset(&state, 0, sizeof(state));
    state.cancel_after = 3;
    request.archive_path = path;
    pd = xx_pd_init();
    CHECK(xfu_native_raw_read(&request, output, &pd) == 1);
    CHECK(strstr(state.log, "!  big.bin -- cancelled\n0 member(s)\n"));
    CHECK(!strstr(state.log, "FAILED") && !strstr(state.log, "could not"));
    CHECK(snprintf(path, sizeof(path), "%s/big.bin", output) > 0);
    CHECK(!xx_io_file_exists_a(path));
    return 0;
}

/* A gzip member of stored deflate blocks: any payload, no compressor. */
static bool write_stored_gz(const char *path, const unsigned char *data, size_t size) {
    static const unsigned char header[10] = {0x1f, 0x8b, 8, 0, 0, 0, 0, 0, 0, 3};
    unsigned char block[5], trailer[8];
    uint32_t crc = xx_crc32_calc(0, data, size);
    xx_io_device *file = xx_io_file_open(path, "wb");
    size_t at = 0;
    bool okay;
    if (!file) return false;
    okay = xx_io_write(file, header, sizeof(header)) == (ssize_t)sizeof(header);
    do {
        size_t part = size - at > 65535 ? 65535 : size - at;
        block[0] = at + part == size ? 1 : 0;
        block[1] = (unsigned char)part; block[2] = (unsigned char)(part >> 8);
        block[3] = (unsigned char)~part; block[4] = (unsigned char)(~part >> 8);
        okay = okay && xx_io_write(file, block, 5) == 5 &&
            (!part || xx_io_write(file, data + at, part) == (ssize_t)part);
        at += part;
    } while (okay && at < size);
    for (at = 0; at < 4; ++at) {
        trailer[at] = (unsigned char)(crc >> (8 * at));
        trailer[4 + at] = (unsigned char)((uint32_t)size >> (8 * at));
    }
    okay = okay && xx_io_write(file, trailer, 8) == 8;
    return xx_io_close(file) == 0 && okay;
}

static void fill_random(unsigned char *data, size_t size, uint32_t seed) {
    size_t i;
    for (i = 0; i < size; ++i) {
        seed = seed * 1664525U + 1013904223U;
        data[i] = (unsigned char)(seed >> 24);
    }
}

/* A newc cpio holding one member of `size` bytes from `data`. */
static size_t make_newc(unsigned char *out, const unsigned char *data, size_t size) {
    static const char name[] = "member.bin";
    size_t at = 0;
    int i;
    for (i = 0; i < 2; ++i) {
        const char *entry = i ? "TRAILER!!!" : name;
        size_t length = strlen(entry) + 1, body = i ? 0 : size;
        at += (size_t)sprintf((char *)out + at,
            "070701%08X%08X%08X%08X%08X%08X%08X%08X%08X%08X%08X%08X%08X",
            i ? 0U : 7U, i ? 0U : 0100644U, 0U, 0U, 1U, 0U, (unsigned)body, 0U, 0U, 0U, 0U,
            (unsigned)length, 0U);
        memcpy(out + at, entry, length);
        at += length;
        while (at % 4) out[at++] = 0;
        if (body) memcpy(out + at, data, body);
        at += body;
        while (at % 4) out[at++] = 0;
    }
    return at;
}

/* Nested layers are judged by their decoded start: a large plain stream is
 * never copied, a large archive that does not fit TEST's RAM is reported
 * as too large without failing the scope, and small layers are decided as
 * before. */
static int check_bounded_layers(const char *root) {
    const size_t big = 9U * 1024U * 1024U;
    unsigned char *data = (unsigned char *)malloc(big), *archive = (unsigned char *)malloc(big + 4096);
    unsigned char prefix[600];
    char path[2048];
    size_t size, i, archive_size;
    bool complete;
    xx_io_device *inner = NULL, *file;
    xx_file_type_t layer = XX_FILE_TYPE_BINARY, types[8];
    xx_pd_struct pd;
    capture state = {0};
    xfu_request request;
    CHECK(data && archive);
    CHECK(snprintf(path, sizeof(path), "%s/dense.gz", root) > 0);
    fill_random(data, big, 1);
    CHECK(write_stored_gz(path, data, big));
    {
        /* Inside a scope far smaller than the layer: nothing is copied. */
        xx_io_memory_only_scope scope = {0};
        CHECK(xx_io_memory_only_begin(&scope, 1024U * 1024U));
        CHECK(xx_io_memory_only_available() == 1024U * 1024U);
        pd = xx_pd_init();
        CHECK(xfu_native_open_inner(path, XX_FILE_TYPE_GZ, &pd, &inner) == XFU_NATIVE_INNER_NOT_ARCHIVE);
        CHECK(!inner && xx_io_memory_only_used() == 0);
        CHECK(xx_io_memory_only_end(&scope));
    }
    CHECK(xx_io_memory_only_available() == UINT64_MAX);
    /* Plain text is decoded whole (see check_text_layers) and is no archive,
     * also in a scope too small for it, which still ends cleanly. */
    for (i = 0; i < big; ++i) data[i] = (unsigned char)(i % 61 == 60 ? '\n' : 'a' + i % 26);
    CHECK(snprintf(path, sizeof(path), "%s/text.gz", root) > 0);
    CHECK(write_stored_gz(path, data, big));
    pd = xx_pd_init();
    CHECK(xfu_native_open_inner(path, XX_FILE_TYPE_GZ, &pd, &inner) == XFU_NATIVE_INNER_NOT_ARCHIVE && !inner);
    {
        xx_io_memory_only_scope scope = {0};
        CHECK(xx_io_memory_only_begin(&scope, 6U * 1024U * 1024U));
        pd = xx_pd_init();
        CHECK(xfu_native_open_inner_ex(path, XX_FILE_TYPE_GZ, &pd, &inner, &layer) == XFU_NATIVE_INNER_NOT_ARCHIVE);
        CHECK(!inner && layer == XX_FILE_TYPE_UNKNOWN);
        CHECK(xx_io_memory_only_end(&scope));
    }
    /* A large cpio (its signature in the prefix) is decoded whole... */
    fill_random(data, big, 2);
    archive_size = make_newc(archive, data, big);
    CHECK(snprintf(path, sizeof(path), "%s/large.cpio.gz", root) > 0);
    CHECK(write_stored_gz(path, archive, archive_size));
    pd = xx_pd_init();
    CHECK(xfu_native_open_inner(path, XX_FILE_TYPE_GZ, &pd, &inner) == XFU_NATIVE_INNER_ARCHIVE);
    CHECK(inner && xx_io_total_size(inner) == (int64_t)archive_size);
    CHECK(xx_io_close(inner) == 0);
    inner = NULL;
    {
        /* ...but in a scope too small for it, it is too large, and the
         * scope still ends cleanly. */
        xx_io_memory_only_scope scope = {0};
        CHECK(xx_io_memory_only_begin(&scope, 2U * 1024U * 1024U));
        pd = xx_pd_init();
        file = xx_io_file_open(path, "rb");
        CHECK(file);
        CHECK(xfu_native_open_inner_device_ex(file, XX_FILE_TYPE_GZ, &pd, &inner, &layer) ==
              XFU_NATIVE_INNER_TOO_LARGE);
        CHECK(!inner && layer == XX_FILE_TYPE_CPIO);
        CHECK(xx_io_close(file) == 0);
        CHECK(xx_io_memory_only_end(&scope));
    }
    /* Structured data that names no archive is still read whole, as every
     * layer was: here it is not one, also when it does not fit. */
    memset(data, 0, big);
    for (i = 0; i < big; i += 4096) memcpy(data + i, "BLOCK", 5);
    CHECK(snprintf(path, sizeof(path), "%s/blocks.gz", root) > 0);
    CHECK(write_stored_gz(path, data, big));
    pd = xx_pd_init();
    CHECK(xfu_native_open_inner(path, XX_FILE_TYPE_GZ, &pd, &inner) == XFU_NATIVE_INNER_NOT_ARCHIVE && !inner);
    {
        xx_io_memory_only_scope scope = {0};
        CHECK(xx_io_memory_only_begin(&scope, 1024U * 1024U));
        pd = xx_pd_init();
        CHECK(xfu_native_open_inner(path, XX_FILE_TYPE_GZ, &pd, &inner) == XFU_NATIVE_INNER_NOT_ARCHIVE && !inner);
        CHECK(xx_io_memory_only_end(&scope));
    }
    /* The prefix decoders: a bounded start, completeness, verification. */
    file = xx_io_file_open(path, "rb");
    CHECK(file);
    CHECK(xx_gz_decode_prefix(file, 0, prefix, sizeof(prefix), &size, &complete, NULL));
    CHECK(size == sizeof(prefix) && !complete && !memcmp(prefix, "BLOCK", 5));
    CHECK(xx_io_close(file) == 0);
    CHECK(snprintf(path, sizeof(path), "%s/small.gz", root) > 0);
    CHECK(write_stored_gz(path, (const unsigned char *)"tiny", 4));
    file = xx_io_file_open(path, "rb");
    CHECK(file);
    CHECK(xx_gz_decode_prefix(file, 0, prefix, sizeof(prefix), &size, &complete, NULL));
    CHECK(size == 4 && complete && !memcmp(prefix, "tiny", 4));
    CHECK(xx_io_close(file) == 0);
    {
        /* A complete member must carry its own checksum. */
        static const unsigned char bad[] = {0x1f, 0x8b, 8, 0, 0, 0, 0, 0, 0, 3, 1, 4, 0, 0xfb, 0xff,
                                            't', 'i', 'n', 'y', 0, 0, 0, 0, 4, 0, 0, 0};
        xx_io_device *memory = xx_io_mem_open_ro(bad, sizeof(bad));
        CHECK(memory);
        CHECK(!xx_gz_decode_prefix(memory, 0, prefix, sizeof(prefix), &size, &complete, NULL));
        CHECK(xx_io_close(memory) == 0);
    }
    {
        /* "BZh9" and an empty stream end: complete with nothing in it. */
        static const unsigned char empty_bz2[] = {'B', 'Z', 'h', '9', 0x17, 0x72, 0x45, 0x38, 0x50, 0x90, 0, 0, 0, 0};
        xx_io_device *memory = xx_io_mem_open_ro(empty_bz2, sizeof(empty_bz2));
        CHECK(memory);
        CHECK(xx_bz2_decode_prefix(memory, 0, prefix, sizeof(prefix), &size, &complete, NULL));
        CHECK(size == 0 && complete);
        CHECK(xx_io_close(memory) == 0);
    }
    /* The signature rules name a cpio from its first bytes alone. */
    {
        xx_io_device *memory = xx_io_mem_open_ro(archive, 4096);
        CHECK(memory);
        size = xx_format_fast_signature_types(memory, 0, types, 8);
        for (i = 0; i < size && types[i] != XX_FILE_TYPE_CPIO; ++i) {}
        CHECK(i < size);
        CHECK(xx_io_close(memory) == 0);
    }
    /* Through the core: a large plain .gz lists and tests as one member. */
    CHECK(snprintf(path, sizeof(path), "%s/dense.gz", root) > 0);
    request = request_for(path, XFU_COMMAND_TEST, &state);
    request.callbacks.log = log_cb;
    CHECK(xfu_run(&request) == 0);
    CHECK(state.tests == 1 && state.test_success && state.percent == 100);
    CHECK(!strstr(state.log, "could not be decoded") && !strstr(state.log, "in-memory"));
    free(data);
    free(archive);
    return 0;
}

/* A "begin-base64" envelope of `data` at `path`. */
static bool write_base64(const char *path, const char *name, const unsigned char *data, size_t size) {
    static const char symbols[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    FILE *file = fopen(path, "wb");
    size_t at, column = 0;
    bool okay;
    if (!file) return false;
    okay = fprintf(file, "begin-base64 644 %s\n", name) > 0;
    for (at = 0; okay && at < size; at += 3) {
        uint32_t group = (uint32_t)data[at] << 16;
        size_t left = size - at;
        char out[4];
        if (left > 1) group |= (uint32_t)data[at + 1] << 8;
        if (left > 2) group |= data[at + 2];
        out[0] = symbols[group >> 18];
        out[1] = symbols[(group >> 12) & 63];
        out[2] = left > 1 ? symbols[(group >> 6) & 63] : '=';
        out[3] = left > 2 ? symbols[group & 63] : '=';
        okay = fwrite(out, 1, 4, file) == 4;
        if (okay && (column += 4) == 76) { okay = fputc('\n', file) != EOF; column = 0; }
    }
    okay = okay && (!column || fputc('\n', file) != EOF) && fputs("====\n", file) != EOF;
    return fclose(file) == 0 && okay;
}

#ifndef _WIN32
/* A temporary folder that is out of space: at `bytes`, a temporary file
 * takes that many and then refuses writes (EFBIG), as a full disk does
 * (ENOSPC). */
static bool limit_file_size(rlim_t bytes, struct rlimit *saved) {
    struct rlimit limit;
    if (getrlimit(RLIMIT_FSIZE, saved) != 0) return false;
    limit = *saved;
    limit.rlim_cur = bytes;
    return signal(SIGXFSZ, SIG_IGN) != SIG_ERR && setrlimit(RLIMIT_FSIZE, &limit) == 0;
}

static xfu_native_inner_status inner_with_room(const char *path, xx_file_type_t filter,
                                               rlim_t bytes, xx_io_device **inner,
                                               xx_file_type_t *layer) {
    struct rlimit saved;
    xx_pd_struct pd = xx_pd_init();
    xx_io_device *file = xx_io_file_open(path, "rb");
    xfu_native_inner_status status = XFU_NATIVE_INNER_DECODE_ERROR;
    if (file && limit_file_size(bytes, &saved)) {
        status = xfu_native_open_inner_device_ex(file, filter, &pd, inner, layer);
        if (setrlimit(RLIMIT_FSIZE, &saved) != 0) status = XFU_NATIVE_INNER_DECODE_ERROR;
    }
    if (file) xx_io_close(file);
    return status;
}

static xfu_native_envelope_status envelope_with_room(const char *path, rlim_t bytes,
                                                     xx_io_device **decoded, char **name) {
    struct rlimit saved;
    xx_pd_struct pd = xx_pd_init();
    xx_io_device *file = xx_io_file_open(path, "rb");
    xfu_native_envelope_status status = XFU_NATIVE_ENVELOPE_DECODE_ERROR;
    if (file && limit_file_size(bytes, &saved)) {
        status = xfu_native_base64_open_device(file, &pd, decoded, name);
        if (setrlimit(RLIMIT_FSIZE, &saved) != 0) status = XFU_NATIVE_ENVELOPE_DECODE_ERROR;
    }
    if (file) xx_io_close(file);
    return status;
}

/* With no room for temporary files, a layer or payload of up to 4 MiB is
 * still read (it is kept in memory), and a longer one that holds an
 * archive is NO_ROOM, never a damaged stream or a cut copy. */
static int check_no_room(const char *root) {
    const size_t big = 5U * 1024U * 1024U;
    static const rlim_t rooms[] = {0, 100000};
    unsigned char *data = (unsigned char *)malloc(big), *archive = (unsigned char *)malloc(big + 4096);
    char path[2048], b64[2048], zst[2048];
    size_t size, i;
    xx_io_device *inner = NULL;
    xx_file_type_t layer = XX_FILE_TYPE_UNKNOWN;
    char *name = NULL;
    capture state = {0};
    xfu_request request;
    CHECK(data && archive);
    fill_random(data, big, 5);
    size = make_newc(archive, data, 1000);
    CHECK(snprintf(path, sizeof(path), "%s/room-small.cpio.gz", root) > 0);
    CHECK(write_stored_gz(path, archive, size));
    CHECK(snprintf(b64, sizeof(b64), "%s/room-small.b64", root) > 0);
    CHECK(write_base64(b64, "small.cpio", archive, size));
    for (i = 0; i < sizeof(rooms) / sizeof(rooms[0]); ++i) {
        CHECK(inner_with_room(path, XX_FILE_TYPE_GZ, rooms[i], &inner, &layer) == XFU_NATIVE_INNER_ARCHIVE);
        CHECK(inner && xx_io_total_size(inner) == (int64_t)size && xx_io_close(inner) == 0);
        inner = NULL;
        CHECK(envelope_with_room(b64, rooms[i], &inner, &name) == XFU_NATIVE_ENVELOPE_ARCHIVE);
        CHECK(inner && xx_io_total_size(inner) == (int64_t)size && xx_io_close(inner) == 0);
        free(name);
        inner = NULL;
        name = NULL;
    }
    size = make_newc(archive, data, big);
    CHECK(snprintf(path, sizeof(path), "%s/room-large.cpio.gz", root) > 0);
    CHECK(write_stored_gz(path, archive, size));
    CHECK(snprintf(b64, sizeof(b64), "%s/room-large.b64", root) > 0);
    CHECK(write_base64(b64, "large.cpio", archive, size));
    for (i = 0; i < sizeof(rooms) / sizeof(rooms[0]); ++i) {
        CHECK(inner_with_room(path, XX_FILE_TYPE_GZ, rooms[i], &inner, &layer) == XFU_NATIVE_INNER_NO_ROOM);
        CHECK(!inner && layer == XX_FILE_TYPE_CPIO);
        CHECK(envelope_with_room(b64, rooms[i], &inner, &name) == XFU_NATIVE_ENVELOPE_NO_ROOM);
        CHECK(!inner && !name);
    }
    /* Room for the 4 MiB held in memory, not for the rest: still NO_ROOM. */
    CHECK(envelope_with_room(b64, 4608U * 1024U, &inner, &name) == XFU_NATIVE_ENVELOPE_NO_ROOM);
    CHECK(!inner && !name);
    /* A payload that starts no archive is not: the ordinary reader takes it
     * as one file, without a note. */
    CHECK(snprintf(b64, sizeof(b64), "%s/room-plain.b64", root) > 0);
    CHECK(write_base64(b64, "photo.jpg", data, big));
    for (i = 0; i < sizeof(rooms) / sizeof(rooms[0]); ++i) {
        CHECK(envelope_with_room(b64, rooms[i], &inner, &name) == XFU_NATIVE_ENVELOPE_NOT_FOUND);
        CHECK(!inner && !name);
    }
    CHECK(inner_with_room(path, XX_FILE_TYPE_GZ, RLIM_INFINITY, &inner, &layer) == XFU_NATIVE_INNER_ARCHIVE);
    CHECK(inner && xx_io_total_size(inner) == (int64_t)size && xx_io_close(inner) == 0);
    inner = NULL;
    /* zstd decodes once (as it is written); the same decisions. */
    if (xx_zstd_is_available()) {
        size_t bound = xx_zstd_compress_bound(size), packed = 0;
        unsigned char *frame = (unsigned char *)malloc(bound);
        CHECK(frame && xx_zstd_compress_memory(archive, size, frame, bound, &packed, XX_ZSTD_LEVEL_FASTEST));
        CHECK(snprintf(zst, sizeof(zst), "%s/room-large.cpio.zst", root) > 0);
        CHECK(write_bytes(zst, frame, packed));
        CHECK(inner_with_room(zst, XX_FILE_TYPE_ZSTD, RLIM_INFINITY, &inner, &layer) == XFU_NATIVE_INNER_ARCHIVE);
        CHECK(inner && xx_io_total_size(inner) == (int64_t)size && xx_io_seek64(inner, 0, SEEK_SET) == 0);
        {
            /* The copy holds the layer, start and rest. */
            unsigned char *copy = (unsigned char *)malloc(size);
            CHECK(copy && xx_io_read(inner, copy, size) == (ssize_t)size && !memcmp(copy, archive, size));
            free(copy);
        }
        CHECK(xx_io_close(inner) == 0);
        inner = NULL;
        CHECK(inner_with_room(zst, XX_FILE_TYPE_ZSTD, 0, &inner, &layer) == XFU_NATIVE_INNER_NO_ROOM);
        CHECK(!inner && layer == XX_FILE_TYPE_CPIO);
        {
            xx_io_memory_only_scope scope = {0};
            xx_pd_struct pd = xx_pd_init();
            CHECK(xx_io_memory_only_begin(&scope, 2U * 1024U * 1024U));
            CHECK(xfu_native_open_inner_ex(zst, XX_FILE_TYPE_ZSTD, &pd, &inner, &layer) == XFU_NATIVE_INNER_TOO_LARGE);
            CHECK(!inner && layer == XX_FILE_TYPE_CPIO);
            CHECK(xx_io_memory_only_end(&scope));
        }
        /* Evenly spread data is no archive and gets no copy. */
        CHECK(xx_zstd_compress_memory(data, big, frame, bound, &packed, XX_ZSTD_LEVEL_FASTEST));
        CHECK(write_bytes(zst, frame, packed));
        CHECK(inner_with_room(zst, XX_FILE_TYPE_ZSTD, 0, &inner, &layer) == XFU_NATIVE_INNER_NOT_ARCHIVE);
        CHECK(!inner);
        free(frame);
    }
    /* Through the core: the cause is said, and the stream is read as one
     * file. */
    {
        struct rlimit saved;
        int result;
        request = request_for(path, XFU_COMMAND_LIST, &state);
        request.callbacks.log = log_cb;
        CHECK(limit_file_size(0, &saved));
        result = xfu_run(&request);
        CHECK(setrlimit(RLIMIT_FSIZE, &saved) == 0);
        CHECK(result == 1 && state.entries == 1);
        CHECK(strstr(state.log, "no space for a temporary copy of the CPIO inside"));
        CHECK(!strstr(state.log, "could not be decoded") && !strstr(state.log, "damaged"));
    }
    free(data);
    free(archive);
    return 0;
}
#endif

/* Only a well-formed "begin[-base64] <octal mode> <name>" line makes an
 * envelope; prose that starts like one is left to detection, while a
 * well-formed header with a damaged body is still an error. */
static int check_envelope_headers(const char *root) {
    static const char *const prose[] = {
        "begin the meeting at 10\nthen lunch\n",
        "begin-base64 is a header\nhello\n",
        "begin-base64 644\nno name\n",
        "begin 0x644 name\nnot octal\n",
        "begin-base64 644 a:b\naGVsbG8K\n====\n",
    };
    char path[2048];
    size_t i;
    xx_io_device *inner = NULL;
    char *name = NULL;
    xx_pd_struct pd;
    capture state = {0};
    xfu_request request;
    CHECK(snprintf(path, sizeof(path), "%s/prose.txt", root) > 0);
    for (i = 0; i < sizeof(prose) / sizeof(prose[0]); ++i) {
        CHECK(write_file(path, prose[i]));
        pd = xx_pd_init();
        CHECK(xfu_native_base64_open(path, &pd, &inner, &name) == XFU_NATIVE_ENVELOPE_NOT_FOUND);
        CHECK(!inner && !name);
        pd = xx_pd_init();
        CHECK(xfu_native_uue_open(path, &pd, &inner, &name) == XFU_NATIVE_ENVELOPE_NOT_FOUND);
        CHECK(!inner && !name);
    }
    {
        /* The Base64 reader's header rules: up to XX_BASE64_HEADER_MAX
         * (4096) bytes with the line break, and six octal digits of mode as
         * in 100644. The probe and the reader take the same lines: as a
         * later envelope, the longest one is a member that decodes, and one
         * byte more makes a member that fails, with the next one still read. */
        static const char first[] = "begin-base64 644 a.txt\naGVsbG8K\n====\n";
        static const char tail[] = "begin-base64 644 c.txt\nY2MK\n====\n";
        char header[XX_BASE64_HEADER_MAX + 64U], *text;
        size_t line, length;
        CHECK(XX_BASE64_HEADER_MAX == 4096U);
        text = (char *)malloc(sizeof(first) + sizeof(header) + sizeof(tail));
        CHECK(text);
        for (line = XX_BASE64_HEADER_MAX - 1U; line <= XX_BASE64_HEADER_MAX; ++line) {
            memset(header, 'n', line);
            memcpy(header, "begin-base64 100644 ", 20);
            memcpy(header + line - 2U, ".b\naGkK\n====\n", 14);
            CHECK(write_file(path, header));
            pd = xx_pd_init();
            if (line < XX_BASE64_HEADER_MAX) {
                CHECK(xfu_native_base64_open(path, &pd, &inner, &name) == XFU_NATIVE_ENVELOPE_RAW);
                CHECK(inner && name && strlen(name) == line - 20U);
                CHECK(xx_io_close(inner) == 0);
                free(name);
                inner = NULL;
                name = NULL;
            } else {
                CHECK(xfu_native_base64_open(path, &pd, &inner, &name) == XFU_NATIVE_ENVELOPE_NOT_FOUND);
                CHECK(!inner && !name);
            }
            length = strlen(header);
            memcpy(text, first, sizeof(first) - 1U);
            memcpy(text + sizeof(first) - 1U, header, length);
            memcpy(text + sizeof(first) - 1U + length, tail, sizeof(tail));
            CHECK(write_file(path, text));
            memset(&state, 0, sizeof(state));
            request = request_for(path, XFU_COMMAND_TEST, &state);
            request.callbacks.log = log_cb;
            request.callbacks.test_result = NULL;
            CHECK(xfu_run(&request) == (line < XX_BASE64_HEADER_MAX ? 0 : 1));
            CHECK(strstr(state.log, "  a.txt -- OK\n") && strstr(state.log, "  c.txt -- OK\n"));
            if (line < XX_BASE64_HEADER_MAX)
                CHECK(strstr(state.log, "  payload -- OK\n") && strstr(state.log, "\n3 member(s)\n"));
            else
                CHECK(strstr(state.log, "!  payload -- FAILED\n") && strstr(state.log, "!3 member(s), 1 failed\n"));
        }
        free(text);
    }
    {
        /* A header with a long path, as tar or a long checkout writes it: the
         * member is its last component. */
        char text[1400];
        size_t at = (size_t)sprintf(text, "begin-base64 644 ");
        int dir;
        for (dir = 0; dir < 12; ++dir) {
            memset(text + at, 'a' + dir, 100);
            at += 100;
            text[at++] = '/';
        }
        strcpy(text + at, "file.txt\naGVsbG8K\n====\n");
        CHECK(strchr(text, '\n') - text > 1200);
        CHECK(write_file(path, text));
        pd = xx_pd_init();
        CHECK(xfu_native_base64_open(path, &pd, &inner, &name) == XFU_NATIVE_ENVELOPE_RAW);
        CHECK(inner && name && !strcmp(name, "file.txt"));
        CHECK(device_matches(inner, (const unsigned char *)"hello\n", 6));
        CHECK(xx_io_close(inner) == 0);
        free(name);
        inner = NULL;
        name = NULL;
        memset(&state, 0, sizeof(state));
        request = request_for(path, XFU_COMMAND_LIST, &state);
        request.callbacks.log = log_cb;
        CHECK(xfu_run(&request) == 0);
        CHECK(strstr(state.log, ": Base64\n") && strstr(state.log, "  file.txt\n1 member(s)\n"));
    }
    {
        /* Blanks may end the "====" line; other text there breaks it. */
        static const char *const ends[] = {"==== \n", "====\t \r\n", "====  "};
        for (i = 0; i < sizeof(ends) / sizeof(ends[0]); ++i) {
            char text[128];
            CHECK(snprintf(text, sizeof(text), "begin-base64 644 sp.txt\naGkK\n%s", ends[i]) > 0);
            CHECK(write_file(path, text));
            pd = xx_pd_init();
            CHECK(xfu_native_base64_open(path, &pd, &inner, &name) == XFU_NATIVE_ENVELOPE_RAW);
            CHECK(inner && name && !strcmp(name, "sp.txt"));
            CHECK(device_matches(inner, (const unsigned char *)"hi\n", 3));
            CHECK(xx_io_close(inner) == 0);
            free(name);
            inner = NULL;
            name = NULL;
        }
        CHECK(write_file(path, "begin-base64 644 sp.txt\naGkK\n==== x\n"));
        pd = xx_pd_init();
        CHECK(xfu_native_base64_open(path, &pd, &inner, &name) == XFU_NATIVE_ENVELOPE_DECODE_ERROR);
        CHECK(!inner && !name);
    }
    CHECK(write_file(path, prose[0]));
    memset(&state, 0, sizeof(state));
    request = request_for(path, XFU_COMMAND_LIST, &state);
    request.callbacks.log = log_cb;
    CHECK(xfu_run(&request) == 2);
    CHECK(strstr(state.log, "cannot be opened as an archive") && !strstr(state.log, "envelope"));
    CHECK(write_file(path, "begin-base64 644 notes.txt\n!!!! not base64 !!!!\n====\n"));
    pd = xx_pd_init();
    CHECK(xfu_native_base64_open(path, &pd, &inner, &name) == XFU_NATIVE_ENVELOPE_DECODE_ERROR);
    CHECK(write_file(path, "begin 644 notes.txt\nthen this is not uuencoded at all\n"));
    pd = xx_pd_init();
    CHECK(xfu_native_uue_open(path, &pd, &inner, &name) == XFU_NATIVE_ENVELOPE_DECODE_ERROR);
    CHECK(!inner && !name);
    {
        /* A payload larger than TEST's RAM is left to the ordinary reader,
         * and the scope does not fail. Only one that starts an archive (here
         * a gzip stream) is TOO_LARGE; other data is not an envelope archive. */
        static const char head[] = "begin-base64 644 big.bin\n";
        static const char *const starts[] = {"QUJD", "H4sIAAAAAAAAAwAA"};
        const size_t groups = 400000;
        size_t kind;
        for (kind = 0; kind < 2U; ++kind) {
            char *text = (char *)malloc(sizeof(head) + 16U + groups * 4U + 8U);
            xx_io_memory_only_scope scope = {0};
            size_t at = sizeof(head) - 1U;
            CHECK(text);
            memcpy(text, head, at);
            memcpy(text + at, starts[kind], strlen(starts[kind]));
            at += strlen(starts[kind]);
            for (i = 0; i < groups; ++i) { memcpy(text + at, kind ? "AAAA" : "QUJD", 4); at += 4; }
            memcpy(text + at, "\n====\n", 7);
            CHECK(write_file(path, text));
            free(text);
            CHECK(xx_io_memory_only_begin(&scope, 512U * 1024U));
            pd = xx_pd_init();
            CHECK(xfu_native_base64_open(path, &pd, &inner, &name) ==
                  (kind ? XFU_NATIVE_ENVELOPE_TOO_LARGE : XFU_NATIVE_ENVELOPE_NOT_FOUND));
            CHECK(!inner && !name);
            CHECK(xx_io_memory_only_end(&scope));
        }
    }
    return 0;
}

/* Raw members follow the walk's log lines on every route, report the
 * envelope a payload came from wherever it sits, and stage under a short
 * name, so a member name of up to NAME_MAX bytes extracts. */
static int check_raw_routes(const char *root) {
    static const char envelope[] = "begin-base64 644 payload.txt\ncGxhaW4gdGV4dAo=\n====\n";
    char path[2048], output[2048], name[300], *decoded_name = NULL, expected[2600];
    capture state = {0};
    xfu_request request;
    xx_io_device *inner = NULL;
    xx_pd_struct pd;
    memset(name, 'n', 251);
    memcpy(name + 251, ".txt", 5);
    CHECK(snprintf(path, sizeof(path), "%s/%s", root, name) > 0);
    CHECK(snprintf(output, sizeof(output), "%s/long-out", root) > 0);
    CHECK(write_file(path, "raw content\n"));
    request = request_for(path, XFU_COMMAND_EXTRACT, &state);
    request.callbacks.log = log_cb;
    pd = xx_pd_init();
    CHECK(xfu_native_raw_read(&request, output, &pd) == 0);
    CHECK(snprintf(expected, sizeof(expected), "%s: Binary\n", path) > 0 && strstr(state.log, expected));
    CHECK(snprintf(path, sizeof(path), "%s/%s", output, name) > 0);
    CHECK(file_matches(path, "raw content\n"));
    /* The envelope type of a payload travels with its device. */
    CHECK(snprintf(path, sizeof(path), "%s/payload.b64", root) > 0);
    CHECK(write_file(path, envelope));
    pd = xx_pd_init();
    CHECK(xfu_native_base64_open(path, &pd, &inner, &decoded_name) == XFU_NATIVE_ENVELOPE_RAW);
    CHECK(snprintf(path, sizeof(path), "%s/payload.b64.gz", root) > 0);
    CHECK(write_stored_gz(path, (const unsigned char *)envelope, sizeof(envelope) - 1U));
    memset(&state, 0, sizeof(state));
    request = request_for(path, XFU_COMMAND_TEST, &state);
    request.callbacks.log = log_cb;
    request.callbacks.test_result = NULL;
    pd = xx_pd_init();
    CHECK(xfu_native_raw_device_read(&request, NULL, &pd, inner, decoded_name) == 0);
    CHECK(snprintf(expected, sizeof(expected), "%s: Base64\n  payload.txt -- OK\n1 member(s)\n", path) > 0);
    CHECK(strstr(state.log, expected));
    CHECK(xx_io_close(inner) == 0);
    free(decoded_name);
    memset(&state, 0, sizeof(state));
    request = request_for(path, XFU_COMMAND_LIST, &state);
    request.callbacks.log = log_cb;
    CHECK(xfu_run(&request) == 0);
    CHECK(snprintf(expected, sizeof(expected), "%s: Base64\n", path) > 0 && strstr(state.log, expected));
    CHECK(strstr(state.log, "  payload.txt\n1 member(s)\n"));
    return 0;
}

/* FASTA records of 70-base lines, as many as make `size` bytes or more. */
static size_t make_fasta(unsigned char *out, size_t size) {
    size_t at = 0, record = 0;
    uint32_t seed = 7;
    while (at < size) {
        size_t line, base;
        at += (size_t)sprintf((char *)out + at, ">seq%u sample\n", (unsigned)record++);
        for (line = 0; line < 4000; ++line) {
            for (base = 0; base < 70; ++base) {
                seed = seed * 1664525U + 1013904223U;
                out[at++] = (unsigned char)"ACGT"[seed >> 30];
            }
            out[at++] = '\n';
        }
    }
    return at;
}

/* A Wavefront OBJ of `vertices` vertex lines and then the faces between
 * them: no prefix of its vertices alone is an OBJ the reader accepts. */
static size_t make_obj(unsigned char *out, unsigned vertices) {
    size_t at = (size_t)sprintf((char *)out, "# mesh\no mesh\n");
    unsigned i;
    for (i = 0; i < vertices; ++i)
        at += (size_t)sprintf((char *)out + at, "v %u.%06u %u.%06u 0.5\n", i % 7, i % 999983, i % 5, i % 7919);
    for (i = 1; i + 2 <= vertices; ++i)
        at += (size_t)sprintf((char *)out + at, "f %u %u %u\n", i, i + 1, i + 2);
    return at;
}

/* A .Z stream of 9-bit literal codes with a CLEAR before the table fills,
 * the way XFileUnpacker's encoder wrote one before it compressed: about 1/8
 * larger than its data, whatever that is. */
static bool write_literal_compress(const char *path, const unsigned char *data, size_t size) {
    static const unsigned char header[3] = {0x1f, 0x9d, 0x90};
    xx_io_device *file = xx_io_file_open(path, "wb");
    uint64_t bits = 0, position = 0, group = 0;
    unsigned available = 0, literals = 0;
    size_t i;
    bool okay;
    if (!file) return false;
    okay = xx_io_write(file, header, 3) == 3;
    for (i = 0; okay && i < size; ++i) {
        unsigned codes = 0, padding = 0, code[2], k;
        if (literals == 254U) {
            /* CLEAR, then zero bits to the end of its group of 8 codes. */
            padding = (unsigned)((72U - ((position + 9U - group) % 72U)) % 72U);
            code[codes++] = 256U;
            literals = 0;
        }
        code[codes++] = data[i];
        ++literals;
        for (k = 0; okay && k < codes; ++k) {
            bits |= (uint64_t)code[k] << available;
            available += 9U;
            position += 9U;
            if (code[k] == 256U && k + 1U < codes) {
                available += padding;
                position += padding;
                group = position;
            }
            while (okay && available >= 8U) {
                unsigned char byte = (unsigned char)bits;
                okay = xx_io_write(file, &byte, 1) == 1;
                bits >>= 8;
                available -= 8U;
            }
        }
    }
    if (okay && available) {
        unsigned char byte = (unsigned char)bits;
        okay = xx_io_write(file, &byte, 1) == 1;
    }
    return xx_io_close(file) == 0 && okay;
}

/* Text record formats that xxfclib reads as archives are found in a large
 * layer as in a small one: their readers check every line, so text is
 * decoded whole, and the prefix cut at its last line break names the
 * layer when it does not fit. A .Z layer that fits is read whatever the
 * size of its stream, which LZW lets grow past its data. */
static int check_text_layers(const char *root) {
    const size_t big = 6U * 1024U * 1024U;
    unsigned char *data = (unsigned char *)malloc(big + 8U * 1024U * 1024U), *archive;
    char path[2048];
    size_t size;
    xx_io_device *inner = NULL;
    xx_file_type_t layer = XX_FILE_TYPE_BINARY;
    xx_pd_struct pd;
    capture state = {0};
    xfu_request request;
    CHECK(data);
    size = make_fasta(data, 5U * 1024U * 1024U);
    CHECK(size > 5U * 1024U * 1024U);
    CHECK(snprintf(path, sizeof(path), "%s/seq.fa.gz", root) > 0);
    CHECK(write_stored_gz(path, data, size));
    pd = xx_pd_init();
    CHECK(xfu_native_open_inner(path, XX_FILE_TYPE_GZ, &pd, &inner) == XFU_NATIVE_INNER_ARCHIVE);
    CHECK(inner && xx_io_total_size(inner) == (int64_t)size);
    CHECK(xx_format_get_file_type_device(inner) == XX_FILE_TYPE_GENOMICS_FASTA);
    CHECK(xx_io_close(inner) == 0);
    inner = NULL;
    {
        xx_io_memory_only_scope scope = {0};
        CHECK(xx_io_memory_only_begin(&scope, 5U * 1024U * 1024U));
        pd = xx_pd_init();
        CHECK(xfu_native_open_inner_ex(path, XX_FILE_TYPE_GZ, &pd, &inner, &layer) == XFU_NATIVE_INNER_TOO_LARGE);
        CHECK(!inner && layer == XX_FILE_TYPE_GENOMICS_FASTA);
        CHECK(xx_io_memory_only_end(&scope));
    }
    request = request_for(path, XFU_COMMAND_LIST, &state);
    request.callbacks.log = log_cb;
    CHECK(xfu_run(&request) == 0);
    CHECK(strstr(state.log, ": genomics fasta\n") && state.entries > 1);
    size = make_obj(data, 200000U);
    CHECK(size > 5U * 1024U * 1024U);
    CHECK(snprintf(path, sizeof(path), "%s/mesh.obj.gz", root) > 0);
    CHECK(write_stored_gz(path, data, size));
    pd = xx_pd_init();
    CHECK(xfu_native_open_inner(path, XX_FILE_TYPE_GZ, &pd, &inner) == XFU_NATIVE_INNER_ARCHIVE);
    CHECK(inner && xx_format_get_file_type_device(inner) == XX_FILE_TYPE_WAVEFRONT_OBJ);
    CHECK(xx_io_close(inner) == 0);
    inner = NULL;
    /* 6 MB in a 6 MiB scope: its .Z stream is 6.8 MB, more than the 1/16
     * that the other filters may grow by. */
    archive = data + 7U * 1024U * 1024U;
    fill_random(archive, 6000000U, 3);
    size = make_newc(data, archive, 6000000U);
    CHECK(snprintf(path, sizeof(path), "%s/large.cpio.Z", root) > 0);
    CHECK(write_literal_compress(path, data, size));
    {
        xx_io_device *file = xx_io_file_open(path, "rb");
        xx_io_memory_only_scope scope = {0};
        CHECK(file && xx_io_total_size(file) > (int64_t)(6U * 1024U * 1024U / 16U * 17U));
        CHECK(xx_io_memory_only_begin(&scope, 6U * 1024U * 1024U));
        pd = xx_pd_init();
        CHECK(xfu_native_open_inner_device(file, XX_FILE_TYPE_UNIX_COMPRESS, &pd, &inner) == XFU_NATIVE_INNER_ARCHIVE);
        CHECK(inner && xx_io_total_size(inner) == (int64_t)size);
        CHECK(xx_io_close(inner) == 0);
        inner = NULL;
        CHECK(xx_io_memory_only_end(&scope));
        CHECK(xx_io_close(file) == 0);
    }
    free(data);
    return 0;
}

/* A file whose name cannot be a member name is said so on the raw route
 * instead of failing without a word. ':' is such a character on Windows
 * only (POSIX file names here). */
static int check_raw_name_messages(const char *root) {
    static const char *const names[] = {"x\033[2Jy.dat"};
    static const char *const reasons[] = {"its name holds a control character"};
    char path[2048], expected[2600];
    size_t i;
#ifndef _WIN32
    {
        capture state = {0};
        xfu_request request;
        xx_pd_struct pd = xx_pd_init();
        CHECK(snprintf(path, sizeof(path), "%s/a:b.dat", root) > 0);
        CHECK(write_file(path, "raw\n"));
        request = request_for(path, XFU_COMMAND_LIST, &state);
        request.callbacks.log = log_cb;
        CHECK(xfu_native_raw_read(&request, NULL, &pd) == 0);
        CHECK(state.entries == 1);
        CHECK(strstr(state.log, "a:b.dat\n") != NULL);
    }
#endif
    for (i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
        capture state = {0};
        xfu_request request;
        xx_pd_struct pd = xx_pd_init();
        CHECK(snprintf(path, sizeof(path), "%s/%s", root, names[i]) > 0);
        request = request_for(path, XFU_COMMAND_LIST, &state);
        request.callbacks.log = log_cb;
        CHECK(xfu_native_raw_read(&request, NULL, &pd) == 2);
        CHECK(snprintf(expected, sizeof(expected), "!%s: cannot be read as one file: %s\n", path, reasons[i]) > 0);
        CHECK(!strcmp(state.log, expected));
        CHECK(state.entries == 0);
    }
    return 0;
}

/* Each growth of a temporary stream that a memory-only scope refuses is
 * counted, so that Test can tell which member hit its limit after the
 * scope's first failure is set (core failure_reason). */
static int check_memory_refusals(void) {
    static const unsigned char block[4096] = {0};
    xx_io_memory_only_scope scope = {0};
    xx_io_device *temp;
    CHECK(xx_io_memory_only_refusals() == 0);
    CHECK(xx_io_memory_only_begin(&scope, 1024U));
    CHECK(xx_io_memory_only_refusals() == 0);
    temp = xx_io_temp_open();
    CHECK(temp && xx_io_write(temp, block, 512U) == 512);
    CHECK(xx_io_memory_only_refusals() == 0);
    CHECK(xx_io_write(temp, block, sizeof(block)) < 0);
    CHECK(xx_io_memory_only_refusals() == 1);
    CHECK(xx_io_write(temp, block, sizeof(block)) < 0);
    CHECK(xx_io_memory_only_refusals() == 2);
    CHECK(xx_io_close(temp) == 0);
    CHECK(!xx_io_memory_only_end(&scope));
    CHECK(xx_io_memory_only_error(&scope) == XX_IO_MEMORY_ONLY_LIMIT);
    CHECK(xx_io_memory_only_refusals() == 0);
    return 0;
}

int main(int argc, char **argv) {
    static const char content[] = "a raw input with no archive signature\n";
    static const unsigned char cpio_gz[] = {
        0x1f,0x8b,0x08,0x00,0x00,0x00,0x00,0x00,0x02,0xff,0x33,0x30,0x37,0x30,0x37,0x30,
        0x34,0x80,0x00,0x30,0x6d,0x61,0xe8,0x68,0x62,0x80,0x1d,0x18,0xa2,0x71,0x5d,0x0c,
        0x88,0x03,0x8e,0x30,0x46,0x46,0x6a,0x4e,0x4e,0xbe,0x5e,0x49,0x45,0x09,0x03,0x98,
        0xa5,0x90,0x97,0x58,0x92,0x59,0x96,0xaa,0x90,0x5f,0x5a,0x92,0x5a,0xa4,0x90,0x9c,
        0x9f,0x57,0x92,0x98,0x99,0x97,0x5a,0xc4,0xc5,0xc0,0xc0,0x60,0x80,0xec,0x2e,0x03,
        0xd2,0xdc,0x45,0x34,0x70,0x82,0x31,0x42,0x82,0x1c,0x3d,0x7d,0x5c,0x83,0x14,0x15,
        0x15,0x81,0x56,0x33,0x00,0x00,0x3c,0xf9,0x98,0x56,0x14,0x01,0x00,0x00
    };
    static const unsigned char text_gz[] = {
        0x1f,0x8b,0x08,0x00,0x00,0x00,0x00,0x00,0x02,0xff,0x2b,0xc8,0x49,0xcc,0xcc,0x53,
        0x28,0x49,0xad,0x28,0xe1,0x02,0x00,0x22,0x36,0x29,0xf7,0x0b,0x00,0x00,0x00
    };
    static const char cpio_b64[] =
        "begin-base64 644 payload\n"
        "H4sIAAAAAAAC/zMwNzA3MDSAADBtYehoYoAdGKJxXQyIA44wRkZqTk6+XklFCQOYpZCXWJJZlqqQ\n"
        "X1qSWqSQnJ9XkpiZl1rExcDAYIDsLgPS3EU0cIIxQoIcPX1cgxQVFYFWMwAAPPmYVhQBAAA=\n"
        "====\n";
    static const char cpio_uue[] =
        "begin 644 payload\n"
        "M'XL(       \"_S,P-S W,#2  #!M8>AH8H =&*)Q70R( XXP1D9J3DZ^7DE%\n"
        "M\"0.8I9\"76))9EJJ07UJ26J20G)]7DIB9EUK$Q<# 8(#L+@/2W$4T<((Q0H(<\n"
        "4/7U<@Q05%8%6,P  //F85A0!    \n"
        "`\nend\n";
    const char *name = NULL;
    bool raw = false;
    char source[2048], output[2048], extracted[2048], wrapped[2048];
    capture listed = {0}, tested = {0}, unpacked = {0}, rejected = {0};
    xfu_request request;
    xx_pd_struct pd;
    xx_io_device *inner = NULL, *borrowed = NULL;
    char *decoded_name = NULL;
    xx_io_memory_only_scope scope = {0};
    unsigned char broken[sizeof(cpio_gz)];
    const size_t first[] = {0}, absent[] = {1};
    CHECK(argc == 2);
    CHECK(xfu_native_reader_resolve("native", &name, &raw) && !name && !raw);
    CHECK(xfu_native_reader_resolve("native:pax", &name, &raw) && !strcmp(name, "tar") && !raw);
    CHECK(xfu_native_reader_resolve("native:cpio_crc", &name, &raw) && !strcmp(name, "cpio") && !raw);
    CHECK(xfu_native_reader_resolve("native:compress", &name, &raw) && !strcmp(name, "unixcompress") && !raw);
    CHECK(xfu_native_reader_resolve("native:raw", &name, &raw) && !name && raw);
    CHECK(xfu_native_reader_resolve("native:empty", &name, &raw) &&
          !strcmp(name, "empty") && !raw);
    CHECK(!xfu_native_reader_resolve("native:unknown", &name, &raw));
    CHECK(!xfu_native_reader_resolve("native:b64encode", &name, &raw));
    CHECK(xfu_native_member_name_safe("folder/file.txt", false));
    CHECK(xfu_native_member_name_safe("./", true));
    CHECK(!xfu_native_member_name_safe("/tmp/escape", false));
#ifdef _WIN32
    /* A drive, or a file's stream: refused there. */
    CHECK(!xfu_native_member_name_safe("C:\\escape", false));
    CHECK(!xfu_native_member_name_safe("a:b.txt", false));
#else
    /* Elsewhere ':' is an ordinary character of a name. */
    CHECK(xfu_native_member_name_safe("C:\\escape", false));
    CHECK(xfu_native_member_name_safe("folder/9:00-notes.txt", false));
#endif
    CHECK(!xfu_native_member_name_safe("folder/../escape", false));
    CHECK(!xfu_native_member_name_safe("folder\\..\\escape", false));
    CHECK(xx_io_create_dirs_a(argv[1], true));
    CHECK(snprintf(source, sizeof(source), "%s/input.txt", argv[1]) > 0);
    CHECK(snprintf(output, sizeof(output), "%s/output", argv[1]) > 0);
    CHECK(snprintf(extracted, sizeof(extracted), "%s/input.txt", output) > 0);
    CHECK(write_file(source, content));
    CHECK(xfu_native_raw_filter_type(source) == XX_FILE_TYPE_UNKNOWN);

    pd = xx_pd_init();
    request = request_for(source, XFU_COMMAND_LIST, &listed);
    CHECK(xfu_native_raw_read(&request, NULL, &pd) == 0);
    CHECK(listed.entries == 1 && listed.complete == 1);
    CHECK(listed.type == XX_FILE_TYPE_BINARY);
    CHECK(!strcmp(listed.name, "input.txt"));

    pd = xx_pd_init();
    request = request_for(source, XFU_COMMAND_TEST, &tested);
    CHECK(xfu_native_raw_read(&request, NULL, &pd) == 0);
    CHECK(tested.entries == 1 && tested.tests == 1 && tested.test_success);
    CHECK(tested.percent == 100 && tested.complete == 1);

    pd = xx_pd_init();
    request = request_for(source, XFU_COMMAND_EXTRACT, &unpacked);
    request.extract_selected = true;
    request.selected_records = first;
    request.selected_record_count = 1;
    CHECK(xfu_native_raw_read(&request, output, &pd) == 0);
    CHECK(unpacked.entries == 1 && unpacked.complete == 1);
    CHECK(file_matches(extracted, content));

    pd = xx_pd_init();
    request = request_for(source, XFU_COMMAND_EXTRACT, &rejected);
    request.extract_selected = true;
    request.selected_records = absent;
    request.selected_record_count = 1;
    CHECK(xfu_native_raw_read(&request, output, &pd) == 1);
    CHECK(rejected.entries == 0);
    CHECK(file_matches(extracted, content));

    rejected.cancel = true;
    pd = xx_pd_init();
    request = request_for(source, XFU_COMMAND_EXTRACT, &rejected);
    CHECK(xfu_native_raw_read(&request, output, &pd) == 1);
    CHECK(file_matches(extracted, content));
    CHECK(check_raw_log_lines(argv[1]) == 0);
    CHECK(check_bounded_layers(argv[1]) == 0);
    CHECK(check_envelope_headers(argv[1]) == 0);
    CHECK(check_raw_routes(argv[1]) == 0);
    CHECK(check_text_layers(argv[1]) == 0);
    CHECK(check_raw_name_messages(argv[1]) == 0);
    CHECK(check_memory_refusals() == 0);
#ifndef _WIN32
    CHECK(check_no_room(argv[1]) == 0);
#endif

    CHECK(snprintf(wrapped, sizeof(wrapped), "%s/inner.cpio.gz", argv[1]) > 0);
    CHECK(write_bytes(wrapped, cpio_gz, sizeof(cpio_gz)));
    CHECK(xx_io_memory_only_begin(&scope, 1024U * 1024U));
    pd = xx_pd_init();
    CHECK(xfu_native_open_inner(wrapped, XX_FILE_TYPE_GZ, &pd, &inner) == XFU_NATIVE_INNER_ARCHIVE);
    CHECK(inner && xx_io_total_size(inner) == 276);
    CHECK(xx_io_close(inner) == 0);
    inner = NULL;
    CHECK(xx_io_memory_only_end(&scope));
    borrowed = xx_io_file_open(wrapped, "rb");
    CHECK(borrowed);
    CHECK(xfu_native_raw_filter_type_device(borrowed) == XX_FILE_TYPE_GZ);
    pd = xx_pd_init();
    CHECK(xfu_native_open_inner_device(borrowed, XX_FILE_TYPE_GZ, &pd, &inner) ==
          XFU_NATIVE_INNER_ARCHIVE);
    CHECK(inner && xx_io_total_size(inner) == 276);
    CHECK(xx_io_close(inner) == 0);
    CHECK(xx_io_close(borrowed) == 0);
    inner = NULL; borrowed = NULL;
    CHECK(snprintf(wrapped, sizeof(wrapped), "%s/text.gz", argv[1]) > 0);
    CHECK(write_bytes(wrapped, text_gz, sizeof(text_gz)));
    pd = xx_pd_init();
    CHECK(xfu_native_open_inner(wrapped, XX_FILE_TYPE_GZ, &pd, &inner) == XFU_NATIVE_INNER_NOT_ARCHIVE);
    CHECK(inner == NULL);
    CHECK(snprintf(wrapped, sizeof(wrapped), "%s/bad.cpio.gz", argv[1]) > 0);
    memcpy(broken, cpio_gz, sizeof(broken));
    broken[sizeof(broken) - 8] ^= 0x80;
    CHECK(write_bytes(wrapped, broken, sizeof(broken)));
    pd = xx_pd_init();
    CHECK(xfu_native_open_inner(wrapped, XX_FILE_TYPE_GZ, &pd, &inner) == XFU_NATIVE_INNER_DECODE_ERROR);
    CHECK(inner == NULL);
    CHECK(snprintf(wrapped, sizeof(wrapped), "%s/payload.b64", argv[1]) > 0);
    CHECK(write_file(wrapped, "begin-base64 644 payload\ncGxhaW4gdGV4dAo=\n====\n"));
    pd = xx_pd_init();
    CHECK(xfu_native_base64_open(wrapped, &pd, &inner, &decoded_name) ==
          XFU_NATIVE_ENVELOPE_RAW);
    CHECK(!strcmp(decoded_name, "payload"));
    CHECK(device_matches(inner, (const unsigned char *)"plain text\n", 11));
    CHECK(xx_io_close(inner) == 0);
    free(decoded_name); inner = NULL; decoded_name = NULL;
    CHECK(write_file(wrapped, cpio_b64));
    pd = xx_pd_init();
    CHECK(xfu_native_base64_open(wrapped, &pd, &inner, &decoded_name) ==
          XFU_NATIVE_ENVELOPE_ARCHIVE);
    CHECK(!strcmp(decoded_name, "payload"));
    CHECK(device_matches(inner, cpio_gz, sizeof(cpio_gz)));
    CHECK(xx_io_close(inner) == 0);
    free(decoded_name); inner = NULL; decoded_name = NULL;
    borrowed = xx_io_file_open(wrapped, "rb");
    CHECK(borrowed);
    pd = xx_pd_init();
    CHECK(xfu_native_base64_open_device(borrowed, &pd, &inner, &decoded_name) ==
          XFU_NATIVE_ENVELOPE_ARCHIVE);
    CHECK(device_matches(inner, cpio_gz, sizeof(cpio_gz)));
    CHECK(xx_io_close(inner) == 0 && xx_io_close(borrowed) == 0);
    free(decoded_name); inner = NULL; borrowed = NULL; decoded_name = NULL;
    listed = (capture){0};
    request = request_for(wrapped, XFU_COMMAND_LIST, &listed);
    CHECK(xfu_run(&request) == 0);
    CHECK(listed.entries == 1 && !strcmp(listed.name, "hello.txt"));
    tested = (capture){0};
    request = request_for(wrapped, XFU_COMMAND_TEST, &tested);
    CHECK(xfu_run(&request) == 0);
    CHECK(tested.tests == 1 && tested.test_success && tested.percent == 100);
    CHECK(write_file(wrapped, "begin-base64 644 payload\ncGxhaW4gdGV4dAo=\n"));
    pd = xx_pd_init();
    CHECK(xfu_native_base64_open(wrapped, &pd, &inner, &decoded_name) ==
          XFU_NATIVE_ENVELOPE_DECODE_ERROR);
    CHECK(!inner && !decoded_name);
    {
        /* base64 -w0 writes the payload as one line of any length. */
        static const char head[] = "begin-base64 644 long.bin\n";
        size_t groups = 3000, at = sizeof(head) - 1U, i;
        char *text = (char *)malloc(sizeof(head) + groups * 4U + 8U);
        unsigned char tail[9];
        CHECK(text);
        memcpy(text, head, at);
        for (i = 0; i < groups; ++i) { memcpy(text + at, "QUJD", 4); at += 4; }
        /* The terminator line, NUL included, fills the buffer exactly. */
        memcpy(text + at, "\r\n====\r\n", 9);
        CHECK(write_file(wrapped, text));
        free(text);
        pd = xx_pd_init();
        CHECK(xfu_native_base64_open(wrapped, &pd, &inner, &decoded_name) ==
              XFU_NATIVE_ENVELOPE_RAW);
        CHECK(!strcmp(decoded_name, "long.bin") && xx_io_total_size(inner) == 9000);
        CHECK(xx_io_seek64(inner, 8991, SEEK_SET) == 0 &&
              xx_io_read(inner, tail, sizeof(tail)) == (ssize_t)sizeof(tail) &&
              !memcmp(tail, "ABCABCABC", sizeof(tail)));
        CHECK(xx_io_close(inner) == 0);
        free(decoded_name); inner = NULL; decoded_name = NULL;
    }
    /* Text after the envelope leaves the file to the ordinary reader. */
    CHECK(write_file(wrapped, "begin-base64 644 payload\ncGxhaW4gdGV4dAo=\n====\nsignature\n"));
    pd = xx_pd_init();
    CHECK(xfu_native_base64_open(wrapped, &pd, &inner, &decoded_name) ==
          XFU_NATIVE_ENVELOPE_NOT_FOUND);
    CHECK(!inner && !decoded_name);
    CHECK(snprintf(wrapped, sizeof(wrapped), "%s/payload.uue", argv[1]) > 0);
    CHECK(write_file(wrapped, cpio_uue));
    pd = xx_pd_init();
    CHECK(xfu_native_uue_open(wrapped, &pd, &inner, &decoded_name) ==
          XFU_NATIVE_ENVELOPE_ARCHIVE);
    CHECK(!strcmp(decoded_name, "payload"));
    CHECK(device_matches(inner, cpio_gz, sizeof(cpio_gz)));
    CHECK(xx_io_close(inner) == 0);
    free(decoded_name); inner = NULL; decoded_name = NULL;
    borrowed = xx_io_file_open(wrapped, "rb");
    CHECK(borrowed);
    pd = xx_pd_init();
    CHECK(xfu_native_uue_open_device(borrowed, &pd, &inner, &decoded_name) ==
          XFU_NATIVE_ENVELOPE_ARCHIVE);
    CHECK(device_matches(inner, cpio_gz, sizeof(cpio_gz)));
    CHECK(xx_io_close(inner) == 0 && xx_io_close(borrowed) == 0);
    free(decoded_name); inner = NULL; borrowed = NULL; decoded_name = NULL;
    listed = (capture){0};
    request = request_for(wrapped, XFU_COMMAND_LIST, &listed);
    CHECK(xfu_run(&request) == 0);
    CHECK(listed.entries == 1 && !strcmp(listed.name, "hello.txt"));
    CHECK(snprintf(wrapped, sizeof(wrapped), "%s/empty", argv[1]) > 0);
    CHECK(write_file(wrapped, ""));
    listed = (capture){0};
    pd = xx_pd_init();
    request = request_for(wrapped, XFU_COMMAND_LIST, &listed);
    CHECK(xfu_native_empty_read(&request, &pd) == 0);
    CHECK(listed.entries == 0 && listed.complete == 1);
    tested = (capture){0};
    pd = xx_pd_init();
    request = request_for(wrapped, XFU_COMMAND_TEST, &tested);
    CHECK(xfu_native_empty_read(&request, &pd) == 0);
    CHECK(tested.entries == 0 && tested.percent == 100 && tested.complete == 1);
    request.extract_selected = true;
    request.selected_records = first;
    request.selected_record_count = 1;
    pd = xx_pd_init();
    CHECK(xfu_native_empty_read(&request, &pd) == 1);
    CHECK(write_file(wrapped, "nonempty"));
    pd = xx_pd_init();
    CHECK(xfu_native_empty_read(&request, &pd) == 2);
    puts("native reader adapter checks passed");
    return 0;
}
