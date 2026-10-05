/* SPDX-License-Identifier: MIT. Deterministic bounded GFS1 pipe producer. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <io.h>
#include <windows.h>
static uint32_t u32(const uint8_t *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void p32(uint8_t *p,uint32_t v){unsigned i;for(i=0;i<4;++i)p[i]=(uint8_t)(v>>(i*8));}
static void p64(uint8_t *p,uint64_t v){unsigned i;for(i=0;i<8;++i)p[i]=(uint8_t)(v>>(i*8));}
static int input(void *p,size_t n){return fread(p,1,n,stdin)==n;}
static int output(const void *p,size_t n){return fwrite(p,1,n,stdout)==n&&fflush(stdout)==0;}
int main(void){uint8_t h[40],body[4096];char fs[17],path[64];uint32_t fn,pn;uint64_t done=0,total=UINT64_C(149)*1024*1024;
    _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
    if(!input(h,40)||memcmp(h,"GFS1",4)||u32(h+4)!=2)return 2;fn=u32(h+32);pn=u32(h+36);if(!fn||fn>16||pn>=sizeof(path)||!input(fs,fn)||!input(path,pn))return 2;fs[fn]=0;path[pn]=0;
    if(!strcmp(fs,"stall")){Sleep(INFINITE);return 3;}
    if(!strcmp(fs,"drip")){total=64;while(done<total){p32(h,3);p32(h+4,1);body[0]=0x5a;if(!output(h,8)||!output(body,1))return 3;++done;Sleep(10);}}
    else if(!strcmp(fs,"roundtrip")){while(done<total){uint32_t n=sizeof(body);p32(h,1);p64(h+4,0);p32(h+12,n);if(!output(h,16)||!input(h,4)||u32(h)!=n||!input(body,n))return 3;p32(h,3);p32(h+4,n);if(!output(h,8)||!output(body,n))return 3;done+=n;}}
    else return 2;
    p32(h,4);p32(h+4,0);p64(h+8,done);return output(h,16)?0:3;
}
