/* SPDX-License-Identifier: MIT. Borrowed I/O, RAM-only TEST and real bytes. */
#include <xxfclib/formats/ue2_games/xx_ue2_games.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define REQUIRE(x) do { ++checks;if(!(x)){fprintf(stderr,"check%u line%u: %s\n",checks,__LINE__,#x);goto done;} }while(0)
int main(int argc,char **argv) {
 xx_io_device *d=NULL;xx_ue2_games *reader=NULL;Abstractformat *f=NULL;xx_archive_record_state *st=NULL;xx_pd_struct pd=xx_pd_init();xx_io_memory_only_scope scope={0};xx_list_s options;xx_meta output;xx_var v;bool scoped=false,have_options=false;int result=1;unsigned count=0,passwords=0;xx_file_type_t type;
 REQUIRE(argc>=3);type=(xx_file_type_t)strtoul(argv[2],NULL,10);REQUIRE((d=xx_io_file_open(argv[1],"rb"))!=NULL);REQUIRE(xx_io_seek64(d,11,SEEK_SET)==0);
 REQUIRE((reader=xx_ue2_games_create(d,0,type))!=NULL);f=&reader->format;
 if(argc>3&&argv[3][0]){xx_var_init(&v);REQUIRE(xx_var_set_str(&v,argv[3]));REQUIRE(xx_format_set_extra_parameter(f,XX_META_ID_OPT_PASSWORD,&v));xx_var_cleanup(&v);}
 if(argc>5){xx_var_init(&v);xx_var_set_u64(&v,strtoull(argv[5],NULL,10));REQUIRE(xx_format_set_extra_parameter(f,XX_META_ID_OPT_MEMORY_LIMIT,&v));xx_var_cleanup(&v);}
 REQUIRE(xx_io_memory_only_begin(&scope,0));scoped=true;REQUIRE(xx_format_is_valid(f,&pd));REQUIRE(xx_io_tell(d)==11);REQUIRE(xx_format_handle_base_info(f,&pd));REQUIRE(xx_io_tell(d)==11);
 REQUIRE((st=xx_format_create_archive_records_reading(f,NULL,&pd))!=NULL);
 while(st->has_record){const xx_archive_record *record=xx_format_get_current_archive_record(f,st);REQUIRE(record!=NULL);if(xx_archive_record_find_meta(record,XX_META_ID_PASSWORD))++passwords;REQUIRE(xx_format_unpack_current_archive_record(f,st,&pd));REQUIRE(xx_io_tell(d)==11);++count;if(!xx_format_archive_record_move_to_next(f,st,&pd))break;}
 REQUIRE(count==f->number_of_archive_records);xx_format_free_archive_records_reading(f,st);st=NULL;REQUIRE(xx_io_memory_only_used()==0);REQUIRE(xx_io_memory_only_end(&scope));scoped=false;
 /* Early cancellation must leave the caller's stream cursor unchanged. */
 {xx_pd_struct stopped=xx_pd_init();xx_pd_stop(&stopped);REQUIRE(!f->check_is_valid(f,&stopped));REQUIRE(xx_io_tell(d)==11);}
 if(argc>4&&argv[4][0]){REQUIRE(xx_list_init(&options,sizeof(xx_meta),NULL));have_options=true;xx_meta_init(&output,XX_META_ID_OPT_UNPACK_PATH);REQUIRE(xx_var_set_str(&output.var,argv[4]));REQUIRE(xx_list_append(&options,&output));
  REQUIRE((st=xx_format_create_archive_records_reading(f,&options,&pd))!=NULL);while(st->has_record){REQUIRE(xx_format_unpack_current_archive_record(f,st,&pd));REQUIRE(xx_io_tell(d)==11);if(!xx_format_archive_record_move_to_next(f,st,&pd))break;}}
 printf("{\"checks\":%u,\"members\":%u,\"password_metadata\":%u,\"memory_only\":true}\n",checks,count,passwords);result=0;
done:if(st)xx_format_free_archive_records_reading(f,st);if(have_options){size_t i;for(i=0;i<options.count;++i)xx_meta_cleanup((xx_meta *)xx_list_at(&options,i));xx_list_clear(&options);}if(scoped)(void)xx_io_memory_only_end(&scope);xx_ue2_games_free(reader);if(d)xx_io_close(d);return result;
}
