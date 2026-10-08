/* Native menu and toolbar presentation for the xxwidgets desktop frontend. */
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <commctrl.h>
#include <shellapi.h>
#include <stdlib.h>
#include <string.h>
#include "native_shell.h"

static void information_layout(HWND dialog)
{
    RECT area;
    GetClientRect(dialog, &area);
    MoveWindow(GetDlgItem(dialog, 100), 10, 10, area.right - 20, area.bottom - 55, TRUE);
    MoveWindow(GetDlgItem(dialog, IDOK), area.right - 90, area.bottom - 35, 80, 25, TRUE);
}

static INT_PTR CALLBACK information_proc(HWND dialog, UINT message, WPARAM wp, LPARAM lp)
{
    if (message == WM_INITDIALOG) {
        HWND edit, button;
        HFONT font = (HFONT)GetStockObject(DEFAULT_GUI_FONT);
        RECT owner, bounds;
        SetWindowTextW(dialog, L"XFileUnpacker - Information");
        SendMessageW(dialog, WM_SETICON, ICON_BIG,
            SendMessageW(GetParent(dialog), WM_GETICON, ICON_BIG, 0));
        SendMessageW(dialog, WM_SETICON, ICON_SMALL,
            SendMessageW(GetParent(dialog), WM_GETICON, ICON_SMALL, 0));
        edit = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", (const wchar_t *)lp,
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_HSCROLL | WS_VSCROLL |
            ES_MULTILINE | ES_READONLY | ES_AUTOHSCROLL | ES_AUTOVSCROLL,
            0, 0, 1, 1, dialog, (HMENU)(INT_PTR)100, GetModuleHandleW(NULL), NULL);
        button = CreateWindowExW(0, L"BUTTON", L"OK", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
            0, 0, 1, 1, dialog, (HMENU)(INT_PTR)IDOK, GetModuleHandleW(NULL), NULL);
        SendMessageW(edit, WM_SETFONT, (WPARAM)font, TRUE);
        SendMessageW(button, WM_SETFONT, (WPARAM)font, TRUE);
        information_layout(dialog);
        if (GetWindowRect(GetParent(dialog), &owner) && GetWindowRect(dialog, &bounds))
            SetWindowPos(dialog, NULL, owner.left + ((owner.right - owner.left) - (bounds.right - bounds.left)) / 2,
                owner.top + ((owner.bottom - owner.top) - (bounds.bottom - bounds.top)) / 2, 0, 0,
                SWP_NOZORDER | SWP_NOSIZE);
        SetFocus(edit);
        return FALSE;
    }
    if (message == WM_SIZE) { information_layout(dialog); return TRUE; }
    if (message == WM_GETMINMAXINFO) {
        MINMAXINFO *limits = (MINMAXINFO *)lp;
        limits->ptMinTrackSize.x = 420; limits->ptMinTrackSize.y = 240;
        return TRUE;
    }
    if (message == WM_CLOSE || (message == WM_COMMAND && (LOWORD(wp) == IDOK || LOWORD(wp) == IDCANCEL))) {
        EndDialog(dialog, IDOK); return TRUE;
    }
    return FALSE;
}

void xfu_native_shell_information(xxwidgets_widget *window, const char *text)
{
    union { DWORD alignment; unsigned char bytes[128]; } storage = {0};
    DLGTEMPLATE *dialog = (DLGTEMPLATE *)storage.bytes;
    int length = MultiByteToWideChar(CP_UTF8, 0, text, -1, NULL, 0), i;
    size_t used = 0;
    wchar_t *wide, *lines;
    if (length <= 0 || (size_t)length > SIZE_MAX / sizeof(wchar_t) / 2) return;
    wide = (wchar_t *)malloc((size_t)length * sizeof(*wide));
    lines = (wchar_t *)malloc((size_t)length * 2 * sizeof(*lines));
    if (!wide || !lines) { free(wide); free(lines); return; }
    MultiByteToWideChar(CP_UTF8, 0, text, -1, wide, length);
    for (i = 0; wide[i]; ++i) {
        if (wide[i] == L'\n' && (!i || wide[i - 1] != L'\r')) lines[used++] = L'\r';
        lines[used++] = wide[i];
    }
    lines[used] = 0;
    dialog->style = WS_POPUP | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | DS_MODALFRAME;
    dialog->cx = 420; dialog->cy = 280;
    DialogBoxIndirectParamW(GetModuleHandleW(NULL), dialog,
        (HWND)xxwidgets_widget_native_handle(window), information_proc, (LPARAM)lines);
    free(wide); free(lines);
}

