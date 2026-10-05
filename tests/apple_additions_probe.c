/* SPDX-License-Identifier: MIT. Native fixtures never execute payload code.
 * The probe verifies to NULL and hashes caller-owned RAM output. Its I/O
 * scope rejects every disk mutation, including transient temporary files. */
#include "xxfclib/formats/applelink_pe/xx_applelink_pe.h"
#include "xxfclib/formats/trackstar/xx_trackstar.h"
#include "xxfclib/formats/gutenberg/xx_gutenberg.h"
#include "xxfclib/formats/apple_rdos/xx_apple_rdos.h"
#include "xxfclib/formats/amdos/xx_amdos.h"
#include "xxfclib/formats/ozdos/xx_ozdos.h"
#include "xxfclib/formats/unidos/xx_unidos.h"
#include "xxfclib/formats/cffa/xx_cffa.h"
#include "xxfclib/formats/apple_dos_hybrid/xx_apple_dos_hybrid.h"
#include "xxfclib/formats/dos_master/xx_dos_master.h"
#include "xxfclib/formats/focusdrive/xx_focusdrive.h"
#include "xxfclib/formats/microdrive/xx_microdrive.h"
#include "xxfclib/formats/mac_ts/xx_mac_ts.h"
#include "xxfclib/formats/pascal_profile_manager/xx_pascal_profile_manager.h"
#include "xxfclib/formats/bsd_disklabel/xx_bsd_disklabel.h"
#include "xxfclib/formats/opera_fs/xx_opera_fs.h"
#include "xxfclib/formats/cdi_fs/xx_cdi_fs.h"
#include "xxfclib/formats/lisa_fs/xx_lisa_fs.h"
#include "xxfclib/formats/apple_cassette/xx_apple_cassette.h"
#include "xxfclib/formats/apple_nib/xx_apple_nib.h"
#include "xxfclib/formats/apple_woz/xx_apple_woz.h"
#include "xxfclib/formats/nufx/xx_nufx.h"
#include "xxfclib/formats/apple_dos33/xx_apple_dos33.h"
#include "xxfclib/formats/prodos/xx_prodos.h"
#include "xxfclib/algo/sha/xx_sha.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "xx_apple_additions_detect.inc"
typedef struct factory {const char *name;Abstractformat *(*create)(xx_io_device *);void (*free)(Abstractformat *);bool (*extract)(Abstractformat *,xx_archive_record_state *,xx_io_device *,xx_pd_struct *);bool family;} factory;
#define MAKE(s) static Abstractformat *make_##s(xx_io_device *d){return (Abstractformat *)xx_##s##_create(d,0);}static void free_##s(Abstractformat *f){xx_##s##_free((xx_##s *)f);}
MAKE(applelink_pe) MAKE(trackstar) MAKE(gutenberg) MAKE(apple_rdos) MAKE(amdos) MAKE(ozdos) MAKE(unidos) MAKE(cffa) MAKE(apple_dos_hybrid) MAKE(dos_master) MAKE(focusdrive) MAKE(microdrive) MAKE(mac_ts) MAKE(pascal_profile_manager) MAKE(bsd_disklabel) MAKE(opera_fs) MAKE(cdi_fs) MAKE(lisa_fs) MAKE(apple_cassette) MAKE(apple_nib) MAKE(apple_woz) MAKE(nufx) MAKE(apple_dos33) MAKE(prodos)
#define ENTRY(s) {#s,make_##s,free_##s,xx_##s##_extract_record_to_device,true}
static const factory readers[]={ENTRY(applelink_pe),ENTRY(trackstar),ENTRY(gutenberg),ENTRY(apple_rdos),ENTRY(amdos),ENTRY(ozdos),ENTRY(unidos),ENTRY(cffa),ENTRY(apple_dos_hybrid),ENTRY(dos_master),ENTRY(focusdrive),ENTRY(microdrive),ENTRY(mac_ts),ENTRY(pascal_profile_manager),ENTRY(bsd_disklabel),ENTRY(opera_fs),ENTRY(cdi_fs),ENTRY(lisa_fs),ENTRY(apple_cassette),ENTRY(apple_nib),ENTRY(apple_woz),ENTRY(nufx),{"apple_dos33",make_apple_dos33,free_apple_dos33,xx_apple_dos33_extract_record_to_device,false},{"prodos",make_prodos,free_prodos,xx_prodos_extract_record_to_device,false}};
typedef struct proxy {xx_io_device device;xx_io_device *source;xx_pd_struct *pd;size_t reads;bool armed;} proxy;
static ssize_t read_proxy(xx_io_device *d,void *p,size_t n){proxy *x=d->priv;ssize_t z=xx_io_read(x->source,p,n);if(z>0){++x->reads;if(x->armed){x->armed=false;xx_pd_stop(x->pd);}}return z;}
static int seek_proxy(xx_io_device *d,int64_t at,int origin){return xx_io_seek64(((proxy *)d->priv)->source,at,origin);}
static int64_t tell_proxy(xx_io_device *d){return xx_io_tell(((proxy *)d->priv)->source);}
static int64_t size_proxy(xx_io_device *d){return xx_io_size(((proxy *)d->priv)->source);}
static void quote(const char *s){unsigned char c;putchar('"');while((c=(unsigned char)*s++)){if(c=='"' || c=='\\'){putchar('\\');putchar(c);}else if(c<32U || c>126U)printf("\\u%04x",c);else putchar(c);}putchar('"');}
static bool option(Abstractformat *f,uint32_t id,uint64_t size){xx_var v;bool ok;xx_var_init(&v);xx_var_set_u64(&v,size);ok=xx_format_set_extra_parameter(f,id,&v);xx_var_cleanup(&v);return ok;}
static bool operation_option(xx_list_s *options,uint32_t id,uint64_t size){xx_meta m;bool ok;xx_meta_init(&m,id);xx_var_set_u64(&m.var,size);ok=xx_list_append(options,&m);xx_meta_cleanup(&m);return ok;}
int main(int argc,char **argv){
 xx_io_memory_only_scope scope={0};xx_io_device *input=NULL;Abstractformat *f=NULL;xx_archive_record_state *st=NULL;const factory *r=NULL;size_t i,seen=0;int result=1;bool active=false,candidate=false,ops_live=false;xx_pd_struct pd=xx_pd_init();proxy p={0};xx_list_s ops={0};
 if(argc<3 || argc>7)return 2;for(i=0;i<sizeof(readers)/sizeof(readers[0]);++i)if(!strcmp(argv[2],readers[i].name))r=readers+i;if(!r)return 2;
 if(!xx_io_memory_only_begin(&scope,UINT64_C(128)*1024U*1024U))return 2;active=true;
 input=xx_io_file_open(argv[1],"rb");if(!input)goto done;p.source=input;p.device.priv=&p;p.device.read=read_proxy;p.device.seek64=seek_proxy;p.device.tell=tell_proxy;p.device.total_size=size_proxy;
 f=r->create(&p.device);if(!f)goto done;
 if(argc>=4 && r->family)((xx_apple_family_info *)f)->profile=(uint32_t)strtoul(argv[3],NULL,0);
 if(argc==7 && (!strcmp(argv[6],"operation") || !strcmp(argv[6],"override"))){
  if(!xx_list_init(&ops,sizeof(xx_meta),xx_meta_free_elem))goto done;ops_live=true;
  if(!operation_option(&ops,XX_META_ID_OPT_MEMORY_LIMIT,strtoull(argv[4],NULL,0)) || !operation_option(&ops,XX_META_ID_OPT_MAX_MEMBER_SIZE,strtoull(argv[5],NULL,0)))goto done;
  if(!strcmp(argv[6],"override") && (!option(f,XX_META_ID_OPT_MEMORY_LIMIT,1) || !option(f,XX_META_ID_OPT_MAX_MEMBER_SIZE,1)))goto done;
 }else{
  if(argc>=5 && !option(f,XX_META_ID_OPT_MEMORY_LIMIT,strtoull(argv[4],NULL,0)))goto done;
  if(argc>=6 && !option(f,XX_META_ID_OPT_MAX_MEMBER_SIZE,strtoull(argv[5],NULL,0)))goto done;
 }
 {uint8_t first[512];int64_t size=xx_io_size(input);size_t n=size>512?512:(size_t)size;
  if(size<0 || xx_io_seek64(input,0,SEEK_SET)!=0 || xx_io_read(input,first,n)!=(ssize_t)n || xx_io_seek64(input,3,SEEK_SET)!=0)goto done;
  candidate=xx_apple_addition_candidate(f->file_type,input,first,(int64_t)n,size);if(xx_io_tell(input)!=3){result=3;goto done;}}
 if(argc==7 && !strcmp(argv[6],"cancel")){p.armed=true;p.pd=&pd;}
 if(xx_io_seek64(input,3,SEEK_SET)!=0)goto done;
 st=(f->create_archive_records_reading)(f,ops_live?&ops:NULL,&pd);
 if(ops_live){xx_list_cleanup(&ops);ops_live=false;}
 if(!st || xx_pd_is_stopped(&pd)){if(xx_io_tell(input)!=3)result=3;goto done;}
 printf("{\"candidate\":%s,\"incomplete\":%s,\"members\":[",candidate?"true":"false",r->family && ((xx_apple_family_info *)f)->incomplete?"true":"false");
 while(st->has_record){const xx_archive_record *rec=xx_format_get_current_archive_record(f,st);uint64_t n;uint8_t *out,digest[32];xx_io_device *mem;bool folder;
  if(!rec || seen>32768U)goto done;n=xx_archive_record_get_meta_u64(rec,XX_META_ID_UNCOMPRESSED_SIZE,UINT64_MAX);folder=xx_archive_record_get_meta_bool(rec,XX_META_ID_IS_FOLDER,false);
  if(n>64U*1024U*1024U || !xx_format_unpack_current_archive_record(f,st,&pd))goto done;
  out=malloc(n?(size_t)n:1U);if(!out)goto done;mem=xx_io_mem_open(out,(size_t)n);
  if(!mem || !r->extract(f,st,mem,&pd) || xx_io_tell(mem)!=(int64_t)n || !xx_sha256_memory(out,(size_t)n,digest)){if(mem)xx_io_close(mem);free(out);goto done;}xx_io_close(mem);free(out);
  if(seen++)putchar(',');printf("{\"name\":");quote(xx_archive_record_get_original_name(rec));printf(",\"size\":%llu,\"folder\":%s,\"sha256\":\"",(unsigned long long)n,folder?"true":"false");for(i=0;i<32U;++i)printf("%02x",digest[i]);printf("\"}");
  if(!xx_format_archive_record_move_to_next(f,st,&pd) && st->has_record)goto done;
 }
 if(seen!=(size_t)st->total_records || xx_io_tell(input)!=3)goto done;printf("]}\n");result=ferror(stdout)?1:0;
done:if(st)xx_format_free_archive_records_reading(NULL,st);if(ops_live)xx_list_cleanup(&ops);if(f)r->free(f);if(input)xx_io_close(input);if(active && !xx_io_memory_only_end(&scope))result=3;return result;
}
