/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT */
#include <xxfclib/formats/superdat/xx_superdat.h>
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv) {
    xx_io_device *io;xx_superdat *a;xx_archive_record_state *s;xx_pd_struct pd=xx_pd_init();
    xx_io_memory_only_scope scope={0};xx_meta option;xx_list_s options={0};int count=0,result=1;int64_t saved;
    if(argc<2||argc>3)return 2;io=xx_io_file_open(argv[1],"rb");if(!io)return 2;
    xx_io_seek64(io,7,SEEK_SET);saved=xx_io_tell(io);
    if(!xx_superdat_has_candidate_device(io,0)||xx_io_tell(io)!=saved){fprintf(stderr,"gate/cursor failed\n");xx_io_close(io);return 1;}
    a=xx_superdat_create(io,0);if(!a){xx_io_close(io);return 2;}
    if(!xx_format_is_valid(&a->format,&pd)||xx_io_tell(io)!=saved){fprintf(stderr,"layout/cursor failed\n");goto done;}
    if(argc==3){xx_meta_init(&option,XX_META_ID_OPT_UNPACK_PATH);xx_var_set_str(&option.var,argv[2]);options.data=(uint8_t*)&option;options.count=options.capacity=1;options.elem_size=sizeof(option);}
    else if(!xx_io_memory_only_begin(&scope,UINT64_C(256)*1024*1024))goto done;
    s=xx_format_create_archive_records_reading(&a->format,argc==3?&options:NULL,&pd);if(!s)goto endscope;
    do {const xx_archive_record *r=xx_format_get_current_archive_record(&a->format,s);
        if(!r)break;
        printf("%s\n",xx_archive_record_get_original_name(r));
        if(!xx_format_unpack_current_archive_record(&a->format,s,&pd)||xx_io_tell(io)!=saved){fprintf(stderr,"decode/cursor failed: %s\n",pd.error_string);goto records;}
        ++count;
    }while(xx_format_archive_record_move_to_next(&a->format,s,&pd));
    result=count==(int)xx_format_get_number_of_archive_records(&a->format,&pd)?0:1;
records:xx_format_free_archive_records_reading(&a->format,s);
endscope:if(argc!=3&&!xx_io_memory_only_end(&scope))result=1;
    if(argc==3)xx_meta_cleanup(&option);
done:xx_superdat_free(a);xx_io_close(io);printf("%d members, result %d\n",count,result);return result;
}
