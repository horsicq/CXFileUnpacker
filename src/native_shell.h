#ifndef XFILEUNPACKER_NATIVE_SHELL_H
#define XFILEUNPACKER_NATIVE_SHELL_H

#include <xxwidgets/xxwidgets.h>

typedef struct xfu_native_shell xfu_native_shell;
typedef enum xfu_shell_action {
    XFU_SHELL_OPEN = 1, XFU_SHELL_ADD, XFU_SHELL_EXTRACT, XFU_SHELL_TEST,
    XFU_SHELL_COPY, XFU_SHELL_INFO, XFU_SHELL_LOG, XFU_SHELL_CANCEL,
    XFU_SHELL_QUIT, XFU_SHELL_ROOT, XFU_SHELL_REFRESH, XFU_SHELL_ABOUT,
    XFU_SHELL_OPEN_PATH, XFU_SHELL_ENTER_FOLDER, XFU_SHELL_UP, XFU_SHELL_OPTIONS,
    XFU_SHELL_EXTRACT_SELECTED, XFU_SHELL_FORMATS
} xfu_shell_action;
typedef struct xfu_shell_button {
    xxwidgets_widget *widget;
    xfu_shell_action action;
} xfu_shell_button;
typedef void (*xfu_shell_callback)(void *user, xfu_shell_action action, const char *path);

int xfu_native_shell_attach(xxwidgets_widget *window, const xfu_shell_button *buttons,
    size_t count, xfu_shell_callback callback, void *user, xfu_native_shell **out_shell);
void xfu_native_shell_set_busy(xfu_native_shell *shell, int busy);
void xfu_native_shell_set_archive_enabled(xfu_native_shell *shell, int enabled);
int xfu_native_shell_archive_menu(xfu_native_shell *shell, xxwidgets_widget *browser,
    int x, int y, int busy);
void xfu_native_shell_destroy(xfu_native_shell *shell);
/* Resizable, scrollable read-only record information with selectable text. */
void xfu_native_shell_information(xxwidgets_widget *window, const char *text);

#endif
