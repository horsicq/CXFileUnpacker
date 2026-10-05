/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 * Persistent SFX ZIP credential ownership and cancellation. The synthetic
 * input is parsed as data; no code from a fixture is executed.
 */
#include "xxfclib/formats/sfx_zipcentral/xx_sfx_zipcentral.h"
#include "xxfclib/io/xx_io.h"
#include "xxfclib/memory/xx_memory.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { if(!(condition)) { \
    fprintf(stderr,"Demolition lifecycle line %d failed: %s\n",__LINE__,#condition); \
    goto done; } } while(0)

typedef struct cancel_io {
    xx_io_device device;
    xx_io_device *source;
    xx_pd_struct *monitor;
    int64_t trigger;
    size_t body_reads;
    bool armed, fired;
} cancel_io;

static ssize_t cancel_read(xx_io_device *device,void *buffer,size_t size) {
    cancel_io *proxy=(cancel_io *)device->priv;
    int64_t before=xx_io_tell(proxy->source);
    ssize_t result=xx_io_read(proxy->source,buffer,size);
    if(result>0 && before==proxy->trigger) ++proxy->body_reads;
    if(proxy->armed && result>0 && before==proxy->trigger) {
        proxy->armed=false; proxy->fired=true;
        xx_pd_stop(proxy->monitor);
    }
    return result;
}
static int cancel_seek64(xx_io_device *device,int64_t offset,int whence) {
    return xx_io_seek64(((cancel_io *)device->priv)->source,offset,whence);
}
static int cancel_seek(xx_io_device *device,long offset,int whence) {
    return cancel_seek64(device,(int64_t)offset,whence);
}
static int64_t cancel_tell(xx_io_device *device) {
    return xx_io_tell(((cancel_io *)device->priv)->source);
}
static int64_t cancel_size(xx_io_device *device) {
    return xx_io_size(((cancel_io *)device->priv)->source);
}
static int digit(char c) {
    if(c>='0' && c<='9') return c-'0';
    if(c>='a' && c<='f') return c-'a'+10;
    if(c>='A' && c<='F') return c-'A'+10;
    return -1;
}

