/* SPDX-License-Identifier: MIT. Independent virtual >5 GiB Xbox region test.
 * No fixture, image or decoder work files are created. */
#include "xxfclib/formats/volume/xx_volume.h"
#include <stdio.h>
#include <string.h>
#include <limits.h>
typedef struct virtual_source {
    xx_io_device io; int64_t position, length; size_t short_read;
    uint64_t bytes; xx_pd_struct *cancel;
} virtual_source;
static ssize_t read_virtual(xx_io_device *io,void *out,size_t n) {
    virtual_source *s=(virtual_source *)io->priv; uint8_t *p=(uint8_t *)out;
    const int64_t magic=17+INT64_C(0x130EB0000); size_t i;
    if(s->position<0 || s->position>s->length) return -1;
    if(n>(uint64_t)(s->length-s->position)) n=(size_t)(s->length-s->position);
    if(n>s->short_read) n=s->short_read; memset(out,0,n);
    for(i=0;i<4;++i) if(magic+(int64_t)i>=s->position && magic+(int64_t)i-s->position<(int64_t)n)
        p[(size_t)(magic+(int64_t)i-s->position)]=(uint8_t)"FATX"[i];
    s->position+=(int64_t)n; s->bytes+=n;
    if(s->cancel && n) { xx_pd_stop(s->cancel); s->cancel=NULL; }
    return (ssize_t)n;
}
static int seek_virtual(xx_io_device *io,int64_t at,int whence) {
    virtual_source *s=(virtual_source *)io->priv;
    if(whence==SEEK_CUR) at+=s->position; else if(whence==SEEK_END) at+=s->length;
    else if(whence!=SEEK_SET) return -1;
    if(at<0 || at>s->length) return -1; s->position=at; return 0;
}
static int seek32_virtual(xx_io_device *io,long at,int whence) { return seek_virtual(io,at,whence); }
static int64_t tell_virtual(xx_io_device *io) { return ((virtual_source *)io->priv)->position; }
static int64_t size_virtual(xx_io_device *io) { return ((virtual_source *)io->priv)->length; }
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"virtual volume line %d: %s\n",__LINE__,#x); goto done; } } while(0)
int main(void) {
    const uint64_t offsets[]={0x2000ULL,0x80000ULL,0x80080000ULL,0x10C080000ULL,0x118EB0000ULL,0x120EB0000ULL,0x130EB0000ULL};
    const uint64_t lengths[]={0x80000ULL,0x80000000ULL,0xA0E30000ULL,0xCE30000ULL,0x8000000ULL,0x10000000ULL,0x100000ULL};
    virtual_source source={0}; xx_volume volume; xx_archive_record_state *state=NULL;
    xx_io_memory_only_scope scope={0}; xx_pd_struct pd; bool initialized=false,scoped=false; unsigned i; int result=1;
    source.length=17+INT64_C(0x130FB0000); source.position=11; source.short_read=3;
    source.io.priv=&source; source.io.read=read_virtual; source.io.seek=seek32_virtual;
    source.io.seek64=seek_virtual; source.io.tell=tell_virtual; source.io.total_size=size_virtual;
    CHECK(xx_io_memory_only_begin(&scope,1048576)); scoped=true;
    xx_volume_init(&volume,&source.io,17,XX_FILE_TYPE_XBOX360_LAYOUT,"img"); initialized=true;
    CHECK(xx_format_is_valid(&volume.format,NULL) && source.position==11);
    state=xx_format_create_archive_records_reading(&volume.format,NULL,NULL);
    CHECK(state && state->total_records==9 && state->has_record && source.position==11);
    source.short_read=SIZE_MAX;
    for(i=0;i<7;++i) {
        const xx_archive_record *r=xx_format_get_current_archive_record(&volume.format,state);
        CHECK(r && r->data_offset==(int64_t)(17+offsets[i]));
        CHECK(xx_archive_record_get_meta_u64(r,XX_META_ID_UNCOMPRESSED_SIZE,0)==lengths[i]);
        source.bytes=0; CHECK(xx_format_unpack_current_archive_record(NULL,state,NULL));
        CHECK(source.bytes==lengths[i] && source.position==11);
        pd=xx_pd_init(); source.cancel=&pd;
        CHECK(!xx_format_unpack_current_archive_record(NULL,state,&pd) && xx_pd_is_stopped(&pd) && source.position==11);
        CHECK(xx_format_archive_record_move_to_next(&volume.format,state,NULL));
    }
    xx_format_free_archive_records_reading(NULL,state); state=NULL;
    source.length=17+INT64_C(0x130EB0000); source.position=11;
    xx_volume_destroy(&volume);
    xx_volume_init(&volume,&source.io,17,XX_FILE_TYPE_XBOX360_LAYOUT,"img");
    CHECK(!xx_format_is_valid(&volume.format,NULL) && source.position==11);
    CHECK(xx_io_memory_only_used()==0); result=0;
    puts("Xbox exact declared regions, >5 GiB virtual source, short reads, complete RAM TEST, cursor, cancellation and truncated source passed");
done:
    if(state) xx_format_free_archive_records_reading(NULL,state);
    if(initialized) xx_volume_destroy(&volume);
    if(scoped && !xx_io_memory_only_end(&scope)) result=1;
    return result;
}
