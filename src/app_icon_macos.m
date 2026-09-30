/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "app_icon.h"
#import <AppKit/AppKit.h>
void xfu_set_application_icon(xxwidgets_widget *window) {
    (void)window;
    NSString *path = [[NSBundle mainBundle] pathForResource:@"xfileunpacker" ofType:@"icns"];
    NSImage *icon = path ? [[NSImage alloc] initWithContentsOfFile:path] : nil;
    if (icon) { [NSApp setApplicationIconImage:icon]; [icon release]; }
}
