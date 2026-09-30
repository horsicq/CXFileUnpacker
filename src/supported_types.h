/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#ifndef XFILEUNPACKER_SUPPORTED_TYPES_H
#define XFILEUNPACKER_SUPPORTED_TYPES_H

#include <stddef.h>

/* Shared UTF-8 report for the console, dialog and clipboard. Caller frees it. */
char *xfu_supported_types_text(size_t *count);

#endif
