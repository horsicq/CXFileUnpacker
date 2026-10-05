/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "core.h"
#include "supported_types.h"
#include <xxfclib/formats/hxc_raw_floppy/xx_hxc_raw_floppy.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <shellapi.h>
#include <xxfclib/strings/xx_string.h>
#else
#include <unistd.h>
#endif

typedef struct console_test {
    xx_pd_struct progress;
    int last_percent;
    bool verbose, terminal, line_open, output_failed;
} console_test;

static bool console_is_terminal(void) {
#ifdef _WIN32
    DWORD mode;
    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    return output != INVALID_HANDLE_VALUE && GetConsoleMode(output, &mode) != 0;
#else
    return isatty(STDOUT_FILENO) != 0;
#endif
}

static void test_output_failed(console_test *test) {
    test->output_failed = true;
    xx_pd_stop(&test->progress);
}

static void test_finish_line(console_test *test) {
    if (test->line_open) {
        test->line_open = false;
        if (fputc('\n', stdout) == EOF || fflush(stdout) == EOF)
            test_output_failed(test);
    }
}

static void test_log(void *user, bool error, const char *line) {
    console_test *test = (console_test *)user;
    if (!error || test->output_failed) return;
    test_finish_line(test);
    if (fprintf(stderr, "%s\n", line) < 0 || fflush(stderr) == EOF)
        test_output_failed(test);
}

static void test_progress(void *user, unsigned percent) {
    console_test *test = (console_test *)user;
    if (test->verbose || test->output_failed) return;
    if (percent > 100U) percent = 100U;
    if ((int)percent <= test->last_percent) return;
    test->last_percent = (int)percent;
    if (fprintf(stdout, test->terminal ? "\r%3u%%" : "%u%%\n", percent) < 0 ||
        fflush(stdout) == EOF) {
        test_output_failed(test);
        return;
    }
    test->line_open = test->terminal;
}

static void test_result(void *user, const xfu_entry *entry, bool success) {
    console_test *test = (console_test *)user;
    /* Installing this callback also suppresses the core's member log in the
     * percentage-only mode. No member name is printed in that mode. */
    if (!test->verbose || test->output_failed) return;
    if (fprintf(stdout, "%s -- %s\n", entry->name, success ? "OK" : "FAILED") < 0 ||
        fflush(stdout) == EOF) test_output_failed(test);
}

static void usage(FILE *out, const char *program) {
    fprintf(out,
            "xfu -- unpack archives with xxfclib\n"
            "\n"
            "Usage: %s <command> <archive> [arguments]\n"
            "\n"
            "Commands (7-Zip letters):\n"
            "  x <archive> [-o<dir>]     Extract with full paths\n"
            "  l <archive> [--advanced]  List contents and optional metadata\n"
            "  p <archive>              Retrieve verified embedded passwords\n"
            "  t <archive> [--verbose]  Test in memory; percentage or member results\n"
            "  a <archive> <file>...     Add files to a new archive\n"
            "  i                         Show all supported file types\n"
            "\n"
            "Options:\n"
            "  -o<dir>   Output directory for x (default: the current directory)\n"
            "  --advanced, -slt  Show all available metadata for each listed file\n"
            "  --verbose, -v  Show each member's OK/FAILED result for t\n"
            "  --reader <name>  Select a validated reader; raw images use hxc-raw:PROFILE\n"
            "  --get-password <archive>  Retrieve embedded passwords (same as p)\n"
            "  l <archive> --get-password  Retrieve instead of listing; conflicts with --advanced\n"
            "  -p<password>  Password for x, l, t, p or a (.7z/.zip) (empty password: -p)\n"
            "  --password-env=<name>  Read the password from an environment variable\n"
            "  --compression=stored|xpress|lzx|lzms  WIM creation method (default: xpress)\n"
            "  --compression-level=0..100  WIM level; 0 uses the compressor default\n"
            "  --formats List all supported file types (same as i; no archive needed)\n"
            "  --raw-profiles  List explicit HxC raw-image geometries\n"
            "  --color=auto|always|never  Colors for the file type list (default: auto)\n"
            "\n"
            "Notes:\n"
            "  `a` writes the container the archive's extension names, and only\n"
            "  the formats xxfclib can write: .tar .tar.gz .tar.bz2 .tar.xz\n"
            "  .tar.zst .tar.lz4 .zip .cpio .7z .gz .bz2 .xz .wim\n", program);
}

