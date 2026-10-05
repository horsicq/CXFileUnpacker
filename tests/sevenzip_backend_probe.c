/* SPDX-License-Identifier: MIT. Real pipe progress and stalled-writer controls. */
#ifdef XFU_STALLED_HELPER
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <fcntl.h>
#include <io.h>
static uint32_t le32(const unsigned char *p) {
    return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static void put32(unsigned char *p, uint32_t n) {
    p[0] = (unsigned char)n; p[1] = (unsigned char)(n >> 8);
    p[2] = (unsigned char)(n >> 16); p[3] = (unsigned char)(n >> 24);
}
int main(void) {
    unsigned char header[12], data[4096];
    uint32_t left;
    if (_setmode(_fileno(stdin), _O_BINARY) == -1 ||
        _setmode(_fileno(stdout), _O_BINARY) == -1) return 2;
    if (fread(header, 1, sizeof(header), stdin) != sizeof(header) ||
        le32(header) != UINT32_C(0x3150375a) || le32(header + 4) != 1) return 2;
    left = le32(header + 8);
    if (left > 1048576U) return 2;
    while (left) {
        size_t n = left < sizeof(data) ? left : sizeof(data);
        if (fread(data, 1, n, stdin) != n) return 2;
        left -= (uint32_t)n;
    }
    put32(header, UINT32_C(0x3150375a)); put32(header + 4, 2); put32(header + 8, 12);
    put32(data, 0); put32(data + 4, 0); put32(data + 8, 65536);
    if (fwrite(header, 1, sizeof(header), stdout) != sizeof(header) ||
        fwrite(data, 1, 12, stdout) != 12 || fflush(stdout)) return 2;
    /* A complete 64 KiB response plus its frame exceeds the pipe quota.
     * The parent must interrupt its pending write without this process
     * draining even one response byte. The parent Job cleans us up. */
    Sleep(INFINITE);
    return 2;
}
#else
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <xxfclib/formats/sevenzip_backend/xx_sevenzip_backend.h>
#include <xxfclib/io/xx_io.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;
#define REQUIRE(expression) do { ++checks; if (!(expression)) { fprintf(stderr, "check %u failed at line %u: %s\n", checks, __LINE__, #expression); goto done; } } while (0)
typedef enum cancel_mode { NO_CANCEL, ON_DATA, ON_ENTER, ON_LEAVE, BY_CLOCK } cancel_mode;
typedef struct observations {
    cancel_mode cancel;
    uint64_t start, last, expected;
    unsigned increases;
    bool saw_level, saw_middle, saw_leave, wrong_total;
} observations;
static bool observe(const xx_pd_struct *pd, void *user) {
    observations *o = (observations *)user;
    const xx_pd_record *record = &pd->records[1];
    if (record->is_busy) {
        o->saw_level = true;
        if (record->total != o->expected) o->wrong_total = true;
        if (record->current > o->last) { o->last = record->current; ++o->increases; }
        if (record->current && record->current < record->total) o->saw_middle = true;
        if (o->cancel == ON_ENTER || (o->cancel == ON_DATA && record->current)) return true;
    } else if (o->saw_level) {
        o->saw_leave = true;
        if (o->cancel == ON_LEAVE) return true;
    }
    return o->cancel == BY_CLOCK && GetTickCount64() - o->start >= 100U;
}
int main(int argc, char **argv) {
    unsigned char bytes[65536] = {0};
    xx_io_device *source = NULL;
    xx_io_memory_only_scope scope = {0};
    xx_pd_struct pd = xx_pd_init();
    xx_pd_observer previous = {0};
    xx_sevenzip_backend_status status;
    xx_sevenzip_backend_options options;
    observations seen;
    uint64_t expected, start;
    int result = 1, outer, trial;
    bool scoped = false, bound = false;
    REQUIRE(argc == 5);
    expected = _strtoui64(argv[4], NULL, 10);
    REQUIRE(expected > 65536U);
    REQUIRE(xx_io_memory_only_begin(&scope, 8U * 1024U * 1024U)); scoped = true;
    for (trial = 0; trial < 6; ++trial) {
        bool success;
        pd = xx_pd_init();
        memset(&options, 0, sizeof(options)); memset(&seen, 0, sizeof(seen));
        options.max_member_size = UINT64_MAX; options.memory_limit = 64U * 1024U * 1024U;
        options.status = &status; options.pd = &pd;
        options.helper_path = trial < 2 ? argv[1] : argv[2];
        options.timeout_ms = trial == 0 ? 200U : trial == 1 ? 1000U : 60000U;
        seen.expected = trial < 2 ? sizeof(bytes) : expected;
        seen.cancel = trial == 0 ? NO_CANCEL : trial == 1 ? BY_CLOCK :
            trial == 2 ? NO_CANCEL : trial == 3 ? ON_DATA : trial == 4 ? ON_ENTER : ON_LEAVE;
        source = trial < 2 ? xx_io_mem_open_ro(bytes, sizeof(bytes)) : xx_io_file_open(argv[3], "rb");
        REQUIRE(source != NULL);
        REQUIRE(xx_io_seek64(source, 11, SEEK_SET) == 0);
        outer = xx_pd_enter_level(&pd, 42, "caller"); REQUIRE(outer == 0);
        xx_pd_set_current(&pd, outer, 17);
        seen.start = start = GetTickCount64();
        previous = xx_pd_set_observer(&pd, observe, &seen); bound = true;
        success = xx_sevenzip_backend_read(source, 0, -1, "gzip", 0,
            seen.expected, NULL, &options);
        REQUIRE(GetTickCount64() - start < (trial < 2 ? 1000U : 60000U));
        REQUIRE(xx_io_tell(source) == 11);
        REQUIRE(pd.records[0].is_busy && pd.records[0].current == 17 &&
            pd.records[0].total == 42 && !strcmp(pd.records[0].status, "caller"));
        REQUIRE(!pd.records[1].is_busy && !pd.records[2].is_busy &&
            !pd.records[3].is_busy && !pd.records[4].is_busy);
        REQUIRE(seen.saw_level && seen.saw_leave && !seen.wrong_total);
        if (trial == 0) REQUIRE(!success && status == XX_SEVENZIP_BACKEND_TIMEOUT);
        else if (trial != 2) REQUIRE(!success && status == XX_SEVENZIP_BACKEND_CANCELLED);
        else {
            REQUIRE(success && status == XX_SEVENZIP_BACKEND_OK);
            REQUIRE(seen.increases > 1 && seen.saw_middle && seen.last == expected);
        }
        if (trial == 3) REQUIRE(seen.last > 0 && seen.last < expected);
        if (trial == 4) REQUIRE(seen.last == 0);
        if (trial == 5) REQUIRE(seen.last == expected);
        xx_pd_set_observer(previous.progress, previous.callback, previous.user_data); bound = false;
        xx_pd_leave_level(&pd, outer);
        xx_io_close(source); source = NULL;
        REQUIRE(xx_io_memory_only_used() == 0);
    }
    REQUIRE(xx_io_memory_only_end(&scope)); scoped = false;
    printf("{\"checks\":%u,\"decoded_size\":%llu,\"stalled_write_timeout\":true,\"stalled_write_cancel\":true,\"member_progress\":true}\n",
        checks, (unsigned long long)expected);
    result = 0;
done:
    if (bound) xx_pd_set_observer(previous.progress, previous.callback, previous.user_data);
    if (source) xx_io_close(source);
    if (scoped) (void)xx_io_memory_only_end(&scope);
    return result;
}
#endif
