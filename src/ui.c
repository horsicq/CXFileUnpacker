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
#include "supported_types.h"
#include "xxwidgets/xxwidgets_settings.h"
#include "xxwidgets/xxwidgets_combobox.h"
#include "xxwidgets/xxwidgets_process.h"
#include "xxfclib/global/xx_settings_global.h"

#include <inttypes.h>
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
    char *archive_path, *output_dir;
    char **files;
    size_t *selected_records;
    ui_mutex mutex;
    ui_thread thread;
    int thread_started, done, result, cancel_requested, memory_error;
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
    xxwidgets_widget *type_label, *file_type;
    xxwidgets_widget *open, *extract, *test, *add, *cancel, *quit;
    xxwidgets_widget *copy_path, *info, *log_toggle, *advanced, *details, *options, *about_button, *formats_button;
    xxwidgets_widget *members_label, *members, *metadata;
    xxwidgets_widget *source_label, *source_path, *source_browse, *queue_add, *queue_remove, *queue;
    xxwidgets_widget *progress, *status, *log_label, *log, *help;
    char **queued_paths;
    size_t queued_count;
    ui_job *job;
    xfu_entry *listed_entries;
    size_t listed_count;
    char *file_types_path, *pending_type_path;
    xx_file_type_t selected_type;
    xfu_command pending_command;
    int pending_extract_selected;
    int type_smoke, type_smoke_stage;
    int progress_smoke, progress_smoke_shown, progress_smoke_cancelled;
    uint64_t progress_smoke_started;
    int running, closing, smoke, exit_code, columns, rows, layout_ready, log_visible, busy, advanced_visible, options_requested, about_requested, formats_requested;
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
            memcpy(result + position, input, count);
            position += count; input += count; remaining -= count;
        } else {
            if (member_path) {
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
    char *name;
    xfu_entry *grown;
    size_t capacity;
    xfu_property *properties = NULL;
    size_t i;
    if (job->memory_error) return;
    name = display_member_text(entry->name);
    if (!name) { job->memory_error = 1; return; }
    if (entry->property_count) {
        if (entry->property_count > SIZE_MAX / sizeof(*properties)) { free(name); job->memory_error = 1; return; }
        properties = (xfu_property *)calloc(entry->property_count, sizeof(*properties));
        if (!properties) { free(name); job->memory_error = 1; return; }
        for (i = 0; i < entry->property_count; ++i) {
            properties[i].name = display_member_text(entry->properties[i].name);
            properties[i].value = display_text(entry->properties[i].value);
            if (!properties[i].name || !properties[i].value) {
                xfu_free_properties(properties, entry->property_count); free(name); job->memory_error = 1; return;
            }
        }
    }
    if (job->entry_count == job->entry_capacity) {
        capacity = job->entry_capacity ? job->entry_capacity * 2 : 128;
        if (capacity > SIZE_MAX / sizeof(*grown)) {
            xfu_free_properties(properties, entry->property_count); free(name); job->memory_error = 1; return;
        }
        grown = (xfu_entry *)realloc(job->entries, capacity * sizeof(*grown));
        if (!grown) { xfu_free_properties(properties, entry->property_count); free(name); job->memory_error = 1; return; }
        job->entries = grown;
        job->entry_capacity = capacity;
    }
    job->entries[job->entry_count] = *entry;
    job->entries[job->entry_count].properties = properties;
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
    /* A newly created archive gets a listing through the same format API. */
    if (job->request.command == XFU_COMMAND_ADD && result == 0 && !job_cancelled(job)) {
        xfu_request listing = job->request;
        listing.command = XFU_COMMAND_LIST;
        listing.files = NULL;
        listing.file_count = 0;
        result = xfu_run(&listing);
    }
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
    for (i = 0; i < job->request.file_count; ++i) free(job->files[i]);
    free(job->files);
    free(job->selected_records);
    free(job->archive_path);
    free(job->output_dir);
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
    xxwidgets_widget *controls[] = {
        ui->archive_path, ui->archive_browse, ui->output_dir, ui->open,
        ui->extract, ui->test, ui->add, ui->source_path, ui->source_browse,
        ui->queue_add, ui->queue_remove, ui->queue
    };
    size_t i;
    for (i = 0; i < sizeof(controls) / sizeof(controls[0]); ++i)
        xxwidgets_widget_set_enabled(controls[i], !busy);
    xxwidgets_widget_set_enabled(ui->file_type, !busy);
    xxwidgets_widget_set_enabled(ui->extract, !busy && ui->selected_type != XX_FILE_TYPE_BINARY);
    xxwidgets_widget_set_enabled(ui->test, !busy && ui->selected_type != XX_FILE_TYPE_BINARY);
    xxwidgets_widget_set_enabled(ui->cancel, busy);
    ui->busy = busy;
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
    case XFU_COMMAND_ADD: return "Adding";
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

static void show_supported_types(ui_state *ui)
{
    char *text = xfu_supported_types_text(NULL);
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
    update_metadata(ui);
    return 1;
}

static int clear_members(ui_state *ui)
{
    xxwidgets_status status;
    if (xxwidgets_widget_kind(ui->members) == XXWIDGETS_ARCHIVEBROWSER)
        status = xxwidgets_archivebrowser_set_entries(ui->members, NULL, 0);
    else status = xxwidgets_archiveview_set_entries(ui->members, NULL, 0);
    if (status != XXWIDGETS_OK) return 0;
    free_entries(ui->listed_entries, ui->listed_count);
    ui->listed_entries = NULL; ui->listed_count = 0;
    update_metadata(ui);
    return 1;
}

static int start_job(ui_state *ui, xfu_command command)
{
    ui_job *job;
    size_t i;
    char message[80];
    int known_file, requested_type;
    if (ui->job) return 0;
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
    job->request.command = command;
    job->request.archive_path = job->archive_path;
    job->request.output_dir = job->output_dir[0] ? job->output_dir : ".";
    job->request.callbacks.user = job;
    job->request.callbacks.log = job_log;
    job->request.callbacks.entry = job_entry;
    job->request.callbacks.progress = job_progress;
    job->request.callbacks.cancelled = job_cancelled;
    job->request.callbacks.file_types = job_file_types;
    job->worker_progress = xx_pd_init();
    job->overall_level = -1;
    job->request.progress_state = &job->worker_progress;
    job->smoke_progress_delay = ui->progress_smoke;
    known_file = ui->file_types_path && !strcmp(ui->file_types_path, job->archive_path);
    requested_type = ui->pending_type_path && !strcmp(ui->pending_type_path, job->archive_path);
    free(ui->pending_type_path); ui->pending_type_path = NULL;
    if (command != XFU_COMMAND_ADD && (known_file || requested_type))
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
    if (job->request.file_type == XX_FILE_TYPE_BINARY && known_file) {
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
    if (command == XFU_COMMAND_ADD) {
        if (!ui->queued_count) {
            show_status(ui, "Queue at least one source file before Add (a).");
            job_destroy(job); return 0;
        }
        job->files = (char **)calloc(ui->queued_count, sizeof(*job->files));
        if (!job->files) { show_status(ui, "Out of memory."); job_destroy(job); return 0; }
        job->request.file_count = ui->queued_count;
        for (i = 0; i < ui->queued_count; ++i) {
            job->files[i] = copy_text(ui->queued_paths[i]);
            if (!job->files[i]) { show_status(ui, "Out of memory."); job_destroy(job); return 0; }
        }
        job->request.files = (const char *const *)job->files;
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
    xxwidgets_widget_set_enabled(ui->cancel, 0);
}

static void drain_job(ui_state *ui)
{
    ui_job *job = ui->job;
    char *lines[UI_PENDING_LOGS], *current = NULL;
    size_t i, count;
    uint64_t completed, total;
    int done, changed, cancelled, display_ok = 1;
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
    if (job->have_file_types && job->type_count && !populate_file_types(ui, job)) {
        append_log(ui, "Could not display the detected file types."); job->result = 2; display_ok = 0;
    }
    if (!job->request.extract_selected && !populate_members(ui, job)) {
        append_log(ui, "Could not display archive members."); job->result = 2; display_ok = 0;
    }
    if (cancelled) show_status(ui, "Cancelled. Completed files are kept.");
    else if (job->request.command == XFU_COMMAND_LIST && job->have_file_types &&
             job->selected_type == XX_FILE_TYPE_BINARY && !job->memory_error && display_ok) {
        show_status(ui, "Binary: no archive members."); job->result = 0;
        xxwidgets_widget_set_value(ui->progress, 0);
    } else if (job->result == 0) {
        show_status(ui, "Done."); xxwidgets_widget_set_value(ui->progress, 100);
    } else if (job->result == 1) show_status(ui, "Completed with errors; see log.");
    else show_status(ui, "Operation failed; see log.");
    if (job->result != 0 && desktop_shell(ui)) ui->log_visible = 1;
    if (ui->smoke && (!ui->type_smoke || job->result != 0)) {
        ui->exit_code = job->result; ui->running = 0;
    }
    ui->job = NULL;
    job_destroy(job);
    set_busy(ui, 0);
    if (ui->closing) ui->running = 0;
}

static int queue_path(ui_state *ui, const char *path)
{
    char **grown, *copy;
    if (!path || !path[0]) { show_status(ui, "Enter a source file path."); return 0; }
    copy = copy_text(path);
    if (!copy) { show_status(ui, "Out of memory."); return 0; }
    grown = (char **)realloc(ui->queued_paths, (ui->queued_count + 1) * sizeof(*grown));
    if (!grown) { free(copy); show_status(ui, "Out of memory."); return 0; }
    ui->queued_paths = grown;
    if (xxwidgets_listbox_add(ui->queue, path) != XXWIDGETS_OK) { free(copy); return 0; }
    ui->queued_paths[ui->queued_count++] = copy;
    xxwidgets_widget_set_value(ui->queue, (int)ui->queued_count - 1);
    show_status(ui, "Source file queued. Add (a) creates a new archive at the archive path.");
    return 1;
}

static void remove_queued(ui_state *ui)
{
    int selected = -1;
    size_t i;
    xxwidgets_widget_get_value(ui->queue, &selected);
    if (selected < 0 || (size_t)selected >= ui->queued_count) return;
    free(ui->queued_paths[selected]);
    for (i = (size_t)selected + 1; i < ui->queued_count; ++i)
        ui->queued_paths[i - 1] = ui->queued_paths[i];
    --ui->queued_count;
    xxwidgets_listbox_clear(ui->queue);
    for (i = 0; i < ui->queued_count; ++i) xxwidgets_listbox_add(ui->queue, ui->queued_paths[i]);
    if (ui->queued_count) xxwidgets_widget_set_value(ui->queue,
        (size_t)selected < ui->queued_count ? selected : (int)ui->queued_count - 1);
}

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

static void clear_queue(ui_state *ui)
{
    size_t i;
    for (i = 0; i < ui->queued_count; ++i) free(ui->queued_paths[i]);
    free(ui->queued_paths); ui->queued_paths = NULL; ui->queued_count = 0;
    xxwidgets_listbox_clear(ui->queue);
}

static void native_create_archive(ui_state *ui)
{
    wchar_t *sources = (wchar_t *)calloc(65536, sizeof(*sources));
    wchar_t archive[32768] = L"";
    OPENFILENAMEW dialog;
    wchar_t *item;
    int ok = 1;
    if (!sources) { show_status(ui, "Out of memory."); return; }
    memset(&dialog, 0, sizeof(dialog));
    dialog.lStructSize = sizeof(dialog);
    dialog.hwndOwner = (HWND)xxwidgets_widget_native_handle(ui->window);
    dialog.lpstrTitle = L"Select files for a new archive";
    dialog.lpstrFilter = L"All files\0*.*\0\0";
    dialog.lpstrFile = sources; dialog.nMaxFile = 65536;
    dialog.Flags = OFN_EXPLORER | OFN_ALLOWMULTISELECT | OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    if (!GetOpenFileNameW(&dialog)) { free(sources); return; }
    dialog.lpstrTitle = L"Create archive";
    dialog.lpstrFilter = L"ZIP archive\0*.zip\0TAR archive\0*.tar\0Gzip TAR archive\0*.tar.gz\0CPIO archive\0*.cpio\0All files\0*.*\0\0";
    dialog.lpstrFile = archive; dialog.nMaxFile = 32768; dialog.lpstrDefExt = L"zip";
    dialog.Flags = OFN_EXPLORER | OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    if (!GetSaveFileNameW(&dialog)) { free(sources); return; }
    clear_queue(ui);
    item = sources + wcslen(sources) + 1;
    if (!*item) {
        char *path = wide_utf8(sources);
        ok = path && queue_path(ui, path); free(path);
    } else {
        while (*item && ok) {
            size_t length = wcslen(sources) + wcslen(item) + 2;
            wchar_t *joined = (wchar_t *)malloc(length * sizeof(*joined));
            char *path = NULL;
            if (joined) { swprintf(joined, length, L"%ls\\%ls", sources, item); path = wide_utf8(joined); }
            ok = path && queue_path(ui, path); free(path); free(joined);
            item += wcslen(item) + 1;
        }
    }
    free(sources);
    if (ok) {
        char *path = wide_utf8(archive);
        if (path) { xxwidgets_widget_set_text(ui->archive_path, path); free(path); ui->pending_command = XFU_COMMAND_ADD; }
        else show_status(ui, "Cannot read the selected archive path.");
    } else { clear_queue(ui); show_status(ui, "Could not queue the selected files."); }
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
    size_t source, capacity;
    char *message;
    if (!archive) return;
    if (xxwidgets_archivebrowser_get_selection(ui->members, &source, &entry) != XXWIDGETS_OK)
        memset(&entry, 0, sizeof(entry));
    capacity = strlen(archive) + strlen(entry.path ? entry.path : "") + 480;
    if (ui->advanced_visible) {
        size_t i;
        for (i = 0; i < entry.property_count; ++i) {
            size_t length = strlen(entry.properties[i].name) + strlen(entry.properties[i].value) + 4;
            if (capacity > SIZE_MAX - length) { free(archive); return; }
            capacity += length;
        }
    }
    message = (char *)malloc(capacity);
    if (message) {
        char size[40] = "unknown", packed[40] = "unknown";
        if (entry.flags & XXWIDGETS_ARCHIVE_SIZE_KNOWN) snprintf(size, sizeof(size), "%" PRIu64, entry.size);
        if (entry.flags & XXWIDGETS_ARCHIVE_PACKED_SIZE_KNOWN) snprintf(packed, sizeof(packed), "%" PRIu64, entry.packed_size);
        snprintf(message, capacity,
            "Archive: %s\nMembers: %zu\n\nSelected: %s\nType: %s\nSize: %s bytes\nPacked size: %s bytes\nModified: %s\nAttributes: %s",
            archive, xxwidgets_archivebrowser_count(ui->members), entry.path ? entry.path : "none",
            entry.path ? (entry.is_directory ? "Folder" : "File") : "", size, packed,
            entry.modified ? entry.modified : "", entry.attributes ? entry.attributes : "");
        if (ui->advanced_visible) {
            size_t i, used = strlen(message);
            for (i = 0; i < entry.property_count; ++i)
                used += (size_t)snprintf(message + used, capacity - used, "\n%s: %s",
                    entry.properties[i].name, entry.properties[i].value);
        }
        xfu_native_shell_information(ui->window, message); free(message);
    }
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
    } else if (action == XFU_SHELL_ADD) native_create_archive(ui);
    else if (action == XFU_SHELL_EXTRACT) native_extract_archive(ui, 0);
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
        {"open", "Ctrl+O", XFU_SHELL_OPEN}, {"create_archive", "Ctrl+N", XFU_SHELL_ADD},
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

static void rect(xxwidgets_widget *widget, int x, int y, int width, int height)
{
    xxwidgets_rect bounds = { x, y, width > 0 ? width : 1, height > 0 ? height : 1 };
    xxwidgets_widget_set_rect(widget, bounds);
}

static void layout(ui_state *ui, int columns, int rows)
{
    int extra, archive_height, queue_height, log_height, metadata_y, source_y, progress_y;
    int native_browse = ui->backend == XXWIDGETS_BACKEND_NATIVE;
    int browse_width;
    if (desktop_shell(ui)) {
        xxwidgets_widget *hidden[] = {
            ui->archive_label, ui->archive_path, ui->archive_browse, ui->output_label, ui->output_dir,
            ui->members_label, ui->source_label, ui->source_path, ui->source_browse,
            ui->queue_add, ui->queue_remove, ui->queue, ui->quit, ui->help, ui->add,
            ui->log_toggle, ui->cancel, ui->options, ui->about_button, ui->formats_button
        };
        xxwidgets_widget *toolbar[] = { ui->open, ui->extract, ui->test,
            ui->copy_path, ui->info };
        size_t i;
        int log_rows, detail_rows;
        if (columns < 96) columns = 96;
        if (rows < 18) rows = 18;
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
        log_rows = ui->log_visible ? 7 : 0;
        detail_rows = ui->advanced_visible ? (rows - log_rows - 8 < 6 ? rows - log_rows - 8 : 6) : 0;
        rect(ui->members, 0, 3, columns, rows - 4 - log_rows - detail_rows);
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
    native_browse = 0;
#endif
    if (columns < 76) columns = 76;
    if (rows < 23) rows = 23;
    ui->columns = columns; ui->rows = rows;
    browse_width = native_browse ? 11 : 0;
    rect(ui->archive_label, 1, 0, 9, 1);
    rect(ui->archive_path, 10, 0, columns - 11 - browse_width, 1);
    rect(ui->archive_browse, columns - 11, 0, 10, 1);
    xxwidgets_widget_set_visible(ui->archive_browse, native_browse);
    rect(ui->output_label, 1, 2, 9, 1);
    rect(ui->output_dir, 10, 2, columns - 40, 1);
    rect(ui->type_label, columns - 29, 2, 10, 1);
    rect(ui->file_type, columns - 19, 2, 18, 1);
    rect(ui->open, 1, 4, 11, 1);
    rect(ui->extract, 13, 4, 13, 1);
    rect(ui->test, 27, 4, 10, 1);
    rect(ui->add, 38, 4, 10, 1);
    rect(ui->cancel, 49, 4, 10, 1);
    rect(ui->quit, 61, 4, 10, 1);
    rect(ui->advanced, columns - 17, 6, 16, 1);
    rect(ui->options, columns - 31, 6, 12, 1);
    rect(ui->about_button, columns - 43, 6, 10, 1);
    rect(ui->formats_button, columns - 58, 6, 13, 1);
    xxwidgets_widget_set_visible(ui->details, ui->advanced_visible);
    extra = rows - 23;
    queue_height = 2 + extra / 7;
    log_height = 2 + extra / 4;
    archive_height = 4 + extra - extra / 7 - extra / 4;
    if (ui->advanced_visible) archive_height -= 3;
    metadata_y = 7 + archive_height;
    source_y = metadata_y + 2 + (ui->advanced_visible ? 3 : 0);
    progress_y = source_y + 2 + queue_height;
    rect(ui->members_label, 1, 6, columns - 60, 1);
    rect(ui->members, 1, 7, columns - 2, archive_height);
    rect(ui->metadata, 1, metadata_y, columns - 2, 1);
    if (ui->advanced_visible) rect(ui->details, 1, metadata_y + 1, columns - 2, 3);
    rect(ui->source_label, 1, source_y, 9, 1);
    rect(ui->source_path, 10, source_y, columns - 34 - browse_width, 1);
    rect(ui->source_browse, columns - 24 - browse_width, source_y, 10, 1);
    xxwidgets_widget_set_visible(ui->source_browse, native_browse);
    rect(ui->queue_add, columns - 24, source_y, 10, 1);
    rect(ui->queue_remove, columns - 13, source_y, 12, 1);
    rect(ui->queue, 1, source_y + 1, columns - 2, queue_height);
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
#else
    (void)ui;
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
    if (columns < 76) columns = 76;
    if (rows < 23) rows = 23;
    if (columns == ui->columns && rows == ui->rows) return;
    bounds.x = bounds.y = 0; bounds.width = columns; bounds.height = rows;
    xxwidgets_widget_set_rect(ui->window, bounds);
    layout(ui, columns, rows);
}

static void on_event(xxwidgets_app *app, const xxwidgets_event *event, void *user)
{
    ui_state *ui = (ui_state *)user;
    (void)app;
    if (event->type == XXWIDGETS_EVENT_SHORTCUT && event->widget == ui->window) {
#ifdef _WIN32
        if (desktop_shell(ui)) ui->pending_action = (xfu_shell_action)event->value;
#endif
    } else if (event->widget == ui->file_type && event->type == XXWIDGETS_EVENT_SELECT &&
               !ui->job && !ui->closing) {
        xx_var value = {0};
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
            else if (event->widget == ui->add) ui->pending_action = XFU_SHELL_ADD;
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
            else if (event->widget == ui->add) ui->pending_command = XFU_COMMAND_ADD;
            else if (event->widget == ui->queue_add) {
                char *path = widget_text(ui->source_path);
                if (path && queue_path(ui, path)) xxwidgets_widget_set_text(ui->source_path, "");
                free(path);
            } else if (event->widget == ui->queue_remove) remove_queued(ui);
#ifdef _WIN32
            else if (event->widget == ui->archive_browse) browse_file(ui, ui->archive_path);
            else if (event->widget == ui->source_browse) browse_file(ui, ui->source_path);
#endif
        }
    }
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
    if (!create_about(ui)) return 0;
    if (ui->smoke) xxwidgets_widget_set_visible(ui->window, 0);
    if (ui->backend == XXWIDGETS_BACKEND_NATIVE) xfu_set_application_icon(ui->window);
#define CONTROL(field, kind, text) do { ui->field = create(ui, kind, text); if (!ui->field) return 0; } while (0)
    CONTROL(archive_label, XXWIDGETS_LABEL, "Archive:");
    CONTROL(archive_path, XXWIDGETS_EDIT, archive);
    CONTROL(archive_browse, XXWIDGETS_BUTTON, "Browse...");
    CONTROL(output_label, XXWIDGETS_LABEL, "Output:");
    CONTROL(output_dir, XXWIDGETS_EDIT, output);
    CONTROL(type_label, XXWIDGETS_LABEL, "File type:");
    CONTROL(file_type, XXWIDGETS_COMBOBOX, "Binary");
    CONTROL(open, XXWIDGETS_BUTTON, desktop_shell(ui) ? "Open" : "Open (l)");
    CONTROL(extract, XXWIDGETS_BUTTON, desktop_shell(ui) ? "Extract" : "Extract (x)");
    CONTROL(test, XXWIDGETS_BUTTON, desktop_shell(ui) ? "Test" : "Test (t)");
    CONTROL(add, XXWIDGETS_BUTTON, desktop_shell(ui) ? "Add" : "Add (a)");
    CONTROL(cancel, XXWIDGETS_BUTTON, "Cancel");
    CONTROL(quit, XXWIDGETS_BUTTON, "Quit");
    CONTROL(members_label, XXWIDGETS_LABEL, "Archive members");
    CONTROL(members, ui->backend == XXWIDGETS_BACKEND_NATIVE ? XXWIDGETS_ARCHIVEBROWSER : XXWIDGETS_ARCHIVEVIEW, "");
    CONTROL(metadata, XXWIDGETS_LABEL, "No member selected.");
    CONTROL(advanced, XXWIDGETS_CHECKBOX, "Advanced");
    CONTROL(details, XXWIDGETS_LISTBOX, "");
    CONTROL(options, XXWIDGETS_BUTTON, "Options...");
    CONTROL(about_button, XXWIDGETS_BUTTON, "About...");
    CONTROL(formats_button, XXWIDGETS_BUTTON, "File types...");
    CONTROL(source_label, XXWIDGETS_LABEL, "Add file:");
    CONTROL(source_path, XXWIDGETS_EDIT, "");
    CONTROL(source_browse, XXWIDGETS_BUTTON, "Browse...");
    CONTROL(queue_add, XXWIDGETS_BUTTON, "Queue");
    CONTROL(queue_remove, XXWIDGETS_BUTTON, "Remove");
    CONTROL(queue, XXWIDGETS_LISTBOX, "");
    CONTROL(progress, XXWIDGETS_PROGRESS, "");
    CONTROL(status, XXWIDGETS_LABEL, "Ready. Enter an archive path and select Open (l).");
    CONTROL(log_label, XXWIDGETS_LABEL, "Operation log");
    CONTROL(log, XXWIDGETS_LISTBOX, "");
    CONTROL(help, XXWIDGETS_LABEL, "Tab: next control | Enter: activate | Arrows: select | Esc: quit");
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
    "  t <archive>               Test: extract to a scratch dir, then discard\n"
    "  a <archive> <file>...     Add files to a new archive\n\n"
    "Without a command, an archive path opens its listing.\n"
    "-o<dir>: output directory for x (default: the current directory).\n"
    "Add writes .tar .tar.gz .tar.bz2 .tar.xz .tar.zst .tar.lz4 .zip .cpio.\n"
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
    size_t lines = 0, count = 0;
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
    expected = xfu_supported_types_text(&count);
    EnumChildWindows(dialog, smoke_find_copy_button, (LPARAM)&copy);
    if (body && expected && GetWindowTextW(edit, body, length + 1)) {
        wchar_t *cursor;
        for (cursor = body; *cursor; ++cursor) if (*cursor == L'\n') ++lines;
        state->valid = !IsWindowEnabled(state->owner) && GetWindow(dialog, GW_OWNER) == state->owner &&
            copy && IsWindowEnabled(copy) && (GetWindowLongPtrW(edit, GWL_STYLE) & ES_READONLY) &&
            wcsstr(body, L"Supported file types (xxfclib): ") && wcsstr(body, L"CPX4") &&
            wcsstr(body, L"TAR.GZ") && wcsstr(body, L"Xamarin compressed assembly (XALZ)") &&
            lines == count + 4;
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
    const char *archive = "", *output = ".";
    xfu_command startup = XFU_COMMAND_NONE;
    const char **startup_files = NULL;
    size_t startup_file_count = 0, file_index;
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
            !strncmp(argv[i], "--smoke-progress-", 17)) ui.smoke = 1;
    startup_files = (const char **)calloc((size_t)argc + 1, sizeof(*startup_files));
    if (!startup_files) { if (!ui.smoke) report(backend, "Out of memory.", 1); return 2; }
    for (i = 1; i < argc; ++i) {
        const char *argument = argv[i];
        if (!end_options && !strcmp(argument, "--help")) {
            if (!ui.smoke) report(backend, ui_usage, 0);
            free(startup_files); return 0;
        }
        if (!end_options && !strcmp(argument, "--smoke-test")) { ui.smoke = 1; continue; }
        if (!end_options && !strcmp(argument, "--smoke-file-types")) {
            ui.smoke = ui.type_smoke = 1; continue;
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
        if (!end_options && argument[0] == '-') {
            if (!ui.smoke) report(backend, "Unknown option. Use --help for usage.", 1);
            free(startup_files); return 2;
        }
        if (!have_archive && !have_command && xfu_parse_command(argument) != XFU_COMMAND_NONE) {
            startup = xfu_parse_command(argument); have_command = 1; continue;
        }
        if (!have_archive) { archive = argument; have_archive = 1; continue; }
        if (startup == XFU_COMMAND_ADD) startup_files[startup_file_count++] = argument;
        else {
            if (!ui.smoke) report(backend, "Unexpected argument. Use --help for usage.", 1);
            free(startup_files); return 2;
        }
    }
    if (have_command && !have_archive) {
        if (!ui.smoke) report(backend, "A command requires an archive path.", 1);
        free(startup_files); return 2;
    }
    if (startup == XFU_COMMAND_ADD && !startup_file_count) {
        if (!ui.smoke) report(backend, "Add (a) requires at least one source file.", 1);
        free(startup_files); return 2;
    }
    if (have_archive && startup == XFU_COMMAND_NONE) startup = XFU_COMMAND_LIST;
    if (ui.type_smoke && (!have_archive || startup != XFU_COMMAND_LIST)) {
        free(startup_files); return 2;
    }
    if (ui.progress_smoke && (!have_archive || startup != XFU_COMMAND_EXTRACT)) {
        free(startup_files); return 2;
    }
#ifdef _WIN32
    if (ui.smoke && backend == XXWIDGETS_BACKEND_TUI && !smoke_console_create(&console)) {
        smoke_console_destroy(&console); free(startup_files); return 2;
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
    if (settings_load_status != XXFC_OK) show_status(&ui, "Cannot load application settings. Using defaults.");
#ifdef _WIN32
    if (desktop_shell(&ui) && !install_native_shortcuts(&ui)) {
        ui.exit_code = 2; goto cleanup;
    }
#endif
    for (file_index = 0; file_index < startup_file_count; ++file_index) {
        if (!queue_path(&ui, startup_files[file_index])) { ui.exit_code = 2; goto cleanup; }
    }
    ui.running = 1;
    if (ui.smoke && !have_archive) {
        ui.exit_code = smoke_widgets(&ui) ? 0 : 2;
        ui.running = 0;
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
        if (ui.pending_command != XFU_COMMAND_NONE && !ui.closing) {
            xfu_command command = ui.pending_command;
            ui.pending_command = XFU_COMMAND_NONE;
            start_job(&ui, command);
        }
        drain_job(&ui);
        if (ui.type_smoke) smoke_file_types(&ui);
        if (ui.options_requested) { ui.options_requested = 0; show_options(&ui); }
        if (ui.formats_requested) { ui.formats_requested = 0; show_supported_types(&ui); }
        if (ui.about_requested) {
            ui.about_requested = 0;
            if (xxwidgets_about_dialog_show(ui.about, ui.window) != XXWIDGETS_OK)
                show_status(&ui, "Cannot show the About dialog.");
        }
    }
cleanup:
    free(startup_files);
    if (ui.job) { cancel_job(&ui); job_destroy(ui.job); }
    free_entries(ui.listed_entries, ui.listed_count);
    free(ui.file_types_path);
    free(ui.pending_type_path);
    for (i = 0; (size_t)i < ui.queued_count; ++i) free(ui.queued_paths[i]);
    free(ui.queued_paths);
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