int main(int argc,char **argv) {
    xx_io_device *source=NULL;
    xx_sfx_zipcentral *archive=NULL;
    xx_archive_record_state *state=NULL;
    cancel_io proxy={0};
    xx_pd_struct monitor;
    xx_var retained[2];
    char password[65]={0};
    unsigned round,i;
    size_t length;
    int result=1;
    for(i=0;i<2;++i) xx_var_init(&retained[i]);
    CHECK(argc==4);
    length=strlen(argv[2]);
    CHECK(length>0 && length<=128 && !(length&1U));
    for(i=0;i<length/2;++i) {
        int a=digit(argv[2][i*2]),b=digit(argv[2][i*2+1]);
        CHECK(a>=0 && b>=0 && (a || b));
        password[i]=(char)((a<<4)|b);
    }
    source=xx_io_file_open(argv[1],"rb");
    CHECK(source!=NULL);
    proxy.source=source;
    proxy.trigger=(int64_t)strtoll(argv[3],NULL,10);
    proxy.device.priv=&proxy;
    proxy.device.read=cancel_read;
    proxy.device.seek=cancel_seek;
    proxy.device.seek64=cancel_seek64;
    proxy.device.tell=cancel_tell;
    proxy.device.total_size=cancel_size;
    archive=xx_sfx_zipcentral_create(&proxy.device,0);
    CHECK(archive!=NULL);
    CHECK(xx_sfx_zipcentral_handle_base_info(&archive->format,NULL));
    CHECK(archive->format.number_of_archive_records==2);
    /* Cancel during the encrypted body read used to prove the password,
     * rather than merely before entering the reader. No state may publish. */
    monitor=xx_pd_init();
    proxy.monitor=&monitor; proxy.armed=true;
    state=xx_format_create_archive_records_reading(&archive->format,NULL,&monitor);
    CHECK(proxy.fired && xx_pd_is_stopped(&monitor) && state==NULL);
    proxy.monitor=NULL;
    /* Password discovery is a decode operation too. Respect restrictive
     * operation and format budgets; a later unlimited iterator can recover. */
    for(round=0;round<4;++round) {
        xx_list_s limits;
        xx_meta limit;
        size_t before_body_reads=proxy.body_reads;
        uint32_t id=(round&1U) ? XX_META_ID_OPT_MEMORY_LIMIT : XX_META_ID_OPT_MAX_MEMBER_SIZE;
        xx_meta_init(&limit,id);
        xx_var_set_u64(&limit.var,1U);
        xx_list_init(&limits,sizeof(xx_meta),xx_meta_free_elem);
        if(round<2) {
            if(!xx_list_append(&limits,&limit)) { xx_meta_cleanup(&limit); goto done; }
        } else {
            if(!xx_format_set_extra_parameter(&archive->format,id,&limit.var)) {
                xx_meta_cleanup(&limit); xx_list_cleanup(&limits); goto done;
            }
        }
        xx_meta_cleanup(&limit);
        state=xx_format_create_archive_records_reading(&archive->format,&limits,NULL);
        xx_list_cleanup(&limits);
        CHECK(state && state->total_records==2);
        for(i=0;i<2;++i) {
            const xx_archive_record *record=xx_format_get_current_archive_record(&archive->format,state);
            CHECK(record && !xx_archive_record_find_meta(record,XX_META_ID_PASSWORD));
            CHECK(!xx_format_unpack_current_archive_record(&archive->format,state,NULL));
            CHECK(xx_format_archive_record_move_to_next(&archive->format,state,NULL)==(i==0));
        }
        xx_format_free_archive_records_reading(&archive->format,state);
        state=NULL;
        CHECK(proxy.body_reads==before_body_reads);
        if(round>=2) CHECK(xx_format_remove_extra_parameter(&archive->format,id));
    }
    /* Reuse the same reader after that interrupted metadata attempt. Source
     * values remain independent of caller options and are re-proven. */
    for(round=0;round<6;++round) {
        Abstractformat *dispatch=round==5 ? NULL : &archive->format;
        const char *caller=round==1 || round==4 ? password :
                           round==2 ? "wrong caller password" : NULL;
        bool expected_decode=round!=2;
        CHECK(xx_format_set_password(&archive->format,caller));
        state=xx_format_create_archive_records_reading(&archive->format,NULL,NULL);
        CHECK(state && state->total_records==2);
        CHECK(state->format==&archive->format);
        CHECK(xx_format_is_valid(&archive->format,NULL));
        for(i=0;i<2;++i) {
            const xx_archive_record *record;
            const xx_var *recovered;
            CHECK(state->has_record);
            record=xx_format_get_current_archive_record(dispatch,state);
            CHECK(record!=NULL);
            recovered=xx_archive_record_find_meta(record,XX_META_ID_PASSWORD);
            CHECK(recovered && recovered->type==XX_VAR_TYPE_STRING && recovered->is_allocated);
            CHECK(!strcmp(xx_var_get_str(recovered),password));
            CHECK(xx_var_copy(&retained[i],recovered));
            CHECK(retained[i].val.str.ptr!=recovered->val.str.ptr);
            CHECK(xx_format_unpack_current_archive_record(dispatch,state,NULL)==expected_decode);
            CHECK(xx_format_archive_record_move_to_next(dispatch,state,NULL)==(i==0));
        }
        xx_format_free_archive_records_reading(dispatch,state);
        state=NULL;
        for(i=0;i<2;++i) {
            CHECK(!strcmp(xx_var_get_str(&retained[i]),password));
            xx_mem_zero(retained[i].val.str.ptr,retained[i].val.str.len+1U);
            xx_var_cleanup(&retained[i]);
        }
    }
    puts("Demolition cancellation/retry, caller limits, owned metadata and explicit precedence passed");
    result=0;
done:
    if(state) xx_format_free_archive_records_reading(archive ? &archive->format : NULL,state);
    xx_sfx_zipcentral_free(archive);
    if(source) xx_io_close(source);
    for(i=0;i<2;++i) {
        if(retained[i].is_allocated && retained[i].type==XX_VAR_TYPE_STRING)
            xx_mem_zero(retained[i].val.str.ptr,retained[i].val.str.len+1U);
        xx_var_cleanup(&retained[i]);
    }
    xx_mem_zero(password,sizeof(password));
    return result;
}
