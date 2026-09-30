/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "ui.h"

int main(int argc, char **argv)
{
#ifdef _WIN32
    int unicode_argc = 0, result;
    char **unicode_argv = NULL;
    (void)argc; (void)argv;
    if (!xfu_ui_windows_arguments(&unicode_argc, &unicode_argv)) return 2;
    result = xfu_ui_run(unicode_argc, unicode_argv, XXWIDGETS_BACKEND_TUI);
    xfu_ui_free_arguments(unicode_argc, unicode_argv);
    return result;
#else
    return xfu_ui_run(argc, argv, XXWIDGETS_BACKEND_TUI);
#endif
}
