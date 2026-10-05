/* SPDX-License-Identifier: MIT */
#include "xxfclib/formats/molebox/xx_molebox.h"
#include "xxfclib/memory/xx_memory.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static bool password_state_checks(Abstractformat*f,xx_pd_struct*pd){xx_archive_record_state*live=NULL,*replacement=NULL;xx_list_s opts;xx_meta password;char*saved;bool ok=false;
    saved=xx_str_dup(xx_format_get_password(f));if(!saved)return false;live=xx_format_create_archive_records_reading(f,NULL,pd);if(!live||!live->has_record)goto done;
    if(!xx_format_set_password(f,"incorrect-live-state-password")||xx_format_get_current_archive_record(f,live)||xx_format_archive_record_move_to_next(f,live,pd)||xx_format_unpack_current_archive_record(f,live,pd))goto done;
    (void)xx_format_handle_base_info(f,pd);if(xx_format_get_current_archive_record(f,live)||xx_format_archive_record_move_to_next(f,live,pd)||xx_format_unpack_current_archive_record(f,live,pd))goto done;
    if(!xx_format_set_password(f,saved)||!xx_format_handle_base_info(f,pd)||xx_format_get_current_archive_record(f,live)||xx_format_archive_record_move_to_next(f,live,pd))goto done;
    if(!xx_format_set_password(f,"incorrect-operation-password"))goto done;
    xx_list_init(&opts,sizeof(xx_meta),xx_meta_free_elem);xx_meta_init(&password,XX_META_ID_OPT_PASSWORD);
    /* A format's actual credential is passed through operation options. */
    xx_var_set_str(&password.var,saved);xx_list_append(&opts,&password);replacement=xx_format_create_archive_records_reading(f,&opts,pd);xx_list_cleanup(&opts);
    if(!replacement||!replacement->has_record||!xx_format_get_current_archive_record(f,replacement)||!xx_format_unpack_current_archive_record(f,replacement,pd)||!xx_format_get_password(f)||strcmp(xx_format_get_password(f),saved))goto done;
    xx_format_free_archive_records_reading(f,replacement);replacement=NULL;
    if(!xx_format_set_password(f,"incorrect-wide-operation-password"))goto done;
    {wchar_t*wide=xx_str_utf8_to_unicode(saved);if(!wide)goto done;xx_list_init(&opts,sizeof(xx_meta),xx_meta_free_elem);xx_meta_init(&password,XX_META_ID_OPT_PASSWORD);xx_var_set_wstr(&password.var,wide);xx_mem_free(wide);xx_list_append(&opts,&password);replacement=xx_format_create_archive_records_reading(f,&opts,pd);xx_list_cleanup(&opts);}
    if(!replacement||!xx_format_get_current_archive_record(f,replacement)||!xx_format_unpack_current_archive_record(f,replacement,pd))goto done;
    ok=true;printf("password_state_checks=1\n");
done:if(replacement)xx_format_free_archive_records_reading(f,replacement);if(live)xx_format_free_archive_records_reading(f,live);xx_str_free(saved);return ok;
}
int main(int argc,char **argv) {
    xx_io_device *io;xx_molebox *archive;Abstractformat *f;xx_archive_record_state *state=NULL;
    xx_list_s options;xx_pd_struct pd=xx_pd_init();xx_io_memory_only_scope scope={0};
    bool memory,ok=true,candidate;uint64_t count=0;int64_t base=0;
    if(argc<2||argc>7)return 90;memory=argc<3||!strcmp(argv[2],"-");
    io=xx_io_file_open(argv[1],"rb");if(!io)return 91;
    xx_io_seek64(io,3,SEEK_SET);candidate=xx_molebox_has_candidate_device(io,base);
    if(xx_io_tell(io)!=3){xx_io_close(io);return 92;}printf("candidate=%d\n",candidate);
    if(argc>3&&strcmp(argv[3],"-")){xx_file_type_t type=xx_molebox_detect_device(io,argv[3],&pd);printf("password_detect=%d\n",(int)type);if(xx_io_tell(io)!=3)return 94;}
    xx_list_init(&options,sizeof(xx_meta),xx_meta_free_elem);
    if(!memory){xx_meta p;xx_meta_init(&p,XX_META_ID_OPT_UNPACK_PATH);xx_var_set_str(&p.var,argv[2]);xx_list_append(&options,&p);}
    if(argc>4){xx_meta m;xx_meta_init(&m,XX_META_ID_OPT_MEMORY_LIMIT);xx_var_set_u64(&m.var,strtoull(argv[4],NULL,10));xx_list_append(&options,&m);}
    if(argc>5){xx_meta m;xx_meta_init(&m,XX_META_ID_OPT_MAX_MEMBER_SIZE);xx_var_set_u64(&m.var,strtoull(argv[5],NULL,10));xx_list_append(&options,&m);}
    archive=xx_molebox_create(io,base);f=(Abstractformat *)archive;
    if(argc>3&&strcmp(argv[3],"-"))xx_format_set_password(f,argv[3]);
    if(memory&&!xx_io_memory_only_begin(&scope,UINT64_C(256)*1024*1024))return 93;
    if(argc>6&&atoi(argv[6]))xx_pd_stop(&pd);
    if(!f||!xx_format_is_valid(f,&pd)||!xx_format_handle_base_info(f,&pd)){ok=false;goto done;}
    printf("type=%d\npassword=%s\n",(int)f->file_type,xx_format_get_password(f)?xx_format_get_password(f):"");state=xx_format_create_archive_records_reading(f,&options,&pd);
    if(!state){ok=false;goto done;}
    while(state->has_record){const xx_archive_record *r=xx_format_get_current_archive_record(f,state);
        if(!r||!xx_archive_record_get_meta_str(r,XX_META_ID_OPT_PASSWORD)){ok=false;break;}printf("%s\n",xx_archive_record_get_original_name(r));++count;
        if(!xx_format_unpack_current_archive_record(f,state,&pd)){ok=false;break;}
        if(!xx_format_archive_record_move_to_next(f,state,&pd))break;
    }
    if(count!=xx_format_get_number_of_archive_records(f,&pd))ok=false;
    if(ok&&!password_state_checks(f,&pd))ok=false;
done:
    if(state)xx_format_free_archive_records_reading(f,state);
    if(!ok&&pd.last_error)fprintf(stderr,"%s\n",pd.error_string);
    if(memory&&!xx_io_memory_only_end(&scope))ok=false;
    xx_molebox_free(archive);xx_list_cleanup(&options);xx_io_close(io);return ok?0:1;
}
