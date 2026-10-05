/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 * Usage: superdat_lifecycle classic-generated.exe modern-generated.exe
 */
#include <xxfclib/formats/superdat/xx_superdat.h>
#include <xxfclib/algo/lzh/xx_lzh.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <stddef.h>
/* Test-only allocator replacement. All xx_mem/xx_rt allocations are measured;
 * realloc always moves, so the transient old+new peak is observed as well.
 * Fixture storage allocated directly by this test's CRT is outside the reader. */
typedef union audit_block {size_t size;long double alignment;void *pointer;uint64_t padding[4];} audit_block;
static size_t audit_live,audit_peak;
static void *audit_alloc(size_t n) {audit_block*h;if(n>SIZE_MAX-sizeof(*h))return NULL;h=malloc(sizeof(*h)+n);if(!h)return NULL;h->size=n;audit_live+=n;if(audit_live>audit_peak)audit_peak=audit_live;return h+1;}
static void audit_free(void*p) {audit_block*h;if(!p)return;h=(audit_block*)p-1;audit_live-=h->size;free(h);}
static void *audit_realloc(void*p,size_t n) {audit_block*h;void*out;size_t old;if(!p)return n?audit_alloc(n):NULL;if(!n){audit_free(p);return NULL;}h=(audit_block*)p-1;old=h->size;out=audit_alloc(n);if(!out)return NULL;memcpy(out,p,n<old?n:old);audit_free(p);return out;}
void *xx_memory_platform_alloc(size_t n) {return n?audit_alloc(n):NULL;}
void *xx_memory_platform_calloc(size_t count,size_t n) {void*p;if(!count||!n||count>SIZE_MAX/n)return NULL;p=audit_alloc(count*n);if(p)memset(p,0,count*n);return p;}
void *xx_memory_platform_realloc(void*p,size_t n) {return audit_realloc(p,n);}
void xx_memory_platform_free(void*p) {audit_free(p);}
size_t xx_memory_platform_usable_size(void*p) {return p?((audit_block*)p-1)->size:0;}
void *xx_rt_malloc(size_t n) {return audit_alloc(n?n:1);}
void *xx_rt_calloc(size_t count,size_t n) {void*p;if(count&&n>SIZE_MAX/count)return NULL;n*=count;p=audit_alloc(n?n:1);if(p)memset(p,0,n?n:1);return p;}
void *xx_rt_realloc(void*p,size_t n) {return audit_realloc(p,n?n:1);}
void xx_rt_free(void*p) {audit_free(p);}
typedef struct blob { unsigned char *bytes;size_t len,chunk;int64_t pos,base;unsigned closed; } blob;
typedef struct sink { unsigned char *bytes;size_t cap,used,chunk,fail_at;xx_pd_struct *cancel; } sink;
static unsigned checks;
#define CHECK(x) do {++checks;if(!(x)){fprintf(stderr,"check %u failed at line %u: %s\n",checks,__LINE__,#x);return 1;}}while(0)
static ssize_t br(xx_io_device*d,void*out,size_t n) {blob*b=d->priv;size_t at,take;if(b->pos<b->base)return -1;at=(size_t)(b->pos-b->base);if(at>b->len)return -1;take=b->len-at;if(take>n)take=n;if(b->chunk&&take>b->chunk)take=b->chunk;if(take)memcpy(out,b->bytes+at,take);b->pos+=(int64_t)take;return (ssize_t)take;}
static int bs(xx_io_device*d,int64_t off,int w) {blob*b=d->priv;int64_t anchor=w==SEEK_SET?0:w==SEEK_CUR?b->pos:w==SEEK_END?b->base+(int64_t)b->len:-1;if(anchor<0||off< -anchor||off>INT64_MAX-anchor||anchor+off<0||anchor+off>b->base+(int64_t)b->len)return -1;b->pos=anchor+off;return 0;}
static int64_t bt(xx_io_device*d) {return ((blob*)d->priv)->pos;}
static int64_t bz(xx_io_device*d) {blob*b=d->priv;return b->base+(int64_t)b->len;}
static int bc(xx_io_device*d) {++((blob*)d->priv)->closed;return 0;}
static xx_io_device device(blob*b) {xx_io_device d={0};d.priv=b;d.read=br;d.seek64=bs;d.tell=bt;d.total_size=bz;d.close=bc;return d;}
static ssize_t sw(xx_io_device*d,const void*in,size_t n) {sink*s=d->priv;size_t take=n;if(s->fail_at&&s->used>=s->fail_at)return -1;if(take>s->chunk)take=s->chunk;if(take>s->cap-s->used)return -1;memcpy(s->bytes+s->used,in,take);s->used+=take;if(s->cancel)xx_pd_stop(s->cancel);return (ssize_t)take;}
static unsigned char *load(const char*p,size_t*n) {FILE*f=fopen(p,"rb");long size;unsigned char*b;if(!f)return NULL;if(fseek(f,0,SEEK_END)||((size=ftell(f))<0)||fseek(f,0,SEEK_SET)){fclose(f);return NULL;}b=malloc((size_t)size+1);if(!b||fread(b,1,(size_t)size,f)!=(size_t)size){free(b);b=NULL;}fclose(f);*n=(size_t)size;return b;}
static xx_archive_record_state *records(xx_superdat*a,xx_pd_struct*pd) {return xx_format_create_archive_records_reading(&a->format,NULL,pd);}
static int exercise(const unsigned char *first,size_t first_n,const unsigned char*second,size_t second_n,size_t short_read) {
 blob a={(unsigned char*)first,first_n,short_read,7,0,0},b={(unsigned char*)second,second_n,short_read,9,0,0},bad={NULL,0,short_read,0,0,0};
 xx_io_device ai=device(&a),bi=device(&b),bad_io=device(&bad);xx_superdat reader;xx_pd_struct pd=xx_pd_init();xx_archive_record_state *old=NULL,*fresh=NULL,*third=NULL;xx_io_memory_only_scope scope={0};xx_meta option;xx_list_s opts={0};uint64_t generation;
 xx_superdat_init(&reader,&ai,0);CHECK(xx_superdat_has_candidate_device(&ai,0)&&a.pos==7);CHECK(xx_format_is_valid(&reader.format,&pd)&&a.pos==7);old=records(&reader,&pd);CHECK(old&&a.pos==7);generation=reader.generation;CHECK(xx_format_get_current_archive_record(&reader.format,old));
 CHECK(xx_io_memory_only_begin(&scope,UINT64_C(256)*1024*1024));CHECK(xx_format_unpack_current_archive_record(&reader.format,old,&pd)&&a.pos==7&&a.closed==0);CHECK(xx_io_memory_only_end(&scope));
 pd=xx_pd_init();xx_pd_stop(&pd);CHECK(!xx_format_unpack_current_archive_record(&reader.format,old,&pd)&&a.pos==7);CHECK(!xx_format_archive_record_move_to_next(&reader.format,old,&pd));pd=xx_pd_init();
 reader.format.device=&bi;CHECK(!xx_format_get_current_archive_record(&reader.format,old));CHECK(!xx_format_unpack_current_archive_record(&reader.format,old,&pd)&&b.pos==9);fresh=records(&reader,&pd);CHECK(fresh&&reader.generation!=generation&&b.pos==9);CHECK(!xx_format_get_current_archive_record(&reader.format,old));
 reader.format.device=&ai;third=records(&reader,&pd);CHECK(third&&a.pos==7);CHECK(!xx_format_get_current_archive_record(&reader.format,old));CHECK(!xx_format_get_current_archive_record(&reader.format,fresh));CHECK(!xx_format_archive_record_move_to_next(&reader.format,old,&pd));
 reader.format.device=&bad_io;CHECK(!records(&reader,&pd));CHECK(!xx_format_get_current_archive_record(&reader.format,third));CHECK(!xx_format_unpack_current_archive_record(&reader.format,third,&pd));reader.format.device=&ai;
 xx_meta_init(&option,XX_META_ID_OPT_MEMORY_LIMIT);xx_var_set_u64(&option.var,1);opts.data=(uint8_t*)&option;opts.count=opts.capacity=1;opts.elem_size=sizeof(option);CHECK(!xx_format_create_archive_records_reading(&reader.format,&opts,&pd));xx_meta_cleanup(&option);
 xx_superdat_destroy(&reader);CHECK(!xx_format_get_current_archive_record(&reader.format,third));CHECK(!xx_format_archive_record_move_to_next(&reader.format,third,&pd));CHECK(!xx_format_unpack_current_archive_record(&reader.format,third,&pd));CHECK(a.closed==0&&b.closed==0);{xx_archive_record_state *renewed=records(&reader,&pd);CHECK(renewed!=NULL);xx_format_free_archive_records_reading(&reader.format,renewed);}
 xx_format_free_archive_records_reading(&reader.format,old);xx_format_free_archive_records_reading(&reader.format,fresh);xx_format_free_archive_records_reading(&reader.format,third);xx_superdat_destroy(&reader);return 0;
}
static int streaming(unsigned char*data,size_t n) {
 blob b={data,n,17,7,0,0};xx_io_device io=device(&b);xx_superdat reader;xx_pd_struct pd=xx_pd_init();xx_archive_record_state*s;const xx_archive_record*r=NULL;uint64_t plain=0,written=0;unsigned char *expected,*actual;size_t memory_written=0;blob packed;xx_io_device pi,out={0};sink target;
 xx_superdat_init(&reader,&io,0);s=records(&reader,&pd);CHECK(s);
 do{r=xx_format_get_current_archive_record(&reader.format,s);CHECK(r);plain=xx_archive_record_get_meta_u64(r,XX_META_ID_UNCOMPRESSED_SIZE,0);if(plain>4096)break;}while(xx_format_archive_record_move_to_next(&reader.format,s,&pd));CHECK(plain>4096&&plain<16*1024*1024);expected=malloc((size_t)plain);actual=malloc((size_t)plain);CHECK(expected&&actual);
 CHECK(xx_lzh1_decode_memory(data+r->data_offset,(size_t)r->compressed_size,expected,(size_t)plain,&memory_written)&&memory_written==plain);packed=(blob){data+r->data_offset,(size_t)r->compressed_size,1,0,0,0};pi=device(&packed);target=(sink){actual,(size_t)plain,0,3,0,NULL};out.priv=&target;out.write=sw;
 CHECK(xx_lzh1_decode_to_device(&pi,packed.len,&out,plain,&written,&pd)&&written==plain&&target.used==plain&&!memcmp(expected,actual,(size_t)plain));CHECK(packed.closed==0);
 packed.pos=0;target.used=0;target.cancel=&pd;pd=xx_pd_init();CHECK(!xx_lzh1_decode_to_device(&pi,packed.len,&out,plain,&written,&pd)&&written==3&&target.used==3&&xx_pd_is_stopped(&pd));
 packed.pos=0;target.used=0;target.cancel=NULL;target.fail_at=3;pd=xx_pd_init();CHECK(!xx_lzh1_decode_to_device(&pi,packed.len,&out,plain,&written,&pd)&&written==3&&target.used==3);
 packed.pos=0;target.used=0;target.fail_at=0;pd=xx_pd_init();xx_pd_stop(&pd);CHECK(!xx_lzh1_decode_to_device(&pi,packed.len,&out,plain,&written,&pd)&&written==0&&target.used==0&&packed.pos==0);pd=xx_pd_init();
 packed.len=0;CHECK(xx_lzh1_decode_to_device(&pi,0,&out,0,&written,&pd)&&written==0);CHECK(!xx_lzh1_decode_to_device(&pi,0,&out,1,&written,&pd));CHECK(!xx_lzh1_decode_to_device(&pi,UINT64_MAX,&out,0,&written,&pd));
 CHECK(!xx_lzh1_decode_memory(data,SIZE_MAX,actual,0,&memory_written)&&memory_written==0);
 xx_meta option;xx_list_s opts={0};xx_meta_init(&option,XX_META_ID_OPT_MAX_MEMBER_SIZE);xx_var_set_u64(&option.var,1);opts.data=(uint8_t*)&option;opts.count=opts.capacity=1;opts.elem_size=sizeof(option);xx_archive_record_state*limited=xx_format_create_archive_records_reading(&reader.format,&opts,&pd);CHECK(limited);CHECK(!xx_format_unpack_current_archive_record(&reader.format,limited,&pd)&&b.pos==7);xx_format_free_archive_records_reading(&reader.format,limited);xx_meta_cleanup(&option);
 xx_format_free_archive_records_reading(&reader.format,s);xx_superdat_destroy(&reader);free(expected);free(actual);return 0;
}
static unsigned get32(const unsigned char*p) {return p[0]|(unsigned)p[1]<<8|(unsigned)p[2]<<16|(unsigned)p[3]<<24;}
static void put32(unsigned char*p,unsigned v) {p[0]=(unsigned char)v;p[1]=(unsigned char)(v>>8);p[2]=(unsigned char)(v>>16);p[3]=(unsigned char)(v>>24);}
/* Repeat the independent fixture's empty member. This reaches several index
 * capacity growths without depending on producer executables or disk output. */
