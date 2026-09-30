/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "ui.h"

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous,
                    PWSTR command_line, int show_command)
{
    int argc = 0, result;
    char **argv = NULL;
    (void)instance; (void)previous; (void)command_line; (void)show_command;
    if (!xfu_ui_windows_arguments(&argc, &argv)) {
        MessageBoxW(NULL, L"Cannot read the command line.", L"XFileUnpacker", MB_OK | MB_ICONERROR);
        return 2;
    }
    result = xfu_ui_run(argc, argv, XXWIDGETS_BACKEND_NATIVE);
    xfu_ui_free_arguments(argc, argv);
    return result;
}
#else
int main(int argc, char **argv)
{
    return xfu_ui_run(argc, argv, XXWIDGETS_BACKEND_NATIVE);
}
#endif
