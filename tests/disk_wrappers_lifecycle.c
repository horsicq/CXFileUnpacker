/* SPDX-License-Identifier: MIT. Resource-option and iterator lifecycle checks.
 * Input images are data only. Verification never opens an output path.
 */
#include "xxfclib/formats/lisa_blu/xx_lisa_blu.h"
#include "xxfclib/formats/blindwrite4/xx_blindwrite4.h"
#include "xxfclib/formats/ciscopy/xx_ciscopy.h"
#include "xxfclib/formats/copytape/xx_copytape.h"
#include "xxfclib/formats/wc_disk_image/xx_wc_disk_image.h"
#include "xxfclib/formats/dri_diskcopy/xx_dri_diskcopy.h"
#include "xxfclib/formats/maxi_disk/xx_maxi_disk.h"
#include "xxfclib/formats/ray_dim/xx_ray_dim.h"
#include "xxfclib/formats/rs_ide/xx_rs_ide.h"
#include "xxfclib/formats/t98_hdd/xx_t98_hdd.h"
#include "xxfclib/formats/pc_86f/xx_pc_86f.h"
#include "xxfclib/formats/fdx68_fdx/xx_fdx68_fdx.h"
#include "xxfclib/formats/heathkit_h17/xx_heathkit_h17.h"
#include "xxfclib/formats/bochs_growing/xx_bochs_growing.h"
#include "xxfclib/formats/hxc_logic_analyzer/xx_hxc_logic_analyzer.h"
#include "xxfclib/formats/micral_n_raw/xx_micral_n_raw.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

