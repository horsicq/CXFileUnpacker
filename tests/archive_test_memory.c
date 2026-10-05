/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 * Operation-level checks: fixtures are created by the Python harness before
 * this process runs. The tested TEST operation has no output destination.
 */
#include "core.h"
#include <xxfclib/io/xx_io.h>
#include <xxfclib/formats/izpack/xx_izpack.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "%s:%d: %s\n", \
    __FILE__, __LINE__, #c); return 1; } } while (0)

typedef struct observation {
    const char *mode;
    unsigned results, failures, entries, percent, percent_calls, inside_polls;
    bool bad, stop, inside_stopped, attempted;
} observation;

static void entry(void *user, const xfu_entry *item) {
    observation *o = (observation *)user;
    ++o->entries;
    if (!item || !item->name || !*item->name) o->bad = true;
    if (!strcmp(o->mode, "mutate") && !o->attempted) {
        xx_io_device *d;
        o->attempted = true;
        d = xx_io_file_open("forbidden-test-output.bin", "wb");
        if (d) { o->bad = true; xx_io_close(d); }
    }
}
static void result(void *user, const xfu_entry *item, bool ok) {
    observation *o = (observation *)user;
    if (!item || !item->name || !*item->name) o->bad = true;
    ++o->results;
    if (!ok) ++o->failures;
    if (!strcmp(o->mode, "cancel-after")) o->stop = true;
}
static void percent(void *user, unsigned value) {
    observation *o = (observation *)user;
    if (value > 100U || (o->percent_calls && value < o->percent)) o->bad = true;
    o->percent = value;
    ++o->percent_calls;
}
static bool cancel(void *user) { return ((observation *)user)->stop; }
static bool observer(const xx_pd_struct *pd, void *user) {
    observation *o = (observation *)user;
    (void)pd;
    /* Arm only after the first member is handed to the callback. The large
     * stored ZIP fixture polls repeatedly while reading its payload. */
    if (!strcmp(o->mode, "cancel-inside") && o->entries && !o->results &&
        ++o->inside_polls == 16U) {
        o->inside_stopped = true;
        return true;
    }
    return false;
}

typedef struct foreign_stream { xx_io_device *device; bool passed; } foreign_stream;
#ifdef _WIN32
static DWORD WINAPI foreign_use(LPVOID user)
#else
static void *foreign_use(void *user)
#endif
{
    foreign_stream *test = (foreign_stream *)user;
    uint8_t byte;
    /* None of these operations may touch or free the owner thread's stream. */
    test->passed = xx_io_read(test->device, &byte, 1) < 0 &&
                   xx_io_write(test->device, "x", 1) < 0 &&
                   xx_io_seek64(test->device, 0, SEEK_SET) < 0 &&
                   xx_io_close(test->device) < 0;
    return 0;
}

