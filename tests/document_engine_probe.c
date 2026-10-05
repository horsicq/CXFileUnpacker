/* SPDX-License-Identifier: MIT. Borrowed IO, cancellation, limits and RAM TEST. */
#include "xxfclib/formats/sevenzip_engine/xx_sevenzip_engine.h"
#include "xxfclib/io/xx_io.h"
#include <stdio.h>
#include <string.h>
static unsigned checks;
#define REQUIRE(x) do { ++checks; if(!(x)) { fprintf(stderr,"check %u line %u failed: %s\n",checks,__LINE__,#x);goto done; } } while(0)
typedef struct proxy { xx_io_device device;xx_io_device *source;size_t reads; } proxy;
static ssize_t read_short(xx_io_device *d,void *p,size_t n) { proxy *s=d->priv;++s->reads;return xx_io_read(s->source,p,n>7?7:n); }
static int seek_proxy(xx_io_device *d,int64_t a,int w) { return xx_io_seek64(((proxy *)d->priv)->source,a,w); }
static int64_t tell_proxy(xx_io_device *d) { return xx_io_tell(((proxy *)d->priv)->source); }
static int64_t size_proxy(xx_io_device *d) { return xx_io_size(((proxy *)d->priv)->source); }
typedef struct seen { bool cancel,data;uint64_t size,last; } seen;
static bool observe(const xx_pd_struct *pd,void *opaque) { seen *s=opaque;const xx_pd_record *r=&pd->records[0];if(r->is_busy && r->current && r->total==s->size) {s->data=true;s->last=r->current;return s->cancel;}return false; }
int main(int argc,char **argv) {
    xx_io_device *source=NULL;Abstractformat *f=NULL;xx_archive_record_state *state=NULL;
    xx_io_memory_only_scope scope={0};bool scoped=false,bound=false;proxy p={0};
    xx_var v;xx_pd_struct pd=xx_pd_init();xx_pd_observer previous={0};unsigned members=0;int result=1;
    xx_var_init(&v);REQUIRE(argc>=3);REQUIRE((source=xx_io_file_open(argv[1],"rb"))!=NULL);
    p.source=source;p.device.read=read_short;p.device.seek64=seek_proxy;p.device.tell=tell_proxy;p.device.total_size=size_proxy;p.device.priv=&p;
    REQUIRE((f=xx_sevenzip_engine_create_helper(&p.device,0,"PDF","xfu_document_helper.exe",XX_FILE_TYPE_PDF,"pdf"))!=NULL);
    if(argc>3 && strcmp(argv[3],"-")) { xx_var_set_str(&v,argv[3]);REQUIRE(xx_format_set_extra_parameter(f,XX_META_ID_OPT_PASSWORD,&v)); }
    REQUIRE(xx_io_seek64(source,11,SEEK_SET)==0);REQUIRE(xx_io_memory_only_begin(&scope,0));scoped=true;
    if(!strcmp(argv[2],"reject")) { bool opened=xx_format_handle_base_info(f,&pd);REQUIRE(!opened || xx_sevenzip_engine_get_status(f)==XX_SEVENZIP_BACKEND_PASSWORD);REQUIRE(xx_io_tell(source)==11);REQUIRE((state=xx_format_create_archive_records_reading(f,NULL,&pd))==NULL);result=0;goto done; }
    REQUIRE(xx_format_handle_base_info(f,&pd));REQUIRE(xx_io_tell(source)==11);
    REQUIRE(f->is_crypted==(argc>3 && !strcmp(argv[3],"xfu-pdf-secret")));
    REQUIRE((state=xx_format_create_archive_records_reading(f,NULL,&pd))!=NULL);
    while(state->has_record) {
        const xx_archive_record *r=xx_format_get_current_archive_record(f,state);seen s={0};size_t before;
        REQUIRE(r && xx_archive_record_get_original_name(r));s.size=xx_archive_record_get_meta_u64(r,XX_META_ID_UNCOMPRESSED_SIZE,0);
        REQUIRE(xx_archive_record_get_meta_bool(r,XX_META_ID_IS_ENCRYPTED,false)==f->is_crypted);
        xx_var_set_u64(&v,1);REQUIRE(xx_format_set_extra_parameter(f,XX_META_ID_OPT_MEMORY_LIMIT,&v));before=p.reads;
        REQUIRE(!xx_format_unpack_current_archive_record(f,state,&pd));REQUIRE(before==p.reads && xx_io_tell(source)==11);
        REQUIRE(xx_format_remove_extra_parameter(f,XX_META_ID_OPT_MEMORY_LIMIT));pd=xx_pd_init();
        previous=xx_pd_set_observer(&pd,observe,&s);bound=true;REQUIRE(xx_format_unpack_current_archive_record(f,state,&pd));
        REQUIRE(!s.size || (s.data && s.last==s.size));REQUIRE(xx_io_tell(source)==11);
        xx_pd_set_observer(previous.progress,previous.callback,previous.user_data);bound=false;
        if(!members && s.size) {s.cancel=true;s.data=false;pd=xx_pd_init();previous=xx_pd_set_observer(&pd,observe,&s);bound=true;
            REQUIRE(!xx_format_unpack_current_archive_record(f,state,&pd));REQUIRE(s.data && xx_sevenzip_engine_get_status(f)==XX_SEVENZIP_BACKEND_CANCELLED);
            REQUIRE(xx_io_tell(source)==11);xx_pd_set_observer(previous.progress,previous.callback,previous.user_data);bound=false;pd=xx_pd_init();}
        ++members;if(!xx_format_archive_record_move_to_next(f,state,&pd))break;
    }
    REQUIRE(members==state->total_records && members>0);REQUIRE(xx_io_memory_only_used()==0);REQUIRE(xx_io_memory_only_end(&scope));scoped=false;
    if(argc>4) {
        xx_format_free_archive_records_reading(f,state);state=NULL;xx_var_set_str(&v,argv[4]);REQUIRE(xx_format_set_extra_parameter(f,XX_META_ID_OPT_UNPACK_PATH,&v));
        REQUIRE((state=xx_format_create_archive_records_reading(f,NULL,&pd))!=NULL);
        while(state->has_record) {REQUIRE(xx_format_unpack_current_archive_record(f,state,&pd));REQUIRE(xx_io_tell(source)==11);if(!xx_format_archive_record_move_to_next(f,state,&pd))break;}
    }
    result=0;
done:
    if(result)fprintf(stderr,"status=%d error=%d: %s\n",(int)xx_sevenzip_engine_get_status(f),pd.last_error,pd.error_string);
    if(bound)xx_pd_set_observer(previous.progress,previous.callback,previous.user_data);
    if(state)xx_format_free_archive_records_reading(f,state);xx_sevenzip_engine_free(f);if(source)xx_io_close(source);if(scoped)(void)xx_io_memory_only_end(&scope);xx_var_cleanup(&v);
    printf("{\"checks\":%u,\"members\":%u}\n",checks,members);return result;
}
