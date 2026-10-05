/* SPDX-License-Identifier: MIT
 * Native reader fixture driver with independent short-I/O, cancellation,
 * cursor, limit and repeated ownership checks. Inputs are disk data only.
 */
#include "xxfclib/formats/ensoniq_gkh/xx_ensoniq_gkh.h"
#include "xxfclib/formats/ensoniq_ede/xx_ensoniq_ede.h"
#include "xxfclib/formats/samcoupe_sad/xx_samcoupe_sad.h"
#include "xxfclib/formats/apple_nib/xx_apple_nib.h"
#include "xxfclib/formats/ti99_pc99/xx_ti99_pc99.h"
#include "xxfclib/formats/emax_disk/xx_emax_disk.h"
#include "xxfclib/formats/emulatorii_eii/xx_emulatorii_eii.h"
#include "xxfclib/formats/casio_fzf/xx_casio_fzf.h"
#include "xxfclib/formats/vtr_disk/xx_vtr_disk.h"
#include "xxfclib/formats/speccydos_sdd/xx_speccydos_sdd.h"
#include "xxfclib/formats/thomson_fd/xx_thomson_fd.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"HxC lifecycle line %d: %s\n",__LINE__,#x); goto done; } } while (0)
typedef union reader_storage { xx_hxc_sector_info common; xx_thomson_fd fd; } reader_storage;
typedef struct short_io { xx_io_device device; xx_io_device *source; xx_pd_struct *cancel; bool fired; } short_io;
static ssize_t read_short(xx_io_device *d, void *p, size_t n) {
    short_io *io = (short_io *)d->priv; ssize_t got;
    if (n > 17U) n = 17U;
    got = xx_io_read(io->source,p,n);
    if (got > 0 && io->cancel) { xx_pd_stop(io->cancel); io->fired = true; }
    return got;
}
static int seek_short(xx_io_device *d, int64_t n, int w) { return xx_io_seek64(((short_io *)d->priv)->source,n,w); }
static int64_t tell_short(xx_io_device *d) { return xx_io_tell(((short_io *)d->priv)->source); }
static int64_t size_short(xx_io_device *d) { return xx_io_size(((short_io *)d->priv)->source); }
static bool init_reader(const char *name, reader_storage *r, xx_io_device *d) {
    memset(r,0,sizeof(*r));
#define READER(n) if (!strcmp(name,#n)) { xx_##n##_init((xx_##n *)r,d,0); return true; }
    READER(ensoniq_gkh) READER(ensoniq_ede) READER(samcoupe_sad)
    READER(apple_nib) READER(ti99_pc99) READER(emax_disk)
    READER(emulatorii_eii) READER(casio_fzf) READER(vtr_disk) READER(speccydos_sdd)
    READER(thomson_fd)
#undef READER
    if (!strcmp(name,"thomson_fd_hxc")) { xx_thomson_fd_init_hxc(&r->fd,d,0); return true; }
    return false;
}
int main(int argc,char **argv) {
    xx_io_device *source = NULL; short_io io = {0}; reader_storage r; Abstractformat *f = (Abstractformat *)&r;
    xx_archive_record_state *st = NULL; xx_pd_struct pd; xx_list_s options; bool initialized = false, opts = false;
    bool structured; uint64_t expected, count; unsigned round; int result = 1;
    CHECK(argc == 4);
    source = xx_io_file_open(argv[2],"rb"); CHECK(source);
    io.source = source; io.device.priv = &io; io.device.read = read_short;
    io.device.seek64 = seek_short; io.device.tell = tell_short; io.device.total_size = size_short;
    CHECK(init_reader(argv[1],&r,&io.device)); initialized = true;
    structured = strncmp(argv[1],"thomson_fd",10) != 0;
    CHECK(xx_io_seek64(source,3,SEEK_SET) == 0);
    if (!xx_format_is_valid(f,NULL)) { CHECK(xx_io_tell(source) == 3); result = 2; goto done; }
    CHECK(xx_io_tell(source) == 3);
    pd = xx_pd_init(); pd.is_stop = true;
    CHECK(!xx_format_is_valid(f,&pd));
    CHECK(xx_format_create_archive_records_reading(f,NULL,&pd) == NULL);
    CHECK(xx_io_tell(source) == 3);
    pd = xx_pd_init(); io.cancel = &pd; io.fired = false;
    CHECK(xx_format_create_archive_records_reading(f,NULL,&pd) == NULL && io.fired);
    CHECK(xx_io_tell(source) == 3); io.cancel = NULL;
    CHECK(xx_format_handle_base_info(f,NULL));
    expected = f->number_of_archive_records; CHECK(expected > 0U);
    if (structured) for (round = 0U; round < 4U; ++round) {
        xx_meta m; uint32_t id = (round & 1U) ? XX_META_ID_OPT_MAX_MEMBER_SIZE : XX_META_ID_OPT_MEMORY_LIMIT;
        xx_list_init(&options,sizeof(xx_meta),xx_meta_free_elem); opts = true;
        xx_meta_init(&m,id); xx_var_set_u64(&m.var,1U);
        if (round < 2U) {
            if (!xx_list_append(&options,&m)) { xx_meta_cleanup(&m); goto done; }
        } else if (!xx_format_set_extra_parameter(f,id,&m.var)) { xx_meta_cleanup(&m); goto done; }
        xx_meta_cleanup(&m);
        CHECK(xx_format_create_archive_records_reading(f,&options,NULL) == NULL);
        xx_list_cleanup(&options); opts = false;
        if (round >= 2U) CHECK(xx_format_remove_extra_parameter(f,id));
    }
    for (round = 0U; round < 3U; ++round) {
        xx_meta destination;
        xx_list_init(&options,sizeof(xx_meta),xx_meta_free_elem); opts = true;
        if (round == 2U && strcmp(argv[3],"-")) {
            xx_meta_init(&destination,XX_META_ID_OPT_UNPACK_PATH);
            if (!xx_var_set_str(&destination.var,argv[3]) || !xx_list_append(&options,&destination)) {
                xx_meta_cleanup(&destination); goto done;
            }
            /* xx_list_append takes this shallow element by value; the list
             * now owns its string. Iterator creation makes its own copy. */
        }
        st = xx_format_create_archive_records_reading(f,&options,NULL);
        xx_list_cleanup(&options); opts = false;
        CHECK(st && st->total_records == expected && xx_io_tell(source) == 3);
        count = 0U;
        do {
            const xx_archive_record *record = xx_format_get_current_archive_record(f,st);
            CHECK(record && xx_archive_record_get_original_name(record));
            pd = xx_pd_init(); pd.is_stop = true;
            CHECK(!xx_format_unpack_current_archive_record(f,st,&pd));
            CHECK(xx_format_unpack_current_archive_record(f,st,NULL));
            CHECK(xx_io_tell(source) == 3); ++count;
        } while (xx_format_archive_record_move_to_next(f,st,NULL));
        CHECK(count == expected);
        xx_format_free_archive_records_reading(f,st); st = NULL;
    }
    printf("members=%llu incomplete=%u\n",(unsigned long long)expected,
        structured && r.common.incomplete ? 1U : 0U);
    result = 0;
done:
    if (st) xx_format_free_archive_records_reading(f,st);
    if (opts) xx_list_cleanup(&options);
    if (initialized) xx_format_cleanup_extra_parameters(f);
    if (source) xx_io_close(source);
    return result;
}
