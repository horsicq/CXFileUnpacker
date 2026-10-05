/* Exercise cancellation inside HFE Amiga scans using a synchronous observer.
 * The independent Python fixture writer supplies the valid input. */
#include "xxfclib/formats/hfe/xx_hfe.h"
#include "xxfclib/io/xx_io.h"
#include "xxfclib/data/xx_pd.h"
#include <stdio.h>
#include <stdlib.h>

#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); exit(1); } } while (0)

typedef struct observation { size_t calls, stop_after; } observation;

static bool observe(const xx_pd_struct *pd, void *user)
{
    observation *seen = (observation *)user;
    (void)pd;
    ++seen->calls;
    return seen->stop_after != 0U && seen->calls >= seen->stop_after;
}

int main(int argc, char **argv)
{
    xx_io_device *device;
    xx_hfe archive;
    xx_pd_struct pd = xx_pd_init();
    xx_pd_observer previous;
    xx_archive_record_state *state;
    observation seen = {0U, 0U};
    size_t probe_checks;
    CHECK(argc == 2);
    device = xx_io_file_open(argv[1], "rb");
    CHECK(device != NULL);
    xx_hfe_init(&archive, device, 0);
    previous = xx_pd_set_observer(&pd, observe, &seen);
    CHECK(xx_hfe_check_is_valid(&archive.format, &pd));
    probe_checks = seen.calls;
    CHECK(probe_checks > 16U);

    /* These requests arrive after entry/header checks, inside the bit scan. */
    seen.calls = 0U;
    seen.stop_after = 8U;
    CHECK(!xx_hfe_check_is_valid(&archive.format, &pd) && seen.calls == 8U);
    seen.calls = 0U;
    CHECK(!xx_hfe_handle_base_info(&archive.format, &pd) && seen.calls == 8U);
    CHECK(!archive.format.base_info_handled);
    seen.calls = 0U;
    CHECK(xx_hfe_create_archive_records_reading(&archive.format, NULL, &pd) == NULL && seen.calls == 8U);

    state = xx_hfe_create_archive_records_reading(&archive.format, NULL, NULL);
    CHECK(state != NULL);
    seen.calls = 0U;
    seen.stop_after = 0U;
    CHECK(xx_hfe_unpack_current_archive_record(&archive.format, state, &pd));
    CHECK(seen.calls > probe_checks + 8U);
    /* Parsing has one scan; unpacking has that probe and a second rendering
     * scan. Stop after the first scan to cover the rendering path separately. */
    seen.calls = 0U;
    seen.stop_after = probe_checks + 8U;
    CHECK(!xx_hfe_unpack_current_archive_record(&archive.format, state, &pd));
    CHECK(seen.calls == seen.stop_after);

    pd.is_stop = true;
    seen.calls = 0U;
    CHECK(!xx_hfe_check_is_valid(&archive.format, &pd));
    CHECK(!xx_hfe_handle_base_info(&archive.format, &pd));
    CHECK(xx_hfe_create_archive_records_reading(&archive.format, NULL, &pd) == NULL);
    CHECK(!xx_hfe_unpack_current_archive_record(&archive.format, state, &pd));
    CHECK(seen.calls == 0U);
    xx_pd_set_observer(previous.progress, previous.callback, previous.user_data);
    xx_hfe_free_archive_records_reading(&archive.format, state);
    xx_hfe_destroy(&archive);
    xx_io_close(device);
    puts("HFE Amiga validation, record creation and rendering cancellation passed");
    return 0;
}
