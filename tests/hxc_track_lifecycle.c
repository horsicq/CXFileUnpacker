/* SPDX-License-Identifier: MIT. Resource-option and iterator lifecycle checks.
 * Input images are data only. Verification never opens an output path.
 */
#include "xxfclib/formats/amiga_ext_adf/xx_amiga_ext_adf.h"
#include "xxfclib/formats/amiga_old_ext_adf/xx_amiga_old_ext_adf.h"
#include "xxfclib/formats/atari_dim/xx_atari_dim.h"
#include "xxfclib/formats/atari_stt/xx_atari_stt.h"
#include "xxfclib/formats/atari_stw/xx_atari_stw.h"
#include "xxfclib/formats/discferret_dfi/xx_discferret_dfi.h"
#include "xxfclib/formats/hxc_afi/xx_hxc_afi.h"
#include "xxfclib/formats/hxc_qd/xx_hxc_qd.h"
#include "xxfclib/formats/hxc_stream/xx_hxc_stream.h"
#include "xxfclib/formats/svd/xx_svd.h"
#include "xxfclib/formats/sdu/xx_sdu.h"
#include "xxfclib/formats/fei/xx_fei.h"
#include "xxfclib/formats/oric_dsk/xx_oric_dsk.h"
#include <stdio.h>
#include <string.h>

typedef struct hx_proxy {xx_io_device device;xx_io_device *source;xx_pd_struct *pd;size_t reads;bool armed,fired;} hx_proxy;
static ssize_t hx_read(xx_io_device *d,void *p,size_t n){hx_proxy *x=(hx_proxy *)d->priv;ssize_t z=xx_io_read(x->source,p,n);if(z>0){++x->reads;if(x->armed){x->armed=false;x->fired=true;xx_pd_stop(x->pd);}}return z;}
static int hx_seek64(xx_io_device *d,int64_t a,int w){return xx_io_seek64(((hx_proxy *)d->priv)->source,a,w);}
static int hx_seek(xx_io_device *d,long a,int w){return hx_seek64(d,a,w);}
static int64_t hx_tell(xx_io_device *d){return xx_io_tell(((hx_proxy *)d->priv)->source);}
static int64_t hx_size(xx_io_device *d){return xx_io_size(((hx_proxy *)d->priv)->source);}
typedef struct hx_factory {const char *name;Abstractformat *(*create)(xx_io_device *);void (*free)(Abstractformat *);} hx_factory;
#define FACTORY(stem) static Abstractformat *make_##stem(xx_io_device *d){return (Abstractformat *)xx_##stem##_create(d,0);}static void free_##stem(Abstractformat *f){xx_##stem##_free((xx_##stem *)f);}
FACTORY(amiga_ext_adf) FACTORY(amiga_old_ext_adf) FACTORY(atari_dim)
FACTORY(atari_stt) FACTORY(atari_stw) FACTORY(discferret_dfi)
FACTORY(hxc_afi) FACTORY(hxc_qd) FACTORY(hxc_stream)
FACTORY(svd) FACTORY(sdu) FACTORY(fei) FACTORY(oric_dsk)
#define ENTRY(stem) {#stem,make_##stem,free_##stem}
static const hx_factory factories[]={ENTRY(amiga_ext_adf),ENTRY(amiga_old_ext_adf),ENTRY(atari_dim),ENTRY(atari_stt),ENTRY(atari_stw),ENTRY(discferret_dfi),ENTRY(hxc_afi),ENTRY(hxc_qd),ENTRY(hxc_stream),ENTRY(svd),ENTRY(sdu),ENTRY(fei),ENTRY(oric_dsk)};
#define CHECK(x) do{if(!(x)){fprintf(stderr,"HxC lifecycle line%d: %s\n",__LINE__,#x);goto done;}}while(0)
int main(int argc,char **argv){
 xx_io_device *source=NULL;Abstractformat *f=NULL;const hx_factory *factory=NULL;
 xx_archive_record_state *st=NULL;xx_pd_struct pd;hx_proxy proxy={0};xx_var retained;
 xx_list_s opts={0};xx_meta limit;size_t i,j;int result=1;bool opts_live=false;uint64_t records=0;
 xx_var_init(&retained);CHECK(argc==3);
 for(i=0;i<sizeof(factories)/sizeof(factories[0]);++i)if(!strcmp(argv[2],factories[i].name))factory=&factories[i];CHECK(factory);
 source=xx_io_file_open(argv[1],"rb");CHECK(source);proxy.source=source;
 proxy.device.priv=&proxy;proxy.device.read=hx_read;proxy.device.seek=hx_seek;proxy.device.seek64=hx_seek64;proxy.device.tell=hx_tell;proxy.device.total_size=hx_size;
 f=factory->create(&proxy.device);CHECK(f);
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
 /* Cancellation during the first actual source read must publish no iterator
  * and must restore the caller's existing device cursor. */
 CHECK(xx_io_seek64(source,3,SEEK_SET)==0);pd=xx_pd_init();proxy.pd=&pd;proxy.armed=true;
 st=xx_format_create_archive_records_reading(f,NULL,&pd);CHECK(proxy.fired&&xx_pd_is_stopped(&pd)&&!st&&xx_io_tell(source)==3);proxy.pd=NULL;
 /* Retry a persistent reader, exercise NULL-format dispatch and retained
  * owned record metadata after iterator movement/destruction. */
 for(j=0;j<2;++j){st=xx_format_create_archive_records_reading(f,NULL,NULL);CHECK(st&&st->format==f&&st->total_records==records);
  for(i=0;i<records;++i){const xx_archive_record *r=xx_format_get_current_archive_record(NULL,st);const xx_var *name;CHECK(r);
   if(i==0){name=xx_archive_record_find_meta(r,XX_META_ID_ORIGINAL_NAME);CHECK(name&&xx_var_copy(&retained,name));}
   CHECK(xx_format_unpack_current_archive_record(NULL,st,NULL));CHECK(xx_format_archive_record_move_to_next(NULL,st,NULL)==(i+1U<records));
  }
  xx_format_free_archive_records_reading(NULL,st);st=NULL;CHECK(xx_var_get_str(&retained)&&xx_var_get_str(&retained)[0]);xx_var_cleanup(&retained);xx_var_init(&retained);
 }
 puts("HxC resource options, cancellation/cursor, NULL dispatch and ownership passed");result=0;
done:
 if(st)xx_format_free_archive_records_reading(f,st);if(opts_live)xx_list_cleanup(&opts);xx_var_cleanup(&retained);
 if(f&&factory)factory->free(f);if(source)xx_io_close(source);return result;
}
