/* SPDX-License-Identifier: MIT. Native parent adapter, all-RAM lifecycle. */
#include "xxfclib/formats/grub_backend/xx_grub_backend.h"
#include "xxfclib/formats/volume/xx_volume.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct observed {const char *wanted;uint64_t size,count;bool found;} observed;
typedef struct proxy {xx_io_device device;xx_io_device *source;xx_pd_struct *pd;bool arm;size_t reads;} proxy;
static bool limit_option(xx_list_s *list,uint32_t id,uint64_t n){xx_meta m;xx_meta_init(&m,id);xx_var_set_u64(&m.var,n);if(!xx_list_append(list,&m)){xx_meta_cleanup(&m);return false;}return true;}
static bool limit_outer(Abstractformat *f,uint32_t id,uint64_t n){xx_var v;bool ok;xx_var_init(&v);xx_var_set_u64(&v,n);ok=xx_format_set_extra_parameter(f,id,&v);xx_var_cleanup(&v);return ok;}
static bool entry(void *u,const xx_grub_backend_entry *e){observed *o=u;++o->count;if(!strcmp(o->wanted,e->path)){o->found=!e->directory;o->size=e->size;}return true;}
static ssize_t read_proxy(xx_io_device *d,void *p,size_t n){proxy *x=d->priv;ssize_t got=xx_io_read(x->source,p,n);if(got>0){++x->reads;if(x->arm){x->arm=false;xx_pd_stop(x->pd);}}return got;}
static int seek_proxy(xx_io_device *d,int64_t n,int w){return xx_io_seek64(((proxy *)d->priv)->source,n,w);}
static int seek_small(xx_io_device *d,long n,int w){return seek_proxy(d,n,w);}
static int64_t tell_proxy(xx_io_device *d){return xx_io_tell(((proxy *)d->priv)->source);}
static int64_t size_proxy(xx_io_device *d){return xx_io_size(((proxy *)d->priv)->source);}
static uint8_t *load(const char *path,size_t *n){FILE *f=fopen(path,"rb");long z;uint8_t *p;if(!f)return NULL;if(fseek(f,0,SEEK_END)||((z=ftell(f))<0)||fseek(f,0,SEEK_SET)){fclose(f);return NULL;}p=malloc((size_t)z+1U);if(!p||fread(p,1,(size_t)z,f)!=(size_t)z){free(p);fclose(f);return NULL;}fclose(f);*n=(size_t)z;return p;}
#define CHECK(x) do{if(!(x)){fprintf(stderr,"GRUB backend line%d: %s\n",__LINE__,#x);goto done;}}while(0)
int main(int argc,char **argv){uint8_t *image=NULL,*body=NULL,*wrapped=NULL,*plain=NULL;size_t image_n=0,body_n=0;xx_io_device *source=NULL,*sub=NULL,*output=NULL;xx_io_memory_only_scope scope={0};bool scoped=false;xx_grub_backend_status status;xx_grub_backend_options opts={0};observed o={0};proxy x={0};xx_pd_struct pd;int result=1;
 CHECK(argc==6);image=load(argv[1],&image_n);body=load(argv[5],&body_n);CHECK(image&&body);wrapped=malloc(image_n+17U);plain=malloc(body_n+1U);CHECK(wrapped&&plain);memset(wrapped,0xCC,17);memcpy(wrapped+17,image,image_n);source=xx_io_mem_open_ro(wrapped,image_n+17U);CHECK(source);sub=xx_io_sub_open_ro(source,17,(int64_t)image_n);CHECK(sub);output=xx_io_mem_open(plain,body_n);CHECK(output);
 opts.helper_path=argv[3];opts.memory_limit=8U*1024U*1024U;opts.max_member_size=UINT64_MAX;opts.timeout_ms=10000;opts.status=&status;o.wanted=argv[4];
 CHECK(xx_io_memory_only_begin(&scope,1048576));scoped=true;CHECK(xx_io_seek64(source,5,SEEK_SET)==0);
 CHECK(xx_grub_backend_list(source,17,(int64_t)image_n,argv[2],&opts,entry,&o));CHECK(status==XX_GRUB_BACKEND_OK&&o.found&&o.size==body_n&&xx_io_tell(source)==5);
 CHECK(xx_grub_backend_read(source,17,(int64_t)image_n,argv[2],argv[4],body_n,NULL,&opts));CHECK(xx_io_tell(source)==5);
 CHECK(xx_grub_backend_read(sub,0,-1,argv[2],argv[4],body_n,output,&opts));CHECK(xx_io_tell(output)==(int64_t)body_n&&!memcmp(plain,body,body_n));
 if(body_n){CHECK(!xx_grub_backend_read(sub,0,-1,argv[2],argv[4],body_n-1U,NULL,&opts));CHECK(status==XX_GRUB_BACKEND_FORMAT);}
 opts.memory_limit=1;CHECK(!xx_grub_backend_list(sub,0,-1,argv[2],&opts,entry,&o)&&status==XX_GRUB_BACKEND_LIMIT);opts.memory_limit=8U*1024U*1024U;
 opts.max_member_size=body_n?body_n-1U:0;CHECK(!xx_grub_backend_read(sub,0,-1,argv[2],argv[4],body_n?body_n:1U,NULL,&opts)&&status==XX_GRUB_BACKEND_LIMIT);opts.max_member_size=UINT64_MAX;
 x.source=sub;x.device.priv=&x;x.device.read=read_proxy;x.device.seek=seek_small;x.device.seek64=seek_proxy;x.device.tell=tell_proxy;x.device.total_size=size_proxy;pd=xx_pd_init();x.pd=&pd;x.arm=true;opts.pd=&pd;CHECK(xx_io_seek64(sub,3,SEEK_SET)==0);CHECK(!xx_grub_backend_list(&x.device,0,-1,argv[2],&opts,entry,&o));CHECK(!x.arm&&xx_pd_is_stopped(&pd)&&status==XX_GRUB_BACKEND_CANCELLED&&xx_io_tell(sub)==3);
 opts.pd=NULL;CHECK(xx_grub_backend_read(sub,0,-1,argv[2],argv[4],body_n,NULL,&opts));
 if(!strcmp(argv[2],"xfs")){
  xx_volume volume;xx_archive_record_state *st;xx_list_s parameters;const xx_archive_record *record;bool folder=false,controls=true;size_t before;
  x.pd=NULL;x.arm=false;xx_volume_init(&volume,&x.device,0,XX_FILE_TYPE_XFS,"img");
  CHECK(xx_format_handle_base_info(&volume.format,NULL));CHECK(limit_outer(&volume.format,XX_META_ID_OPT_MEMORY_LIMIT,1));CHECK(limit_outer(&volume.format,XX_META_ID_OPT_MAX_MEMBER_SIZE,1));
  CHECK(xx_list_init(&parameters,sizeof(xx_meta),xx_meta_free_elem));CHECK(limit_option(&parameters,XX_META_ID_OPT_MEMORY_LIMIT,8U*1024U*1024U));CHECK(limit_option(&parameters,XX_META_ID_OPT_MAX_MEMBER_SIZE,4096));
  st=xx_format_create_archive_records_reading(&volume.format,&parameters,NULL);xx_list_cleanup(&parameters);CHECK(st&&st->has_record);
  CHECK(xx_var_get_u64(xx_format_find_extra_parameter(&volume.format,XX_META_ID_OPT_MEMORY_LIMIT))==1);
  CHECK(xx_format_unpack_current_archive_record(NULL,st,NULL));
  xx_list_clear(&st->options);CHECK(limit_option(&st->options,XX_META_ID_OPT_MEMORY_LIMIT,1));CHECK(limit_option(&st->options,XX_META_ID_OPT_MAX_MEMBER_SIZE,4096));before=x.reads;
  CHECK(!xx_format_unpack_current_archive_record(NULL,st,NULL)&&x.reads==before);
  xx_list_clear(&st->options);CHECK(limit_option(&st->options,XX_META_ID_OPT_MEMORY_LIMIT,8U*1024U*1024U));CHECK(limit_option(&st->options,XX_META_ID_OPT_MAX_MEMBER_SIZE,body_n-1));before=x.reads;
  CHECK(!xx_format_unpack_current_archive_record(NULL,st,NULL)&&x.reads==before);
  xx_list_clear(&st->options);CHECK(limit_option(&st->options,XX_META_ID_OPT_MEMORY_LIMIT,8U*1024U*1024U));CHECK(limit_option(&st->options,XX_META_ID_OPT_MAX_MEMBER_SIZE,4096));
  CHECK(xx_format_unpack_current_archive_record(NULL,st,NULL));
  while(xx_format_archive_record_move_to_next(NULL,st,NULL)) {record=xx_format_get_current_archive_record(NULL,st);if(record&&!strcmp(xx_archive_record_get_meta_str(record,XX_META_ID_ORIGINAL_NAME),"empty")){folder=xx_archive_record_get_meta_bool(record,XX_META_ID_IS_FOLDER,false);controls=folder&&xx_format_unpack_current_archive_record(NULL,st,NULL);}}
  xx_format_free_archive_records_reading(NULL,st);xx_volume_destroy(&volume);CHECK(folder&&controls);
 }
 CHECK(xx_io_memory_only_used()==0);CHECK(xx_io_memory_only_end(&scope));scoped=false;puts("GRUB backend RAM/subdevice/cursor, no-path decode, exact size, limits, cancellation, folders and operation override passed");result=0;
done:if(output)xx_io_close(output);if(sub)xx_io_close(sub);if(source)xx_io_close(source);if(scoped)(void)xx_io_memory_only_end(&scope);free(image);free(body);free(wrapped);free(plain);return result;}
