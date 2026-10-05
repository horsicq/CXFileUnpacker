/* SPDX-License-Identifier: MIT
 * Direct native archive fixture probe. No archived program is executed.
 * Short reads, nonzero base, cursor preservation, RAM-only TEST, limits,
 * cancellation and repeated iterator ownership are checked independently.
 */
#include "xxfclib/formats/nsis/xx_nsis.h"
#include "xxfclib/formats/nowcompress/xx_nowcompress.h"
#include "xxfclib/formats/cpm_crunch/xx_cpm_crunch.h"
#include "xxfclib/formats/amplus/xx_amplus.h"
#include "xxfclib/formats/warp/xx_warp.h"
#include "xxfclib/formats/lhwarp/xx_lhwarp.h"
#include "xxfclib/formats/compdisk/xx_compdisk.h"
#include "xxfclib/formats/arc_cbm/xx_arc_cbm.h"
#include "xxfclib/formats/crunchdisk/xx_crunchdisk.h"
#include "xxfclib/formats/lhf/xx_lhf.h"
#include "xxfclib/formats/shrink_cdaf/xx_shrink_cdaf.h"
#include "xxfclib/formats/spack/xx_spack.h"
#include "xxfclib/formats/pcompress_pack/xx_pcompress_pack.h"
#include "xxfclib/formats/balz/xx_balz.h"
#include "xxfclib/formats/quad/xx_quad.h"
#include "xxfclib/formats/paq8/xx_paq8.h"
#include "xxfclib/formats/lrzip/xx_lrzip.h"
#include "xxfclib/formats/grzip/xx_grzip.h"
#include "xxfclib/formats/lpaq8/xx_lpaq8.h"
#include "xxfclib/formats/lpaq1/xx_lpaq1.h"
#include "xxfclib/formats/lpaq5/xx_lpaq5.h"
#include "xxfclib/formats/savage/xx_savage.h"
#include "xxfclib/formats/mxm_simplearc/xx_mxm_simplearc.h"
#include "xxfclib/formats/sds_sfx/xx_sds_sfx.h"
#include "xxfclib/formats/lhpak_sfx/xx_lhpak_sfx.h"
#include "xxfclib/formats/lhsfx/xx_lhsfx.h"
#include "xxfclib/formats/s_omni/xx_s_omni.h"
#include "xxfclib/formats/lha/xx_lha.h"
#include "xxfclib/formats/dms/xx_dms.h"
#include "xxfclib/rt/xx_rt.h"
#include "xx_archive_additions_detect.inc"
#include "xx_legacy_archive.h"
#include "xx_archive_codec_pipe.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* The private member adapter's generic helpers reference this callback;
 * this test translation unit only uses the independent pipe client. */
static bool pm_parse(Abstractformat *f,pm_stream *s,xx_pd_struct *pd) { (void)f;(void)s;(void)pd;return false; }
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"archive lifecycle %d: %s\n",__LINE__,#x); goto done; } } while(0)
typedef struct short_io { xx_io_device device; xx_io_device *source; xx_pd_struct *cancel; bool fired; } short_io;
static ssize_t short_read(xx_io_device *d,void *p,size_t n) { short_io *s=(short_io *)d->priv; ssize_t got;
    if(n>17U) n=17U; got=xx_io_read(s->source,p,n); if(got>0 && s->cancel) { s->fired=true; xx_pd_stop(s->cancel); } return got; }
