/* Copyright (c) 2026 hors <horsicq@gmail.com>
 * SPDX-License-Identifier: MIT */
#include "xxfclib/algo/lzip/xx_lzip.h"
#include <stdio.h>
#include <string.h>

static const unsigned char member[] = {
    0x4c,0x5a,0x49,0x50,0x01,0x0c,0x00,0x31,0x1b,0xcb,0x11,0x9b,0x05,0x06,0x3c,
    0xd3,0x24,0x0e,0xeb,0xc1,0x1a,0x39,0xcc,0xd0,0xf1,0x56,0x66,0x09,0x9a,0x4a,
    0x6b,0xe5,0x7a,0xf7,0xff,0xfe,0x42,0x50,0x00,0x4a,0xef,0x80,0x2e,0x04,0x01,
    0x00,0x00,0x00,0x00,0x00,0x00,0x3b,0x00,0x00,0x00,0x00,0x00,0x00,0x00
};

static int check(const unsigned char *bytes, size_t size, int strict, int valid,
                 size_t expected_members, size_t expected_consumed)
{
    unsigned char output[1024];
    xx_io_device *input = xx_io_mem_open_ro(bytes, size);
    xx_io_device *sink = xx_io_mem_open(output, sizeof(output));
    int64_t written = -1, consumed = 0;
    size_t count = 0, i;
    bool ok;
    if (!input || !sink) return 1;
    memset(output, 0, sizeof(output));
    ok = strict ? xx_lzip_decode_device(input, 0, (int64_t)size, sink, &written, &count, NULL)
                : xx_lzip_decode_prefix_device(input, 0, (int64_t)size, sink, &written, &count, &consumed, NULL);
    xx_io_close(sink);
    xx_io_close(input);
    if (ok != (valid != 0)) {
        fprintf(stderr, "decode strict=%d size=%zu returned %d, expected %d\n", strict, size, ok, valid);
        return 1;
    }
    if (!ok) return 0;
    if (count != expected_members || written != (int64_t)(260U * count) ||
        (!strict && consumed != (int64_t)expected_consumed)) return 1;
    for (i = 0; i < 13U * count; ++i)
        if (memcmp(output + i * 20U, "bounded lzip member\n", 20U)) return 1;
    return 0;
}

int main(void)
{
    unsigned char bytes[256];
    int failures = 0;
    const size_t n = sizeof(member);
    failures += check(member, n, 1, 1, 1, n);
    failures += check(member, n, 0, 1, 1, n);
    memcpy(bytes, member, n);
    memcpy(bytes + n, "plain text after a complete member", 34U);
    failures += check(bytes, n + 34U, 1, 0, 0, 0);
    failures += check(bytes, n + 34U, 0, 1, 1, n);
    memcpy(bytes + n, member, n);
    failures += check(bytes, n * 2U, 0, 1, 2, n * 2U);
    failures += check(bytes, n * 2U, 1, 1, 2, n * 2U);
    failures += check(bytes, n + 3U, 0, 0, 0, 0); /* truncated next header */
    failures += check(bytes, n * 2U - 1U, 0, 0, 0, 0); /* truncated next trailer */
    bytes[n] ^= 1U;
    failures += check(bytes, n * 2U, 0, 0, 0, 0); /* damaged next magic */
    memcpy(bytes + n, member, n);
    bytes[n + 4U] = 2U;
    failures += check(bytes, n * 2U, 0, 0, 0, 0); /* unsupported next version */
    bytes[n + 4U] = 1U;
    bytes[n + 5U] = 0U;
    failures += check(bytes, n * 2U, 0, 0, 0, 0); /* invalid next dictionary */
    memcpy(bytes, member, n);
    bytes[n - 20U] ^= 1U;
    failures += check(bytes, n, 0, 0, 0, 0); /* CRC */
    memcpy(bytes, member, n);
    bytes[n - 8U] ^= 1U;
    failures += check(bytes, n, 0, 0, 0, 0); /* member size */
    memcpy(bytes, member, n);
    bytes[4] = 0U; /* v0 has no final eight-byte member-size field */
    failures += check(bytes, n - 8U, 0, 1, 1, n - 8U);
    memcpy(bytes + n - 8U, member, n);
    failures += check(bytes, n * 2U - 8U, 0, 0, 0, 0); /* v0 cannot concatenate */
    return failures ? 1 : 0;
}
