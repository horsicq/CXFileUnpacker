/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "core.h"
#include "supported_types.h"

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

static void usage(FILE *out, const char *program) {
    fprintf(out,
            "xfu -- unpack archives with xxfclib\n"
            "\n"
            "Usage: %s <command> <archive> [arguments]\n"
            "\n"
            "Commands (7-Zip letters):\n"
            "  x <archive> [-o<dir>]     Extract with full paths\n"
            "  l <archive>               List contents\n"
            "  t <archive>               Test: extract to a scratch dir, then discard\n"
            "  a <archive> <file>...     Add files to a new archive\n"
            "  i                         Show all supported file types\n"
            "\n"
            "Options:\n"
            "  -o<dir>   Output directory for x (default: the current directory)\n"
            "  --formats List all supported file types (same as i; no archive needed)\n"
            "  --color=auto|always|never  Colors for the file type list (default: auto)\n"
            "\n"
            "Notes:\n"
            "  `a` writes the container the archive's extension names, and only\n"
            "  the formats xxfclib can write: .tar .tar.gz .tar.bz2 .tar.xz\n"
            "  .tar.zst .tar.lz4 .zip .cpio\n", program);
}

static void console_log(void *user, bool error, const char *line) {
    (void)user;
    fprintf(error ? stderr : stdout, "%s\n", line);
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
    int i, result;

    if (argc >= 2 && (!strcmp(argv[1], "--formats") || !strcmp(argv[1], "i")))
        return show_supported_types(argc, argv);

    if (argc == 1 || (argc == 2 &&
        (strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0))) {
        usage(stdout, argv[0]);
        return 0;
    }
    if (argc < 3) {
        usage(stderr, argv[0]);
        return 2;
    }
    request.command = xfu_parse_command(argv[1]);
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
        if (request.command == XFU_COMMAND_ADD) {
            if (!literal_files && strcmp(argv[i], "--") == 0) {
                literal_files = true;
                continue;
            }
            if (!literal_files && argv[i][0] == '-') {
                fprintf(stderr, "unknown option: %s\n", argv[i]);
                free(files);
                return 2;
            }
            files[request.file_count++] = argv[i];
        } else if (request.command == XFU_COMMAND_EXTRACT &&
                   strncmp(argv[i], "-o", 2) == 0) {
            if (!argv[i][2]) {
                fprintf(stderr, "-o: name an output directory\n");
                return 2;
            }
            if (request.output_dir) {
                fprintf(stderr, "-o: output directory specified more than once\n");
                return 2;
            }
            request.output_dir = argv[i] + 2;
        } else {
            fprintf(stderr, "%s: %s\n", argv[i][0] == '-' ?
                    "unknown option" : "unexpected argument", argv[i]);
            return 2;
        }
    }
    result = xfu_run(&request);
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
