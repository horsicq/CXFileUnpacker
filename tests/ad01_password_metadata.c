/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 * Public AD01 metadata ownership and cached extraction lifecycle. Input is
 * an independent synthetic fixture; no sample programs or files are run.
 */
#include "xxfclib/formats/sfx_ad01/xx_sfx_ad01.h"
#include "xxfclib/io/xx_io.h"
#include "xxfclib/memory/xx_memory.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { if(!(condition)) { \
    fprintf(stderr,"AD01 metadata line %d failed: %s\n",__LINE__,#condition); \
    goto done; } } while(0)

int main(int argc,char **argv) {
    FILE *file=NULL;
    unsigned char *bytes=NULL;
    long length;
    unsigned i,stored;
    bool encrypted;
    xx_io_device *device=NULL;
    xx_sfx_ad01 *archive=NULL;
    xx_archive_record_state *state=NULL;
    xx_var retained[6];
    int result=1;
    for(i=0;i<6;++i) xx_var_init(&retained[i]);
    CHECK(argc==6);
    stored=(unsigned)strtoul(argv[2],NULL,10);
    encrypted=strcmp(argv[5],"1")==0;
    CHECK(stored<=6);
    CHECK(!encrypted || stored==1 || stored==3);
    file=fopen(argv[1],"rb");
    CHECK(file && fseek(file,0,SEEK_END)==0);
    length=ftell(file);
    CHECK(length>0 && length<=1048576 && fseek(file,0,SEEK_SET)==0);
    bytes=(unsigned char *)malloc((size_t)length);
    CHECK(bytes && fread(bytes,1,(size_t)length,file)==(size_t)length);
    { int closed=fclose(file); file=NULL; CHECK(closed==0); }
    device=xx_io_mem_open_ro(bytes,(size_t)length);
    CHECK(device && (archive=xx_sfx_ad01_create(device,0))!=NULL);
    state=xx_format_create_archive_records_reading(&archive->format,NULL,NULL);
    CHECK(state && state->total_records==6);
    /* Parsed records must own recovered credentials and decoded bytes,
     * independently of both the source buffer and parser stack locals. */
    memset(bytes,0,(size_t)length);
    for(i=0;i<6;++i) {
        const xx_archive_record *record;
        const xx_var *password;
        const char *expected=i<stored ? argv[4] : argv[3];
        CHECK(state->has_record);
        record=xx_format_get_current_archive_record(&archive->format,state);
        CHECK(record!=NULL);
        CHECK(xx_archive_record_get_meta_bool(record,XX_META_ID_IS_ENCRYPTED,!encrypted)==encrypted);
        CHECK(xx_archive_record_get_meta_u64(record,XX_META_ID_COMPRESSION_METHOD,99)==
              (i<stored ? 0U : 8U));
        password=xx_archive_record_find_meta(record,XX_META_ID_PASSWORD);
        if(encrypted) {
            CHECK(password && password->type==XX_VAR_TYPE_STRING && password->is_allocated);
            CHECK(strcmp(xx_var_get_str(password),expected)==0);
            CHECK(xx_var_copy(&retained[i],password));
            CHECK(retained[i].is_allocated && retained[i].val.str.ptr!=password->val.str.ptr);
        } else CHECK(password==NULL);
        /* Source encryption is descriptive metadata. Cached plaintext can
         * still be verified without a caller password or output path. */
        CHECK(xx_format_unpack_current_archive_record(&archive->format,state,NULL));
        CHECK(xx_format_archive_record_move_to_next(&archive->format,state,NULL)==(i<5));
    }
    xx_format_free_archive_records_reading(&archive->format,state);
    state=NULL;
    /* A new parse of the now-invalid buffer must not expose old credentials. */
    state=xx_format_create_archive_records_reading(&archive->format,NULL,NULL);
    CHECK(state==NULL);
    xx_sfx_ad01_free(archive);
    archive=NULL;
    { int closed=xx_io_close(device); device=NULL; CHECK(closed==0); }
    free(bytes);
    bytes=NULL;
    for(i=0;i<6;++i) {
        if(encrypted) CHECK(strcmp(xx_var_get_str(&retained[i]),i<stored ? argv[4] : argv[3])==0);
        else CHECK(retained[i].type==XX_VAR_TYPE_NONE);
    }
    puts("AD01 owned password metadata, original flags/methods and cached plaintext lifecycle passed");
    result=0;
done:
    if(state) xx_format_free_archive_records_reading(archive ? &archive->format : NULL,state);
    xx_sfx_ad01_free(archive);
    if(device) xx_io_close(device);
    if(file) fclose(file);
    free(bytes);
    for(i=0;i<6;++i) {
        if(retained[i].type==XX_VAR_TYPE_STRING && retained[i].is_allocated)
            xx_mem_zero(retained[i].val.str.ptr,retained[i].val.str.len+1U);
        xx_var_cleanup(&retained[i]);
    }
    return result;
}