#define SHELL_MENU_BASE 0x5a00
struct xfu_native_shell {
    HWND window;
    HMENU menu;
    xfu_shell_button buttons[8];
    size_t count;
    xfu_shell_callback callback;
    void *user;
    int busy, archive_enabled;
};

static void segment(HDC dc, int x1, int y1, int x2, int y2)
{
    MoveToEx(dc, x1, y1, NULL); LineTo(dc, x2, y2);
}

static void draw_icon(HDC dc, xfu_shell_action action, int x, int y, int disabled)
{
    COLORREF color = disabled ? GetSysColor(COLOR_GRAYTEXT) : RGB(30, 105, 180);
    HPEN pen, old_pen;
    HBRUSH brush, old_brush;
    if (!disabled) {
        if (action == XFU_SHELL_TEST) color = RGB(20, 145, 70);
        else if (action == XFU_SHELL_OPEN || action == XFU_SHELL_INFO) color = RGB(225, 166, 20);
        else if (action == XFU_SHELL_CANCEL) color = RGB(200, 45, 45);
    }
    pen = CreatePen(PS_SOLID, 2, color);
    brush = CreateSolidBrush(color);
    old_pen = (HPEN)SelectObject(dc, pen);
    old_brush = (HBRUSH)SelectObject(dc, brush);
    switch (action) {
    case XFU_SHELL_OPEN: {
        POINT folder[] = {{x+1,y+6},{x+10,y+6},{x+13,y+9},{x+26,y+9},
                          {x+26,y+23},{x+1,y+23}};
        Polygon(dc, folder, 6);
        SelectObject(dc, GetStockObject(NULL_BRUSH));
        segment(dc,x+3,y+12,x+25,y+12);
        break;
    }
    case XFU_SHELL_EXTRACT:
        Rectangle(dc,x+11,y+2,x+16,y+15);
        { POINT arrow[]={{x+4,y+13},{x+23,y+13},{x+13,y+23}}; Polygon(dc,arrow,3); }
        SelectObject(dc,GetStockObject(NULL_BRUSH));
        segment(dc,x+1,y+20,x+1,y+27); segment(dc,x+1,y+27,x+26,y+27); segment(dc,x+26,y+27,x+26,y+20);
        break;
    case XFU_SHELL_TEST:
        { POINT tick[]={{x+1,y+13},{x+6,y+8},{x+12,y+15},{x+23,y+2},{x+27,y+6},{x+12,y+24}};
          Polygon(dc,tick,6); } break;
    case XFU_SHELL_COPY:
        SelectObject(dc,GetStockObject(NULL_BRUSH));
        Rectangle(dc,x+2,y+2,x+19,y+21); Rectangle(dc,x+9,y+8,x+26,y+27); break;
    case XFU_SHELL_INFO:
        Ellipse(dc,x+1,y+1,x+27,y+27);
        SelectObject(dc,GetStockObject(WHITE_PEN));
        segment(dc,x+14,y+12,x+14,y+23); segment(dc,x+13,y+7,x+15,y+7); break;
    case XFU_SHELL_LOG:
        SelectObject(dc,GetStockObject(NULL_BRUSH));
        Rectangle(dc,x+2,y+1,x+26,y+27);
        segment(dc,x+7,y+7,x+21,y+7); segment(dc,x+7,y+13,x+21,y+13); segment(dc,x+7,y+19,x+21,y+19); break;
    case XFU_SHELL_CANCEL:
        segment(dc,x+4,y+4,x+24,y+24); segment(dc,x+24,y+4,x+4,y+24); break;
    default: break;
    }
    SelectObject(dc,old_brush); SelectObject(dc,old_pen);
    DeleteObject(brush); DeleteObject(pen);
}