static int policy_checks(void) {
    xx_io_memory_only_scope outer = {0}, inner = {0};
    xx_io_device *a, *b;
    unsigned char data[80];
    static const unsigned char marker[] = {0, 0x80, 0xff, 9};
    CHECK(!xx_io_memory_only_active());
    CHECK(xx_io_memory_only_begin(&outer, 8192U));
    a = xx_io_temp_open();
    CHECK(a && xx_io_is_memory(a) && !xx_io_source_path(a));
    CHECK(xx_io_write(a, marker, sizeof(marker)) == sizeof(marker));
    CHECK(xx_io_seek64(a, 64, SEEK_SET) == 0);
    CHECK(xx_io_write(a, marker, sizeof(marker)) == sizeof(marker));
    CHECK(xx_io_total_size(a) == 68);
    CHECK(xx_io_seek64(a, 0, SEEK_SET) == 0 && xx_io_read(a, data, 68) == 68);
    CHECK(!memcmp(data, marker, sizeof(marker)) && !memcmp(data + 64, marker, 4));
    { size_t i; for (i = 4; i < 64; ++i) CHECK(data[i] == 0); }
    CHECK(xx_io_memory_only_used() > 0U && xx_io_memory_only_used() <= 8192U);
    CHECK(xx_io_memory_only_begin(&inner, 4096U));
    b = xx_io_temp_open();
    CHECK(b && xx_io_is_memory(b));
    CHECK(xx_io_seek64(b, 4096, SEEK_SET) == 0);
    CHECK(xx_io_write(b, marker, 1) < 0);
    CHECK(xx_io_close(b) == 0);
    CHECK(!xx_io_memory_only_end(&inner));
    CHECK(xx_io_memory_only_error(&inner) == XX_IO_MEMORY_ONLY_LIMIT);
    CHECK(xx_io_close(a) == 0 && xx_io_memory_only_used() == 0U);
    CHECK(!xx_io_memory_only_end(&outer));
    CHECK(!xx_io_memory_only_active());

    memset(&outer, 0, sizeof(outer)); memset(&inner, 0, sizeof(inner));
    CHECK(xx_io_memory_only_begin(&outer, 4096U));
    a = xx_io_temp_open();
    CHECK(a && xx_io_write(a, marker, sizeof(marker)) == sizeof(marker));
    CHECK(xx_io_memory_only_begin(&inner, 0U));
    CHECK(xx_io_seek64(a, 0, SEEK_SET) == 0 && xx_io_read(a, data, 4) == 4);
    /* Even writing inside existing capacity cannot bypass the child ceiling. */
    CHECK(xx_io_seek64(a, 0, SEEK_SET) == 0 && xx_io_write(a, marker, 1) < 0);
    CHECK(!xx_io_memory_only_end(&inner) &&
          xx_io_memory_only_error(&inner) == XX_IO_MEMORY_ONLY_SCOPE_ORDER);
    CHECK(xx_io_close(a) == 0 && !xx_io_memory_only_end(&outer));

    memset(&outer, 0, sizeof(outer));
    CHECK(xx_io_memory_only_begin(&outer, 4096U));
    a = xx_io_temp_open();
    CHECK(a && xx_io_write(a, marker, 4) == 4 && xx_io_seek64(a, 0, SEEK_SET) == 0);
    {
        foreign_stream test = {a, false};
#ifdef _WIN32
        HANDLE thread = CreateThread(NULL, 0, foreign_use, &test, 0, NULL);
        CHECK(thread && WaitForSingleObject(thread, 5000) == WAIT_OBJECT_0);
        CHECK(CloseHandle(thread));
#else
        pthread_t thread;
        CHECK(pthread_create(&thread, NULL, foreign_use, &test) == 0);
        CHECK(pthread_join(thread, NULL) == 0);
#endif
        CHECK(test.passed);
    }
    CHECK(xx_io_read(a, data, 4) == 4 && !memcmp(data, marker, 4));
    CHECK(xx_io_close(a) == 0 && xx_io_memory_only_end(&outer));

    memset(&outer, 0, sizeof(outer));
    CHECK(xx_io_memory_only_begin(&outer, 4096U));
    a = xx_io_temp_open();
    CHECK(a && xx_io_write(a, marker, 4) == 4);
    CHECK(!xx_io_memory_only_end(&outer) &&
          xx_io_memory_only_error(&outer) == XX_IO_MEMORY_ONLY_LIVE_TEMP);
    CHECK(xx_io_read(a, data, 1) < 0 && xx_io_write(a, marker, 1) < 0);
    CHECK(xx_io_close(a) == 0 && !xx_io_memory_only_active());

    memset(&outer, 0, sizeof(outer));
    CHECK(xx_io_memory_only_begin(&outer, 4096U));
    CHECK(!xx_io_file_open("forbidden-test-output.bin", "wb"));
    CHECK(!xx_io_file_remove_a("forbidden-test-output.bin"));
    CHECK(!xx_io_file_replace_a("forbidden-test-output.bin", "other.bin", true));
    CHECK(!xx_io_create_dirs_a("forbidden-test-directory", true));
    CHECK(!xx_io_memory_only_end(&outer));
    CHECK(xx_io_memory_only_error(&outer) == XX_IO_MEMORY_ONLY_DISK_WRITE);
    CHECK(!xx_io_memory_only_active());
    return 0;
}

