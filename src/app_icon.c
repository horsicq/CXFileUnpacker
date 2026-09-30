/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "app_icon.h"
#ifdef _WIN32
#include <windows.h>
void xfu_set_application_icon(xxwidgets_widget *window) {
    HWND handle = (HWND)xxwidgets_widget_native_handle(window);
    HINSTANCE instance = GetModuleHandleW(NULL);
    HICON large = (HICON)LoadImageW(instance, MAKEINTRESOURCEW(101), IMAGE_ICON,
        GetSystemMetrics(SM_CXICON), GetSystemMetrics(SM_CYICON), LR_SHARED);
    HICON small = (HICON)LoadImageW(instance, MAKEINTRESOURCEW(101), IMAGE_ICON,
        GetSystemMetrics(SM_CXSMICON), GetSystemMetrics(SM_CYSMICON), LR_SHARED);
    if (large) SendMessageW(handle, WM_SETICON, ICON_BIG, (LPARAM)large);
    if (small) SendMessageW(handle, WM_SETICON, ICON_SMALL, (LPARAM)small);
}
#elif defined(XFU_GTK)
#include <gtk/gtk.h>
#include <unistd.h>
#include <string.h>
void xfu_set_application_icon(xxwidgets_widget *window) {
    GtkWindow *handle = GTK_WINDOW(xxwidgets_widget_native_handle(window));
    char executable[4096];
    ssize_t length;
    gtk_window_set_icon_name(handle, "xfileunpacker");
    gtk_window_set_wmclass(handle, "XFileUnpacker", "XFileUnpacker");
    /* Build-tree/portable launch; installed launchers use the icon theme. */
    length = readlink("/proc/self/exe", executable, sizeof(executable) - 1);
    if (length > 0) {
        char *slash;
        executable[length] = 0;
        slash = strrchr(executable, '/');
        if (slash && (size_t)(slash - executable) + sizeof("/xfileunpacker.png") <= sizeof(executable)) {
            strcpy(slash, "/xfileunpacker.png");
            if (access(executable, R_OK) == 0) gtk_window_set_icon_from_file(handle, executable, NULL);
        }
    }
}
#else
void xfu_set_application_icon(xxwidgets_widget *window) { (void)window; }
#endif