typedef struct hx_proxy {xx_io_device device;xx_io_device *source;xx_pd_struct *pd;size_t reads;bool armed,fired;} hx_proxy;
static ssize_t hx_read(xx_io_device *d,void *p,size_t n){hx_proxy *x=(hx_proxy *)d->priv;ssize_t z=xx_io_read(x->source,p,n);if(z>0){++x->reads;if(x->armed){x->armed=false;x->fired=true;xx_pd_stop(x->pd);}}return z;}
static int hx_seek64(xx_io_device *d,int64_t a,int w){return xx_io_seek64(((hx_proxy *)d->priv)->source,a,w);}
static int hx_seek(xx_io_device *d,long a,int w){return hx_seek64(d,a,w);}
static int64_t hx_tell(xx_io_device *d){return xx_io_tell(((hx_proxy *)d->priv)->source);}
static int64_t hx_size(xx_io_device *d){return xx_io_size(((hx_proxy *)d->priv)->source);}
typedef struct hx_factory {const char *name;Abstractformat *(*create)(xx_io_device *);void (*free)(Abstractformat *);} hx_factory;
#define FACTORY(stem) static Abstractformat *make_##stem(xx_io_device *d){return (Abstractformat *)xx_##stem##_create(d,0);}static void free_##stem(Abstractformat *f){xx_##stem##_free((xx_##stem *)f);}
FACTORY(lisa_blu) FACTORY(blindwrite4) FACTORY(ciscopy) FACTORY(copytape) FACTORY(wc_disk_image) FACTORY(dri_diskcopy) FACTORY(maxi_disk) FACTORY(ray_dim) FACTORY(rs_ide) FACTORY(t98_hdd) FACTORY(pc_86f) FACTORY(fdx68_fdx) FACTORY(heathkit_h17) FACTORY(bochs_growing) FACTORY(hxc_logic_analyzer) FACTORY(micral_n_raw)
#define ENTRY(stem) {#stem,make_##stem,free_##stem}
static const hx_factory factories[]={ENTRY(lisa_blu),ENTRY(blindwrite4),ENTRY(ciscopy),ENTRY(copytape),ENTRY(wc_disk_image),ENTRY(dri_diskcopy),ENTRY(maxi_disk),ENTRY(ray_dim),ENTRY(rs_ide),ENTRY(t98_hdd),ENTRY(pc_86f),ENTRY(fdx68_fdx),ENTRY(heathkit_h17),ENTRY(bochs_growing),ENTRY(hxc_logic_analyzer),ENTRY(micral_n_raw)};
#define CHECK(x) do{if(!(x)){fprintf(stderr,"HxC lifecycle line%d: %s\n",__LINE__,#x);goto done;}}while(0)
int main(int argc,char **argv){
 xx_io_device *source=NULL;Abstractformat *f=NULL;const hx_factory *factory=NULL;
 xx_archive_record_state *st=NULL;xx_pd_struct pd;hx_proxy proxy={0};xx_var retained;
 xx_list_s opts={0};xx_meta limit;size_t i,j;int result=1;bool opts_live=false,scope_live=false;uint8_t *input=NULL,*raw=NULL,*sub=NULL;xx_io_device *raw_io=NULL,*sub_io=NULL;xx_io_memory_only_scope scope={0};uint64_t records=0;
 xx_var_init(&retained);CHECK(argc==3);
 for(i=0;i<sizeof(factories)/sizeof(factories[0]);++i)if(!strcmp(argv[2],factories[i].name))factory=&factories[i];CHECK(factory);
 {FILE *disk=fopen(argv[1],"rb");long n;CHECK(disk);CHECK(fseek(disk,0,SEEK_END)==0&&(n=ftell(disk))>0&&fseek(disk,0,SEEK_SET)==0);input=(uint8_t *)malloc((size_t)n);CHECK(input&&fread(input,1,(size_t)n,disk)==(size_t)n);CHECK(fclose(disk)==0);source=xx_io_mem_open_ro(input,(size_t)n);CHECK(source);}proxy.source=source;
 proxy.device.priv=&proxy;proxy.device.read=hx_read;proxy.device.seek=hx_seek;proxy.device.seek64=hx_seek64;proxy.device.tell=hx_tell;proxy.device.total_size=hx_size;
 f=factory->create(&proxy.device);CHECK(f);
 if(!strcmp(factory->name,"blindwrite4")){size_t k;raw=(uint8_t *)malloc(4704);sub=(uint8_t *)malloc(192);CHECK(raw&&sub);for(k=0;k<4704;++k)raw[k]=(uint8_t)(k*29U+11U);for(k=0;k<192;++k)sub[k]=(uint8_t)(k*29U+11U);raw_io=xx_io_mem_open_ro(raw,4704);sub_io=xx_io_mem_open_ro(sub,192);CHECK(raw_io&&sub_io);xx_blindwrite4_set_companions((xx_blindwrite4 *)f,raw_io,sub_io);}
 CHECK(xx_io_memory_only_begin(&scope,1024U*1024U));scope_live=true;
 /* The public dispatcher performs initial base-info validation before it
  * passes operation options to the reader callback. Exercise scoped parse
  * limits on an already validated reader, as applications normally do. */
 CHECK(xx_format_handle_base_info(f,NULL)&&f->base_info_handled);
 /* Limits supplied to record creation must apply before parse/decode work,
  * with operation values taking precedence over format defaults. */
 for(i=0;i<4;++i){uint32_t id=(i&1U)?XX_META_ID_OPT_MEMORY_LIMIT:XX_META_ID_OPT_MAX_MEMBER_SIZE;size_t before=proxy.reads;
  CHECK(xx_list_init(&opts,sizeof(xx_meta),xx_meta_free_elem));opts_live=true;xx_meta_init(&limit,id);xx_var_set_u64(&limit.var,1);
  if(i<2)CHECK(xx_list_append(&opts,&limit));else CHECK(xx_format_set_extra_parameter(f,id,&limit.var));xx_meta_cleanup(&limit);
  st=xx_format_create_archive_records_reading(f,&opts,NULL);CHECK(!st&&proxy.reads==before);
  xx_list_cleanup(&opts);opts_live=false;if(i>=2)CHECK(xx_format_remove_extra_parameter(f,id));
 }
 /* A large operation override must not mutate the persisted lower default. */
 xx_meta_init(&limit,XX_META_ID_OPT_MEMORY_LIMIT);xx_var_set_u64(&limit.var,1);CHECK(xx_format_set_extra_parameter(f,limit.meta_id,&limit.var));
 CHECK(xx_list_init(&opts,sizeof(xx_meta),xx_meta_free_elem));opts_live=true;xx_var_set_u64(&limit.var,256U*1024U*1024U);CHECK(xx_list_append(&opts,&limit));xx_meta_cleanup(&limit);
 st=xx_format_create_archive_records_reading(f,&opts,NULL);CHECK(st&&st->format==f&&st->has_record);records=st->total_records;CHECK(records);
 CHECK(xx_var_get_u64(xx_format_find_extra_parameter(f,XX_META_ID_OPT_MEMORY_LIMIT))==1U);
 xx_format_free_archive_records_reading(NULL,st);st=NULL;xx_list_cleanup(&opts);opts_live=false;CHECK(xx_format_remove_extra_parameter(f,XX_META_ID_OPT_MEMORY_LIMIT));
 /* Micral is an explicit raw geometry profile, so parsing has no bytes to
  * read. Its cancellation control must reach the actual payload read. */
 if(!strcmp(factory->name,"micral_n_raw")) {
  st=xx_format_create_archive_records_reading(f,NULL,NULL);CHECK(st&&st->has_record);
  CHECK(xx_io_seek64(source,3,SEEK_SET)==0);pd=xx_pd_init();proxy.pd=&pd;proxy.armed=true;
  CHECK(!xx_format_unpack_current_archive_record(NULL,st,&pd)&&proxy.fired&&xx_pd_is_stopped(&pd)&&xx_io_tell(source)==3);
  xx_format_free_archive_records_reading(NULL,st);st=NULL;proxy.pd=NULL;
 } else {
  /* Cancellation during first structural source read publishes no iterator. */
  CHECK(xx_io_seek64(source,3,SEEK_SET)==0);pd=xx_pd_init();proxy.pd=&pd;proxy.armed=true;
  st=xx_format_create_archive_records_reading(f,NULL,&pd);CHECK(proxy.fired&&xx_pd_is_stopped(&pd)&&!st&&xx_io_tell(source)==3);proxy.pd=NULL;
 }
 /* Retry a persistent reader, exercise NULL-format dispatch and retained
  * owned record metadata after iterator movement/destruction. */
 for(j=0;j<2;++j){st=xx_format_create_archive_records_reading(f,NULL,NULL);CHECK(st&&st->format==f&&st->total_records==records);
  for(i=0;i<records;++i){const xx_archive_record *r=xx_format_get_current_archive_record(NULL,st);const xx_var *name;CHECK(r);
   if(i==0){name=xx_archive_record_find_meta(r,XX_META_ID_ORIGINAL_NAME);CHECK(name&&xx_var_copy(&retained,name));}
   CHECK(xx_format_unpack_current_archive_record(NULL,st,NULL));CHECK(xx_format_archive_record_move_to_next(NULL,st,NULL)==(i+1U<records));
  }
  xx_format_free_archive_records_reading(NULL,st);st=NULL;CHECK(xx_var_get_str(&retained)&&xx_var_get_str(&retained)[0]);xx_var_cleanup(&retained);xx_var_init(&retained);
 }
 if(!strcmp(factory->name,"hxc_logic_analyzer")){CHECK(!xx_hxc_logic_analyzer_set_signals((xx_hxc_logic_analyzer *)f,16000000U,3,3));CHECK(xx_hxc_logic_analyzer_set_signals((xx_hxc_logic_analyzer *)f,8000000U,3,0));st=xx_format_create_archive_records_reading(f,NULL,NULL);CHECK(st&&xx_format_unpack_current_archive_record(NULL,st,NULL));xx_format_free_archive_records_reading(NULL,st);st=NULL;}
 CHECK(xx_io_memory_only_used()==0);CHECK(xx_io_memory_only_end(&scope));scope_live=false;
 puts("Disk resource options, all-RAM inputs/no-path decoding, cancellation/cursor, NULL dispatch and ownership passed");result=0;
done:
 if(st)xx_format_free_archive_records_reading(f,st);if(opts_live)xx_list_cleanup(&opts);xx_var_cleanup(&retained);
 if(f&&factory)factory->free(f);if(raw_io)xx_io_close(raw_io);if(sub_io)xx_io_close(sub_io);if(source)xx_io_close(source);if(scope_live)(void)xx_io_memory_only_end(&scope);free(input);free(raw);free(sub);return result;
}