static void console_log(void *user, bool error, const char *line) {
    (void)user;
    fprintf(error ? stderr : stdout, "%s\n", line);
}

static void console_advanced_entry(void *user, const xfu_entry *entry) {
    size_t i;
    (void)user;
    fprintf(stdout, "    Type: %s\n", entry->is_directory ? "Directory" : "File");
    if (entry->packed_size >= 0) fprintf(stdout, "    Packed size: %lld\n", (long long)entry->packed_size);
    else fputs("    Packed size: unknown\n", stdout);
    if (entry->unpacked_size >= 0) fprintf(stdout, "    Unpacked size: %lld\n", (long long)entry->unpacked_size);
    else fputs("    Unpacked size: unknown\n", stdout);
    fprintf(stdout, "    Modified: %s\n", entry->modified[0] ? entry->modified : "unknown");
    fprintf(stdout, "    Attributes: %s\n", entry->attributes[0] ? entry->attributes : "unknown");
    for (i = 0; i < entry->property_count; ++i)
        fprintf(stdout, "    %s: %s\n", entry->properties[i].name, entry->properties[i].value);
}

typedef struct password_group {
    char *raw;
    char *display;
    size_t members;
} password_group;

typedef struct password_retrieval {
    password_group *groups;
    size_t count, capacity;
    int failed;
    xx_pd_struct progress;
} password_retrieval;

static void wipe_password(char *password) {
    if (password) {
        volatile char *byte = password;
        size_t size = strlen(password) + 1U;
        while (size--) *byte++ = 0;
        free(password);
    }
}

static void retrieval_cleanup(password_retrieval *retrieval) {
    size_t i;
    for (i = 0; i < retrieval->count; ++i) {
        wipe_password(retrieval->groups[i].raw);
        wipe_password(retrieval->groups[i].display);
    }
    free(retrieval->groups);
    memset(retrieval, 0, sizeof(*retrieval));
}

/* Password metadata already escapes ASCII controls and literal backslashes.
 * Preserve that reversible text, while escaping any remaining invalid UTF-8
 * bytes or Unicode C1 controls so the summary is safe single-line output. */
static char *retrieval_display(const char *property) {
    static const char digits[] = "0123456789ABCDEF";
    size_t size = strlen(property), i = 0, used = 0;
    char *text;
    if (size > (SIZE_MAX - 1U) / 4U) return NULL;
    text = (char *)malloc(size * 4U + 1U);
    if (!text) return NULL;
    while (i < size) {
        unsigned char c = (unsigned char)property[i];
        size_t length = 0, j;
        if (c >= 0x20U && c < 0x7fU) length = 1;
        else if (c >= 0xc2U && c <= 0xdfU) length = 2;
        else if (c >= 0xe0U && c <= 0xefU) length = 3;
        else if (c >= 0xf0U && c <= 0xf4U) length = 4;
        if (length > size - i) length = 0;
        for (j = 1; j < length; ++j)
            if (((unsigned char)property[i + j] & 0xc0U) != 0x80U) {
                length = 0; break;
            }
        if (length > 1) {
            unsigned char second = (unsigned char)property[i + 1];
            if ((c == 0xc2U && second < 0xa0U) ||
                (c == 0xe0U && second < 0xa0U) ||
                (c == 0xedU && second >= 0xa0U) ||
                (c == 0xf0U && second < 0x90U) ||
                (c == 0xf4U && second >= 0x90U)) length = 0;
        }
        if (length) {
            memcpy(text + used, property + i, length);
            used += length; i += length;
        } else {
            text[used++] = '\\'; text[used++] = 'x';
            text[used++] = digits[c >> 4]; text[used++] = digits[c & 15U];
            ++i;
        }
    }
    text[used] = 0;
    return text;
}

static void retrieval_fail(password_retrieval *retrieval, int reason) {
    retrieval->failed = reason;
    xx_pd_stop(&retrieval->progress);
}

static void retrieval_log(void *user, bool error, const char *line) {
    password_retrieval *retrieval = (password_retrieval *)user;
    if (error && fprintf(stderr, "%s\n", line) < 0) retrieval_fail(retrieval, 2);
}