static ssize_t fail_read(xx_io_device *device, void *buffer, size_t size) {
    (void)device; (void)buffer; (void)size; return -1;
}
static int izpack_read_error(const char *path) {
    xx_io_device *source = xx_io_file_open(path, "rb"), *memory;
    int64_t size;
    uint8_t *bytes;
    xx_izpack format;
    xx_archive_record_state *state;
    xx_pd_struct pd = xx_pd_init();
    xx_io_memory_only_scope scope = {0};
    ssize_t (*read_fn)(xx_io_device *, void *, size_t);
    CHECK(source && (size = xx_io_size(source)) > 0 && size < 1048576);
    bytes = (uint8_t *)malloc((size_t)size);
    CHECK(bytes && xx_io_read(source, bytes, (size_t)size) == size);
    CHECK(xx_io_close(source) == 0);
    CHECK(xx_io_memory_only_begin(&scope, 1048576U));
    memory = xx_io_mem_open_ro(bytes, (size_t)size);
    CHECK(memory);
    xx_izpack_init(&format, memory, 0);
    state = xx_izpack_create_archive_records_reading(&format.format, NULL, &pd);
    CHECK(state && state->has_record && state->options.count == 0);
    /* Parsing succeeds first. A later body-read failure must not become a
     * successful address-only dry run. Restore the reader to prove the same
     * framed member then verifies, and a stopped monitor still rejects it. */
    read_fn = memory->read;
    memory->read = fail_read;
    CHECK(!xx_izpack_unpack_current_archive_record(&format.format, state, &pd));
    memory->read = read_fn;
    CHECK(xx_izpack_unpack_current_archive_record(&format.format, state, &pd));
    xx_pd_stop(&pd);
    CHECK(!xx_izpack_unpack_current_archive_record(&format.format, state, &pd));
    xx_izpack_free_archive_records_reading(&format.format, state);
    xx_izpack_destroy(&format);
    CHECK(xx_io_close(memory) == 0 && xx_io_memory_only_end(&scope));
    free(bytes);
    puts("Framed IzPack validation reads payload and honors read failure/cancel");
    return 0;
}

int main(int argc, char **argv) {
    xfu_request request = {0};
    xx_pd_struct pd = xx_pd_init();
    xx_pd_observer previous;
    xx_io_memory_only_scope scope = {0};
    observation o = {0};
    int status, expected_status;
    unsigned expected_results, expected_failures;
    bool ended;
    CHECK(argc == 6 || argc == 7);
    CHECK(policy_checks() == 0);
    if (!strcmp(argv[5], "izpack-read-error")) return izpack_read_error(argv[1]);
    expected_status = atoi(argv[2]);
    expected_results = (unsigned)strtoul(argv[3], NULL, 10);
    expected_failures = (unsigned)strtoul(argv[4], NULL, 10);
    o.mode = argv[5];
    o.stop = !strcmp(o.mode, "cancel-before");
    request.command = XFU_COMMAND_TEST;
    request.archive_path = argv[1];
    /* Even an explicitly supplied output path must have no effect on TEST. */
    request.output_dir = "forbidden-test-directory";
    request.password = argc == 7 ? argv[6] : NULL;
    request.progress_state = &pd;
    request.callbacks.user = &o;
    request.callbacks.entry = entry;
    request.callbacks.test_result = result;
    request.callbacks.test_progress = percent;
    request.callbacks.cancelled = cancel;
    previous = xx_pd_set_observer(&pd, observer, &o);
    CHECK(xx_io_memory_only_begin(&scope, UINT64_C(64) * 1024U * 1024U));
    status = xfu_run(&request);
    CHECK(xx_io_memory_only_used() == 0U);
    ended = xx_io_memory_only_end(&scope);
    xx_pd_set_observer(previous.progress, previous.callback, previous.user_data);
    CHECK(!xx_io_memory_only_active());
    CHECK(status == expected_status && o.results == expected_results &&
          o.failures == expected_failures && !o.bad);
    if (!strcmp(o.mode, "mutate")) {
        CHECK(o.attempted && !ended &&
              xx_io_memory_only_error(&scope) == XX_IO_MEMORY_ONLY_DISK_WRITE);
    } else CHECK(ended && xx_io_memory_only_error(&scope) == XX_IO_MEMORY_ONLY_OK);
    if (!strcmp(o.mode, "normal") && status != 2)
        CHECK(o.percent_calls && o.percent == 100U);
    if (!strcmp(o.mode, "cancel-before"))
        CHECK(!o.entries && !o.percent_calls && !o.results);
    if (!strcmp(o.mode, "cancel-after") || !strcmp(o.mode, "cancel-inside"))
        CHECK(o.percent < 100U && xx_pd_is_stopped(&pd));
    if (!strcmp(o.mode, "cancel-inside")) CHECK(o.inside_stopped);
    puts("Memory-only policy, callbacks and archive result verified");
    return 0;
}
