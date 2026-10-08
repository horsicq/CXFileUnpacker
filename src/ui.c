/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include "ui.h"
#include "core.h"
#include "app_icon.h"
#include "../assets/icons/xfileunpacker_rgba.h"
#include "metadata.h"
#include "information.h"
#include "supported_types.h"
#include "xxwidgets/xxwidgets_settings.h"
#include "xxwidgets/xxwidgets_combobox.h"
#include "xxwidgets/xxwidgets_process.h"
#include "xxfclib/global/xx_settings_global.h"

#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <commctrl.h>
#include <commdlg.h>
#include <shellapi.h>
#include <shlobj.h>
#include "native_shell.h"
typedef CRITICAL_SECTION ui_mutex;
typedef HANDLE ui_thread;
#else
#include <pthread.h>
#include <time.h>
#include <sys/ioctl.h>
#include <unistd.h>
typedef pthread_mutex_t ui_mutex;
typedef pthread_t ui_thread;
#endif

#define UI_PENDING_LOGS 512
#define UI_DISPLAY_LOGS 1000
#define UI_SETTING_ADVANCED "UI/Advanced"
#define UI_SETTING_LOG "UI/OperationLog"

typedef struct ui_job {
    xfu_request request;
    char *archive_path, *output_dir, *password;
    char *retrieve_member_name;
    size_t retrieve_member;
    uint64_t retrieve_revision;
    int retrieve_password;
    size_t *selected_records;
    ui_mutex mutex;
    ui_thread thread;
    int thread_started, done, result, cancel_requested, memory_error;
    int read_all; /* The run read every member (walk_end). */
    xx_pd_struct worker_progress, progress_snapshot;
    int overall_level, worker_stopped;
    uint64_t progress_published;
    int smoke_progress_delay, smoke_progress_paused, smoke_progress_shown;
    char *logs[UI_PENDING_LOGS];
    size_t log_first, log_count;
    uint64_t completed, total;
    char *current_name;
    int progress_changed;
    xfu_entry *entries;
    size_t entry_count, entry_capacity;
    xx_file_type_t file_types[XX_FILE_TYPE_CHAIN_MAX], selected_type;
    size_t type_count;
    int have_file_types;
} ui_job;

typedef struct ui_state {
    xxwidgets_app *app;
    xxwidgets_about_dialog *about;
    xx_settings *settings, *previous_settings;
    xxwidgets_backend backend;
    xxwidgets_widget *window, *archive_label, *archive_path, *archive_browse;
    xxwidgets_widget *output_label, *output_dir;
    xxwidgets_widget *password_label, *password, *get_password;
    xxwidgets_widget *type_label, *file_type;
    xxwidgets_widget *open, *extract, *test, *cancel, *quit;
    xxwidgets_widget *copy_path, *info, *log_toggle, *advanced, *details, *options, *about_button, *formats_button;
    xxwidgets_widget *members_label, *members, *metadata;
    xxwidgets_widget *progress, *status, *log_label, *log, *help;
    ui_job *job;
    xfu_entry *listed_entries;
    size_t listed_count;
    char *file_types_path, *pending_type_path;
    char *members_archive; /* Archive the members view lists, or NULL. */
    char *password_archive, *password_listed_archive;
    char *automatic_password, *automatic_password_display;
    int password_manual, password_updating;
    int pending_password_retrieval;
    uint64_t password_archive_revision;
    int retrieve_smoke_click;
    size_t retrieve_smoke_member;
    xx_file_type_t selected_type;
    size_t file_type_count; /* Entries in the File type list. */
    xfu_command pending_command;
    int pending_extract_selected;
    int type_smoke, type_smoke_stage;
    int password_smoke, password_smoke_stage;
    const char *password_smoke_expected;
    int progress_smoke, progress_smoke_shown, progress_smoke_cancelled;
    uint64_t progress_smoke_started;
    int running, closing, smoke, exit_code, columns, rows, layout_ready, log_visible, busy, advanced_visible, options_requested, about_requested, formats_requested, browse_requested;
    xxwidgets_widget *busy_focus; /* Control that started the running operation. */
    int window_columns, window_rows; /* Window size in cells last laid out for. */
#ifdef _WIN32
    int cell_width, cell_height;
    xfu_native_shell *shell;
    xfu_shell_action pending_action;
    int context_pending, context_x, context_y;
#endif
} ui_state;

static void layout(ui_state *ui, int columns, int rows);
static void report(xxwidgets_backend backend, const char *message, int error);
static const char *command_name(xfu_command command);
static void cancel_job(ui_state *ui);
static int drive_progress_smoke(ui_state *ui);
static int smoke_password_listing(ui_state *ui);
static int select_source_member(ui_state *ui, size_t source);
static int finish_password_retrieval(ui_state *ui, const ui_job *job);
static void smoke_retrieval_finished(ui_state *ui, const ui_job *job, int result);
static void on_event(xxwidgets_app *app, const xxwidgets_event *event, void *user);

static uint64_t progress_clock(void)
{
#ifdef _WIN32
    return (uint64_t)GetTickCount64();
#else
    struct timespec now = {0, 0};
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (uint64_t)now.tv_sec * 1000 + (uint64_t)now.tv_nsec / 1000000;
#endif
}

static int create_about(ui_state *ui)
{
    if (xxwidgets_about_dialog_create(&ui->about) != XXWIDGETS_OK) return 0;
#define ABOUT(field, text) do { if (xxwidgets_about_dialog_set_text(ui->about, field, text) != XXWIDGETS_OK) return 0; } while (0)
    ABOUT(XXWIDGETS_ABOUT_TITLE, "About XFileUnpacker");
    ABOUT(XXWIDGETS_ABOUT_PROGRAM_NAME, "XFileUnpacker");
    ABOUT(XXWIDGETS_ABOUT_VERSION, "Version " XFILEUNPACKER_VERSION);
    ABOUT(XXWIDGETS_ABOUT_DESCRIPTION, "Archive browser and unpacker.\nConsole, desktop and terminal interfaces.");
    ABOUT(XXWIDGETS_ABOUT_COPYRIGHT, "Copyright (c) 2026 hors <horsicq@gmail.com>");
    ABOUT(XXWIDGETS_ABOUT_WEBSITE, "https://github.com/horsicq");
    ABOUT(XXWIDGETS_ABOUT_LICENSE, "MIT License");
    ABOUT(XXWIDGETS_ABOUT_CREDITS, "Built with xxwidgets and xxfclib.\nSee the distributed licenses for third-party components.");
#undef ABOUT
    return xxwidgets_about_dialog_set_image(ui->about, xfu_icon_rgba, XFU_ICON_WIDTH,
        XFU_ICON_HEIGHT, XFU_ICON_WIDTH * 4) == XXWIDGETS_OK;
}

static int desktop_shell(const ui_state *ui)
{
#ifdef _WIN32
    return ui->backend == XXWIDGETS_BACKEND_NATIVE;
#else
    (void)ui;
    return 0;
#endif
}

static char *copy_text(const char *text)
{
    size_t length = strlen(text ? text : "") + 1;
    char *result = (char *)malloc(length);
    if (result) memcpy(result, text ? text : "", length);
    return result;
}

static void free_password(char *text)
{
    if (text) {
        volatile unsigned char *wipe = (volatile unsigned char *)text;
        size_t length = strlen(text);
        while (length--) *wipe++ = 0;
        free(text);
    }
}

/* Some legacy archives store byte names in an unspecified DOS code page.
 * Preserve Unicode text; show undecodable bytes visibly without guessing a
 * code page. Display names never feed back into extraction or source paths. */
static char *display_text_impl(const char *text, int member_path)
{
    const unsigned char *input = (const unsigned char *)(text ? text : "");
    const char hex[] = "0123456789ABCDEF";
    size_t remaining = strlen((const char *)input), position = 0;
    char *result;
    if (remaining > (SIZE_MAX - 1) / 4) return NULL;
    result = (char *)malloc(remaining * 4 + 1);
    if (!result) return NULL;
    while (remaining) {
        size_t count = 0, i;
        if (input[0] >= 32 && input[0] < 127) count = 1;
        else if (input[0] >= 0xc2 && input[0] <= 0xdf) count = 2;
        else if (input[0] >= 0xe0 && input[0] <= 0xef) count = 3;
        else if (input[0] >= 0xf0 && input[0] <= 0xf4) count = 4;
        if (count > remaining) count = 0;
        for (i = 1; count && i < count; ++i)
            if ((input[i] & 0xc0) != 0x80) count = 0;
        if (count > 1 && ((input[0] == 0xe0 && input[1] < 0xa0) ||
            (input[0] == 0xed && input[1] >= 0xa0) ||
            (input[0] == 0xf0 && input[1] < 0x90) ||
            (input[0] == 0xf4 && input[1] >= 0x90))) count = 0;
        if (count) {
            if (member_path == 2 && input[0] == '\\') result[position++] = '\\';
            memcpy(result + position, input, count);
            position += count; input += count; remaining -= count;
        } else {
            if (member_path == 1) {
                /* Backslash escapes would become archive folder separators. */
                result[position++] = '[';
                result[position++] = hex[input[0] >> 4];
                result[position++] = hex[input[0] & 15];
                result[position++] = ']';
            } else {
                result[position++] = '\\'; result[position++] = 'x';
                result[position++] = hex[input[0] >> 4];
                result[position++] = hex[input[0] & 15];
            }
            ++input; --remaining;
        }
    }
    result[position] = '\0';
    return result;
}

static char *display_text(const char *text)
{
    return display_text_impl(text, 0);
}

static char *display_member_text(const char *text)
{
    return display_text_impl(text, 1);
}

static void mutex_lock(ui_mutex *mutex)
{
#ifdef _WIN32
    EnterCriticalSection(mutex);
#else
    pthread_mutex_lock(mutex);
#endif
}

static void mutex_unlock(ui_mutex *mutex)
{
#ifdef _WIN32
    LeaveCriticalSection(mutex);
#else
    pthread_mutex_unlock(mutex);
#endif
}

static int mutex_init(ui_mutex *mutex)
{
#ifdef _WIN32
    InitializeCriticalSection(mutex);
    return 1;
#else
    return pthread_mutex_init(mutex, NULL) == 0;
#endif
}

static void mutex_destroy(ui_mutex *mutex)
{
#ifdef _WIN32
    DeleteCriticalSection(mutex);
#else
    pthread_mutex_destroy(mutex);
#endif
}

static void free_entries(xfu_entry *entries, size_t count)
{
    size_t i;
    for (i = 0; i < count; ++i) {
        free((char *)entries[i].name);
        free_password((char *)entries[i].embedded_password);
        xfu_free_properties((xfu_property *)entries[i].properties, entries[i].property_count);
    }
    free(entries);
}

static void job_log(void *user, bool error, const char *line)
{
    ui_job *job = (ui_job *)user;
    char *copy = display_text(line);
    size_t position;
    (void)error; /* Keep the sample's informational and diagnostic lines intact. */
    if (!copy) return;
    mutex_lock(&job->mutex);
    if (job->log_count == UI_PENDING_LOGS) {
        free(job->logs[job->log_first]);
        job->log_first = (job->log_first + 1) % UI_PENDING_LOGS;
        --job->log_count;
    }
    position = (job->log_first + job->log_count) % UI_PENDING_LOGS;
    job->logs[position] = copy;
    ++job->log_count;
    mutex_unlock(&job->mutex);
}

static void job_entry(void *user, const xfu_entry *entry)
{
    ui_job *job = (ui_job *)user;
    char *name, *password = NULL;
    xfu_entry *grown;
    size_t capacity;
    xfu_property *properties = NULL;
    size_t i;
    if (job->memory_error) return;
    name = display_member_text(entry->name);
    if (!name) { job->memory_error = 1; return; }
    if (entry->embedded_password) {
        password = copy_text(entry->embedded_password);
        if (!password) { free(name); job->memory_error = 1; return; }
    }
    if (entry->property_count) {
        if (entry->property_count > SIZE_MAX / sizeof(*properties)) { free_password(password); free(name); job->memory_error = 1; return; }
        properties = (xfu_property *)calloc(entry->property_count, sizeof(*properties));
        if (!properties) { free_password(password); free(name); job->memory_error = 1; return; }
        for (i = 0; i < entry->property_count; ++i) {
            properties[i].name = display_member_text(entry->properties[i].name);
            properties[i].value = display_text(entry->properties[i].value);
            if (!properties[i].name || !properties[i].value) {
                xfu_free_properties(properties, entry->property_count); free_password(password); free(name); job->memory_error = 1; return;
            }
        }
    }
    if (job->entry_count == job->entry_capacity) {
        capacity = job->entry_capacity ? job->entry_capacity * 2 : 128;
        if (capacity > SIZE_MAX / sizeof(*grown)) {
            xfu_free_properties(properties, entry->property_count); free_password(password); free(name); job->memory_error = 1; return;
        }
        grown = (xfu_entry *)realloc(job->entries, capacity * sizeof(*grown));
        if (!grown) { xfu_free_properties(properties, entry->property_count); free_password(password); free(name); job->memory_error = 1; return; }
        job->entries = grown;
        job->entry_capacity = capacity;
    }
    job->entries[job->entry_count] = *entry;
    job->entries[job->entry_count].properties = properties;
    job->entries[job->entry_count].embedded_password = password;
    job->entries[job->entry_count++].name = name;
}

static void job_progress(void *user, uint64_t completed, uint64_t total, const char *name)
{
    ui_job *job = (ui_job *)user;
    char *copy = display_text(name);
    /* Only the worker touches this monitor. Its observer publishes a copy. */
    if (job->overall_level >= 0) {
        xx_pd_record *record = &job->worker_progress.records[job->overall_level];
        record->total = total;
        snprintf(record->status, sizeof(record->status), "%s", copy && copy[0] ? copy : "Archive members");
        xx_pd_set_current(&job->worker_progress, job->overall_level, completed);
    }
    mutex_lock(&job->mutex);
    job->completed = completed;
    job->total = total;
    free(job->current_name);
    job->current_name = copy;
    job->progress_changed = 1;
    mutex_unlock(&job->mutex);
}

static bool job_cancelled(void *user)
{
    ui_job *job = (ui_job *)user;
    int cancelled;
    mutex_lock(&job->mutex);
    cancelled = job->cancel_requested;
    mutex_unlock(&job->mutex);
    return cancelled || job->memory_error;
}

static void job_file_types(void *user, const xx_file_type_t *types, size_t count,
                           xx_file_type_t selected)
{
    ui_job *job = (ui_job *)user;
    if (count > XX_FILE_TYPE_CHAIN_MAX) { job->memory_error = 1; return; }
    if (count) memcpy(job->file_types, types, count * sizeof(*types));
    job->type_count = count;
    job->selected_type = selected;
    job->have_file_types = 1;
}

static void job_walk_end(void *user, bool complete)
{
    ((ui_job *)user)->read_all = complete;
}

static bool job_observe_progress(const xx_pd_struct *progress, void *user)
{
    ui_job *job = (ui_job *)user;
    uint64_t now = progress_clock();
    int pause = job->smoke_progress_delay > 1 && !job->smoke_progress_paused && progress->records[1].is_busy;
    /* Decoder stop checks can be very frequent. Publish/poll at most every
     * 30 ms; the cached stop belongs exclusively to this worker thread. */
    if (!pause && now - job->progress_published < 30) return job->worker_stopped != 0;
    job->progress_published = now;
    mutex_lock(&job->mutex);
    job->progress_snapshot = *progress;
    job->worker_stopped = job->cancel_requested || job->memory_error;
    mutex_unlock(&job->mutex);
    if (pause) {
        /* The explicit integration-test flag slows an active decoder on its
         * worker thread. The real modal loop must remain responsive. */
        job->smoke_progress_paused = 1;
        while (progress_clock() - now < 8000) {
            int shown, stopped;
            mutex_lock(&job->mutex);
            shown = job->smoke_progress_shown;
            stopped = job->cancel_requested || job->memory_error;
            mutex_unlock(&job->mutex);
            if (stopped || (job->smoke_progress_delay == 2 && shown)) break;
#ifdef _WIN32
            Sleep(10);
#else
            struct timespec delay = {0, 10000000};
            nanosleep(&delay, NULL);
#endif
        }
        job->worker_stopped = job_cancelled(job);
    }
    return job->worker_stopped != 0;
}

static xxwidgets_status job_dialog_update(void *user, int stop,
    xx_pd_struct *progress, int *finished)
{
    ui_state *ui = (ui_state *)user;
    ui_job *job = ui->job;
    mutex_lock(&job->mutex);
    if (stop || ui->closing) job->cancel_requested = 1;
    *progress = job->progress_snapshot;
    progress->is_stop = progress->is_stop || job->cancel_requested;
    *finished = job->done;
    mutex_unlock(&job->mutex);
    if (ui->progress_smoke && !drive_progress_smoke(ui)) return XXWIDGETS_PLATFORM_ERROR;
    return XXWIDGETS_OK;
}

#ifdef _WIN32
static DWORD WINAPI job_worker(LPVOID parameter)
#else
static void *job_worker(void *parameter)
#endif
{
    ui_job *job = (ui_job *)parameter;
    xx_pd_observer previous = xx_pd_set_observer(&job->worker_progress, job_observe_progress, job);
    int result;
    job->overall_level = xx_pd_enter_level(&job->worker_progress, 0, command_name(job->request.command));
    result = xfu_run(&job->request);
    if (job->memory_error) {
        job_log(job, true, "Out of memory while collecting archive members.");
        result = 2;
    }
    xx_pd_leave_level(&job->worker_progress, job->overall_level);
    xx_pd_set_observer(previous.progress, previous.callback, previous.user_data);
    mutex_lock(&job->mutex);
    job->progress_snapshot = job->worker_progress;
    job->result = result;
    job->done = 1;
    mutex_unlock(&job->mutex);
#ifdef _WIN32
    return 0;
#else
    return NULL;
#endif
}

static void job_join(ui_job *job)
{
    if (!job->thread_started) return;
#ifdef _WIN32
    WaitForSingleObject(job->thread, INFINITE);
    CloseHandle(job->thread);
#else
    pthread_join(job->thread, NULL);
#endif
    job->thread_started = 0;
}

static void job_destroy(ui_job *job)
{
    size_t i;
    if (!job) return;
    job_join(job);
    free(job->selected_records);
    free(job->archive_path);
    free(job->output_dir);
    free_password(job->password);
    free(job->retrieve_member_name);
    free(job->current_name);
    for (i = 0; i < job->log_count; ++i)
        free(job->logs[(job->log_first + i) % UI_PENDING_LOGS]);
    free_entries(job->entries, job->entry_count);
    mutex_destroy(&job->mutex);
    free(job);
}

