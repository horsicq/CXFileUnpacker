/* SPDX-License-Identifier: MIT. Windows adaptive pipe wait controls. */
#include "xxfclib/formats/grub_backend/xx_grub_backend.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
typedef struct pipe_output{xx_io_device io;uint64_t count;bool valid;}pipe_output;
static ssize_t receive(xx_io_device *io,const void *data,size_t n){pipe_output *out=io->priv;const uint8_t *p=data;size_t i;for(i=0;i<n;++i)if(p[i]!=0x5a)out->valid=false;out->count+=n;return (ssize_t)n;}
static DWORD WINAPI cancel_later(void *opaque){Sleep(100);xx_pd_stop((xx_pd_struct *)opaque);return 0;}
#define CONTROL(x) do{if(!(x)){fprintf(stderr,"pipe control line %u: %s (status %u, bytes %llu, elapsed %llu)\n",(unsigned)__LINE__,#x,(unsigned)status,(unsigned long long)out.count,(unsigned long long)(GetTickCount64()-began));goto done;}}while(0)
int main(int argc,char **argv){uint8_t body[4096];xx_io_device *source=NULL;xx_io_memory_only_scope scope={0};bool scoped=false,ok=false;xx_grub_backend_options options={0};xx_grub_backend_status status=XX_GRUB_BACKEND_IO;xx_pd_struct pd=xx_pd_init();pipe_output out={0};HANDLE thread=NULL;ULONGLONG began=GetTickCount64(),elapsed;bool read_result;unsigned control;
    if(argc!=3)return 2;control=(unsigned)atoi(argv[2]);memset(body,0x5a,sizeof(body));source=xx_io_mem_open_ro(body,sizeof(body));CONTROL(source);CONTROL(xx_io_seek64(source,11,SEEK_SET)==0);out.io.priv=&out;out.io.write=receive;out.valid=true;
    options.helper_path=argv[1];options.memory_limit=8U*1024U*1024U;options.max_member_size=UINT64_C(149)*1024*1024;options.status=&status;options.pd=&pd;options.timeout_ms=control==0?60000:500;
    CONTROL(xx_io_memory_only_begin(&scope,16U*1024U*1024U));scoped=true;
    if(control==2){options.timeout_ms=5000;thread=CreateThread(NULL,0,cancel_later,&pd,0,NULL);CONTROL(thread);}
    began=GetTickCount64();read_result=xx_grub_backend_read(source,0,-1,control==0?"roundtrip":control==3?"drip":"stall","/fixture",control==0?UINT64_C(149)*1024*1024:64,control==3?&out.io:NULL,&options);elapsed=GetTickCount64()-began;
    if(control==0)CONTROL(read_result&&status==XX_GRUB_BACKEND_OK&&elapsed<60000);
    else if(control==2)CONTROL(!read_result&&status==XX_GRUB_BACKEND_CANCELLED&&elapsed<1500);
    else CONTROL(!read_result&&status==XX_GRUB_BACKEND_TIMEOUT&&elapsed<1500);
    if(control==3)CONTROL(out.valid&&out.count>0&&out.count<64);
    CONTROL(xx_io_tell(source)==11&&xx_io_memory_only_used()==0&&xx_io_memory_only_error(&scope)==XX_IO_MEMORY_ONLY_OK);CONTROL(xx_io_memory_only_end(&scope));scoped=false;ok=true;
    printf("{\"control\":%u,\"passed\":true,\"status\":%u,\"elapsed_ms\":%llu,\"large_member_bytes\":%llu,\"drip_bytes_before_timeout\":%llu,\"ram_guard\":true,\"cursor_restored\":11}\n",control,(unsigned)status,(unsigned long long)elapsed,(unsigned long long)(control==0?UINT64_C(149)*1024*1024:0),(unsigned long long)out.count);
done:if(thread){WaitForSingleObject(thread,2000);CloseHandle(thread);}if(scoped)(void)xx_io_memory_only_end(&scope);if(source)xx_io_close(source);return ok?0:1;
}
