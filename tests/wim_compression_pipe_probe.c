/* SPDX-License-Identifier: MIT. Persistent WIM compressor bounded pipe proof. */
#ifdef XFU_WIM_STALLED_HELPER
#include <windows.h>
#include <stdio.h>
#include <io.h>
#include <fcntl.h>
int main(void){unsigned char h[32],reply[16]={'W','C','R','1',0,0,0,0,0,0,1,0,0,0,0,0};_setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);if(fread(h,1,32,stdin)!=32||fwrite(reply,1,16,stdout)!=16||fflush(stdout))return 2;Sleep(INFINITE);return 2;}
#else
#include "xxfclib/formats/wim/xx_wim.h"
#include "xxfclib/memory/xx_memory.h"
#include "xx_wim_compressor_pipe.inc"
#include <stdio.h>
#include <stdlib.h>
static unsigned checks;
#define R(x) do{++checks;if(!(x)){fprintf(stderr,"check%u line%d: %s\n",checks,__LINE__,#x);goto done;}}while(0)
typedef struct observer_state {uint64_t start;} observer_state;
static bool stop(const xx_pd_struct *pd,void *u){(void)pd;return wep_clock()-((observer_state *)u)->start>=100;}
int main(int argc,char **argv){wep_process p;xx_pd_struct pd=xx_pd_init();xx_pd_observer old={0};observer_state observer;bool bound=false,live=false;uint8_t h[32]={0},*buffer=NULL;uint64_t timeout_ms=0,cancel_ms=0;unsigned pass;wimw_encoder *e=NULL;size_t encoded=0;int result=1;
 if(argc!=2)return 2;R((buffer=(uint8_t *)xx_mem_alloc(262144))!=NULL);xx_mem_zero(buffer,262144);
 for(pass=0;pass<2;++pass){xx_mem_zero(&p,sizeof(p));p.start=wep_clock();p.timeout=200;p.pd=&pd;R(wep_start(&p,argv[1],16*1024*1024));live=true;R(wep_output(&p,h,32));R(wep_input(&p,h,16));R(!xx_rt_memcmp(h,"WCR1",4));p.start=wep_clock();
 if(pass){p.timeout=2000;observer.start=p.start;old=xx_pd_set_observer(&pd,stop,&observer);bound=true;}
 R(!wep_output(&p,buffer,262144));R(p.status==(pass?WEP_CANCELLED:WEP_TIMEOUT));if(pass){cancel_ms=wep_clock()-p.start;R(xx_pd_is_stopped(&pd)&&cancel_ms>=80&&cancel_ms<1000);xx_pd_set_observer(old.progress,old.callback,old.user_data);bound=false;}else{timeout_ms=wep_clock()-p.start;R(timeout_ms>=180&&timeout_ms<1000);}wep_close(&p);live=false;pd=xx_pd_init();}
 for(pass=1;pass<=3;++pass){R((e=wimw_encoder_create(pass,0,32*1024*1024,&pd))!=NULL);R(wimw_encoder_chunk(e,buffer,32768,buffer+32768,&encoded,&pd));R(encoded>0&&encoded<32768);R(wimw_encoder_chunk(e,buffer,32768,buffer+32768,&encoded,&pd));R(encoded>0&&encoded<32768);wimw_encoder_free(e);e=NULL;}
 printf("{\"checks\":%u,\"stalled_timeout_ms\":%llu,\"stalled_cancel_ms\":%llu}\n",checks,(unsigned long long)timeout_ms,(unsigned long long)cancel_ms);result=0;
done:if(bound)xx_pd_set_observer(old.progress,old.callback,old.user_data);if(live)wep_close(&p);wimw_encoder_free(e);xx_mem_free(buffer);return result;}
#endif
