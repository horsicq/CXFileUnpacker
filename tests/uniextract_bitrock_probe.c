/* SPDX-License-Identifier: MIT */
#include "xxfclib/formats/bitrock/xx_bitrock.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv) {
    xx_io_device *io;xx_bitrock *archive;Abstractformat *f;xx_archive_record_state *state=NULL;
    xx_list_s options;xx_pd_struct pd=xx_pd_init();xx_io_memory_only_scope scope={0};
    bool memory,ok=true,candidate;uint64_t count=0;int64_t base=argc>6?strtoll(argv[6],NULL,10):0;
    if(argc<2||argc>7)return 90;memory=argc<3||!strcmp(argv[2],"-");
    io=xx_io_file_open(argv[1],"rb");if(!io)return 91;
    xx_io_seek64(io,3,SEEK_SET);candidate=xx_bitrock_has_candidate_device(io,base);
    if(xx_io_tell(io)!=3){xx_io_close(io);return 92;}printf("candidate=%d\n",candidate);
    xx_list_init(&options,sizeof(xx_meta),xx_meta_free_elem);
    if(!memory){xx_meta p;xx_meta_init(&p,XX_META_ID_OPT_UNPACK_PATH);xx_var_set_str(&p.var,argv[2]);xx_list_append(&options,&p);}
    if(argc>3){xx_meta m;xx_meta_init(&m,XX_META_ID_OPT_MEMORY_LIMIT);xx_var_set_u64(&m.var,strtoull(argv[3],NULL,10));xx_list_append(&options,&m);}
    if(argc>4){xx_meta m;xx_meta_init(&m,XX_META_ID_OPT_MAX_MEMBER_SIZE);xx_var_set_u64(&m.var,strtoull(argv[4],NULL,10));xx_list_append(&options,&m);}
    archive=xx_bitrock_create(io,base);f=(Abstractformat *)archive;
    if(memory&&!xx_io_memory_only_begin(&scope,UINT64_C(256)*1024*1024))return 93;
    if(argc>5&&atoi(argv[5]))xx_pd_stop(&pd);
    if(!f||!xx_format_is_valid(f,&pd)||!xx_format_handle_base_info(f,&pd)){ok=false;goto done;}
    printf("type=%d\n",(int)f->file_type);state=xx_format_create_archive_records_reading(f,&options,&pd);
    if(!state){ok=false;goto done;}
    while(state->has_record){const xx_archive_record *r=xx_format_get_current_archive_record(f,state);
        if(!r){ok=false;break;}printf("%s\n",xx_archive_record_get_original_name(r));++count;
        if(!xx_format_unpack_current_archive_record(f,state,&pd)){ok=false;break;}
        if(!xx_format_archive_record_move_to_next(f,state,&pd))break;
    }
    if(count!=xx_format_get_number_of_archive_records(f,&pd))ok=false;
done:
    if(state)xx_format_free_archive_records_reading(f,state);
    if(!ok&&pd.last_error)fprintf(stderr,"%s\n",pd.error_string);
    if(memory&&!xx_io_memory_only_end(&scope))ok=false;
    xx_bitrock_free(archive);xx_list_cleanup(&options);xx_io_close(io);return ok?0:1;
}