static int draw_button(xfu_native_shell *shell, const DRAWITEMSTRUCT *draw)
{
    size_t i;
    for (i=0;i<shell->count;++i) {
        if ((HWND)xxwidgets_widget_native_handle(shell->buttons[i].widget)==draw->hwndItem) {
            RECT area=draw->rcItem, text=area;
            wchar_t label[80];
            HFONT old_font;
            int pressed=(draw->itemState & ODS_SELECTED)!=0;
            FillRect(draw->hDC,&area,GetSysColorBrush(COLOR_BTNFACE));
            if (pressed || (draw->itemState & ODS_FOCUS))
                DrawEdge(draw->hDC,&area,pressed?EDGE_SUNKEN:EDGE_RAISED,BF_RECT);
            draw_icon(draw->hDC,shell->buttons[i].action,
                (area.right-28)/2+pressed,area.top+5+pressed,(draw->itemState & ODS_DISABLED)!=0);
            GetWindowTextW(draw->hwndItem,label,80);
            text.top=area.top+35+pressed; text.bottom=area.bottom-2;
            old_font=(HFONT)SelectObject(draw->hDC,(HFONT)SendMessageW(draw->hwndItem,WM_GETFONT,0,0));
            SetBkMode(draw->hDC,TRANSPARENT);
            SetTextColor(draw->hDC,GetSysColor((draw->itemState & ODS_DISABLED)?COLOR_GRAYTEXT:COLOR_BTNTEXT));
            DrawTextW(draw->hDC,label,-1,&text,DT_CENTER|DT_SINGLELINE|DT_VCENTER);
            if (draw->itemState & ODS_FOCUS) { InflateRect(&area,-3,-3); DrawFocusRect(draw->hDC,&area); }
            SelectObject(draw->hDC,old_font);
            return 1;
        }
    }
    return 0;
}

static LRESULT CALLBACK shell_proc(HWND window, UINT message, WPARAM wp, LPARAM lp,
                                   UINT_PTR subclass, DWORD_PTR reference)
{
    xfu_native_shell *shell=(xfu_native_shell *)reference;
    (void)subclass;
    if (message==WM_DRAWITEM && draw_button(shell,(const DRAWITEMSTRUCT *)lp)) return TRUE;
    if (message==WM_COMMAND && !lp && LOWORD(wp)>SHELL_MENU_BASE && LOWORD(wp)<=SHELL_MENU_BASE+(UINT)XFU_SHELL_FORMATS) {
        shell->callback(shell->user,(xfu_shell_action)(LOWORD(wp)-SHELL_MENU_BASE),NULL); return 0;
    }
    if (message==WM_GETMINMAXINFO) {
        MINMAXINFO *limits=(MINMAXINFO *)lp;
        limits->ptMinTrackSize.x=640; limits->ptMinTrackSize.y=400;
        return 0;
    }
    if (message==WM_DROPFILES) {
        HDROP drop=(HDROP)wp;
        UINT length=DragQueryFileW(drop,0,NULL,0);
        wchar_t *wide=(wchar_t *)malloc(((size_t)length+1)*sizeof(*wide));
        if (wide && DragQueryFileW(drop,0,wide,length+1)) {
            int bytes=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,-1,NULL,0,NULL,NULL);
            char *path=bytes>0?(char *)malloc((size_t)bytes):NULL;
            if (path && WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,-1,path,bytes,NULL,NULL))
                shell->callback(shell->user,XFU_SHELL_OPEN_PATH,path);
            free(path);
        }
        free(wide); DragFinish(drop); return 0;
    }
    return DefSubclassProc(window,message,wp,lp);
}

static void menu_item(HMENU menu, xfu_shell_action action, const wchar_t *label)
{
    AppendMenuW(menu,MF_STRING,SHELL_MENU_BASE+(UINT_PTR)action,label);
}

static void archive_menu_item(HMENU menu, xfu_shell_action action, const wchar_t *label, int enabled)
{
    AppendMenuW(menu,MF_STRING|(enabled?MF_ENABLED:MF_GRAYED),
                SHELL_MENU_BASE+(UINT_PTR)action,label);
}