static char *widget_text(xxwidgets_widget *widget)
{
    char *result;
    size_t size = 0;
    xxwidgets_status status = xxwidgets_widget_get_text(widget, NULL, 0, &size);
    if (status != XXWIDGETS_OK && status != XXWIDGETS_BUFFER_TOO_SMALL) return NULL;
    result = (char *)malloc(size);
    if (result && xxwidgets_widget_get_text(widget, result, size, NULL) != XXWIDGETS_OK) {
        free(result); result = NULL;
    }
    return result;
}

static void show_status(ui_state *ui, const char *message)
{
    xxwidgets_widget_set_text(ui->status, message);
}

/* A single-line editor cannot preserve embedded controls. Keep the raw
 * automatic credential separately; only its visible representation is escaped.
 * User edits, including literal backslashes, always become literal passwords. */
static char *password_display(const char *password, int *escaped)
{
    char *text = display_text(password);
    if (!text) return NULL;
    *escaped = strcmp(text, password) != 0;
    if (*escaped) {
        free_password(text);
        /* Escape literal backslashes too when this value needs an escaped
         * representation, keeping controls/invalid UTF-8 unambiguous. */
        text = display_text_impl(password, 2);
    }
    return text;
}

static int set_automatic_password(ui_state *ui, const char *password)
{
    char *raw = NULL, *display = NULL;
    int escaped = 0;
    if (ui->password_manual) return 1;
    if (password) {
        raw = copy_text(password);
        display = password_display(password, &escaped);
        if (!raw || !display) { free_password(raw); free_password(display); return 0; }
    }
    ui->password_updating = 1;
    if (xxwidgets_widget_set_text(ui->password, display ? display : "") != XXWIDGETS_OK) {
        ui->password_updating = 0; free_password(raw); free_password(display); return 0;
    }
    ui->password_updating = 0;
    free_password(ui->automatic_password); free_password(ui->automatic_password_display);
    ui->automatic_password = raw; ui->automatic_password_display = display;
    xxwidgets_widget_set_text(ui->password_label, escaped ? "Password (escaped):" : "Password:");
    return 1;
}

static void password_edited(ui_state *ui)
{
    if (ui->password_updating) return;
    ui->password_manual = 1;
    free_password(ui->automatic_password); free_password(ui->automatic_password_display);
    ui->automatic_password = ui->automatic_password_display = NULL;
    xxwidgets_widget_set_text(ui->password_label, "Password:");
}

static int password_archive_changed(ui_state *ui, const char *archive)
{
    char *path;
    if (ui->password_archive && !strcmp(ui->password_archive, archive)) return 1;
    path = copy_text(archive);
    if (!path) return 0;
    if (!set_automatic_password(ui, NULL)) { free(path); return 0; }
    free(ui->password_archive); ui->password_archive = path;
    free(ui->password_listed_archive); ui->password_listed_archive = NULL;
    ++ui->password_archive_revision;
    return 1;
}

static int password_snapshot(ui_state *ui, char **password)
{
    char *field = widget_text(ui->password);
    *password = NULL;
    if (!field) return 0;
    if (ui->automatic_password && ui->automatic_password_display &&
        !strcmp(field, ui->automatic_password_display)) {
        *password = copy_text(ui->automatic_password);
        free_password(field); return *password != NULL;
    }
    if (ui->password_manual || field[0]) { *password = field; return 1; }
    free_password(field); return 1;
}

static void autofill_selected_password(ui_state *ui, size_t index)
{
    if (!(ui->job && ui->job->retrieve_password) && !ui->password_manual && index < ui->listed_count &&
        ui->password_listed_archive && ui->password_archive &&
        !strcmp(ui->password_listed_archive, ui->password_archive) &&
        ui->listed_entries[index].embedded_password &&
        !set_automatic_password(ui, ui->listed_entries[index].embedded_password))
        show_status(ui, "Cannot display the recovered password.");
}

static int autofill_listing_password(ui_state *ui, const ui_job *job)
{
    char *path = NULL;
    size_t i;
    if (job->result == 0 && ui->password_archive &&
        !strcmp(ui->password_archive, job->archive_path)) {
        path = copy_text(job->archive_path);
        if (!path) return 0;
    }
    free(ui->password_listed_archive); ui->password_listed_archive = path;
    if (job->retrieve_password) return 1;
    if (!ui->password_manual) {
        const char *first = NULL;
        for (i = 0; path && i < ui->listed_count; ++i)
            if (ui->listed_entries[i].embedded_password) {
                first = ui->listed_entries[i].embedded_password; break;
            }
        return set_automatic_password(ui, first);
    }
    return 1;
}

static void append_log(ui_state *ui, const char *line)
{
    if (xxwidgets_listbox_count(ui->log) >= UI_DISPLAY_LOGS) {
        xxwidgets_listbox_clear(ui->log);
        xxwidgets_listbox_add(ui->log, "Earlier log lines discarded (1000-line display limit).");
    }
    xxwidgets_listbox_add(ui->log, line);
    xxwidgets_widget_set_value(ui->log, (int)xxwidgets_listbox_count(ui->log) - 1);
}

static void set_busy(ui_state *ui, int busy)
{
    /* About, Options and File types are modal: opened during an operation they
     * would stop its progress display and keep Cancel out of reach. */
    xxwidgets_widget *controls[] = {
        ui->archive_path, ui->archive_browse, ui->output_dir, ui->open,
        ui->extract, ui->test, ui->password, ui->get_password,
        ui->options, ui->about_button, ui->formats_button
    };
    size_t i;
    int cancel_focused = 0;
    /* A backend moves focus off a control it disables. Cancel is enabled
     * first, so focus can land there and never fall through to Quit, where
     * the terminal UI's next Enter would end the program. */
    if (busy) xxwidgets_widget_set_enabled(ui->cancel, 1);
    for (i = 0; i < sizeof(controls) / sizeof(controls[0]); ++i)
        xxwidgets_widget_set_enabled(controls[i], !busy);
    xxwidgets_widget_set_enabled(ui->file_type, !busy);
    xxwidgets_widget_set_enabled(ui->extract, !busy && ui->selected_type != XX_FILE_TYPE_BINARY);
    xxwidgets_widget_set_enabled(ui->test, !busy && ui->selected_type != XX_FILE_TYPE_BINARY);
    /* Asked before Cancel is disabled, which moves focus off it. -1: unknown. */
    if (!busy) cancel_focused = xxwidgets_widget_has_focus(ui->cancel);
    if (!busy) xxwidgets_widget_set_enabled(ui->cancel, 0);
    ui->busy = busy;
    if (!ui->smoke && ui->layout_ready && !desktop_shell(ui)) {
        /* Keyboard users keep their place: Cancel while working, then the
         * control that started the operation, or the Archive field. Focus the
         * user moved elsewhere during the operation stays where it is. */
        if (busy) xxwidgets_widget_focus(ui->cancel);
        else if (cancel_focused != 0 &&
                 (!ui->busy_focus || xxwidgets_widget_focus(ui->busy_focus) != XXWIDGETS_OK))
            xxwidgets_widget_focus(ui->archive_path);
        if (!busy) ui->busy_focus = NULL;
    }
#ifdef _WIN32
    xfu_native_shell_set_busy(ui->shell, busy);
    xfu_native_shell_set_archive_enabled(ui->shell, ui->selected_type != XX_FILE_TYPE_BINARY);
#endif
    if (desktop_shell(ui) && ui->layout_ready) layout(ui, ui->columns, ui->rows);
}

static const char *command_name(xfu_command command)
{
    switch (command) {
    case XFU_COMMAND_LIST: return "Listing";
    case XFU_COMMAND_EXTRACT: return "Extracting";
    case XFU_COMMAND_TEST: return "Testing";
    default: return "Working";
    }
}

static void update_details(ui_state *ui, size_t index)
{
    size_t i;
    xxwidgets_listbox_clear(ui->details);
    if (!ui->advanced_visible || index >= ui->listed_count) return;
    for (i = 0; i < ui->listed_entries[index].property_count; ++i) {
        const xfu_property *property = &ui->listed_entries[index].properties[i];
        size_t length = strlen(property->name) + strlen(property->value) + 3;
        char *line = (char *)malloc(length);
        if (!line) return;
        snprintf(line, length, "%s: %s", property->name, property->value);
        xxwidgets_listbox_add(ui->details, line); free(line);
    }
}

static void update_metadata(ui_state *ui)
{
    size_t index = SIZE_MAX;
    xxwidgets_archive_entry entry;
    char *message;
    size_t capacity;
    if (xxwidgets_widget_kind(ui->members) == XXWIDGETS_ARCHIVEBROWSER) {
        xxwidgets_archive_browser_entry member;
        size_t selected_count = xxwidgets_archivebrowser_selection_count(ui->members);
        char size[40] = "", packed[40] = "";
        if (xxwidgets_archivebrowser_get_selection(ui->members, &index, &member) != XXWIDGETS_OK || !member.path) {
            char count[80];
            snprintf(count, sizeof(count), "0 / %zu object(s) selected", xxwidgets_archivebrowser_visible_count(ui->members));
            xxwidgets_widget_set_text(ui->metadata, count);
            update_details(ui, SIZE_MAX);
            return;
        }
        autofill_selected_password(ui, index);
        if (member.flags & XXWIDGETS_ARCHIVE_SIZE_KNOWN) snprintf(size, sizeof(size), "%" PRIu64, member.size);
        if (member.flags & XXWIDGETS_ARCHIVE_PACKED_SIZE_KNOWN) snprintf(packed, sizeof(packed), "%" PRIu64, member.packed_size);
        capacity = strlen(member.path) + 180;
        message = (char *)malloc(capacity);
        if (!message) return;
        snprintf(message, capacity, "%zu / %zu object(s) selected | %s | %s%s%s%s",
            selected_count, xxwidgets_archivebrowser_visible_count(ui->members), member.path,
            member.is_directory ? "Folder" : "Size: ", member.is_directory ? "" : size,
            member.is_directory ? "" : "; packed: ", member.is_directory ? "" : packed);
        xxwidgets_widget_set_text(ui->metadata, message);
        update_details(ui, index);
        free(message);
        return;
    }
    if (xxwidgets_archiveview_get_selection(ui->members, &index, &entry) != XXWIDGETS_OK ||
        index == SIZE_MAX) {
        xxwidgets_widget_set_text(ui->metadata, "No member selected.");
        update_details(ui, SIZE_MAX);
        return;
    }
    autofill_selected_password(ui, index);
    capacity = strlen(entry.path) + 192;
    message = (char *)malloc(capacity);
    if (!message) return;
    if (index < ui->listed_count) {
        const xfu_entry *details = &ui->listed_entries[index];
        char packed[32], unpacked[32];
        if (details->packed_size < 0) strcpy(packed, "unknown");
        else snprintf(packed, sizeof(packed), "%" PRId64, details->packed_size);
        if (details->unpacked_size < 0) strcpy(unpacked, "unknown");
        else snprintf(unpacked, sizeof(unpacked), "%" PRId64, details->unpacked_size);
        snprintf(message, capacity, "%s | %s | packed: %s; size: %s bytes",
                 details->name, details->is_directory ? "directory" : "file", packed, unpacked);
    } else {
        snprintf(message, capacity, "%s | %s | %" PRIu64 " bytes", entry.path,
                 entry.is_directory ? "directory" : "file", entry.size);
    }
    xxwidgets_widget_set_text(ui->metadata, message);
    update_details(ui, index);
    free(message);
}

static int apply_advanced(ui_state *ui, int checked)
{
    if (xxwidgets_widget_kind(ui->members) == XXWIDGETS_ARCHIVEBROWSER &&
        xxwidgets_archivebrowser_set_advanced(ui->members, checked) != XXWIDGETS_OK) {
        xxwidgets_widget_set_value(ui->advanced, ui->advanced_visible);
        show_status(ui, "Cannot change metadata columns."); return 0;
    }
    ui->advanced_visible = checked;
    xxwidgets_widget_set_value(ui->advanced, checked);
    layout(ui, ui->columns, ui->rows); update_metadata(ui);
    return 1;
}

/* The library/console reference, with a note on what this window leaves to xfu. */
static char *ui_supported_types_text(size_t *count)
{
    static const char note[] =
        "This window opens, tests and extracts existing archives. Creating archives and the --reader "
        "options below are console features: xfu a <archive> <file>..., xfu <command> <archive> --reader <name>\n\n";
    char *text = xfu_supported_types_text(count), *joined;
    size_t prefix = sizeof(note) - 1, length;
    if (!text) return NULL;
    length = strlen(text);
    joined = (char *)malloc(prefix + length + 1);
    if (joined) {
        memcpy(joined, note, prefix);
        memcpy(joined + prefix, text, length + 1);
    }
    free(text);
    return joined;
}

static void show_supported_types(ui_state *ui)
{
    char *text = ui_supported_types_text(NULL);
    if (!text) { show_status(ui, "Cannot allocate the supported file type list."); return; }
    if (xxwidgets_text_dialog(ui->window, "Supported file types", text) != XXWIDGETS_OK)
        show_status(ui, "Cannot show the supported file type dialog.");
    free(text);
}

static void show_options(ui_state *ui)
{
    const xxwidgets_setting_option options[] = {
        {"Advanced archive metadata", UI_SETTING_ADVANCED, 0},
        {"Show operation log", UI_SETTING_LOG, 0}
    };
    int accepted = 0;
    xxwidgets_status status;
    if (ui->job || ui->closing) return;
    status = xxwidgets_settings_options_dialog(ui->window, "XFileUnpacker - Options", ui->settings, options,
        desktop_shell(ui) ? 2 : 1, &accepted);
    if (status != XXWIDGETS_OK) { show_status(ui, "Cannot open or save Options."); return; }
    if (accepted && apply_advanced(ui, xxwidgets_settings_get_bool(ui->settings, UI_SETTING_ADVANCED, 0))) {
        ui->log_visible = xxwidgets_settings_get_bool(ui->settings, UI_SETTING_LOG, 0);
        layout(ui, ui->columns, ui->rows);
    }
}

static void change_advanced(ui_state *ui, int checked)
{
    int previous = ui->advanced_visible;
    if (!apply_advanced(ui, checked)) return;
    if (xxwidgets_settings_set_bool(ui->settings, UI_SETTING_ADVANCED, checked) != XXWIDGETS_OK) {
        apply_advanced(ui, previous);
        show_status(ui, "Cannot save the Advanced setting.");
    }
}

static const char *file_type_label(xx_file_type_t type)
{
    switch (type) {
    case XX_FILE_TYPE_BINARY: return "Binary";
    case XX_FILE_TYPE_GZ: return "gzip";
    case XX_FILE_TYPE_BZ2: return "bzip2";
    case XX_FILE_TYPE_XZ: return "xz";
    case XX_FILE_TYPE_TAR: return "tar";
    case XX_FILE_TYPE_TAR_GZ: return "tar.gz";
    case XX_FILE_TYPE_TAR_BZ2: return "tar.bz2";
    case XX_FILE_TYPE_TAR_XZ: return "tar.xz";
    case XX_FILE_TYPE_TAR_ZSTD: return "tar.zst";
    default: return xx_format_file_type_to_string(type);
    }
}

static int populate_file_types(ui_state *ui, const ui_job *job)
{
    xx_meta_string records[XX_FILE_TYPE_CHAIN_MAX] = {0};
    xx_str_w_s labels[XX_FILE_TYPE_CHAIN_MAX] = {0};
    char *path;
    size_t i, selected;
    int result = 0;
    if (!job->type_count || job->type_count > XX_FILE_TYPE_CHAIN_MAX) return 0;
    path = copy_text(job->archive_path);
    if (!path) return 0;
    selected = job->type_count - 1;
    for (i = 0; i < job->type_count; ++i) {
        labels[i].data = xx_str_utf8_to_unicode(file_type_label(job->file_types[i]));
        if (!labels[i].data) goto done;
        labels[i].length = wcslen(labels[i].data);
        labels[i].capacity = labels[i].length + 1; labels[i].is_view = true;
        records[i].meta_string = labels + i;
        records[i].var.type = XX_VAR_TYPE_UINT32;
        records[i].var.val.u32 = (uint32_t)job->file_types[i];
        if (job->file_types[i] == job->selected_type) selected = i;
    }
    if (xxwidgets_combobox_set_records(ui->file_type, records, job->type_count) != XXWIDGETS_OK ||
        xxwidgets_widget_set_value(ui->file_type, (int)selected) != XXWIDGETS_OK) goto done;
    free(ui->file_types_path); ui->file_types_path = path; path = NULL;
    ui->selected_type = job->file_types[selected];
    ui->file_type_count = job->type_count;
    result = 1;
done:
    for (i = 0; i < job->type_count; ++i) xx_str_wfree(labels[i].data);
    free(path); return result;
}

static int populate_members(ui_state *ui, ui_job *job)
{
    xxwidgets_archive_entry *entries = NULL;
    xxwidgets_status status;
    size_t i;
    if (xxwidgets_widget_kind(ui->members) == XXWIDGETS_ARCHIVEBROWSER) {
        xxwidgets_archive_browser_entry *members = NULL;
        if (job->entry_count) {
            members = (xxwidgets_archive_browser_entry *)calloc(job->entry_count, sizeof(*members));
            if (!members) return 0;
        }
        for (i = 0; i < job->entry_count; ++i) {
            members[i].path = job->entries[i].name;
            members[i].is_directory = job->entries[i].is_directory;
            if (job->entries[i].unpacked_size >= 0) {
                members[i].size = (uint64_t)job->entries[i].unpacked_size;
                members[i].flags |= XXWIDGETS_ARCHIVE_SIZE_KNOWN;
            }
            if (job->entries[i].packed_size >= 0) {
                members[i].packed_size = (uint64_t)job->entries[i].packed_size;
                members[i].flags |= XXWIDGETS_ARCHIVE_PACKED_SIZE_KNOWN;
            }
            members[i].modified = job->entries[i].modified;
            members[i].attributes = job->entries[i].attributes;
            if (job->entries[i].property_count) {
                size_t j;
                xxwidgets_archive_property *properties = (xxwidgets_archive_property *)calloc(
                    job->entries[i].property_count, sizeof(*properties));
                if (!properties) {
                    for (j = 0; j < i; ++j) free((void *)members[j].properties);
                    free(members); return 0;
                }
                members[i].properties = properties;
                members[i].property_count = job->entries[i].property_count;
                for (j = 0; j < members[i].property_count; ++j) {
                    properties[j].name = job->entries[i].properties[j].name;
                    properties[j].value = job->entries[i].properties[j].value;
                }
            }
        }
        status = xxwidgets_archivebrowser_set_entries(ui->members, members, job->entry_count);
        for (i = 0; i < job->entry_count; ++i) free((void *)members[i].properties);
        free(members);
        if (status != XXWIDGETS_OK) return 0;
        xxwidgets_archivebrowser_set_archive(ui->members, job->archive_path);
        if (desktop_shell(ui)) {
            size_t length = strlen(job->archive_path) + 24;
            char *title = (char *)malloc(length);
            if (title) {
                snprintf(title, length, "%s - XFileUnpacker", job->archive_path);
                xxwidgets_widget_set_text(ui->window, title); free(title);
            }
        }
        free_entries(ui->listed_entries, ui->listed_count);
        ui->listed_entries = job->entries; ui->listed_count = job->entry_count;
        job->entries = NULL; job->entry_count = job->entry_capacity = 0;
        free(ui->members_archive); ui->members_archive = copy_text(job->archive_path);
        if (!autofill_listing_password(ui, job)) return 0;
        update_metadata(ui);
        return 1;
    }
    if (job->entry_count) {
        entries = (xxwidgets_archive_entry *)calloc(job->entry_count, sizeof(*entries));
        if (!entries) return 0;
    }
    for (i = 0; i < job->entry_count; ++i) {
        entries[i].path = job->entries[i].name;
        entries[i].size = job->entries[i].unpacked_size >= 0 ?
            (uint64_t)job->entries[i].unpacked_size : 0;
        entries[i].is_directory = job->entries[i].is_directory;
    }
    status = xxwidgets_archiveview_set_entries(ui->members, entries, job->entry_count);
    free(entries);
    if (status != XXWIDGETS_OK) return 0;
    free_entries(ui->listed_entries, ui->listed_count);
    ui->listed_entries = job->entries;
    ui->listed_count = job->entry_count;
    job->entries = NULL;
    job->entry_count = job->entry_capacity = 0;
    free(ui->members_archive); ui->members_archive = copy_text(job->archive_path);
    if (!autofill_listing_password(ui, job)) return 0;
    update_metadata(ui);
    return 1;
}