static void retrieval_entry(void *user, const xfu_entry *entry) {
    password_retrieval *retrieval = (password_retrieval *)user;
    const char *property = NULL;
    char *raw, *display;
    size_t i, size;
    if (retrieval->failed || !entry->embedded_password) return;
    for (i = 0; i < retrieval->count; ++i) {
        if (!strcmp(retrieval->groups[i].raw, entry->embedded_password)) {
            if (retrieval->groups[i].members == SIZE_MAX) retrieval_fail(retrieval, 1);
            else ++retrieval->groups[i].members;
            return;
        }
    }
    for (i = 0; i < entry->property_count; ++i)
        if (!strcmp(entry->properties[i].name, "Password")) {
            property = entry->properties[i].value;
            break;
        }
    if (!property) { retrieval_fail(retrieval, 3); return; }
    size = strlen(entry->embedded_password);
    if (size == SIZE_MAX) { retrieval_fail(retrieval, 1); return; }
    raw = (char *)malloc(size + 1U);
    if (raw) memcpy(raw, entry->embedded_password, size + 1U);
    display = retrieval_display(property);
    if (!raw || !display) {
        wipe_password(raw); wipe_password(display); retrieval_fail(retrieval, 1); return;
    }
    if (retrieval->count == retrieval->capacity) {
        size_t capacity = retrieval->capacity ? retrieval->capacity * 2U : 4U;
        password_group *grown;
        if (capacity < retrieval->capacity || capacity > SIZE_MAX / sizeof(*grown)) {
            wipe_password(raw); wipe_password(display); retrieval_fail(retrieval, 1); return;
        }
        grown = (password_group *)realloc(retrieval->groups, capacity * sizeof(*grown));
        if (!grown) {
            wipe_password(raw); wipe_password(display); retrieval_fail(retrieval, 1); return;
        }
        retrieval->groups = grown;
        retrieval->capacity = capacity;
    }
    retrieval->groups[retrieval->count].raw = raw;
    retrieval->groups[retrieval->count].display = display;
    retrieval->groups[retrieval->count++].members = 1;
}

static int retrieval_result(password_retrieval *retrieval, int status) {
    size_t i;
    if (fflush(stderr) == EOF || ferror(stderr)) return 2;
    if (retrieval->failed) {
        fprintf(stderr, "%s\n", retrieval->failed == 1 ?
                "cannot allocate recovered password summary" : retrieval->failed == 2 ?
                "cannot write password diagnostics" : "recovered password display is unavailable");
        return 2;
    }
    if (status == 2) return 2;
    if (!retrieval->count) {
        if (fputs("No embedded password found.\n", stdout) == EOF ||
            fflush(stdout) == EOF || ferror(stdout)) return 2;
        return 1;
    }
    for (i = 0; i < retrieval->count; ++i) {
        if ((i && fputc('\n', stdout) == EOF) ||
            fprintf(stdout, "Password: %s\nMembers: %zu\n",
                    retrieval->groups[i].display, retrieval->groups[i].members) < 0)
            return 2;
    }
    return fflush(stdout) == EOF || ferror(stdout) ? 2 : 0;
}

