/* SPDX-License-Identifier: MIT */
#include <xxfclib/formats/ue2_documents/xx_ue2_documents.h>
#include <xxfclib/formats/sqlite_sql/xx_sqlite_sql.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv) {
    xx_io_device *d=NULL;Abstractformat *f=NULL;xx_archive_record_state *st=NULL;
    xx_pd_struct pd=xx_pd_init();xx_io_memory_only_scope scope={0};xx_list_s options;bool memory=false,ok=false;unsigned count=0;int type;
    if(argc<3)return 90;type=atoi(argv[2]);d=xx_io_file_open(argv[1],"rb");if(!d)return 91;
    f=type==650?(Abstractformat *)xx_sqlite_sql_create(d,0):(Abstractformat *)xx_ue2_documents_create(d,0,(xx_file_type_t)type);
    if(!f)goto done;
    if(argc>4) { xx_var v;xx_var_init(&v);xx_var_set_u64(&v,strtoull(argv[4],NULL,10));xx_format_set_extra_parameter(f,XX_META_ID_OPT_MEMORY_LIMIT,&v);xx_var_cleanup(&v); }
    if(xx_io_seek64(d,11,SEEK_SET)!=0 || !xx_io_memory_only_begin(&scope,0))goto done;memory=true;
    if(!xx_format_is_valid(f,&pd) || !xx_format_handle_base_info(f,&pd) || xx_io_tell(d)!=11)goto done;
    st=xx_format_create_archive_records_reading(f,NULL,&pd);if(!st)goto done;
    while(st->has_record) { if(!xx_format_unpack_current_archive_record(f,st,&pd) || xx_io_tell(d)!=11)goto done;++count;if(!xx_format_archive_record_move_to_next(f,st,&pd))break; }
    xx_format_free_archive_records_reading(f,st);st=NULL;
    if(xx_io_memory_only_used()!=0 || !xx_io_memory_only_end(&scope))goto done;memory=false;
    { xx_pd_struct stopped=xx_pd_init();xx_pd_stop(&stopped);if(f->check_is_valid(f,&stopped) || xx_io_tell(d)!=11)goto done; }
    if(argc>3 && argv[3][0]) {
        xx_meta path;xx_list_init(&options,sizeof(xx_meta),xx_meta_free_elem);xx_meta_init(&path,XX_META_ID_OPT_UNPACK_PATH);
        if(!xx_var_set_str(&path.var,argv[3]) || !xx_list_append(&options,&path)) { xx_meta_cleanup(&path);xx_list_cleanup(&options);goto done; }
        st=xx_format_create_archive_records_reading(f,&options,&pd);xx_list_cleanup(&options);if(!st)goto done;
        while(st->has_record) { if(!xx_format_unpack_current_archive_record(f,st,&pd))goto done;if(!xx_format_archive_record_move_to_next(f,st,&pd))break; }
    }
    printf("{\"members\":%u,\"memory_only\":true,\"cursor_restored\":true,\"cancelled\":true}\n",count);ok=true;
done:
    if(st)xx_format_free_archive_records_reading(f,st);if(memory)xx_io_memory_only_end(&scope);
    if(type==650)xx_sqlite_sql_free((xx_sqlite_sql *)f);else xx_ue2_documents_free((xx_ue2_documents *)f);
    if(d)xx_io_close(d);return ok?0:1;
}
