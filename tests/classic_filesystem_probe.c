/* SPDX-License-Identifier: MIT. Borrowed RAM and public iterator TEST probe.
 * Private member reads emit exact bytes to the independent Python oracle. */
#include "volume/xx_volume.c"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
typedef struct classic_source { xx_io_device io;uint8_t *bytes;size_t length,position,shortread;xx_pd_struct *cancel; } classic_source;
static ssize_t classic_read(xx_io_device *io,void *out,size_t n) {
    classic_source *s=(classic_source *)io->priv;if(s->position>s->length)return -1;
    if(n>s->length-s->position)n=s->length-s->position;if(n>s->shortread)n=s->shortread;
    memcpy(out,s->bytes+s->position,n);s->position+=n;if(s->cancel && n){xx_pd_stop(s->cancel);s->cancel=NULL;}return (ssize_t)n;
}
static int classic_seek(xx_io_device *io,int64_t at,int whence) {classic_source *s=(classic_source *)io->priv;if(whence==SEEK_CUR)at+=s->position;else if(whence==SEEK_END)at+=s->length;else if(whence!=SEEK_SET)return -1;if(at<0 || (uint64_t)at>s->length)return -1;s->position=(size_t)at;return 0;}
static int classic_seek32(xx_io_device *io,long at,int whence){return classic_seek(io,at,whence);}
static int64_t classic_tell(xx_io_device *io){return (int64_t)((classic_source *)io->priv)->position;}
static int64_t classic_size(xx_io_device *io){return (int64_t)((classic_source *)io->priv)->length;}
int main(int argc,char **argv) {
    FILE *file=NULL;long size;classic_source source={0};xx_volume reader;xx_archive_record_state *st=NULL;xx_io_memory_only_scope scope={0};
    xx_pd_struct pd=xx_pd_init();xx_list_s options;bool started=false,initialized=false,ok=false;int result=1;unsigned count=0;
    xx_list_init(&options,sizeof(xx_meta),xx_meta_cleanup);if(argc<3)return 2;
    file=fopen(argv[2],"rb");if(!file || fseek(file,0,SEEK_END) || (size=ftell(file))<0 || size>64L*1024L*1024L || fseek(file,0,SEEK_SET))goto done;
    source.bytes=(uint8_t *)malloc((size_t)size+17);if(!source.bytes)goto done;memset(source.bytes,0xcc,17);
    if(fread(source.bytes+17,1,(size_t)size,file)!=(size_t)size)goto done;fclose(file);file=NULL;
    source.length=(size_t)size+17;source.position=11;source.shortread=7;source.io.priv=&source;source.io.read=classic_read;source.io.seek64=classic_seek;source.io.seek=classic_seek32;source.io.tell=classic_tell;source.io.total_size=classic_size;
    if(!xx_io_memory_only_begin(&scope,32U*1024U*1024U))goto done;started=true;
    xx_volume_init(&reader,&source.io,17,(xx_file_type_t)atoi(argv[1]),"img");initialized=true;
    xx_pd_stop(&pd);if(xx_format_create_archive_records_reading(&reader.format,NULL,&pd) || source.position!=11)goto done;pd=xx_pd_init();
    source.cancel=&pd;if(xx_format_create_archive_records_reading(&reader.format,NULL,&pd) || !xx_pd_is_stopped(&pd) || source.position!=11)goto done;pd=xx_pd_init();source.cancel=NULL;
    {xx_meta limit;xx_var outer;xx_meta_init(&limit,XX_META_ID_OPT_MEMORY_LIMIT);xx_var_set_u64(&limit.var,argc>=4?(uint64_t)strtoull(argv[3],NULL,10):32U*1024U*1024U);if(!xx_list_append(&options,&limit))goto done;
        xx_var_init(&outer);xx_var_set_u64(&outer,1);if(!xx_format_set_extra_parameter(&reader.format,XX_META_ID_OPT_MEMORY_LIMIT,&outer))goto done;xx_var_cleanup(&outer);}
    if(argc>=5) {xx_meta limit;xx_meta_init(&limit,XX_META_ID_OPT_MAX_MEMBER_SIZE);xx_var_set_u64(&limit.var,(uint64_t)strtoull(argv[4],NULL,10));if(!xx_list_append(&options,&limit))goto done;}
    st=xx_format_create_archive_records_reading(&reader.format,&options,&pd);if(!st || source.position!=11)goto done;
    xx_list_cleanup(&options);xx_list_init(&options,sizeof(xx_meta),xx_meta_cleanup);
    if(xx_var_get_u64(xx_format_find_extra_parameter(&reader.format,XX_META_ID_OPT_MEMORY_LIMIT))!=1)goto done;
    ok=true;
    while(st->has_record) {const xx_archive_record *r=xx_format_get_current_archive_record(&reader.format,st);pm_stream *stream=(pm_stream *)st->internal_state;pm_member *m=&stream->items[stream->index];uint64_t pos=0;uint8_t b[4096];
        if(m->read_all) {size_t parameter;xx_meta *limit=NULL;uint64_t old,used=xx_io_memory_only_used();
            for(parameter=0;parameter<st->options.count;++parameter){xx_meta *entry=(xx_meta *)xx_list_at(&st->options,parameter);if(entry->meta_id==XX_META_ID_OPT_MEMORY_LIMIT){limit=entry;break;}}
            if(!limit){ok=false;break;}old=xx_var_get_u64(&limit->var);xx_var_set_u64(&limit->var,1);
            if(xx_format_unpack_current_archive_record(NULL,st,&pd) || source.position!=11 || xx_io_memory_only_used()!=used){ok=false;break;}xx_var_set_u64(&limit->var,old);
        }
        if(!r || !xx_format_unpack_current_archive_record(NULL,st,&pd) || source.position!=11){ok=false;break;}
        xx_sha256_context hash;uint8_t digest[32];unsigned hash_i;xx_sha256_init(&hash);
        printf("%s\t%d\t",m->display_name?m->display_name:m->name,m->directory?1:0);
        if(!m->directory && strcmp(m->display_name?m->display_name:m->name,"0000-volume-info.txt") && !strstr(m->name,"volume-info.txt")) {
            while(pos<(uint64_t)m->size) {size_t n=(uint64_t)m->size-pos<sizeof(b)?(size_t)((uint64_t)m->size-pos):sizeof(b),i;
                if(m->read_range){if(!m->read_range(&reader.format,m,pos,b,n,NULL)){ok=false;break;}}
                else if(m->memory)memcpy(b,m->memory+pos,n);else {ok=false;break;}
                xx_sha256_update(&hash,b,n);pos+=n;(void)i;
            }
        }xx_sha256_final(&hash,digest,sizeof(digest));for(hash_i=0;hash_i<32;++hash_i)printf("%02x",digest[hash_i]);puts("");if(!ok)break;++count;
        if(m->size && m->read_range) {source.cancel=&pd;source.position=11;if(xx_format_unpack_current_archive_record(NULL,st,&pd) || !xx_pd_is_stopped(&pd) || source.position!=11){ok=false;break;}pd=xx_pd_init();source.cancel=NULL;}
        if(!xx_format_archive_record_move_to_next(&reader.format,st,&pd))break;
    }
    if(!count || pd.last_error)ok=false;
done:if(st)xx_format_free_archive_records_reading(NULL,st);if(initialized)xx_volume_destroy(&reader);if(started && (!xx_io_memory_only_end(&scope)))ok=false;
    xx_list_cleanup(&options);free(source.bytes);if(file)fclose(file);if(ok)result=0;return result;
}
