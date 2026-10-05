/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 * Public-API probe: all parser input is borrowed RAM. Test operations also
 * run under the existing no-filesystem-mutation scope. */
#include "xxfclib/formats/volume/xx_volume.h"
#include "xxfclib/memory/xx_memory.h"
#include "xxfclib/rt/xx_rt.h"
#include "xx_volume_additions_detect.inc"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv) {
    FILE *file=NULL; uint8_t *bytes=NULL; long size; xx_io_device *device=NULL; xx_volume reader; xx_pd_struct pd;
    xx_archive_record_state *state=NULL; xx_io_memory_only_scope scope={0}; bool scoped=false,initialized=false,ok=false;
    xx_list_s options; xx_meta path; unsigned records=0; int result=1;
    if(argc<4) return 2;
    xx_list_init(&options,sizeof(xx_meta),xx_meta_cleanup); pd=xx_pd_init();
    file=fopen(argv[3],"rb"); if(!file || fseek(file,0,SEEK_END) || (size=ftell(file))<0 || size>128L*1024L*1024L || fseek(file,0,SEEK_SET)) goto done;
    bytes=(uint8_t *)xx_mem_alloc(size?(size_t)size:1); if(!bytes || fread(bytes,1,(size_t)size,file)!=(size_t)size) goto done; fclose(file); file=NULL;
    device=xx_io_mem_open_ro(bytes,(size_t)size); if(!device) goto done;
    if(!strcmp(argv[1],"t")) { if(!xx_io_memory_only_begin(&scope,UINT64_C(256)*1024*1024)) goto done; scoped=true; }
    xx_volume_init(&reader,device,0,(xx_file_type_t)atoi(argv[2]),"img"); initialized=true;
    if(argc>=8 && !xx_volume_set_geometry(&reader,(uint32_t)atoi(argv[5]),(uint32_t)atoi(argv[6]),(uint32_t)atoi(argv[7]))) goto done;
    if(!strcmp(argv[1],"i")) { ok=xx_format_is_valid(&reader.format,&pd); goto done; }
    if(!strcmp(argv[1],"d")) { ok=xx_volume_addition_candidate(reader.format.file_type,device,bytes,(size_t)size<512?(size_t)size:512,size) && xx_format_is_valid(&reader.format,&pd); goto done; }
    if(!strcmp(argv[1],"x")) {
        xx_meta overwrite;
        if(argc<5) goto done; xx_meta_init(&overwrite,XX_META_ID_OPT_OVERWRITE);
        xx_var_set_bool(&overwrite.var,true);
        if(!xx_list_append(&options,&overwrite)) goto done;
        xx_meta_init(&path,XX_META_ID_OPT_UNPACK_PATH);
        if(!xx_var_set_str(&path.var,argv[4]) || !xx_list_append(&options,&path)) { xx_meta_cleanup(&path); goto done; }
    }
    state=xx_format_create_archive_records_reading(&reader.format,&options,&pd); if(!state) goto done;
    ok=true;
    while(state->has_record) { const xx_archive_record *record=reader.format.get_current_archive_record(&reader.format,state); const char *name; uint64_t unpacked;
        if(!record) { ok=false; break; }
        name=xx_archive_record_get_meta_str(record,XX_META_ID_ORIGINAL_NAME); unpacked=xx_archive_record_get_meta_u64(record,XX_META_ID_UNCOMPRESSED_SIZE,UINT64_MAX);
        if(!name || unpacked==UINT64_MAX) { ok=false; break; }
        printf("%s\t%llu\n",name,(unsigned long long)unpacked);
        if(strcmp(argv[1],"l") && !reader.format.unpack_current_archive_record(&reader.format,state,&pd)) { ok=false; break; }
        ++records; if(!reader.format.archive_record_move_to_next(&reader.format,state,&pd)) break;
    }
    if(pd.last_error || !records) ok=false;
done:
    if(state && initialized) reader.format.free_archive_records_reading(&reader.format,state);
    if(initialized) xx_volume_destroy(&reader);
    if(device) xx_io_close(device); xx_mem_free(bytes); if(file) fclose(file);
    if(scoped) { if(xx_io_memory_only_error(&scope)!=XX_IO_MEMORY_ONLY_OK || !xx_io_memory_only_end(&scope)) ok=false; }
    xx_list_cleanup(&options); if(!ok && pd.last_error) fprintf(stderr,"%s\n",pd.error_string);
    if(ok) result=0; return result;
}