static int show_supported_types(int argc, char **argv)
{
    char *text, *rows;
    int i, color = 0, ansi = 0, mode = 0, result;
#ifdef _WIN32
    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD original_mode = 0;
    CONSOLE_SCREEN_BUFFER_INFO info = {0};
    int console = GetConsoleMode(output, &original_mode) && GetConsoleScreenBufferInfo(output, &info);
#endif
    for (i = 2; i < argc; ++i) {
        if (!strcmp(argv[i], "--color=auto")) mode = 0;
        else if (!strcmp(argv[i], "--color=always")) mode = 1;
        else if (!strcmp(argv[i], "--color=never")) mode = 2;
        else { fprintf(stderr, "unexpected argument: %s\n", argv[i]); return 2; }
    }
    text = xfu_supported_types_text(NULL);
    if (!text) { fprintf(stderr, "cannot allocate supported file type list\n"); return 2; }
    if (mode != 2 && (mode == 1 || !getenv("NO_COLOR"))) {
#ifdef _WIN32
        color = console || mode == 1;
        if (console) ansi = SetConsoleMode(output, original_mode | ENABLE_VIRTUAL_TERMINAL_PROCESSING) != 0;
        else ansi = mode == 1;
#else
        color = mode == 1 || isatty(STDOUT_FILENO);
        ansi = color;
#endif
    }
    rows = strstr(text, "   ID  File type\n");
    if (rows) rows += strlen("   ID  File type\n");
    if (color && ansi) fputs("\033[1;36m", stdout);
#ifdef _WIN32
    if (color && !ansi) { fflush(stdout); SetConsoleTextAttribute(output, FOREGROUND_GREEN | FOREGROUND_BLUE | FOREGROUND_INTENSITY); }
#endif
    if (rows) {
        fwrite(text, 1, (size_t)(rows - text), stdout);
        if (color && ansi) fputs("\033[0;32m", stdout);
#ifdef _WIN32
        if (color && !ansi) { fflush(stdout); SetConsoleTextAttribute(output, FOREGROUND_GREEN | FOREGROUND_INTENSITY); }
#endif
        fputs(rows, stdout);
    } else fputs(text, stdout);
    if (color && ansi) fputs("\033[0m", stdout);
    fflush(stdout);
#ifdef _WIN32
    if (console) {
        if (ansi) SetConsoleMode(output, original_mode);
        else if (color) SetConsoleTextAttribute(output, info.wAttributes);
    }
#endif
    result = ferror(stdout) ? 2 : 0;
    free(text);
    return result;
}