int xfu_native_shell_archive_menu(xfu_native_shell *shell, xxwidgets_widget *browser,
                                 int x, int y, int busy)
{
    xxwidgets_archive_browser_entry entry;
    const char *archive, *directory;
    size_t source;
    HMENU menu;
    HWND container;
    POINT position;
    UINT command;
    xfu_shell_action default_action;
    int selected, have_archive, inside_folder;
    if (!shell || !browser) return 0;
    container=(HWND)xxwidgets_widget_native_handle(browser);
    if (!container) return 0;
    memset(&entry,0,sizeof(entry));
    selected=xxwidgets_archivebrowser_get_selection(browser,&source,&entry)==XXWIDGETS_OK && entry.path;
    archive=xxwidgets_archivebrowser_archive(browser);
    directory=xxwidgets_archivebrowser_directory(browser);
    have_archive=archive && archive[0] && shell->archive_enabled;
    inside_folder=directory && directory[0];
    menu=CreatePopupMenu();
    if (!menu) return 0;
    if (selected && entry.is_directory) {
        archive_menu_item(menu,XFU_SHELL_ENTER_FOLDER,L"&Open folder",!busy);
        default_action=XFU_SHELL_ENTER_FOLDER;
    } else if (selected) {
        archive_menu_item(menu,XFU_SHELL_INFO,L"&Information",1);
        default_action=XFU_SHELL_INFO;
    } else {
        archive_menu_item(menu,XFU_SHELL_OPEN,L"&Open archive...",!busy);
        default_action=XFU_SHELL_OPEN;
    }
    AppendMenuW(menu,MF_SEPARATOR,0,NULL);
    archive_menu_item(menu,XFU_SHELL_EXTRACT,L"&Extract entire archive...",have_archive && !busy);
    archive_menu_item(menu,XFU_SHELL_EXTRACT_SELECTED,L"Extract only &selected...",
        have_archive && !busy && xxwidgets_archivebrowser_selection_count(browser) > 0);
    archive_menu_item(menu,XFU_SHELL_TEST,L"&Test archive",have_archive && !busy);
    AppendMenuW(menu,MF_SEPARATOR,0,NULL);
    if (selected) archive_menu_item(menu,XFU_SHELL_COPY,L"&Copy member path",1);
    if (!selected || entry.is_directory)
        archive_menu_item(menu,XFU_SHELL_INFO,selected?L"&Information":L"Archive &information",have_archive);
    AppendMenuW(menu,MF_SEPARATOR,0,NULL);
    archive_menu_item(menu,XFU_SHELL_UP,L"&Up",inside_folder && !busy);
    archive_menu_item(menu,XFU_SHELL_ROOT,L"Archive &root",inside_folder && !busy);
    archive_menu_item(menu,XFU_SHELL_REFRESH,L"&Refresh",have_archive && !busy);
    SetMenuDefaultItem(menu,SHELL_MENU_BASE+(UINT)default_action,FALSE);
    position.x=x; position.y=y;
    if (!ClientToScreen(container,&position)) { DestroyMenu(menu); return 0; }
    command=TrackPopupMenuEx(menu,TPM_RETURNCMD|TPM_RIGHTBUTTON|TPM_LEFTALIGN|TPM_TOPALIGN,
                            position.x,position.y,shell->window,NULL);
    DestroyMenu(menu);
    if (command) shell->callback(shell->user,(xfu_shell_action)(command-SHELL_MENU_BASE),NULL);
    return 1;
}

