/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 * Positive public callback checks on independent AD01 fixtures. The final
 * two credentials are hex arguments so control bytes need no shell escapes.
 */
#include "core.h"
#include "xxfclib/memory/xx_memory.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { if(!(condition)) { \
    fprintf(stderr,"Embedded callback line %d failed: %s\n",__LINE__,#condition); \
    goto done; } } while(0)

typedef struct callback_state {
    char expected[2][65];
    char retained[6][65];
    size_t count, stored;
    bool encrypted, failed;
} callback_state;

static int hex_digit(char c) {
    if(c>='0' && c<='9') return c-'0';
    if(c>='a' && c<='f') return c-'a'+10;
    if(c>='A' && c<='F') return c-'A'+10;
    return -1;
}

static bool decode_hex(char result[65],const char *hex) {
    size_t i,n=strlen(hex);
    if(n>128 || (n&1U)) return false;
    for(i=0;i<n/2;++i) {
        int a=hex_digit(hex[i*2]),b=hex_digit(hex[i*2+1]);
        if(a<0 || b<0 || !(a || b)) return false;
        result[i]=(char)((a<<4)|b);
    }
    result[n/2]='\0';
    return true;
}

static void observe_entry(void *user,const xfu_entry *entry) {
    callback_state *state=(callback_state *)user;
    size_t i=state->count++;
    const char *expected=i<state->stored ? state->expected[1] : state->expected[0];
    if(!entry || !entry->name || entry->is_directory || i>=6) {
        state->failed=true; return;
    }
    if(!state->encrypted) {
        if(entry->embedded_password) state->failed=true;
        return;
    }
    /* This is the raw borrowed callback field, not escaped Info properties. */
    if(!entry->embedded_password || strcmp(entry->embedded_password,expected) ||
       strlen(entry->embedded_password)>=sizeof(state->retained[i])) {
        state->failed=true; return;
    }
    memcpy(state->retained[i],entry->embedded_password,strlen(entry->embedded_password)+1);
}

int main(int argc,char **argv) {
    callback_state seen={0};
    xfu_request request={0};
    unsigned round;
    size_t i;
    int result=1;
    CHECK(argc==6);
    seen.stored=(size_t)strtoul(argv[2],NULL,10);
    seen.encrypted=strcmp(argv[5],"1")==0;
    CHECK(seen.stored<=6);
    CHECK(decode_hex(seen.expected[0],argv[3]));
    CHECK(decode_hex(seen.expected[1],argv[4]));
    request.command=XFU_COMMAND_LIST;
    request.archive_path=argv[1];
    request.callbacks.user=&seen;
    request.callbacks.entry=observe_entry;
    for(round=0;round<2;++round) {
        seen.count=0; seen.failed=false;
        xx_mem_zero(seen.retained,sizeof(seen.retained));
        /* A caller option must never become or replace a recovered value. */
        request.password=round ? "caller option is not a discovered credential" : NULL;
        CHECK(xfu_run(&request)==0);
        CHECK(seen.count==6 && !seen.failed);
        /* xfu_run has freed reader state by now; these retained values own
         * their storage and still distinguish controls from literal slashes. */
        for(i=0;i<6;++i) {
            if(seen.encrypted)
                CHECK(!strcmp(seen.retained[i],seen.expected[i<seen.stored ? 1 : 0]));
            else CHECK(seen.retained[i][0]=='\0');
        }
    }
    puts("Raw embedded callback groups, caller-option isolation and owned copies passed");
    result=0;
done:
    xx_mem_zero(&seen,sizeof(seen));
    return result;
}
