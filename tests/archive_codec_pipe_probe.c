/* SPDX-License-Identifier: MIT. Bounded archive-codec pipe regression. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifdef XFU_AFC_FAKE_HELPER
#include <fcntl.h>
#include <io.h>
static void put32(uint8_t *p,uint32_t n){p[0]=(uint8_t)n;p[1]=(uint8_t)(n>>8);p[2]=(uint8_t)(n>>16);p[3]=(uint8_t)(n>>24);}
int main(void){uint8_t h[32],data[65536];
 if(_setmode(_fileno(stdin),_O_BINARY)==-1||_setmode(_fileno(stdout),_O_BINARY)==-1||fread(h,1,32,stdin)!=32||memcmp(h,"AFC1",4))return 2;
 memset(h,0,16);put32(h,1);put32(h+12,sizeof(data));if(fwrite(h,1,16,stdout)!=16||fflush(stdout))return 2;
#ifdef XFU_AFC_ECHO_HELPER
 if(fread(h,1,4,stdin)!=4||h[0]||h[1]||h[2]!=1||h[3]||fread(data,1,sizeof(data),stdin)!=sizeof(data))return 2;
 put32(h,3);put32(h+4,sizeof(data));if(fwrite(h,1,8,stdout)!=8||fwrite(data,1,sizeof(data),stdout)!=sizeof(data))return 2;
 memset(h,0,16);put32(h,4);put32(h+8,sizeof(data));if(fwrite(h,1,16,stdout)!=16||fflush(stdout))return 2;return 0;
#else
 /* Parent response prefix + 64 KiB exceeds quota; never drain any byte. */
 Sleep(INFINITE);return 2;
#endif
}
#else
#include <xxfclib/formats/xx_format.h>
#include <xxfclib/io/xx_io.h>
#include <xxfclib/memory/xx_memory.h>
typedef struct ac_blob {uint8_t *p;uint32_t n;uint64_t used,limit;xx_pd_struct *pd;}ac_blob;
static bool ac_error(ac_blob *b,const char *why){xx_pd_set_error(b->pd,1,why);return false;}
#include "xx_archive_codec_pipe.h"
static unsigned checks;
#define REQUIRE(x) do{++checks;if(!(x)){fprintf(stderr,"check %u failed at line %u: %s\n",checks,__LINE__,#x);goto done;}}while(0)
static bool clock_stop(const xx_pd_struct *pd,void *user){(void)pd;return GetTickCount64()-*(uint64_t *)user>=100U;}
int main(int argc,char **argv){af_process p={0};xx_pd_struct pd=xx_pd_init();xx_pd_observer previous={0};xx_io_memory_only_scope scope={0};uint8_t data[65536],decoded[65536],h[32];uint64_t start,elapsed[3]={0};int trial,result=1;bool bound=false,scoped=false;size_t i;
 REQUIRE(argc==3);for(i=0;i<sizeof(data);++i)data[i]=(uint8_t)(i*37U);REQUIRE(xx_io_memory_only_begin(&scope,0));scoped=true;
 for(trial=0;trial<3;++trial){bool success;memset(&p,0,sizeof(p));pd=xx_pd_init();p.start=start=GetTickCount64();p.timeout=trial==0?200U:trial==1?1000U:5000U;p.pd=&pd;p.status=AF_FORMAT;
  if(trial==1){previous=xx_pd_set_observer(&pd,clock_stop,&start);bound=true;}
  REQUIRE(af_start(&p,trial<2?argv[1]:argv[2],64U*1024U*1024U));memset(h,0,sizeof(h));memcpy(h,"AFC1",4);af_put64(h+8,sizeof(data));af_put64(h+16,sizeof(data));af_put64(h+24,64U*1024U*1024U);REQUIRE(af_output(&p,h,32));
  REQUIRE(af_input(&p,h,16));REQUIRE(af_le32(h)==1&&af_le64(h+4)==0&&af_le32(h+12)==sizeof(data));af_put32(h,sizeof(data));REQUIRE(af_output(&p,h,4));success=af_output(&p,data,sizeof(data));elapsed[trial]=GetTickCount64()-start;
  if(trial<2){REQUIRE(!success);REQUIRE(elapsed[trial]<1000U);REQUIRE(p.status==(trial==0?AF_TIMEOUT:AF_CANCELLED));}
  else{REQUIRE(success);REQUIRE(af_input(&p,h,8)&&af_le32(h)==3&&af_le32(h+4)==sizeof(data));REQUIRE(af_input(&p,decoded,sizeof(decoded))&&!memcmp(data,decoded,sizeof(data)));REQUIRE(af_input(&p,h,16)&&af_le32(h)==4&&!af_le32(h+4)&&af_le64(h+8)==sizeof(data));}
  if(bound){xx_pd_set_observer(previous.progress,previous.callback,previous.user_data);bound=false;}af_close(&p);memset(&p,0,sizeof(p));
 }
 REQUIRE(xx_io_memory_only_used()==0);REQUIRE(xx_io_memory_only_end(&scope));scoped=false;printf("{\"checks\":%u,\"timeout_ms\":%llu,\"cancel_ms\":%llu,\"success_ms\":%llu,\"memory_only\":true}\n",checks,(unsigned long long)elapsed[0],(unsigned long long)elapsed[1],(unsigned long long)elapsed[2]);result=0;
done:if(bound)xx_pd_set_observer(previous.progress,previous.callback,previous.user_data);af_close(&p);if(scoped)(void)xx_io_memory_only_end(&scope);return result;
}
#endif
