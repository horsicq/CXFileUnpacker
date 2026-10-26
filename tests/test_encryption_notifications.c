/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 *
 * Public engine encryption-notification contract. No external archiver is
 * invoked: FreeArc uses checked-in independent fixtures and ZIP/7z archives
 * are written by the native engine. Usage: test FIXTURE_DIR TEMP_ROOT.
 */
#include "core.h"
#include <xxfclib/io/xx_io.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); return 1; \
} } while (0)

static const char fixture_password[] = "FreeArc-fixture-password";
static const char native_password[] = "xfu-native-test-password";
static const char incorrect_password[] = "xfu-incorrect-secret";

typedef struct capture {
    size_t events;
    size_t detected;
    size_t required;
    size_t rejected;
    size_t archive_required;
    size_t archive_rejected;
    size_t entries;
    size_t encrypted_entries;
    size_t test_results;
    size_t encrypted_test_results;
    size_t failed_test_results;
    bool invalid_status;
    bool leaked_credential;
    bool cancel_on_entry;
    xx_pd_struct *progress;
} capture;

static bool contains_credential(const char *text) {
    return text && (strstr(text, fixture_password) ||
                    strstr(text, native_password) ||
                    strstr(text, incorrect_password));
}

static void capture_log(void *user, bool error, const char *line) {
    capture *state = (capture *)user;
    (void)error;
    /* Do not echo engine diagnostics: a regression must not print a secret. */
    if (contains_credential(line)) state->leaked_credential = true;
}

static void capture_entry(void *user, const xfu_entry *entry) {
    capture *state = (capture *)user;
    ++state->entries;
    if (entry->is_encrypted) ++state->encrypted_entries;
    if (contains_credential(entry->name)) state->leaked_credential = true;
    if (state->cancel_on_entry) xx_pd_stop(state->progress);
}

static void capture_test_result(void *user, const xfu_entry *entry, bool success) {
    capture *state = (capture *)user;
    ++state->test_results;
    if (entry->is_encrypted) ++state->encrypted_test_results;
    if (!success) ++state->failed_test_results;
    if (contains_credential(entry->failure)) state->leaked_credential = true;
}

static void capture_encryption(void *user, xfu_encryption_status status,
                               const char *member_name) {
    capture *state = (capture *)user;
    ++state->events;
    if (contains_credential(member_name)) state->leaked_credential = true;
    switch (status) {
        case XFU_ENCRYPTION_DETECTED:
            ++state->detected;
            break;
        case XFU_ENCRYPTION_PASSWORD_REQUIRED:
            ++state->required;
            if (!member_name) ++state->archive_required;
            break;
        case XFU_ENCRYPTION_PASSWORD_REJECTED:
            ++state->rejected;
            if (!member_name) ++state->archive_rejected;
            break;
        default:
            state->invalid_status = true;
            break;
    }
}

static xfu_request request_for(capture *state, xfu_command command,
                               const char *archive, xx_file_type_t type,
                               const char *password) {
    xfu_request request = {0};
    memset(state, 0, sizeof(*state));
    request.command = command;
    request.archive_path = archive;
    request.file_type = type; /* Exact native type suppresses helper fallback. */
    request.password = password;
    request.callbacks.user = state;
    request.callbacks.log = capture_log;
    request.callbacks.entry = capture_entry;
    request.callbacks.test_result = capture_test_result;
    request.callbacks.encryption = capture_encryption;
    return request;
}