static int clear_members(ui_state *ui)
{
    xxwidgets_status status;
    if (xxwidgets_widget_kind(ui->members) == XXWIDGETS_ARCHIVEBROWSER) {
        status = xxwidgets_archivebrowser_set_entries(ui->members, NULL, 0);
        /* The path bar must not keep naming the archive that was listed. */
        if (status == XXWIDGETS_OK) status = xxwidgets_archivebrowser_set_archive(ui->members, "");
    } else status = xxwidgets_archiveview_set_entries(ui->members, NULL, 0);
    if (status != XXWIDGETS_OK) return 0;
    free(ui->members_archive); ui->members_archive = NULL;
    free_entries(ui->listed_entries, ui->listed_count);
    ui->listed_entries = NULL; ui->listed_count = 0;
    update_metadata(ui);
    return 1;
}

#ifndef _WIN32
/* Fields are not run through a shell: "~" and "~/..." mean the home folder,
 * not a directory literally named "~". The field then shows the full path. */
static void expand_home_field(xxwidgets_widget *field)
{
    char *text = widget_text(field), *expanded;
    const char *home = getenv("HOME");
    if (text && text[0] == '~' && (!text[1] || text[1] == '/') && home && home[0]) {
        size_t home_length = strlen(home), rest = strlen(text + 1);
        expanded = (char *)malloc(home_length + rest + 1);
        if (expanded) {
            memcpy(expanded, home, home_length);
            memcpy(expanded + home_length, text + 1, rest + 1);
            xxwidgets_widget_set_text(field, expanded);
            free(expanded);
        }
    }
    free(text);
}
#endif

static int start_job(ui_state *ui, xfu_command command)
{
    ui_job *job;
    char message[80];
    int known_file, requested_type;
    int retrieve = command == XFU_COMMAND_LIST && ui->pending_password_retrieval;
    if (ui->job) return 0;
#ifndef _WIN32
    expand_home_field(ui->archive_path);
    expand_home_field(ui->output_dir);
#endif
    ui->pending_password_retrieval = 0;
    job = (ui_job *)calloc(1, sizeof(*job));
    if (!job) { show_status(ui, "Out of memory."); return 0; }
    if (!mutex_init(&job->mutex)) { free(job); show_status(ui, "Cannot initialize worker."); return 0; }
    job->archive_path = widget_text(ui->archive_path);
    job->output_dir = widget_text(ui->output_dir);
    if (!job->archive_path || !job->output_dir) {
        show_status(ui, "Out of memory."); job_destroy(job); return 0;
    }
    if (!job->archive_path[0]) {
        show_status(ui, "Enter an archive path first."); job_destroy(job); return 0;
    }
    job->retrieve_password = retrieve;
    job->retrieve_member = SIZE_MAX;
    if (retrieve && ui->password_listed_archive && !strcmp(ui->password_listed_archive, job->archive_path)) {
        size_t source = SIZE_MAX;
        if (xxwidgets_widget_kind(ui->members) == XXWIDGETS_ARCHIVEBROWSER) {
            xxwidgets_archive_browser_entry entry;
            xxwidgets_archivebrowser_get_selection(ui->members, &source, &entry);
        } else {
            xxwidgets_archive_entry entry;
            xxwidgets_archiveview_get_selection(ui->members, &source, &entry);
        }
        if (source < ui->listed_count) {
            job->retrieve_member = source;
            job->retrieve_member_name = copy_text(ui->listed_entries[source].name);
            if (!job->retrieve_member_name) { job_destroy(job); return 0; }
        }
    }
    if (!password_archive_changed(ui, job->archive_path) ||
        (!retrieve && ui->password_manual && !password_snapshot(ui, &job->password))) {
        show_status(ui, "Cannot read the archive password."); job_destroy(job); return 0;
    }
    job->request.command = command;
    job->retrieve_revision = ui->password_archive_revision;
    job->request.archive_path = job->archive_path;
    job->request.output_dir = job->output_dir[0] ? job->output_dir : ".";
    /* Automatic values describe a selected member's recovered credential.
     * They must not override other groups in a reader that recovers each
     * member separately. Only an explicit startup value or user edit is an
     * operation-wide override, including an explicitly empty password. */
    job->request.password = job->password;
    if (ui->password_smoke == 2 &&
        (((ui->password_smoke_expected != NULL) != (ui->password_manual != 0)) ||
         ((job->request.password == NULL) != (ui->password_smoke_expected == NULL)) ||
         (job->request.password && strcmp(job->request.password, ui->password_smoke_expected)))) {
        show_status(ui, "Password smoke: manual job value changed."); job_destroy(job); return 0;
    }
    if (retrieve && job->request.password) { job_destroy(job); return 0; }
    if (ui->password_smoke == 1 &&
        (ui->password_manual || job->password || job->request.password)) {
        show_status(ui, "Password smoke: automatic value became a caller override."); job_destroy(job); return 0;
    }
    if (ui->password_smoke == 3 && command == XFU_COMMAND_TEST &&
        (ui->password_manual || job->password || job->request.password)) {
        show_status(ui, "Password retrieval smoke: recovered value became a caller override.");
        job_destroy(job); return 0;
    }
    job->request.callbacks.user = job;
    job->request.callbacks.log = job_log;
    job->request.callbacks.entry = job_entry;
    job->request.callbacks.progress = job_progress;
    job->request.callbacks.cancelled = job_cancelled;
    job->request.callbacks.file_types = job_file_types;
    job->request.callbacks.walk_end = job_walk_end;
    job->worker_progress = xx_pd_init();
    job->overall_level = -1;
    job->request.progress_state = &job->worker_progress;
    job->smoke_progress_delay = ui->progress_smoke;
    known_file = ui->file_types_path && !strcmp(ui->file_types_path, job->archive_path);
    /* A file recognised as no archive at all is detected again: it may have
     * become one since (a finished download, another file at that path). */
    if (known_file && ui->selected_type == XX_FILE_TYPE_BINARY && ui->file_type_count <= 1) known_file = 0;
    requested_type = ui->pending_type_path && !strcmp(ui->pending_type_path, job->archive_path);
    free(ui->pending_type_path); ui->pending_type_path = NULL;
    if (known_file || requested_type)
        job->request.file_type = ui->selected_type;
    else ui->selected_type = XX_FILE_TYPE_UNKNOWN;
    if (ui->selected_type == XX_FILE_TYPE_UNKNOWN) {
        ui_job initial = {0};
        initial.archive_path = ""; initial.file_types[0] = XX_FILE_TYPE_BINARY;
        initial.type_count = 1; initial.selected_type = XX_FILE_TYPE_BINARY;
        if (!populate_file_types(ui, &initial)) {
            show_status(ui, "Cannot reset the file type list."); job_destroy(job); return 0;
        }
        if (!clear_members(ui)) {
            show_status(ui, "Cannot clear the archive listing."); job_destroy(job); return 0;
        }
    }
    if (!retrieve && job->request.file_type == XX_FILE_TYPE_BINARY && known_file) {
        ui->pending_extract_selected = 0;
        if (command != XFU_COMMAND_LIST) {
            show_status(ui, "Binary cannot be opened as an archive. Choose an archive file type.");
            job_destroy(job); return 0;
        }
        if (!populate_members(ui, job)) {
            show_status(ui, "Cannot clear the archive listing."); job_destroy(job); return 0;
        }
        show_status(ui, "Binary: no archive members.");
        xxwidgets_widget_set_value(ui->progress, 0);
        set_busy(ui, 0); job_destroy(job);
        if (ui->smoke && !ui->type_smoke) { ui->exit_code = 0; ui->running = 0; }
        return 1;
    }
    if (command == XFU_COMMAND_EXTRACT && ui->pending_extract_selected) {
        size_t count = 0;
        ui->pending_extract_selected = 0;
        if (xxwidgets_archivebrowser_selected_sources(ui->members, NULL, 0, &count) != XXWIDGETS_OK ||
            !count || count > SIZE_MAX / sizeof(*job->selected_records)) {
            show_status(ui, "Select at least one member to extract."); job_destroy(job); return 0;
        }
        job->selected_records = (size_t *)malloc(count * sizeof(*job->selected_records));
        if (!job->selected_records ||
            xxwidgets_archivebrowser_selected_sources(ui->members, job->selected_records, count, &count) != XXWIDGETS_OK) {
            show_status(ui, "Cannot collect the selected members."); job_destroy(job); return 0;
        }
        job->request.extract_selected = true;
        job->request.selected_records = job->selected_records;
        job->request.selected_record_count = count;
        job->request.callbacks.entry = NULL;
    }
#ifdef _WIN32
    job->thread = CreateThread(NULL, 0, job_worker, job, 0, NULL);
    if (!job->thread) {
#else
    if (pthread_create(&job->thread, NULL, job_worker, job) != 0) {
#endif
        show_status(ui, "Cannot start archive worker."); job_destroy(job); return 0;
    }
    job->thread_started = 1;
    ui->job = job;
    set_busy(ui, 1);
    xxwidgets_widget_set_value(ui->progress, 0);
    snprintf(message, sizeof(message), "%s archive...", command_name(command));
    show_status(ui, message);
    if (command == XFU_COMMAND_EXTRACT) {
        xx_pd_struct snapshot = xx_pd_init();
        xxwidgets_status status;
        ui->progress_smoke_started = progress_clock();
        status = xxwidgets_process_dialog(ui->window, "Extracting archive", &snapshot, job_dialog_update, ui);
        /* A UI failure still delivers stop, and this controller owns joining.
         * Keep the job and its mutex alive until the worker has exited. */
        if (status != XXWIDGETS_OK) cancel_job(ui);
        job_join(job);
        /* Cancelled from the dialog: as after the main Cancel, a second Enter
         * must not land on Extract and start it again. */
        if (job->cancel_requested && !ui->closing) ui->busy_focus = ui->members;
        if (status != XXWIDGETS_OK) {
            snprintf(message, sizeof(message), "Progress dialog: %s", xxwidgets_status_string(status));
            if (ui->progress_smoke) fprintf(stderr, "%s\n", message);
            append_log(ui, message); job->result = 2;
        }
        if (ui->progress_smoke &&
            ((ui->progress_smoke == 1 && ui->progress_smoke_shown) ||
             (ui->progress_smoke > 1 && ui->progress_smoke_shown != 1) ||
             (ui->progress_smoke == 3 && (!ui->progress_smoke_cancelled || !snapshot.is_stop || job->result != 1)))) {
            fprintf(stderr, "Threaded progress smoke: mode=%d shown=%d cancel=%d stopped=%d result=%d\n",
                ui->progress_smoke, ui->progress_smoke_shown, ui->progress_smoke_cancelled,
                snapshot.is_stop != 0, job->result);
            append_log(ui, "Threaded progress smoke check failed."); job->result = 2;
        }
    }
    return 1;
}

static void cancel_job(ui_state *ui)
{
    if (!ui->job) return;
    mutex_lock(&ui->job->mutex);
    ui->job->cancel_requested = 1;
    mutex_unlock(&ui->job->mutex);
    show_status(ui, "Stopping archive worker...");
    ui->busy_focus = ui->members;
}

/* A member path without its trailing separators, so a folder record ("b/",
 * or "b" in 7z) and a folder implied by its members ("b/") match. */
static int same_member_path(const char *a, const char *b)
{
    size_t m = strlen(a), n = strlen(b);
    while (m && (a[m - 1] == '/' || a[m - 1] == '\\')) --m;
    while (n && (b[n - 1] == '/' || b[n - 1] == '\\')) --n;
    return m == n && !strncmp(a, b, m);
}

static size_t member_rows(ui_state *ui)
{
    return xxwidgets_widget_kind(ui->members) == XXWIDGETS_ARCHIVEBROWSER ?
        xxwidgets_archivebrowser_visible_count(ui->members) : xxwidgets_archiveview_count(ui->members);
}

/* The path of a members row (a browser row in the folder shown, or an
 * archive view entry), borrowed from the widget, and whether it is a folder;
 * NULL on failure. */
static const char *member_row_path(ui_state *ui, size_t row, int *is_directory)
{
    if (xxwidgets_widget_kind(ui->members) == XXWIDGETS_ARCHIVEBROWSER) {
        xxwidgets_archive_browser_entry entry;
        size_t source;
        if (xxwidgets_archivebrowser_get_entry(ui->members, row, &source, &entry) != XXWIDGETS_OK) return NULL;
        *is_directory = entry.is_directory != 0; return entry.path;
    } else {
        xxwidgets_archive_entry entry;
        if (xxwidgets_archiveview_get_entry(ui->members, row, &entry) != XXWIDGETS_OK) return NULL;
        *is_directory = entry.is_directory != 0; return entry.path;
    }
}

/* The current members row, so a relisting can show it again: its path,
 * whether it is a folder (a file "b" and a folder "b/" are different rows)
 * and which of the rows with that path and kind it is (archives can hold a
 * path twice). NULL when nothing is current. */
static char *current_member_path(ui_state *ui, size_t *occurrence, int *is_directory)
{
    const char *path;
    size_t row;
    int value = -1, kind = 0;
    *occurrence = 0; *is_directory = 0;
    if (xxwidgets_widget_get_value(ui->members, &value) != XXWIDGETS_OK || value < 0 ||
        !(path = member_row_path(ui, (size_t)value, is_directory))) return NULL;
    for (row = 0; row < (size_t)value; ++row) {
        const char *other = member_row_path(ui, row, &kind);
        if (other && kind == *is_directory && same_member_path(other, path)) ++*occurrence;
    }
    return copy_text(path);
}

/* Make that row current again if the listing still has it. */
static int select_member_path(ui_state *ui, const char *path, size_t occurrence, int is_directory)
{
    size_t row, count, seen = 0;
    int found = -1, kind = 0;
    if (!path) return 0;
    count = member_rows(ui);
    for (row = 0; row < count && row <= INT_MAX; ++row) {
        const char *other = member_row_path(ui, row, &kind);
        if (!other || kind != is_directory || !same_member_path(other, path)) continue;
        found = (int)row; /* Fewer copies than before: the last one. */
        if (seen++ == occurrence) break;
    }
    return found >= 0 && xxwidgets_widget_set_value(ui->members, found) == XXWIDGETS_OK;
}

/* Whether a Test or Extract of the archive on screen leaves the listing (and
 * the user's folder and selection) alone. It does while the members the run
 * read match the listing. A run that read every member (with or without
 * failed members) must match it all; one that was cancelled or stopped early
 * may have read only the first of them. A file replaced on disk shows as a
 * mismatch, or as a detected type chain without the type it was listed as. */
static int keep_listing(const ui_state *ui, const ui_job *job, int cancelled)
{
    size_t i;
    if (job->request.command == XFU_COMMAND_LIST || job->retrieve_password || !ui->listed_count ||
        !ui->file_types_path || strcmp(ui->file_types_path, job->archive_path)) return 0;
    if (job->have_file_types && job->request.file_type != XX_FILE_TYPE_UNKNOWN) {
        for (i = 0; i < job->type_count && job->file_types[i] != job->request.file_type; ++i) {}
        if (i == job->type_count) return 0;
    }
    if (job->entry_count > ui->listed_count) return 0;
    if ((job->read_all || (!cancelled && job->result == 0)) && ui->listed_count != job->entry_count) return 0;
    for (i = 0; i < job->entry_count; ++i) {
        const xfu_entry *listed = &ui->listed_entries[i], *read = &job->entries[i];
        if (!listed->name || !read->name || strcmp(listed->name, read->name) ||
            listed->unpacked_size != read->unpacked_size || listed->packed_size != read->packed_size ||
            listed->is_directory != read->is_directory || strcmp(listed->modified, read->modified) ||
            strcmp(listed->attributes, read->attributes)) return 0;
    }
    return 1;
}

static void drain_job(ui_state *ui)
{
    ui_job *job = ui->job;
    char *lines[UI_PENDING_LOGS], *current = NULL;
    size_t i, count;
    uint64_t completed, total;
    int done, changed, cancelled, display_ok = 1, retrieval_current = 1, retrieval_result = 2;
    if (!job) return;
    mutex_lock(&job->mutex);
    count = job->log_count;
    for (i = 0; i < count; ++i)
        lines[i] = job->logs[(job->log_first + i) % UI_PENDING_LOGS];
    job->log_first = job->log_count = 0;
    completed = job->completed; total = job->total;
    changed = job->progress_changed;
    if (changed) current = copy_text(job->current_name);
    job->progress_changed = 0;
    done = job->done;
    cancelled = job->cancel_requested;
    mutex_unlock(&job->mutex);
    for (i = 0; i < count; ++i) { append_log(ui, lines[i]); free(lines[i]); }
    if (changed && !cancelled) {
        char *message;
        size_t capacity = strlen(current ? current : "") + 128;
        message = (char *)malloc(capacity);
        if (message) {
            if (total) snprintf(message, capacity, "%s: %" PRIu64 "/%" PRIu64 " | %s",
                command_name(job->request.command), completed, total, current ? current : "");
            else snprintf(message, capacity, "%s: %" PRIu64 " member(s) | %s",
                command_name(job->request.command), completed, current ? current : "");
            show_status(ui, message);
            free(message);
        }
        if (total) {
            int percent = completed >= total ? 100 : (int)((long double)completed * 100 / total);
            xxwidgets_widget_set_value(ui->progress, percent);
        }
    }
    free(current);
    if (!done) return;
    job_join(job);
    if (job->retrieve_password) {
        char *path = widget_text(ui->archive_path);
        retrieval_current = path && !strcmp(path, job->archive_path) &&
            ui->password_archive_revision == job->retrieve_revision;
        free(path);
    }
    if ((!job->retrieve_password || (job->result == 0 && !cancelled && retrieval_current)) &&
        job->have_file_types && job->type_count && !populate_file_types(ui, job)) {
        append_log(ui, "Could not display the detected file types."); job->result = 2; display_ok = 0;
    }
    if ((!job->retrieve_password || (job->result == 0 && !cancelled && retrieval_current)) &&
        !job->request.extract_selected &&
        !keep_listing(ui, job, cancelled)) {
        /* A password retrieval, or a complete Test/Extract of an archive
         * changed on disk, lists the archive on screen again: keep the folder
         * and the current row the user had, or no current row (a recovered
         * member's folder wins later). Open starts at the root, and so does a
         * partial relisting. */
        int browser = xxwidgets_widget_kind(ui->members) == XXWIDGETS_ARCHIVEBROWSER;
        int keep = (job->retrieve_password || (job->request.command != XFU_COMMAND_LIST && !cancelled && job->read_all)) &&
            ui->members_archive && !strcmp(ui->members_archive, job->archive_path) && ui->listed_count;
        size_t occurrence = 0;
        int current_directory = 0;
        char *directory = keep && browser ? copy_text(xxwidgets_archivebrowser_directory(ui->members)) : NULL;
        char *current = keep ? current_member_path(ui, &occurrence, &current_directory) : NULL;
        if (!populate_members(ui, job)) {
            append_log(ui, "Could not display archive members."); job->result = 2; display_ok = 0;
        } else if (keep) {
            /* A folder that is gone leaves the root shown, with its first row. */
            int restored = !directory || !directory[0] ||
                xxwidgets_archivebrowser_set_directory(ui->members, directory) == XXWIDGETS_OK;
            if (current) select_member_path(ui, current, occurrence, current_directory);
            else if (browser && restored) xxwidgets_archivebrowser_set_selection(ui->members, NULL, 0);
            update_metadata(ui);
        }
        free(directory); free(current);
    }
    if (cancelled) show_status(ui, job->request.command == XFU_COMMAND_EXTRACT ?
        "Cancelled. Completed files are kept." : "Cancelled.");
    else if (!job->retrieve_password && job->request.command == XFU_COMMAND_LIST && job->have_file_types &&
             job->selected_type == XX_FILE_TYPE_BINARY && !job->memory_error && display_ok) {
        show_status(ui, "Binary: no archive members."); job->result = 0;
        xxwidgets_widget_set_value(ui->progress, 0);
    } else if (job->result == 0) {
        show_status(ui, "Done."); xxwidgets_widget_set_value(ui->progress, 100);
    } else if (job->result == 1) show_status(ui, "Completed with errors; see log.");
    else show_status(ui, "Operation failed; see log.");
    if (job->result != 0 && desktop_shell(ui)) ui->log_visible = 1;
    if (job->retrieve_password) {
        if (!retrieval_current) show_status(ui, "Archive changed; password result discarded.");
        else if (cancelled) show_status(ui, "Password retrieval cancelled; existing input kept.");
        else if (job->result != 0) show_status(ui, "Password retrieval failed; existing input kept.");
        else retrieval_result = finish_password_retrieval(ui, job);
    }
    if (ui->password_smoke == 3 && job->retrieve_password)
        smoke_retrieval_finished(ui, job, retrieval_result);
    if ((ui->password_smoke == 1 || ui->password_smoke == 2) && job->result == 0) {
        if (job->request.command == XFU_COMMAND_LIST) {
            if (!smoke_password_listing(ui)) {
                fputs("Password smoke: editor, selection or archive lifecycle failed.\n", stderr);
                job->result = 2;
            } else if (ui->password_smoke == 1 && ui->password_smoke_stage == 0) {
                ui->password_smoke_stage = 1;
                ui->pending_command = XFU_COMMAND_LIST;
            } else {
                ui->password_smoke_stage = 2;
                ui->pending_command = XFU_COMMAND_TEST;
            }
        } else if (job->request.command == XFU_COMMAND_TEST) {
            ui->password_smoke_stage = 3;
            ui->pending_command = XFU_COMMAND_EXTRACT;
        }
    }
    if (ui->smoke && !(ui->password_smoke == 3 && job->retrieve_password) &&
        (!ui->type_smoke || job->result != 0) &&
        (!ui->password_smoke || job->result != 0 || job->request.command == XFU_COMMAND_EXTRACT ||
         (ui->password_smoke == 3 && job->request.command == XFU_COMMAND_TEST))) {
        ui->exit_code = job->result; ui->running = 0;
    }
    ui->job = NULL;
    job_destroy(job);
    set_busy(ui, 0);
    if (ui->closing) ui->running = 0;
}

#ifndef _WIN32
/* Runs from the main loop: the chooser is modal and cannot open inside an
 * input callback. */
static int browse_file(ui_state *ui, xxwidgets_widget *target)
{
    char *current = widget_text(target), *selected = NULL;
    int accepted = 0;
    xxwidgets_status status = xxwidgets_file_dialog(ui->window, XXWIDGETS_FILE_DIALOG_OPEN,
        "Open archive", current, &selected, &accepted);
    free(current);
    if (status != XXWIDGETS_OK) { show_status(ui, "Cannot show the file dialog."); return 0; }
    if (!accepted) return 0;
    status = xxwidgets_widget_set_text(target, selected);
    free(selected);
    /* The field holds UTF-8; a name in another encoding cannot be shown there. */
    if (status == XXWIDGETS_INVALID_ARGUMENT)
        show_status(ui, "The selected file name is not valid UTF-8; rename the file to open it here.");
    return status == XXWIDGETS_OK;
}
#endif

#ifdef _WIN32
static char *wide_utf8(const wchar_t *wide)
{
    int length = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide, -1, NULL, 0, NULL, NULL);
    char *result;
    if (!length) return NULL;
    result = (char *)malloc((size_t)length);
    if (result && !WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide, -1,
                                      result, length, NULL, NULL)) { free(result); result = NULL; }
    return result;
}

