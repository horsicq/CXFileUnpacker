/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#ifndef XFILEUNPACKER_CORE_H
#define XFILEUNPACKER_CORE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <xxfclib/data/xx_pd.h>
#include <xxfclib/xxfc_defs.h>

typedef enum xfu_command {
    XFU_COMMAND_NONE = 0,
    XFU_COMMAND_EXTRACT,
    XFU_COMMAND_LIST,
    XFU_COMMAND_TEST,
    XFU_COMMAND_ADD
} xfu_command;

typedef struct xfu_property {
    const char *name;
    const char *value;
} xfu_property;

/* Names and messages are UTF-8; callback arguments are borrowed for the call. */
typedef struct xfu_entry {
    const char *name;
    int64_t packed_size;
    int64_t unpacked_size; /* -1 when the format does not report a size. */
    bool is_directory;
    char modified[20]; /* Display timestamp, or empty when not reported. */
    char attributes[24]; /* Format attributes as hexadecimal, or empty. */
    const xfu_property *properties; /* All reader metadata and record fields. */
    size_t property_count;
} xfu_entry;

typedef struct xfu_callbacks {
    void *user;
    void (*log)(void *user, bool error, const char *line);
    void (*entry)(void *user, const xfu_entry *entry);
    /* total == 0 means that the member count is not known yet. */
    void (*progress)(void *user, uint64_t completed, uint64_t total,
                     const char *name);
    bool (*cancelled)(void *user);
    /* Detected interpretations, generic first, and the type used to open.
     * Called before parsing; the array is borrowed for this call. */
    void (*file_types)(void *user, const xx_file_type_t *types, size_t count,
                       xx_file_type_t selected);
} xfu_callbacks;

typedef struct xfu_request {
    xfu_command command;
    const char *archive_path;
    const char *output_dir; /* NULL uses "." for extraction. */
    const char *const *files;
    size_t file_count;
    xfu_callbacks callbacks;
    /* Optional caller-initialized monitor. xx_pd_stop() also cancels decoding
     * inside a member; callbacks run synchronously on the calling thread. */
    xx_pd_struct *progress_state;
    /* EXTRACT only: sorted, unique zero-based reader record indexes. Selection
     * is explicit: an empty/invalid selection never falls back to all members. */
    bool extract_selected;
    const size_t *selected_records;
    size_t selected_record_count;
    /* UNKNOWN (zero) detects automatically. Other values select an exact
     * interpretation from the detected chain; BINARY cannot open an archive.
     * ADD still chooses its writer from the destination extension. */
    xx_file_type_t file_type;
} xfu_request;

xfu_command xfu_parse_command(const char *text);
/* 0: success, 1: partial failure/cancellation, 2: usage/open/format failure.
 * The core never prints; diagnostics only go to the attached log callback. */
int xfu_run(const xfu_request *request);

#endif
