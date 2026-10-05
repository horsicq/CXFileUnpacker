/* SPDX-License-Identifier: MIT. Authentic ZFS NULL-output checksum control. */
#include "xxfclib/formats/grub_backend/xx_grub_backend.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct zfs_seen { bool found; uint64_t size; } zfs_seen;
#define ZFS_CHECK(x) do { if(!(x)) { fprintf(stderr,"ZFS checksum control line %u failed: %s (status %u, found %u, size %llu, cursor %lld, RAM %llu)\n",(unsigned)__LINE__,#x,(unsigned)status,seen.found?1U:0U,(unsigned long long)seen.size,(long long)(source?xx_io_tell(source):-1),(unsigned long long)xx_io_memory_only_used());goto done; } } while(0)
static bool zfs_entry(void *user,const xx_grub_backend_entry *entry) {
    zfs_seen *seen=(zfs_seen *)user;
    if(!strcmp(entry->path,"/fs/@/f_with_data")) { seen->found=!entry->directory;seen->size=entry->size; }
    return true;
}
int main(int argc,char **argv) {
    FILE *file=NULL;long size;uint8_t *bytes=NULL;xx_io_device *source=NULL;
    xx_io_memory_only_scope scope={0};bool scoped=false,read_ok=false,passed=false;
    xx_grub_backend_status status=XX_GRUB_BACKEND_UNAVAILABLE;xx_grub_backend_options options={0};zfs_seen seen={0};int result=1;
    if(argc!=4)return 2;
    file=fopen(argv[1],"rb");if(!file||fseek(file,0,SEEK_END)||(size=ftell(file))<0||size>128L*1024L*1024L||fseek(file,0,SEEK_SET))goto done;
    bytes=(uint8_t *)malloc((size_t)size+17);if(!bytes)goto done;memset(bytes,0xcc,17);
    if(fread(bytes+17,1,(size_t)size,file)!=(size_t)size)goto done;fclose(file);file=NULL;
    source=xx_io_mem_open_ro(bytes,(size_t)size+17);if(!source||xx_io_seek64(source,11,SEEK_SET))goto done;
    options.helper_path=argv[2];options.memory_limit=16U*1024U*1024U;options.max_member_size=1024U*1024U;options.timeout_ms=30000;options.status=&status;
    ZFS_CHECK(xx_io_memory_only_begin(&scope,32U*1024U*1024U));scoped=true;
    ZFS_CHECK(xx_grub_backend_list(source,17,size,"zfs",&options,zfs_entry,&seen));
    ZFS_CHECK(status==XX_GRUB_BACKEND_OK&&seen.found&&seen.size==512000&&xx_io_tell(source)==11);
    read_ok=xx_grub_backend_read(source,17,size,"zfs","/fs/@/f_with_data",seen.size,NULL,&options);
    if(atoi(argv[3])) { ZFS_CHECK(!read_ok&&status==XX_GRUB_BACKEND_FORMAT); }
    else ZFS_CHECK(read_ok&&status==XX_GRUB_BACKEND_OK);
    ZFS_CHECK(xx_io_tell(source)==11&&xx_io_memory_only_used()==0&&xx_io_memory_only_error(&scope)==XX_IO_MEMORY_ONLY_OK);
    ZFS_CHECK(xx_io_memory_only_end(&scope));scoped=false;passed=true;
    printf("{\"passed\":true,\"file\":\"fs/@/f_with_data\",\"size\":512000,\"read_success\":%s,\"status\":%u,\"ram_guard\":true,\"ram_workspace_bytes_after_read\":0,\"base\":17,\"restored_cursor\":11}\n",read_ok?"true":"false",(unsigned)status);
done:
    if(scoped && !xx_io_memory_only_end(&scope))passed=false;
    if(source)xx_io_close(source);free(bytes);if(file)fclose(file);if(passed)result=0;return result;
}
