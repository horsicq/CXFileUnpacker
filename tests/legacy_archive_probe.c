/* SPDX-License-Identifier: MIT */
#include <xxfclib/formats/legacy_archive_engine/xx_legacy_archive_engine.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <shellapi.h>
#include <xxfclib/strings/xx_string.h>
#endif
static int probe_main(int argc,char **argv) {
    xx_io_device *io;Abstractformat *f;xx_archive_record_state *s=NULL;
    xx_pd_struct pd=xx_pd_init();xx_io_memory_only_scope scope={0};int count=0,result=1;bool began=false;
    if(argc<3||argc>4)return 2;io=xx_io_file_open(argv[2],"rb");if(!io)return 2;
    f=!strcmp(argv[1],"uharc")?xx_uharc_payload_create(io,0):xx_dgca_create(io,0);
    if(!f){xx_io_close(io);return 2;}if(argc==4&&!xx_format_set_password(f,argv[3]))goto done;
    if(!xx_io_memory_only_begin(&scope,UINT64_C(256)*1024*1024))goto done;began=true;
    if(!xx_format_handle_base_info(f,&pd)){fprintf(stderr,"open failed: %s\n",pd.error_string);goto done;}
    s=xx_format_create_archive_records_reading(f,NULL,&pd);if(!s)goto done;
    do {const xx_archive_record *r=xx_format_get_current_archive_record(f,s);if(!r)break;
        printf("%s\n",xx_archive_record_get_original_name(r));
        if(!xx_format_unpack_current_archive_record(f,s,&pd)){fprintf(stderr,"decode failed: %s\n",pd.error_string);goto done;}++count;
    }while(xx_format_archive_record_move_to_next(f,s,&pd));
    result=count==(int)xx_format_get_number_of_archive_records(f,&pd)?0:1;
done:if(s)xx_format_free_archive_records_reading(f,s);xx_legacy_archive_free(f);xx_io_close(io);
    if(began&&!xx_io_memory_only_end(&scope))result=1;printf("%d members, result%d\n",count,result);return result;
}
int main(int argc,char **argv) {
#ifdef _WIN32
    int count=0,i,result;wchar_t **wide=CommandLineToArgvW(GetCommandLineW(),&count);char **utf8;
    (void)argc;(void)argv;if(!wide)return 2;
    utf8=calloc((size_t)count+1,sizeof(*utf8));if(!utf8){LocalFree(wide);return 2;}
    for(i=0;i<count;++i)if(!(utf8[i]=xx_str_unicode_to_utf8(wide[i])))break;
    result=i==count?probe_main(count,utf8):2;
    for(i=0;i<count;++i)xx_str_free(utf8[i]);free(utf8);LocalFree(wide);return result;
#else
    return probe_main(argc,argv);
#endif
}
