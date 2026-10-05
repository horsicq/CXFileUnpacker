/* SPDX-License-Identifier: MIT
 * Raw/XML API ownership, explicit selection and lifecycle checks. These
 * synthetic devices contain only data; no descriptor path is opened.
 */
#include "xxfclib/formats/hxc_raw_floppy/xx_hxc_raw_floppy.h"
#include "xxfclib/formats/hxc_xml_disk_layout/xx_hxc_xml_disk_layout.h"
#include "xxfc_readers.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"HxC layout line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
typedef struct small_io { xx_io_device device; xx_io_device *source; xx_pd_struct *pd; bool fired; } small_io;
static ssize_t short_read(xx_io_device *d,void *buffer,size_t size) {
    small_io *io=(small_io *)d->priv; ssize_t got;
    if(size>13U) size=13U;
    got=xx_io_read(io->source,buffer,size);
    if(got>0 && io->pd) { io->fired=true; xx_pd_stop(io->pd); }
    return got;
}
static int short_seek(xx_io_device *d,int64_t at,int mode) { return xx_io_seek64(((small_io *)d->priv)->source,at,mode); }
static int64_t short_tell(xx_io_device *d) { return xx_io_tell(((small_io *)d->priv)->source); }
static int64_t short_size(xx_io_device *d) { return xx_io_size(((small_io *)d->priv)->source); }
static void init_io(small_io *io,xx_io_device *source) {
    memset(io,0,sizeof(*io)); io->source=source; io->device.priv=io;
    io->device.read=short_read; io->device.seek64=short_seek;
    io->device.tell=short_tell; io->device.total_size=short_size;
}
static void exercise(xx_hxc_raw_floppy *reader,small_io *io,bool xml) {
    Abstractformat *f=&reader->format; xx_archive_record_state *st; xx_pd_struct pd;
    xx_list_s options; xx_meta m; unsigned round; uint64_t count;
    CHECK(xx_io_seek64(io->source,7,SEEK_SET)==0);
    CHECK(xx_format_is_valid(f,NULL) && xx_io_tell(io->source)==7);
    CHECK(xx_format_handle_base_info(f,NULL) && f->number_of_archive_records==2U);
    CHECK(xx_io_tell(io->source)==7);
    pd=xx_pd_init(); pd.is_stop=true;
    CHECK(!f->check_is_valid(f,&pd));
    CHECK(xx_format_create_archive_records_reading(f,NULL,&pd)==NULL);
    CHECK(xx_io_tell(io->source)==7);
    if(xml) {
        pd=xx_pd_init(); io->pd=&pd; io->fired=false;
        CHECK(xx_format_create_archive_records_reading(f,NULL,&pd)==NULL && io->fired);
        CHECK(xx_io_tell(io->source)==7); io->pd=NULL;
    }
    for(round=0U;round<4U;++round) {
        uint32_t id=round&1U ? XX_META_ID_OPT_MAX_MEMBER_SIZE : XX_META_ID_OPT_MEMORY_LIMIT;
        xx_list_init(&options,sizeof(xx_meta),xx_meta_free_elem);
        xx_meta_init(&m,id); xx_var_set_u64(&m.var,1U);
        if(round<2U) CHECK(xx_list_append(&options,&m));
        else CHECK(xx_format_set_extra_parameter(f,id,&m.var));
        xx_meta_cleanup(&m);
        st=xx_format_create_archive_records_reading(f,&options,NULL);
        xx_list_cleanup(&options);
        if(id==XX_META_ID_OPT_MEMORY_LIMIT) CHECK(st==NULL);
        else {
            CHECK(st && st->total_records==2U);
            CHECK(!xx_format_unpack_current_archive_record(f,st,NULL));
            CHECK(xx_format_archive_record_move_to_next(f,st,NULL));
            CHECK(!xx_format_unpack_current_archive_record(f,st,NULL));
            xx_format_free_archive_records_reading(f,st);
        }
        if(round>=2U) CHECK(xx_format_remove_extra_parameter(f,id));
        CHECK(xx_io_tell(io->source)==7);
    }
    for(round=0U;round<3U;++round) {
        st=xx_format_create_archive_records_reading(f,NULL,NULL);
        CHECK(st && st->total_records==2U && xx_io_tell(io->source)==7);
        count=0U;
        do {
            const xx_archive_record *record=xx_format_get_current_archive_record(f,st);
            const xx_var *comment;
            CHECK(record && xx_archive_record_get_original_name(record));
            comment=xx_archive_record_find_meta(record,XX_META_ID_COMMENT);
            CHECK(comment && xx_var_get_str(comment));
            pd=xx_pd_init(); pd.is_stop=true;
            CHECK(!xx_format_unpack_current_archive_record(f,st,&pd));
            /* The original member always reads source. A raw mapped member
             * also reads source; an initialized descriptor may contain only
             * inline/fill bytes and is covered by the entry stop above. */
            if(!xml || count==0U) {
                pd=xx_pd_init(); io->pd=&pd; io->fired=false;
                CHECK(!xx_format_unpack_current_archive_record(f,st,&pd) && io->fired);
                CHECK(xx_io_tell(io->source)==7); io->pd=NULL;
            }
            CHECK(xx_format_unpack_current_archive_record(f,st,NULL));
            CHECK(xx_io_tell(io->source)==7); ++count;
        } while(xx_format_archive_record_move_to_next(f,st,NULL));
        CHECK(count==2U);
        xx_format_free_archive_records_reading(f,st);
    }
}
static void reject_profile(xx_io_device *d,const xx_hxc_raw_profile *p) {
    xx_hxc_raw_floppy *r=xx_hxc_raw_floppy_create_layout(d,64,p);
    CHECK(r==NULL);
}
int main(void) {
    uint8_t raw[64U+512U],inline_bytes[8]={1,2,3,4,5,6,7,8}; char name[]="owned layout";
    xx_hxc_raw_extent runs[3]={{496U,16U,32U,-16,0U,XX_HXC_RAW_SOURCE,NULL},
        {0U,8U,1U,INT64_MIN,0U,XX_HXC_RAW_INLINE,inline_bytes}, {0U,4U,2U,INT64_MIN,0xE5U,XX_HXC_RAW_FILL,NULL}};
    xx_hxc_raw_profile profile={name,2U,1U,512U,runs,3U};
    xx_hxc_raw_floppy *reader; xx_io_device *device; small_io io; size_t i;
    char xml[]="<disk_layout><disk_layout_name>Owned XML</disk_layout_name><file_size>512</file_size>"
        "<layout><number_of_track>1</number_of_track><number_of_side>1</number_of_side>"
        "<sector_per_track>2</sector_per_track><sector_size>256</sector_size><formatvalue>229</formatvalue>"
        "<track_list><track track_number=\"0\" side_number=\"0\"><sector_list>"
        "<sector sector_id=\"1\"><data_offset>256</data_offset><sector_data>01020304</sector_data></sector>"
        "<sector sector_id=\"2\"><data_offset>0</data_offset><data_fill>170</data_fill></sector>"
        "</sector_list></track></track_list></layout></disk_layout>";
    const char *bad_xml[]={"<disk_layout>","<!DOCTYPE disk_layout><disk_layout/>",
        "<disk_layout><layout><number_of_track>18446744073709551616</number_of_track></layout></disk_layout>",
        "<disk_layout><layout><number_of_track>1</number_of_track><number_of_side>1</number_of_side>"
        "<sector_per_track>999999999</sector_per_track><sector_size>512</sector_size></layout></disk_layout>"};
    for(i=0U;i<sizeof(raw);++i) raw[i]=(uint8_t)(i*7U);
    device=xx_io_mem_open_ro(raw,sizeof(raw)); CHECK(device); init_io(&io,device);
    reader=xx_hxc_raw_floppy_create_layout(&io.device,64,&profile); CHECK(reader);
    CHECK(reader->profile!=&profile && reader->profile->extents!=runs && reader->profile->name!=name);
    CHECK(reader->profile->extents[1].data!=inline_bytes);
    memset(name,'X',sizeof(name)-1U); memset(inline_bytes,0,sizeof(inline_bytes)); runs[0].offset=0U;
    CHECK(!strcmp(reader->profile->name,"owned layout") && reader->profile->extents[0].offset==496U);
    CHECK(reader->profile->extents[1].data[0]==1U && reader->profile->extents[1].data[7]==8U);
    exercise(reader,&io,false); xx_hxc_raw_floppy_free(reader);

    /* Reject overflow/underflow at construction, before source I/O. */
    runs[0].offset=496U;
    profile.tracks=0U; reject_profile(&io.device,&profile); profile.tracks=2U;
    profile.source_size=UINT64_MAX; reject_profile(&io.device,&profile); profile.source_size=512U;
    runs[0].stride=INT64_MIN; reject_profile(&io.device,&profile);
    runs[0].stride=INT64_MAX; reject_profile(&io.device,&profile);
    runs[0].stride=-17; reject_profile(&io.device,&profile); runs[0].stride=-16;
    runs[0].offset=UINT64_MAX; reject_profile(&io.device,&profile); runs[0].offset=496U;
    runs[0].mode=3U; reject_profile(&io.device,&profile); runs[0].mode=XX_HXC_RAW_SOURCE;
    runs[1].data=NULL; reject_profile(&io.device,&profile); runs[1].data=inline_bytes;
    profile.extent_count=SIZE_MAX; reject_profile(&io.device,&profile); profile.extent_count=3U;

    reader=xx_hxc_raw_floppy_create_layout_xml(&io.device,64,xml,strlen(xml)); CHECK(reader);
    CHECK(reader->owned_profile && reader->profile && !strcmp(reader->profile->name,"Owned XML"));
    /* The parsed descriptor is independent of the caller's XML buffer. */
    xml[0]='X';
    exercise(reader,&io,false); xx_hxc_raw_floppy_free(reader); xml[0]='<';
    for(i=0U;i<sizeof(bad_xml)/sizeof(bad_xml[0]);++i)
        CHECK(xx_hxc_raw_floppy_create_layout_xml(&io.device,64,bad_xml[i],strlen(bad_xml[i]))==NULL);
    CHECK(xx_hxc_raw_floppy_create_profile(&io.device,64,"not-an-existing-profile")==NULL);
    xx_io_close(device);

    /* XML as the input is a descriptor initializer, distinct from a layout
     * applied to explicitly supplied raw bytes. A nonzero base is preserved. */
    {
        size_t length=strlen(xml); uint8_t *prefixed=(uint8_t *)malloc(length+64U);
        CHECK(prefixed); memset(prefixed,0xCC,64U); memcpy(prefixed+64U,xml,length);
        device=xx_io_mem_open_ro(prefixed,length+64U); CHECK(device); init_io(&io,device);
        reader=xx_hxc_xml_disk_layout_create(&io.device,64); CHECK(reader);
        exercise(reader,&io,true); xx_hxc_xml_disk_layout_free(reader); xx_io_close(device); free(prefixed);
    }
    /* Check both public named-profile construction routes against the same
     * geometry. The registry route exercises the hxc-raw:NAME selector. */
    {
        const xx_hxc_raw_profile *known=xx_hxc_raw_floppy_profile_by_name("ACORN_ADFS_160K");
        xxfc_opened opened={0}; uint8_t *bytes; char selector[160];
        CHECK(known && known->source_size==163840U);
        bytes=(uint8_t *)calloc(1U,(size_t)known->source_size+64U); CHECK(bytes);
        device=xx_io_mem_open_ro(bytes,(size_t)known->source_size+64U); CHECK(device); init_io(&io,device);
        reader=xx_hxc_raw_floppy_create_profile(&io.device,64,known->name); CHECK(reader);
        CHECK(reader->profile==known); exercise(reader,&io,false); xx_hxc_raw_floppy_free(reader);
        snprintf(selector,sizeof(selector),"hxc-raw:%s",known->name);
        CHECK(xxfc_open_named(&opened,&io.device,64,selector));
        exercise((xx_hxc_raw_floppy *)opened.format,&io,false); xxfc_close(&opened);
        xx_io_close(device); free(bytes);
    }
    puts("HxC raw/XML explicit selection, deep ownership, short I/O, base/cursor, cancellation and limits passed");
    return 0;
}