int xfu_ui_windows_arguments(int *argc, char ***argv)
{
    LPWSTR *wide;
    int count, i;
    char **result;
    *argc = 0; *argv = NULL;
    wide = CommandLineToArgvW(GetCommandLineW(), &count);
    if (!wide) return 0;
    result = (char **)calloc((size_t)count + 1, sizeof(*result));
    if (!result) { LocalFree(wide); return 0; }
    for (i = 0; i < count; ++i) {
        result[i] = wide_utf8(wide[i]);
        if (!result[i]) { xfu_ui_free_arguments(count, result); LocalFree(wide); return 0; }
    }
    LocalFree(wide);
    *argc = count; *argv = result;
    return 1;
}

void xfu_ui_free_arguments(int argc, char **argv)
{
    int i;
    for (i = 0; i < argc; ++i) free(argv[i]);
    free(argv);
}

static int browse_file(ui_state *ui, xxwidgets_widget *target)
{
    wchar_t path[32768] = L"";
    OPENFILENAMEW dialog;
    char *current = widget_text(target), *selected;
    if (current && current[0])
        MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, current, -1, path, 32768);
    free(current);
    memset(&dialog, 0, sizeof(dialog));
    dialog.lStructSize = sizeof(dialog);
    dialog.hwndOwner = (HWND)xxwidgets_widget_native_handle(ui->window);
    dialog.lpstrFilter = L"All files\0*.*\0\0";
    dialog.lpstrFile = path;
    dialog.nMaxFile = 32768;
    dialog.Flags = OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    if (!GetOpenFileNameW(&dialog)) return 0;
    selected = wide_utf8(path);
    if (selected) { xxwidgets_widget_set_text(target, selected); free(selected); return 1; }
    return 0;
}

static int CALLBACK native_folder_callback(HWND dialog, UINT message, LPARAM parameter, LPARAM owner)
{
    (void)parameter;
    if (message == BFFM_INITIALIZED) {
        RECT parent, bounds;
        if (GetWindowRect((HWND)owner, &parent) && GetWindowRect(dialog, &bounds))
            SetWindowPos(dialog, NULL,
                parent.left + ((parent.right - parent.left) - (bounds.right - bounds.left)) / 2,
                parent.top + ((parent.bottom - parent.top) - (bounds.bottom - bounds.top)) / 2,
                0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
    }
    return 0;
}

static void native_extract_archive(ui_state *ui, int selected_only)
{
    BROWSEINFOW dialog;
    wchar_t path[MAX_PATH];
    PIDLIST_ABSOLUTE selected;
    HRESULT initialized = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    memset(&dialog, 0, sizeof(dialog));
    dialog.hwndOwner = (HWND)xxwidgets_widget_native_handle(ui->window);
    if (selected_only && !xxwidgets_archivebrowser_selection_count(ui->members)) {
        show_status(ui, "Select at least one member to extract.");
        if (SUCCEEDED(initialized)) CoUninitialize();
        return;
    }
    dialog.lpszTitle = selected_only ? L"Extract the selected files and folders to this folder:" :
        L"Extract the entire archive to this folder:";
    dialog.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE;
    dialog.lpfn = native_folder_callback;
    dialog.lParam = (LPARAM)dialog.hwndOwner;
    selected = SHBrowseForFolderW(&dialog);
    if (selected) {
        if (SHGetPathFromIDListW(selected, path)) {
            char *destination = wide_utf8(path);
            if (destination) {
                xxwidgets_widget_set_text(ui->output_dir, destination); free(destination);
                ui->pending_extract_selected = selected_only;
                ui->pending_command = XFU_COMMAND_EXTRACT;
            }
        }
        CoTaskMemFree(selected);
    }
    if (SUCCEEDED(initialized)) CoUninitialize();
}

static void native_copy_path(ui_state *ui)
{
    xxwidgets_archive_browser_entry entry;
    size_t source;
    int length;
    HGLOBAL memory;
    wchar_t *wide;
    if (xxwidgets_archivebrowser_get_selection(ui->members, &source, &entry) != XXWIDGETS_OK || !entry.path) return;
    length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, entry.path, -1, NULL, 0);
    if (!length) return;
    memory = GlobalAlloc(GMEM_MOVEABLE, (SIZE_T)length * sizeof(*wide));
    wide = memory ? (wchar_t *)GlobalLock(memory) : NULL;
    if (!wide) { if (memory) GlobalFree(memory); return; }
    MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, entry.path, -1, wide, length);
    GlobalUnlock(memory);
    if (OpenClipboard((HWND)xxwidgets_widget_native_handle(ui->window))) {
        EmptyClipboard();
        if (SetClipboardData(CF_UNICODETEXT, memory)) memory = NULL;
        CloseClipboard();
    }
    if (memory) GlobalFree(memory);
    else show_status(ui, "Member path copied.");
}

static void native_information(ui_state *ui)
{
    char *archive = widget_text(ui->archive_path);
    xxwidgets_archive_browser_entry entry;
    xfu_entry selected;
    const xfu_entry *selection = NULL;
    size_t source;
    char *message;
    if (!archive) return;
    if (xxwidgets_archivebrowser_get_selection(ui->members, &source, &entry) == XXWIDGETS_OK && entry.path) {
        memset(&selected, 0, sizeof(selected));
        selected.unpacked_size = selected.packed_size = -1;
        /* Explicit members retain the owned display properties. Synthesized
         * directory rows have no source metadata or password of their own. */
        if (source < ui->listed_count) selected = ui->listed_entries[source];
        selected.name = entry.path;
        selected.is_directory = entry.is_directory != 0;
        if ((entry.flags & XXWIDGETS_ARCHIVE_SIZE_KNOWN) && entry.size <= INT64_MAX)
            selected.unpacked_size = (int64_t)entry.size;
        if ((entry.flags & XXWIDGETS_ARCHIVE_PACKED_SIZE_KNOWN) && entry.packed_size <= INT64_MAX)
            selected.packed_size = (int64_t)entry.packed_size;
        if (source >= ui->listed_count) {
            snprintf(selected.modified, sizeof(selected.modified), "%s", entry.modified ? entry.modified : "");
            snprintf(selected.attributes, sizeof(selected.attributes), "%s", entry.attributes ? entry.attributes : "");
        }
        selection = &selected;
    }
    /* Selection and listing pointers are borrowed only until this synchronous
     * formatter returns; the modal dialog receives its own complete text. */
    message = xfu_information_text(archive, ui->listed_entries, ui->listed_count,
                                   selection, ui->advanced_visible != 0);
    if (message) {
        xfu_native_shell_information(ui->window, message); free(message);
    } else show_status(ui, "Cannot allocate archive information.");
    free(archive);
}

static void native_action(void *user, xfu_shell_action action, const char *path)
{
    ui_state *ui = (ui_state *)user;
    if (action == XFU_SHELL_OPEN_PATH) {
        if (!ui->job && !ui->closing && path) {
            xxwidgets_widget_set_text(ui->archive_path, path); ui->pending_command = XFU_COMMAND_LIST;
        }
    } else ui->pending_action = action;
}

static void run_native_action(ui_state *ui)
{
    xfu_shell_action action = ui->pending_action;
    ui->pending_action = 0;
    if (action == XFU_SHELL_QUIT) {
        ui->closing = 1; if (ui->job) cancel_job(ui); else ui->running = 0; return;
    }
    if (action == XFU_SHELL_CANCEL) { cancel_job(ui); return; }
    if (action == XFU_SHELL_OPTIONS) { show_options(ui); return; }
    if (action == XFU_SHELL_LOG) {
        int visible = !ui->log_visible;
        if (xxwidgets_settings_set_bool(ui->settings, UI_SETTING_LOG, visible) == XXWIDGETS_OK) {
            ui->log_visible = visible; layout(ui, ui->columns, ui->rows);
        } else show_status(ui, "Cannot save the operation log setting.");
        return;
    }
    if (action == XFU_SHELL_COPY) { native_copy_path(ui); return; }
    if (action == XFU_SHELL_INFO) { native_information(ui); return; }
    if (action == XFU_SHELL_FORMATS) { show_supported_types(ui); return; }
    if (action == XFU_SHELL_ABOUT) {
        if (xxwidgets_about_dialog_show(ui->about, ui->window) != XXWIDGETS_OK)
            show_status(ui, "Cannot show the About dialog.");
        return;
    }
    if (ui->job || ui->closing) return;
    if (ui->selected_type == XX_FILE_TYPE_BINARY &&
        (action == XFU_SHELL_EXTRACT || action == XFU_SHELL_EXTRACT_SELECTED || action == XFU_SHELL_TEST)) {
        show_status(ui, "Binary cannot be opened as an archive. Choose an archive file type."); return;
    }
    if (action == XFU_SHELL_EXTRACT || action == XFU_SHELL_TEST || action == XFU_SHELL_REFRESH) {
        char *path = widget_text(ui->archive_path);
        int present = path && path[0];
        free(path);
        if (!present) { show_status(ui, "Open an archive first."); return; }
    }
    if (action == XFU_SHELL_OPEN) {
        if (browse_file(ui, ui->archive_path)) ui->pending_command = XFU_COMMAND_LIST;
    } else if (action == XFU_SHELL_EXTRACT) native_extract_archive(ui, 0);
    else if (action == XFU_SHELL_EXTRACT_SELECTED) native_extract_archive(ui, 1);
    else if (action == XFU_SHELL_TEST) ui->pending_command = XFU_COMMAND_TEST;
    else if (action == XFU_SHELL_REFRESH) ui->pending_command = XFU_COMMAND_LIST;
    else if (action == XFU_SHELL_ROOT) {
        xxwidgets_archivebrowser_set_directory(ui->members, ""); update_metadata(ui);
    } else if (action == XFU_SHELL_UP) {
        xxwidgets_archivebrowser_up(ui->members); update_metadata(ui);
    } else if (action == XFU_SHELL_ENTER_FOLDER) {
        xxwidgets_archive_browser_entry entry;
        size_t source;
        if (xxwidgets_archivebrowser_get_selection(ui->members, &source, &entry) == XXWIDGETS_OK &&
            entry.path && entry.is_directory) {
            xxwidgets_archivebrowser_set_directory(ui->members, entry.path); update_metadata(ui);
        }
    }
}
static int install_native_shortcuts(ui_state *ui)
{
    static const struct { const char *name, *sequence; xfu_shell_action action; } definitions[] = {
        {"open", "Ctrl+O", XFU_SHELL_OPEN},
        {"extract", "Ctrl+E", XFU_SHELL_EXTRACT},
        {"extract_selected", "Ctrl+Shift+E", XFU_SHELL_EXTRACT_SELECTED},
        {"test", "Ctrl+T", XFU_SHELL_TEST}, {"copy_path", "Ctrl+Shift+C", XFU_SHELL_COPY},
        {"information", "Alt+Enter", XFU_SHELL_INFO}, {"log", "Ctrl+L", XFU_SHELL_LOG},
        {"cancel", "Escape", XFU_SHELL_CANCEL}, {"quit", "Ctrl+Q", XFU_SHELL_QUIT},
        {"root", "Ctrl+Home", XFU_SHELL_ROOT}, {"refresh", "F5", XFU_SHELL_REFRESH},
        {"about", "F1", XFU_SHELL_ABOUT}, {"options", "Ctrl+Comma", XFU_SHELL_OPTIONS}
    };
    xx_shortcut defaults[sizeof(definitions) / sizeof(definitions[0])];
    xxwidgets_shortcut_action actions[sizeof(definitions) / sizeof(definitions[0])];
    xxwidgets_shortcut fallback[sizeof(definitions) / sizeof(definitions[0])];
    xx_shortcuts *loaded = NULL;
    xxwidgets_status installed = XXWIDGETS_PLATFORM_ERROR;
    wchar_t *path = NULL, *slash;
    char *utf8 = NULL;
    size_t count = sizeof(definitions) / sizeof(definitions[0]);
    for (size_t i = 0; i < count; ++i) {
        defaults[i].action = actions[i].name = definitions[i].name;
        defaults[i].sequence = fallback[i].sequence = definitions[i].sequence;
        actions[i].action = fallback[i].action = definitions[i].action;
    }
    if (ui->smoke) return xxwidgets_window_set_shortcuts(ui->window, fallback, count) == XXWIDGETS_OK;
    path = (wchar_t *)calloc(32768, sizeof(*path));
    if (path) {
        DWORD length = GetModuleFileNameW(NULL, path, 32768);
        slash = length && length < 32768 ? wcsrchr(path, L'\\') : NULL;
        if (slash && (size_t)(slash - path) + 15 < 32768) {
            wcscpy(slash + 1, L"shortcuts.ini"); utf8 = wide_utf8(path);
        }
    }
    if (utf8 && xx_shortcuts_load(utf8, defaults, count, &loaded) == XXFC_OK)
        installed = xxwidgets_settings_install_shortcuts(ui->window, loaded, actions, count);
    xx_shortcuts_destroy(loaded); free(utf8); free(path);
    if (installed == XXWIDGETS_OK) return 1;
    show_status(ui, "Cannot apply shortcuts.ini. Using default shortcuts.");
    return xxwidgets_window_set_shortcuts(ui->window, fallback, count) == XXWIDGETS_OK;
}
#endif

