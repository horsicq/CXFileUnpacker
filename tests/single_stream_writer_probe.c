/* SPDX-License-Identifier: MIT. Public single-stream writer API controls. */
#include "xxfclib/formats/gz/xx_gz.h"
#include "xxfclib/formats/bz2/xx_bz2.h"
#include "xxfclib/formats/xz/xx_xz.h"
#include "xxfclib/global/xx_global.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
typedef struct memory { xx_io_device device; unsigned char *bytes; size_t size,position,capacity,maxread,maxwrite; unsigned reads,writes,closes; xx_pd_struct *cancel; } memory;
static ssize_t rd(xx_io_device *d,void *p,size_t n) { memory *m=d->priv; if(n>m->maxread)m->maxread=n; m->reads++; if(n>m->size-m->position)n=m->size-m->position; if(n>7)n=7; memcpy(p,m->bytes+m->position,n);m->position+=n;if(m->cancel)xx_pd_stop(m->cancel);return (ssize_t)n; }
static ssize_t wr(xx_io_device *d,const void *p,size_t n) { memory *m=d->priv;if(n>m->maxwrite)m->maxwrite=n;m->writes++;if(n>m->capacity-m->position)return -1;if(n>7)n=7;memcpy(m->bytes+m->position,p,n);m->position+=n;if(m->position>m->size)m->size=m->position;if(m->cancel)xx_pd_stop(m->cancel);return (ssize_t)n; }
static int sk(xx_io_device *d,int64_t off,int whence){memory *m=d->priv;int64_t base=whence==SEEK_SET?0:whence==SEEK_CUR?(int64_t)m->position:whence==SEEK_END?(int64_t)m->size:-1;if(base<0||off<-base||off>(int64_t)m->capacity-base)return -1;m->position=(size_t)(base+off);return 0;}
static int sk32(xx_io_device *d,long off,int w){return sk(d,off,w);}
static int64_t sz(xx_io_device *d){return (int64_t)((memory *)d->priv)->size;}
static int64_t tl(xx_io_device *d){return (int64_t)((memory *)d->priv)->position;}
static int cl(xx_io_device *d){((memory *)d->priv)->closes++;return 0;}
static void init(memory *m,unsigned char *p,size_t n,size_t cap){memset(m,0,sizeof(*m));m->bytes=p;m->size=n;m->capacity=cap;m->device.priv=m;m->device.read=rd;m->device.write=wr;m->device.seek=sk32;m->device.seek64=sk;m->device.tell=tl;m->device.size=m->device.get_total_size=m->device.total_size=sz;m->device.close=cl;}
static Abstractformat *create(const char *name,xx_io_device *d,int64_t base){if(!strcmp(name,"gz"))return &xx_gz_create(d,base)->format;if(!strcmp(name,"bz2"))return &xx_bz2_create(d,base)->format;return &xx_xz_create(d,base)->format;}
static void release(const char *name,Abstractformat *f){if(!strcmp(name,"gz"))xx_gz_free((xx_gz *)f);else if(!strcmp(name,"bz2"))xx_bz2_free((xx_bz2 *)f);else xx_xz_free((xx_xz *)f);}
static unsigned checks;
#define C(x) do{checks++;if(!(x)){fprintf(stderr,"line%u: %s\n",__LINE__,#x);return 1;}}while(0)
static bool opt(xx_list_s *l,uint32_t id,uint64_t n){xx_meta m;xx_meta_init(&m,id);xx_var_set_u64(&m.var,n);return xx_list_append(l,&m);}
int main(int argc,char **argv){
 unsigned char *input,*output;size_t n;FILE *file;memory src,dst;Abstractformat *f;xx_archive_write_state *s;xx_archive_record r;xx_pd_struct pd=xx_pd_init();xx_list_s opts;const char *kind;
 if(argc!=4)return 2;kind=argv[1];file=fopen(argv[2],"rb");if(!file)return 2;fseek(file,0,SEEK_END);n=(size_t)ftell(file);rewind(file);input=malloc(n+32);output=malloc(n*2+1048576);C(input&&output);memset(input,0xa5,n+32);C(fread(input+17,1,n,file)==n);fclose(file);
 init(&src,input+17,n,n);src.position=n>11?11:0;init(&dst,output,17,n*2+1048576);memset(output,0xa5,17);xx_set_file_buffer_size(31);
 f=create(kind,&dst.device,17);C(f&&f->create_archive_records_writing&&f->pack_archive_record&&f->finalize_archive_records_writing&&f->free_archive_records_writing);
 s=xx_format_create_archive_records_writing(f,NULL,&pd);C(s&&dst.writes==0);xx_archive_record_init(&r);C(xx_archive_record_set_original_name(&r,"payload.bin"));
 C(xx_format_pack_archive_record(f,s,&r,&src.device,&pd));C(src.position==(n>11?11:0));C(src.closes==0&&dst.closes==0&&src.maxread<=31&&dst.maxwrite<=31);C(!memcmp(input,"\xa5\xa5\xa5\xa5",4));C(!memcmp(output,"\xa5\xa5\xa5\xa5",4));C(xx_format_finalize_archive_records_writing(f,s,&pd));C(xx_format_finalize_archive_records_writing(f,s,&pd));C(f->format_size==(int64_t)dst.size-17);file=fopen(argv[3],"wb");C(file&&fwrite(output+17,1,dst.size-17,file)==dst.size-17);fclose(file);
 {size_t previous=dst.size;C(!xx_format_pack_archive_record(f,s,&r,&src.device,&pd));C(dst.size==previous);}xx_format_free_archive_records_writing(f,s);release(kind,f);
 /* Empty sessions, folders, second members, unsupported options, low limits and
  * cancellation fail explicitly, without closing either borrowed device. */
 dst.size=17;dst.position=17;dst.writes=0;f=create(kind,&dst.device,17);s=xx_format_create_archive_records_writing(f,NULL,&pd);C(s);C(!xx_format_finalize_archive_records_writing(f,s,&pd));xx_format_free_archive_records_writing(f,s);
 s=xx_format_create_archive_records_writing(f,NULL,&pd);C(s);C(xx_archive_record_set_meta_bool(&r,XX_META_ID_IS_FOLDER,true));C(!xx_format_pack_archive_record(f,s,&r,&src.device,&pd));C(dst.writes==0);xx_format_free_archive_records_writing(f,s);C(xx_archive_record_set_meta_bool(&r,XX_META_ID_IS_FOLDER,false));
 xx_list_init(&opts,sizeof(xx_meta),NULL);C(opt(&opts,XX_META_ID_OPT_MEMORY_LIMIT,1));C(!xx_format_create_archive_records_writing(f,&opts,&pd));C(dst.writes==0);xx_list_cleanup(&opts);
 xx_list_init(&opts,sizeof(xx_meta),NULL);C(opt(&opts,XX_META_ID_OPT_PASSWORD,0));C(!xx_format_create_archive_records_writing(f,&opts,&pd));C(dst.writes==0);xx_list_cleanup(&opts);
 xx_list_init(&opts,sizeof(xx_meta),NULL);C(opt(&opts,XX_META_ID_COMPRESSION_METHOD,999));C(!xx_format_create_archive_records_writing(f,&opts,&pd));C(dst.writes==0);xx_list_cleanup(&opts);
 s=xx_format_create_archive_records_writing(f,NULL,&pd);C(s);{xx_var limit;xx_var_init(&limit);xx_var_set_u64(&limit,1);C(xx_format_set_extra_parameter(f,XX_META_ID_OPT_MEMORY_LIMIT,&limit));xx_var_cleanup(&limit);} {unsigned before=src.reads;C(!xx_format_pack_archive_record(f,s,&r,&src.device,&pd));C(dst.writes==0&&src.reads==before);}xx_format_free_archive_records_writing(f,s);release(kind,f);
 f=create(kind,&dst.device,17);s=xx_format_create_archive_records_writing(f,NULL,&pd);C(s);xx_pd_stop(&pd);C(!xx_format_pack_archive_record(f,s,&r,&src.device,&pd));C(dst.writes==0);xx_format_free_archive_records_writing(f,s);release(kind,f);
 pd=xx_pd_init();f=create(kind,&dst.device,17);s=xx_format_create_archive_records_writing(f,NULL,&pd);C(s);if(n)src.cancel=&pd;else dst.cancel=&pd;C(!xx_format_pack_archive_record(f,s,&r,&src.device,&pd));C(src.position==(n>11?11:0));C(!xx_format_finalize_archive_records_writing(f,s,&pd));src.cancel=NULL;dst.cancel=NULL;xx_format_free_archive_records_writing(f,s);release(kind,f);
 C(src.closes==0&&dst.closes==0);xx_archive_record_cleanup(&r);free(output);free(input);printf("%s %u controls passed\n",kind,checks);return 0;
}
