/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#ifndef XFILEUNPACKER_UI_H
#define XFILEUNPACKER_UI_H

#include <xxwidgets/xxwidgets.h>

/* Both frontends share the same C controller and xxwidgets archive browser. */
int xfu_ui_run(int argc, char **argv, xxwidgets_backend backend);

#ifdef _WIN32
/* Convert the actual Unicode Windows command line, including argv[0]. */
int xfu_ui_windows_arguments(int *argc, char ***argv);
void xfu_ui_free_arguments(int argc, char **argv);
#endif

#endif