/* Smallest grid the classic layout arranges; smaller windows and terminals
 * are laid out at this size. */
#define CLASSIC_MIN_COLUMNS 76
#define CLASSIC_MIN_ROWS 23

static void rect(xxwidgets_widget *widget, int x, int y, int width, int height)
{
    xxwidgets_rect bounds = { x, y, width > 0 ? width : 1, height > 0 ? height : 1 };
    xxwidgets_widget_set_rect(widget, bounds);
}

static void layout(ui_state *ui, int columns, int rows)
{
    int extra, archive_height, log_height, metadata_y, progress_y;
    int native_browse = ui->backend == XXWIDGETS_BACKEND_NATIVE;
    int browse_width;
    if (desktop_shell(ui)) {
        xxwidgets_widget *hidden[] = {
            ui->archive_label, ui->archive_path, ui->archive_browse, ui->output_label, ui->output_dir,
            ui->members_label, ui->quit, ui->help,
            ui->log_toggle, ui->cancel, ui->options, ui->about_button, ui->formats_button
        };
        xxwidgets_widget *toolbar[] = { ui->open, ui->extract, ui->test,
            ui->copy_path, ui->info };
        size_t i;
        int log_rows, detail_rows;
        if (columns < 96) columns = 96;
        if (rows < 20) rows = 20;
        ui->columns = columns; ui->rows = rows;
        for (i = 0; i < sizeof(hidden) / sizeof(hidden[0]); ++i)
            xxwidgets_widget_set_visible(hidden[i], 0);
        for (i = 0; i < sizeof(toolbar) / sizeof(toolbar[0]); ++i)
            rect(toolbar[i], 1 + (int)i * 10, 0, 9, 3);
        {
            int type_width = columns < 104 ? columns - 80 : 24;
            rect(ui->type_label, 52, 1, 10, 1);
            rect(ui->file_type, 62, 1, type_width, 1);
            rect(ui->advanced, 63 + type_width, 1, 16, 1);
        }
        rect(ui->password_label, 1, 3, 21, 1);
        rect(ui->password, 22, 3, columns - 41, 1);
        rect(ui->get_password, columns - 17, 3, 16, 1);
        log_rows = ui->log_visible ? 7 : 0;
        detail_rows = ui->advanced_visible ? (rows - log_rows - 10 < 6 ? rows - log_rows - 10 : 6) : 0;
        rect(ui->members, 0, 4, columns, rows - 5 - log_rows - detail_rows);
        xxwidgets_widget_set_visible(ui->details, ui->advanced_visible);
        if (ui->advanced_visible) rect(ui->details, 1, rows - 1 - detail_rows - log_rows, columns - 2, detail_rows);
        xxwidgets_widget_set_visible(ui->log_label, ui->log_visible);
        xxwidgets_widget_set_visible(ui->log, ui->log_visible);
        if (ui->log_visible) {
            rect(ui->log_label, 1, rows - 8, columns - 2, 1);
            rect(ui->log, 1, rows - 7, columns - 2, 6);
        }
        rect(ui->metadata, 1, rows - 1, columns - 40, 1);
        rect(ui->status, ui->busy ? 1 : columns - 38, rows - 1,
            ui->busy ? columns - 30 : 37, 1);
        rect(ui->progress, columns - 28, rows - 1, 27, 1);
        xxwidgets_widget_set_visible(ui->metadata, !ui->busy);
        xxwidgets_widget_set_visible(ui->progress, ui->busy);
        return;
    }
#ifndef _WIN32
    /* Win32 browses with its common dialog; other desktops need a native chooser. */
    if (!xxwidgets_file_dialog_available(ui->app)) native_browse = 0;
#endif
    if (columns < CLASSIC_MIN_COLUMNS) columns = CLASSIC_MIN_COLUMNS;
    if (rows < CLASSIC_MIN_ROWS) rows = CLASSIC_MIN_ROWS;
    ui->columns = columns; ui->rows = rows;
    browse_width = native_browse ? 11 : 0;
    rect(ui->archive_label, 1, 0, 9, 1);
    rect(ui->archive_path, 10, 0, columns - 11 - browse_width, 1);
    rect(ui->archive_browse, columns - 11, 0, 10, 1);
    xxwidgets_widget_set_visible(ui->archive_browse, native_browse);
    rect(ui->output_label, 1, 1, 9, 1);
    rect(ui->output_dir, 10, 1, columns - 40, 1);
    rect(ui->type_label, columns - 29, 1, 10, 1);
    rect(ui->file_type, columns - 19, 1, 18, 1);
    rect(ui->password_label, 1, 2, 21, 1);
    rect(ui->password, 22, 2, columns - 41, 1);
    rect(ui->get_password, columns - 17, 2, 16, 1);
    rect(ui->open, 1, 3, 11, 1);
    rect(ui->extract, 13, 3, 13, 1);
    rect(ui->test, 27, 3, 10, 1);
    rect(ui->cancel, 38, 3, 10, 1);
    rect(ui->quit, 49, 3, 10, 1);
    rect(ui->advanced, columns - 17, 5, 16, 1);
    rect(ui->options, columns - 30, 5, 12, 1);
    rect(ui->about_button, columns - 41, 5, 10, 1);
    rect(ui->formats_button, columns - 57, 5, 15, 1);
    xxwidgets_widget_set_visible(ui->details, ui->advanced_visible);
    /* Rows 0-5 hold the fields, buttons and the members heading; the rest is
     * members, metadata, optional details, progress, status, log and help. */
    extra = rows - 23;
    log_height = 2 + extra / 4;
    archive_height = rows - 12 - log_height;
    if (ui->advanced_visible) archive_height -= 3;
    metadata_y = 6 + archive_height;
    progress_y = metadata_y + 2 + (ui->advanced_visible ? 3 : 0);
    rect(ui->members_label, 1, 5, columns - 59, 1);
    rect(ui->members, 1, 6, columns - 2, archive_height);
    rect(ui->metadata, 1, metadata_y, columns - 2, 1);
    if (ui->advanced_visible) rect(ui->details, 1, metadata_y + 1, columns - 2, 3);
    rect(ui->progress, 1, progress_y, columns - 2, 1);
    rect(ui->status, 1, progress_y + 1, columns - 2, 1);
    rect(ui->log_label, 1, progress_y + 2, columns - 2, 1);
    rect(ui->log, 1, progress_y + 3, columns - 2, log_height);
    rect(ui->help, 1, rows - 1, columns - 2, 1);
}

static void resize_native(ui_state *ui)
{
#ifdef _WIN32
    RECT bounds;
    if (ui->layout_ready && ui->backend == XXWIDGETS_BACKEND_NATIVE && ui->cell_width && ui->cell_height &&
        GetClientRect((HWND)xxwidgets_widget_native_handle(ui->window), &bounds))
        layout(ui, (bounds.right - bounds.left) / ui->cell_width,
               (bounds.bottom - bounds.top) / ui->cell_height);
#elif defined(__APPLE__)
    /* AppKit rounds window sizes to the nearest cell and is left as it was. */
    (void)ui;
#else
    /* The backend has already converted the new window size to cells. */
    xxwidgets_rect bounds;
    if (ui->layout_ready && ui->backend == XXWIDGETS_BACKEND_NATIVE &&
        xxwidgets_widget_get_rect(ui->window, &bounds) == XXWIDGETS_OK &&
        (bounds.width != ui->window_columns || bounds.height != ui->window_rows)) {
        ui->window_columns = bounds.width;
        ui->window_rows = bounds.height;
        layout(ui, bounds.width, bounds.height);
    }
#endif
}

static void resize_terminal(ui_state *ui)
{
    int columns = 80, rows = 25;
    xxwidgets_rect bounds;
    if (ui->backend != XXWIDGETS_BACKEND_TUI) return;
#ifdef _WIN32
    HANDLE output = CreateFileW(L"CONOUT$", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                               NULL, OPEN_EXISTING, 0, NULL);
    CONSOLE_SCREEN_BUFFER_INFO info;
    if (output != INVALID_HANDLE_VALUE) {
        if (GetConsoleScreenBufferInfo(output, &info)) {
            columns = info.srWindow.Right - info.srWindow.Left + 1;
            rows = info.srWindow.Bottom - info.srWindow.Top + 1;
        }
        CloseHandle(output);
    }
#else
    struct winsize size;
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &size) == 0 && size.ws_col && size.ws_row) {
        columns = size.ws_col; rows = size.ws_row;
    }
#endif
    columns -= 2; rows -= 2;
    if (columns < CLASSIC_MIN_COLUMNS) columns = CLASSIC_MIN_COLUMNS;
    if (rows < CLASSIC_MIN_ROWS) rows = CLASSIC_MIN_ROWS;
    if (columns == ui->columns && rows == ui->rows) return;
    bounds.x = bounds.y = 0; bounds.width = columns; bounds.height = rows;
    xxwidgets_widget_set_rect(ui->window, bounds);
    layout(ui, columns, rows);
}

static int queue_password_retrieval(ui_state *ui)
{
    char *path;
    if (ui->job || ui->closing) return 0;
    path = widget_text(ui->archive_path);
    if (!path || !path[0]) {
        free(path); show_status(ui, "Enter an archive path before retrieving its password."); return 0;
    }
    free(path);
    ui->pending_password_retrieval = 1;
    ui->pending_command = XFU_COMMAND_LIST;
    return 1;
}

static void on_event(xxwidgets_app *app, const xxwidgets_event *event, void *user)
{
    ui_state *ui = (ui_state *)user;
    (void)app;
#ifndef _WIN32
    if (!ui->job && !ui->closing &&
        ((event->type == XXWIDGETS_EVENT_CLICK &&
          (event->widget == ui->open || event->widget == ui->extract || event->widget == ui->test ||
           event->widget == ui->archive_browse || event->widget == ui->get_password)) ||
         (event->type == XXWIDGETS_EVENT_ACTIVATE && event->widget == ui->archive_path) ||
         (event->type == XXWIDGETS_EVENT_SELECT && event->widget == ui->file_type))) {
        /* Before the action reads them, so Browse, File type and the job all
         * see the same path. */
        expand_home_field(ui->archive_path);
        expand_home_field(ui->output_dir);
    }
#endif
    if (event->type == XXWIDGETS_EVENT_CLICK && event->widget == ui->get_password) {
        ui->busy_focus = ui->get_password;
        queue_password_retrieval(ui);
    } else if (event->type == XXWIDGETS_EVENT_CHANGE && event->widget == ui->password) {
        password_edited(ui);
    } else if (event->type == XXWIDGETS_EVENT_CHANGE && event->widget == ui->archive_path && ui->password) {
        char *path = widget_text(ui->archive_path);
        if (!path || !password_archive_changed(ui, path)) show_status(ui, "Cannot reset the archive password.");
        free(path);
    } else if (event->type == XXWIDGETS_EVENT_SHORTCUT && event->widget == ui->window) {
#ifdef _WIN32
        if (desktop_shell(ui)) ui->pending_action = (xfu_shell_action)event->value;
#endif
    } else if (event->widget == ui->file_type && event->type == XXWIDGETS_EVENT_SELECT &&
               !ui->job && !ui->closing) {
        xx_var value = {0};
        ui->busy_focus = ui->file_type;
        if (xxwidgets_combobox_get_current(ui->file_type, &value) == XXWIDGETS_OK &&
            value.type == XX_VAR_TYPE_UINT32) {
            char *path = widget_text(ui->archive_path);
            if (!path) { show_status(ui, "Cannot read the file path."); return; }
            free(ui->pending_type_path); ui->pending_type_path = path;
            ui->selected_type = (xx_file_type_t)value.val.u32;
            if (!clear_members(ui)) show_status(ui, "Cannot clear the previous archive listing.");
            ui->pending_extract_selected = 0;
            ui->pending_command = XFU_COMMAND_LIST;
        }
    } else if (event->type == XXWIDGETS_EVENT_CLOSE ||
        (event->type == XXWIDGETS_EVENT_CLICK && event->widget == ui->quit)) {
        ui->closing = 1;
        if (ui->job) cancel_job(ui);
        else ui->running = 0;
    } else if (event->widget == ui->advanced &&
               (event->type == XXWIDGETS_EVENT_CHANGE || event->type == XXWIDGETS_EVENT_CLICK)) {
        int checked = 0;
        if (xxwidgets_widget_get_value(ui->advanced, &checked) != XXWIDGETS_OK) return;
        change_advanced(ui, checked);
    } else if (event->type == XXWIDGETS_EVENT_CLICK && event->widget == ui->options) {
        ui->options_requested = 1;
    } else if (event->type == XXWIDGETS_EVENT_CLICK && event->widget == ui->about_button) {
        ui->about_requested = 1;
    } else if (event->type == XXWIDGETS_EVENT_CLICK && event->widget == ui->formats_button) {
        ui->formats_requested = 1;
    } else if (event->type == XXWIDGETS_EVENT_RESIZE && event->widget == ui->window) {
        resize_native(ui);
    } else if ((event->type == XXWIDGETS_EVENT_SELECT || event->type == XXWIDGETS_EVENT_CHANGE) && event->widget == ui->members) {
        update_metadata(ui);
    } else if (event->type == XXWIDGETS_EVENT_ACTIVATE && event->widget == ui->archive_path) {
        if (!ui->job && !ui->closing) {
            ui->pending_command = XFU_COMMAND_LIST;
            ui->busy_focus = ui->archive_path;
        }
    } else if (event->type == XXWIDGETS_EVENT_ACTIVATE && event->widget == ui->members) {
#ifdef _WIN32
        if (desktop_shell(ui)) ui->pending_action = XFU_SHELL_INFO;
#endif
    } else if (event->type == XXWIDGETS_EVENT_CONTEXT_MENU && event->widget == ui->members) {
#ifdef _WIN32
        if (desktop_shell(ui) && !ui->closing) {
            ui->context_x = event->x; ui->context_y = event->y;
            ui->context_pending = 1;
        }
#endif
    } else if (event->type == XXWIDGETS_EVENT_CLICK) {
#ifdef _WIN32
        if (desktop_shell(ui)) {
            if (event->widget == ui->open) ui->pending_action = XFU_SHELL_OPEN;
            else if (event->widget == ui->extract) ui->pending_action = XFU_SHELL_EXTRACT;
            else if (event->widget == ui->test) ui->pending_action = XFU_SHELL_TEST;
            else if (event->widget == ui->copy_path) ui->pending_action = XFU_SHELL_COPY;
            else if (event->widget == ui->info) ui->pending_action = XFU_SHELL_INFO;
            else if (event->widget == ui->log_toggle) ui->pending_action = XFU_SHELL_LOG;
            else if (event->widget == ui->cancel) ui->pending_action = XFU_SHELL_CANCEL;
            return;
        }
#endif
        if (event->widget == ui->cancel) cancel_job(ui);
        else if (!ui->job && !ui->closing) {
            if (event->widget == ui->open) ui->pending_command = XFU_COMMAND_LIST;
            else if (event->widget == ui->extract) ui->pending_command = XFU_COMMAND_EXTRACT;
            else if (event->widget == ui->test) ui->pending_command = XFU_COMMAND_TEST;
            else if (event->widget == ui->archive_browse) ui->browse_requested = 1;
            if (event->widget == ui->open || event->widget == ui->extract || event->widget == ui->test ||
                event->widget == ui->archive_browse) ui->busy_focus = event->widget;
        }
    }
}

static int select_source_member(ui_state *ui, size_t source)
{
    size_t row;
    if (source >= ui->listed_count || !ui->listed_entries[source].name) return 0;
    if (xxwidgets_widget_kind(ui->members) == XXWIDGETS_ARCHIVEBROWSER) {
        const char *name = ui->listed_entries[source].name;
        size_t end = strlen(name), parent = 0, i, count;
        char *directory;
        xxwidgets_status status;
        /* Ignore a directory record's trailing slash when finding its parent.
         * Select by original source index so synthesized folders never stand
         * in for a real member's password metadata. */
        while (end && (name[end - 1] == '/' || name[end - 1] == '\\')) --end;
        for (i = 0; i < end; ++i) if (name[i] == '/' || name[i] == '\\') parent = i + 1;
        directory = (char *)malloc(parent + 1);
        if (!directory) return 0;
        memcpy(directory, name, parent); directory[parent] = 0;
        status = xxwidgets_archivebrowser_set_directory(ui->members, directory);
        free(directory);
        if (status != XXWIDGETS_OK) return 0;
        count = xxwidgets_archivebrowser_visible_count(ui->members);
        for (row = 0; row < count; ++row) {
            xxwidgets_archive_browser_entry entry;
            size_t index;
            if (xxwidgets_archivebrowser_get_entry(ui->members, row, &index, &entry) != XXWIDGETS_OK) return 0;
            if (index == source) break;
        }
        if (row == count) return 0;
    } else row = source;
    if (row > INT_MAX || xxwidgets_widget_set_value(ui->members, (int)row) != XXWIDGETS_OK) return 0;
    update_metadata(ui); return 1;
}

static int finish_password_retrieval(ui_state *ui, const ui_job *job)
{
    size_t source = job->retrieve_member;
    int manual = ui->password_manual;
    if (source == SIZE_MAX) {
        for (source = 0; source < ui->listed_count; ++source)
            if (ui->listed_entries[source].embedded_password) break;
    } else if (source >= ui->listed_count || !job->retrieve_member_name ||
               strcmp(job->retrieve_member_name, ui->listed_entries[source].name)) {
        show_status(ui, "Selected member changed; existing password input kept."); return 1;
    }
    if (source < ui->listed_count && !select_source_member(ui, source)) {
        show_status(ui, "Cannot restore the selected member; existing password input kept."); return 2;
    }
    if (source >= ui->listed_count || !ui->listed_entries[source].embedded_password) {
        show_status(ui, job->retrieve_member == SIZE_MAX ? "No embedded password is available; existing input kept." :
                    "The selected member has no embedded password; existing input kept.");
        return 1;
    }
    ui->password_manual = 0;
    if (!set_automatic_password(ui, ui->listed_entries[source].embedded_password)) {
        ui->password_manual = manual;
        show_status(ui, "Cannot display the recovered password; existing input kept."); return 2;
    }
    show_status(ui, "Password retrieved; automatic member recovery restored.");
    return 0;
}