int xfu_native_shell_attach(xxwidgets_widget *window, const xfu_shell_button *buttons,
    size_t count, xfu_shell_callback callback, void *user, xfu_native_shell **out_shell)
{
    xfu_native_shell *shell;
    HMENU file,view,tools,help;
    size_t i;
    if (!window || !buttons || count>8 || !callback || !out_shell) return 0;
    *out_shell=NULL;
    shell=(xfu_native_shell *)calloc(1,sizeof(*shell));
    if (!shell) return 0;
    shell->window=(HWND)xxwidgets_widget_native_handle(window);
    shell->callback=callback; shell->user=user; shell->count=count;
    shell->archive_enabled=1;
    memcpy(shell->buttons,buttons,count*sizeof(*buttons));
    shell->menu=CreateMenu(); file=CreatePopupMenu(); view=CreatePopupMenu(); tools=CreatePopupMenu(); help=CreatePopupMenu();
    if (!shell->menu || !file || !view || !tools || !help) {
        if (file) { DestroyMenu(file); } if (view) { DestroyMenu(view); } if (tools) { DestroyMenu(tools); } if (help) DestroyMenu(help);
        xfu_native_shell_destroy(shell); return 0;
    }
    menu_item(file,XFU_SHELL_OPEN,L"&Open archive...");
    menu_item(file,XFU_SHELL_EXTRACT,L"&Extract archive..."); menu_item(file,XFU_SHELL_TEST,L"&Test archive");
    AppendMenuW(file,MF_SEPARATOR,0,NULL); menu_item(file,XFU_SHELL_QUIT,L"E&xit");
    menu_item(view,XFU_SHELL_ROOT,L"Archive &root"); menu_item(view,XFU_SHELL_REFRESH,L"&Refresh");
    menu_item(view,XFU_SHELL_LOG,L"Operation &log");
    menu_item(tools,XFU_SHELL_COPY,L"&Copy member path"); menu_item(tools,XFU_SHELL_INFO,L"Archive &information");
    menu_item(tools,XFU_SHELL_CANCEL,L"&Cancel operation");
    AppendMenuW(tools,MF_SEPARATOR,0,NULL); menu_item(tools,XFU_SHELL_OPTIONS,L"&Options...");
    EnableMenuItem(tools,SHELL_MENU_BASE+(UINT)XFU_SHELL_CANCEL,MF_BYCOMMAND|MF_GRAYED);
    menu_item(help,XFU_SHELL_FORMATS,L"&Supported file types...");
    AppendMenuW(help,MF_SEPARATOR,0,NULL);
    menu_item(help,XFU_SHELL_ABOUT,L"&About XFileUnpacker...");
    AppendMenuW(shell->menu,MF_POPUP,(UINT_PTR)file,L"&File"); AppendMenuW(shell->menu,MF_POPUP,(UINT_PTR)view,L"&View");
    AppendMenuW(shell->menu,MF_POPUP,(UINT_PTR)tools,L"&Tools"); AppendMenuW(shell->menu,MF_POPUP,(UINT_PTR)help,L"&Help");
    if (!SetWindowSubclass(shell->window,shell_proc,1,(DWORD_PTR)shell) || !SetMenu(shell->window,shell->menu)) {
        xfu_native_shell_destroy(shell); return 0;
    }
    for (i=0;i<count;++i) {
        HWND button=(HWND)xxwidgets_widget_native_handle(buttons[i].widget);
        LONG_PTR style=GetWindowLongPtrW(button,GWL_STYLE);
        SetWindowLongPtrW(button,GWL_STYLE,(style & ~(LONG_PTR)BS_TYPEMASK)|BS_OWNERDRAW);
        InvalidateRect(button,NULL,TRUE);
    }
    DragAcceptFiles(shell->window,TRUE); DrawMenuBar(shell->window);
    *out_shell=shell; return 1;
}

void xfu_native_shell_set_busy(xfu_native_shell *shell, int busy)
{
    static const xfu_shell_action operations[]={XFU_SHELL_OPEN,XFU_SHELL_EXTRACT,XFU_SHELL_TEST,XFU_SHELL_REFRESH,XFU_SHELL_OPTIONS};
    size_t i;
    if (!shell) return;
    shell->busy=busy;
    for (i=0;i<sizeof(operations)/sizeof(operations[0]);++i) {
        int blocked=busy || (!shell->archive_enabled &&
            (operations[i]==XFU_SHELL_EXTRACT || operations[i]==XFU_SHELL_TEST));
        EnableMenuItem(shell->menu,SHELL_MENU_BASE+(UINT)operations[i],MF_BYCOMMAND|(blocked?MF_GRAYED:MF_ENABLED));
    }
    EnableMenuItem(shell->menu,SHELL_MENU_BASE+(UINT)XFU_SHELL_CANCEL,MF_BYCOMMAND|(busy?MF_ENABLED:MF_GRAYED));
}

void xfu_native_shell_set_archive_enabled(xfu_native_shell *shell, int enabled)
{
    if (!shell) return;
    shell->archive_enabled=!!enabled;
    xfu_native_shell_set_busy(shell,shell->busy);
}

void xfu_native_shell_destroy(xfu_native_shell *shell)
{
    if (!shell) return;
    if (IsWindow(shell->window)) {
        DragAcceptFiles(shell->window,FALSE); RemoveWindowSubclass(shell->window,shell_proc,1);
        if (GetMenu(shell->window)==shell->menu) SetMenu(shell->window,NULL);
    }
    if (shell->menu) DestroyMenu(shell->menu);
    free(shell);
}