static int budget(const unsigned char *data,size_t n) {
 size_t footer=n-33,table=footer-356,empty=0,i,at,length,sign,new_footer;unsigned char *many;char name[32];const unsigned copies=1000;blob b;xx_io_device io;xx_superdat reader;xx_archive_record_state *s;xx_pd_struct pd=xx_pd_init();xx_meta option;xx_list_s opts={0};
 CHECK(n>512+292+17+356+33&&!memcmp(data+footer,"_SUPERDAT_HEADER\0",17));
 for(i=512;i+292<=table;++i)if(!memcmp(data+i,"__NAILZHUFLIB\0",14)&&!strcmp((const char*)data+i+14,"empty.bin")){empty=i;break;}
 CHECK(empty&&get32(data+empty+274)==0&&get32(data+empty+278)==4);sign=empty+292;CHECK(sign+17==table);
 length=empty+copies*292+17+(copies+1)*178+33;many=malloc(length);CHECK(many);memcpy(many,data,empty);at=empty;
 for(i=0;i<copies;++i){snprintf(name,sizeof(name),"entry_%04u.bin",(unsigned)i);memcpy(many+at,data+empty,292);memset(many+at+14,0,260);memcpy(many+at+14,name,strlen(name));at+=292;}
 memcpy(many+at,data+sign,17);at+=17;memcpy(many+at,data+table,178);at+=178;
 for(i=0;i<copies;++i){snprintf(name,sizeof(name),"entry_%04u.bin",(unsigned)i);memcpy(many+at,data+table+178,178);memset(many+at,0,144);memcpy(many+at,name,strlen(name));at+=178;}
 new_footer=at;memcpy(many+at,data+footer,33);put32(many+at+17,(unsigned)(empty+copies*292+17-512-4));put32(many+at+25,copies+1);CHECK(new_footer+33==length);
 b=(blob){many,length,17,7,0,0};io=device(&b);xx_superdat_init(&reader,&io,0);xx_meta_init(&option,XX_META_ID_OPT_MEMORY_LIMIT);xx_var_set_u64(&option.var,65536);opts.data=(uint8_t*)&option;opts.count=opts.capacity=1;opts.elem_size=sizeof(option);
 {size_t baseline=audit_live;audit_peak=baseline;
 CHECK(!xx_format_create_archive_records_reading(&reader.format,&opts,&pd));
 printf("First generic 64 KiB parse: peak requested allocation=%zu bytes\n",audit_peak-baseline);
 CHECK(audit_peak>baseline&&audit_peak-baseline<=65536&&audit_live==baseline);
 CHECK(b.pos==7&&reader.index==NULL&&strstr(pd.error_string,"memory limit"));}
 pd=xx_pd_init();xx_var_set_u64(&option.var,1024*1024);s=xx_format_create_archive_records_reading(&reader.format,&opts,&pd);CHECK(s&&s->total_records==copies+3&&b.pos==7);xx_format_free_archive_records_reading(&reader.format,s);
 xx_var_set_u64(&option.var,65536);CHECK(!xx_format_create_archive_records_reading(&reader.format,&opts,&pd)&&b.pos==7);xx_meta_cleanup(&option);xx_superdat_destroy(&reader);CHECK(b.closed==0);free(many);return 0;
}
int main(int argc,char**argv) {
 unsigned char *a,*b;size_t an=0,bn=0;size_t chunks[]={1,17,4096};unsigned i;
 if(argc!=3)return 2;a=load(argv[1],&an);b=load(argv[2],&bn);CHECK(a&&b);for(i=0;i<3;++i)if(exercise(a,an,b,bn,chunks[i]))return 1;if(streaming(a,an)||budget(a,an))return 1;
 {blob high={a,an,17,0,INT64_MAX-(int64_t)an,0};xx_io_device d=device(&high);xx_superdat r;xx_pd_struct pd=xx_pd_init();high.pos=high.base+7;unsigned char old_pe[4];memcpy(old_pe,a+60,4);memset(a+60,255,4);xx_superdat_init(&r,&d,high.base);CHECK(xx_superdat_has_candidate_device(&d,high.base)&&high.pos==high.base+7);CHECK(xx_format_is_valid(&r.format,&pd)&&high.pos==high.base+7);xx_superdat_destroy(&r);memcpy(a+60,old_pe,4);}
 free(a);free(b);CHECK(audit_live==0);printf("%u SuperDAT lifecycle/stream controls passed\n",checks);return 0;
}