static void smoke_retrieval_finished(ui_state *ui, const ui_job *job, int result)
{
    char *value = NULL;
    int okay = password_snapshot(ui, &value);
    if (result == 0) {
        char *display, *field, *caption;
        int escaped = 0;
        okay = okay && !ui->password_manual && ui->automatic_password && value &&
            !strcmp(value, ui->automatic_password) && !job->request.password;
        if (job->retrieve_member != SIZE_MAX)
            okay = okay && job->retrieve_member < ui->listed_count &&
                ui->listed_entries[job->retrieve_member].embedded_password &&
                !strcmp(value, ui->listed_entries[job->retrieve_member].embedded_password);
        display = password_display(value ? value : "", &escaped);
        field = widget_text(ui->password); caption = widget_text(ui->password_label);
        okay = okay && display && field && caption && !strcmp(display, field) &&
            !strcmp(caption, escaped ? "Password (escaped):" : "Password:");
        free_password(display); free_password(field); free(caption);
    } else {
        const char *expected = ui->password_smoke_stage ? "UI retrieve manual override ; \\x0A" : ui->password_smoke_expected;
        okay = okay && ((value == NULL) == (expected == NULL)) &&
            (!value || !strcmp(value, expected)) &&
            (expected == NULL || ui->password_manual);
    }
    free_password(value);
    if (ui->password_smoke_stage == 3 || ui->password_smoke_stage == 4) {
        /* The actual worker is deliberately invalidated/cancelled before
         * drain_job can consume it. Its result must not replace manual input. */
        if (!okay || result != 2 ||
            (ui->password_smoke_stage == 4 && !job->cancel_requested)) {
            ui->exit_code = 2; ui->running = 0; return;
        }
        ui->password_smoke_stage = ui->password_smoke_stage == 3 ? 4 : 6;
        ui->retrieve_smoke_click = 1;
        return;
    }
    if (!okay || result == 2) {
        ui->exit_code = job->result ? job->result : 2; ui->running = 0; return;
    }
    if (result == 1 && !ui->password_smoke_stage) {
        ui->exit_code = 1; ui->running = 0; return;
    }
    if (ui->password_smoke_stage == 6) {
        if (result != 0) { ui->exit_code = 2; ui->running = 0; return; }
        ui->password_smoke_stage = 2;
        ui->pending_command = XFU_COMMAND_TEST;
        return;
    }
    /* Retrieve one representative of each exact recovered group and one
     * member with no credential. This keeps real-corpus smoke runs bounded
     * without repeatedly reparsing hundreds of members from the same group. */
    while (ui->password_smoke_stage != 5 && ui->retrieve_smoke_member < ui->listed_count) {
        size_t source = ui->retrieve_smoke_member++, previous;
        const char *raw = ui->listed_entries[source].embedded_password;
        for (previous = 0; previous < source; ++previous) {
            const char *other = ui->listed_entries[previous].embedded_password;
            if ((!raw && !other) || (raw && other && !strcmp(raw, other))) break;
        }
        if (previous != source) continue;
        if (!select_source_member(ui, source) ||
            xxwidgets_widget_set_text(ui->password, "UI retrieve manual override ; \\x0A") != XXWIDGETS_OK) {
            ui->exit_code = 2; ui->running = 0; return;
        }
        password_edited(ui);
        ui->password_smoke_stage = 1;
        /* Dispatch the real button event once drain_job releases its worker. */
        ui->retrieve_smoke_click = 1;
        return;
    }
    if (result != 0) {
        /* The last checked member may have no credential. Pick a verified
         * group explicitly before the final no-output test operation. */
        size_t source;
        for (source = 0; source < ui->listed_count; ++source)
            if (ui->listed_entries[source].embedded_password) break;
        if (source == ui->listed_count) { ui->exit_code = 2; ui->running = 0; return; }
        if (!select_source_member(ui, source)) {
            ui->exit_code = 2; ui->running = 0; return;
        }
        ui->password_smoke_stage = 5;
        ui->retrieve_smoke_click = 1;
        return;
    }
    if (xxwidgets_widget_set_text(ui->password, "UI retrieve manual override ; \\x0A") != XXWIDGETS_OK) {
        ui->exit_code = 2; ui->running = 0; return;
    }
    password_edited(ui);
    ui->password_smoke_stage = 3;
    ui->retrieve_smoke_click = 1;
}

/* Staged tests drive the real editor and ordinary list/test/extract job paths.
 * No password bytes are written to diagnostic logs. */
static int smoke_password_listing(ui_state *ui)
{
    size_t i;
    char *value = NULL;
    int have_password = 0;
    if (!ui->password || xxwidgets_widget_kind(ui->password) != XXWIDGETS_EDIT) return 0;
    if (ui->password_smoke == 2) {
        for (i = 0; i < ui->listed_count; ++i)
            if (ui->listed_entries[i].embedded_password) return 0;
        if (!password_snapshot(ui, &value)) return 0;
        i = (value == NULL) == (ui->password_smoke_expected == NULL) &&
            (!value || !strcmp(value, ui->password_smoke_expected));
        free_password(value); return i != 0;
    }
    /* The normal listing replacement must reset navigation to archive root,
     * even when the preceding pass selected a nested member. */
    if (ui->password_smoke_stage == 1 &&
        xxwidgets_widget_kind(ui->members) == XXWIDGETS_ARCHIVEBROWSER &&
        xxwidgets_archivebrowser_directory(ui->members)[0]) return 0;
    for (i = 0; i < ui->listed_count; ++i)
        if (ui->listed_entries[i].embedded_password) have_password = 1;
    for (i = 0; i < ui->listed_count; ++i) {
        const char *raw = ui->listed_entries[i].embedded_password;
        char *display, *field;
        int escaped, same;
        if (!select_source_member(ui, i) || !password_snapshot(ui, &value)) return 0;
        if (!raw) {
            /* Clear members/directories may coexist with protected payloads.
             * They have no replacement credential; retain the current auto
             * value. An entirely clear archive must have no auto value. */
            if ((!have_password && value) ||
                (value && (!ui->automatic_password || strcmp(value, ui->automatic_password)))) {
                free_password(value); return 0;
            }
            free_password(value); value = NULL;
            continue;
        }
        display = password_display(raw, &escaped);
        field = widget_text(ui->password);
        same = value && display && field && !strcmp(value, raw) && !strcmp(field, display);
        free_password(value); value = NULL;
        free_password(display); free_password(field);
        if (!same) return 0;
    }
    if (ui->password_smoke_stage == 0) {
        const char *manual = "UI manual override ; \\x0A";
        char *archive = widget_text(ui->archive_path);
        xxwidgets_event edit = {XXWIDGETS_EVENT_CHANGE, ui->password, 0, 0, 0};
        xxwidgets_event change = {XXWIDGETS_EVENT_CHANGE, ui->archive_path, 0, 0, 0};
        int okay = 1;
        if (!archive || xxwidgets_widget_set_text(ui->password, manual) != XXWIDGETS_OK) { free(archive); return 0; }
        on_event(ui->app, &edit, ui);
        for (i = 0; i < ui->listed_count; ++i) {
            if (!select_source_member(ui, i) || !password_snapshot(ui, &value)) { okay = 0; break; }
            if (!value || strcmp(value, manual)) okay = 0;
            free_password(value); value = NULL;
            if (!okay) break;
        }
        /* Return from the explicit manual-edit test to automatic mode before
         * switching sources. This is test setup, not a user-facing reset flow. */
        ui->password_manual = 0;
        if (!set_automatic_password(ui, ui->listed_count ? ui->listed_entries[0].embedded_password : NULL) ||
            xxwidgets_widget_set_text(ui->archive_path, "password-smoke-other.zip") != XXWIDGETS_OK) okay = 0;
        on_event(ui->app, &change, ui);
        if (!password_snapshot(ui, &value) || value || ui->automatic_password || ui->password_listed_archive) okay = 0;
        free_password(value); value = NULL;
        if (xxwidgets_widget_set_text(ui->archive_path, archive) != XXWIDGETS_OK) okay = 0;
        on_event(ui->app, &change, ui);
        if (!password_snapshot(ui, &value) || value) okay = 0;
        free_password(value); free(archive);
        return okay;
    }
    return 1;
}

static xxwidgets_widget *create(ui_state *ui, xxwidgets_kind kind, const char *text)
{
    xxwidgets_widget *widget = NULL;
    xxwidgets_rect initial = { 1, 1, 10, 1 };
    if (xxwidgets_widget_create(ui->app, ui->window, kind, text, initial, &widget) != XXWIDGETS_OK)
        return NULL;
    return widget;
}

static int create_ui(ui_state *ui, const char *archive, const char *output)
{
    xxwidgets_rect bounds = { 0, 0, 78, 23 };
    xxwidgets_config config = { ui->backend, on_event, ui };
    if (ui->backend == XXWIDGETS_BACKEND_NATIVE) {
        bounds.x = bounds.y = 3; bounds.width = 112; bounds.height = 37;
        if (desktop_shell(ui)) { bounds.width = 160; bounds.height = 36; }
    }
    if (xxwidgets_app_create(&config, &ui->app) != XXWIDGETS_OK) return 0;
    if (xxwidgets_widget_create(ui->app, NULL, XXWIDGETS_WINDOW,
        "XFileUnpacker", bounds, &ui->window) != XXWIDGETS_OK) return 0;
#ifndef _WIN32
    /* The classic layout follows RESIZE, so the window may shrink to its
     * minimum. Should the backend refuse, the window only loses that limit. */
    if (ui->backend == XXWIDGETS_BACKEND_NATIVE)
        (void)xxwidgets_window_set_minimum_size(ui->window, CLASSIC_MIN_COLUMNS, CLASSIC_MIN_ROWS);
#endif
    if (!create_about(ui)) return 0;
    if (ui->smoke) xxwidgets_widget_set_visible(ui->window, 0);
    if (ui->backend == XXWIDGETS_BACKEND_NATIVE) xfu_set_application_icon(ui->window);
#define CONTROL(field, kind, text) do { ui->field = create(ui, kind, text); if (!ui->field) return 0; } while (0)
    CONTROL(archive_label, XXWIDGETS_LABEL, "Archive:");
    CONTROL(archive_path, XXWIDGETS_EDIT, archive);
    CONTROL(archive_browse, XXWIDGETS_BUTTON, "Browse...");
    /* Created in on-screen order, which is also the Tab order. */
    CONTROL(output_label, XXWIDGETS_LABEL, "Output:");
    CONTROL(output_dir, XXWIDGETS_EDIT, output);
    CONTROL(type_label, XXWIDGETS_LABEL, "File type:");
    CONTROL(file_type, XXWIDGETS_COMBOBOX, "Binary");
    CONTROL(password_label, XXWIDGETS_LABEL, "Password:");
    CONTROL(password, XXWIDGETS_EDIT, "");
    CONTROL(get_password, XXWIDGETS_BUTTON, "Get password");
    CONTROL(open, XXWIDGETS_BUTTON, desktop_shell(ui) ? "Open" : "Open (l)");
    CONTROL(extract, XXWIDGETS_BUTTON, desktop_shell(ui) ? "Extract" : "Extract (x)");
    CONTROL(test, XXWIDGETS_BUTTON, desktop_shell(ui) ? "Test" : "Test (t)");
    CONTROL(cancel, XXWIDGETS_BUTTON, "Cancel");
    CONTROL(quit, XXWIDGETS_BUTTON, "Quit");
    CONTROL(members_label, XXWIDGETS_LABEL, "Archive members");
    CONTROL(formats_button, XXWIDGETS_BUTTON, "File types...");
    CONTROL(about_button, XXWIDGETS_BUTTON, "About...");
    CONTROL(options, XXWIDGETS_BUTTON, "Options...");
    CONTROL(advanced, XXWIDGETS_CHECKBOX, "Advanced");
    CONTROL(members, ui->backend == XXWIDGETS_BACKEND_NATIVE ? XXWIDGETS_ARCHIVEBROWSER : XXWIDGETS_ARCHIVEVIEW, "");
    CONTROL(metadata, XXWIDGETS_LABEL, "No member selected.");
    CONTROL(details, XXWIDGETS_LISTBOX, "");
    CONTROL(progress, XXWIDGETS_PROGRESS, "");
    CONTROL(status, XXWIDGETS_LABEL, "Ready. Enter an archive path and select Open (l).");
    CONTROL(log_label, XXWIDGETS_LABEL, "Operation log");
    CONTROL(log, XXWIDGETS_LISTBOX, "");
    /* Escape quits only the terminal edition; a desktop window closes normally. */
    CONTROL(help, XXWIDGETS_LABEL, ui->backend == XXWIDGETS_BACKEND_NATIVE ?
        "Tab: next control | Enter: activate | Arrows: select" :
        "Tab: next control | Enter: activate | Arrows: select | Esc: quit");
    if (desktop_shell(ui)) {
        CONTROL(copy_path, XXWIDGETS_BUTTON, "Copy path");
        CONTROL(info, XXWIDGETS_BUTTON, "Info");
        CONTROL(log_toggle, XXWIDGETS_BUTTON, "Log");
        xxwidgets_archivebrowser_set_archive(ui->members, archive);
        xxwidgets_widget_set_text(ui->status, "Open an archive or drop it here.");
        xxwidgets_widget_set_text(ui->metadata, "0 objects");
    }
#undef CONTROL
    {
        ui_job initial = {0};
        initial.archive_path = ""; initial.file_types[0] = XX_FILE_TYPE_BINARY;
        initial.type_count = 1; initial.selected_type = XX_FILE_TYPE_BINARY;
        if (!populate_file_types(ui, &initial)) return 0;
    }
    if (xxwidgets_widget_set_value(ui->advanced, ui->advanced_visible) != XXWIDGETS_OK) return 0;
    if (xxwidgets_widget_kind(ui->members) == XXWIDGETS_ARCHIVEBROWSER &&
        xxwidgets_archivebrowser_set_advanced(ui->members, ui->advanced_visible) != XXWIDGETS_OK) return 0;
    layout(ui, bounds.width, bounds.height);
    ui->window_columns = bounds.width;
    ui->window_rows = bounds.height;
#ifdef _WIN32
    if (ui->backend == XXWIDGETS_BACKEND_NATIVE) {
        RECT client;
        if (GetClientRect((HWND)xxwidgets_widget_native_handle(ui->window), &client)) {
            ui->cell_width = (client.right - client.left) / bounds.width;
            ui->cell_height = (client.bottom - client.top) / bounds.height;
        }
    }
#endif
    ui->layout_ready = 1;
#ifdef _WIN32
    if (desktop_shell(ui)) {
        xfu_shell_button buttons[] = {
            {ui->open, XFU_SHELL_OPEN}, {ui->extract, XFU_SHELL_EXTRACT},
            {ui->test, XFU_SHELL_TEST}, {ui->copy_path, XFU_SHELL_COPY}, {ui->info, XFU_SHELL_INFO}
        };
        if (!xfu_native_shell_attach(ui->window, buttons, sizeof(buttons) / sizeof(buttons[0]),
                                     native_action, ui, &ui->shell)) return 0;
        resize_native(ui);
    }
#endif
    set_busy(ui, 0);
    if (!ui->smoke) xxwidgets_widget_focus(desktop_shell(ui) ? ui->members : ui->archive_path);
    return 1;
}

static void report(xxwidgets_backend backend, const char *message, int error)
{
#ifdef _WIN32
    if (backend == XXWIDGETS_BACKEND_NATIVE) {
        int length = MultiByteToWideChar(CP_UTF8, 0, message, -1, NULL, 0);
        wchar_t *wide = (wchar_t *)malloc((size_t)length * sizeof(*wide));
        if (wide) {
            MultiByteToWideChar(CP_UTF8, 0, message, -1, wide, length);
            MessageBoxW(NULL, wide, L"XFileUnpacker", MB_OK | (error ? MB_ICONERROR : MB_ICONINFORMATION));
            free(wide);
        }
        return;
    }
#else
    (void)backend;
#endif
    fprintf(error ? stderr : stdout, "%s\n", message);
}

static const char ui_usage[] =
    "XFileUnpacker -- unpack archives with xxfclib\n\n"
    "Usage: XFileUnpacker|xfut [<command>] [<archive>] [arguments]\n\n"
    "Commands (7-Zip letters):\n"
    "  x <archive> [-o<dir>]     Extract with full paths\n"
    "  l <archive>               List contents\n"
    "  t <archive>               Test archive contents in memory\n\n"
    "Without a command, an archive path opens its listing.\n"
    "-o<dir>: output directory for x (default: the current directory).\n"
    "-p<password>: initialize the editable Password field (-p for an empty password).\n"
    "Recovered passwords autofill unless edited; manual input is literal.\n"
    "Automatic values allow per-member recovery; explicit input overrides it.\n"
    "Password (escaped) displays controls/byte escapes while keeping the original credential.\n"
    "Opens existing archives only; create archives with: xfu a <archive> <file>...\n"
    "--help: show help. --smoke-test: hidden widget/backend lifecycle check.\n"
    "Tab navigates controls; Enter activates buttons; arrows select members.\n"
    "Cancel requests a safe stop, including while decoding a member.";

#ifdef _WIN32
typedef struct smoke_console {
    HANDLE input, output, inherited_input, inherited_output;
    int allocated;
} smoke_console;

