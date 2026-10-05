/* SPDX-License-Identifier: MIT. Independent encrypted-disk RAM lifecycle. */
#include "qcow/xx_qcow.c"
#include "qcow1/xx_qcow1.c"
#include "luks/xx_luks.c"
#include <stdlib.h>
#include <string.h>
typedef struct proxy { xx_io_device io; xx_io_device *source; xx_pd_struct *pd; bool arm; size_t reads; } proxy;
static ssize_t proxy_read(xx_io_device *d,void *p,size_t n) { proxy *x=d->priv; ssize_t got=xx_io_read(x->source,p,n); if(got>0){x->reads++;if(x->arm){x->arm=false;xx_pd_stop(x->pd);}} return got; }
static int proxy_seek(xx_io_device *d,int64_t n,int w) { return xx_io_seek64(((proxy*)d->priv)->source,n,w); }
static int proxy_seek32(xx_io_device *d,long n,int w) { return proxy_seek(d,n,w); }
static int64_t proxy_tell(xx_io_device *d) { return xx_io_tell(((proxy*)d->priv)->source); }
static int64_t proxy_size(xx_io_device *d) { return xx_io_size(((proxy*)d->priv)->source); }
static uint8_t *load(const char *path,size_t *n) { FILE *f=fopen(path,"rb");long z;uint8_t *p;if(!f)return NULL;if(fseek(f,0,SEEK_END)||(z=ftell(f))<0||fseek(f,0,SEEK_SET)){fclose(f);return NULL;}p=malloc((size_t)z+1);if(!p||fread(p,1,(size_t)z,f)!=(size_t)z){free(p);fclose(f);return NULL;}fclose(f);*n=(size_t)z;return p; }
static bool option(xx_list_s *list,xx_meta_id_t id,uint64_t n) { xx_meta m;xx_meta_init(&m,id);xx_var_set_u64(&m.var,n);if(!xx_list_append(list,&m)){xx_meta_cleanup(&m);return false;}return true; }
static bool password(xx_list_s *list,const char *p) { xx_meta m;xx_meta_init(&m,XX_META_ID_OPT_PASSWORD);if(!xx_var_set_str(&m.var,p)||!xx_list_append(list,&m)){xx_meta_cleanup(&m);return false;}return true; }
static bool outer_limit(Abstractformat *f,uint64_t n) { xx_var v;bool ok;xx_var_init(&v);xx_var_set_u64(&v,n);ok=xx_format_set_extra_parameter(f,XX_META_ID_OPT_MEMORY_LIMIT,&v);xx_var_cleanup(&v);return ok; }
#define CHECK(x) do { if(!(x)){fprintf(stderr,"disk crypto line %d: %s\n",__LINE__,#x);goto done;} } while(0)
int main(int argc,char **argv) {
    uint8_t *image=NULL,*expected=NULL,*wrapped=NULL,*plain=NULL;size_t image_n=0,expected_n=0;xx_io_device *source=NULL,*out=NULL;
    Abstractformat *f=NULL;xx_archive_record_state *st=NULL;xx_io_memory_only_scope scope={0};bool scoped=false;proxy x={0};xx_pd_struct pd;
    dc_crypto crypto;uint8_t key[16]={0};int kind=0,result=1;size_t pw_n;bool reject=argc==6&&!strcmp(argv[5],"reject");
    CHECK(argc==5||reject);kind=atoi(argv[1]);image=load(argv[2],&image_n);expected=load(argv[4],&expected_n);CHECK(image&&expected);
    wrapped=malloc(image_n+17);plain=malloc(expected_n+1);CHECK(wrapped&&plain);memset(wrapped,0xcc,17);memcpy(wrapped+17,image,image_n);
    source=xx_io_mem_open_ro(wrapped,image_n+17);out=xx_io_mem_open(plain,expected_n);CHECK(source&&out);
    x.source=source;x.io.priv=&x;x.io.read=proxy_read;x.io.seek=proxy_seek32;x.io.seek64=proxy_seek;x.io.tell=proxy_tell;x.io.total_size=proxy_size;
    if(kind==1) f=(Abstractformat*)xx_qcow1_create(&x.io,17);else if(kind==2) f=(Abstractformat*)xx_qcow_create(&x.io,17);else f=(Abstractformat*)xx_luks_create(&x.io,17);
    CHECK(f);if(!xx_format_handle_base_info(f,NULL)){CHECK(reject);result=0;goto done;}CHECK(xx_format_set_password(f,argv[3]));st=xx_format_create_archive_records_reading(f,NULL,NULL);if(!st||!st->has_record){CHECK(reject);result=0;goto done;}
    CHECK(xx_io_memory_only_begin(&scope,1048576));scoped=true;CHECK(xx_io_seek64(source,5,SEEK_SET)==0);
    if(reject){CHECK(!xx_format_unpack_current_archive_record(NULL,st,NULL)&&xx_io_tell(source)==5);CHECK(xx_io_memory_only_used()==0);result=0;goto done;}
    CHECK(xx_format_unpack_current_archive_record(NULL,st,NULL)&&xx_io_tell(source)==5);
    /* Full plaintext comparison through the same native mapper and private RAM output. */
    xx_mem_zero(&crypto,sizeof(crypto));pw_n=strlen(argv[3]);if(pw_n>16)pw_n=16;memcpy(key,argv[3],pw_n);
    if(kind==1){CHECK(dc_crypto_init(&crypto,DC_CBC_PLAIN64,key,16));CHECK(xx_qcow1_write_image(f,st->internal_state,out,&crypto,NULL));}
    else if(kind==2){xx_qcow_private *p=st->internal_state;if(p->crypt_method==1)CHECK(dc_crypto_init(&crypto,DC_CBC_PLAIN64,key,16));else CHECK(dc_luks_unlock(source,17+p->crypto_header_offset,p->crypto_header_size,true,(const uint8_t*)argv[3],strlen(argv[3]),&crypto,NULL));CHECK(xx_qcow_write_image(f,p,out,&crypto,NULL));}
    else {xx_luks_private *p=st->internal_state;CHECK(dc_luks_unlock(source,17,image_n,false,(const uint8_t*)argv[3],strlen(argv[3]),&crypto,NULL));CHECK(xx_luks_decode(f,p,&crypto,out,NULL));}
    CHECK(xx_io_tell(out)==(int64_t)expected_n&&!memcmp(plain,expected,expected_n));dc_clear(&crypto,sizeof(crypto));dc_clear(key,sizeof(key));
    /* Operation limits take precedence over outer defaults and fail before reads. */
    CHECK(option(&st->options,XX_META_ID_OPT_MEMORY_LIMIT,1));x.reads=0;CHECK(!xx_format_unpack_current_archive_record(NULL,st,NULL)&&x.reads==0);xx_list_clear(&st->options);
    CHECK(option(&st->options,XX_META_ID_OPT_MAX_MEMBER_SIZE,expected_n?expected_n-1:0));x.reads=0;CHECK(!xx_format_unpack_current_archive_record(NULL,st,NULL)&&x.reads==0);xx_list_clear(&st->options);
    CHECK(outer_limit(f,1));CHECK(option(&st->options,XX_META_ID_OPT_MEMORY_LIMIT,16U*1024U*1024U));CHECK(xx_format_unpack_current_archive_record(NULL,st,NULL));xx_list_clear(&st->options);CHECK(!xx_format_unpack_current_archive_record(NULL,st,NULL));CHECK(outer_limit(f,16U*1024U*1024U));
    if(kind==3 || (kind==2&&((xx_qcow_private*)st->internal_state)->crypt_method==2)){CHECK(password(&st->options,"wrong"));CHECK(!xx_format_unpack_current_archive_record(NULL,st,NULL));xx_list_clear(&st->options);CHECK(xx_format_unpack_current_archive_record(NULL,st,NULL));}
    pd=xx_pd_init();x.pd=&pd;x.arm=true;CHECK(xx_io_seek64(source,5,SEEK_SET)==0);CHECK(!xx_format_unpack_current_archive_record(NULL,st,&pd)&&xx_pd_is_stopped(&pd)&&!x.arm&&xx_io_tell(source)==5);
    CHECK(xx_format_unpack_current_archive_record(NULL,st,NULL));CHECK(xx_io_memory_only_used()==0);CHECK(xx_io_memory_only_end(&scope));scoped=false;puts("Encrypted disk exact RAM plaintext, complete no-path verification, NULL dispatch, limits, password override, cursor and cancellation passed");result=0;
done:if(st)xx_format_free_archive_records_reading(NULL,st);if(f){if(kind==1)xx_qcow1_free((xx_qcow1*)f);else if(kind==2)xx_qcow_free((xx_qcow*)f);else xx_luks_free((xx_luks*)f);}if(out)xx_io_close(out);if(source)xx_io_close(source);if(scoped)(void)xx_io_memory_only_end(&scope);free(image);free(expected);free(wrapped);free(plain);return result;
}