static bool make_path(char *output, size_t capacity, const char *root,
                       const char *name) {
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

static bool has_text(const char *path, const char *text) {
    char buffer[128];
    xx_io_device *file = xx_io_file_open(path, "rb");
    ssize_t size;
    bool success;
    if (!file) return false;
    size = xx_io_read(file, buffer, sizeof(buffer));
    success = size >= 0 && (size_t)size == strlen(text) && !memcmp(buffer, text, (size_t)size);
    return xx_io_close(file) == 0 && success;
}

/* Failure may report DETECTED before REQUIRED/REJECTED. Do not require an
 * exact event count: one archive and its separate encrypted members can each
 * notify. A successful metadata-only LIST must never request a password. */
static int expect_read(const char *archive, xx_file_type_t type,
                        xfu_command command, const char *password,
                        bool succeeds, xfu_encryption_status wanted,
                        size_t expected_entries, bool encrypted,
                        bool locked_metadata, const char *output) {
    capture state;
    xfu_request request = request_for(&state, command, archive, type, password);
    int result;
    request.output_dir = output;
    result = xfu_run(&request);
    if ((result == 0) != succeeds) {
        /* Paths and status are safe; supplied passwords are never printed. */
        fprintf(stderr, "unexpected result %d for %s, command %d\n",
                result, archive, (int)command);
        return 1;
    }
    CHECK(!state.invalid_status && !state.leaked_credential);
    if (expected_entries != SIZE_MAX) CHECK(state.entries == expected_entries);
    CHECK(state.encrypted_entries == (encrypted ? state.entries : 0U));
    CHECK(state.encrypted_test_results == (encrypted ? state.test_results : 0U));
    if (wanted == XFU_ENCRYPTION_PASSWORD_REQUIRED) {
        CHECK(state.required > 0 && state.rejected == 0);
        if (locked_metadata) CHECK(state.archive_required > 0);
    } else if (wanted == XFU_ENCRYPTION_PASSWORD_REJECTED) {
        CHECK(state.rejected > 0 && state.required == 0);
        if (locked_metadata) CHECK(state.archive_rejected > 0);
    } else if (wanted == XFU_ENCRYPTION_DETECTED) {
        CHECK(state.detected > 0 && state.required == 0 && state.rejected == 0);
    } else {
        CHECK(state.events == 0);
    }
    if (succeeds && command == XFU_COMMAND_TEST) {
        CHECK(state.failed_test_results == 0);
        if (expected_entries != SIZE_MAX) CHECK(state.test_results == expected_entries);
    }
    return 0;
}

static int freearc_checks(const char *fixtures, const char *temporary) {
    static const char *const locked_names[] = {
        "legacy_headers_and_members.arc", "fixed_headers_and_members.arc"
    };
    static const xfu_command commands[] = {XFU_COMMAND_LIST, XFU_COMMAND_TEST};
    static const char *const wrong_inputs[] = {NULL, incorrect_password, ""};
    char archive[2048], output[2048];
    size_t file, operation, candidate;

    for (file = 0; file < sizeof(locked_names) / sizeof(locked_names[0]); ++file) {
        CHECK(make_path(archive, sizeof(archive), fixtures, locked_names[file]));
        for (operation = 0; operation < sizeof(commands) / sizeof(commands[0]); ++operation) {
            for (candidate = 0; candidate < sizeof(wrong_inputs) / sizeof(wrong_inputs[0]); ++candidate) {
                CHECK(expect_read(archive, XX_FILE_TYPE_FREEARC, commands[operation],
                    wrong_inputs[candidate], false,
                    candidate ? XFU_ENCRYPTION_PASSWORD_REJECTED : XFU_ENCRYPTION_PASSWORD_REQUIRED,
                    0, true, true, NULL) == 0);
            }
            CHECK(expect_read(archive, XX_FILE_TYPE_FREEARC, commands[operation],
                fixture_password, true, XFU_ENCRYPTION_DETECTED, 2, true, false, NULL) == 0);
        }
    }

    CHECK(make_path(archive, sizeof(archive), fixtures, "legacy_members_only.arc"));
    /* Public names remain listable with absent, incorrect, or empty credentials. */
    for (candidate = 0; candidate < sizeof(wrong_inputs) / sizeof(wrong_inputs[0]); ++candidate) {
        CHECK(expect_read(archive, XX_FILE_TYPE_FREEARC, XFU_COMMAND_LIST,
            wrong_inputs[candidate], true, XFU_ENCRYPTION_DETECTED, 2, true, false, NULL) == 0);
        CHECK(expect_read(archive, XX_FILE_TYPE_FREEARC, XFU_COMMAND_TEST,
            wrong_inputs[candidate], false,
            candidate ? XFU_ENCRYPTION_PASSWORD_REJECTED : XFU_ENCRYPTION_PASSWORD_REQUIRED,
            SIZE_MAX, true, false, NULL) == 0);
    }
    CHECK(expect_read(archive, XX_FILE_TYPE_FREEARC, XFU_COMMAND_TEST,
        fixture_password, true, XFU_ENCRYPTION_DETECTED, 2, true, false, NULL) == 0);
    CHECK(make_path(output, sizeof(output), temporary, "freearc-extracted"));
    CHECK(expect_read(archive, XX_FILE_TYPE_FREEARC, XFU_COMMAND_EXTRACT,
        fixture_password, true, XFU_ENCRYPTION_DETECTED, 2, true, false, output) == 0);

    CHECK(make_path(archive, sizeof(archive), fixtures, "plain.arc"));
    for (operation = 0; operation < sizeof(commands) / sizeof(commands[0]); ++operation) {
        for (candidate = 0; candidate < sizeof(wrong_inputs) / sizeof(wrong_inputs[0]); ++candidate) {
            CHECK(expect_read(archive, XX_FILE_TYPE_FREEARC, commands[operation],
                wrong_inputs[candidate], true, (xfu_encryption_status)0, 2, false, false, NULL) == 0);
        }
    }
    return 0;
}

static int native_archive_checks(const char *temporary) {
    static const struct {
        const char *suffix;
        const char *format;
        xx_file_type_t type;
    } formats[] = {{"zip", "zip", XX_FILE_TYPE_ZIP},
                   {"7z", "7zip", XX_FILE_TYPE_7ZIP}};
    static const char *const passwords[] = {NULL, incorrect_password, ""};
    char source[2048], archive[2048], name[80];
    const char *sources[1];
    capture state;
    size_t format, protected_archive, candidate;
    CHECK(make_path(source, sizeof(source), temporary, "payload.txt"));
    CHECK(write_text(source, "encryption notification native writer fixture\n"));
    sources[0] = source;
    for (format = 0; format < sizeof(formats) / sizeof(formats[0]); ++format) {
        for (protected_archive = 0; protected_archive < 2; ++protected_archive) {
            xfu_request request;
            int length = snprintf(name, sizeof(name), "%s.%s",
                protected_archive ? "encrypted" : "plaintext", formats[format].suffix);
            CHECK(length >= 0 && (size_t)length < sizeof(name));
            CHECK(make_path(archive, sizeof(archive), temporary, name));
            request = request_for(&state, XFU_COMMAND_ADD, archive,
                                  XX_FILE_TYPE_UNKNOWN,
                                  protected_archive ? native_password : NULL);
            request.archive_format = formats[format].format;
            request.compression_method = "stored";
            request.files = sources;
            request.file_count = 1;
            CHECK(xfu_run(&request) == 0);
            CHECK(!state.leaked_credential && !state.invalid_status);
            if (!protected_archive) CHECK(state.events == 0);

            for (candidate = 0; candidate < sizeof(passwords) / sizeof(passwords[0]); ++candidate) {
                CHECK(expect_read(archive, formats[format].type, XFU_COMMAND_LIST,
                    passwords[candidate], true,
                    protected_archive ? XFU_ENCRYPTION_DETECTED : (xfu_encryption_status)0,
                    1, protected_archive != 0, false, NULL) == 0);
                CHECK(expect_read(archive, formats[format].type, XFU_COMMAND_TEST,
                    passwords[candidate], protected_archive == 0,
                    protected_archive
                        ? (candidate ? XFU_ENCRYPTION_PASSWORD_REJECTED : XFU_ENCRYPTION_PASSWORD_REQUIRED)
                        : (xfu_encryption_status)0,
                    SIZE_MAX, protected_archive != 0, false, NULL) == 0);
            }
            CHECK(expect_read(archive, formats[format].type, XFU_COMMAND_TEST,
                native_password, true,
                protected_archive ? XFU_ENCRYPTION_DETECTED : (xfu_encryption_status)0,
                1, protected_archive != 0, false, NULL) == 0);
        }
    }
    return 0;
}

static int ordinary_failure_checks(const char *fixtures, const char *temporary) {
    char archive[2048];
    CHECK(make_path(archive, sizeof(archive), temporary, "missing.arc"));
    CHECK(expect_read(archive, XX_FILE_TYPE_FREEARC, XFU_COMMAND_LIST,
        incorrect_password, false, (xfu_encryption_status)0, 0, false, false, NULL) == 0);
    CHECK(make_path(archive, sizeof(archive), temporary, "not-an-archive.bin"));
    CHECK(write_text(archive, "ordinary non-archive input\n"));
    CHECK(expect_read(archive, XX_FILE_TYPE_UNKNOWN, XFU_COMMAND_TEST,
        incorrect_password, false, (xfu_encryption_status)0, 0, false, false, NULL) == 0);
    CHECK(make_path(archive, sizeof(archive), fixtures, "plain.arc"));
    CHECK(expect_read(archive, XX_FILE_TYPE_ZIP, XFU_COMMAND_LIST,
        incorrect_password, false, (xfu_encryption_status)0, 0, false, false, NULL) == 0);
    return 0;
}

static int existing_output_checks(const char *fixtures, const char *temporary) {
    static const char sentinel[] = "keep the existing output\n";
    static const char *const passwords[] = {NULL, incorrect_password, ""};
    char archive[2048], output[2048], first[2048], second[2048];
    capture state;
    xfu_request request;
    size_t i;
    CHECK(make_path(archive, sizeof(archive), fixtures, "legacy_members_only.arc"));
    CHECK(make_path(output, sizeof(output), temporary, "existing-encrypted-output"));
    CHECK(xx_io_create_dirs_a(output, true));
    CHECK(make_path(first, sizeof(first), output, "first.txt"));
    CHECK(make_path(second, sizeof(second), output, "second.bin"));
    CHECK(write_text(first, sentinel) && write_text(second, sentinel));
    for (i = 0; i < sizeof(passwords) / sizeof(passwords[0]); ++i) {
        CHECK(expect_read(archive, XX_FILE_TYPE_FREEARC, XFU_COMMAND_EXTRACT,
            passwords[i], false, i ? XFU_ENCRYPTION_PASSWORD_REJECTED : XFU_ENCRYPTION_PASSWORD_REQUIRED,
            2, true, false, output) == 0);
        CHECK(has_text(first, sentinel) && has_text(second, sentinel));
    }
    /* Cancelling after an encrypted entry is announced must not turn the
     * interruption into a password failure, even when output already exists. */
    request = request_for(&state, XFU_COMMAND_EXTRACT, archive, XX_FILE_TYPE_FREEARC, NULL);
    {
        xx_pd_struct pd = xx_pd_init();
        state.cancel_on_entry = true;
        state.progress = &pd;
        request.progress_state = &pd;
        request.output_dir = output;
        CHECK(xfu_run(&request) != 0);
        CHECK(state.required == 0 && state.rejected == 0);
        CHECK(has_text(first, sentinel) && has_text(second, sentinel));
    }
    /* A real destination error stays a filesystem failure. Give the correct
     * password, but put a directory where the first file must be written. */
    CHECK(make_path(output, sizeof(output), temporary, "blocked-encrypted-output"));
    CHECK(xx_io_create_dirs_a(output, true));
    CHECK(make_path(first, sizeof(first), output, "first.txt"));
    CHECK(xx_io_create_dirs_a(first, true));
    request = request_for(&state, XFU_COMMAND_EXTRACT, archive, XX_FILE_TYPE_FREEARC, fixture_password);
    request.output_dir = output;
    CHECK(xfu_run(&request) != 0);
    CHECK(state.detected > 0 && state.required == 0 && state.rejected == 0);
    CHECK(!state.invalid_status && !state.leaked_credential);
    return 0;
}

int main(int argc, char **argv) {
    char temporary[2048];
    capture unique;
    int length;
    CHECK(argc == 3);
    CHECK(xx_io_create_dirs_a(argv[2], true));
    length = snprintf(temporary, sizeof(temporary), "%s/run-%lu-%p", argv[2],
                      (unsigned long)time(NULL), (void *)&unique);
    CHECK(length >= 0 && (size_t)length < sizeof(temporary));
    CHECK(xx_io_create_dirs_a(temporary, true));
    CHECK(freearc_checks(argv[1], temporary) == 0);
    CHECK(native_archive_checks(temporary) == 0);
    CHECK(ordinary_failure_checks(argv[1], temporary) == 0);
    CHECK(existing_output_checks(argv[1], temporary) == 0);
    puts("engine encryption notifications and member flags passed");
    return 0;
}
