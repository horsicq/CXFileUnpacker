#include "core.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif

#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); exit(1); } } while (0)
typedef struct observation { int calls, stop; uint64_t current; } observation;

static bool observe(const xx_pd_struct *pd, void *user)
{
    observation *seen = (observation *)user;
    ++seen->calls; seen->current = pd->records[0].current;
    /* Querying from a callback must not recursively invoke the observer. */
    CHECK(xx_pd_is_stopped(pd) == pd->is_stop);
    return seen->stop != 0;
}

#ifdef _WIN32
static DWORD WINAPI worker(LPVOID user)
#else
static void *worker(void *user)
#endif
{
    observation *seen = (observation *)user;
    xx_pd_struct pd = xx_pd_init();
    xx_pd_observer previous = xx_pd_set_observer(&pd, observe, seen);
    CHECK(!previous.progress && !previous.callback && !previous.user_data);
    CHECK(xx_pd_enter_level(&pd, 10, "Worker") == 0 && seen->calls == 1);
    xx_pd_set_observer(previous.progress, previous.callback, previous.user_data);
    xx_pd_increment_current(&pd, 0, 2);
    CHECK(seen->calls == 1);
    return 0;
}

int main(void)
{
    xx_pd_struct pd = xx_pd_init(), other = xx_pd_init();
    observation seen = {0}, thread_seen = {0}, nested = {0};
    xx_pd_observer previous = xx_pd_set_observer(&pd, observe, &seen), binding;
    CHECK(!previous.callback);
    CHECK(xx_pd_enter_level(&other, 10, "Other") == 0 && !seen.calls);
    CHECK(xx_pd_enter_level(&pd, 10, "Main") == 0 && seen.calls == 1);
    xx_pd_set_current(&pd, 0, 3);
    CHECK(seen.calls == 2 && seen.current == 3);
    xx_pd_increment_current(&pd, 0, 1);
    CHECK(seen.calls == 3 && seen.current == 4);
    binding = xx_pd_set_observer(&other, observe, &nested);
    CHECK(binding.progress == &pd && binding.callback == observe && binding.user_data == &seen);
    xx_pd_set_current(&other, 0, 1);
    CHECK(nested.calls == 1 && seen.calls == 3);
    xx_pd_set_observer(binding.progress, binding.callback, binding.user_data);
#ifdef _WIN32
    {
        HANDLE thread = CreateThread(NULL, 0, worker, &thread_seen, 0, NULL);
        CHECK(thread && WaitForSingleObject(thread, 5000) == WAIT_OBJECT_0 && CloseHandle(thread));
    }
#else
    {
        pthread_t thread;
        CHECK(pthread_create(&thread, NULL, worker, &thread_seen) == 0 && pthread_join(thread, NULL) == 0);
    }
#endif
    CHECK(thread_seen.calls == 1 && seen.calls == 3);
    xx_pd_set_error(&pd, 7, "Error");
    CHECK(seen.calls == 4 && pd.last_error == 7 && !strcmp(pd.error_string, "Error"));
    xx_pd_clear_error(&pd);
    CHECK(seen.calls == 5 && !pd.last_error);
    seen.stop = 1;
    CHECK(xx_pd_is_stopped(&pd) && seen.calls == 6);
    xx_pd_set_current(&pd, 0, 5);
    CHECK(pd.is_stop && seen.calls == 7);
    xx_pd_leave_level(&pd, 0);
    CHECK(!pd.records[0].is_busy && seen.calls == 8);
    xx_pd_set_observer(previous.progress, previous.callback, previous.user_data);
    xx_pd_stop(&pd);
    CHECK(seen.calls == 8);
    puts("Progress observer snapshots, cancellation, recursion and thread isolation passed");
    return 0;
}