static int short_seek(xx_io_device *d,int64_t at,int whence) { return xx_io_seek64(((short_io *)d->priv)->source,at,whence); }
static int64_t short_tell(xx_io_device *d) { return xx_io_tell(((short_io *)d->priv)->source); }
static int64_t short_size(xx_io_device *d) { return xx_io_size(((short_io *)d->priv)->source); }
typedef struct observed { unsigned calls,stop; } observed;
static bool observe(const xx_pd_struct *pd,void *p) { observed *o=(observed *)p; (void)pd; ++o->calls; return o->stop && o->calls>=o->stop; }
typedef union reader_storage { xx_legacy_archive_info common; xx_lha lha; xx_dms dms; xx_lpaq8 lpaq8; } reader_storage;
static bool init_reader(const char *name,reader_storage *r,xx_io_device *d) {
    memset(r,0,sizeof(*r));
#define READER(n) if(!strcmp(name,#n)) { xx_##n##_init((xx_##n *)r,d,63); return true; }
    READER(nsis) READER(nowcompress) READER(cpm_crunch) READER(amplus) READER(warp)
    READER(lhwarp) READER(compdisk) READER(arc_cbm) READER(crunchdisk) READER(lhf)
    READER(shrink_cdaf) READER(spack) READER(pcompress_pack)
    READER(lha) READER(dms) READER(balz) READER(quad) READER(paq8) READER(lrzip) READER(grzip) READER(lpaq8) READER(lpaq1) READER(lpaq5)
    READER(savage) READER(mxm_simplearc) READER(sds_sfx) READER(lhpak_sfx) READER(lhsfx) READER(s_omni)
#undef READER
    return false;
}
int main(int argc,char **argv) {
    FILE *input=NULL; long length; uint8_t *bytes=NULL; xx_io_device *memory=NULL;
    short_io io={0}; reader_storage reader; Abstractformat *f=&reader.common.format;
    xx_archive_record_state *st=NULL; xx_io_memory_only_scope scope={0}; xx_list_s options;
    bool initialized=false,scoped=false,opts=false,existing; xx_pd_struct pd; unsigned round; uint64_t expected,count;
    int result=1;
    CHECK(argc==4); existing=!strcmp(argv[1],"lha") || !strcmp(argv[1],"dms"); input=fopen(argv[2],"rb"); CHECK(input && !fseek(input,0,SEEK_END));
    length=ftell(input); CHECK(length>0 && length<=64L*1024L*1024L && !fseek(input,0,SEEK_SET));
    bytes=(uint8_t *)malloc((size_t)length+63U); CHECK(bytes); memset(bytes,0xA5,63);
    CHECK(fread(bytes+63U,1,(size_t)length,input)==(size_t)length); fclose(input); input=NULL;
    memory=xx_io_mem_open_ro(bytes,(size_t)length+63U); CHECK(memory);
    io.source=memory; io.device.priv=&io; io.device.read=short_read; io.device.seek64=short_seek;
    io.device.tell=short_tell; io.device.total_size=short_size;
    CHECK(init_reader(argv[1],&reader,&io.device)); initialized=true; CHECK(xx_io_seek64(memory,3,SEEK_SET)==0);
    CHECK(xx_io_memory_only_begin(&scope,UINT64_C(256)*1024U*1024U)); scoped=true;
    pd=xx_pd_init(); if(!xx_format_is_valid(f,&pd)) { fprintf(stderr,"%s\n",pd.error_string); CHECK(existing || xx_io_tell(memory)==3); result=2; goto done; }
    if(strcmp(argv[1],"lha") && strcmp(argv[1],"dms") && strcmp(argv[1],"quad")) {
        xx_io_device *gate=xx_io_mem_open_ro(bytes+63,(size_t)length); bool candidate;
        CHECK(gate && xx_io_seek64(gate,3,SEEK_SET)==0);
        candidate=xx_archive_addition_candidate(f->file_type,gate,bytes+63,(size_t)length<512U?(size_t)length:512U,length);
        CHECK(xx_io_tell(gate)==3); xx_io_close(gate); CHECK(candidate);
    }
    CHECK(existing || xx_io_tell(memory)==3);
    pd=xx_pd_init(); xx_pd_stop(&pd); CHECK(!f->check_is_valid(f,&pd));
    CHECK(xx_format_create_archive_records_reading(f,NULL,&pd)==NULL && (existing || xx_io_tell(memory)==3));
    pd=xx_pd_init(); io.cancel=&pd;
    CHECK(xx_format_create_archive_records_reading(f,NULL,&pd)==NULL && io.fired && (existing || xx_io_tell(memory)==3)); io.cancel=NULL;
    if(!existing) {
        observed o={0}; xx_pd_observer previous; pd=xx_pd_init(); previous=xx_pd_set_observer(&pd,observe,&o);
        /* Pipe polling count depends on scheduling; never derive a future stop
         * threshold from an earlier child process's elapsed wait. */
        CHECK(f->check_is_valid(f,&pd) && o.calls>=5U); o.stop=5U; o.calls=0U; pd=xx_pd_init();
        CHECK(!f->check_is_valid(f,&pd) && xx_pd_is_stopped(&pd) && (existing || xx_io_tell(memory)==3));
        if(!strcmp(argv[1],"quad")||!strcmp(argv[1],"paq8")||!strncmp(argv[1],"lpaq",4)||!strcmp(argv[1],"grzip")) {
            ac_blob b={0};uint8_t output[8]={0};o.calls=0;o.stop=3;pd=xx_pd_init();
            b.p=bytes+63;b.n=(uint32_t)length;b.limit=UINT64_C(256)*1024U*1024U;b.pd=&pd;
            /* The third pipe poll occurs after spawning the helper. */
            CHECK(!af_decode(&b,1,output,sizeof(output))&&xx_pd_is_stopped(&pd));
        }
        xx_pd_set_observer(previous.progress,previous.callback,previous.user_data);
    }
    CHECK(xx_format_handle_base_info(f,NULL)); expected=f->number_of_archive_records; CHECK(expected>0);
    for(round=0;round<4U && strcmp(argv[1],"lha") && strcmp(argv[1],"dms");++round) {
        xx_meta m; uint32_t id=(round&1U)?XX_META_ID_OPT_MAX_MEMBER_SIZE:XX_META_ID_OPT_MEMORY_LIMIT;
        xx_list_init(&options,sizeof(xx_meta),xx_meta_free_elem); opts=true; xx_meta_init(&m,id); xx_var_set_u64(&m.var,1);
        if(round<2U) CHECK(xx_list_append(&options,&m)); else CHECK(xx_format_set_extra_parameter(f,id,&m.var));
        xx_meta_cleanup(&m); CHECK(xx_format_create_archive_records_reading(f,&options,NULL)==NULL);
        xx_list_cleanup(&options); opts=false; if(round>=2U) CHECK(xx_format_remove_extra_parameter(f,id));
    }
    for(round=0;round<2U;++round) {
        st=xx_format_create_archive_records_reading(f,NULL,NULL); CHECK(st && st->total_records==expected); count=0;
        do { const xx_archive_record *record=xx_format_get_current_archive_record(f,st); CHECK(record && xx_archive_record_get_original_name(record));
            pd=xx_pd_init(); xx_pd_stop(&pd); CHECK(!xx_format_unpack_current_archive_record(f,st,&pd));
            CHECK(xx_format_unpack_current_archive_record(f,st,NULL) && (existing || xx_io_tell(memory)==3)); ++count;
        } while(xx_format_archive_record_move_to_next(f,st,NULL));
        CHECK(count==expected); xx_format_free_archive_records_reading(f,st); st=NULL;
    }
    CHECK(xx_io_memory_only_end(&scope)); scoped=false;
    if(strcmp(argv[3],"-")) {
        xx_meta m; xx_list_init(&options,sizeof(xx_meta),xx_meta_free_elem); opts=true; xx_meta_init(&m,XX_META_ID_OPT_UNPACK_PATH);
        CHECK(xx_var_set_str(&m.var,argv[3]) && xx_list_append(&options,&m));
        st=xx_format_create_archive_records_reading(f,&options,NULL); CHECK(st); xx_list_cleanup(&options); opts=false;
        do { CHECK(xx_format_unpack_current_archive_record(f,st,NULL)); } while(xx_format_archive_record_move_to_next(f,st,NULL));
        xx_format_free_archive_records_reading(f,st); st=NULL;
    }
    printf("members=%llu incomplete=%u\n",(unsigned long long)expected,strcmp(argv[1],"lha") && strcmp(argv[1],"dms") && reader.common.incomplete?1U:0U); result=0;
done:
    if(st) xx_format_free_archive_records_reading(f,st); if(opts) xx_list_cleanup(&options);
    if(initialized) { if(f->destroy) f->destroy(f); else xx_format_cleanup_extra_parameters(f); }
    if(scoped && !xx_io_memory_only_end(&scope)) result=1;
    if(memory) xx_io_close(memory); if(input) fclose(input); free(bytes); return result;
}