static int run_cli(int argc, char **argv) {
    xfu_request request = {0};
    const char **files = NULL;
    bool literal_files = false;
    bool get_password = false;
    bool verbose_test = false;
    console_test test = {0};
    password_retrieval retrieval = {0};
    char *environment_password = NULL;
    int i, result;

    if (argc >= 2 && (!strcmp(argv[1], "--formats") || !strcmp(argv[1], "i")))
        return show_supported_types(argc, argv);
    if (argc >= 2 && !strcmp(argv[1], "--raw-profiles")) {
        size_t index;
        if (argc != 2) { fprintf(stderr, "--raw-profiles takes no arguments\n"); return 2; }
        for (index=0; index<xx_hxc_raw_floppy_profile_count(); ++index) {
            const xx_hxc_raw_profile *profile=xx_hxc_raw_floppy_profile_at(index);
            printf("hxc-raw:%s\t%llu bytes\t%u cylinders\t%u heads\n",profile->name,
                   (unsigned long long)profile->source_size,(unsigned)profile->tracks,(unsigned)profile->sides);
        }
        return ferror(stdout) ? 2 : 0;
    }

    if (argc == 1 || (argc == 2 &&
        (strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0))) {
        usage(stdout, argv[0]);
        return 0;
    }
    if (argc < 3) {
        usage(stderr, argv[0]);
        return 2;
    }
    get_password = !strcmp(argv[1], "--get-password") ||
                   !strcmp(argv[1], "p") || !strcmp(argv[1], "P");
    request.command = get_password ? XFU_COMMAND_LIST : xfu_parse_command(argv[1]);
    if (request.command == XFU_COMMAND_NONE) {
        fprintf(stderr, "unknown command: %s\n\n", argv[1]);
        usage(stderr, argv[0]);
        return 2;
    }
    request.archive_path = argv[2];
    request.callbacks.log = console_log;
    if (request.command == XFU_COMMAND_ADD) {
        files = (const char **)calloc((size_t)argc, sizeof(*files));
        if (!files) {
            fprintf(stderr, "cannot allocate file arguments\n");
            return 2;
        }
        request.files = files;
    }
    for (i = 3; i < argc; ++i) {
        if (!literal_files && (strncmp(argv[i], "-p", 2) == 0 ||
                   strncmp(argv[i], "--password-env=", 15) == 0)) {
            if (request.password) {
                fprintf(stderr, "password specified more than once\n");
                result = 2;
                goto cleanup;
            }
            if (strncmp(argv[i], "-p", 2) == 0) request.password = argv[i] + 2;
            else {
                const char *name = argv[i] + 15;
                if (!*name) { fprintf(stderr, "name a password environment variable\n"); result = 2; goto cleanup; }
#ifdef _WIN32
                wchar_t *wide_name = xx_str_utf8_to_unicode(name);
                wchar_t *wide_value;
                char *utf8_value;
                DWORD needed, copied;
                if (!wide_name) { fprintf(stderr, "cannot allocate environment variable name\n"); result = 2; goto cleanup; }
                SetLastError(ERROR_SUCCESS);
                needed = GetEnvironmentVariableW(wide_name, NULL, 0);
                if (!needed && GetLastError() != ERROR_SUCCESS) {
                    xx_str_wfree(wide_name);
                    fprintf(stderr, "password environment variable is not set\n");
                    result = 2; goto cleanup;
                }
                wide_value = (wchar_t *)calloc(needed ? needed : 1, sizeof(wchar_t));
                SetLastError(ERROR_SUCCESS);
                copied = wide_value && needed ? GetEnvironmentVariableW(wide_name, wide_value, needed) : 0;
                if (!wide_value || copied >= (needed ? needed : 1) ||
                    (!copied && GetLastError() != ERROR_SUCCESS)) {
                    xx_str_wfree(wide_name); free(wide_value);
                    fprintf(stderr, "cannot read password environment variable\n");
                    result = 2; goto cleanup;
                }
                xx_str_wfree(wide_name);
                utf8_value = xx_str_unicode_to_utf8(wide_value);
                SecureZeroMemory(wide_value, (needed ? needed : 1) * sizeof(wchar_t));
                free(wide_value);
                if (utf8_value) {
                    size_t length = strlen(utf8_value);
                    environment_password = (char *)malloc(length + 1);
                    if (environment_password) memcpy(environment_password, utf8_value, length + 1);
                    SecureZeroMemory(utf8_value, length);
                    xx_str_free(utf8_value);
                }
#else
                const char *value = getenv(name);
                if (!value) { fprintf(stderr, "password environment variable is not set\n"); result = 2; goto cleanup; }
                environment_password = (char *)malloc(strlen(value) + 1);
                if (environment_password) strcpy(environment_password, value);
#endif
                if (!environment_password) { fprintf(stderr, "cannot allocate password\n"); result = 2; goto cleanup; }
                request.password = environment_password;
            }

        } else if (request.command == XFU_COMMAND_ADD) {
            if (!literal_files && (!strcmp(argv[i], "--compression") || !strncmp(argv[i], "--compression=", 14))) {
                const char *value = argv[i][13] == '=' ? argv[i] + 14 : (++i < argc ? argv[i] : NULL);
                if (request.compression_method || !value || !*value || value[0] == '-') {
                    fprintf(stderr, "--compression: specify one WIM method (stored, xpress, lzx, lzms)\n"); result = 2; goto cleanup;
                }
                request.compression_method = value; continue;
            }
            if (!literal_files && (!strcmp(argv[i], "--compression-level") || !strncmp(argv[i], "--compression-level=", 20))) {
                const char *value = argv[i][19] == '=' ? argv[i] + 20 : (++i < argc ? argv[i] : NULL);
                const char *p = value;
                int level = 0;
                if (request.compression_level_set || !p || !*p) {
                    fprintf(stderr, "--compression-level: specify one number from 0 to 100\n"); result = 2; goto cleanup;
                }
                while (*p) {
                    if (*p < '0' || *p > '9' || level > 100) break;
                    level = level * 10 + *p++ - '0';
                }
                if (*p || level > 100) {
                    fprintf(stderr, "--compression-level: expected 0..100\n"); result = 2; goto cleanup;
                }
                request.compression_level = level; request.compression_level_set = true; continue;
            }
            if (!literal_files && strcmp(argv[i], "--") == 0) {
                literal_files = true;
                continue;
            }
            if (!literal_files && argv[i][0] == '-') {
                fprintf(stderr, "unknown option: %s\n", argv[i]);
                result = 2;
                goto cleanup;
            }
            files[request.file_count++] = argv[i];
        } else if (request.command == XFU_COMMAND_TEST &&
                   (!strcmp(argv[i], "--verbose") || !strcmp(argv[i], "-v"))) {
            if (verbose_test) {
                fprintf(stderr, "verbose testing specified more than once\n");
                result = 2;
                goto cleanup;
            }
            verbose_test = true;
        } else if (!strcmp(argv[i], "--reader") || !strncmp(argv[i], "--reader=", 9)) {
            const char *name = argv[i][8] == '=' ? argv[i] + 9 : (++i < argc ? argv[i] : NULL);
            if (request.reader_name || !name || !name[0] || name[0] == '-') {
                fprintf(stderr, "--reader: specify one reader name\n"); result = 2; goto cleanup;
            }
            request.reader_name = name;
        } else if (!strcmp(argv[i], "--get-password")) {
            if (request.command != XFU_COMMAND_LIST || get_password || request.callbacks.entry) {
                fprintf(stderr, "%s\n", request.command != XFU_COMMAND_LIST ?
                        "--get-password requires l or p" : get_password ?
                        "password retrieval specified more than once" :
                        "--get-password cannot be combined with --advanced or -slt");
                result = 2;
                goto cleanup;
            }
            get_password = true;
        } else if (request.command == XFU_COMMAND_LIST &&
                   (!strcmp(argv[i], "--advanced") || !strcmp(argv[i], "-slt"))) {
            if (get_password) {
                fprintf(stderr, "--get-password cannot be combined with --advanced or -slt\n");
                result = 2;
                goto cleanup;
            }
            if (request.callbacks.entry) {
                fprintf(stderr, "advanced listing specified more than once\n");
                result = 2;
                goto cleanup;
            }
            request.callbacks.entry = console_advanced_entry;
        } else if (request.command == XFU_COMMAND_EXTRACT &&
                   strncmp(argv[i], "-o", 2) == 0) {
            if (!argv[i][2]) {
                fprintf(stderr, "-o: name an output directory\n");
                result = 2;
                goto cleanup;
            }
            if (request.output_dir) {
                fprintf(stderr, "-o: output directory specified more than once\n");
                result = 2;
                goto cleanup;
            }
            request.output_dir = argv[i] + 2;
        } else {
            fprintf(stderr, "%s: %s\n", argv[i][0] == '-' ?
                    "unknown option" : "unexpected argument", argv[i]);
            result = 2;
            goto cleanup;
        }
    }
    if (get_password) {
        retrieval.progress = xx_pd_init();
        request.progress_state = &retrieval.progress;
        request.callbacks.user = &retrieval;
        request.callbacks.log = retrieval_log;
        request.callbacks.entry = retrieval_entry;
    } else if (request.command == XFU_COMMAND_TEST) {
        test.progress = xx_pd_init();
        test.last_percent = -1;
        test.verbose = verbose_test;
        test.terminal = console_is_terminal();
        request.progress_state = &test.progress;
        request.callbacks.user = &test;
        request.callbacks.log = test_log;
        request.callbacks.test_progress = test_progress;
        request.callbacks.test_result = test_result;
    }
    result = xfu_run(&request);
    if (get_password) result = retrieval_result(&retrieval, result);
    else if (request.command == XFU_COMMAND_TEST) {
        test_finish_line(&test);
        if (fflush(stdout) == EOF || fflush(stderr) == EOF ||
            ferror(stdout) || ferror(stderr)) test_output_failed(&test);
        if (test.output_failed) result = 2;
    }
cleanup:
    retrieval_cleanup(&retrieval);
    if (environment_password) {
        volatile char *wipe = environment_password;
        size_t size = strlen(environment_password);
        while (size--) *wipe++ = 0;
        free(environment_password);
    }
    free(files);
    return result;
}

int main(int argc, char **argv) {
#ifdef _WIN32
    wchar_t **wide;
    char **utf8;
    int count = 0, i, result;
    (void)argc;
    (void)argv;
    SetConsoleOutputCP(CP_UTF8);
    wide = CommandLineToArgvW(GetCommandLineW(), &count);
    if (!wide) {
        fprintf(stderr, "cannot read command line\n");
        return 2;
    }
    utf8 = (char **)calloc((size_t)count + 1, sizeof(*utf8));
    if (!utf8) {
        LocalFree(wide);
        fprintf(stderr, "cannot allocate command line\n");
        return 2;
    }
    for (i = 0; i < count; ++i) {
        utf8[i] = xx_str_unicode_to_utf8(wide[i]);
        if (!utf8[i]) break;
    }
    LocalFree(wide);
    if (i == count) result = run_cli(count, utf8);
    else {
        fprintf(stderr, "cannot convert command line to UTF-8\n");
        result = 2;
    }
    for (i = 0; i < count; ++i) xx_str_free(utf8[i]);
    free(utf8);
    return result;
#else
    return run_cli(argc, argv);
#endif
}
