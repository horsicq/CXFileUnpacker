/* SPDX-License-Identifier: MIT. Public API lifecycle controls on borrowed RAM. */
#include "xxfclib/formats/volume/xx_volume.h"
#include "xxfclib/memory/xx_memory.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct vl_source { xx_io_device io; const uint8_t *bytes; size_t size,step; int64_t cursor; uint64_t read; xx_pd_struct *cancel; } vl_source;
static ssize_t vl_input(xx_io_device *io,void *out,size_t n) { vl_source *s=(vl_source *)io->priv; if(s->cursor<0 || (uint64_t)s->cursor>s->size) return -1; if(n>s->size-(size_t)s->cursor) n=s->size-(size_t)s->cursor; if(n>s->step) n=s->step; memcpy(out,s->bytes+s->cursor,n); s->cursor+=(int64_t)n; s->read+=n; if(s->cancel && n) { xx_pd_stop(s->cancel); s->cancel=NULL; } return (ssize_t)n; }
static int vl_seek(xx_io_device *io,int64_t at,int whence) { vl_source *s=(vl_source *)io->priv; if(whence==SEEK_CUR) at+=s->cursor; else if(whence==SEEK_END) at+=(int64_t)s->size; else if(whence!=SEEK_SET) return -1; if(at<0 || (uint64_t)at>s->size) return -1; s->cursor=at; return 0; }
static int vl_seek32(xx_io_device *io,long at,int whence) { return vl_seek(io,at,whence); }
static int64_t vl_tell(xx_io_device *io) { return ((vl_source *)io->priv)->cursor; }
static int64_t vl_size(xx_io_device *io) { return (int64_t)((vl_source *)io->priv)->size; }
static bool vl_outer(Abstractformat *f,uint32_t id,uint64_t value) { xx_var var; bool ok; xx_var_init(&var); xx_var_set_u64(&var,value); ok=xx_format_set_extra_parameter(f,id,&var); xx_var_cleanup(&var); return ok; }
static bool vl_option(xx_list_s *o,uint32_t id,uint64_t value) { xx_meta m; xx_meta_init(&m,id); xx_var_set_u64(&m.var,value); return xx_list_append(o,&m); }
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"legacy lifecycle line %u: %s\n",(unsigned)__LINE__,#x); goto done; } ++checks; } while(0)
int main(int argc,char **argv) {
    FILE *file=NULL; long length; uint8_t *bytes=NULL,*copy=NULL; vl_source src={0}; xx_volume r; bool initialized=false,scoped=false; xx_io_memory_only_scope scope={0}; xx_archive_record_state *state=NULL; xx_pd_struct pd; xx_list_s opts; unsigned checks=0; int result=1;
    if(argc!=3) return 2; xx_list_init(&opts,sizeof(xx_meta),xx_meta_cleanup); file=fopen(argv[2],"rb"); if(!file || fseek(file,0,SEEK_END) || (length=ftell(file))<0 || length>64L*1024L*1024L || fseek(file,0,SEEK_SET)) goto done;
    bytes=(uint8_t *)malloc((size_t)length+17); copy=(uint8_t *)malloc((size_t)length); if(!bytes || !copy || fread(bytes+17,1,(size_t)length,file)!=(size_t)length) goto done; fclose(file); file=NULL; memset(bytes,0xCC,17); memcpy(copy,bytes+17,(size_t)length);
    src.bytes=bytes; src.size=(size_t)length+17; src.step=3; src.cursor=11; src.io.priv=&src; src.io.read=vl_input; src.io.seek=vl_seek32; src.io.seek64=vl_seek; src.io.tell=vl_tell; src.io.total_size=vl_size;
    CHECK(xx_io_memory_only_begin(&scope,16U*1024U*1024U)); scoped=true; xx_volume_init(&r,&src.io,17,(xx_file_type_t)atoi(argv[1]),"img"); initialized=true;
    CHECK(xx_format_is_valid(&r.format,NULL) && src.cursor==11);
    CHECK(vl_outer(&r.format,XX_META_ID_OPT_MEMORY_LIMIT,1));
    CHECK(!xx_format_create_archive_records_reading(&r.format,NULL,NULL) && src.cursor==11);
    CHECK(vl_option(&opts,XX_META_ID_OPT_MEMORY_LIMIT,16U*1024U*1024U));
    state=xx_format_create_archive_records_reading(&r.format,&opts,NULL); CHECK(state && state->has_record && src.cursor==11);
    while(state->has_record && !xx_archive_record_get_meta_u64(&state->current_record,XX_META_ID_UNCOMPRESSED_SIZE,0)) {
        if(!xx_format_archive_record_move_to_next(NULL,state,NULL)) break;
    }
    CHECK(state->has_record && xx_archive_record_get_meta_u64(&state->current_record,XX_META_ID_UNCOMPRESSED_SIZE,0)>1 && src.cursor==11);
    xx_list_cleanup(&opts); xx_list_init(&opts,sizeof(xx_meta),xx_meta_cleanup);
    /* The iterator owns its option copy after caller cleanup. The lower
     * outer default does not replace the iterator's larger active override. */
    CHECK(xx_format_unpack_current_archive_record(NULL,state,NULL) && src.cursor==11);
    xx_list_cleanup(&state->options); xx_list_init(&state->options,sizeof(xx_meta),xx_meta_cleanup);
    CHECK(vl_option(&state->options,XX_META_ID_OPT_MEMORY_LIMIT,1));
    CHECK(!xx_format_unpack_current_archive_record(NULL,state,NULL) && src.cursor==11);
    xx_list_cleanup(&state->options); xx_list_init(&state->options,sizeof(xx_meta),xx_meta_cleanup);
    CHECK(vl_option(&state->options,XX_META_ID_OPT_MEMORY_LIMIT,16U*1024U*1024U));
    CHECK(vl_outer(&r.format,XX_META_ID_OPT_MAX_MEMBER_SIZE,1));
    CHECK(!xx_format_unpack_current_archive_record(NULL,state,NULL) && src.cursor==11);
    CHECK(vl_outer(&r.format,XX_META_ID_OPT_MAX_MEMBER_SIZE,UINT64_MAX));
    pd=xx_pd_init(); xx_pd_stop(&pd); CHECK(!xx_format_create_archive_records_reading(&r.format,NULL,&pd) && src.cursor==11);
    pd=xx_pd_init(); src.cancel=&pd; CHECK(!xx_format_unpack_current_archive_record(NULL,state,&pd) && xx_pd_is_stopped(&pd) && src.cursor==11);
    src.step=SIZE_MAX; pd=xx_pd_init(); CHECK(xx_format_unpack_current_archive_record(NULL,state,&pd) && src.cursor==11);
    { xx_archive_record_state *previous=state;
      state=xx_format_create_archive_records_reading(&r.format,&previous->options,NULL);
      xx_format_free_archive_records_reading(NULL,previous);
      CHECK(state && state->has_record && src.cursor==11); }
    /* Every retained iterator record, including directories, empty files and
     * information, must enforce a lower active aggregate memory override. */
    while(state->has_record) {
        xx_meta *memory=(xx_meta *)xx_list_at(&state->options,0); uint64_t before=xx_io_memory_only_used();
        if(!memory || memory->meta_id!=XX_META_ID_OPT_MEMORY_LIMIT) goto done;
        xx_var_set_u64(&memory->var,1);
        CHECK(!xx_format_unpack_current_archive_record(NULL,state,NULL) && src.cursor==11 && xx_io_memory_only_used()==before);
        xx_var_set_u64(&memory->var,16U*1024U*1024U);
        CHECK(xx_format_unpack_current_archive_record(NULL,state,NULL) && src.cursor==11);
        if(!xx_format_archive_record_move_to_next(NULL,state,NULL)) break;
    }
    CHECK(memcmp(bytes+17,copy,(size_t)length)==0);
    xx_format_free_archive_records_reading(NULL,state); state=NULL; xx_volume_destroy(&r); initialized=false; CHECK(xx_io_memory_only_used()==0);
    result=0; printf("%u legacy lifecycle checks passed\n",checks);
done: if(state) xx_format_free_archive_records_reading(NULL,state); if(initialized) xx_volume_destroy(&r); if(scoped && !xx_io_memory_only_end(&scope)) result=1; xx_list_cleanup(&opts); free(bytes); free(copy); if(file) fclose(file); return result;
}