static int smoke_console_create(smoke_console *console)
{
    console->input = console->output = INVALID_HANDLE_VALUE;
    console->inherited_input = GetStdHandle(STD_INPUT_HANDLE);
    console->inherited_output = GetStdHandle(STD_OUTPUT_HANDLE);
    /* An explicitly requested test owns a private, hidden terminal. */
    if (!AllocConsole()) {
        if (GetLastError() != ERROR_ACCESS_DENIED || !FreeConsole() || !AllocConsole()) return 0;
    }
    console->allocated = 1;
    if (GetConsoleWindow()) ShowWindow(GetConsoleWindow(), SW_HIDE);
    console->input = CreateFileW(L"CONIN$", GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    console->output = CreateFileW(L"CONOUT$", GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (console->input == INVALID_HANDLE_VALUE || console->output == INVALID_HANDLE_VALUE) return 0;
    return SetStdHandle(STD_INPUT_HANDLE, console->input) &&
           SetStdHandle(STD_OUTPUT_HANDLE, console->output) && FlushConsoleInputBuffer(console->input);
}

static void smoke_console_destroy(smoke_console *console)
{
    if (console->input != INVALID_HANDLE_VALUE) CloseHandle(console->input);
    if (console->output != INVALID_HANDLE_VALUE) CloseHandle(console->output);
    if (console->allocated) FreeConsole();
    SetStdHandle(STD_INPUT_HANDLE, console->inherited_input);
    SetStdHandle(STD_OUTPUT_HANDLE, console->inherited_output);
}
#endif

#ifdef _WIN32
typedef struct about_smoke_state {
    HWND owner;
    xxwidgets_app *app;
    int ticks, valid;
} about_smoke_state;

static BOOL CALLBACK smoke_find_about(HWND window, LPARAM result)
{
    wchar_t title[80];
    GetWindowTextW(window, title, 80);
    if (!wcscmp(title, L"About XFileUnpacker")) { *(HWND *)result = window; return FALSE; }
    return TRUE;
}

static VOID CALLBACK smoke_close_about(HWND unused, UINT message, UINT_PTR timer, DWORD time)
{
    about_smoke_state *state = (about_smoke_state *)timer;
    HWND dialog = NULL;
    wchar_t body[2048];
    (void)unused; (void)message; (void)time;
    EnumThreadWindows(GetCurrentThreadId(), smoke_find_about, (LPARAM)&dialog);
    if (!dialog) {
        if (++state->ticks >= 100) { KillTimer(state->owner, timer); xxwidgets_app_quit(state->app, 2); }
        return;
    }
    state->valid = !IsWindowEnabled(state->owner) && GetWindow(dialog, GW_OWNER) == state->owner &&
        GetWindowTextW(GetDlgItem(dialog, 101), body, 2048) && wcsstr(body, L"XFileUnpacker") &&
        wcsstr(body, L"Version ") && wcsstr(body, L"MIT License") && GetDlgItem(dialog, 102) &&
        SendMessageW(dialog, WM_GETICON, ICON_BIG, 0);
    KillTimer(state->owner, timer);
    PostMessageW(dialog, WM_CLOSE, 0, 0);
}

static BOOL CALLBACK smoke_find_formats(HWND window, LPARAM result)
{
    wchar_t title[80];
    GetWindowTextW(window, title, 80);
    if (!wcscmp(title, L"Supported file types")) { *(HWND *)result = window; return FALSE; }
    return TRUE;
}

static BOOL CALLBACK smoke_find_copy_button(HWND window, LPARAM result)
{
    wchar_t text[40];
    GetWindowTextW(window, text, 40);
    if (!wcscmp(text, L"Copy all")) { *(HWND *)result = window; return FALSE; }
    return TRUE;
}

static VOID CALLBACK smoke_close_formats(HWND unused, UINT message, UINT_PTR timer, DWORD time)
{
    about_smoke_state *state = (about_smoke_state *)timer;
    HWND dialog = NULL, copy = NULL, edit;
    wchar_t *body;
    int length;
    size_t lines = 0, count = 0, expected_lines = 0;
    char *expected;
    (void)unused; (void)message; (void)time;
    EnumThreadWindows(GetCurrentThreadId(), smoke_find_formats, (LPARAM)&dialog);
    if (!dialog) {
        if (++state->ticks >= 100) { KillTimer(state->owner, timer); xxwidgets_app_quit(state->app, 2); }
        return;
    }
    edit = GetDlgItem(dialog, 101);
    length = GetWindowTextLengthW(edit);
    body = length > 0 ? (wchar_t *)calloc((size_t)length + 1, sizeof(*body)) : NULL;
    expected = ui_supported_types_text(&count);
    EnumChildWindows(dialog, smoke_find_copy_button, (LPARAM)&copy);
    if (body && expected && GetWindowTextW(edit, body, length + 1)) {
        wchar_t *cursor;
        const char *expected_cursor;
        for (cursor = body; *cursor; ++cursor) if (*cursor == L'\n') ++lines;
        for (expected_cursor = expected; *expected_cursor; ++expected_cursor)
            if (*expected_cursor == '\n') ++expected_lines;
        state->valid = !IsWindowEnabled(state->owner) && GetWindow(dialog, GW_OWNER) == state->owner &&
            copy && IsWindowEnabled(copy) && (GetWindowLongPtrW(edit, GWL_STYLE) & ES_READONLY) &&
            wcsstr(body, L"Supported file types (xxfclib): ") && wcsstr(body, L"CPX4") &&
            wcsstr(body, L"TAR.GZ") && wcsstr(body, L"Xamarin compressed assembly (XALZ)") &&
            count > 1200 && wcsstr(body, L"Archive creation: 7z, ZIP, TAR, GZIP, BZIP2, XZ, WIM") &&
            lines == expected_lines;
    }
    free(body); free(expected);
    KillTimer(state->owner, timer);
    PostMessageW(dialog, WM_CLOSE, 0, 0);
}
#endif

static int smoke_widgets(ui_state *ui)
{
    xxwidgets_archive_entry entries[] = {
        { "folder/", 0, 1 }, { "folder/hello.txt", 123, 0 },
        { "Unicode-\xd0\xbf\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82.bin", UINT64_C(4294967297), 0 }
    }, selected;
    size_t index;
    char path[32];
    char *escaped = display_text("legacy-\x82\xff-\xc0\xaf-\xed\xa0\x80.txt");
    char *unicode = display_text(entries[2].path);
    int valid_display = escaped && unicode &&
        !strcmp(escaped, "legacy-\\x82\\xFF-\\xC0\\xAF-\\xED\\xA0\\x80.txt") &&
        !strcmp(unicode, entries[2].path);
    free(escaped); free(unicode);
    if (!valid_display) return 0;
    if (xxwidgets_app_backend(ui->app) != ui->backend) return 0;
    {
        char *snapshot = NULL;
        const char *raw = "smoke\nbyte\xff\\x0A";
        xxwidgets_status focused, hidden;
        if (!ui->password || xxwidgets_widget_kind(ui->password) != XXWIDGETS_EDIT ||
            !ui->get_password || xxwidgets_widget_kind(ui->get_password) != XXWIDGETS_BUTTON) return 0;
        /* xxwidgets intentionally rejects focus under a hidden owner. The
         * lifecycle smoke normally hides its window; make it visible only
         * for this actual backend focus check, then restore the test setup. */
        if (xxwidgets_widget_set_visible(ui->window, 1) != XXWIDGETS_OK) return 0;
        focused = xxwidgets_widget_focus(ui->password);
        if (focused != XXWIDGETS_OK || xxwidgets_widget_focus(ui->get_password) != XXWIDGETS_OK) return 0;
        set_busy(ui, 1);
        if (xxwidgets_widget_focus(ui->get_password) != XXWIDGETS_INVALID_ARGUMENT) return 0;
        set_busy(ui, 0);
        if (xxwidgets_widget_focus(ui->get_password) != XXWIDGETS_OK) return 0;
        hidden = xxwidgets_widget_set_visible(ui->window, 0);
        if (focused != XXWIDGETS_OK || hidden != XXWIDGETS_OK) return 0;
        if (!set_automatic_password(ui, raw) || !password_snapshot(ui, &snapshot)) return 0;
        if (!snapshot || strcmp(snapshot, raw)) { free_password(snapshot); return 0; }
        free_password(snapshot);
        if (xxwidgets_widget_set_text(ui->password, "manual literal \\x0A") != XXWIDGETS_OK) return 0;
        password_edited(ui);
        if (!password_snapshot(ui, &snapshot)) return 0;
        if (!snapshot || strcmp(snapshot, "manual literal \\x0A")) { free_password(snapshot); return 0; }
        free_password(snapshot);
        {
            xxwidgets_event event = {0};
            event.type = XXWIDGETS_EVENT_CLICK; event.widget = ui->get_password;
            /* An empty/unopened path cannot queue recovery or clear input. */
            on_event(ui->app, &event, ui);
            if (ui->pending_command != XFU_COMMAND_NONE || ui->pending_password_retrieval ||
                !password_snapshot(ui, &snapshot)) return 0;
            if (!snapshot || strcmp(snapshot, "manual literal \\x0A")) { free_password(snapshot); return 0; }
            free_password(snapshot);
        }
        ui->password_manual = 0;
        if (!set_automatic_password(ui, NULL)) return 0;
    }
    {
        int checked = 0;
        if (xx_get_settings() != ui->settings || !ui->advanced_visible || !ui->log_visible ||
            xxwidgets_widget_get_value(ui->advanced, &checked) != XXWIDGETS_OK || !checked) return 0;
    }
#ifdef _WIN32
    if (desktop_shell(ui)) {
        HWND window = (HWND)xxwidgets_widget_native_handle(ui->window);
        HMENU tools = GetSubMenu(GetMenu(window), 2);
        int count = GetMenuItemCount(tools);
        UINT command = count > 0 ? GetMenuItemID(tools, count - 1) : (UINT)-1;
        wchar_t label[32];
        if (command == (UINT)-1 || !GetMenuStringW(tools, command, label, 32, MF_BYCOMMAND) ||
            wcscmp(label, L"&Options...")) return 0;
        SendMessageW(window, WM_COMMAND, (WPARAM)command, 0);
        if (ui->pending_action != XFU_SHELL_OPTIONS) return 0;
        ui->pending_action = 0;
        {
            HMENU help = GetSubMenu(GetMenu(window), 3);
            about_smoke_state about = {window, ui->app, 0, 0};
            UINT command_about = GetMenuItemID(help, GetMenuItemCount(help) - 1);
            if (command_about == (UINT)-1) return 0;
            SendMessageW(window, WM_COMMAND, (WPARAM)command_about, 0);
            if (ui->pending_action != XFU_SHELL_ABOUT ||
                !SetTimer(window, (UINT_PTR)&about, 20, smoke_close_about)) return 0;
            run_native_action(ui);
            KillTimer(window, (UINT_PTR)&about);
            if (!about.valid || !IsWindowEnabled(window)) return 0;
        }
        {
            HMENU help = GetSubMenu(GetMenu(window), 3);
            about_smoke_state formats = {window, ui->app, 0, 0};
            UINT command_formats = GetMenuItemID(help, 0);
            wchar_t formats_label[80];
            if (command_formats == (UINT)-1 || !GetMenuStringW(help, command_formats, formats_label, 80, MF_BYCOMMAND) ||
                wcscmp(formats_label, L"&Supported file types...")) return 0;
            SendMessageW(window, WM_COMMAND, (WPARAM)command_formats, 0);
            if (ui->pending_action != XFU_SHELL_FORMATS ||
                !SetTimer(window, (UINT_PTR)&formats, 20, smoke_close_formats)) return 0;
            run_native_action(ui);
            KillTimer(window, (UINT_PTR)&formats);
            if (!formats.valid || !IsWindowEnabled(window)) return 0;
        }
        ui->pending_action = XFU_SHELL_LOG; run_native_action(ui);
        if (ui->log_visible || xxwidgets_settings_get_bool(ui->settings, UI_SETTING_LOG, 1)) return 0;
        ui->pending_action = XFU_SHELL_LOG; run_native_action(ui);
        if (!ui->log_visible || !xxwidgets_settings_get_bool(ui->settings, UI_SETTING_LOG, 0)) return 0;
    }
#endif
#ifdef _WIN32
    if (ui->backend == XXWIDGETS_BACKEND_NATIVE &&
        (!SendMessageW((HWND)xxwidgets_widget_native_handle(ui->window), WM_GETICON, ICON_BIG, 0) ||
         !SendMessageW((HWND)xxwidgets_widget_native_handle(ui->window), WM_GETICON, ICON_SMALL, 0))) return 0;
#endif
    if (ui->backend == XXWIDGETS_BACKEND_NATIVE) {
        xxwidgets_archive_browser_entry members[3] = {0}, member;
        size_t i;
        for (i = 0; i < 3; ++i) {
            members[i].path = entries[i].path; members[i].size = entries[i].size;
            members[i].is_directory = entries[i].is_directory; members[i].flags = XXWIDGETS_ARCHIVE_SIZE_KNOWN;
        }
        if (xxwidgets_archivebrowser_set_entries(ui->members, members, 3) != XXWIDGETS_OK ||
            xxwidgets_archivebrowser_count(ui->members) != 3 ||
            xxwidgets_archivebrowser_visible_count(ui->members) != 2 ||
            xxwidgets_archivebrowser_set_directory(ui->members, "folder") != XXWIDGETS_OK ||
            xxwidgets_archivebrowser_visible_count(ui->members) != 1 ||
            xxwidgets_archivebrowser_get_selection(ui->members, &index, &member) != XXWIDGETS_OK ||
            index != 1 || member.size != 123 ||
            xxwidgets_archivebrowser_up(ui->members) != XXWIDGETS_OK ||
            xxwidgets_widget_set_value(ui->members, 1) != XXWIDGETS_OK ||
            xxwidgets_archivebrowser_get_selection(ui->members, &index, &member) != XXWIDGETS_OK ||
            index != 2 || member.size != UINT64_C(4294967297) ||
            xxwidgets_archivebrowser_set_entries(ui->members, NULL, 0) != XXWIDGETS_OK) return 0;
        {
            ui_job listing = {0};
            xfu_entry legacy = {0};
            int valid;
            listing.archive_path = "legacy.zip";
            legacy.name = "legacy-\x82\n.txt";
            job_entry(&listing, &legacy);
            valid = !listing.memory_error && populate_members(ui, &listing) &&
                xxwidgets_archivebrowser_visible_count(ui->members) == 1 &&
                xxwidgets_archivebrowser_get_selection(ui->members, &index, &member) == XXWIDGETS_OK &&
                index == 0 && !member.is_directory && !strcmp(member.path, "legacy-[82][0A].txt");
            free_entries(listing.entries, listing.entry_count);
            if (!valid || xxwidgets_archivebrowser_set_entries(ui->members, NULL, 0) != XXWIDGETS_OK) return 0;
        }
        {
            ui_job listing = {0};
            xfu_property properties[] = {{"CRC32", "75BCC38E"}, {"Method", "Deflate:Fastest"}};
            xfu_entry document = {0}, nested = {0};
            xxwidgets_event toggle = {XXWIDGETS_EVENT_CHANGE, ui->advanced, 1, 0, 0};
            document.name = "word/document.xml"; document.properties = properties; document.property_count = 2;
            nested.name = "word/theme/theme1.xml";
            listing.archive_path = "document.docx";
            job_entry(&listing, &document); job_entry(&listing, &nested);
            if (listing.memory_error || !populate_members(ui, &listing) ||
                xxwidgets_archivebrowser_visible_count(ui->members) != 1 ||
                xxwidgets_archivebrowser_set_directory(ui->members, "word") != XXWIDGETS_OK ||
                xxwidgets_archivebrowser_visible_count(ui->members) != 2 ||
                xxwidgets_widget_set_value(ui->members, 1) != XXWIDGETS_OK ||
                xxwidgets_widget_set_value(ui->advanced, 1) != XXWIDGETS_OK) {
                free_entries(listing.entries, listing.entry_count); return 0;
            }
            on_event(ui->app, &toggle, ui);
            if (!ui->advanced_visible || !xxwidgets_settings_get_bool(ui->settings, UI_SETTING_ADVANCED, 0) ||
                xxwidgets_archivebrowser_column_count(ui->members) != 7 ||
                xxwidgets_listbox_count(ui->details) != 2 ||
                strcmp(xxwidgets_archivebrowser_directory(ui->members), "word/") ||
                xxwidgets_archivebrowser_get_selection(ui->members, &index, &member) != XXWIDGETS_OK || index != 0)
                return 0;
            xxwidgets_widget_set_value(ui->advanced, 0); on_event(ui->app, &toggle, ui);
            if (ui->advanced_visible || xxwidgets_settings_get_bool(ui->settings, UI_SETTING_ADVANCED, 1) ||
                xxwidgets_archivebrowser_column_count(ui->members) != 5 ||
                xxwidgets_archivebrowser_get_selection(ui->members, &index, &member) != XXWIDGETS_OK || index != 0)
                return 0;
            {
                size_t rows[] = {0, 1}, sources[2], count = 0;
                if (xxwidgets_archivebrowser_set_selection(ui->members, rows, 2) != XXWIDGETS_OK ||
                    xxwidgets_archivebrowser_selection_count(ui->members) != 2 ||
                    xxwidgets_archivebrowser_selected_sources(ui->members, sources, 2, &count) != XXWIDGETS_OK ||
                    count != 2 || sources[0] != 0 || sources[1] != 1) return 0;
                update_metadata(ui);
            }
            if (xxwidgets_archivebrowser_set_entries(ui->members, NULL, 0) != XXWIDGETS_OK) return 0;
        }
    } else if (xxwidgets_archiveview_set_entries(ui->members, entries, 3) != XXWIDGETS_OK ||
               xxwidgets_archiveview_count(ui->members) != 3 ||
               xxwidgets_widget_set_value(ui->members, 2) != XXWIDGETS_OK ||
               xxwidgets_archiveview_get_selection(ui->members, &index, &selected) != XXWIDGETS_OK ||
               index != 2 || selected.size != UINT64_C(4294967297) ||
               xxwidgets_archiveview_clear(ui->members) != XXWIDGETS_OK) return 0;
    if (xxwidgets_widget_set_text(ui->output_dir, "test-output") != XXWIDGETS_OK ||
        xxwidgets_widget_get_text(ui->output_dir, path, sizeof(path), NULL) != XXWIDGETS_OK ||
        strcmp(path, "test-output") ||
        xxwidgets_widget_set_value(ui->progress, 73) != XXWIDGETS_OK ||
        xxwidgets_app_poll(ui->app, 0) != XXWIDGETS_OK) return 0;
    return 1;
}

/* Exercise the actual controller with the roundtrip fixture in both backends. */
static void smoke_file_types(ui_state *ui)
{
    xx_var value = {0};
    const xx_meta_string *record = NULL;
    xxwidgets_event event = {0};
    int valid = 1, next = -1;
    if (ui->job || ui->pending_command != XFU_COMMAND_NONE || !ui->running) return;
    if (xxwidgets_combobox_get_current(ui->file_type, &value) != XXWIDGETS_OK ||
        value.type != XX_VAR_TYPE_UINT32) valid = 0;
    if (ui->type_smoke_stage != 4) {
        static const wchar_t *labels[] = {L"Binary", L"gzip", L"tar.gz"};
        size_t i;
        if (xxwidgets_combobox_count(ui->file_type) != 3) valid = 0;
        for (i = 0; i < 3; ++i) {
            if (xxwidgets_combobox_get_record(ui->file_type, i, &record) != XXWIDGETS_OK ||
                wcscmp(record->meta_string->data, labels[i])) valid = 0;
        }
    }
    switch (ui->type_smoke_stage) {
    case 0:
        valid = valid && value.val.u32 == XX_FILE_TYPE_TAR_GZ && ui->listed_count == 2;
        next = 1; break;
    case 1:
        valid = valid && value.val.u32 == XX_FILE_TYPE_GZ && ui->listed_count == 1 &&
            ui->listed_entries[0].unpacked_size >= 2048;
        next = 0; break;
    case 2:
        valid = valid && value.val.u32 == XX_FILE_TYPE_BINARY && ui->listed_count == 0;
#ifdef _WIN32
        if (desktop_shell(ui)) {
            HWND owner = (HWND)xxwidgets_widget_native_handle(ui->window);
            valid = valid && !IsWindowEnabled((HWND)xxwidgets_widget_native_handle(ui->extract)) &&
                !IsWindowEnabled((HWND)xxwidgets_widget_native_handle(ui->test)) &&
                (GetMenuState(GetSubMenu(GetMenu(owner), 0), 2, MF_BYPOSITION) & MF_GRAYED) &&
                (GetMenuState(GetSubMenu(GetMenu(owner), 0), 3, MF_BYPOSITION) & MF_GRAYED);
        }
#endif
        next = 2; break;
    case 3:
        valid = valid && value.val.u32 == XX_FILE_TYPE_TAR_GZ && ui->listed_count == 2;
        next = 0; break;
    case 4:
        valid = valid && value.val.u32 == XX_FILE_TYPE_ZIP && ui->listed_count == 2 &&
            xxwidgets_combobox_count(ui->file_type) == 2;
        next = 0; break;
    case 5:
        valid = valid && value.val.u32 == XX_FILE_TYPE_BINARY && ui->listed_count == 0;
        next = 2; break;
    case 6:
        valid = valid && value.val.u32 == XX_FILE_TYPE_TAR_GZ && ui->listed_count == 2;
        if (valid) { ui->exit_code = 0; ui->running = 0; return; }
        break;
    default: valid = 0; break;
    }
    if (valid && next >= 0 && xxwidgets_widget_set_value(ui->file_type, next) == XXWIDGETS_OK) {
        if (ui->type_smoke_stage == 4) {
            char *path = widget_text(ui->archive_path), *grown;
            size_t length = path ? strlen(path) : 0;
            if (length < 4 || strcmp(path + length - 4, ".zip")) valid = 0;
            else if (!(grown = realloc(path, length + 4))) valid = 0;
            else {
                path = grown;
                memcpy(path + length - 4, ".tar.gz", 8);
                if (xxwidgets_widget_set_text(ui->archive_path, path) != XXWIDGETS_OK) valid = 0;
            }
            free(path);
        }
        event.type = XXWIDGETS_EVENT_SELECT; event.widget = ui->file_type; event.value = next;
        on_event(ui->app, &event, ui);
        valid = valid && ui->listed_count == 0;
        if (ui->type_smoke_stage == 3) {
            char *path = widget_text(ui->archive_path);
            size_t length = path ? strlen(path) : 0;
            if (length < 7 || strcmp(path + length - 7, ".tar.gz")) valid = 0;
            else {
                memcpy(path + length - 7, ".zip", 5);
                if (xxwidgets_widget_set_text(ui->archive_path, path) != XXWIDGETS_OK) valid = 0;
            }
            free(path);
        }
        ++ui->type_smoke_stage;
        if (valid) return;
    }
    ui->exit_code = 2; ui->running = 0;
}

#ifdef _WIN32
typedef struct progress_smoke_window { HWND owner, dialog; } progress_smoke_window;
static BOOL CALLBACK find_progress_smoke(HWND window, LPARAM data)
{
    progress_smoke_window *found = (progress_smoke_window *)data;
    wchar_t title[80];
    if (GetWindow(window, GW_OWNER) != found->owner) return TRUE;
    GetWindowTextW(window, title, 80);
    if (!wcscmp(title, L"Extracting archive")) { found->dialog = window; return FALSE; }
    return TRUE;
}
#endif

static int drive_progress_smoke(ui_state *ui)
{
#ifdef _WIN32
    HWND dialog = NULL;
    int visible = 0;
    if (ui->backend == XXWIDGETS_BACKEND_NATIVE) {
        progress_smoke_window found = {(HWND)xxwidgets_widget_native_handle(ui->window), NULL};
        EnumThreadWindows(GetCurrentThreadId(), find_progress_smoke, (LPARAM)&found);
        dialog = found.dialog; visible = dialog && IsWindowVisible(dialog);
        if (visible && !ui->progress_smoke_shown) {
            HWND bar = NULL;
            int count = 0, busy = 0;
            if (IsWindowEnabled(found.owner)) return 0;
            while ((bar = FindWindowExW(dialog, bar, PROGRESS_CLASSW, NULL))) {
                ++count; if (IsWindowVisible(bar)) ++busy;
            }
            if (count != XX_PD_LEVELS || busy < 2) return 0;
        }
    } else {
        HANDLE output = CreateFileW(L"CONOUT$", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
            NULL, OPEN_EXISTING, 0, NULL);
        CONSOLE_SCREEN_BUFFER_INFO info;
        int row;
        if (output == INVALID_HANDLE_VALUE) return 0;
        if (!GetConsoleScreenBufferInfo(output, &info)) { CloseHandle(output); return 0; }
        for (row = info.srWindow.Top; row <= info.srWindow.Bottom && !visible; ++row) {
            WCHAR line[501];
            DWORD read_count, width = (DWORD)(info.srWindow.Right - info.srWindow.Left + 1);
            COORD position = {info.srWindow.Left, (SHORT)row};
            if (width > 500) width = 500;
            if (!ReadConsoleOutputCharacterW(output, line, width, position, &read_count)) {
                CloseHandle(output); return 0;
            }
            line[read_count] = 0;
            visible = wcsstr(line, L"Extracting archive") != NULL;
        }
        CloseHandle(output);
    }
    if (!visible) return 1;
    if (progress_clock() - ui->progress_smoke_started <= 1000) return 0;
    ui->progress_smoke_shown = 1;
    mutex_lock(&ui->job->mutex);
    ui->job->smoke_progress_shown = 1;
    mutex_unlock(&ui->job->mutex);
    if (ui->progress_smoke == 3 && !ui->progress_smoke_cancelled) {
        if (dialog) {
            if (!PostMessageW(dialog, WM_CLOSE, 0, 0)) return 0;
        } else {
            INPUT_RECORD record = {0};
            DWORD written;
            record.EventType = KEY_EVENT; record.Event.KeyEvent.bKeyDown = TRUE;
            record.Event.KeyEvent.wRepeatCount = 1; record.Event.KeyEvent.wVirtualKeyCode = VK_ESCAPE;
            if (!WriteConsoleInputW(GetStdHandle(STD_INPUT_HANDLE), &record, 1, &written) || written != 1) return 0;
        }
        ui->progress_smoke_cancelled = 1;
    }
    return 1;
#else
    (void)ui;
    return 0;
#endif
}

int xfu_ui_run(int argc, char **argv, xxwidgets_backend backend)
{
    ui_state ui;
    const char *archive = "", *output = ".", *password = NULL;
    xfu_command startup = XFU_COMMAND_NONE;
    int i, have_archive = 0, have_command = 0, end_options = 0;
    xxfc_status_t settings_load_status;
#ifdef _WIN32
    smoke_console console;
    memset(&console, 0, sizeof(console));
    console.input = console.output = INVALID_HANDLE_VALUE;
#endif
    memset(&ui, 0, sizeof(ui));
    ui.backend = backend;
    /* Test invocations must report failure through their exit code, including
     * invalid startup arguments, without waiting for a modal error dialog. */
    for (i = 1; i < argc && strcmp(argv[i], "--"); ++i)
        if (!strcmp(argv[i], "--smoke-test") || !strcmp(argv[i], "--smoke-file-types") ||
            !strcmp(argv[i], "--smoke-password-embedded") || !strcmp(argv[i], "--smoke-password-manual") ||
            !strcmp(argv[i], "--smoke-password-retrieve") ||
            !strncmp(argv[i], "--smoke-progress-", 17)) ui.smoke = 1;
    for (i = 1; i < argc; ++i) {
        const char *argument = argv[i];
        if (!end_options && !strcmp(argument, "--help")) {
            if (!ui.smoke) report(backend, ui_usage, 0);
            return 0;
        }
        if (!end_options && !strcmp(argument, "--smoke-test")) { ui.smoke = 1; continue; }
        if (!end_options && !strcmp(argument, "--smoke-file-types")) {
            ui.smoke = ui.type_smoke = 1; continue;
        }
        if (!end_options && (!strcmp(argument, "--smoke-password-embedded") ||
                             !strcmp(argument, "--smoke-password-manual") ||
                             !strcmp(argument, "--smoke-password-retrieve"))) {
            ui.smoke = 1;
            ui.password_smoke = !strcmp(argument, "--smoke-password-embedded") ? 1 :
                !strcmp(argument, "--smoke-password-manual") ? 2 : 3;
            continue;
        }
        if (!end_options && (!strcmp(argument, "--smoke-progress-fast") ||
            !strcmp(argument, "--smoke-progress-slow") || !strcmp(argument, "--smoke-progress-cancel"))) {
            ui.smoke = 1;
            ui.progress_smoke = !strcmp(argument, "--smoke-progress-fast") ? 1 :
                !strcmp(argument, "--smoke-progress-slow") ? 2 : 3;
            continue;
        }
        if (!end_options && !strcmp(argument, "--")) { end_options = 1; continue; }
        if (!end_options && !strncmp(argument, "-o", 2) && argument[2]) { output = argument + 2; continue; }
        if (!end_options && !strncmp(argument, "-p", 2)) {
            if (password) {
                if (!ui.smoke) report(backend, "Give the password only once (-p<password>).", 1);
                return 2;
            }
            password = argument + 2; continue;
        }
        if (!end_options && argument[0] == '-') {
            if (!ui.smoke) report(backend, "Unknown option. Use --help for usage.", 1);
            return 2;
        }
        if (!have_archive && !have_command && xfu_parse_command(argument) != XFU_COMMAND_NONE) {
            startup = xfu_parse_command(argument); have_command = 1;
            if (startup == XFU_COMMAND_ADD) {
                if (!ui.smoke) report(backend, "XFileUnpacker opens existing archives only. "
                    "Create archives with the console tool: xfu a <archive> <file>...", 1);
                return 2;
            }
            continue;
        }
        if (!have_archive) { archive = argument; have_archive = 1; continue; }
        if (!ui.smoke) report(backend, "Unexpected argument. Use --help for usage.", 1);
        return 2;
    }
    if (have_command && !have_archive) {
        if (!ui.smoke) report(backend, "A command requires an archive path.", 1);
        return 2;
    }
    if (have_archive && startup == XFU_COMMAND_NONE) startup = XFU_COMMAND_LIST;
    if (ui.type_smoke && (!have_archive || startup != XFU_COMMAND_LIST)) {
        return 2;
    }
    if (ui.progress_smoke && (!have_archive || startup != XFU_COMMAND_EXTRACT)) {
        return 2;
    }
    if (ui.password_smoke && (!have_archive || startup != XFU_COMMAND_LIST ||
                             (ui.password_smoke == 1 && password))) {
        return 2;
    }
    ui.password_smoke_expected = password;
#ifdef _WIN32
    if (ui.smoke && backend == XXWIDGETS_BACKEND_TUI && !smoke_console_create(&console)) {
        smoke_console_destroy(&console); return 2;
    }
#endif
    ui.settings = ui.smoke ? xx_settings_create_memory() :
        xx_settings_create_native("horsicq", "XFileUnpacker");
    if (!ui.settings) {
        if (!ui.smoke) report(backend, "Cannot create application settings.", 1);
        ui.exit_code = 2; goto cleanup;
    }
    ui.previous_settings = xx_get_settings();
    xx_set_settings(ui.settings);
    settings_load_status = xx_settings_load(ui.settings);
    if (ui.smoke && !have_archive &&
        (xxwidgets_settings_set_bool(ui.settings, UI_SETTING_ADVANCED, 1) != XXWIDGETS_OK ||
         xxwidgets_settings_set_bool(ui.settings, UI_SETTING_LOG, 1) != XXWIDGETS_OK)) {
        ui.exit_code = 2; goto cleanup;
    }
    ui.advanced_visible = xxwidgets_settings_get_bool(ui.settings, UI_SETTING_ADVANCED, 0);
    ui.log_visible = xxwidgets_settings_get_bool(ui.settings, UI_SETTING_LOG, 0);
    if (!create_ui(&ui, archive, output)) {
        if (!ui.smoke) report(backend, "Cannot open the interface. Run the terminal edition in an interactive terminal.", 1);
        ui.exit_code = 2; goto cleanup;
    }
    if (!password_archive_changed(&ui, archive) ||
        (password && !set_automatic_password(&ui, password))) {
        ui.exit_code = 2; goto cleanup;
    }
    if (password) ui.password_manual = 1;
    if (settings_load_status != XXFC_OK) show_status(&ui, "Cannot load application settings. Using defaults.");
#ifdef _WIN32
    if (desktop_shell(&ui) && !install_native_shortcuts(&ui)) {
        ui.exit_code = 2; goto cleanup;
    }
#endif
    ui.running = 1;
    resize_terminal(&ui);
    if (ui.smoke && !have_archive) {
        ui.exit_code = smoke_widgets(&ui) ? 0 : 2;
        ui.running = 0;
    } else if (ui.password_smoke == 3) {
        /* Retrieve before ordinary startup LIST, which would otherwise use
         * the caller's deliberately incorrect smoke password. */
        ui.retrieve_smoke_click = 1;
    } else if (startup != XFU_COMMAND_NONE && !start_job(&ui, startup)) {
        if (ui.smoke) { ui.exit_code = 2; ui.running = 0; }
    }
    while (ui.running) {
        xxwidgets_status status;
        resize_terminal(&ui);
        status = xxwidgets_app_poll(ui.app, 30);
        if (status != XXWIDGETS_OK) {
            ui.exit_code = 2;
            ui.closing = 1;
            cancel_job(&ui);
            if (!ui.job) break;
        }
#ifdef _WIN32
        if (desktop_shell(&ui) && ui.context_pending) {
            ui.context_pending = 0;
            if (!ui.closing && !xfu_native_shell_archive_menu(ui.shell, ui.members,
                    ui.context_x, ui.context_y, ui.busy))
                show_status(&ui, "Cannot show the archive context menu.");
        }
        if (desktop_shell(&ui) && ui.pending_action) run_native_action(&ui);
#endif
        if (ui.retrieve_smoke_click && !ui.job && !ui.closing) {
            xxwidgets_event event = {0};
            ui.retrieve_smoke_click = 0;
            event.type = XXWIDGETS_EVENT_CLICK; event.widget = ui.get_password;
            on_event(ui.app, &event, &ui);
            if (!ui.pending_password_retrieval || ui.pending_command != XFU_COMMAND_LIST) {
                ui.exit_code = 2; ui.running = 0;
            }
        }
        if (ui.running && ui.pending_command != XFU_COMMAND_NONE && !ui.job && !ui.closing) {
            xfu_command command = ui.pending_command;
            ui.pending_command = XFU_COMMAND_NONE;
            if (!start_job(&ui, command)) {
                ui.busy_focus = NULL;
                if (ui.smoke) { ui.exit_code = 2; ui.running = 0; }
            } else if (ui.password_smoke == 3 && ui.job && ui.job->retrieve_password) {
                xxwidgets_event event = {0};
                /* An in-flight click cannot queue another operation. */
                event.type = XXWIDGETS_EVENT_CLICK; event.widget = ui.get_password;
                on_event(ui.app, &event, &ui);
                if (ui.pending_password_retrieval || ui.pending_command != XFU_COMMAND_NONE) {
                    ui.exit_code = 2; ui.running = 0; cancel_job(&ui);
                } else if (ui.password_smoke_stage == 3) {
                    /* Change away and back: equality of the final path alone
                     * must not make an earlier recovery result current. */
                    event.type = XXWIDGETS_EVENT_CHANGE; event.widget = ui.archive_path;
                    if (xxwidgets_widget_set_text(ui.archive_path, "UI-stale-password-retrieval.invalid") != XXWIDGETS_OK) {
                        ui.exit_code = 2; ui.running = 0; cancel_job(&ui);
                    } else {
                        on_event(ui.app, &event, &ui);
                        if (xxwidgets_widget_set_text(ui.archive_path, ui.job->archive_path) != XXWIDGETS_OK) {
                            ui.exit_code = 2; ui.running = 0; cancel_job(&ui);
                        } else on_event(ui.app, &event, &ui);
                    }
                } else if (ui.password_smoke_stage == 4) cancel_job(&ui);
            }
        }
        drain_job(&ui);
#ifndef _WIN32
        /* A modal dialog's own event handler swallows the main window's
         * RESIZE; its new size in cells is still recorded, so check it here. */
        resize_native(&ui);
#endif
        if (ui.type_smoke) smoke_file_types(&ui);
        if (ui.browse_requested) {
            ui.browse_requested = 0;
            /* Choosing an archive opens it, as File > Open does on Windows. */
            if (!ui.job && !ui.closing && browse_file(&ui, ui.archive_path))
                ui.pending_command = XFU_COMMAND_LIST;
            else {
                ui.busy_focus = NULL;
                if (!ui.smoke) xxwidgets_widget_focus(ui.archive_browse);
            }
        }
        /* After a dialog, focus returns to the button that opened it. */
        if (ui.options_requested) {
            ui.options_requested = 0; show_options(&ui);
            if (!ui.smoke) xxwidgets_widget_focus(ui.options);
        }
        if (ui.formats_requested) {
            ui.formats_requested = 0; show_supported_types(&ui);
            if (!ui.smoke) xxwidgets_widget_focus(ui.formats_button);
        }
        if (ui.about_requested) {
            ui.about_requested = 0;
            if (xxwidgets_about_dialog_show(ui.about, ui.window) != XXWIDGETS_OK)
                show_status(&ui, "Cannot show the About dialog.");
            else if (!ui.smoke) xxwidgets_widget_focus(ui.about_button);
        }
    }
cleanup:
    if (ui.job) { cancel_job(&ui); job_destroy(ui.job); }
    free_entries(ui.listed_entries, ui.listed_count);
    free(ui.file_types_path);
    free(ui.members_archive);
    free(ui.pending_type_path);
    free(ui.password_archive);
    free(ui.password_listed_archive);
    ui.password_updating = 1;
    if (ui.password) xxwidgets_widget_set_text(ui.password, "");
    free_password(ui.automatic_password);
    free_password(ui.automatic_password_display);
    ui.automatic_password = ui.automatic_password_display = NULL;
#ifdef _WIN32
    xfu_native_shell_destroy(ui.shell);
#endif
    if (ui.app) {
        xxwidgets_app_quit(ui.app, ui.exit_code);
        if (xxwidgets_app_destroy(ui.app) != XXWIDGETS_OK) ui.exit_code = 2;
    }
    if (ui.about && xxwidgets_about_dialog_destroy(ui.about) != XXWIDGETS_OK) ui.exit_code = 2;
    if (ui.settings) {
        xx_set_settings(ui.previous_settings);
        xx_settings_destroy(ui.settings);
    }
#ifdef _WIN32
    if (ui.smoke && backend == XXWIDGETS_BACKEND_TUI) smoke_console_destroy(&console);
#endif
    return ui.exit_code;
}
