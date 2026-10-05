/* SPDX-License-Identifier: MIT. WIM compression public API/RAM controls. */
#include "xxfclib/formats/wim/xx_wim.h"
#include "xxfclib/io/xx_io.h"
#include "xxfclib/memory/xx_memory.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define R(x) do{++checks;if(!(x)){fprintf(stderr,"check%u line%d: %s\n",checks,__LINE__,#x);goto done;}}while(0)
static bool extra(Abstractformat *f,unsigned id,uint64_t n){xx_var v;bool ok;xx_var_init(&v);xx_var_set_u64(&v,n);ok=xx_format_set_extra_parameter(f,id,&v);xx_var_cleanup(&v);return ok;}
static bool text(Abstractformat *f,unsigned id,const char *s){xx_var v;bool ok;xx_var_init(&v);xx_var_set_str(&v,s);ok=xx_format_set_extra_parameter(f,id,&v);xx_var_cleanup(&v);return ok;}
typedef struct slow {xx_io_device d,*source;int64_t fail;unsigned closed;} slow;
static ssize_t rd(xx_io_device *d,void *p,size_t n){slow *s=(slow *)d->priv;if(s->fail>=0&&xx_io_tell(s->source)>=s->fail)return -1;return xx_io_read(s->source,p,n>7?7:n);}
static int seek(xx_io_device *d,int64_t n,int origin){return xx_io_seek64(((slow *)d->priv)->source,n,origin);}
static int64_t tell(xx_io_device *d){return xx_io_tell(((slow *)d->priv)->source);}
static int64_t size(xx_io_device *d){return xx_io_total_size(((slow *)d->priv)->source);}
static int close_s(xx_io_device *d){++((slow *)d->priv)->closed;return 0;}
static bool observer(const xx_pd_struct *pd,void *unused){unsigned i;(void)unused;for(i=0;i<XX_PD_LEVELS;++i)if(pd->records[i].is_busy&&pd->records[i].current)return true;return false;}
static bool test(xx_wim *f,unsigned *members){xx_archive_record_state *r=NULL;xx_io_memory_only_scope ram={0};bool ok=false;if(!xx_io_memory_only_begin(&ram,256ULL*1024*1024))return false;if(!xx_wim_check_is_valid(&f->format,NULL)||(r=xx_wim_create_archive_records_reading(&f->format,NULL,NULL))==NULL)goto done;
 *members=0;while(r->has_record){if(!xx_wim_get_current_archive_record(&f->format,r)||!xx_wim_unpack_current_archive_record(&f->format,r,NULL))goto done;++*members;if(!xx_wim_archive_record_move_to_next(&f->format,r,NULL))break;}ok=true;
done:if(r)xx_wim_free_archive_records_reading(&f->format,r);return xx_io_memory_only_end(&ram)&&ok;}
static uint32_t random_byte(uint32_t *x){*x^=*x<<13;*x^=*x>>17;*x^=*x<<5;return *x;}
int main(int argc,char **argv){xx_io_device *d=NULL,*source=NULL;xx_wim *f=NULL;xx_archive_write_state *w=NULL;xx_archive_record record,options;uint8_t *data=NULL,*output=NULL;unsigned members=0;size_t n=0,i;unsigned method=0;int result=1;slow s={0};xx_pd_struct pd=xx_pd_init();xx_pd_observer previous={0};bool bound=false;xx_archive_record_init(&record);xx_archive_record_init(&options);
 if(argc<2)return 2;
 if(!strcmp(argv[1],"test")){if(argc!=4)return 2;R((d=xx_io_file_open(argv[2],"rb"))!=NULL);R((f=xx_wim_create(d,0))!=NULL);R(test(f,&members)==(atoi(argv[3])!=0));result=0;goto done;}
 if(!strcmp(argv[1],"create")){uint32_t random=0x12345678;if(argc!=7)return 2;method=(unsigned)atoi(argv[3]);n=(size_t)strtoull(argv[5],NULL,10);if(n>2*1024*1024)return 2;R((data=(uint8_t *)malloc(n?n:1))!=NULL);
 for(i=0;i<n;++i){uint8_t b=(uint8_t)random_byte(&random);data[i]=!strcmp(argv[4],"random")?b:!strcmp(argv[4],"mixed")&&i/32768%2?b:(uint8_t)(i%23);}
 R((d=xx_io_file_open(argv[2],"w+b"))!=NULL);R((f=xx_wim_create(d,0))!=NULL);R(extra(&f->format,XX_META_ID_COMPRESSION_METHOD,method));R(extra(&f->format,XX_META_ID_COMPRESSION_LEVEL,(unsigned)atoi(argv[6])));R((w=xx_wim_create_archive_records_writing(&f->format,NULL,NULL))!=NULL);
 R((source=xx_io_mem_open_ro(data,n))!=NULL);s.source=source;s.fail=-1;s.d.priv=&s;s.d.read=rd;s.d.seek64=seek;s.d.tell=tell;s.d.total_size=size;s.d.close=close_s;R(xx_io_seek64(source,n>3?3:0,SEEK_SET)==0);
 R(xx_archive_record_set_original_name(&record,"nested/payload-\xe2\x98\x83.bin"));R(xx_archive_record_set_meta_u64(&record,XX_META_ID_UNCOMPRESSED_SIZE,n));R(xx_wim_pack_archive_record(&f->format,w,&record,&s.d,NULL));R(xx_io_tell(source)==(int64_t)(n>3?3:0)&&!s.closed);R(xx_wim_finalize_archive_records_writing(&f->format,w,NULL));R(xx_wim_finalize_archive_records_writing(&f->format,w,NULL));xx_wim_free_archive_records_writing(&f->format,w);w=NULL;R(test(f,&members));R(members==3);result=0;goto done;}
 if(strcmp(argv[1],"controls")||argc!=3)return 2;method=(unsigned)atoi(argv[2]);R((output=(uint8_t *)malloc(1048576))!=NULL);memset(output,0x5a,1048576);R((d=xx_io_mem_open(output,1048576))!=NULL);R((f=xx_wim_create(d,0))!=NULL);
 #define BAD(id,value) do{R(extra(&f->format,id,value));R(xx_wim_create_archive_records_writing(&f->format,NULL,&pd)==NULL);R(output[0]==0x5a&&output[207]==0x5a);R(xx_format_remove_extra_parameter(&f->format,id));}while(0)
 BAD(XX_META_ID_COMPRESSION_METHOD,4);BAD(XX_META_ID_COMPRESSION_LEVEL,101);BAD(XX_META_ID_ENCRYPTION_METHOD,1);BAD(XX_META_ID_OPT_MEMORY_LIMIT,0);
 R(text(&f->format,XX_META_ID_OPT_PASSWORD,"secret"));R(xx_wim_create_archive_records_writing(&f->format,NULL,&pd)==NULL);R(output[0]==0x5a);R(xx_format_remove_extra_parameter(&f->format,XX_META_ID_OPT_PASSWORD));
 R(extra(&f->format,XX_META_ID_COMPRESSION_METHOD,method));if(method){R(extra(&f->format,XX_META_ID_OPT_MEMORY_LIMIT,524288));R(xx_wim_create_archive_records_writing(&f->format,NULL,&pd)==NULL);R(output[0]==0x5a);R(xx_format_remove_extra_parameter(&f->format,XX_META_ID_OPT_MEMORY_LIMIT));}
 {uint8_t header[208];xx_io_device *pre=xx_io_mem_open(header,sizeof(header));xx_wim *pf=NULL;xx_archive_write_state *pw=NULL;R(pre!=NULL);R((pf=xx_wim_create(pre,0))!=NULL);R(extra(&pf->format,XX_META_ID_COMPRESSION_METHOD,method));R((pw=xx_wim_create_archive_records_writing(&pf->format,NULL,NULL))!=NULL);R(xx_io_tell(pre)==208);xx_wim_free_archive_records_writing(&pf->format,pw);xx_wim_free(pf);xx_io_close(pre);}
 R(text(&f->format,XX_META_ID_COMPRESSION_METHOD,method==1?"xpress":method==2?"lzx":method==3?"lzms":"stored"));
 R(xx_archive_record_set_meta_u64(&options,XX_META_ID_COMPRESSION_METHOD,method));R((w=xx_wim_create_archive_records_writing(&f->format,&options.list_meta,NULL))!=NULL);R((data=(uint8_t *)malloc(65537))!=NULL);memset(data,0x42,65537);R((source=xx_io_mem_open_ro(data,65537))!=NULL);
 s.source=source;s.fail=-1;s.d.priv=&s;s.d.read=rd;s.d.seek64=seek;s.d.tell=tell;s.d.total_size=size;s.d.close=close_s;R(xx_io_seek64(source,3,SEEK_SET)==0);R(xx_archive_record_set_original_name(&record,"payload"));R(xx_archive_record_set_meta_u64(&record,XX_META_ID_UNCOMPRESSED_SIZE,65537));
 previous=xx_pd_set_observer(&pd,observer,NULL);bound=true;R(!xx_wim_pack_archive_record(&f->format,w,&record,&s.d,&pd));R(pd.is_stop);R(xx_io_tell(source)==3&&!s.closed);R(!xx_wim_finalize_archive_records_writing(&f->format,w,NULL));xx_pd_set_observer(previous.progress,previous.callback,previous.user_data);bound=false;pd=xx_pd_init();xx_wim_free_archive_records_writing(&f->format,w);w=NULL;
 R(extra(&f->format,XX_META_ID_OPT_MAX_MEMBER_SIZE,0));R((w=xx_wim_create_archive_records_writing(&f->format,NULL,NULL))!=NULL);R(!xx_wim_pack_archive_record(&f->format,w,&record,&s.d,NULL));R(xx_io_tell(source)==3&&!s.closed);xx_wim_free_archive_records_writing(&f->format,w);w=NULL;R(xx_format_remove_extra_parameter(&f->format,XX_META_ID_OPT_MAX_MEMBER_SIZE));
 R((w=xx_wim_create_archive_records_writing(&f->format,NULL,NULL))!=NULL);s.fail=10;R(!xx_wim_pack_archive_record(&f->format,w,&record,&s.d,NULL));R(xx_io_tell(source)==3&&!s.closed);R(!xx_wim_finalize_archive_records_writing(&f->format,w,NULL));xx_wim_free_archive_records_writing(&f->format,w);w=NULL;s.fail=-1;
 R((w=xx_wim_create_archive_records_writing(&f->format,NULL,NULL))!=NULL);R(!xx_wim_pack_archive_record(&f->format,w,&record,d,NULL));R(!s.closed);result=0;
done:if(bound)xx_pd_set_observer(previous.progress,previous.callback,previous.user_data);if(w)xx_wim_free_archive_records_writing(f?&f->format:NULL,w);xx_wim_free(f);if(source)xx_io_close(source);if(d)xx_io_close(d);xx_archive_record_cleanup(&record);xx_archive_record_cleanup(&options);free(data);free(output);if(!result)printf("{\"checks\":%u,\"members\":%u}\n",checks,members);return result;
}
