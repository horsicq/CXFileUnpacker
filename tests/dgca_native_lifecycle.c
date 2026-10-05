/* SPDX-License-Identifier: MIT. Independent public-reader lifecycle controls. */
#include <xxfclib/formats/legacy_archive_engine/xx_legacy_archive_engine.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <limits.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#include <time.h>
#endif
#ifdef DG_NATIVE_PROTOTYPE
extern Abstractformat *xx_dgca_native_create(xx_io_device *,int64_t);
extern void xx_dgca_native_free(Abstractformat *);
#define make xx_dgca_native_create
#define destroy xx_dgca_native_free
#else
#define make xx_dgca_create
#define destroy xx_legacy_archive_free
#endif
typedef struct borrowed {const unsigned char *bytes;size_t size,short_read;int64_t base,pos;unsigned closed;} borrowed;
static ssize_t read_borrowed(xx_io_device*d,void*out,size_t n) {
    borrowed*b=d->priv;size_t at,take;if(b->pos<b->base)return -1;at=(size_t)(b->pos-b->base);
    if(at>b->size)return -1;take=b->size-at;if(take>n)take=n;if(take>b->short_read)take=b->short_read;
    memcpy(out,b->bytes+at,take);b->pos+=(int64_t)take;return (ssize_t)take;
}
static int seek_borrowed(xx_io_device*d,int64_t off,int w) {
    borrowed*b=d->priv;int64_t origin=w==SEEK_SET?0:w==SEEK_CUR?b->pos:w==SEEK_END?b->base+(int64_t)b->size:-1;
    if(origin<0||off< -origin||off>INT64_MAX-origin||origin+off<0||origin+off>b->base+(int64_t)b->size)return -1;
    b->pos=origin+off;return 0;
}
static int64_t tell_borrowed(xx_io_device*d) {return ((borrowed*)d->priv)->pos;}
static int64_t size_borrowed(xx_io_device*d) {borrowed*b=d->priv;return b->base+(int64_t)b->size;}
static int close_borrowed(xx_io_device*d) {++((borrowed*)d->priv)->closed;return 0;}
static xx_io_device device(borrowed*b) {
    xx_io_device d={0};d.priv=b;d.read=read_borrowed;d.seek64=seek_borrowed;d.tell=tell_borrowed;d.total_size=size_borrowed;d.close=close_borrowed;return d;
}
static unsigned checks;
#define CHECK(x) do {++checks;if(!(x)){fprintf(stderr,"check%u line%u: %s\n",checks,__LINE__,#x);return 1;}}while(0)
static unsigned char *load(const char*path,size_t*size) {
    FILE*f=fopen(path,"rb");long n;unsigned char*b;if(!f)return NULL;
    if(fseek(f,0,SEEK_END)||(n=ftell(f))<=0||fseek(f,0,SEEK_SET)){fclose(f);return NULL;}
    b=malloc((size_t)n);if(!b||fread(b,1,(size_t)n,f)!=(size_t)n){free(b);b=NULL;}fclose(f);*size=(size_t)n;return b;
}
static int exercise(const unsigned char*data,size_t size,size_t short_read,int64_t base) {
    borrowed b={data,size,short_read,base,base+7,0},other={data,size,short_read,base,base+9,0};
    xx_io_device io=device(&b),foreign_io=device(&other);Abstractformat*f=make(&io,base),*foreign=make(&foreign_io,base);
    xx_pd_struct pd=xx_pd_init();xx_archive_record_state*s=NULL,*fresh=NULL,*foreign_s=NULL;const xx_archive_record*r;
    xx_io_memory_only_scope scope={0};xx_meta option;xx_list_s options={0};unsigned count=0;
    CHECK(f&&foreign);CHECK(xx_io_memory_only_begin(&scope,UINT64_C(256)*1024*1024));
    CHECK(xx_format_handle_base_info(f,&pd)&&b.pos==base+7&&!b.closed);
    s=xx_format_create_archive_records_reading(f,NULL,&pd);CHECK(s&&b.pos==base+7);
    do {r=xx_format_get_current_archive_record(f,s);CHECK(r);CHECK(xx_format_unpack_current_archive_record(f,s,&pd)&&b.pos==base+7&&!b.closed);++count;
    }while(xx_format_archive_record_move_to_next(f,s,&pd));
    CHECK(count==xx_format_get_number_of_archive_records(f,&pd)&&count==5);
    xx_format_free_archive_records_reading(f,s);s=xx_format_create_archive_records_reading(f,NULL,&pd);CHECK(s);
    foreign_s=xx_format_create_archive_records_reading(foreign,NULL,&pd);CHECK(foreign_s&&other.pos==base+9);
    CHECK(!xx_format_get_current_archive_record(f,foreign_s));
    xx_pd_stop(&pd);CHECK(!xx_format_unpack_current_archive_record(f,s,&pd));pd=xx_pd_init();
    CHECK(xx_format_set_password(f,"changed-cache-key"));CHECK(!xx_format_get_current_archive_record(f,s));
    fresh=xx_format_create_archive_records_reading(f,NULL,&pd);CHECK(fresh&&!xx_format_get_current_archive_record(f,s));
    CHECK(xx_format_get_current_archive_record(f,fresh));xx_format_free_archive_records_reading(f,fresh);fresh=NULL;
    xx_format_free_archive_records_reading(f,s);s=NULL;
    f->device=&foreign_io;CHECK(xx_format_handle_base_info(f,&pd)&&other.pos==base+9);f->device=&io;
    CHECK(xx_format_handle_base_info(f,&pd)&&b.pos==base+7);
    xx_meta_init(&option,XX_META_ID_OPT_MEMORY_LIMIT);xx_var_set_u64(&option.var,1);options.data=(uint8_t*)&option;
    options.elem_size=sizeof(option);options.count=options.capacity=1;
    CHECK(!xx_format_create_archive_records_reading(f,&options,&pd)&&b.pos==base+7);xx_meta_cleanup(&option);
    xx_meta_init(&option,XX_META_ID_OPT_MAX_MEMBER_SIZE);xx_var_set_u64(&option.var,1);
    CHECK(!xx_format_create_archive_records_reading(f,&options,&pd)&&b.pos==base+7);xx_meta_cleanup(&option);
    xx_format_free_archive_records_reading(foreign,foreign_s);destroy(foreign);destroy(f);
    CHECK(!b.closed&&!other.closed);CHECK(xx_io_memory_only_end(&scope));return 0;
}
static int password_operation(const unsigned char*data,size_t size,const char*password,
                              const wchar_t*wide_password,unsigned kind,unsigned cached,unsigned choice) {
    borrowed b={data,size,17,37,44,0};xx_io_device io=device(&b);Abstractformat*f=make(&io,37);
    xx_pd_struct pd=xx_pd_init();xx_archive_record_state*prime=NULL,*state=NULL;xx_meta option;
    xx_list_s options={0};char narrow_view[1024];wchar_t wide_view[1024];size_t n,i;
    const char*selected=choice==0?password:choice==1?"incorrect":"";
    const wchar_t*wide_selected=choice==0?wide_password:choice==1?L"incorrect":L"";
    const char*fallback=cached?password:"format-fallback-must-not-win";xx_io_memory_only_scope scope={0};
    CHECK(f);CHECK(xx_io_memory_only_begin(&scope,UINT64_C(256)*1024*1024));CHECK(xx_format_set_password(f,fallback));
    if(cached){prime=xx_format_create_archive_records_reading(f,NULL,&pd);CHECK(prime&&xx_format_get_current_archive_record(f,prime));}
    xx_meta_init(&option,XX_META_ID_OPT_PASSWORD);
    if(kind==0)CHECK(xx_var_set_str(&option.var,selected));
    else if(kind==1){n=strlen(selected);memset(narrow_view,0xa5,sizeof(narrow_view));memcpy(narrow_view,selected,n);xx_var_set_str_view(&option.var,narrow_view,n);}
    else if(kind==2)CHECK(xx_var_set_wstr(&option.var,wide_selected));
    else{n=wcslen(wide_selected);for(i=0;i<1024;++i)wide_view[i]=0x7fff;memcpy(wide_view,wide_selected,n*sizeof(wchar_t));xx_var_set_wstr_view(&option.var,wide_view,n);}
    options.data=(uint8_t*)&option;options.elem_size=sizeof(option);options.count=options.capacity=1;
    state=xx_format_create_archive_records_reading(f,&options,&pd);
    CHECK((state!=NULL)==(choice==0));CHECK(b.pos==44&&!b.closed);CHECK(!strcmp(xx_format_get_password(f),fallback));
    if(kind==1)memset(narrow_view,'x',sizeof(narrow_view));
    if(kind==3)for(i=0;i<1024;++i)wide_view[i]=L'x';
    xx_meta_cleanup(&option); /* The state must own the effective credential. */
    if(state){
        const xx_meta*owned=xx_list_at(&state->options,0);
        CHECK(owned&&owned->meta_id==XX_META_ID_OPT_PASSWORD&&owned->var.type==XX_VAR_TYPE_STRING&&owned->var.is_allocated);
        CHECK(!strcmp(xx_var_get_str(&owned->var),password));
        CHECK(xx_format_get_current_archive_record(f,state));CHECK(xx_format_unpack_current_archive_record(f,state,&pd));
        CHECK(b.pos==44&&!b.closed);
        if(prime)CHECK(xx_format_get_current_archive_record(f,prime));
    }else if(prime)CHECK(!xx_format_get_current_archive_record(f,prime));
    xx_format_free_archive_records_reading(f,state);xx_format_free_archive_records_reading(f,prime);destroy(f);
    CHECK(!b.closed);CHECK(xx_io_memory_only_end(&scope));return 0;
}
static int password_bounds(const unsigned char*data,size_t size,const char*password) {
    borrowed b={data,size,17,37,44,0};xx_io_device io=device(&b);Abstractformat*f=make(&io,37);
    xx_pd_struct pd=xx_pd_init();xx_meta option;xx_list_s options={0};xx_archive_record_state*state=NULL;
    char long_narrow[1025],embedded_nul[3]={'a',0,'b'};wchar_t long_wide[342],bad_surrogate[1]={0xd800};unsigned i;
    xx_io_memory_only_scope scope={0};CHECK(f);CHECK(xx_io_memory_only_begin(&scope,UINT64_C(256)*1024*1024));CHECK(xx_format_set_password(f,password));
    CHECK(xx_format_handle_base_info(f,&pd));xx_meta_init(&option,XX_META_ID_OPT_PASSWORD);
    options.data=(uint8_t*)&option;options.elem_size=sizeof(option);options.count=options.capacity=1;
    memset(long_narrow,'a',sizeof(long_narrow));xx_var_set_str_view(&option.var,long_narrow,sizeof(long_narrow));
    CHECK(!xx_format_create_archive_records_reading(f,&options,&pd)&&b.pos==44);xx_meta_cleanup(&option);pd=xx_pd_init();
    for(i=0;i<342;++i)long_wide[i]=0x20ac;xx_meta_init(&option,XX_META_ID_OPT_PASSWORD);xx_var_set_wstr_view(&option.var,long_wide,342);
    CHECK(!xx_format_create_archive_records_reading(f,&options,&pd)&&b.pos==44);xx_meta_cleanup(&option);pd=xx_pd_init();
    xx_meta_init(&option,XX_META_ID_OPT_PASSWORD);xx_var_set_str_view(&option.var,embedded_nul,3);
    CHECK(!xx_format_create_archive_records_reading(f,&options,&pd)&&b.pos==44);xx_meta_cleanup(&option);pd=xx_pd_init();
    xx_meta_init(&option,XX_META_ID_OPT_PASSWORD);xx_var_set_wstr_view(&option.var,bad_surrogate,1);
    CHECK(!xx_format_create_archive_records_reading(f,&options,&pd)&&b.pos==44);xx_meta_cleanup(&option);pd=xx_pd_init();
    state=xx_format_create_archive_records_reading(f,NULL,&pd);CHECK(state&&xx_format_get_current_archive_record(f,state));
    xx_format_free_archive_records_reading(f,state);destroy(f);CHECK(!b.closed);CHECK(xx_io_memory_only_end(&scope));return 0;
}
static int password_exercise(const char*filename,const char*password,const wchar_t*wide_password) {
    unsigned char*data;size_t size;unsigned kind,cached,choice;data=load(filename,&size);CHECK(data);
    for(kind=0;kind<4;++kind)for(cached=0;cached<2;++cached)for(choice=0;choice<3;++choice)
        if(password_operation(data,size,password,wide_password,kind,cached,choice))return 1;
    if(password_bounds(data,size,password))return 1;free(data);return 0;
}
static int extracted_bytes(const char*root,const char*name,unsigned expected) {
    char path[1024];FILE*file;long length;size_t i;int c;bool exact=true;
    static const char greeting[]="Hello exact decompression!\n";
    CHECK(snprintf(path,sizeof(path),"%s/%s",root,name)>0);
    file=fopen(path,"rb");CHECK(file);CHECK(!fseek(file,0,SEEK_END));length=ftell(file);
    CHECK(length==(long)expected);CHECK(!fseek(file,0,SEEK_SET));
    for(i=0;i<expected;++i){c=fgetc(file);if(c!=(name[14]=='H'?(unsigned char)greeting[i%(sizeof(greeting)-1)]:(int)(i&255)))exact=false;}
    CHECK(exact);
    CHECK(fgetc(file)==EOF);CHECK(!fclose(file));return 0;
}
static int extraction_path(const unsigned char*data,size_t size,const char*root,unsigned wide,unsigned format_option) {
    borrowed b={data,size,17,37,44,0};xx_io_device io=device(&b);Abstractformat*f=make(&io,37);
    xx_pd_struct pd=xx_pd_init();xx_archive_record_state*state=NULL,*test=NULL;xx_meta option;
    xx_list_s options={0};char *narrow=NULL;wchar_t *unicode=NULL;size_t n=strlen(root),i;unsigned count=0;
    const xx_var*owned;xx_io_memory_only_scope scope={0};CHECK(f);
    /* TEST is explicitly separate from extraction and runs under the RAM gate. */
    CHECK(xx_io_memory_only_begin(&scope,UINT64_C(256)*1024*1024));
    test=xx_format_create_archive_records_reading(f,NULL,&pd);CHECK(test);
    do{CHECK(xx_format_get_current_archive_record(f,test));CHECK(xx_format_unpack_current_archive_record(f,test,&pd));++count;
    }while(xx_format_archive_record_move_to_next(f,test,&pd));
    CHECK(count==5&&b.pos==44&&!b.closed);xx_format_free_archive_records_reading(f,test);CHECK(xx_io_memory_only_end(&scope));
    xx_meta_init(&option,XX_META_ID_OPT_UNPACK_PATH);
    /* Exactly n units: no terminator is available to a view consumer. */
    if(wide){unicode=malloc(n*sizeof(*unicode));CHECK(unicode);for(i=0;i<n;++i)unicode[i]=(unsigned char)root[i];xx_var_set_wstr_view(&option.var,unicode,n);}
    else{narrow=malloc(n);CHECK(narrow);memcpy(narrow,root,n);xx_var_set_str_view(&option.var,narrow,n);}
    options.data=(uint8_t*)&option;options.elem_size=sizeof(option);options.count=options.capacity=1;
    if(format_option){CHECK(xx_format_set_extra_parameter(f,XX_META_ID_OPT_UNPACK_PATH,&option.var));state=xx_format_create_archive_records_reading(f,NULL,&pd);}
    else state=xx_format_create_archive_records_reading(f,&options,&pd);
    CHECK(state&&b.pos==44);owned=xx_format_resolve_extra_parameter(f,&state->options,XX_META_ID_OPT_UNPACK_PATH);
    CHECK(owned&&owned->is_allocated&&owned->type==(wide?XX_VAR_TYPE_WSTRING:XX_VAR_TYPE_STRING));
    if(wide){CHECK(owned->val.wstr.len==n&&owned->val.wstr.ptr[n]==0);for(i=0;i<n;++i)unicode[i]=L'x';}
    else{CHECK(owned->val.str.len==n&&!strcmp(xx_var_get_str(owned),root));memset(narrow,'x',n);}
    free(narrow);free(unicode);xx_meta_cleanup(&option);
    if(format_option)CHECK(xx_format_remove_extra_parameter(f,XX_META_ID_OPT_UNPACK_PATH));
    count=0;do{CHECK(xx_format_get_current_archive_record(f,state));CHECK(xx_format_unpack_current_archive_record(f,state,&pd));++count;
    }while(xx_format_archive_record_move_to_next(f,state,&pd));
    CHECK(count==5&&b.pos==44&&!b.closed);
    if(extracted_bytes(root,"fixture-input/Empty.BIN",0)||extracted_bytes(root,"fixture-input/Hello.TXT",2700)||extracted_bytes(root,"fixture-input/Sub/Bytes.BIN",2304))return 1;
    xx_format_free_archive_records_reading(f,state);destroy(f);CHECK(!b.closed);return 0;
}
static int path_bounds(const unsigned char*data,size_t size) {
    borrowed b={data,size,17,37,44,0};xx_io_device io=device(&b);Abstractformat*f=make(&io,37);
    xx_pd_struct pd=xx_pd_init();xx_meta option;xx_list_s options={0};xx_archive_record_state*state;
    char*long_narrow=malloc(32769);wchar_t*long_wide=malloc(32769*sizeof(wchar_t));char nul[3]={'a',0,'b'};unsigned i;
    xx_io_memory_only_scope scope={0};CHECK(f&&long_narrow&&long_wide);CHECK(xx_io_memory_only_begin(&scope,UINT64_C(256)*1024*1024));
    xx_meta_init(&option,XX_META_ID_OPT_UNPACK_PATH);options.data=(uint8_t*)&option;options.elem_size=sizeof(option);options.count=options.capacity=1;
    memset(long_narrow,'x',32769);xx_var_set_str_view(&option.var,long_narrow,32769);
    CHECK(!xx_format_create_archive_records_reading(f,&options,&pd)&&b.pos==44);xx_meta_cleanup(&option);pd=xx_pd_init();
    for(i=0;i<32769;++i)long_wide[i]=L'x';xx_meta_init(&option,XX_META_ID_OPT_UNPACK_PATH);xx_var_set_wstr_view(&option.var,long_wide,32769);
    CHECK(!xx_format_create_archive_records_reading(f,&options,&pd)&&b.pos==44);xx_meta_cleanup(&option);pd=xx_pd_init();
    xx_meta_init(&option,XX_META_ID_OPT_UNPACK_PATH);xx_var_set_str_view(&option.var,nul,3);
    CHECK(!xx_format_create_archive_records_reading(f,&options,&pd)&&b.pos==44);xx_meta_cleanup(&option);pd=xx_pd_init();
    state=xx_format_create_archive_records_reading(f,NULL,&pd);CHECK(state&&xx_format_unpack_current_archive_record(f,state,&pd));
    xx_format_free_archive_records_reading(f,state);destroy(f);free(long_narrow);free(long_wide);CHECK(!b.closed);CHECK(xx_io_memory_only_end(&scope));return 0;
}
static int path_exercise(const unsigned char*data,size_t size) {
    char temp[512],root[768],path[1024];unsigned wide,format_option;unsigned long process,tick;
#ifdef _WIN32
    CHECK(GetTempPathA(sizeof(temp),temp)>0);process=GetCurrentProcessId();tick=GetTickCount();
#else
    strcpy(temp,"/tmp/");process=(unsigned long)getpid();tick=(unsigned long)time(NULL);
#endif
    for(wide=0;wide<2;++wide)for(format_option=0;format_option<2;++format_option){
        CHECK(snprintf(root,sizeof(root),"%sdgca-view-%lu-%lu-%u-%u",temp,process,tick,wide,format_option)>0);
        if(extraction_path(data,size,root,wide,format_option))return 1;
        CHECK(snprintf(path,sizeof(path),"%s/fixture-input/Hello.TXT",root)>0);CHECK(xx_io_file_remove_a(path));
        CHECK(snprintf(path,sizeof(path),"%s/fixture-input/Empty.BIN",root)>0);CHECK(xx_io_file_remove_a(path));
        CHECK(snprintf(path,sizeof(path),"%s/fixture-input/Sub/Bytes.BIN",root)>0);CHECK(xx_io_file_remove_a(path));
#ifdef _WIN32
        CHECK(snprintf(path,sizeof(path),"%s/fixture-input/Sub",root)>0);CHECK(RemoveDirectoryA(path));
        CHECK(snprintf(path,sizeof(path),"%s/fixture-input",root)>0);CHECK(RemoveDirectoryA(path));CHECK(RemoveDirectoryA(root));
#else
        CHECK(snprintf(path,sizeof(path),"%s/fixture-input/Sub",root)>0);CHECK(!rmdir(path));
        CHECK(snprintf(path,sizeof(path),"%s/fixture-input",root)>0);CHECK(!rmdir(path));CHECK(!rmdir(root));
#endif
    }
    return path_bounds(data,size);
}
int main(int argc,char**argv) {
    unsigned char*data;size_t size;unsigned i;size_t reads[]={1,17,4096};
    if(argc!=2&&argc!=4)return 2;data=load(argv[1],&size);CHECK(data);
    for(i=0;i<3;++i)if(exercise(data,size,reads[i],37))return 1;
    if(exercise(data,size,17,INT64_MAX-(int64_t)size))return 1;
    if(path_exercise(data,size))return 1;
    free(data);
    if(argc==4){
        if(password_exercise(argv[2],"Secret42",L"Secret42"))return 1;
        if(password_exercise(argv[3],"P\xc3\xa4ssword \xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e",L"P\u00e4ssword \u65e5\u672c\u8a9e"))return 1;
    }
    printf("%u DGCA native lifecycle controls passed\n",checks);return 0;
}
